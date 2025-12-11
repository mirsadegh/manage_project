# tasks/tasks.py

from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from .models import Task
from notifications.models import Notification

@shared_task
def check_overdue_tasks():
    """
    Check for overdue tasks and create notifications.
    Runs every hour via Celery Beat.
    """
    now = timezone.now()
    
    # Find overdue tasks that are not completed
    overdue_tasks = Task.objects.filter(
        due_date__lt=now.date(),
        status__in=['TODO', 'IN_PROGRESS', 'BLOCKED']
    ).select_related('assignee', 'project')
    
    notifications_created = 0
    
    for task in overdue_tasks:
        if task.assignee:
            # Check if notification already exists
            existing = Notification.objects.filter(
                recipient=task.assignee,
                notification_type='TASK_DUE_SOON',
                object_id=task.id,
                is_read=False
            ).exists()
            
            if not existing:
                Notification.objects.create(
                    recipient=task.assignee,
                    notification_type='TASK_DUE_SOON',
                    title='Task Overdue',
                    message=f'Task "{task.title}" in project "{task.project.name}" is overdue.',
                    content_object=task
                )
                notifications_created += 1
    
    return f'Checked overdue tasks. Created {notifications_created} notifications.'


@shared_task
def send_task_reminder(task_id, days_before=1):
    """
    Send reminder notification for upcoming task deadline.
    Can be scheduled when task is created/updated.
    """
    try:
        task = Task.objects.get(id=task_id)
        
        if task.assignee and task.status not in ['COMPLETED', 'CANCELLED']:
            Notification.objects.create(
                recipient=task.assignee,
                notification_type='TASK_DUE_SOON',
                title='Task Deadline Approaching',
                message=f'Task "{task.title}" is due in {days_before} day(s).',
                content_object=task
            )
            return f'Reminder sent for task {task_id}'
    except Task.DoesNotExist:
        return f'Task {task_id} not found'


@shared_task
def bulk_update_task_status(task_ids, new_status):
    """
    Bulk update task statuses.
    Useful for batch operations.
    """
    updated = Task.objects.filter(id__in=task_ids).update(status=new_status)
    return f'Updated {updated} tasks to status {new_status}'


@shared_task
def calculate_task_metrics(project_id):
    """
    Calculate task metrics for a project.
    Can be expensive, so run async.
    """
    from projects.models import Project
    
    try:
        project = Project.objects.get(id=project_id)
        tasks = project.tasks.all()
        
        metrics = {
            'total': tasks.count(),
            'completed': tasks.filter(status='COMPLETED').count(),
            'in_progress': tasks.filter(status='IN_PROGRESS').count(),
            'overdue': tasks.filter(
                due_date__lt=timezone.now().date(),
                status__in=['TODO', 'IN_PROGRESS']
            ).count(),
        }
        
        # Cache the results
        from django.core.cache import cache
        cache.set(f'project_metrics_{project_id}', metrics, timeout=300)  # 5 minutes
        
        return metrics
    except Project.DoesNotExist:
        return f'Project {project_id} not found'