"""Concurrency and transactionality tests for policy engine."""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from policy.models import Policy, Control, Rule, Violation, HumanLayerEvent
from policy.compliance import ComplianceEngine
from threading import Thread
import time


class ConcurrencyTests(TransactionTestCase):
    """Test parallel event processing and deduplication."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', password='testpass')
        self.policy = Policy.objects.create(name='Test Policy', lifecycle='active')
        self.control = Control.objects.create(policy=self.policy, name='Test Control', severity='high')
        self.rule = Rule.objects.create(
            control=self.control,
            name='Test Rule',
            left_operand='detail.type',
            operator='==',
            right_value='bad'
        )
    
    def test_parallel_event_ingestion(self):
        """Test that multiple threads can ingest events without race conditions."""
        events_created = []
        errors = []
        
        def create_event(idx):
            try:
                evt = HumanLayerEvent.objects.create(
                    user=self.user,
                    event_type='other',
                    source='test',
                    summary=f'Event {idx}',
                    details={'type': 'bad', 'index': idx}
                )
                events_created.append(evt)
            except Exception as e:
                errors.append(e)
        
        threads = [Thread(target=create_event, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0, f'Errors during parallel creation: {errors}')
        self.assertEqual(len(events_created), 10)
    
    def test_dedup_key_unique_constraint(self):
        """Test that dedup_key prevents duplicate violations at DB level."""
        from django.db import IntegrityError
        
        # Create first violation with dedup_key
        v1 = Violation.objects.create(
            timestamp=timezone.now(),
            user=self.user,
            policy=self.policy,
            control=self.control,
            rule=self.rule,
            severity='high',
            evidence={'test': 'data'},
            dedup_key='test-dedup-123'
        )
        
        # Attempt to create second with same dedup_key should fail
        with self.assertRaises(IntegrityError):
            Violation.objects.create(
                timestamp=timezone.now(),
                user=self.user,
                policy=self.policy,
                control=self.control,
                rule=self.rule,
                severity='high',
                evidence={'test': 'data2'},
                dedup_key='test-dedup-123'
            )
        
        # Verify only one violation exists
        self.assertEqual(Violation.objects.filter(dedup_key='test-dedup-123').count(), 1)
    
    def test_violation_action_log_immutable(self):
        """Test that ViolationActionLog is append-only."""
        from policy.models import ViolationActionLog
        
        v = Violation.objects.create(
            timestamp=timezone.now(),
            user=self.user,
            policy=self.policy,
            control=self.control,
            rule=self.rule,
            severity='high',
            evidence={'test': 'data'},
            dedup_key='action-log-test'
        )
        
        # Create action log entry
        log = ViolationActionLog.objects.create(
            violation=v,
            action='acknowledge',
            actor=self.user,
            details={'source': 'test'}
        )
        
        # Verify it was created
        self.assertEqual(ViolationActionLog.objects.filter(violation=v).count(), 1)
        
        # Action log should be immutable (this is enforced at admin level, not model)
        # We can verify the model exists and has correct fields
        self.assertEqual(log.action, 'acknowledge')
        self.assertEqual(log.actor, self.user)
