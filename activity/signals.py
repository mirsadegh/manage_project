# activity/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from tasks.models import Task
from projects.models import Project
from .utils import log_activity


@receiver(post_save, sender=Task)
def log_task_activity(sender, instance, created, **kwargs):
    """Log task creation and updates"""
    if created:
        log_activity(
            user=instance.created_by,
            action='CREATED',
            content_object=instance,
            description=f'Created task "{instance.title}" in project "{instance.project.name}"'
        )
    else:
        pass
        # Check if status changed
        # if hasattr(instance, '_original_status') and instance._original_status != instance.status:
        #     log_activity(
        #         user=instance.created_by,  # or get from request
        #         action='STATUS_CHANGED',
        #         content_object=instance,
        #         description=f'Changed task "{instance.title}" status from {instance._original_status} to {instance.status}',
        #         changes={
        #             'status': {
        #                 'old': instance._original_