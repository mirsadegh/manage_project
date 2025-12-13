# notifications/utils.py

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)


def send_realtime_notification(user, notification_data):
    """
    Send a real-time notification to a specific user via WebSocket.
    
    Args:
        user: CustomUser object
        notification_data: dict containing notification details
            - type: notification type
            - title: notification title
            - message: notification message
            - id: notification ID (optional)
            - created_at: timestamp (optional)
    
    Example:
        notification_data = {
            'type': 'TASK_ASSIGNED',
            'title': 'New Task',
            'message': 'You have been assigned to a task',
            'id': 123,
            'created_at': '2025-01-20T10:30:00Z'
        }
        send_realtime_notification(user, notification_data)
    """
    channel_layer = get_channel_layer()
    group_name = f'user_{user.id}_notifications'
    
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'notification_message',
                'notification': notification_data
            }
        )
        logger.info(f'Sent real-time notification to user {user.username}')
    except Exception as e:
        logger.error(f'Failed to send notification to {user.username}: {str(e)}')


def broadcast_project_update(project_slug, update_type, update_data):
    """
    Broadcast an update to all users watching a project.
    
    Args:
        project_slug: str - Project slug
        update_type: str - Type of update ('task_update', 'project_update', 'member_joined')
        update_data: dict - Update details
    
    Example:
        broadcast_project_update(
            'my-project',
            'task_update',
            {
                'task_id': 123,
                'task_title': 'New Task',
                'status': 'TODO'
            }
        )
    """
    channel_layer = get_channel_layer()
    group_name = f'project_{project_slug}'
    
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': update_type,  # Maps to consumer method: task_update, project_update, etc.
                'task' if update_type == 'task_update' else 'project' if update_type == 'project_update' else 'member': update_data
            }
        )
        logger.info(f'Broadcast {update_type} to project {project_slug}')
    except Exception as e:
        logger.error(f'Failed to broadcast to project {project_slug}: {str(e)}')


def notify_project_members(project, notification_type, title, message):
    """
    Send notification to all members of a project.
    
    Args:
        project: Project object
        notification_type: str - Type of notification
        title: str - Notification title
        message: str - Notification message
    """
    from .models import Notification
    
    members = project.members.all().select_related('user')
    
    for member in members:
        # Create database notification
        notification = Notification.objects.create(
            recipient=member.user,
            notification_type=notification_type,
            title=title,
            message=message,
            content_object=project
        )
        
        # Send real-time notification
        notification_data = {
            'id': notification.id,
            'type': notification_type,
            'title': title,
            'message': message,
            'created_at': notification.created_at.isoformat()
        }
        send_realtime_notification(member.user, notification_data)