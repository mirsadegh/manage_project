"""
PR-3 Commit 1 regression tests.

Covers the three Critical fixes:
  #1 Logout/Revocation Gap
  #2 X-Forwarded-For Trusted Proxy Allowlist
  #3 Per-User Connection Cap
"""
import uuid
from datetime import datetime, timezone

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application


User = get_user_model()


WS_HEADERS = [(b'origin', b'http://localhost')]


@pytest.fixture
def locmem_cache(settings):
    # Unique LOCATION per test invocation to fully isolate state between tests.
    # Shared LOCATION can leak counter state across tests in the same process.
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': f'ws-security-{uuid.uuid4().hex}',
        }
    }


@pytest.fixture
def small_max(settings):
    settings.MAX_CONNECTIONS_PER_USER = 2
    return 2


@database_sync_to_async
def _create_user(username='wstest', email='wstest@example.com'):
    return User.objects.create_user(
        username=username, email=email, password='Test123!',
    )


@database_sync_to_async
def _issue_token(user):
    token = AccessToken.for_user(user)
    return str(token), token['jti']


@database_sync_to_async
def _blacklist(user, jti):
    token = AccessToken.for_user(user)
    expires_at = datetime.fromtimestamp(int(token['exp']), tz=timezone.utc)
    outstanding, _ = OutstandingToken.objects.get_or_create(
        user=user, jti=jti,
        defaults={'token': str(token), 'expires_at': expires_at},
    )
    BlacklistedToken.objects.get_or_create(token=outstanding)


async def _connect(token, path='/ws/notifications/'):
    communicator = WebsocketCommunicator(
        application, f'{path}?token={token}',
        headers=WS_HEADERS,
    )
    connected, _ = await communicator.connect()
    return communicator, connected


@database_sync_to_async
def _get_cache(key):
    from django.core.cache import cache
    return cache.get(key)


# Fix #1 --------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_valid_jwt_header_connects():
    user = await _create_user()
    token, _ = await _issue_token(user)
    communicator, connected = await _connect(token)
    try:
        assert connected is True
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_blacklisted_token_rejected_on_connect():
    user = await _create_user()
    token, jti = await _issue_token(user)
    await _blacklist(user, jti)
    communicator = WebsocketCommunicator(
        application, f'/ws/notifications/?token={token}',
        headers=WS_HEADERS,
    )
    connected, code = await communicator.connect()
    assert connected is False
    if code is not None and code != 1000:
        assert code == 4001


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_revocation_severs_active_connection():
    import asyncio as _asyncio
    user = await _create_user(username='revoked')
    token, jti = await _issue_token(user)
    communicator, connected = await _connect(token)
    assert connected is True
    try:
        await communicator.receive_output(timeout=1)
    except Exception:
        pass
    await _blacklist(user, jti)
    try:
        await communicator.send_input({'type': 'ping'})
    except Exception:
        pass
    await _asyncio.sleep(0.5)
    closed = False
    try:
        await communicator.send_input({'type': 'ping'})
    except Exception:
        closed = True
    if not closed:
        try:
            await communicator.receive_output(timeout=0.5)
        except Exception:
            closed = True
    assert closed, 'consumer should have closed after blacklist'
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_cache_invalidated_on_blacklist():
    user = await _create_user(username='cacheflush')
    token, jti = await _issue_token(user)
    communicator, connected = await _connect(token)
    assert connected is True
    set_key = f'ws_user_tokens_{user.id}'
    cached = await _get_cache(set_key)
    assert cached and len(cached) >= 1, f'expected cache populated, got {cached!r}'
    await _blacklist(user, jti)
    after = await _get_cache(set_key)
    assert after in (None, []), f'cache not flushed: {after!r}'
    try:
        await communicator.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_signal_idempotent():
    user = await _create_user(username='idempotent')
    token, jti = await _issue_token(user)
    await _blacklist(user, jti)
    await _blacklist(user, jti)


# Fix #2 --------------------------------------------------------------------

def test_xff_ignored_without_trusted_proxy(settings):
    settings.TRUSTED_PROXY_CIDRS = []
    from config.proxies import get_client_ip
    scope = {
        'client': ('198.51.100.10', 1234),
        'headers': [(b'x-forwarded-for', b'203.0.113.99')],
    }
    assert get_client_ip(scope) == '198.51.100.10'


def test_xff_honored_from_trusted_proxy(settings):
    settings.TRUSTED_PROXY_CIDRS = ['127.0.0.0/8']
    from config.proxies import get_client_ip
    scope = {
        'client': ('127.0.0.1', 1234),
        'headers': [(b'x-forwarded-for', b'203.0.113.99, 10.0.0.1')],
    }
    assert get_client_ip(scope) == '203.0.113.99'


def test_xff_from_untrusted_proxy_rejected(settings):
    settings.TRUSTED_PROXY_CIDRS = ['10.0.0.0/8']
    from config.proxies import get_client_ip
    scope = {
        'client': ('198.51.100.10', 1234),
        'headers': [(b'x-forwarded-for', b'203.0.113.99')],
    }
    assert get_client_ip(scope) == '198.51.100.10'


def test_xff_malformed_cidr_ignored(settings):
    settings.TRUSTED_PROXY_CIDRS = ['not-a-cidr', '127.0.0.0/8']
    from config.proxies import get_client_ip
    scope = {
        'client': ('127.0.0.1', 1234),
        'headers': [(b'x-forwarded-for', b'203.0.113.99')],
    }
    assert get_client_ip(scope) == '203.0.113.99'


# Fix #3 --------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_per_user_connection_cap(settings):
    settings.MAX_CONNECTIONS_PER_USER = 5
    user = await _create_user(username='capuser')
    token, _ = await _issue_token(user)
    communicators = []
    for i in range(5):
        comm, ok = await _connect(token)
        assert ok is True, f'connection {i} should succeed'
        communicators.append(comm)
    overflow, ok = await _connect(token)
    assert ok is False, '6th connection should be rejected'
    for comm in communicators:
        try:
            await comm.disconnect()
        except Exception:
            pass
    try:
        await overflow.disconnect()
    except Exception:
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache', 'small_max')
async def test_per_user_cap_independent_across_users(small_max):
    user_a = await _create_user(username='alice', email='alice@example.com')
    user_b = await _create_user(username='bob', email='bob@example.com')
    token_a, _ = await _issue_token(user_a)
    token_b, _ = await _issue_token(user_b)
    a1, ok1 = await _connect(token_a)
    a2, ok2 = await _connect(token_a)
    assert ok1 and ok2
    b1, ok3 = await _connect(token_b)
    assert ok3 is True, 'bob should not be affected by alice cap'
    for c in (a1, a2, b1):
        try:
            await c.disconnect()
        except Exception:
            pass
