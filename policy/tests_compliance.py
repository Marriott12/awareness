from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from policy.models import Policy, Control, Rule, HumanLayerEvent, Violation
from policy.compliance import ComplianceEngine


class ComplianceEngineTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('comp', 'c@x.com', 'pw')
        self.policy = Policy.objects.create(name='Telemetry Policy')
        self.ctrl = Control.objects.create(policy=self.policy, name='Auth Control', severity='high')
        # Example rules (engine records violations when a rule evaluates False).
        # To express forbidden condition "event.type == 'auth' and remote == 1.2.3.4"
        # create rules that assert the *allowed* state; when these expectations fail a violation is recorded.
        self.rule = Rule.objects.create(control=self.ctrl, name='Expect non-auth', left_operand='event.type', operator='!=', right_value='auth')
        self.rule2 = Rule.objects.create(control=self.ctrl, name='Expect other IP', left_operand='detail.remote_addr', operator='!=', right_value='1.2.3.4')

    def test_evaluate_event_creates_violation(self):
        # create an event with matching details
        ev = HumanLayerEvent.objects.create(user=self.user, event_type='auth', source='auth.login', summary='test', details={'remote_addr': '1.2.3.4'})
        engine = ComplianceEngine()
        res = engine.evaluate_event(ev, self.policy)
        self.assertTrue(len(res['violations']) >= 1)
        # violation created in DB
        self.assertTrue(Violation.objects.filter(control=self.ctrl).exists())
