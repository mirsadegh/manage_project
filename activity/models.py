from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class ActivityLog(models.Model):
    """Activity log for audit trail"""
    
    class Action(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        UPDATED = 'UPDATED', 'Updated'
        DELETED = 'DELETED', 'Deleted'
        ASSIGNED = 'ASSIGNED', 'Assigned'
        COMMENTED = 'COMMENTED', 'Commented'
        STATUS_CHANGED = 'STATUS_CHANGED', 'Status Changed'
        UPLOADED = 'UPLOADED', 'Uploaded File'
    
    # Who did it
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='activities'
    )
    
    # What was done
    action = models.CharField(max_length=20, choices=Action.choices)
    description = models.TextField()
    
    # On what object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Changes (JSON field to store before/after values)
    changes = models.JSONField(null=True, blank=True)
    
    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'action']),
        ]
    
    def __str__(self):
        return f"{self.user} {self.action} {self.content_object}"



