# projects/tasks.py

from celery import shared_task
from django.db.models import Count, Q
from .models import Project

@shared_task
def update_project_progress(project_id):
    """
    Calculate and update project progress based on completed tasks.
    """
    try:
        project = Project.objects.get(id=project_id)
        
        total_tasks = project.tasks.count()
        if total_tasks > 0:
            completed_tasks = project.tasks.filter(status='COMPLETED').count()
            progress = int((completed_tasks / total_tasks) * 100)
            
            project.progress = progress
            project.save(update_fields=['progress'])
            
            return f'Updated project {project_id} progress to {progress}%'
        
        return f'Project {project_id} has no tasks'
    except Project.DoesNotExist:
        return f'Project {project_id} not found'


@shared_task
def update_all_project_progress():
    """
    Update progress for all active projects.
    Runs every 30 minutes via Celery Beat.
    """
    active_projects = Project.objects.filter(is_active=True)
    
    updated = 0
    for project in active_projects:
        total_tasks = project.tasks.count()
        if total_tasks > 0:
            completed_tasks = project.tasks.filter(status='COMPLETED').count()
            progress = int((completed_tasks / total_tasks) * 100)
            
            if project.progress != progress:
                project.progress = progress
                project.save(update_fields=['progress'])
                updated += 1
    
    return f'Updated progress for {updated} projects'


@shared_task
def generate_project_report(project_id, user_id):
    """
    Generate comprehensive project report.
    Heavy operation, run async.
    """
    try:
        from accounts.models import CustomUser
        
        project = Project.objects.get(id=project_id)
        user = CustomUser.objects.get(id=user_id)
        
        report_data = {
            'project_name': project.name,
            'status': project.status,
            'progress': project.progress,
            'total_tasks': project.tasks.count(),
            'completed_tasks': project.tasks.filter(status='COMPLETED').count(),
            'overdue_tasks': project.tasks.filter(
                due_date__lt=timezone.now().date(),
                status__in=['TODO', 'IN_PROGRESS']
            ).count(),
            'team_size': project.members.count(),
        }
        
        # Create notification with report
        from notifications.models import Notification
        Notification.objects.create(
            recipient=user,
            notification_type='STATUS_CHANGE',
            title='Project Report Ready',
            message=f'Report for "{project.name}" has been generated.',
            content_object=project
        )
        
        return report_data
    except (Project.DoesNotExist, CustomUser.DoesNotExist) as e:
        return f'Error: {str(e)}'