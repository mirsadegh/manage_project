from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Notification, NotificationPreference, NotificationTemplate

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    """
    Notification serializer.

    All content fields (recipient, sender, notification_type, title,
    message) are read-only. Notifications are created server-side by
    signals and tasks. Clients can only read and mark-as-read via
    dedicated endpoints.
    """

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'sender', 'notification_type',
            'title', 'message', 'is_read', 'is_email_sent',
            'read_at', 'email_sent_at', 'created_at',
        ]
        read_only_fields = fields  # ALL fields are read-only


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences."""

    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'user', 'notification_type', 'in_app_enabled',
            'email_enabled', 'push_enabled', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """Serializer for notification templates."""

    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'notification_type', 'title_template', 'message_template',
            'email_subject_template', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
