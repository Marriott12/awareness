"""Database-agnostic immutability enforcement.

Provides application-level protection against UPDATE/DELETE operations on
immutable tables (Evidence, HumanLayerEvent). Works on both Postgres and SQLite.

Architecture:
- Postgres: DB triggers + application checks (defense in depth)
- SQLite: Application checks only (no trigger support)

Usage:
    Add to MIDDLEWARE in settings.py:
        'policy.immutability_middleware.ImmutabilityEnforcementMiddleware'
"""
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models.signals import pre_save, pre_delete
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)


class ImmutabilityEnforcementMiddleware:
    """Middleware to block UPDATE/DELETE on immutable models."""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Middleware doesn't need to do anything per-request
        # Signal handlers below do the actual enforcement
        response = self.get_response(request)
        return response


@receiver(pre_save, sender='policy.Evidence')
def block_evidence_update(sender, instance, **kwargs):
    """Block updates to Evidence model (database-agnostic)."""
    if instance.pk:
        # Check if record actually exists in DB
        if sender.objects.filter(pk=instance.pk).exists():
            raise PermissionDenied(
                'Evidence objects are immutable and cannot be updated. '
                'Attempted UPDATE on Evidence.pk={}'.format(instance.pk)
            )


@receiver(pre_delete, sender='policy.Evidence')
def block_evidence_delete(sender, instance, **kwargs):
    """Block deletes from Evidence model (database-agnostic)."""
    raise PermissionDenied(
        'Evidence objects are immutable and cannot be deleted. '
        'Attempted DELETE on Evidence.pk={}'.format(instance.pk)
    )


@receiver(pre_save, sender='policy.HumanLayerEvent')
def block_event_update(sender, instance, **kwargs):
    """Block updates to HumanLayerEvent model (database-agnostic)."""
    if instance.pk:
        # Check if record actually exists in DB
        if sender.objects.filter(pk=instance.pk).exists():
            raise PermissionDenied(
                'HumanLayerEvent objects are immutable and cannot be updated. '
                'Use EventMetadata for mutable fields. '
                'Attempted UPDATE on HumanLayerEvent.pk={}'.format(instance.pk)
            )


@receiver(pre_delete, sender='policy.HumanLayerEvent')
def block_event_delete(sender, instance, **kwargs):
    """Block deletes from HumanLayerEvent model (database-agnostic)."""
    raise PermissionDenied(
        'HumanLayerEvent objects are immutable and cannot be deleted. '
        'Attempted DELETE on HumanLayerEvent.pk={}'.format(instance.pk)
    )


def validate_immutability():
    """Runtime validation that immutability enforcement is active.
    
    Returns:
        Tuple of (bool, str): (success, message)
    """
    from policy.models import Evidence, HumanLayerEvent
    import uuid
    from django.utils import timezone
    
    messages = []
    
    # Test Evidence immutability
    try:
        ev = Evidence.objects.create(payload={'test': 'immutability_check'})
        ev.payload = {'modified': True}
        try:
            ev.save()
            messages.append('FAIL: Evidence UPDATE was not blocked')
            success = False
        except (ValueError, PermissionDenied):
            messages.append('OK: Evidence UPDATE blocked')
        finally:
            # Clean up test record
            Evidence.objects.filter(pk=ev.pk).delete()
    except PermissionDenied:
        messages.append('FAIL: Evidence DELETE was blocked during cleanup')
        success = False
    
    # Test HumanLayerEvent immutability
    try:
        event = HumanLayerEvent.objects.create(
            id=uuid.uuid4(),
            event_type='other',
            summary='immutability test',
            details={}
        )
        event.summary = 'modified'
        try:
            event.save()
            messages.append('FAIL: HumanLayerEvent UPDATE was not blocked')
            success = False
        except (ValueError, PermissionDenied):
            messages.append('OK: HumanLayerEvent UPDATE blocked')
        finally:
            HumanLayerEvent.objects.filter(pk=event.pk).delete()
    except PermissionDenied:
        messages.append('FAIL: HumanLayerEvent DELETE was blocked during cleanup')
        success = False
    
    # Check database vendor
    vendor = connection.vendor
    if vendor == 'postgresql':
        messages.append(f'Database: {vendor} (has DB triggers)')
    elif vendor == 'sqlite':
        messages.append(f'Database: {vendor} (application-level enforcement only)')
    else:
        messages.append(f'Database: {vendor} (unknown, verify enforcement)')
    
    return success, '\n'.join(messages)
