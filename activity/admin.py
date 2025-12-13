# activity/admin.py

from django.contrib import admin
from .models import ActivityLog, ActivityFeed


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'action', 'content_type', 'object_id', 'created_at']
    list_filter = ['action', 'content_type', 'created_at']
    search_fields = ['description', 'user__username']
    raw_id_fields = ['user']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Action Details', {
            'fields': ('user', 'action', 'description')
        }),
        ('Target Object', {
            'fields': ('content_type', 'object_id')
        }),
        ('Change Details', {
            'fields': ('changes',),
            'classes': ('collapse',)
        }),
        ('Request Info', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )


@admin.register(ActivityFeed)
class ActivityFeedAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'activity', 'is_read', 'is_important', 'created_at']
    list_filter = ['is_read', 'is_important', 'created_at']
    search_fields = ['user__username', 'activity__description']
    raw_id_fields = ['user', 'activity']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    