"""
Access-token blacklist behaviour for HTTP and WebSocket auth.

SimpleJWT's OutstandingToken table only tracks refresh tokens, so
LogoutView additionally writes the presented access token's jti to the
cache for its remaining lifetime. This module covers both enforcement
surfaces (config.websocket_auth on the WS handshake,
config.auth_jwt.CookieJWTAuthentication on the HTTP path), the
logout-ordering guarantee that the access token is revoked before the
BlacklistedToken post_save signal fires, and the failure modes:
is_jti_blacklisted fails closed, blacklist_access_token reports its
failures, and a result-cache write failure never denies a validated
user.

settings_test.py uses DummyCache (a no-op backend), so every test uses
the locmem_cache override for real storage.
"""
import contextlib
import logging

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from unittest.mock import patch

from config.asgi import application
from config.token_blacklist import blacklist_access_token, is_jti_blacklisted

User = get_user_model()

WS_HEADERS = [(b'origin', b'http://localhost')]


@pytest.fixture
def locmem_cache(settings):
    """Isolate the cache. settings_test.py uses DummyCache (no-op)."""
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'access-blacklist-tests',
        }
    }


@contextlib.contextmanager
def _capture_ws_log():
    """Capture logs from config.websocket_auth across the thread boundary.

    get_user_from_token runs on the WebsocketCommunicator's worker
    thread, where pytest's caplog handler is not installed.
    """
    records = []
    ws_logger = logging.getLogger('config.websocket_auth')

    class _Sink(logging.Handler):
        def emit(self, record):
            records.append(record)

    sink = _Sink(level=logging.DEBUG)
    ws_logger.addHandler(sink)
    try:
        yield records
    finally:
        ws_logger.removeHandler(sink)


# --- shared helpers -------------------------------------------------------


def _make_token(user, jti=None):
    """Build a signed access token for ``user``."""
    token = AccessToken.for_user(user)
    if jti is not None:
        token['jti'] = jti
    return str(token)


def _decode(token_string):
    """Return (token, jti) for an access or refresh token string."""
    for cls in (AccessToken, RefreshToken):
        try:
            token = cls(token_string)
        except TokenError:
            continue
        return token, token['jti']
    raise AssertionError(f'undecodable token string: {token_string[:16]}…')


# --- Req 1: WS blacklisted jti is denied ----------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_ws_blacklisted_jti_denied():
    """A blacklisted access token cannot open a WebSocket connection."""
    user = await _create_user()
    token, jti = await _issue(user)
    await _blacklist_jti(jti)

    connected, code = await _connect(token)

    assert connected is False
    assert code == 4001


# --- Req 2: single decode -------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_ws_valid_token_decoded_once():
    """A valid token connects and AccessToken is constructed exactly once."""
    user = await _create_user()
    token, _ = await _issue(user)

    with patch('config.websocket_auth.AccessToken', wraps=AccessToken) as spy:
        connected, _ = await _connect(token)

    assert connected is True
    assert spy.call_count == 1


# --- Req 3: WS cache failure is fail-closed -------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_ws_cache_error_denies_connection():
    """A cache.get failure on the blacklist lookup denies the connection.

    is_jti_blacklisted fails closed, so an unreachable cache cannot turn
    into an allow. Uses the builtin ConnectionError so the test never
    depends on redis-py being installed.
    """
    user = await _create_user()
    token, _ = await _issue(user)

    # Patch the module global, not `cache.get`. `django.core.cache.cache`
    # is a proxy whose attribute lookups are forwarded to a per-thread
    # backend, and get_user_from_token runs in *another* thread via
    # database_sync_to_async, so an attribute patch made here never
    # reaches it. Replacing the whole name does.
    with patch('config.token_blacklist.cache') as fake_cache:
        fake_cache.get.side_effect = ConnectionError
        connected, code = await _connect(token)

    assert connected is False
    assert code == 4001
    assert fake_cache.get.called


