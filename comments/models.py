from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Comment(models.Model):
    """
    Comments on tasks, projects, or any other content.
    Uses generic foreign key to allow comments on multiple models.
    """
    
    # Generic foreign key setup
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="The type of object this comment is attached to"
    )
    object_id = models.PositiveIntegerField(
        help_text="The ID of the object this comment is attached to"
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Comment details
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="User who wrote this comment"
    )
    text = models.TextField(
        help_text="Comment text content"
    )
    
    # Threading (for nested comments/replies)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        help_text="Parent comment if this is a reply"
    )
    
    # Metadata
    is_edited = models.BooleanField(
        default=False,
        help_text="Whether this comment has been edited"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['author', 'created_at']),
        ]
        verbose_name = 'Comment'
        verbose_name_plural = 'Comments'
    
    def __str__(self):
        return f"Comment by {self.author.username} on {self.content_object}"
    
    def save(self, *args, **kwargs):
        # Mark as edited if it's an update (not creation)
        if self.pk:
            self.is_edited = True
        super().save(*args, **kwargs)
    
    @property
    def reply_count(self):
        """Get the number of replies to this comment"""
        return self.replies.count()
    
    @property
    def is_reply(self):
        """Check if this comment is a reply to another comment"""
        return self.parent is not None
    
    def get_thread(self):
        """Get all comments in this thread (parent + all descendants)"""
        if self.parent:
            return self.parent.get_thread()
        
        # This is the parent, return self + all descendants
        thread = [self]
        thread.extend(self._get_descendants())
        return thread
    
    def _get_descendants(self):
        """Recursively get all descendant comments"""
        descendants = []
        for reply in self.replies.all():
            descendants.append(reply)
            descendants.extend(reply._get_descendants())
        return descendants


class CommentMention(models.Model):
    """
    Track users mentioned in comments (@username).
    Used for sending notifications.
    """
    
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='mentions'
    )
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comment_mentions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['comment', 'mentioned_user']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.mentioned_user.username} mentioned in comment {self.comment.id}"


class CommentReaction(models.Model):
    """
    Reactions to comments (like, love, etc.).
    """
    
    class ReactionType(models.TextChoices):
        LIKE = 'LIKE', '👍'
        LOVE = 'LOVE', '❤️'
        LAUGH = 'LAUGH', '😄'
        CONFUSED = 'CONFUSED', '😕'
        CELEBRATE = 'CELEBRATE', '🎉'
    
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comment_reactions'
    )
    reaction_type = models.CharField(
        max_length=10,
        choices=ReactionType.choices,
        default=ReactionType.LIKE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['comment', 'user', 'reaction_type']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} reacted {self.reaction_type} to comment {self.comment.id}"