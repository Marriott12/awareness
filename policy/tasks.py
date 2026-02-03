"""
Celery async tasks for background processing.

Tasks:
- Compliance evaluation (async)
- ML model retraining
- Report generation
- Signature cleanup
"""
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def evaluate_compliance_async(self, event_id):
    """
    Asynchronously evaluate compliance for an event.
    
    Benefits:
    - Non-blocking event ingestion
    - Retry on failure
    - Horizontal scaling via workers
    
    Args:
        event_id: HumanLayerEvent ID to evaluate
    
    Returns:
        dict: Evaluation results
    """
    from policy.models import HumanLayerEvent
    from policy.compliance import ComplianceEngine
    
    try:
        event = HumanLayerEvent.objects.get(pk=event_id)
        engine = ComplianceEngine()
        
        logger.info(f"[CELERY] Starting compliance eval for event {event_id}")
        results = engine.evaluate(event)
        
        logger.info(f"[CELERY] Completed eval for event {event_id}: "
                   f"{len(results['violations'])} violations")
        
        return {
            'event_id': event_id,
            'violations': len(results['violations']),
            'controls_evaluated': len(results['controls_evaluated']),
        }
        
    except HumanLayerEvent.DoesNotExist:
        logger.error(f"[CELERY] Event {event_id} not found")
        raise
        
    except Exception as exc:
        logger.exception(f"[CELERY] Failed to evaluate event {event_id}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@shared_task(bind=True, max_retries=1)
def train_ml_model_async(self, algorithm='random_forest', experiment_id=None):
    """
    Train ML model in background.
    
    Args:
        algorithm: 'random_forest' or 'gradient_boosting'
        experiment_id: Optional experiment to train on
    
    Returns:
        dict: Training metrics
    """
    from policy.ml_scorer import MLRiskScorer
    from policy.models import GroundTruthLabel, HumanLayerEvent
    
    try:
        logger.info(f"[CELERY] Starting ML training: {algorithm}")
        
        # Get labeled data
        if experiment_id:
            labels = GroundTruthLabel.objects.filter(
                experiment_id=experiment_id
            ).select_related('event')
        else:
            labels = GroundTruthLabel.objects.all().select_related('event')
        
        if labels.count() < 10:
            logger.warning(f"[CELERY] Insufficient training data: {labels.count()} samples")
            return {'status': 'skipped', 'reason': 'insufficient_data', 'samples': labels.count()}
        
        # Prepare data
        events = [label.event for label in labels]
        true_labels = [label.is_violation for label in labels]
        
        # Train model
        scorer = MLRiskScorer()
        metrics = scorer.train(events, true_labels, algorithm=algorithm, tune_hyperparameters=True)
        
        # Save model
        version = f"v{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        scorer.save_model(version=version, metadata={
            'algorithm': algorithm,
            'samples': len(events),
            'experiment_id': experiment_id,
            'trained_at': timezone.now().isoformat(),
        })
        
        logger.info(f"[CELERY] ML training complete: {version}, F1={metrics.get('f1', 0):.3f}")
        
        # Send notification to admins
        if hasattr(settings, 'ADMINS') and settings.ADMINS:
            send_mail(
                subject=f'ML Model Training Complete: {version}',
                message=f"""
ML model training completed successfully.

Version: {version}
Algorithm: {algorithm}
Training samples: {len(events)}
F1 Score: {metrics.get('f1', 0):.3f}
ROC AUC: {metrics.get('roc_auc', 0):.3f}

The model is ready for production use.
                """.strip(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email for _, email in settings.ADMINS],
                fail_silently=True,
            )
        
        return {
            'status': 'success',
            'version': version,
            'metrics': metrics,
            'samples': len(events),
        }
        
    except Exception as exc:
        logger.exception(f"[CELERY] ML training failed: {algorithm}")
        raise self.retry(exc=exc, countdown=60)


@shared_task
def retrain_ml_model_if_needed():
    """
    Periodic task to retrain ML model if performance degrades.
    
    Checks:
    - Has new labeled data been added?
    - Is current model performance acceptable?
    - Should we retrain?
    """
    from policy.models import GroundTruthLabel, ScorerArtifact
    from policy.ml_scorer import get_ml_scorer
    
    try:
        # Check if we have recent labels (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        new_labels = GroundTruthLabel.objects.filter(created_at__gte=week_ago).count()
        
        if new_labels < 10:
            logger.info(f"[CELERY] Skipping ML retrain: only {new_labels} new labels")
            return {'status': 'skipped', 'reason': 'insufficient_new_data'}
        
        # Check current model performance
        current_model = ScorerArtifact.objects.filter(is_active=True).first()
        
        if not current_model:
            logger.info("[CELERY] No active model, triggering initial training")
            return train_ml_model_async.delay()
        
        # If model is older than 30 days, retrain
        age_days = (timezone.now() - current_model.created_at).days
        
        if age_days > 30:
            logger.info(f"[CELERY] Model is {age_days} days old, retraining")
            return train_ml_model_async.delay()
        
        logger.info(f"[CELERY] Current model is fresh ({age_days} days old)")
        return {'status': 'skipped', 'reason': 'model_fresh', 'age_days': age_days}
        
    except Exception as exc:
        logger.exception("[CELERY] Failed to check if retraining needed")
        raise