# --- Req 4: HTTP cache failure -> 401 -------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_http_cache_error_returns_401_not_500(api_client):
    """A cache error on the HTTP path yields 401, never a 500.

    Uses the builtin ConnectionError so the test never depends on
    redis-py being installed.
    """
    user = User.objects.create_user(
        username='http_cache_user', email='http_cache_user@example.com',
        password='Test123!',
    )
    token = _make_token(user)

    # Module global, for the per-thread reason noted above.
    with patch('config.token_blacklist.cache') as fake_cache:
        fake_cache.get.side_effect = ConnectionError
        response = api_client.get(
            '/api/accounts/users/me/', HTTP_AUTHORIZATION=f'Bearer {token}'
        )

    assert response.status_code == 401, response.content[:200]
    assert fake_cache.get.called


# --- Req 5: HTTP blacklisted access token -> 401 --------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_http_blacklisted_access_token_returns_401(api_client):
    """A blacklisted access token is rejected on the HTTP path too."""
    user = User.objects.create_user(
        username='http_blacklist_user', email='http_blacklist_user@example.com',
        password='Test123!',
    )
    token = _make_token(user)
    assert blacklist_access_token(token) is True

    response = api_client.get(
        '/api/accounts/users/me/', HTTP_AUTHORIZATION=f'Bearer {token}'
    )
    assert response.status_code == 401


# --- Req 6: logout then WS reconnect --------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_logout_then_reconnect_rejected(api_client):
    """After logout, the same access token cannot reconnect over WS."""
    user = await _create_user()
    token, _ = await _issue(user)

    connected, _ = await _connect(token)
    assert connected is True

    await _logout(api_client, user, token)

    connected, code = await _connect(token)
    assert connected is False
    assert code == 4001


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_logout_then_reconnect_via_cookie_rejected(api_client):
    """The production path: the ws_access cookie, no ?token= query.

    Browsers attach the HttpOnly cookie on the WS upgrade automatically;
    the query-string form is deprecated. Reconnecting with the same
    cookie after logout must still be denied.
    """
    user = await _create_user()
    token, _ = await _issue(user)

    connected, _ = await _connect_with_cookie(token)
    assert connected is True

    await _logout(api_client, user, token)

    connected, code = await _connect_with_cookie(token)
    assert connected is False
    assert code == 4001


# --- Req 7: logout_all scope ----------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_logout_all_revokes_refresh_tokens_and_access(api_client):
    """logout_all revokes every refresh token and the device's access token."""
    user = await _create_user()
    token, _ = await _issue(user)
    refresh = await _issue_refresh(user)

    await _logout_all(api_client, refresh, token)

    # Every refresh token for the user is now blacklisted.
    outstanding = await _outstanding_for(user)
    assert outstanding, 'expected refresh tokens to be tracked'
    blacklisted = await _blacklisted_count(outstanding)
    assert blacklisted == len(outstanding)

    # The device's access token is revoked: WS and HTTP both deny it.
    connected, code = await _connect(token)
    assert connected is False
    assert code == 4001

    assert (await _http_me(token)) == 401


# --- Task C: blacklist_access_token reports failure loudly ----------------


@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_blacklist_access_token_returns_true_on_success():
    """A successful write returns True and the jti reads back blacklisted."""
    user = User.objects.create_user(
        username='ok_user', email='ok_user@example.com', password='Test123!'
    )
    token = _make_token(user)

    assert blacklist_access_token(token) is True
    _, jti = _decode(token)
    assert is_jti_blacklisted(jti) is True


