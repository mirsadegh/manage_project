
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class ActivityLog(models.Model):
    """
    Activity log for audit trail.
    Tracks all important actions in the system.
    """
    
    class Action(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        UPDATED = 'UPDATED', 'Updated'
        DELETED = 'DELETED', 'Deleted'
        ASSIGNED = 'ASSIGNED', 'Assigned'
        UNASSIGNED = 'UNASSIGNED', 'Unassigned'
        COMMENTED = 'COMMENTED', 'Commented'
        STATUS_CHANGED = 'STATUS_CHANGED', 'Status Changed'
        UPLOADED = 'UPLOADED', 'Uploaded File'
        DOWNLOADED = 'DOWNLOADED', 'Downloaded File'
        INVITED = 'INVITED', 'Invited'
        JOINED = 'JOINED', 'Joined'
        LEFT = 'LEFT', 'Left'
        ARCHIVED = 'ARCHIVED', 'Archived'
        RESTORED = 'RESTORED', 'Restored'
    
    # Who performed the action
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='activities',
        help_text="User who performed the action"
    )
    
    # What action was performed
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        help_text="Type of action performed"
    )
    description = models.TextField(
        help_text="Human-readable description of the action"
    )
    
    # On what object
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of object affected"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of object affected"
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Additional details
    changes = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON containing before/after values of changes"
    )
    
    # Request metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Browser/device user agent string"
    )
    
    # Timestamp
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'action']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
    
    def __str__(self):
        username = self.user.username if self.user else 'System'
        return f"{username} {self.action} {self.content_object}"
    
    @classmethod
    def log_activity(cls, user, action, content_object, description, changes=None, request=None):
        """
        Convenience method to log an activity.
        
        Args:
            user: User who performed the action
            action: Action type (from Action choices)
            content_object: The object affected
            description: Human-readable description
            changes: Dict of changes (optional)
            request: HTTP request object (optional, for IP/user agent)
        
        Returns:
            ActivityLog instance
        """
        ip_address = None
        user_agent = ''
        
        if request:
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            # Get user agent
            user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        return cls.objects.create(
            user=user,
            action=action,
            content_object=content_object,
            description=description,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent
        )


class ActivityFeed(models.Model):
    """
    Personalized activity feed for users.
    Shows relevant activities based on user's projects and teams.
    """
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activity_feed',
        help_text="User this feed item belongs to"
    )
    activity = models.ForeignKey(
        ActivityLog,
        on_delete=models.CASCADE,
        related_name='feed_items',
        help_text="The activity log entry"
    )
    
    # Feed metadata
    is_read = models.BooleanField(
        default=False,
        help_text="Whether user has seen this activity"
    )
    is_important = models.BooleanField(
        default=False,
        help_text="Whether this is marked as important"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'activity']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]
        verbose_name = 'Activity Feed Item'
        verbose_name_plural = 'Activity Feed Items'
    
    def __str__(self):
        return f"Feed for {self.user.username}: {self.activity}"
