from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Notification(models.Model):
    """User notifications"""

    class NotificationType(models.TextChoices):
        MENTION = 'MENTION', 'Mentioned'
        COMMENT = 'COMMENT', 'New Comment'
        ASSIGNMENT = 'ASSIGNMENT', 'Task Assigned'
        PROJECT_INVITE = 'PROJECT_INVITE', 'Project Invitation'
        TASK_COMPLETED = 'TASK_COMPLETED', 'Task Completed'
        DEADLINE_REMINDER = 'DEADLINE_REMINDER', 'Deadline Reminder'
        PROJECT_UPDATE = 'PROJECT_UPDATE', 'Project Update'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )

    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices
    )

    title = models.CharField(max_length=255)
    message = models.TextField()

    # Link to related object
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # Email tracking
    is_email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.notification_type} for {self.recipient.username}"

    def mark_as_read(self):
        """Mark notification as read"""
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()


class NotificationPreference(models.Model):
    """Per-user, per-type notification preferences."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=Notification.NotificationType.choices
    )
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['notification_type']

    def __str__(self):
        return f"{self.user.username} - {self.notification_type}"


class NotificationTemplate(models.Model):
    """Templates used to render notification titles/messages/emails."""

    notification_type = models.CharField(
        max_length=20,
        choices=Notification.NotificationType.choices
    )
    title_template = models.TextField()
    message_template = models.TextField()
    email_subject_template = models.TextField()
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['notification_type']

    def __str__(self):
        return f"Template: {self.notification_type}"
