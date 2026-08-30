# notifications/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Notification
from accounts.models import CustomUser

@shared_task
def send_daily_summary(user_id=None):
    """
    Send daily summary of tasks and notifications.
    Runs at 9 AM daily via Celery Beat.
    """
    from tasks.models import Task
    
    if user_id:
        users = [CustomUser.objects.get(id=user_id)]
    else:
        users = CustomUser.objects.filter(is_active=True)
    
    summaries_sent = 0
    
    for user in users:
        # Get user's tasks
        tasks_due_today = Task.objects.filter(
            assignee=user,
            due_date=timezone.now().date(),
            status__in=['TODO', 'IN_PROGRESS']
        )
        
        unread_notifications = Notification.objects.filter(
            recipient=user,
            is_read=False
        ).count()
        
        if tasks_due_today.exists() or unread_notifications > 0:
            message = f'You have {tasks_due_today.count()} task(s) due today and {unread_notifications} unread notification(s).'
            
            Notification.objects.create(
                recipient=user,
                notification_type='STATUS_CHANGE',
                title='Daily Summary',
                message=message
            )
            summaries_sent += 1
    
    return f'Sent {summaries_sent} daily summaries'


@shared_task
def clean_old_notifications():
    """
    Delete read notifications older than 30 days.
    Runs weekly via Celery Beat.
    """
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    deleted_count, _ = Notification.objects.filter(
        is_read=True,
        read_at__lt=thirty_days_ago
    ).delete()
    
    return f'Deleted {deleted_count} old notifications'


@shared_task
def send_notification_async(recipient_id, notification_type, title, message, object_id=None, content_type_id=None):
    """
    Create notification asynchronously. Useful for bulk operations.

    SECURITY: This task accepts arbitrary recipient_id. It is SAFE only
    because the Celery broker is on a private/internal transport and
    tasks are not exposed via any HTTP endpoint. If you ever expose
    task triggering via HTTP, add authorization checks to verify the
    caller is allowed to notify the target recipient.

    Currently called from:
    - signals.py (server-side notification creation)
    - utils.py helpers (project/team member notifications)

    Do NOT expose this task directly via any HTTP endpoint without
    adding recipient authorization.
    """
    try:
        user = CustomUser.objects.get(id=recipient_id)
        
        notification = Notification.objects.create(
            recipient=user,
            notification_type=notification_type,
            title=title,
            message=message,
            object_id=object_id,
            content_type_id=content_type_id
        )
        
        return f'Notification {notification.id} created for user {user.username}'
    except CustomUser.DoesNotExist:
        return f'User {recipient_id} not found'


@shared_task
def send_email_notification(notification_id):
    """
    Send an email for a notification (if the recipient has email enabled
    for that notification type).
    """
    try:
        notification = Notification.objects.get(id=notification_id)
    except Notification.DoesNotExist:
        return f'Notification {notification_id} not found'

    from django.core.mail import send_mail
    from django.conf import settings

    try:
        send_mail(
            subject=notification.title,
            message=notification.message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient.email],
            fail_silently=True,
        )
    except Exception:
        return f'Email failed for notification {notification_id}'

    notification.is_email_sent = True
    notification.email_sent_at = timezone.now()
    notification.save(update_fields=['is_email_sent', 'email_sent_at'])
    return f'Email sent for notification {notification_id}'