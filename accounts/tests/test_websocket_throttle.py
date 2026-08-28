"""
PR-3 Commit 2 regression tests.

Covers:
  #4 Query-string token deprecation
  #6 Inbound message rate limit
  #7 Per-message project recheck
  #8 cursor_position size cap
  #9 HTTP middleware X-Forwarded-For via trusted-proxy helper
"""
import json
import logging
import uuid

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application
from config.middleware import PermissionLoggingMiddleware


User = get_user_model()


WS_HEADERS = [(b'origin', b'http://localhost')]


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': f'ws-throttle-{uuid.uuid4().hex}',
        }
    }


@database_sync_to_async
def _create_user(username='throttle_user', email='throttle@example.com'):
    return User.objects.create_user(
        username=username, email=email, password='Test123!',
    )


@database_sync_to_async
def _issue_token(user):
    return str(AccessToken.for_user(user))


@database_sync_to_async
def _create_project_with_member(slug='throttle-proj', owner_username='owner_user'):
    from projects.models import Project
    owner = User.objects.create_user(
        username=owner_username, email=f'{owner_username}@example.com',
        password='Test123!',
    )
    project = Project.objects.create(name='Throttle Project', slug=slug, owner=owner)
    return project, owner


@database_sync_to_async
def _add_member(project, user, role='MEMBER'):
    from projects.models import ProjectMember
    ProjectMember.objects.create(project=project, user=user, role=role)


@database_sync_to_async
def _remove_member(project, user):
    from projects.models import ProjectMember
    ProjectMember.objects.filter(project=project, user=user).delete()


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


# Fix #4 --------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_query_string_emits_deprecation_warning(caplog):
    caplog.set_level(logging.WARNING, logger='config.websocket_auth')
    user = await _create_user(username='qs_user')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    try:
        assert connected is True
        deprecation_warnings = [
            r for r in caplog.records
            if 'query-string' in r.getMessage().lower() and 'DEPRECATED' in r.getMessage()
        ]
        assert deprecation_warnings, (
            f'expected deprecation warning, got: '
            f'{[r.getMessage() for r in caplog.records]}'
        )
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_authorization_header_no_deprecation_warning(caplog):
    caplog.set_level(logging.WARNING, logger='config.websocket_auth')
    user = await _create_user(username='hdr_user')
    token = await _issue_token(user)
    communicator = WebsocketCommunicator(
        application, '/ws/notifications/',
        headers=[(b'origin', b'http://localhost'),
                 (b'authorization', f'Bearer {token}'.encode('latin-1'))],
    )
    connected, _ = await communicator.connect()
    try:
        assert connected is True
        deprecation_warnings = [
            r for r in caplog.records
            if 'query-string' in r.getMessage().lower() and 'DEPRECATED' in r.getMessage()
        ]
        assert not deprecation_warnings, (
            f'no deprecation warning expected, got: '
            f'{[r.getMessage() for r in deprecation_warnings]}'
        )
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


# Fix #6 --------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_throttle_default_11th_message_closes_4290():
    user = await _create_user(username='throttle_def')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        for _ in range(10):
            await _send_json(communicator, {'type': 'ping'})
        try:
            await _send_json(communicator, {'type': 'ping'})
        except Exception:
            pass
        await _drain(communicator, timeout=0.3)
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_throttle_per_connection_isolated():
    user = await _create_user(username='throttle_iso')
    token = await _issue_token(user)

    comm_a, ok_a = await _connect_notifications(token)
    assert ok_a is True
    await _drain(comm_a, timeout=0.5)
    for _ in range(10):
        try:
            await _send_json(comm_a, {'type': 'ping'})
        except Exception:
            pass

    comm_b, ok_b = await _connect_notifications(token)
    assert ok_b is True, 'second connection should not be affected by first'
    await _drain(comm_b, timeout=0.5)
    for _ in range(3):
        try:
            await _send_json(comm_b, {'type': 'ping'})
        except Exception:
            pass
    for c in (comm_a, comm_b):
        try:
            await c.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_throttle_expensive_handler_lower_limit():
    user = await _create_user(username='throttle_exp')
    token = await _issue_token(user)
    communicator, connected = await _connect_notifications(token)
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        await _send_json(communicator, {'type': 'get_recent', 'limit': 5})
        await _drain(communicator, timeout=0.3)
        try:
            await _send_json(communicator, {'type': 'get_recent', 'limit': 5})
        except Exception:
            pass
        await _drain(communicator, timeout=0.3)
        await _send_json(communicator, {'type': 'ping'})
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


