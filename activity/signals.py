# activity/signals.py

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from tasks.models import Task
from projects.models import Project, ProjectMember
from comments.models import Comment
from .models import ActivityLog


@receiver(pre_save, sender=Task)
def store_original_task_values(sender, instance, **kwargs):
    """
    Store original values before save to detect changes.
    This runs before the task is saved.
    """
    if instance.pk:
        try:
            original = Task.objects.get(pk=instance.pk)
            instance._original_status = original.status
            instance._original_assignee = original.assignee
        except Task.DoesNotExist:
            pass


@receiver(post_save, sender=Task)
def log_task_activity(sender, instance, created, **kwargs):
    """Log task creation and updates"""
    if created:
        # Task was created
        ActivityLog.objects.create(
            user=instance.created_by,
            action=ActivityLog.Action.CREATED,
            content_object=instance,
            description=f'Created task "{instance.title}"'
        )
    else:
        
        # Check if status changed
        if hasattr(instance, '_original_status') and instance._original_status != instance.status:
            ActivityLog.objects.create(
                user=instance.created_by,  # Should ideally come from request
                action=ActivityLog.Action.STATUS_CHANGED,
                content_object=instance,
                description=f'Changed status of "{instance.title}" from {instance._original_status} to {instance.status}',
                changes={
                    'field': 'status',
                    'old_value': instance._original_status,
                    'new_value': instance.status
                }
            )
        
        # Check if assignee changed
        if hasattr(instance, '_original_assignee') and instance._original_assignee != instance.assignee:
            if instance.assignee:
                ActivityLog.objects.create(
                    user=instance.created_by,
                    action=ActivityLog.Action.ASSIGNED,
                    content_object=instance,
                    description=f'Assigned "{instance.title}" to {instance.assignee.get_full_name()}',
                    changes={
                        'field': 'assignee',
                        'old_value': instance._original_assignee.username if instance._original_assignee else None,
                        'new_value': instance.assignee.username
                    }
                )
            else:
                ActivityLog.objects.create(
                    user=instance.created_by,
                    action=ActivityLog.Action.UNASSIGNED,
                    content_object=instance,
                    description=f'Unassigned "{instance.title}"'
                )


@receiver(post_save, sender=Project)
def log_project_activity(sender, instance, created, **kwargs):
    """Log project creation"""
    if created:
        ActivityLog.objects.create(
            user=instance.owner,
            action=ActivityLog.Action.CREATED,
            content_object=instance,
            description=f'Created project "{instance.name}"'
        )


@receiver(post_save, sender=ProjectMember)
def log_member_joined(sender, instance, created, **kwargs):
    """Log when a member joins a project"""
    if created:
        ActivityLog.objects.create(
            user=instance.user,
            action=ActivityLog.Action.JOINED,
            content_object=instance.project,
            description=f'{instance.user.get_full_name()} joined project "{instance.project.name}"'
        )


@receiver(post_delete, sender=ProjectMember)
def log_member_left(sender, instance, **kwargs):
    """Log when a member leaves a project"""
    ActivityLog.objects.create(
        user=instance.user,
        action=ActivityLog.Action.LEFT,
        content_object=instance.project,
        description=f'{instance.user.get_full_name()} left project "{instance.project.name}"'
    )


@receiver(post_save, sender=Comment)
def log_comment_activity(sender, instance, created, **kwargs):
    """Log when a comment is created"""
    if created:
        ActivityLog.objects.create(
            user=instance.author,
            action=ActivityLog.Action.COMMENTED,
            content_object=instance.content_object,
            description=f'{instance.author.get_full_name()} commented on {instance.content_object}'
        )