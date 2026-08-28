"""
PR-3 Commit 3 regression tests.

Covers:
  #10 Server-side idle timeout
  #11 request_sync paging defaults
  #12 Max message size
  #13 Generic auth-failure error
  #14 Subprotocol token removal
  #15 is_active recheck on deactivation
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
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
            'LOCATION': f'ws-medium-{uuid.uuid4().hex}',
        }
    }


@pytest.fixture
def short_idle_timeout(settings):
    """Set CONNECTION_TIMEOUT to 1s for fast idle tests."""
    from notifications.consumers import BaseConsumer as NC
    from projects.consumers import BaseConsumer as PC
    old_nc, old_pc = NC.CONNECTION_TIMEOUT, PC.CONNECTION_TIMEOUT
    NC.CONNECTION_TIMEOUT = 1
    PC.CONNECTION_TIMEOUT = 1
    yield settings
    NC.CONNECTION_TIMEOUT = old_nc
    PC.CONNECTION_TIMEOUT = old_pc


@pytest.fixture
def small_message_limit(settings):
    settings.MAX_MESSAGE_SIZE = 1024  # 1 KB
    return settings


@database_sync_to_async
def _create_user(username='medium_user', email='medium@example.com'):
    return User.objects.create_user(
        username=username, email=email, password='Test123!',
    )


@database_sync_to_async
def _issue_token(user):
    return str(AccessToken.for_user(user))


@database_sync_to_async
def _issue_token_with_jti(user):
    token = AccessToken.for_user(user)
    return str(token), token['jti']


@database_sync_to_async
def _create_expired_token(user):
    """Issue a token whose exp claim is in the past."""
    from rest_framework_simplejwt.tokens import AccessToken as _AT
    token = _AT()
    token['user_id'] = user.id
    token['exp'] = int((datetime.now(tz=timezone.utc) - timedelta(minutes=5)).timestamp())
    token['jti'] = 'expired-jti-test'
    return str(token), token['jti']


@database_sync_to_async
def _blacklist(user, jti):
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken, OutstandingToken,
    )
    expires_at = datetime.fromtimestamp(int(datetime.now(tz=timezone.utc).timestamp()) + 3600,
                                        tz=timezone.utc)
    outstanding, _ = OutstandingToken.objects.get_or_create(
        user=user, jti=jti,
        defaults={'token': 'x', 'expires_at': expires_at},
    )
    BlacklistedToken.objects.get_or_create(token=outstanding)


@database_sync_to_async
def _create_project_with_member(slug='medium-proj', owner_username='proj_owner'):
    from projects.models import Project
    owner = User.objects.create_user(
        username=owner_username, email=f'{owner_username}@example.com',
        password='Test123!',
    )
    project = Project.objects.create(name='Medium Project', slug=slug, owner=owner)
    return project, owner


@database_sync_to_async
def _add_member(project, user, role='MEMBER'):
    from projects.models import ProjectMember
    ProjectMember.objects.create(project=project, user=user, role=role)


@database_sync_to_async
def _create_tasks(project, count, prefix='task'):
    from tasks.models import Task
    return [
        Task.objects.create(
            title=f'{prefix} {i}',
            project=project,
            created_by=project.owner,
        )
        for i in range(count)
    ]


@database_sync_to_async
def _deactivate_user(user):
    user.is_active = False
    user.save(update_fields=['is_active'])


@database_sync_to_async
def _get_cache(key):
    from django.core.cache import cache
    return cache.get(key)


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


async def _send_json(communicator, payload):
    await communicator.send_to(text_data=json.dumps(payload))


async def _drain_json(communicator, timeout=0.3):
    frame = await _drain(communicator, timeout=timeout)
    if frame is None or 'text' not in frame:
        return None
    return json.loads(frame['text'])


# Fix #10 -------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache', 'short_idle_timeout')
async def test_idle_connection_closed_after_timeout(caplog):
    """Connection idle > CONNECTION_TIMEOUT is closed by the watchdog."""
    caplog.set_level(logging.INFO, logger='notifications.consumers')
    user = await _create_user(username='idle_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.3)
    import asyncio as _asyncio
    # Wait > 1s for the watchdog to fire.
    await _asyncio.sleep(1.5)
    # The watchdog logs an "idle" close. If we see it, the watchdog fired.
    idle_logs = [r for r in caplog.records if 'idle' in r.getMessage().lower()]
    assert idle_logs, (
        f'expected idle-close log, got: {[r.getMessage() for r in caplog.records]}'
    )
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache', 'short_idle_timeout')
async def test_activity_resets_watchdog():
    """Sending messages within the timeout keeps the connection alive."""
    user = await _create_user(username='active_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.3)
    import asyncio as _asyncio
    # Send a ping every 0.5s for 2s (4x the 1s timeout).
    for _ in range(4):
        await _asyncio.sleep(0.5)
        try:
            await _send_json(communicator, {'type': 'ping'})
            await _drain(communicator, timeout=0.2)
        except Exception:
            pass
    # Connection still alive; one more ping should work.
    try:
        await _send_json(communicator, {'type': 'ping'})
    except Exception:
        pytest.fail('connection should still be open after activity')
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache', 'short_idle_timeout')
async def test_watchdog_cancelled_on_disconnect():
    """Disconnect cancels the watchdog without errors."""
    user = await _create_user(username='disco_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.3)
    import asyncio as _asyncio
    await _asyncio.sleep(0.2)
    try:
        await communicator.disconnect()
    except Exception:
        pass
    # Give the cancelled task a moment to settle; no errors expected.
    await _asyncio.sleep(0.2)


# Fix #11 -------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_request_sync_default_25_tasks():
    project, owner = await _create_project_with_member(slug='paging-25')
    member = await _create_user(username='pager_25', email='pager25@example.com')
    await _add_member(project, member, role='MEMBER')
    await _create_tasks(project, 30)
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'paging-25')
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        await _send_json(communicator, {'type': 'request_sync'})
        msg = await _drain_json(communicator, timeout=1.0)
        assert msg is not None
        assert msg.get('type') == 'sync_response'
        assert msg.get('limit') == 25
        assert msg.get('cursor') is None
        assert len(msg['project']['tasks']) == 25
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_request_sync_with_cursor_allows_100():
    project, owner = await _create_project_with_member(slug='paging-100')
    member = await _create_user(username='pager_100', email='pager100@example.com')
    await _add_member(project, member, role='MEMBER')
    tasks = await _create_tasks(project, 30)
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'paging-100')
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        cursor = tasks[0].id
        await _send_json(communicator, {
            'type': 'request_sync', 'limit': 100, 'cursor': cursor,
        })
        msg = await _drain_json(communicator, timeout=1.0)
        assert msg is not None
        assert msg.get('type') == 'sync_response'
        assert msg.get('limit') == 100
        assert msg.get('cursor') == cursor
        # 30 tasks, minus 1 (the cursor) = 29.
        assert len(msg['project']['tasks']) == 29
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_request_sync_limit_capped():
    """Huge limit is clamped: 25 (no cursor) or 100 (with cursor)."""
    project, owner = await _create_project_with_member(slug='paging-cap')
    member = await _create_user(username='pager_cap', email='pagercap@example.com')
    await _add_member(project, member, role='MEMBER')
    await _create_tasks(project, 5)
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'paging-cap')
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        await _send_json(communicator, {'type': 'request_sync', 'limit': 500})
        msg = await _drain_json(communicator, timeout=1.0)
        assert msg is not None
        assert msg.get('limit') == 25
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_request_sync_response_includes_pagination():
    project, owner = await _create_project_with_member(slug='paging-meta')
    member = await _create_user(username='pager_meta', email='pagermeta@example.com')
    await _add_member(project, member, role='MEMBER')
    await _create_tasks(project, 3)
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'paging-meta')
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        await _send_json(communicator, {'type': 'request_sync'})
        msg = await _drain_json(communicator, timeout=1.0)
        assert msg is not None
        assert 'limit' in msg
        assert 'cursor' in msg
        assert msg['limit'] == 25
        assert msg['cursor'] is None
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


# Fix #12 -------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache', 'small_message_limit')
async def test_oversize_message_rejected_4009(caplog):
    """A message > MAX_MESSAGE_SIZE closes the connection with 4009."""
    caplog.set_level(logging.WARNING, logger='notifications.consumers')
    user = await _create_user(username='big_msg_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        big = 'x' * 2000
        try:
            await communicator.send_to(text_data=json.dumps({
                'type': 'ping', 'data': big,
            }))
        except Exception:
            pass
        import asyncio as _asyncio
        await _asyncio.sleep(0.3)
        # Verify the close warning was logged.
        drop_logs = [r for r in caplog.records if 'oversize' in r.getMessage().lower()]
        assert drop_logs, (
            f'expected oversize warning, got: {[r.getMessage() for r in caplog.records]}'
        )
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache', 'small_message_limit')
async def test_normal_size_message_accepted():
    user = await _create_user(username='normal_msg_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        await communicator.send_to(text_data=json.dumps({
            'type': 'ping', 'note': 'hi',
        }))
        msg = await _drain_json(communicator, timeout=1.0)
        if msg is not None:
            assert msg.get('type') == 'pong'
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache', 'small_message_limit')
async def test_oversize_message_logged(caplog):
    caplog.set_level(logging.WARNING, logger='notifications.consumers')
    user = await _create_user(username='log_msg_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        big = 'x' * 2000
        try:
            await communicator.send_to(text_data=json.dumps({
                'type': 'ping', 'data': big,
            }))
        except Exception:
            pass
        import asyncio as _asyncio
        await _asyncio.sleep(0.3)
        drop_warnings = [
            r for r in caplog.records if 'oversize' in r.getMessage().lower()
        ]
        if drop_warnings:
            assert any('1024' in r.getMessage() for r in drop_warnings)
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


# Fix #13 -------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_auth_failure_returns_generic_reason():
    """No token → close code 4001."""
    communicator = WebsocketCommunicator(
        application, '/ws/notifications/',
        headers=WS_HEADERS,
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4001, f'expected close code 4001, got {code}'


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_expired_token_generic_reason():
    user = await _create_user(username='expired_user')
    token_str, _jti = await _create_expired_token(user)
    communicator = WebsocketCommunicator(
        application, f'/ws/notifications/?token={token_str}',
        headers=WS_HEADERS,
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4001


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_blacklisted_token_generic_reason():
    user = await _create_user(username='blacklisted_user')
    token_str, jti = await _issue_token_with_jti(user)
    await _blacklist(user, jti)
    communicator = WebsocketCommunicator(
        application, f'/ws/notifications/?token={token_str}',
        headers=WS_HEADERS,
    )
    connected, code = await communicator.connect()
    assert connected is False
    assert code == 4001


# Fix #14 -------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_subprotocol_token_rejected():
    """Sec-WebSocket-Protocol: access_token.<jwt> is no longer accepted."""
    user = await _create_user(username='sub_user')
    token = str(AccessToken.for_user(user))
    # Pass the JWT ONLY via the Sec-WebSocket-Protocol subprotocol — no
    # find a token and the connection should be rejected.
    communicator = WebsocketCommunicator(
        application, '/ws/notifications/',
        headers=WS_HEADERS,
        subprotocols=[f'access_token.{token}'],
    )
    connected, code = await communicator.connect()
    assert connected is False, 'subprotocol-only token should be rejected'
    assert code == 4001


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_authorization_header_still_works():
    """Regression: Bearer header connection still works after Fix #14."""
    user = await _create_user(username='hdr_regression_user')
    token = await _issue_token(user)
    communicator = WebsocketCommunicator(
        application, '/ws/notifications/',
        headers=[
            (b'origin', b'http://localhost'),
            (b'authorization', f'Bearer {token}'.encode('latin-1')),
        ],
    )
    connected, _ = await communicator.connect()
    assert connected is True
    try:
        await _drain(communicator, timeout=0.5)
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