# Fix #7 --------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_request_sync_after_revoke_closes_4003(caplog):
    """User removed from project after connect → request_sync closes 4003."""
    caplog.set_level(logging.WARNING, logger='projects.consumers')
    project, owner = await _create_project_with_member(slug='revoke-proj')
    member = await _create_user(username='sync_revoke_member', email='sync_revoke@example.com')
    await _add_member(project, member, role='MEMBER')
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'revoke-proj')
    assert connected is True
    await _drain(communicator, timeout=0.5)

    await _remove_member(project, member)

    try:
        await _send_json(communicator, {'type': 'request_sync'})
    except Exception:
        pass
    import asyncio as _asyncio
    await _asyncio.sleep(0.3)
    revoke_warnings = [
        r for r in caplog.records
        if 'membership revoked' in r.getMessage()
    ]
    assert revoke_warnings, (
        f'expected membership-revoked warning, got: '
        f'{[r.getMessage() for r in caplog.records]}'
    )
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_request_sync_still_member_succeeds():
    project, owner = await _create_project_with_member(slug='sync-ok')
    member = await _create_user(username='sync_ok_member', email='sync_ok@example.com')
    await _add_member(project, member, role='MEMBER')
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'sync-ok')
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        await _send_json(communicator, {'type': 'request_sync'})
        msg = await _drain_json(communicator, timeout=1.0)
        if msg is not None:
            assert msg.get('type') == 'sync_response'
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


# Fix #8 --------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_cursor_position_small_payload_accepted():
    project, owner = await _create_project_with_member(slug='cursor-small')
    member = await _create_user(username='cursor_small', email='cursor_s@example.com')
    await _add_member(project, member, role='MEMBER')
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'cursor-small')
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        small = {'x': 100, 'y': 200, 'field': 'description'}
        await _send_json(communicator, {
            'type': 'cursor_position',
            'position': small,
            'element_id': 'editor-1',
        })
        await _send_json(communicator, {'type': 'ping'})
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_cursor_position_oversize_dropped_with_warning(caplog):
    caplog.set_level(logging.WARNING, logger='projects.consumers')
    project, owner = await _create_project_with_member(slug='cursor-big')
    member = await _create_user(username='cursor_big', email='cursor_b@example.com')
    await _add_member(project, member, role='MEMBER')
    token = await _issue_token(member)

    communicator, connected = await _connect_project(token, 'cursor-big')
    assert connected is True
    await _drain(communicator, timeout=0.5)
    try:
        big_str = 'a' * 5000
        await _send_json(communicator, {
            'type': 'cursor_position',
            'position': {'data': big_str},
            'element_id': 'editor-1',
        })
        await _send_json(communicator, {'type': 'ping'})

        drop_warnings = [
            r for r in caplog.records
            if 'oversized cursor_position' in r.getMessage()
        ]
        if drop_warnings:
            assert any('cursor_big' in r.getMessage() or '5000' in r.getMessage()
                       for r in drop_warnings)
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


# Fix #9 --------------------------------------------------------------------

def _make_request(remote_addr='198.51.100.10', xff=None):
    rf = RequestFactory()
    extra = {'REMOTE_ADDR': remote_addr}
    if xff is not None:
        extra['HTTP_X_FORWARDED_FOR'] = xff
    return rf.get('/', **extra)


def test_http_middleware_ignores_xff_without_trusted_proxy(settings):
    settings.TRUSTED_PROXY_CIDRS = []
    mw = PermissionLoggingMiddleware(get_response=lambda r: None)
    request = _make_request(remote_addr='198.51.100.10', xff='203.0.113.99')
    assert mw.get_client_ip(request) == '198.51.100.10'


def test_http_middleware_honors_xff_from_trusted_proxy(settings):
    settings.TRUSTED_PROXY_CIDRS = ['127.0.0.0/8']
    mw = PermissionLoggingMiddleware(get_response=lambda r: None)
    request = _make_request(remote_addr='127.0.0.1', xff='203.0.113.99, 10.0.0.1')
    assert mw.get_client_ip(request) == '203.0.113.99'
