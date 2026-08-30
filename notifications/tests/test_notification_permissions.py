# notifications/tests/test_notification_permissions.py
"""
Regression tests for PR-5 Commit 2 fixes.

Covers:
- H-1: NotificationTemplateViewSet is admin-only (IsAdmin permission)
- M-1: NotificationPreference unique_together on (user, notification_type)
- M-2: IsNotificationRecipient permission enforces recipient-only access
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test.client import RequestFactory

from notifications.models import (
    Notification, NotificationPreference, NotificationTemplate,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


# ─── Fixtures ───

@pytest.fixture
def admin_user():
    return User.objects.create_user(
        username='notif_admin', email='admin@example.com',
        password='Test123!', role='ADMIN',
    )


@pytest.fixture
def pm_user():
    return User.objects.create_user(
        username='notif_pm', email='pm@example.com',
        password='Test123!', role='PM',
    )


@pytest.fixture
def dev_user():
    return User.objects.create_user(
        username='notif_dev', email='dev@example.com',
        password='Test123!', role='DEV',
    )


@pytest.fixture
def template():
    return NotificationTemplate.objects.create(
        notification_type='MENTION',
        title_template='You were mentioned',
        message_template='{{ user }} mentioned you',
        email_subject_template='You were mentioned in a comment',
        is_active=True,
    )


@pytest.fixture
def user_notification(dev_user):
    sender = User.objects.create_user(
        username='sender', email='sender@example.com', password='Test123!',
    )
    return Notification.objects.create(
        recipient=dev_user,
        sender=sender,
        notification_type=Notification.NotificationType.MENTION,
        title='Test',
        message='Test message',
    )


# ─── H-1: NotificationTemplateViewSet is admin-only ───

class TestTemplateAdminOnly:
    """H-1: only ADMIN role can list/retrieve notification templates."""

    def test_admin_can_list_templates(self, api_client, admin_user, template):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get(reverse('notification-template-list'))
        assert response.status_code == status.HTTP_200_OK
        # The response is paginated or a plain list
        body = response.json()
        items = body.get('results', body) if isinstance(body, dict) else body
        assert any(t['id'] == template.id for t in items)

    def test_non_admin_cannot_list_templates(self, api_client, dev_user, template):
        api_client.force_authenticate(user=dev_user)
        response = api_client.get(reverse('notification-template-list'))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_pm_cannot_list_templates(self, api_client, pm_user, template):
        # PM role is NOT admin per IsAdmin.has_permission
        api_client.force_authenticate(user=pm_user)
        response = api_client.get(reverse('notification-template-list'))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_retrieve_template(self, api_client, admin_user, template):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get(
            reverse('notification-template-detail', kwargs={'pk': template.id})
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['id'] == template.id

    def test_non_admin_cannot_retrieve_template(self, api_client, dev_user, template):
        api_client.force_authenticate(user=dev_user)
        response = api_client.get(
            reverse('notification-template-detail', kwargs={'pk': template.id})
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── M-1: NotificationPreference uniqueness ───

class TestPreferenceUniqueness:
    """M-1: UniqueConstraint on (user, notification_type) is enforced."""

    def test_preference_unique_constraint_enforced(self, dev_user):
        NotificationPreference.objects.create(
            user=dev_user,
            notification_type=NotificationPreference._meta.get_field(
                'notification_type'
            ).choices[0][0],  # first choice
            email_enabled=True,
        )
        with pytest.raises(IntegrityError):
            NotificationPreference.objects.create(
                user=dev_user,
                notification_type=NotificationPreference._meta.get_field(
                    'notification_type'
                ).choices[0][0],
                email_enabled=False,
            )

    def test_user_can_have_different_types(self, dev_user):
        for n_type, _ in NotificationPreference._meta.get_field(
            'notification_type'
        ).choices[:3]:
            NotificationPreference.objects.create(
                user=dev_user, notification_type=n_type,
            )
        assert NotificationPreference.objects.filter(user=dev_user).count() == 3

    def test_different_users_same_type_allowed(self):
        a = User.objects.create_user(
            username='user_a', email='a@example.com', password='Test123!',
        )
        b = User.objects.create_user(
            username='user_b', email='b@example.com', password='Test123!',
        )
        n_type, _ = NotificationPreference._meta.get_field(
            'notification_type'
        ).choices[0]
        NotificationPreference.objects.create(user=a, notification_type=n_type)
        NotificationPreference.objects.create(user=b, notification_type=n_type)
        assert NotificationPreference.objects.filter(notification_type=n_type).count() == 2


# ─── M-2: IsNotificationRecipient defense-in-depth ───

class TestIsNotificationRecipientPermission:
    """M-2: only the notification recipient can access it."""

    def test_recipient_can_access_own_notification(
        self, api_client, user_notification, dev_user,
    ):
        api_client.force_authenticate(user=dev_user)
        response = api_client.get(
            reverse('notification-detail', kwargs={'pk': user_notification.id})
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['id'] == user_notification.id

    def test_non_recipient_gets_404_on_other_notification(
        self, api_client, user_notification,
    ):
        other = User.objects.create_user(
            username='other', email='other@example.com', password='Test123!',
            role='DEV',
        )
        api_client.force_authenticate(user=other)
        response = api_client.get(
            reverse('notification-detail', kwargs={'pk': user_notification.id})
        )
        # 404 (queryset filter) or 403 (object permission) both acceptable
        assert response.status_code in (403, 404)

    def test_is_notification_recipient_permission_unit(self, dev_user, template):
        """Direct unit test of the permission class."""
        from notifications.permissions import IsNotificationRecipient
        factory = RequestFactory()
        request = factory.get('/')
        request.user = dev_user

        # Notification owned by dev_user
        own = Notification.objects.create(
            recipient=dev_user, sender=None,
            notification_type='MENTION',
            title='Mine', message='mine',
        )
        # Notification owned by someone else
        other = User.objects.create_user(
            username='someone', email='s@example.com', password='Test123!',
        )
        not_mine = Notification.objects.create(
            recipient=other, sender=None,
            notification_type='MENTION',
            title='Theirs', message='theirs',
        )

        perm = IsNotificationRecipient()
        assert perm.has_object_permission(request, None, own) is True
        assert perm.has_object_permission(request, None, not_mine) is False

    def test_mark_read_respects_recipient(
        self, api_client, user_notification,
    ):
        other = User.objects.create_user(
            username='attacker', email='attacker@example.com',
            password='Test123!', role='DEV',
        )
        api_client.force_authenticate(user=other)
        response = api_client.post(
            reverse('notification-mark-read', kwargs={'pk': user_notification.id})
        )
        # Non-recipient must not be able to mark as read
        assert response.status_code in (403, 404)
        # The notification stays unread
        user_notification.refresh_from_db()
        assert user_notification.is_read is False
