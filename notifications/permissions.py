# notifications/permissions.py
from rest_framework.permissions import BasePermission


class IsNotificationRecipient(BasePermission):
    """
    Object-level permission: only the notification's recipient can
    access it. Defense-in-depth alongside the queryset filter in
    NotificationViewSet.get_queryset.
    """

    message = "You can only access your own notifications."

    def has_object_permission(self, request, view, obj):
        # obj is a Notification; recipient is a FK to User
        return obj.recipient == request.user
