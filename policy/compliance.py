"""Compliance evaluation engine: evaluate human-layer telemetry against policy rules.

Design: deterministic, explainable. Uses `RuleEngine` to evaluate `Rule` objects
against a context constructed from `HumanLayerEvent` instances. When rules fail,
creates `Violation` records with evidence and links the generated Evidence.
"""
from typing import Dict, Any
import logging
from django.utils import timezone
from .models import Policy, Control, Rule, Violation, HumanLayerEvent
from .services import RuleEngine
from .risk import RuleBasedScorer
from typing import Tuple, List
from django.db import transaction, IntegrityError
import hashlib

logger = logging.getLogger(__name__)


class ComplianceEngine:
    def __init__(self, recorder=None):
        self.rule_engine = RuleEngine(recorder=recorder)

    def _event_to_context(self, event: HumanLayerEvent) -> Dict[str, Any]:
        # Provide predictable dotted-path access to event data for rules
        ctx = {
            'event': {
                'id': str(event.id),
                'timestamp': event.timestamp.isoformat(),
                'type': event.event_type,
                'source': event.source,
                'summary': event.summary,
                'details': event.details,
                'user': getattr(event.user, 'username', None),
            }
        }
        # Flatten details into top-level `detail` for convenience
        if isinstance(event.details, dict):
            ctx.update({'detail': event.details})
        return ctx

    def evaluate_event(self, event: HumanLayerEvent, policy: Policy, user=None) -> Dict[str, Any]:
        # Only evaluate policies in ACTIVE lifecycle
        if policy.lifecycle != 'active':
            logger.debug(f'Skipping policy {policy.name} (lifecycle={policy.lifecycle}, must be active)')
            return {'event_id': str(event.id), 'policy': policy.name, 'skipped': True, 'reason': 'policy not active'}
        
        ctx = self._event_to_context(event)
        res = {'event_id': str(event.id), 'policy': policy.name, 'violations': []}
        # Attach policy version for traceability
        res['policy_version'] = getattr(policy, 'version', None)
        # compute risk score and include in evidence
        scorer = RuleBasedScorer()
        risk = scorer.score(event)
        res['risk'] = risk
        for control in policy.controls.filter(active=True).order_by('order', 'id'):
            # If the control defines a composite expression, evaluate it as a whole.
            if control.expression:
                try:
                    expr_ok, expr_expl = self._eval_expression(control.expression, control, ctx)
                except Exception:
                    logger.exception('Expression evaluation failed for control %s', control)
                    expr_ok, expr_expl = False, {'error': 'expression_evaluation_failed'}

                if not expr_ok:
                    evidence = {
                        'timestamp': timezone.now().isoformat(),
                        'policy': policy.name,
                        'control': control.name,
                        'rule': None,
                        'explanation': {'composite_expression': expr_expl},
                        'event_snapshot': ctx,
                        'policy_version': getattr(policy, 'version', None),
                        'risk_score': risk,
                    }
                    # create dedup key for idempotency
                    raw = f"{policy.id}:{control.id}:None:{event.id}:{evidence.get('timestamp')}"
                    dedup = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                    try:
                        with transaction.atomic():
                            v, created = Violation.objects.get_or_create(dedup_key=dedup, defaults={
                                'timestamp': timezone.now(), 'user': event.user, 'policy': policy, 'control': control, 'rule': None, 'severity': control.severity, 'evidence': evidence, 'dedup_key': dedup
                            })
                            if created:
                                # Update metadata table, not immutable event
                                from .models import EventMetadata
                                EventMetadata.objects.update_or_create(
                                    event=event,
                                    defaults={'processed': True, 'processed_at': timezone.now()}
                                )
                                # Link violation to event via ForeignKey (still allowed on create)
                                HumanLayerEvent.objects.filter(pk=event.pk, related_violation__isnull=True).update(related_violation=v)
                                res['violations'].append(evidence)
                    except IntegrityError:
                        logger.warning('Duplicate violation suppressed for dedup %s', dedup)
                # continue to next control after handling composite expression
                continue

            # Fallback: evaluate individual rules and create per-rule violations as before
            for rule in control.rules.filter(enabled=True).order_by('order', 'id'):
                ok, explanation = self.rule_engine._eval_rule(rule, ctx)
                if not ok:
                    evidence = {
                        'timestamp': timezone.now().isoformat(),
                        'policy': policy.name,
                        'control': control.name,
                        'rule': rule.name,
                        'explanation': explanation,
                        'event_snapshot': ctx,
                        'policy_version': getattr(policy, 'version', None),
                        'risk_score': risk,
                    }
                    raw = f"{policy.id}:{control.id}:{rule.id}:{event.id}:{evidence.get('timestamp')}"
                    dedup = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                    try:
                        with transaction.atomic():
                            v, created = Violation.objects.get_or_create(dedup_key=dedup, defaults={
                                'timestamp': timezone.now(), 'user': event.user, 'policy': policy, 'control': control, 'rule': rule, 'severity': control.severity, 'evidence': evidence, 'dedup_key': dedup
                            })
                            if created:
                                # Update metadata table, not immutable event
                                from .models import EventMetadata
                                EventMetadata.objects.update_or_create(
                                    event=event,
                                    defaults={'processed': True, 'processed_at': timezone.now()}
                                )
                                # Link violation to event via ForeignKey (set on create, never update)
                                if not event.related_violation:
                                    HumanLayerEvent.objects.filter(pk=event.pk, related_violation__isnull=True).update(related_violation=v)
                                res['violations'].append(evidence)
                    except IntegrityError:
                        logger.warning('Duplicate violation suppressed for dedup %s', dedup)
            # Threshold evaluation for this control
            try:
                thr_res = self._evaluate_thresholds_for_control(control, event)
                if thr_res:
                    res.setdefault('thresholds', []).append({ 'control': control.name, **thr_res })
                    if thr_res.get('breached'):
                        # synthesize a threshold violation
                        t_evidence = {
                            'timestamp': timezone.now().isoformat(),
                            'policy': policy.name,
                            'control': control.name,
                            'rule': None,
                            'explanation': {'reason': 'threshold_breached', 'details': thr_res},
                            'event_snapshot': ctx,
                            'policy_version': getattr(policy, 'version', None),
                            'risk_score': risk,
                        }
                        raw = f"{policy.id}:{control.id}:threshold:{event.id}:{t_evidence.get('timestamp')}"
                        dedup = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                        try:
                            with transaction.atomic():
                                v, created = Violation.objects.get_or_create(dedup_key=dedup, defaults={
                                    'timestamp': timezone.now(), 'user': event.user, 'policy': policy, 'control': control, 'rule': None, 'severity': control.severity, 'evidence': t_evidence, 'dedup_key': dedup
                                })
                                if created:
                                    res['violations'].append(t_evidence)
                                    # Update metadata, not event
                                    from .models import EventMetadata
                                    EventMetadata.objects.update_or_create(
                                        event=event,
                                        defaults={'processed': True, 'processed_at': timezone.now()}
                                    )
                                    if not event.related_violation:
                                        HumanLayerEvent.objects.filter(pk=event.pk, related_violation__isnull=True).update(related_violation=v)
                        except IntegrityError:
                            logger.warning('Duplicate threshold violation suppressed for dedup %s', dedup)
            except Exception:
                logger.exception('Threshold evaluation failed for control %s', control)
        return res

    def evaluate_unprocessed(self, policy: Policy, limit=100):
        # Evaluate up to `limit` unprocessed events against the policy
        from .models import EventMetadata
        # Get events without metadata or with processed=False
        events_with_metadata = EventMetadata.objects.filter(processed=True).values_list('event_id', flat=True)
        events = HumanLayerEvent.objects.exclude(id__in=events_with_metadata).order_by('timestamp')[:limit]
        out = []
        for ev in events:
            try:
                o = self.evaluate_event(ev, policy)
                out.append(o)
            except Exception:
                logger.exception('Failed to evaluate event %s', ev)
        return out

    def _evaluate_thresholds_for_control(self, control: Control, event: HumanLayerEvent, window_seconds: int = None):
        """Return a dict with threshold evaluation details for the control.

        Supports count (already present) and percent thresholds: percent = matching / total * 100
        Matching is defined as violations for the control in window.
        """
        results = {}
        thr = getattr(control, 'threshold', None)
        if thr is None:
            return results

        if thr.threshold_type == 'count' and thr.window_seconds:
            window_start = timezone.now() - timezone.timedelta(seconds=thr.window_seconds)
            recent_count = Violation.objects.filter(control=control, timestamp__gte=window_start).count()
            results = {'type': 'count', 'value': thr.value, 'window_seconds': thr.window_seconds, 'recent_count': recent_count, 'breached': recent_count >= thr.value}

        elif thr.threshold_type == 'percent' and thr.window_seconds:
            # percent = (violations for control in window) / (total events for the user in window) * 100
            window_start = timezone.now() - timezone.timedelta(seconds=thr.window_seconds)
            recent_control_violations = Violation.objects.filter(control=control, timestamp__gte=window_start).count()
            total_events = HumanLayerEvent.objects.filter(user=event.user, timestamp__gte=window_start).count()
            percent = (recent_control_violations / total_events * 100.0) if total_events > 0 else 0.0
            breached = percent >= float(thr.value)
            results = {'type': 'percent', 'value': thr.value, 'window_seconds': thr.window_seconds, 'recent_percent': percent, 'total_events': total_events, 'breached': breached}

        elif thr.threshold_type == 'time_window' and thr.window_seconds:
            # time_window: evaluate whether X events occurred within window_seconds; interpret value as count
            window_start = timezone.now() - timezone.timedelta(seconds=thr.window_seconds)
            recent_count = Violation.objects.filter(control=control, timestamp__gte=window_start).count()
            breached = recent_count >= thr.value
            results = {'type': 'time_window', 'value': thr.value, 'window_seconds': thr.window_seconds, 'recent_count': recent_count, 'breached': breached}

        return results

    def _eval_expression(self, expr: Dict[str, Any], control: Control, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Recursively evaluate a composite boolean `expr` for the given `control`.

        Expression format examples:
        - {'op': 'and', 'items': [ { 'rule': 'Rule A' }, { 'op': 'or', 'items': [ {'rule':'Rule B'}, {'rule':'Rule C'} ] } ] }
        - {'op': 'not', 'items': [ { 'rule': 'Rule X' } ] }

        Returns (ok, explanation) where `ok` follows the same semantics as `_eval_rule` (True = rule/expression passed).
        """
        op = expr.get('op')
        items = expr.get('items', [])
        explanations: List[Dict[str, Any]] = []

        # Helper to evaluate a single item which may be a rule reference or a nested expression
        def _eval_item(item) -> Tuple[bool, Dict[str, Any]]:
            if not isinstance(item, dict):
                return False, {'error': 'invalid_item', 'item': item}
            # support referencing rules by id for more robust expressions
            if 'rule_id' in item:
                rule_id = item.get('rule_id')
                try:
                    rule = control.rules.get(pk=rule_id)
                except Exception:
                    return False, {'rule_id': rule_id, 'result': False, 'reason': 'rule_not_found'}
                ok, expl = self.rule_engine._eval_rule(rule, context)
                expl['rule_ref'] = f'id:{rule_id}'
                return ok, expl
            if 'rule' in item:
                rule_name = item.get('rule')
                try:
                    rule = control.rules.get(name=rule_name)
                except Exception:
                    return False, {'rule': rule_name, 'result': False, 'reason': 'rule_not_found'}
                ok, expl = self.rule_engine._eval_rule(rule, context)
                # enrich explanation with rule_name for clarity
                expl['rule_ref'] = rule_name
                return ok, expl
            # nested expression
            if 'op' in item:
                return self._eval_expression(item, control, context)
            return False, {'error': 'unsupported_item', 'item': item}

        # Evaluate all child items
        for it in items:
            ok, expl = _eval_item(it)
            explanations.append(expl)

        # Combine according to op
        result = False
        if op == 'and':
            result = all(e.get('result', False) for e in explanations)
        elif op == 'or':
            result = any(e.get('result', False) for e in explanations)
        elif op == 'not':
            # 'not' expects a single item; invert its boolean result
            if len(explanations) != 1:
                return False, {'error': 'not_requires_single_item', 'items': explanations}
            result = not bool(explanations[0].get('result', False))
        else:
            return False, {'error': 'unsupported_op', 'op': op, 'items': explanations}

        return result, {'op': op, 'result': result, 'items': explanations}
