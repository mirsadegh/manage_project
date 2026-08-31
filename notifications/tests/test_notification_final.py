# notifications/tests/test_notification_final.py
"""
Regression tests for PR-5 Commit 3: low-priority hardening.

Covers:
- L-1: Notification.mark_as_read is atomic and idempotent.
- L-2: NotificationViewSet has throttle_scope='notification_read'
       and the rate is configured in production settings.
- L-3: send_notification_async Celery task has SECURITY docstring.
"""
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from notifications.models import Notification

User = get_user_model()

pytestmark = pytest.mark.django_db


# ─── Fixtures ───

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def recipient():
    return User.objects.create_user(
        username='recipient', email='r@example.com',
        password='Test123!', role='DEV',
    )


@pytest.fixture
def unread_notification(recipient):
    return Notification.objects.create(
        recipient=recipient,
        sender=User.objects.create_user(
            username='sender', email='s@example.com',
            password='Test123!', role='PM',
        ),
        notification_type=Notification.NotificationType.MENTION,
        title='Test', message='Test',
    )


# ─── L-1: atomic mark_as_read ───

class TestAtomicMarkAsRead:
    """L-1: mark_as_read is atomic and idempotent."""

    def test_mark_as_read_returns_true_when_newly_read(self, unread_notification):
        assert unread_notification.is_read is False
        result = unread_notification.mark_as_read()
        assert result is True
        unread_notification.refresh_from_db()
        assert unread_notification.is_read is True

    def test_mark_as_read_returns_false_when_already_read(self, unread_notification):
        unread_notification.mark_as_read()
        result = unread_notification.mark_as_read()
        assert result is False

    def test_mark_as_read_sets_read_at(self, unread_notification):
        assert unread_notification.read_at is None
        before = timezone.now()
        unread_notification.mark_as_read()
        unread_notification.refresh_from_db()
        assert unread_notification.read_at is not None
        assert unread_notification.read_at >= before

    def test_mark_as_read_concurrent_safety(self, unread_notification):
        """Two consecutive calls - only the first returns True.

        Real concurrency testing requires threading; this proves the
        idempotency contract that the atomic update provides.
        """
        first = unread_notification.mark_as_read()
        second = unread_notification.mark_as_read()
        assert first is True
        assert second is False
        unread_notification.refresh_from_db()
        assert unread_notification.is_read is True


# ─── L-2: rate limiting configuration ───

class TestRateLimitingConfiguration:
    """L-2: throttle_scope is set and the rate is configured."""

    def test_notification_read_throttle_scope_configured(self):
        from notifications.views import NotificationViewSet
        assert getattr(NotificationViewSet, 'throttle_scope', None) == 'notification_read'

    def test_notification_read_rate_in_production_settings(self):
        """Production settings.py must configure the rate.

        Read the file directly to verify the production rate is set,
        regardless of which settings module is active for the test
        runner. This ensures the production deployment config is in
        place even if the test override is in effect at test time.
        """
        from pathlib import Path
        prod_path = Path(__file__).resolve().parents[2] / 'config' / 'settings.py'
        source = prod_path.read_text()
        assert "'notification_read': '100/min'" in source
        assert 'DEFAULT_THROTTLE_RATES' in source

    def test_notification_read_rate_in_test_settings(self):
        """Test settings must override the rate to avoid test flakiness."""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        assert 'notification_read' in rates
        # Test settings should be generous (not 100/min) so tests don't
        # trip the throttle. The override is in config/settings_test.py.
        assert rates['notification_read'] != '100/min'


# ─── L-3: documentation presence ───

class TestSecurityDocumentation:
    """L-3: SECURITY warnings on dangerous code paths."""

    def test_send_notification_async_has_security_docstring(self):
        from notifications import tasks
        doc = tasks.send_notification_async.__doc__ or ''
        assert 'SECURITY' in doc
