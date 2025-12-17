import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


def send_notification_to_user(user_id, notification_data):
    """
    Send a real-time notification to a specific user.
    
    Args:
        user_id: The ID of the user to notify
        notification_data: Dict containing notification details
        
    Example:
        send_notification_to_user(
            user_id=1,
            notification_data={
                'id': 123,
                'title': 'New Task Assigned',
                'message': 'You have been assigned to Task XYZ',
                'notification_type': 'task_assigned',
                'created_at': '2025-01-15T10:30:00Z',
                'data': {'task_id': 456},
            }
        )
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{user_id}_notifications',
            {
                'type': 'notification_message',
                'notification': notification_data,
            }
        )
        logger.debug(f"Notification sent to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send notification to user {user_id}: {e}")


def send_notification_to_users(user_ids, notification_data):
    """
    Send a notification to multiple users.
    
    Args:
        user_ids: List of user IDs to notify
        notification_data: Dict containing notification details
    """
    for user_id in user_ids:
        send_notification_to_user(user_id, notification_data)


def send_bulk_notifications(user_id, notifications):
    """
    Send multiple notifications to a user at once.
    
    Args:
        user_id: The ID of the user to notify
        notifications: List of notification data dicts
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{user_id}_notifications',
            {
                'type': 'bulk_notification',
                'notifications': notifications,
                'count': len(notifications),
            }
        )
    except Exception as e:
        logger.error(f"Failed to send bulk notifications to user {user_id}: {e}")


def update_unread_count(user_id, count=None):
    """
    Update unread notification count for a user.
    If count is None, the client should refetch the count.
    
    Args:
        user_id: The ID of the user
        count: The new unread count (optional)
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{user_id}_notifications',
            {
                'type': 'unread_count_update',
                'count': count,
            }
        )
    except Exception as e:
        logger.error(f"Failed to update unread count for user {user_id}: {e}")


def send_project_update(project_slug, update_data, updated_by=None, exclude_user_id=None):
    """
    Send a real-time update to all users viewing a project.
    
    Args:
        project_slug: The project's slug
        update_data: Dict containing the update details
        updated_by: Username/ID of user who made the update
        exclude_user_id: User ID to exclude from broadcast
        
    Example:
        send_project_update(
            project_slug='my-project',
            update_data={'status': 'completed', 'progress': 100},
            updated_by='john_doe'
        )
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'project_{project_slug}',
            {
                'type': 'project_update',
                'data': update_data,
                'updated_by': updated_by,
                'timestamp': timezone.now().isoformat(),
            }
        )
        logger.debug(f"Project update sent to {project_slug}")
    except Exception as e:
        logger.error(f"Failed to send project update to {project_slug}: {e}")


def send_task_update(project_slug, task_data, action='update', updated_by=None):
    """
    Send a real-time task update to all users viewing a project.
    
    Args:
        project_slug: The project's slug
        task_data: Dict containing the task details
        action: One of 'create', 'update', 'delete'
        updated_by: Username/ID of user who made the update
    """
    try:
        channel_layer = get_channel_layer()
        event_type = {
            'create': 'task_created',
            'update': 'task_update',
            'delete': 'task_deleted',
        }.get(action, 'task_update')
        
        message = {
            'type': event_type,
            'task': task_data,
            'action': action,
            'updated_by': updated_by,
            'timestamp': timezone.now().isoformat(),
        }
        
        if action == 'delete':
            message['task_id'] = task_data.get('id') or task_data
            message['deleted_by'] = updated_by
        
        async_to_sync(channel_layer.group_send)(
            f'project_{project_slug}',
            message
        )
        logger.debug(f"Task {action} sent to project {project_slug}")
    except Exception as e:
        logger.error(f"Failed to send task update to {project_slug}: {e}")


def send_comment_notification(project_slug, comment_data, task_id=None):
    """
    Send a real-time comment notification.
    
    Args:
        project_slug: The project's slug
        comment_data: Dict containing comment details
        task_id: Optional task ID the comment belongs to
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'project_{project_slug}',
            {
                'type': 'comment_added',
                'comment': comment_data,
                'task_id': task_id,
                'timestamp': timezone.now().isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"Failed to send comment notification: {e}")


def broadcast_member_change(project_slug, member_data, action='joined'):
    """
    Broadcast member join/leave events.
    
    Args:
        project_slug: The project's slug
        member_data: Dict containing member details
        action: 'joined' or 'left'
    """
    try:
        channel_layer = get_channel_layer()
        event_type = 'member_joined' if action == 'joined' else 'member_left'
        
        async_to_sync(channel_layer.group_send)(
            f'project_{project_slug}',
            {
                'type': event_type,
                'member': member_data,
                'timestamp': timezone.now().isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"Failed to broadcast member change: {e}")


def notify_project_members(project_slug, message, notification_type='info', sender=None):
    """
    Notify all members of a project about an event or update.
    
    Args:
        project_slug: The project's slug
        message: The notification message
        notification_type: Type of notification (e.g., 'info', 'warning', 'error')
        sender: User who triggered the notification (optional)
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'project_{project_slug}',
            {
                'type': 'project_notification',
                'message': message,
                'notification_type': notification_type,
                'sender': sender,
                'timestamp': timezone.now().isoformat(),
            }
        )
        logger.debug(f"Notification sent to project {project_slug}: {message}")
    except Exception as e:
        logger.error(f"Failed to notify project members for {project_slug}: {e}")


def broadcast_project_update(project_slug, update_data, updated_by=None):
    """
    Broadcast a project update to all members of a project.
    
    Args:
        project_slug: The project's slug
        update_data: Dict containing the update details
        updated_by: User who made the update (optional)
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'project_{project_slug}',
            {
                'type': 'project_broadcast',
                'update_data': update_data,
                'updated_by': updated_by,
                'timestamp': timezone.now().isoformat(),
            }
        )
        logger.debug(f"Broadcast sent to project {project_slug}: {update_data}")
    except Exception as e:
        logger.error(f"Failed to broadcast project update for {project_slug}: {e}")


def send_realtime_notification(user, notification_data):
    """
    Send a real-time notification to a specific user.
    
    Args:
        user: The user to notify
        notification_data: Dict containing notification details
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{user.id}_notifications',
            {
                'type': 'notification_message',
                'notification': notification_data,
            }
        )
        logger.debug(f"Real-time notification sent to user {user.id}")
    except Exception as e:
        logger.error(f"Failed to send real-time notification to user {user.id}: {e}")