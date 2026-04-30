"""Celery configuration for Awareness Portal."""
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'awareness_portal.settings')

app = Celery('awareness_portal')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Periodic Tasks Configuration
app.conf.beat_schedule = {
    'send-training-reminders': {
        'task': 'policy.tasks.send_pending_training_reminders',
        'schedule': crontab(hour=9, minute=0),  # Daily at 9 AM
    },
    'cleanup-old-events': {
        'task': 'policy.tasks.cleanup_old_events',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),  # Weekly on Sunday at 2 AM
    },
    'retrain-ml-models': {
        'task': 'policy.tasks.retrain_ml_models',
        'schedule': crontab(hour=3, minute=0, day_of_week=1),  # Weekly on Monday at 3 AM
    },
}


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery."""
    print(f'Request: {self.request!r}')
