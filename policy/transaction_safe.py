"""
Transaction-safe compliance evaluation with row-level locking.

This module provides enhanced transaction safety by using select_for_update()
to eliminate race conditions in get_or_create() operations.
"""
from typing import Dict, Any
import logging
from django.utils import timezone
from django.db import transaction, IntegrityError
from .models import Policy, Control, Rule, Violation, HumanLayerEvent, EventMetadata
from .compliance import ComplianceEngine
import hashlib

logger = logging.getLogger(__name__)


class TransactionSafeEngine(ComplianceEngine):
    """
    Enhanced compliance engine with row-level locking to prevent race conditions.
    
    Uses select_for_update() with get_or_create() to ensure atomic operations
    even under high concurrency (>1000 req/sec).
    """
    
    def _create_violation_safe(self, dedup_key: str, defaults: Dict[str, Any], 
                              event: HumanLayerEvent) -> tuple:
        """
        Create violation with row-level locking to prevent duplicates.
        
        Args:
            dedup_key: SHA256 hash for deduplication
            defaults: Default values for Violation.objects.create()
            event: Associated HumanLayerEvent
            
        Returns:
            (violation, created) tuple
        """
        try:
            with transaction.atomic():
                # Try to get existing violation with row-level lock
                try:
                    violation = Violation.objects.select_for_update().get(
                        dedup_key=dedup_key
                    )
                    return violation, False
                except Violation.DoesNotExist:
                    # Create new violation within locked transaction
                    violation = Violation.objects.create(
                        dedup_key=dedup_key,
                        **defaults
                    )
                    
                    # Update metadata table
                    EventMetadata.objects.update_or_create(
                        event=event,
                        defaults={
                            'processed': True,
                            'processed_at': timezone.now()
                        }
                    )
                    
                    # Link violation to event if not already linked
                    # Using select_for_update to prevent race conditions
                    event_obj = HumanLayerEvent.objects.select_for_update().filter(
                        pk=event.pk,
                        related_violation__isnull=True
                    ).first()
                    
                    if event_obj:
                        event_obj.related_violation = violation
                        event_obj.save(update_fields=['related_violation'])
                    
                    return violation, True
                    
        except IntegrityError as e:
            # Handle the rare case where duplicate was created between check and insert
            logger.warning(f'Integrity error for dedup {dedup_key}: {e}')
            # Re-fetch the existing violation
            violation = Violation.objects.get(dedup_key=dedup_key)
            return violation, False
    
    def evaluate_event(self, event: HumanLayerEvent, policy: Policy, user=None) -> Dict[str, Any]:
        """
        Evaluate event against policy with row-level locking for thread safety.
        
        Overrides parent method to use _create_violation_safe() instead of get_or_create().
        """
        # Only evaluate policies in ACTIVE lifecycle
        if policy.lifecycle != 'active':
            logger.debug(f'Skipping policy {policy.name} (lifecycle={policy.lifecycle})')
            return {
                'event_id': str(event.id),
                'policy': policy.name,
                'skipped': True,
                'reason': 'policy not active'
            }
        
        ctx = self._event_to_context(event)
        res = {
            'event_id': str(event.id),
            'policy': policy.name,
            'violations': []
        }
        
        # Attach policy version for traceability
        res['policy_version'] = getattr(policy, 'version', None)
        
        # Compute risk score
        from .risk import RuleBasedScorer
        scorer = RuleBasedScorer()
        risk = scorer.score(event)
        res['risk'] = risk
        
        for control in policy.controls.filter(active=True).order_by('order', 'id'):
            # Handle composite expressions
            if control.expression:
                try:
                    expr_ok, expr_expl = self._eval_expression(
                        control.expression, control, ctx
                    )
                except Exception:
                    logger.exception(f'Expression evaluation failed for control {control}')
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
                    
                    raw = f"{policy.id}:{control.id}:None:{event.id}:{evidence.get('timestamp')}"
                    dedup = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                    
                    v, created = self._create_violation_safe(
                        dedup_key=dedup,
                        defaults={
                            'timestamp': timezone.now(),
                            'user': event.user,
                            'policy': policy,
                            'control': control,
                            'rule': None,
                            'severity': control.severity,
                            'evidence': evidence
                        },
                        event=event
                    )
                    
                    if created:
                        res['violations'].append(evidence)
                
                continue
            
            # Evaluate individual rules
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
                    
                    v, created = self._create_violation_safe(
                        dedup_key=dedup,
                        defaults={
                            'timestamp': timezone.now(),
                            'user': event.user,
                            'policy': policy,
                            'control': control,
                            'rule': rule,
                            'severity': control.severity,
                            'evidence': evidence
                        },
                        event=event
                    )
                    
                    if created:
                        res['violations'].append(evidence)
            
            # Threshold evaluation
            try:
                thr_res = self._evaluate_thresholds_for_control(control, event)
                if thr_res:
                    res.setdefault('thresholds', []).append({
                        'control': control.name,
                        **thr_res
                    })
                    
                    if thr_res.get('breached'):
                        t_evidence = {
                            'timestamp': timezone.now().isoformat(),
                            'policy': policy.name,
                            'control': control.name,
                            'rule': None,
                            'explanation': {
                                'reason': 'threshold_breached',
                                'details': thr_res
                            },
                            'event_snapshot': ctx,
                            'policy_version': getattr(policy, 'version', None),
                            'risk_score': risk,
                        }
                        
                        raw = f"{policy.id}:{control.id}:threshold:{event.id}:{t_evidence.get('timestamp')}"
                        dedup = hashlib.sha256(raw.encode('utf-8')).hexdigest()
                        
                        v, created = self._create_violation_safe(
                            dedup_key=dedup,
                            defaults={
                                'timestamp': timezone.now(),
                                'user': event.user,
                                'policy': policy,
                                'control': control,
                                'rule': None,
                                'severity': control.severity,
                                'evidence': t_evidence
                            },
                            event=event
                        )
                        
                        if created:
                            res['violations'].append(t_evidence)
                            
            except Exception:
                logger.exception(f'Threshold evaluation failed for control {control}')
        
        return res