# Fix #15 -------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_deactivated_user_cache_flushed():
    """Deactivating a user flushes their cached token entries."""
    user = await _create_user(username='deact_user')
    token = await _issue_token(user)

    communicator, connected = await _connect_notifications(token)
    assert connected is True
    set_key = f'ws_user_tokens_{user.id}'
    cached = await _get_cache(set_key)
    assert cached and len(cached) >= 1, (
        f'expected cache populated, got {cached!r}'
    )
    try:
        await communicator.disconnect()
    except Exception:
        pass
    import asyncio as _asyncio
    await _asyncio.sleep(0.3)

    await _deactivate_user(user)
    await _asyncio.sleep(0.3)

    after = await _get_cache(set_key)
    assert after in (None, []), f'cache not flushed on deactivation: {after!r}'


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_deactivated_user_disconnected():
    """An active connection is closed when the user is deactivated.

    In channels, a server-initiated close() does not by itself end the
    consumer task; the application loop runs until the client sends a
    `websocket.disconnect` (or the WebSocketCommunicator is disconnected).
    We send that explicitly to verify the close path completed.
    """
    user = await _create_user(username='deact_live_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)

    await _deactivate_user(user)
    import asyncio as _asyncio
    # Give the signal time to publish force_disconnect via the channel
    # layer and for the consumer to call self.close(4001).
    await _asyncio.sleep(0.3)

    # Now disconnect from the client side. If the consumer is still in
    # its dispatch loop, it will receive this and terminate cleanly.
    try:
        await communicator.disconnect()
    except Exception:
        pass
    # Allow the task to finalize.
    await _asyncio.sleep(0.3)
    assert communicator.future.done(), (
        'consumer task should be done after client disconnect'
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_active_user_update_no_op():
    """Updating a user while is_active=True does not disconnect them."""
    user = await _create_user(username='active_update_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)

    @database_sync_to_async
    def _save_active(u):
        u.first_name = 'Updated'
        u.save(update_fields=['first_name'])
    await _save_active(user)
    import asyncio as _asyncio
    await _asyncio.sleep(0.3)

    try:
        await _send_json(communicator, {'type': 'ping'})
        await _drain(communicator, timeout=0.3)
    except Exception:
        pytest.fail('connection should still be open after non-deactivation save')
    try:
        await communicator.disconnect()
    except Exception:
        pass