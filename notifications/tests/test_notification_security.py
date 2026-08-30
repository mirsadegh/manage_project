# notifications/tests/test_notification_security.py
"""
Regression tests for PR-5 Commit 1: close the mass notification spoofing
vulnerability (N-1: viewset locked down to read-only; N-2: serializer
fields are all read-only).

These tests document the security fix AND verify that legitimate
read functionality still works.
"""
import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from notifications.models import Notification
from accounts.tests.factories import UserFactory

User = get_user_model()

pytestmark = pytest.mark.django_db


# ─── Fixtures ───

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def recipient():
    return UserFactory()


@pytest.fixture
def sender():
    return UserFactory()


@pytest.fixture
def notification(recipient, sender):
    return Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=Notification.NotificationType.MENTION,
        title='Test',
        message='Test message',
    )


# ─── N-1: write methods are disabled (405) ───

class TestNotificationWriteMethodsDisabled:
    """N-1: POST/PUT/PATCH/DELETE on the notifications endpoint return 405."""

    def test_post_notification_returns_405(self, api_client, recipient):
        api_client.force_authenticate(user=recipient)
        response = api_client.post(reverse('notification-list'), {})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_put_notification_returns_405(self, api_client, notification):
        api_client.force_authenticate(user=notification.recipient)
        response = api_client.put(
            reverse('notification-detail', kwargs={'pk': notification.id}),
            data={'title': 'hacked'},
            format='json',
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_patch_notification_returns_405(self, api_client, notification):
        api_client.force_authenticate(user=notification.recipient)
        response = api_client.patch(
            reverse('notification-detail', kwargs={'pk': notification.id}),
            data={'title': 'hacked'},
            format='json',
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_delete_notification_returns_405(self, api_client, notification):
        api_client.force_authenticate(user=notification.recipient)
        response = api_client.delete(
            reverse('notification-detail', kwargs={'pk': notification.id})
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ─── N-2: serializer defense-in-depth ───

class TestSerializerFieldsAreReadOnly:
    """N-2: every NotificationSerializer field is marked read-only."""

    def test_serializer_fields_are_all_read_only(self):
        from notifications.serializers import NotificationSerializer
        meta = NotificationSerializer.Meta
        # Every field in the public API must be read-only
        for field_name in meta.fields:
            assert field_name in meta.read_only_fields, (
                f'{field_name} is not in read_only_fields'
            )

    def test_orm_create_does_not_use_serializer(self, recipient, sender):
        """ORM-level creation still works (server-side path)."""
        notification = Notification.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type=Notification.NotificationType.COMMENT,
            title='Server-created',
            message='Created via signal',
        )
        assert notification.pk is not None
        assert notification.recipient == recipient


# ─── Legitimate read functionality still works ───

class TestLegitimateReadStillWorks:
    """The lockdown must not break legitimate read paths."""

    def test_list_own_notifications_works(self, api_client, recipient):
        Notification.objects.create(
            recipient=recipient, sender=UserFactory(),
            notification_type=Notification.NotificationType.MENTION,
            title='A', message='A',
        )
        api_client.force_authenticate(user=recipient)
        response = api_client.get(reverse('notification-list'))
        assert response.status_code == status.HTTP_200_OK
        results = response.json().get('results', response.json())
        assert any(n['title'] == 'A' for n in results)

    def test_cannot_see_others_notifications(self, api_client, recipient):
        other = UserFactory()
        Notification.objects.create(
            recipient=other, sender=UserFactory(),
            notification_type=Notification.NotificationType.MENTION,
            title='For-Other', message='For other user',
        )
        api_client.force_authenticate(user=recipient)
        response = api_client.get(reverse('notification-list'))
        results = response.json().get('results', response.json())
        assert not any(n['title'] == 'For-Other' for n in results)

    def test_mark_read_still_works(self, api_client, notification):
        api_client.force_authenticate(user=notification.recipient)
        response = api_client.post(
            reverse('notification-mark-read', kwargs={'pk': notification.id})
        )
        assert response.status_code == status.HTTP_200_OK
        notification.refresh_from_db()
        assert notification.is_read is True

    def test_mark_all_read_still_works(self, api_client, recipient):
        for i in range(3):
            Notification.objects.create(
                recipient=recipient, sender=UserFactory(),
                notification_type=Notification.NotificationType.COMMENT,
                title=f'N{i}', message='x',
            )
        api_client.force_authenticate(user=recipient)
        response = api_client.post(reverse('notification-mark-all-read'))
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body.get('updated', 0) >= 3
        assert Notification.objects.filter(
            recipient=recipient, is_read=False,
        ).count() == 0

    def test_unread_count_still_works(self, api_client, recipient):
        Notification.objects.create(
            recipient=recipient, sender=UserFactory(),
            notification_type=Notification.NotificationType.COMMENT,
            title='U', message='x',
        )
        api_client.force_authenticate(user=recipient)
        response = api_client.get(reverse('notification-unread-count'))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['unread_count'] == 1

    def test_statistics_still_works(self, api_client, recipient):
        Notification.objects.create(
            recipient=recipient, sender=UserFactory(),
            notification_type=Notification.NotificationType.MENTION,
            title='S', message='x',
        )
        api_client.force_authenticate(user=recipient)
        response = api_client.get(reverse('notification-statistics'))
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body['total_notifications'] == 1
        assert body['unread_count'] == 1
        assert 'MENTION' in body['by_type']
