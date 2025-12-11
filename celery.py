# project_management/celery.py

import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')

# Create Celery app
app = Celery('project_management')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Celery Beat Schedule (Periodic Tasks)
app.conf.beat_schedule = {
    # Check for overdue tasks every hour
    'check-overdue-tasks': {
        'task': 'tasks.tasks.check_overdue_tasks',
        'schedule': crontab(minute=0),  # Every hour
    },
    # Send daily task summary at 9 AM
    'send-daily-summary': {
        'task': 'notifications.tasks.send_daily_summary',
        'schedule': crontab(hour=9, minute=0),  # 9:00 AM daily
    },
    # Clean old notifications weekly
    'clean-old-notifications': {
        'task': 'notifications.tasks.clean_old_notifications',
        'schedule': crontab(hour=0, minute=0, day_of_week=0),  # Sunday midnight
    },
    # Update project progress every 30 minutes
    'update-project-progress': {
        'task': 'projects.tasks.update_all_project_progress',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
}

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery"""
    print(f'Request: {self.request!r}')