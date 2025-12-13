# files/admin.py

from django.contrib import admin
from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'filename', 'content_type', 'object_id', 'uploaded_by', 'file_size_mb', 'uploaded_at']
    list_filter = ['content_type', 'uploaded_at']
    search_fields = ['filename', 'description', 'uploaded_by__username']
    raw_id_fields = ['uploaded_by']
    readonly_fields = ['filename', 'file_size', 'file_type', 'uploaded_at']
    date_hierarchy = 'uploaded_at'
    
    def file_size_mb(self, obj):
        return f"{obj.file_size_mb} MB"
    file_size_mb.short_description = 'File Size'