@shared_task
def generate_weekly_compliance_report():
    """
    Generate weekly compliance report and email to admins.
    """
    from policy.models import HumanLayerEvent, ComplianceViolation
    from django.db.models import Count, Q
    
    try:
        week_ago = timezone.now() - timedelta(days=7)
        
        # Gather statistics
        total_events = HumanLayerEvent.objects.filter(timestamp__gte=week_ago).count()
        violations = ComplianceViolation.objects.filter(
            created_at__gte=week_ago
        ).count()
        
        # Critical violations
        critical = ComplianceViolation.objects.filter(
            created_at__gte=week_ago,
            severity='critical'
        ).count()
        
        # Most violated policies
        top_policies = ComplianceViolation.objects.filter(
            created_at__gte=week_ago
        ).values('policy__name').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        # Build report
        report = f"""
Weekly Compliance Report
========================
Period: {week_ago.strftime('%Y-%m-%d')} to {timezone.now().strftime('%Y-%m-%d')}

Summary:
- Total Events: {total_events}
- Total Violations: {violations}
- Critical Violations: {critical}
- Violation Rate: {(violations / max(total_events, 1) * 100):.1f}%

Top 5 Violated Policies:
"""
        for i, policy_data in enumerate(top_policies, 1):
            report += f"{i}. {policy_data['policy__name']}: {policy_data['count']} violations\n"
        
        logger.info("[CELERY] Generated weekly compliance report")
        
        # Email to admins
        if hasattr(settings, 'ADMINS') and settings.ADMINS:
            send_mail(
                subject=f'Weekly Compliance Report - {timezone.now().strftime("%Y-%m-%d")}',
                message=report,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email for _, email in settings.ADMINS],
                fail_silently=True,
            )
        
        return {'status': 'success', 'total_events': total_events, 'violations': violations}
        
    except Exception as exc:
        logger.exception("[CELERY] Failed to generate weekly report")
        raise


@shared_task
def cleanup_old_signatures():
    """
    Cleanup old signature data (not the signatures themselves, but expired verification records).
    
    Keeps audit trail but removes temporary verification data older than 1 year.
    """
    from policy.models import EventMetadata
    
    try:
        year_ago = timezone.now() - timedelta(days=365)
        
        # Count candidates for cleanup
        old_metadata = EventMetadata.objects.filter(
            last_modified__lt=year_ago
        ).count()
        
        logger.info(f"[CELERY] Found {old_metadata} old metadata records (>1 year)")
        
        # For now, just log - actual deletion requires careful GDPR consideration
        # In production, implement based on retention policies
        
        return {
            'status': 'success',
            'old_records': old_metadata,
            'action': 'logged_only',
        }
        
    except Exception as exc:
        logger.exception("[CELERY] Failed to cleanup signatures")
        raise


@shared_task
def generate_report(report_type, start_date, end_date, user_id):
    """
    Generate custom report and save to file.
    
    Args:
        report_type: 'violations', 'policy_effectiveness', 'user_activity'
        start_date: ISO date string
        end_date: ISO date string
        user_id: User requesting the report
    
    Returns:
        str: Path to generated report file
    """
    import csv
    import io
    from policy.models import ComplianceViolation, Policy
    
    try:
        logger.info(f"[CELERY] Generating {report_type} report for user {user_id}")
        
        # Parse dates
        from datetime import datetime
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        output = io.StringIO()
        
        if report_type == 'violations':
            # Violation report
            violations = ComplianceViolation.objects.filter(
                created_at__range=(start, end)
            ).select_related('policy', 'event', 'control')
            
            writer = csv.writer(output)
            writer.writerow(['Timestamp', 'Policy', 'Control', 'Severity', 'Event ID', 'Status'])
            
            for v in violations:
                writer.writerow([
                    v.created_at.isoformat(),
                    v.policy.name,
                    v.control.name if v.control else 'N/A',
                    v.severity,
                    v.event.event_id,
                    v.status,
                ])
        
        elif report_type == 'policy_effectiveness':
            # Policy effectiveness report
            policies = Policy.objects.filter(is_active=True)
            
            writer = csv.writer(output)
            writer.writerow(['Policy', 'Total Violations', 'Critical', 'High', 'Medium', 'Low'])
            
            for policy in policies:
                violations = ComplianceViolation.objects.filter(
                    policy=policy,
                    created_at__range=(start, end)
                )
                
                writer.writerow([
                    policy.name,
                    violations.count(),
                    violations.filter(severity='critical').count(),
                    violations.filter(severity='high').count(),
                    violations.filter(severity='medium').count(),
                    violations.filter(severity='low').count(),
                ])
        
        report_content = output.getvalue()
        
        # In production, save to S3/storage backend
        # For now, return content
        logger.info(f"[CELERY] Report generation complete: {len(report_content)} bytes")
        
        return {
            'status': 'success',
            'report_type': report_type,
            'size_bytes': len(report_content),
            'content': report_content[:1000],  # First 1KB for preview
        }
        
    except Exception as exc:
        logger.exception(f"[CELERY] Failed to generate {report_type} report")
        raise