@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_blacklist_access_token_returns_false_on_cache_error(caplog):
    """A cache.set failure returns False and is logged at ERROR."""
    user = User.objects.create_user(
        username='cache_err_user', email='cache_err_user@example.com',
        password='Test123!',
    )
    token = _make_token(user)
    _, jti = _decode(token)

    with patch('config.token_blacklist.cache') as fake_cache:
        fake_cache.set.side_effect = ConnectionError
        with caplog.at_level(logging.ERROR, logger='config.token_blacklist'):
            result = blacklist_access_token(token)

    assert result is False
    # The jti must not appear in the message; only its prefix is logged.
    assert not any(jti in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_blacklist_access_token_undecodable_returns_false():
    """A token that cannot be decoded is skipped, not raised."""
    assert blacklist_access_token('not.a.real.token') is False


@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_logout_still_succeeds_when_blacklist_write_fails(api_client, caplog):
    """A failed blacklist write keeps logout 200 and logs at ERROR.

    The refresh token is still revoked; only the access-token side channel
    is degraded, and that degradation must be visible to operators.
    """
    user = User.objects.create_user(
        username='degraded_logout_user', email='degraded_logout_user@example.com',
        password='Test123!',
    )
    refresh = str(RefreshToken.for_user(user))
    access = _make_token(user)

    # get must report "not blacklisted" (None) or the request is denied
    # before it ever reaches the logout view; only the write path fails.
    with patch('config.token_blacklist.cache') as fake_cache:
        fake_cache.get.return_value = None
        fake_cache.set.side_effect = Exception('cache down')
        with caplog.at_level(logging.ERROR, logger='accounts'):
            response = api_client.post(
                '/api/accounts/auth/logout/',
                {'refresh': refresh},
                HTTP_AUTHORIZATION=f'Bearer {access}',
            )

    assert response.status_code == 200, response.content[:200]
    # The refresh token is still revoked, cache failure or not.
    outstanding = OutstandingToken.objects.filter(user=user).first()
    assert outstanding is not None, 'refresh token was not tracked'
    assert BlacklistedToken.objects.filter(token=outstanding).exists(), (
        'refresh token was not blacklisted'
    )
    # The view itself reported the degradation — not just any logger.
    assert any(
        r.name == 'accounts' and r.levelno == logging.ERROR for r in caplog.records
    ), [r.name for r in caplog.records]


# --- WS post-decode failures ---------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_ws_user_lookup_error_returns_4001():
    """A generic exception during user lookup denies, never crashes."""
    user = await _create_user()
    token, _ = await _issue(user)

    with patch(
        'config.websocket_auth.CustomUser.objects.get',
        side_effect=Exception('DB error'),
    ):
        connected, code = await _connect(token)

    assert connected is False
    assert code == 4001


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.usefixtures('locmem_cache')
async def test_ws_result_cache_write_failure_still_authenticates():
    """A failure of the final cache.set must not deny a validated user.

    Cache-read failures fail closed; this write is not a trust decision,
    so it logs a warning and still returns the user.
    """
    user = await _create_user()
    token, _ = await _issue(user)

    # The result-cache write is the code path this test targets. Only
    # that key fails: the rate limiter's own cache.set must still
    # succeed or the test would exercise a different code path.
    def _set(key, *args, **kwargs):
        if key.startswith('ws_token_'):
            raise Exception('cache write down')

    # get must honour its `default` argument. A real backend never
    # returns None for a miss — it returns the caller's default (the
    # rate limiter passes 0) — and returning a bare MagicMock here
    # made the >= comparison raise a TypeError instead of testing the
    # code under scrutiny.
    def _get(key, default=None, *args, **kwargs):
        return default

    with patch('config.websocket_auth.cache') as write_cache:
        write_cache.get.side_effect = _get
        write_cache.set.side_effect = _set
        with _capture_ws_log() as records:
            connected, code = await _connect(token)

    assert connected is True
    assert code is None, f'expected an accepted socket, got close code {code}'
    assert any(
        r.levelno == logging.WARNING and 'result-cache write failed' in r.getMessage()
        for r in records
    ), [r.getMessage() for r in records]


# --- HTTP: token without jti ---------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_http_token_without_jti_returns_401(api_client):
    """A token carrying no jti is denied on the HTTP path.

    An unidentifiable token is not trusted: is_jti_blacklisted fails
    closed on an empty jti.
    """
    user = User.objects.create_user(
        username='no_jti_user', email='no_jti_user@example.com', password='Test123!'
    )
    token = _make_token(user, jti='')

    response = api_client.get(
        '/api/accounts/users/me/', HTTP_AUTHORIZATION=f'Bearer {token}'
    )
    assert response.status_code == 401


# --- access token must be blacklisted before the signal fires -------------


@pytest.mark.parametrize('logout_kind', ['single', 'all'])
@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_signal_fires_after_access_token_blacklisted(logout_kind, api_client):
    """The force_disconnect signal must not beat the access-token write.

    BlacklistedToken post_save triggers _close_user_sessions, which
    force-disconnects live sockets. A client reconnecting in that
    instant must find the jti already revoked, so the access token has
    to be written first.
    """
    user = User.objects.create_user(
        username=f'ordering_{logout_kind}',
        email=f'ordering_{logout_kind}@example.com',
        password='Test123!',
    )
    access = _make_token(user)
    _, access_jti = _decode(access)
    refresh = str(RefreshToken.for_user(user))

    seen = []

    def _spy(user_id, reason):
        # The signal handler's viewpoint: is the token revoked yet?
        seen.append((user_id, reason, is_jti_blacklisted(access_jti)))

    payload = {'logout_all': True} if logout_kind == 'all' else {'refresh': refresh}

    with patch('accounts.signals._close_user_sessions', side_effect=_spy):
        response = api_client.post(
            '/api/accounts/auth/logout/',
            payload,
            HTTP_AUTHORIZATION=f'Bearer {access}',
        )

    assert response.status_code == 200, response.content[:200]
    assert len(seen) >= 1, 'force_disconnect signal never fired'
    for user_id, reason, blacklisted in seen:
        assert user_id == user.id
        assert blacklisted is True, (
            f'signal fired ({reason}) before the access token was revoked'
        )


# --- async helpers --------------------------------------------------------
# Sync DB access from an async test must be wrapped, per channels' docs.


@database_sync_to_async
def _create_user(username='blacklist_user', email=None):
    return User.objects.create_user(
        username=username,
        email=email or f'{username}@example.com',
        password='Test123!',
    )


@database_sync_to_async
def _issue(user):
    token = AccessToken.for_user(user)
    return str(token), token['jti']


@database_sync_to_async
def _issue_refresh(user):
    return str(RefreshToken.for_user(user))


@database_sync_to_async
def _blacklist_jti(jti):
    cache.set(f'ws_access_blacklist_{jti}', '1', 300)


@database_sync_to_async
def _outstanding_for(user):
    return list(OutstandingToken.objects.filter(user=user))


@database_sync_to_async
def _blacklisted_count(outstanding):
    # Resolve the PKs here rather than passing the queryset to __in:
    # the objects were fetched in a different thread, and lazy
    # evaluation from this thread raises SynchronousOnlyOperation.
    token_ids = [t.pk for t in outstanding]
    return BlacklistedToken.objects.filter(token_id__in=token_ids).count()


@database_sync_to_async
def _http_me(token):
    from rest_framework.test import APIClient

    client = APIClient()
    response = client.get(
        '/api/accounts/users/me/', HTTP_AUTHORIZATION=f'Bearer {token}'
    )
    return response.status_code


def _connect(token):
    return _connect_with(
        f'/ws/notifications/?token={token}',
        [(b'cookie', f'ws_access={token}'.encode())] + WS_HEADERS,
    )


def _connect_with_cookie(token):
    """The production transport: cookie only, no ?token= query string."""
    return _connect_with(
        '/ws/notifications/',
        [(b'cookie', f'ws_access={token}'.encode())] + WS_HEADERS,
    )


async def _connect_with(path, headers):
    communicator = WebsocketCommunicator(
        application, path, headers=headers,
    )
    try:
        return await communicator.connect()
    finally:
        try:
            await communicator.disconnect()
        except Exception:
            pass


@database_sync_to_async
def _logout(api_client, user, access_token):
    refresh = str(RefreshToken.for_user(user))
    api_client.post(
        '/api/accounts/auth/logout/',
        {'refresh': refresh},
        HTTP_AUTHORIZATION=f'Bearer {access_token}',
    )


@database_sync_to_async
def _logout_all(api_client, refresh, access_token):
    api_client.post(
        '/api/accounts/auth/logout/',
        {'logout_all': True, 'refresh': refresh},
        HTTP_AUTHORIZATION=f'Bearer {access_token}',
    )
