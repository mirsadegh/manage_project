# activity/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from .models import ActivityLog, ActivityFeed
from .serializers import ActivityLogSerializer, ActivityFeedSerializer
from django.db.models import Count, Q

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
        """Get recent activities the requester can access. """
        activities = self._accessible_activities(request.user).select_related('content_type')[:100]
        
        page = self.paginate_queryset(activities)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(activities, many=True)
        return Response(serializer.data)
    
    
    def _accessible_activities(self, user):
        """Activities authored by the user or on content they can access."""
        from django.db.models import Q
        from projects.models import Project
        from tasks.models import Task
        from teams.models import Team

        if user.is_superuser or getattr(user, 'role', None) == 'ADMIN':
            return ActivityLog.objects.all()

        project_ids = list(
            Project.objects.filter(
                Q(owner=user) | Q(manager=user) |
                Q(members__user=user, members__is_active=True)
            ).values_list('id', flat=True)
        )
        team_ids = list(Team.objects.filter(members=user).values_list('id', flat=True))
        project_ct = ContentType.objects.get(app_label='projects', model='project')
        task_ct = ContentType.objects.get(app_label='tasks', model='task')
        team_ct = ContentType.objects.get(app_label='teams', model='team')
        task_ids = list(
            Task.objects.filter(project_id__in=project_ids).values_list('id', flat=True)
        )
        return ActivityLog.objects.filter(
            Q(user=user) |
            Q(content_type=project_ct, object_id__in=project_ids) |
            Q(content_type=task_ct, object_id__in=task_ids) |
            Q(content_type=team_ct, object_id__in=team_ids)
        )


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