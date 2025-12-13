# files/models.py

from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
import os
import hashlib
import magic
from PIL import Image


def get_upload_path(instance, filename):
    """
    Generate secure upload path with user ID and timestamp.
    Format: uploads/{content_type}/{object_id}/{user_id}/{timestamp}_{filename}
    """
    from django.utils import timezone
    import uuid
    
    # Get file extension
    ext = filename.split('.')[-1] if '.' in filename else ''
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4().hex[:8]}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
    if ext:
        unique_filename = f"{unique_filename}.{ext}"
    
    # Build path
    path = os.path.join(
        'uploads',
        instance.content_type.model,
        str(instance.object_id),
        str(instance.uploaded_by.id),
        unique_filename
    )
    
    return path


def validate_file_size(file):
    """Validate file size (max 10MB)"""
    max_size = 10 * 1024 * 1024  # 10 MB
    
    if file.size > max_size:
        raise ValidationError(f'File size cannot exceed {max_size / (1024 * 1024)} MB')


def validate_file_type(file):
    """Validate file type using python-magic"""
    # Allowed MIME types
    allowed_types = [
        # Documents
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain',
        'text/csv',
        
        # Images
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/svg+xml',
        
        # Archives
        'application/zip',
        'application/x-rar-compressed',
        'application/x-7z-compressed',
        'application/gzip',
        
        # Code
        'text/html',
        'text/css',
        'application/javascript',
        'application/json',
        'application/xml',
    ]
    
    # Read file content to detect MIME type
    file.seek(0)
    file_content = file.read(2048)  # Read first 2KB
    file.seek(0)  # Reset file pointer
    
    mime = magic.from_buffer(file_content, mime=True)
    
    if mime not in allowed_types:
        raise ValidationError(f'File type "{mime}" is not allowed')


class Attachment(models.Model):
    """
    Secure file attachments for tasks, projects, comments, etc.
    """
    
    # Generic foreign key
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of object this file is attached to"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of object this file is attached to"
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # File details
    file = models.FileField(
        upload_to=get_upload_path,
        validators=[
            validate_file_size,
            FileExtensionValidator(
                allowed_extensions=[
                    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
                    'txt', 'csv', 'jpg', 'jpeg', 'png', 'gif', 'webp',
                    'svg', 'zip', 'rar', '7z', 'gz', 'html', 'css',
                    'js', 'json', 'xml'
                ]
            )
        ],
        help_text="The uploaded file"
    )
    original_filename = models.CharField(
        max_length=255,
        help_text="Original filename from upload"
    )
    file_size = models.BigIntegerField(
        help_text="File size in bytes"
    )
    file_type = models.CharField(
        max_length=100,
        help_text="MIME type of the file"
    )
    file_hash = models.CharField(
        max_length=64,
        help_text="SHA256 hash of file content",
        db_index=True
    )
    
    # Image-specific fields (if applicable)
    is_image = models.BooleanField(default=False)
    image_width = models.IntegerField(null=True, blank=True)
    image_height = models.IntegerField(null=True, blank=True)
    thumbnail = models.ImageField(
        upload_to='thumbnails/',
        null=True,
        blank=True,
        help_text="Thumbnail for image files"
    )
    
    # Upload info
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_files',
        help_text="User who uploaded this file"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Description
    description = models.TextField(
        blank=True,
        help_text="Optional file description"
    )
    
    # Security flags
    is_scanned = models.BooleanField(
        default=False,
        help_text="Whether file has been scanned for viruses"
    )
    is_safe = models.BooleanField(
        default=True,
        help_text="Whether file passed security scan"
    )
    
    # Download tracking
    download_count = models.IntegerField(
        default=0,
        help_text="Number of times file has been downloaded"
    )
    last_downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last download timestamp"
    )
    
    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['uploaded_by', 'uploaded_at']),
            models.Index(fields=['file_hash']),
        ]
        verbose_name = 'Attachment'
        verbose_name_plural = 'Attachments'
    
    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_by.username})"
    
    def clean(self):
        """Validate file before saving"""
        if self.file:
            # Validate file type
            validate_file_type(self.file)
            
            # Validate file size
            validate_file_size(self.file)
    
    def save(self, *args, **kwargs):
        if self.file and not self.pk:
            # Set original filename
            self.original_filename = os.path.basename(self.file.name)
            
            # Set file size
            self.file_size = self.file.size
            
            # Detect MIME type
            self.file.seek(0)
            file_content = self.file.read()
            self.file.seek(0)
            
            self.file_type = magic.from_buffer(file_content, mime=True)
            
            # Calculate file hash
            self.file_hash = hashlib.sha256(file_content).hexdigest()
            
            # Check if it's an image
            if self.file_type.startswith('image/'):
                self.is_image = True
                self._process_image()
        
        super().save(*args, **kwargs)
    
    def _process_image(self):
        """Process image files: get dimensions and create thumbnail"""
        try:
            # Open image
            image = Image.open(self.file)
            
            # Get dimensions
            self.image_width, self.image_height = image.size
            
            # Create thumbnail (max 200x200)
            thumbnail_size = (200, 200)
            image.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
            
            # Save thumbnail
            from io import BytesIO
            from django.core.files.base import ContentFile
            
            thumb_io = BytesIO()
            image.save(thumb_io, format='PNG')
            
            thumbnail_name = f"thumb_{self.original_filename}.png"
            self.thumbnail.save(
                thumbnail_name,
                ContentFile(thumb_io.getvalue()),
                save=False
            )
            
        except Exception as e:
            print(f"Error processing image: {e}")
    
    def delete(self, *args, **kwargs):
        """Delete file from storage when model is deleted"""
        # Delete actual file
        if self.file:
            self.file.delete(save=False)
        
        # Delete thumbnail
        if self.thumbnail:
            self.thumbnail.delete(save=False)
        
        super().delete(*args, **kwargs)
    
    @property
    def file_size_mb(self):
        """Return file size in MB"""
        return round(self.file_size / (1024 * 1024), 2)
    
    @property
    def file_extension(self):
        """Get file extension"""
        return os.path.splitext(self.original_filename)[1].lower()
    
    def increment_download_count(self):
        """Increment download counter"""
        from django.utils import timezone
        self.download_count += 1
        self.last_downloaded_at = timezone.now()
        self.save(update_fields=['download_count', 'last_downloaded_at'])
        
        