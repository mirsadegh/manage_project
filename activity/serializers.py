
from rest_framework import serializers
from .models import ActivityLog, ActivityFeed
from accounts.serializers import UserSerializer


class ActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for activity logs"""
    
    user = UserSerializer(read_only=True)
    content_type_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ActivityLog
        fields = [
            'id', 'user', 'action', 'description',
            'content_type', 'content_type_name', 'object_id',
            'changes', 'ip_address', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_content_type_name(self, obj):
        """Get human-readable content type name"""
        return obj.content_type.model


class ActivityFeedSerializer(serializers.ModelSerializer):
    """Serializer for activity feed"""
    
    activity = ActivityLogSerializer(read_only=True)
    
    class Meta:
        model = ActivityFeed
        fields = [
            'id', 'activity', 'is_read', 'is_important', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']