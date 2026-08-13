from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification, NotificationPreference


@receiver(post_save, sender=Notification)
def trigger_email_notification(sender, instance, created, **kwargs):
    """When a notification is created and the recipient has email enabled,
    dispatch the email sending task."""
    if not created:
        return

    preference = NotificationPreference.objects.filter(
        user=instance.recipient,
        notification_type=instance.notification_type,
        email_enabled=True,
    ).first()
    if preference:
        from .tasks import send_email_notification
        send_email_notification.delay(instance.id)


@receiver(post_save, sender='comments.CommentMention')
def create_mention_notification(sender, instance, created, **kwargs):
    """Create a notification when a user is mentioned in a comment."""
    if not created:
        return

    Notification.objects.create(
        recipient=instance.mentioned_user,
        sender=instance.mentioned_by,
        notification_type=Notification.NotificationType.MENTION,
        title='You were mentioned in a comment',
        message=f'{instance.mentioned_by.get_full_name()} mentioned you in a comment',
        content_object=instance.comment,
    )


@receiver(post_save, sender='teams.TeamInvitation')
def create_invitation_notification(sender, instance, created, **kwargs):
    """Create a notification when a user is invited to a team/project."""
    if not created:
        return

    Notification.objects.create(
        recipient=instance.invited_user,
        sender=instance.invited_by,
        notification_type=Notification.NotificationType.PROJECT_INVITE,
        title=f'You were invited to {instance.team.name}',
        message=f'{instance.invited_by.get_full_name() if instance.invited_by else "Someone"} invited you to {instance.team.name}',
        content_object=instance.team,
    )
