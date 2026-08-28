"""
PR-3 Commit 4 regression tests.

Covers:
  #16 Defensive recipient check in notification_message
  #17 user_focus key whitelist
  #18 Dead decorator removal
  #20 Settings audit

NOTE: As of this writing, the production code does NOT yet have the
recipient-check (Fix #16), user_focus whitelist (Fix #17), or dead-
decorator removal (Fix #18). These tests document the intended
behavior; the relevant assertions will fail until the production code
is updated.
"""
import json
import logging
import uuid

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application


User = get_user_model()


WS_HEADERS = [(b'origin', b'http://localhost')]


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': f'ws-low-{uuid.uuid4().hex}',
        }
    }


@database_sync_to_async
def _create_user(username='low_user', email='low@example.com'):
    return User.objects.create_user(
        username=username, email=email, password='Test123!',
    )


@database_sync_to_async
def _issue_token(user):
    return str(AccessToken.for_user(user))


@database_sync_to_async
def _create_project_with_member(slug='low-proj', owner_username='low_owner'):
    from projects.models import Project
    owner = User.objects.create_user(
        username=owner_username, email=f'{owner_username}@example.com',
        password='Test123!',
    )
    project = Project.objects.create(name='Low Project', slug=slug, owner=owner)
    return project, owner


@database_sync_to_async
def _add_member(project, user, role='MEMBER'):
    from projects.models import ProjectMember
    ProjectMember.objects.create(project=project, user=user, role=role)


@database_sync_to_async
def _create_notification(recipient, notification_type='INFO', title='Hi', message='msg'):
    from notifications.models import Notification
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
    )


@database_sync_to_async
def _dispatch_to_user(user_id, event):
    layer = get_channel_layer()
    if layer is None:
        return
    from asgiref.sync import async_to_sync
    async_to_sync(layer.group_send)(f'user_{user_id}_notifications', event)


@database_sync_to_async
def _dispatch_to_project(slug, event):
    layer = get_channel_layer()
    if layer is None:
        return
    from asgiref.sync import async_to_sync
    async_to_sync(layer.group_send)(f'project_{slug}', event)


async def _connect_notifications(token):
    communicator = WebsocketCommunicator(
        application, f'/ws/notifications/?token={token}',
        headers=WS_HEADERS,
    )
    connected, _ = await communicator.connect()
    return communicator, connected


async def _connect_project(token, slug):
    communicator = WebsocketCommunicator(
        application, f'/ws/projects/{slug}/?token={token}',
        headers=WS_HEADERS,
    )
    connected, _ = await communicator.connect()
    return communicator, connected


async def _drain(communicator, timeout=0.3):
    try:
        return await communicator.receive_output(timeout=timeout)
    except Exception:
        return None


async def _drain_json(communicator, timeout=0.3):
    frame = await _drain(communicator, timeout=timeout)
    if frame is None or 'text' not in frame:
        return None
    return json.loads(frame['text'])


# Fix #16 — defensive recipient check ---------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_notification_forwarded_to_owner():
    """A notification dispatched to user A's group is received by A."""
    user = await _create_user(username='low_recv_user')
    token = await _issue_token(user)

    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)

    notif = await _create_notification(
        user, notification_type='TASK', title='Hello', message='world',
    )
    await _dispatch_to_user(user.id, {
        'type': 'notification_message',
        'notification': {
            'id': notif.id,
            'title': notif.title,
            'message': notif.message,
            'recipient_id': user.id,
            'notification_type': notif.notification_type,
        },
    })

    msg = await _drain_json(communicator, timeout=1.0)
    assert msg is not None
    assert msg.get('type') == 'notification'
    assert msg['notification']['id'] == notif.id
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_notification_not_forwarded_to_wrong_user():
    """
    Defensive check: if a notification is dispatched to user A's group
    but the recipient_id doesn't match A, the consumer must drop it.
    """
    user = await _create_user(username='low_wrong_user')
    other = await _create_user(username='low_other_user', email='low_other@example.com')
    token = await _issue_token(user)

    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)

    # Dispatch a notification that targets `other` (not `user`) to user A's group.
    notif = await _create_notification(
        other, notification_type='TASK', title='Leak', message='should not see',
    )
    await _dispatch_to_user(user.id, {
        'type': 'notification_message',
        'notification': {
            'id': notif.id,
            'title': notif.title,
            'message': notif.message,
            'recipient_id': other.id,  # <-- mismatch
            'notification_type': notif.notification_type,
        },
    })

    msg = await _drain_json(communicator, timeout=0.5)
    assert msg is None or msg.get('type') != 'notification', (
        f'notification with mismatched recipient_id leaked through: {msg!r}'
    )
    # The server-initiated close path leaves the consumer task alive;
    # we don't disconnect here because that races with the test
    # event-loop teardown.
    communicator.future.cancel()


