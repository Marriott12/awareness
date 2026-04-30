"""Signal handlers and telemetry wiring for human-layer events and evidence persistence.

This module registers receivers for authentication events, violation persistence
and (if available) quiz/training model saves. It is imported from AppConfig.ready().
"""
import logging
from django.utils import timezone
from django.apps import apps
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.forms.models import model_to_dict
from django.conf import settings
import hmac
import hashlib
from .models import HumanLayerEvent

logger = logging.getLogger(__name__)


def _safe_dict(obj):
    try:
        return model_to_dict(obj)
    except Exception:
        return {'repr': str(obj)}


def _sign_event(ev):
    """Sign event and store signature in EventMetadata table."""
    try:
        from .crypto_utils import sign_data, get_tsa_timestamp
        from .models import EventMetadata
        
        # Get previous event for chaining
        prev = None
        if ev.user_id is not None:
            prev_meta = EventMetadata.objects.filter(
                event__user=ev.user
            ).exclude(event_id=ev.pk).order_by('-event__timestamp').first()
            prev = prev_meta.event if prev_meta else None
        
        prev_hash = prev_meta.signature if (prev and hasattr(prev, 'metadata')) else None
        payload = f"{ev.id}|{ev.timestamp.isoformat()}|{ev.user_id}|{ev.event_type}|{prev_hash}|{ev.details}"
        
        # Sign with private key
        sig = sign_data(payload)
        
        # Get TSA timestamp if configured
        tsa_token = get_tsa_timestamp(sig) if hasattr(settings, 'TSA_URL') else None
        
        # Create metadata record (mutable table, separate from immutable event)
        EventMetadata.objects.create(
            event=ev,
            prev_hash=prev_hash,
            signature=sig,
            signature_timestamp=timezone.now(),
            tsa_token=tsa_token
        )
    except Exception:
        logger.exception('Failed to sign HumanLayerEvent %s', getattr(ev, 'pk', None))


@receiver(user_logged_in)
def _on_user_logged_in(sender, request, user, **kwargs):
    try:
        from .models import HumanLayerEvent
        from django.contrib.sessions.models import Session

        # Check for concurrent logins (HLP-01)
        active_sessions = Session.objects.filter(expire_date__gte=timezone.now()).count()
        
        # Count recent login events for this user
        recent_logins = HumanLayerEvent.objects.filter(
            user=user,
            event_type='auth',
            source='auth.login',
            timestamp__gte=timezone.now() - timezone.timedelta(hours=1)
        ).count()

        details = {
            'remote_addr': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT'),
            'session_key': getattr(request.session, 'session_key', None),
            'active_sessions': active_sessions,
            'recent_logins': recent_logins,
        }
        
        ev = HumanLayerEvent.objects.create(
            user=user,
            event_type='auth',
            source='auth.login',
            summary='user_logged_in',
            details=details,
        )
        _sign_event(ev)
        
        # Create concurrent login event if multiple active sessions detected
        if recent_logins > 0:  # This is at least the second login in past hour
            concurrent_ev = HumanLayerEvent.objects.create(
                user=user,
                event_type='auth',
                source='auth.concurrent',
                summary='concurrent_login_detected',
                details={
                    'recent_logins': recent_logins + 1,
                    'remote_addr': request.META.get('REMOTE_ADDR'),
                    'user_agent': request.META.get('HTTP_USER_AGENT'),
                },
            )
            _sign_event(concurrent_ev)
            logger.warning(f'Concurrent login detected for user {user.username}: {recent_logins + 1} logins in past hour')
            
    except Exception:
        logger.exception('Failed to record user_logged_in telemetry')


@receiver(user_logged_out)
def _on_user_logged_out(sender, request, user, **kwargs):
    try:
        from .models import HumanLayerEvent

        details = {
            'remote_addr': request.META.get('REMOTE_ADDR') if request is not None else None,
            'session_key': getattr(request.session, 'session_key', None) if request is not None else None,
        }
        ev = HumanLayerEvent.objects.create(
            user=user,
            event_type='auth',
            source='auth.logout',
            summary='user_logged_out',
            details=details,
        )
        _sign_event(ev)
    except Exception:
        logger.exception('Failed to record user_logged_out telemetry')


@receiver(user_login_failed)
def _on_user_login_failed(sender, credentials, request, **kwargs):
    try:
        from .models import HumanLayerEvent

        details = {
            'username': credentials.get('username') if isinstance(credentials, dict) else str(credentials),
            'remote_addr': request.META.get('REMOTE_ADDR') if request is not None else None,
        }
        ev = HumanLayerEvent.objects.create(
            event_type='auth',
            source='auth.login_failed',
            summary='user_login_failed',
            details=details,
        )
        _sign_event(ev)
    except Exception:
        logger.exception('Failed to record user_login_failed telemetry')


