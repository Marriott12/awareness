"""
Asynchronous compliance evaluation using Celery.

Decouples event ingestion from compliance evaluation for improved scalability.

Installation:
    pip install celery redis

Configuration (add to settings.py):
    # Celery Configuration
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'UTC'
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 300  # 5 minutes

Usage:
    # Start Celery worker
    celery -A awareness_portal worker -l info
    
    # Start Celery beat (for periodic tasks)
    celery -A awareness_portal beat -l info
    
    # Evaluate event asynchronously
    from policy.async_compliance import evaluate_event_async
    evaluate_event_async.delay(event_id, policy_id)
"""
from celery import shared_task
from django.utils import timezone
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def evaluate_event_async(self, event_id: int, policy_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Asynchronously evaluate an event against policies.
    
    Args:
        event_id: ID of HumanLayerEvent to evaluate
        policy_id: Optional specific Policy ID (if None, evaluates against all active policies)
        
    Returns:
        Dictionary with evaluation results
    """
    try:
        from .models import HumanLayerEvent, Policy
        from .transaction_safe import TransactionSafeEngine
        
        # Get event
        try:
            event = HumanLayerEvent.objects.get(pk=event_id)
        except HumanLayerEvent.DoesNotExist:
            logger.error(f'Event {event_id} not found')
            return {'error': 'event_not_found', 'event_id': event_id}
        
        # Get policies
        if policy_id:
            try:
                policies = [Policy.objects.get(pk=policy_id)]
            except Policy.DoesNotExist:
                logger.error(f'Policy {policy_id} not found')
                return {'error': 'policy_not_found', 'policy_id': policy_id}
        else:
            policies = Policy.objects.filter(lifecycle='active')
        
        # Evaluate against all policies
        engine = TransactionSafeEngine()
        results = []
        
        for policy in policies:
            try:
                result = engine.evaluate_event(event, policy)
                results.append(result)
            except Exception as e:
                logger.exception(f'Failed to evaluate event {event_id} against policy {policy.id}')
                results.append({
                    'policy': policy.name,
                    'error': str(e),
                    'event_id': event_id
                })
        
        return {
            'event_id': event_id,
            'evaluated_policies': len(policies),
            'results': results,
            'timestamp': timezone.now().isoformat()
        }
    
    except Exception as exc:
        logger.exception(f'Failed to evaluate event {event_id}')
        # Retry with exponential backoff
        raise self.retry(exc=exc)


@shared_task
def evaluate_unprocessed_events(policy_id: Optional[int] = None, limit: int = 100) -> Dict[str, Any]:
    """
    Batch process unprocessed events.
    
    Args:
        policy_id: Optional specific Policy ID
        limit: Maximum number of events to process
        
    Returns:
        Summary of processing results
    """
    try:
        from .models import HumanLayerEvent, EventMetadata, Policy
        
        # Get unprocessed events
        processed_event_ids = EventMetadata.objects.filter(
            processed=True
        ).values_list('event_id', flat=True)
        
        unprocessed_events = HumanLayerEvent.objects.exclude(
            id__in=processed_event_ids
        ).order_by('timestamp')[:limit]
        
        # Queue events for async evaluation
        task_ids = []
        for event in unprocessed_events:
            task = evaluate_event_async.delay(event.id, policy_id)
            task_ids.append(str(task.id))
        
        return {
            'queued_events': len(task_ids),
            'task_ids': task_ids,
            'timestamp': timezone.now().isoformat()
        }
    
    except Exception as e:
        logger.exception('Failed to queue unprocessed events')
        return {'error': str(e)}


@shared_task
def scan_for_anomalies(min_risk_level: str = 'medium') -> Dict[str, Any]:
    """
    Periodic task to scan all users for behavioral anomalies.
    
    Args:
        min_risk_level: Minimum risk level to report ('low', 'medium', 'high', 'critical')
        
    Returns:
        Summary of detected anomalies
    """
    try:
        from .anomaly_detection import AnomalyDetector
        
        threats = AnomalyDetector.scan_all_users(min_risk_level)
        
        # Log critical threats
        if threats:
            from .structured_logging import get_security_logger
            sec_logger = get_security_logger()
            
            for threat in threats:
                if threat['overall_risk'] in ['high', 'critical']:
                    sec_logger.warning(
                        'Behavioral anomaly detected',
                        user_id=threat['user_id'],
                        risk_level=threat['overall_risk'],
                        anomalies=threat['anomalies'],
                        event_type='anomaly_detected'
                    )
        
        return {
            'scanned_users': len(threats),
            'threats_detected': sum(1 for t in threats if t['is_threat']),
            'critical_threats': sum(1 for t in threats if t['overall_risk'] == 'critical'),
            'high_threats': sum(1 for t in threats if t['overall_risk'] == 'high'),
            'timestamp': timezone.now().isoformat()
        }
    
    except Exception as e:
        logger.exception('Anomaly scan failed')
        return {'error': str(e)}


@shared_task
def cleanup_old_data(retention_days: int = 2555) -> Dict[str, Any]:
    """
    Periodic task to clean up old data per retention policy.
    
    Args:
        retention_days: Number of days to retain data (default: 7 years)
        
    Returns:
        Summary of cleanup results
    """
    try:
        from .models import HumanLayerEvent, Violation, EventMetadata
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=retention_days)
        
        # Count records to delete
        old_events = HumanLayerEvent.objects.filter(timestamp__lt=cutoff_date).count()
        old_violations = Violation.objects.filter(timestamp__lt=cutoff_date).count()
        
        # Delete old data
        deleted_events = HumanLayerEvent.objects.filter(timestamp__lt=cutoff_date).delete()[0]
        deleted_violations = Violation.objects.filter(timestamp__lt=cutoff_date).delete()[0]
        
        logger.info(
            f'Cleaned up old data: {deleted_events} events, {deleted_violations} violations'
        )
        
        return {
            'deleted_events': deleted_events,
            'deleted_violations': deleted_violations,
            'cutoff_date': cutoff_date.isoformat(),
            'timestamp': timezone.now().isoformat()
        }
    
    except Exception as e:
        logger.exception('Data cleanup failed')
        return {'error': str(e)}


@shared_task
def rotate_keys_async() -> Dict[str, Any]:
    """
    Periodic task to rotate cryptographic keys.
    
    Should be run monthly or quarterly.
    
    Returns:
        Summary of key rotation results
    """
    try:
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command('rotate_keys', '--batch-size=100', stdout=out)
        
        return {
            'status': 'completed',
            'output': out.getvalue(),
            'timestamp': timezone.now().isoformat()
        }
    
    except Exception as e:
        logger.exception('Key rotation failed')
        return {'error': str(e)}


@shared_task
def backup_database_async(output_dir: str = '/var/backups/awareness') -> Dict[str, Any]:
    """
    Periodic task for automated database backups.
    
    Should be run daily.
    
    Args:
        output_dir: Directory to store backups
        
    Returns:
        Summary of backup results
    """
    try:
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        call_command(
            'backup_database',
            '--output-dir=' + output_dir,
            '--verify',
            '--compress',
            stdout=out
        )
        
        return {
            'status': 'completed',
            'output': out.getvalue(),
            'timestamp': timezone.now().isoformat()
        }
    
    except Exception as e:
        logger.exception('Database backup failed')
        return {'error': str(e)}


# Celery Beat schedule (add to settings.py)
CELERY_BEAT_SCHEDULE_CONFIG = {
    'process-unprocessed-events': {
        'task': 'policy.async_compliance.evaluate_unprocessed_events',
        'schedule': 60.0,  # Every minute
        'args': (None, 1000)  # Process up to 1000 events
    },
    'scan-for-anomalies': {
        'task': 'policy.async_compliance.scan_for_anomalies',
        'schedule': 3600.0,  # Every hour
        'args': ('medium',)
    },
    'cleanup-old-data': {
        'task': 'policy.async_compliance.cleanup_old_data',
        'schedule': 86400.0,  # Daily
        'args': (2555,)  # 7 years
    },
    'rotate-keys': {
        'task': 'policy.async_compliance.rotate_keys_async',
        'schedule': 2592000.0,  # Monthly (30 days)
    },
    'backup-database': {
        'task': 'policy.async_compliance.backup_database_async',
        'schedule': 86400.0,  # Daily
        'args': ('/var/backups/awareness',)
    },
}
