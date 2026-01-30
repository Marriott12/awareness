from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.apps import apps
from policy.models import Policy, Control, Rule, Violation, Evidence, HumanLayerEvent
from django.utils import timezone


class TelemetrySignalsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.User = get_user_model()
        self.user = self.User.objects.create_user('tele', 't@x.com', 'pw')
        self.policy = Policy.objects.create(name='TPol')
        self.ctrl = Control.objects.create(policy=self.policy, name='C1', severity='low')

    def test_violation_creates_evidence(self):
        v = Violation.objects.create(timestamp=timezone.now(), user=self.user, policy=self.policy, control=self.ctrl, rule=None, severity='low', evidence={'k': 'v'})
        # Evidence should be created and linked
        ev = Evidence.objects.filter(violation=v).first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.payload.get('k'), 'v')

    def test_user_logged_in_creates_event(self):
        req = self.factory.get('/')
        # simulate session key presence
        req.session = {}
        user_logged_in.send(sender=self.User, request=req, user=self.user)
        ev = HumanLayerEvent.objects.filter(user=self.user, event_type='auth', source='auth.login').first()
        self.assertIsNotNone(ev)
        self.assertIn('user_agent', ev.details)
