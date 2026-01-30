"""Policy evaluation engine (deterministic, explainable).

This module implements a `RuleEngine` which deterministically evaluates
`Policy` -> `Control` -> `Rule` hierarchies against a provided `context`.

Design goals:
- Deterministic operators only (no ML)
- Explainable output: for each evaluated rule provide reason, input values, and evidence
- Produce `Violation` records (audit-ready)
"""
import re
import logging
from typing import Any, Dict, Tuple, List
from django.utils import timezone
from .models import Policy, Control, Rule, Threshold, Violation

logger = logging.getLogger(__name__)


class RuleEngine:
    OPERATORS = {
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
        '>': lambda a, b: a > b,
        '<': lambda a, b: a < b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b,
        'in': lambda a, b: a in b if b is not None else False,
        'not_in': lambda a, b: a not in b if b is not None else False,
    }

    def __init__(self, recorder=None):
        """`recorder` should implement `record_violation(violation_data)`.

        By default the engine will create `Violation` DB records when violations occur.
        """
        self.recorder = recorder or self._default_recorder

    def _default_recorder(self, data: Dict[str, Any]):
        # Persist a Violation to the DB (audit trail)
        Violation.objects.create(**data)

    def _get_value(self, context: Dict[str, Any], dotted: str):
        """Extract value from context using dotted path, return (found, value).

        This function never raises; missing paths return (False, None) to keep evaluation deterministic.
        """
        if dotted is None or dotted == '':
            return False, None
        parts = dotted.split('.')
        cur = context
        try:
            for p in parts:
                if isinstance(cur, dict):
                    cur = cur.get(p)
                else:
                    cur = getattr(cur, p, None)
            return True, cur
        except Exception:
            return False, None

    def _eval_rule(self, rule: Rule, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Evaluate a single `Rule` against `context`.

        Returns (result, explanation) where explanation is an audit-friendly dict.
        """
        found, left_val = self._get_value(context, rule.left_operand)
        right_val = rule.right_value
        explanation = {
            'rule_id': rule.id,
            'rule_name': rule.name,
            'left_operand': rule.left_operand,
            'left_found': found,
            'left_value': left_val,
            'operator': rule.operator,
            'right_value': right_val,
        }

        if not found:
            explanation['result'] = False
            explanation['reason'] = 'left_operand_not_found'
            return False, explanation

        if rule.operator == 'regex':
            try:
                pattern = re.compile(right_val)
                match = bool(pattern.search(str(left_val)))
                explanation['result'] = match
                explanation['reason'] = 'regex_match' if match else 'regex_no_match'
                return match, explanation
            except Exception as e:
                explanation['result'] = False
                explanation['reason'] = f'regex_error: {str(e)}'
                return False, explanation

        # binary operators
        op = rule.operator
        if op in self.OPERATORS:
            try:
                res = self.OPERATORS[op](left_val, right_val)
                explanation['result'] = bool(res)
                explanation['reason'] = 'comparison'
                return bool(res), explanation
            except Exception as e:
                explanation['result'] = False
                explanation['reason'] = f'operator_error: {str(e)}'
                return False, explanation

        explanation['result'] = False
        explanation['reason'] = 'unsupported_operator'
        return False, explanation

    def evaluate_policy(self, policy: Policy, context: Dict[str, Any], user=None) -> Dict[str, Any]:
        """Evaluate an entire `Policy` object and return structured, explainable results.

        The returned dict has:
        - `policy`: policy id/name
        - `controls`: list of controls, each with `rules` evaluations
        - `violations`: list of recorded violations (audit-friendly summaries)
        """
        results = {'policy_id': policy.id, 'policy_name': policy.name, 'controls': [], 'violations': []}
        for control in policy.controls.filter(active=True).order_by('order', 'id'):
            cres = {'control_id': control.id, 'control_name': control.name, 'severity': control.severity, 'rules': []}
            # Evaluate rules in order
            for rule in control.rules.filter(enabled=True).order_by('order', 'id'):
                ok, explanation = self._eval_rule(rule, context)
                cres['rules'].append(explanation)
                if not ok:
                    # violation: record with evidence
                    evidence = {
                        'timestamp': timezone.now().isoformat(),
                        'policy': policy.name,
                        'control': control.name,
                        'rule': rule.name,
                        'explanation': explanation,
                        'context_snapshot': context,
                    }
                    violation_data = {
                        'timestamp': timezone.now(),
                        'user': user,
                        'policy': policy,
                        'control': control,
                        'rule': rule,
                        'severity': control.severity,
                        'evidence': evidence,
                    }
                    try:
                        self.recorder(violation_data)
                    except Exception as e:
                        logger.exception('Failed to record violation: %s', e)
                    results['violations'].append(evidence)
            # Deterministic threshold checks
            try:
                thr = getattr(control, 'threshold', None)
                if thr is not None:
                    # Example: count threshold — count violations for this control in the past window_seconds
                    if thr.threshold_type == 'count' and thr.window_seconds:
                        window_start = timezone.now() - timezone.timedelta(seconds=thr.window_seconds)
                        recent_count = Violation.objects.filter(control=control, timestamp__gte=window_start).count()
                        cres['threshold_check'] = {'type': 'count', 'value': thr.value, 'window_seconds': thr.window_seconds, 'recent_count': recent_count}
                        if recent_count >= thr.value:
                            # threshold breached -> produce synthesized violation evidence
                            evidence = {
                                'timestamp': timezone.now().isoformat(),
                                'policy': policy.name,
                                'control': control.name,
                                'rule': None,
                                'explanation': {'reason': 'threshold_breached', 'recent_count': recent_count, 'threshold': thr.value},
                                'context_snapshot': context,
                            }
                            violation_data = {
                                'timestamp': timezone.now(),
                                'user': user,
                                'policy': policy,
                                'control': control,
                                'rule': None,
                                'severity': control.severity,
                                'evidence': evidence,
                            }
                            try:
                                self.recorder(violation_data)
                            except Exception as e:
                                logger.exception('Failed to record threshold violation: %s', e)
                            results['violations'].append(evidence)
            except Exception:
                logger.exception('Error while evaluating threshold for control %s', control)
            results['controls'].append(cres)

        return results
