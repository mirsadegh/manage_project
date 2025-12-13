# activity/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from .models import ActivityLog, ActivityFeed
from .serializers import ActivityLogSerializer, ActivityFeedSerializer


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for activity logs (read-only).
    
    Endpoints:
    - GET /activity-logs/ - List activity logs
    - GET /activity-logs/{id}/ - Get activity detail
    - GET /activity-logs/my-activity/ - Get current user's activities
    """
    
    queryset = ActivityLog.objects.all()
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter activity logs"""
        queryset = ActivityLog.objects.select_related('user', 'content_type')
        
        # Filter by content type
        content_type = self.request.query_params.get('content_type')
        object_id = self.request.query_params.get('object_id')
        
        if content_type and object_id:
            try:
                ct = ContentType.objects.get(model=content_type.lower())
                queryset = queryset.filter(content_type=ct, object_id=object_id)
            except ContentType.DoesNotExist:
                queryset = queryset.none()
        
        # Filter by action
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)
        
        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def my_activity(self, request):
        """Get current user's activity history"""
        activities = ActivityLog.objects.filter(
            user=request.user
        ).select_related('content_type')[:50]  # Last 50 activities
        
        serializer = self.get_serializer(activities, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent activities across the system"""
        # Limit to activities user has access to
        activities = ActivityLog.objects.all()[:100]  # Last 100
        
        page = self.paginate_queryset(activities)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(activities, many=True)
        return Response(serializer.data)


class ActivityFeedViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for user's personalized activity feed.
    
    Endpoints:
    - GET /activity-feed/ - Get user's activity feed
    - GET /activity-feed/{id}/ - Get feed item detail
    - POST /activity-feed/{id}/mark_read/ - Mark as read
    - POST /activity-feed/mark_all_read/ - Mark all as read
    """
    
    serializer_class = ActivityFeedSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get current user's activity feed"""
        return ActivityFeed.objects.filter(
            user=self.request.user
        ).select_related('activity', 'activity__user', 'activity__content_type')
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a feed item as read"""
        feed_item = self.get_object()
        feed_item.is_read = True
        feed_item.save(update_fields=['is_read'])
        
        return Response({'message': 'Marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all feed items as read"""
        updated = ActivityFeed.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)
        
        return Response({
            'message': f'Marked {updated} items as read'
        })
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread feed items"""
        count = ActivityFeed.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        
        return Response({'unread_count': count})