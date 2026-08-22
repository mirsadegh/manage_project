
from rest_framework import serializers
from .models import ActivityLog, ActivityFeed
from accounts.serializers import UserSerializer


class ActivityLogSerializer(serializers.ModelSerializer):
    """Serializer for activity logs"""
    
    user = UserSerializer(read_only=True)
    content_type_name = serializers.SerializerMethodField()
    ip_address = serializers.SerializerMethodField()
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
    
    def get_ip_address(self, obj):
        """Only expose IP address to admins (PII)."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN':
                return obj.ip_address
            
            return None


class ActivityFeedSerializer(serializers.ModelSerializer):
    """Serializer for activity feed"""
    
    activity = ActivityLogSerializer(read_only=True)
    
    class Meta:
        model = ActivityFeed
        fields = [
            'id', 'activity', 'is_read', 'is_important', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']