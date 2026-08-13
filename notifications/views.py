from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user notifications.

    Endpoints:
    - GET /notifications/ - List current user's notifications (filter: is_read, notification_type)
    - GET /notifications/<id>/ - Get a notification
    - DELETE /notifications/<id>/ - Delete a notification
    - GET /notifications/unread-count/ - Count of unread notifications
    - POST /notifications/<id>/mark_as_read/ - Mark a notification as read
    - POST /notifications/mark_all_as_read/ - Mark all notifications as read
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)

        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == 'true')

        notification_type = self.request.query_params.get('notification_type')
        if notification_type:
            qs = qs.filter(notification_type=notification_type)

        return qs

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """Return the number of unread notifications for the current user."""
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({'count': count})

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a single notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all of the current user's notifications as read."""
        updated = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({'updated': updated})
