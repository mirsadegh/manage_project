from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Notification(models.Model):
    """User notifications"""
    
    class Type(models.TextChoices):
        TASK_ASSIGNED = 'TASK_ASSIGNED', 'Task Assigned'
        TASK_COMPLETED = 'TASK_COMPLETED', 'Task Completed'
        TASK_COMMENT = 'TASK_COMMENT', 'New Comment'
        TASK_DUE_SOON = 'TASK_DUE_SOON', 'Task Due Soon'
        PROJECT_INVITE = 'PROJECT_INVITE', 'Project Invitation'
        MENTION = 'MENTION', 'Mentioned'
        STATUS_CHANGE = 'STATUS_CHANGE', 'Status Changed'
    
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    notification_type = models.CharField(
        max_length=20,
        choices=Type.choices
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
        self.is_read = True
        self.read_at = timezone.now()
        self.save()
        
        
        