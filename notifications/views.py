from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Count

from .models import Notification, NotificationPreference, NotificationTemplate
from .serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer,
    NotificationTemplateSerializer,
)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Notification feed for the authenticated user.

    Read-only: notifications are created server-side by signals and
    tasks. Clients can list, retrieve, and mark-as-read, but cannot
    create directly.

    Endpoints:
    - GET /notifications/ - List current user's notifications (filter: is_read, notification_type)
    - GET /notifications/<id>/ - Get a notification
    - POST /notifications/<id>/mark-read/ - Mark a notification as read
    - POST /notifications/mark-all-read/ - Mark all notifications as read
    - GET /notifications/unread-count/ - Count of unread notifications
    - GET /notifications/statistics/ - Notification statistics
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)

        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == 'true')

        notification_type = self.request.query_params.get('notification_type')
        if notification_type:
            qs = qs.filter(notification_type=notification_type)

        return qs

    @action(detail=True, methods=['post'], url_name='mark-read')
    def mark_read(self, request, pk=None):
        """Mark a single notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'], url_name='mark-all-read')
    def mark_all_read(self, request):
        """Mark all of the current user's notifications as read."""
        updated = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({'updated': updated})

    @action(detail=False, methods=['get'], url_name='unread-count')
    def unread_count(self, request):
        """Return the number of unread notifications for the current user."""
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({'unread_count': count})

    @action(detail=False, methods=['get'], url_name='statistics')
    def statistics(self, request):
        """Return notification statistics for the current user."""
        qs = Notification.objects.filter(recipient=request.user)
        total = qs.count()
        unread = qs.filter(is_read=False).count()
        by_type = dict(
            qs.values_list('notification_type')
            .annotate(count=Count('notification_type'))
            .values_list('notification_type', 'count')
        )
        return Response({
            'total_notifications': total,
            'unread_count': unread,
            'by_type': by_type,
        })


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing per-user notification preferences."""

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)


class NotificationTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing notification templates."""

    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAuthenticated]
    queryset = NotificationTemplate.objects.all()
