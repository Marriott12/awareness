"""
Celery configuration for Awareness project.
Enables async processing for:
- Compliance evaluation
- ML model training
- Background reporting
- Scheduled maintenance tasks
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'awareness.settings')

app = Celery('awareness')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Task configuration
app.conf.task_routes = {
    'policy.tasks.evaluate_compliance': {'queue': 'compliance'},
    'policy.tasks.train_ml_model': {'queue': 'ml'},
    'policy.tasks.generate_report': {'queue': 'reports'},
}

app.conf.task_time_limit = 60 * 30  # 30 minutes max
app.conf.task_soft_time_limit = 60 * 25  # Soft limit at 25 min

# Periodic tasks
app.conf.beat_schedule = {
    'retrain-ml-model-daily': {
        'task': 'policy.tasks.retrain_ml_model_if_needed',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
    'cleanup-old-signatures-weekly': {
        'task': 'policy.tasks.cleanup_old_signatures',
        'schedule': crontab(day_of_week=0, hour=3, minute=0),  # Sunday 3 AM
    },
    'generate-weekly-report': {
        'task': 'policy.tasks.generate_weekly_compliance_report',
        'schedule': crontab(day_of_week=1, hour=8, minute=0),  # Monday 8 AM
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery configuration."""
    print(f'Request: {self.request!r}')
