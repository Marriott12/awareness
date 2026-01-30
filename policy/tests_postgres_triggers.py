from django.test import TestCase
from unittest import skipIf
from django.db import connection, transaction, IntegrityError, DatabaseError
from policy.models import Evidence, HumanLayerEvent


class PostgresTriggerTests(TestCase):
    @skipIf(connection.vendor != 'postgresql', 'Postgres trigger test - skipped on non-Postgres')
    def test_evidence_update_blocked(self):
        e = Evidence.objects.create(payload={'x': 'y'})
        with self.assertRaises(DatabaseError):
            # attempt to update should raise due to trigger
            e.payload = {'x': 'z'}
            e.save()

    @skipIf(connection.vendor != 'postgresql', 'Postgres trigger test - skipped on non-Postgres')
    def test_humanlayerevent_delete_blocked(self):
        ev = HumanLayerEvent.objects.create(details={'a': 1}, event_type='other')
        with self.assertRaises(DatabaseError):
            ev.delete()
