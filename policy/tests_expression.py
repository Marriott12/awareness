from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from policy.models import Policy, Control, Rule, HumanLayerEvent, Violation
from policy.compliance import ComplianceEngine


class ExpressionEvaluationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('expr', 'e@x.com', 'pw')
        self.policy = Policy.objects.create(name='Expr Policy', lifecycle='active')
        self.ctrl = Control.objects.create(policy=self.policy, name='Expr Control', severity='medium')
        # Rules: these assert allowed states; evaluation returns False when the expectation is violated
        self.rule_a = Rule.objects.create(control=self.ctrl, name='Rule A', left_operand='event.type', operator='!=', right_value='auth')
        self.rule_b = Rule.objects.create(control=self.ctrl, name='Rule B', left_operand='detail.remote_addr', operator='!=', right_value='1.2.3.4')
        self.rule_c = Rule.objects.create(control=self.ctrl, name='Rule C', left_operand='detail.user_agent', operator='!=', right_value='bot')

    def test_expression_by_name_creates_violation(self):
        # composite: AND( Rule A, OR(Rule B, Rule C) )
        expr = {'op': 'and', 'items': [ {'rule': 'Rule A'}, {'op': 'or', 'items': [ {'rule': 'Rule B'}, {'rule': 'Rule C'} ] } ] }
        self.ctrl.expression = expr
        self.ctrl.save()

        ev = HumanLayerEvent.objects.create(user=self.user, event_type='auth', source='svc', summary='x', details={'remote_addr': '1.2.3.4'})
        engine = ComplianceEngine()
        res = engine.evaluate_event(ev, self.policy)
        # expression should evaluate False -> synthesized violation created
        self.assertTrue(len(res['violations']) >= 1)
        self.assertTrue(Violation.objects.filter(control=self.ctrl).exists())

    def test_expression_by_id_creates_violation(self):
        # Use rule_id references
        expr = {'op': 'and', 'items': [ {'rule_id': self.rule_a.id}, {'op': 'or', 'items': [ {'rule_id': self.rule_b.id}, {'rule_id': self.rule_c.id} ] } ] }
        self.ctrl.expression = expr
        self.ctrl.save()

        ev = HumanLayerEvent.objects.create(user=self.user, event_type='auth', source='svc', summary='y', details={'remote_addr': '1.2.3.4'})
        engine = ComplianceEngine()
        res = engine.evaluate_event(ev, self.policy)
        self.assertTrue(len(res['violations']) >= 1)
        self.assertTrue(Violation.objects.filter(control=self.ctrl).exists())