# Fix #17 — user_focus key whitelist --------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_user_focus_whitelisted_keys_forwarded():
    """Whitelisted keys (task_id, is_focused, timestamp) pass through."""
    project, owner = await _create_project_with_member(slug='focus-ok')
    member = await _create_user(username='focus_member', email='focus_member@example.com')
    await _add_member(project, member, role='MEMBER')
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'focus-ok')
    assert connected is True
    await _drain(communicator, timeout=0.5)

    # Dispatch a user_focus FROM the owner so the member sees it
    # (the consumer only forwards OTHER users' events).
    await _dispatch_to_project('focus-ok', {
        'type': 'user_focus',
        'user_id': owner.id,
        'username': owner.username,
        'task_id': 42,
        'is_focused': True,
        'timestamp': '2026-01-01T00:00:00Z',
    })
    msg = await _drain_json(communicator, timeout=1.0)
    assert msg is not None
    assert msg.get('type') == 'user_focus'
    allowed = {'type', 'task_id', 'is_focused', 'timestamp', 'user_id'}
    extras = set(msg.keys()) - allowed
    assert not extras, f'unexpected keys forwarded: {extras}'
    assert msg.get('task_id') == 42
    assert msg.get('is_focused') is True
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_user_focus_unknown_keys_dropped():
    """Extra keys in a user_focus event are dropped before forwarding."""
    project, owner = await _create_project_with_member(slug='focus-drop')
    member = await _create_user(username='focus_drop', email='focus_drop@example.com')
    await _add_member(project, member, role='MEMBER')
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'focus-drop')
    assert connected is True
    await _drain(communicator, timeout=0.5)

    await _dispatch_to_project('focus-drop', {
        'type': 'user_focus',
        'user_id': owner.id,
        'username': owner.username,
        'task_id': 7,
        'is_focused': True,
        'timestamp': '2026-01-01T00:00:00Z',
        'injected': 'pwned',
        'xss': '<script>alert(1)</script>',
        'admin_override': True,
    })
    msg = await _drain_json(communicator, timeout=1.0)
    assert msg is not None
    assert msg.get('type') == 'user_focus'
    for forbidden in ('injected', 'xss', 'admin_override'):
        assert forbidden not in msg, f'forbidden key forwarded: {forbidden}'
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_user_focus_missing_optional_keys_ok():
    """Missing optional keys (is_focused, timestamp) don't break forwarding."""
    project, owner = await _create_project_with_member(slug='focus-min')
    member = await _create_user(username='focus_min', email='focus_min@example.com')
    await _add_member(project, member, role='MEMBER')
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'focus-min')
    assert connected is True
    await _drain(communicator, timeout=0.5)

    # Only user_id and task_id; no is_focused / timestamp.
    await _dispatch_to_project('focus-min', {
        'type': 'user_focus',
        'user_id': owner.id,
        'task_id': 1,
    })
    msg = await _drain_json(communicator, timeout=1.0)
    assert msg is not None
    assert msg.get('type') == 'user_focus'
    assert msg.get('task_id') == 1
    try:
        await communicator.disconnect()
    except Exception:
        pass


# Fix #18 — dead decorator removal ----------------------------------------

def test_no_dead_decorator_in_module():
    """`websocket_auth_required` was removed; the symbol must not be importable."""
    import config.websocket_auth as mod
    assert not hasattr(mod, 'websocket_auth_required'), (
        'websocket_auth_required is dead code and should have been removed in '
        'PR-3 Fix #18. Either remove it from config/websocket_auth.py or '
        'document why it is kept.'
    )


# Fix #20 — settings audit -------------------------------------------------

def test_trusted_proxy_setting_exists():
    assert hasattr(dj_settings, 'TRUSTED_PROXY_CIDRS')
    assert isinstance(dj_settings.TRUSTED_PROXY_CIDRS, list)


def test_max_connections_setting_exists():
    assert hasattr(dj_settings, 'MAX_CONNECTIONS_PER_USER')
    assert isinstance(dj_settings.MAX_CONNECTIONS_PER_USER, int)
    assert dj_settings.MAX_CONNECTIONS_PER_USER > 0


def test_max_message_setting_exists():
    assert hasattr(dj_settings, 'MAX_MESSAGE_SIZE')
    assert isinstance(dj_settings.MAX_MESSAGE_SIZE, int)
    assert dj_settings.MAX_MESSAGE_SIZE > 0
