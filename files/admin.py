from django.contrib import admin
from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    # از فیلد original_filename استفاده کنید که در مدل شما وجود دارد
    list_display = [
        'id', 
        'original_filename',  # <-- اصلاح شد
        'content_type', 
        'object_id', 
        'uploaded_by', 
        'file_size_mb',      # <-- استفاده از پراپرتی برای نمایش بهتر
        'uploaded_at'
    ]
    
    list_filter = ['content_type', 'uploaded_at']
    search_fields = ['original_filename', 'description', 'uploaded_by__username'] # <-- اصلاح شد
    raw_id_fields = ['uploaded_by']
    
    readonly_fields = [
        'original_filename',  # <-- اصلاح شد
        'file_size_mb',      # <-- استفاده از پراپرتی برای نمایش بهتر
        'file_type', 
        'uploaded_at'
    ]
    
    date_hierarchy = 'uploaded_at'
    
    def file_size_mb(self, obj):
        return f"{obj.file_size_mb} MB"
    file_size_mb.short_description = 'File Size'
    
    