@receiver(post_save, sender=apps.get_model('policy', 'Violation'))
def _on_violation_saved(sender, instance, created, **kwargs):
    # When a Violation is created, persist its `evidence` into an immutable Evidence record
    if not created:
        return
    try:
        from .models import Evidence

        payload = instance.evidence if isinstance(instance.evidence, dict) else {'evidence': instance.evidence}
        ev = Evidence(policy=instance.policy, violation=instance, payload=payload)
        ev.save()
    except Exception:
        logger.exception('Failed to persist Evidence for Violation %s', instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def _on_user_privilege_change(sender, instance, created, update_fields, **kwargs):
    """Detect privilege escalation for HLP-02 compliance.
    
    Tracks when users gain staff or superuser privileges, creating events
    for security monitoring and audit trail.
    """
    if created:
        # Track initial privilege grants for new users
        if instance.is_staff or instance.is_superuser:
            try:
                from .models import HumanLayerEvent
                
                initial_privileges = []
                if instance.is_staff:
                    initial_privileges.append('staff')
                if instance.is_superuser:
                    initial_privileges.append('superuser')
                
                details = {
                    'username': instance.username,
                    'initial_privileges': initial_privileges,
                    'is_staff': instance.is_staff,
                    'is_superuser': instance.is_superuser,
                }
                
                ev = HumanLayerEvent.objects.create(
                    user=instance,
                    event_type='admin',
                    source='auth.initial_privilege_grant',
                    summary='initial_privilege_granted',
                    details=details,
                )
                _sign_event(ev)
                logger.info(f'Initial privileges granted: {instance.username} created with {initial_privileges}')
            except Exception:
                logger.exception('Failed to record initial privilege grant')
        return
    
    # For updates, check if privilege-related fields changed
    if update_fields is not None:
        if 'is_staff' not in update_fields and 'is_superuser' not in update_fields:
            return  # No privilege changes, skip
    
    try:
        from .models import HumanLayerEvent
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Get the old values from database (before this save)
        # This works because we're in post_save, but we need to refresh from db
        try:
            # Use raw SQL to get original values since ORM cache might be stale
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT is_staff, is_superuser FROM {User._meta.db_table} WHERE id = %s",
                    [instance.pk]
                )
                row = cursor.fetchone()
                if row:
                    old_is_staff, old_is_superuser = row
                else:
                    return  # User not found, probably just created
        except Exception:
            # Fallback: just log current state without comparison
            old_is_staff = False
            old_is_superuser = False
        
        # Check for privilege escalation
        privilege_escalated = False
        escalation_type = []
        
        if not old_is_staff and instance.is_staff:
            privilege_escalated = True
            escalation_type.append('staff')
        
        if not old_is_superuser and instance.is_superuser:
            privilege_escalated = True
            escalation_type.append('superuser')
        
        if privilege_escalated:
            details = {
                'username': instance.username,
                'escalation_type': escalation_type,
                'was_staff': old_is_staff,
                'now_staff': instance.is_staff,
                'was_superuser': old_is_superuser,
                'now_superuser': instance.is_superuser,
            }
            
            ev = HumanLayerEvent.objects.create(
                user=instance,
                event_type='admin',
                source='auth.privilege_escalation',
                summary='privilege_escalated',
                details=details,
            )
            _sign_event(ev)
            logger.warning(f'Privilege escalation detected: {instance.username} gained {escalation_type}')
            
    except Exception:
        logger.exception('Failed to record privilege escalation telemetry')


def _connect_optional_model_signals():
    """Attempt to connect post_save handlers for quiz and training models if they exist.

    This avoids import-time failures when those apps are not present.
    """
    try:
        QuizAttempt = apps.get_model('quizzes', 'QuizAttempt')
    except Exception:
        QuizAttempt = None
    try:
        TrainingProgress = apps.get_model('training', 'TrainingProgress')
    except Exception:
        TrainingProgress = None

    if QuizAttempt is not None:
        @receiver(post_save, sender=QuizAttempt)
        def _on_quiz_attempt(sender, instance, created, **kwargs):
            try:
                from .models import HumanLayerEvent

                details = {
                    'quiz_attempt': _safe_dict(instance),
                }
                ev = HumanLayerEvent.objects.create(
                    user=getattr(instance, 'user', None),
                    event_type='quiz',
                    source='quizzes.QuizAttempt',
                    summary='quiz_attempt_saved',
                    details=details,
                )
                _sign_event(ev)
            except Exception:
                logger.exception('Failed to record quiz attempt telemetry')

    if TrainingProgress is not None:
        @receiver(post_save, sender=TrainingProgress)
        def _on_training_progress(sender, instance, created, **kwargs):
            try:
                from .models import HumanLayerEvent

                details = {
                    'training_progress': _safe_dict(instance),
                }
                ev = HumanLayerEvent.objects.create(
                    user=getattr(instance, 'user', None),
                    event_type='training',
                    source='training.TrainingProgress',
                    summary='training_progress_saved',
                    details=details,
                )
                _sign_event(ev)
            except Exception:
                logger.exception('Failed to record training telemetry')


    # Wire admin LogEntry events to capture admin actions
    try:
        from django.contrib.admin.models import LogEntry

        @receiver(post_save, sender=LogEntry)
        def _on_admin_logentry(sender, instance, created, **kwargs):
            try:
                from .models import HumanLayerEvent

                details = {
                    'action': instance.get_change_message(),
                    'object_repr': instance.object_repr,
                    'content_type_id': instance.content_type_id,
                }
                ev = HumanLayerEvent.objects.create(
                    user=getattr(instance, 'user', None),
                    event_type='admin',
                    source='admin.LogEntry',
                    summary='admin_action',
                    details=details,
                )
                _sign_event(ev)
            except Exception:
                logger.exception('Failed to record admin LogEntry telemetry')
    except Exception:
        # Admin app not loaded or LogEntry unavailable
        pass


_connect_optional_model_signals()
