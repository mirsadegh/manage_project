from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import os

def get_upload_path(instance, filename):
    """Generate upload path based on content type"""
    return f"uploads/{instance.content_type.model}/{instance.object_id}/{filename}"

class Attachment(models.Model):
    """File attachments for tasks, projects, comments, etc."""
    
    # Generic foreign key
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # File details
    file = models.FileField(upload_to=get_upload_path)
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField()  # in bytes
    file_type = models.CharField(max_length=100)  # MIME type
    
    # Upload info
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_files'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Description
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return self.filename
    
    def save(self, *args, **kwargs):
        if self.file:
            self.filename = os.path.basename(self.file.name)
            self.file_size = self.file.size
        super().save(*args, **kwargs)
    
    @property
    def file_size_mb(self):
        """Return file size in MB"""
        return round(self.file_size / (1024 * 1024), 2)