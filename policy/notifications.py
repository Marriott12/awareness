"""Email notification system for Awareness Portal.

Sends email notifications for:
- Training due dates
- Policy violations
- Quiz completions
- Admin alerts
"""
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_training_reminder(self, user_id, module_id):
    """Send training due date reminder email."""
    try:
        from django.contrib.auth import get_user_model
        from training.models import TrainingModule
        
        User = get_user_model()
        user = User.objects.get(id=user_id)
        module = TrainingModule.objects.get(id=module_id)
        
        subject = f'Reminder: Complete "{module.title}" Training'
        
        html_content = render_to_string('emails/training_reminder.html', {
            'user': user,
            'module': module,
        })
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f'Training reminder sent to {user.email} for module {module.title}')
        return True
        
    except Exception as exc:
        logger.error(f'Failed to send training reminder: {exc}')
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_violation_alert(self, violation_id):
    """Send policy violation alert to security team."""
    try:
        from policy.models import Violation
        
        violation = Violation.objects.select_related('rule', 'user').get(id=violation_id)
        
        subject = f'🚨 Security Alert: {violation.severity.upper()} Violation Detected'
        
        html_content = render_to_string('emails/violation_alert.html', {
            'violation': violation,
        })
        text_content = strip_tags(html_content)
        
        # Send to security team
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.SECURITY_TEAM_EMAIL],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f'Violation alert sent for violation {violation_id}')
        return True
        
    except Exception as exc:
        logger.error(f'Failed to send violation alert: {exc}')
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_quiz_completion_notification(self, attempt_id):
    """Send quiz completion notification to user."""
    try:
        from quizzes.models import QuizAttempt
        
        attempt = QuizAttempt.objects.select_related('quiz', 'user').get(id=attempt_id)
        
        subject = f'Quiz Completed: {attempt.quiz.title}'
        
        html_content = render_to_string('emails/quiz_completion.html', {
            'attempt': attempt,
        })
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[attempt.user.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f'Quiz completion notification sent to {attempt.user.email}')
        return True
        
    except Exception as exc:
        logger.error(f'Failed to send quiz completion notification: {exc}')
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_slack_notification(self, message, channel=None):
    """Send notification to Slack."""
    try:
        import requests
        
        webhook_url = settings.SLACK_WEBHOOK_URL
        if not webhook_url:
            logger.warning('Slack webhook URL not configured')
            return False
        
        payload = {
            'text': message,
            'channel': channel or getattr(settings, 'SLACK_CHANNEL', '#security-alerts'),
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info(f'Slack notification sent to {channel or getattr(settings, "SLACK_CHANNEL", "#security-alerts")}')
        return True
        
    except Exception as exc:
        logger.error(f'Failed to send Slack notification: {exc}')
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_teams_notification(self, title, message):
    """Send notification to Microsoft Teams."""
    try:
        import pymsteams
        
        webhook_url = settings.TEAMS_WEBHOOK_URL
        if not webhook_url:
            logger.warning('Teams webhook URL not configured')
            return False
        
        teams_message = pymsteams.connectorcard(webhook_url)
        teams_message.title(title)
        teams_message.text(message)
        teams_message.send()
        
        logger.info(f'Teams notification sent: {title}')
        return True
        
    except Exception as exc:
        logger.error(f'Failed to send Teams notification: {exc}')
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


def notify_violation(violation):
    """Convenience function to send all violation notifications."""
    send_violation_alert.delay(violation.id)
    
    # Also send to Slack/Teams if configured
    message = f"🚨 {violation.severity.upper()} Violation: {violation.rule.description}\nUser: {violation.user.username}"
    
    if getattr(settings, 'SLACK_WEBHOOK_URL', None):
        send_slack_notification.delay(message)
    
    if getattr(settings, 'TEAMS_WEBHOOK_URL', None):
        send_teams_notification.delay(
            f"Security Violation: {violation.severity.upper()}",
            message
        )
