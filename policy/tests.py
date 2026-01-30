from django.test import TestCase
from django.contrib.auth import get_user_model
from policy.models import Policy, Control, Rule, Threshold, Violation
from policy.services import RuleEngine
from django.utils import timezone


class PolicyEngineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', 't@example.com', 'pass')
        self.policy = Policy.objects.create(name='Test Policy', description='For unit tests')
        self.control = Control.objects.create(policy=self.policy, name='File Size Control', severity='high')
        # Rule: file.size > 1000
        self.rule = Rule.objects.create(control=self.control, name='Large file', left_operand='file.size', operator='>', right_value=1000)

    def test_no_violation_when_rule_passes(self):
        engine = RuleEngine()
        # condition is true (2000 > 1000) -> no violations
        ctx = {'file': {'size': 2000}}
        result = engine.evaluate_policy(self.policy, ctx, user=self.user)
        self.assertIn('violations', result)
        self.assertEqual(len(result['violations']), 0)

    def test_violation_when_rule_fails(self):
        engine = RuleEngine()
        # condition is false (500 > 1000 is False) -> rule violation recorded
        ctx = {'file': {'size': 500}}
        result = engine.evaluate_policy(self.policy, ctx, user=self.user)
        self.assertIn('violations', result)
        self.assertTrue(len(result['violations']) >= 1)

    def test_threshold_count_breach(self):
        # Prepare threshold: 3 events in last 60 seconds
        thr = Threshold.objects.create(control=self.control, threshold_type='count', value=3, window_seconds=60)
        # Create historical violations for this control
        now = timezone.now()
        for i in range(3):
            Violation.objects.create(timestamp=now, user=self.user, policy=self.policy, control=self.control, rule=None, severity='high', evidence={'test': i})
        engine = RuleEngine()
        ctx = {'file': {'size': 500}}
        result = engine.evaluate_policy(self.policy, ctx, user=self.user)
        # threshold is breached; expect synthesized violation evidence
        self.assertTrue(any(v['explanation'].get('reason') == 'threshold_breached' for v in result['violations']))
