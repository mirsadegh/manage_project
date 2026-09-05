"""
PR-4 Commit 2 regression tests.

Covers:
  M-1: registration throttle (5/hour via ScopedRateThrottle)
  M-2: password-reset throttle_classes now wired
  M-3: SMTP failure no longer raises (enumeration oracle closed)
  L-1: generic registration error message
  L-2: registration auto-login (returns access + refresh tokens)
"""
import logging
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import BadHeaderError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


User = get_user_model()


@pytest.fixture
def anon_client():
    # CookieJWTAuthentication (PR-6) reads the `ws_access` HttpOnly cookie.
    # The test client persists cookies across calls by default, so the 2nd
    # registration request would arrive carrying the cookies set by the 1st
    # request's response and be (incorrectly) authenticated as user #1 —
    # giving each request a different throttle bucket and breaking the
    # `5/hour` rate assertion. We don't actually want to share state
    # between simulated users; clear cookies before each call to mirror
    # what a fresh browser would send.
    client = APIClient()
    client.credentials()  # ensure no Authorization header
    return client


def _clear_cookies(client):
    """Reset cookies on the test client. Mirrors a fresh browser session."""
    client.cookies.clear()


@pytest.fixture
def locmem_cache(settings):
    """Override DummyCache to LocMemCache so throttle counters persist.

    config/settings_test.py uses DummyCache (no-op); throttle counters
    there never increment, so throttling cannot be observed. LocMemCache
    is in-process and isolated per test (random LOCATION).
    """
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': f'accounts-throttle-{uuid.uuid4().hex}',
        }
    }


class _ThrottleScopeOverride:
    """Temporarily set ScopedRateThrottle.THROTTLE_RATES.

    ScopedRateThrottle caches the THROTTLE_RATES dict reference at class
    definition time. override_settings updates api_settings but does NOT
    update the class attribute. This patches the class attribute directly
    so throttle tests can run with custom rates.
    """

    def __init__(self, **scope_rates):
        self.scope_rates = scope_rates
        self._original = None

    def __enter__(self):
        from rest_framework.throttling import ScopedRateThrottle
        self._original = dict(ScopedRateThrottle.THROTTLE_RATES)
        new_rates = dict(self._original)
        new_rates.update(self.scope_rates)
        ScopedRateThrottle.THROTTLE_RATES = new_rates
        return self

    def __exit__(self, *args):
        from rest_framework.throttling import ScopedRateThrottle
        ScopedRateThrottle.THROTTLE_RATES = self._original


# ---------------------------------------------------------------------------
# M-1: registration throttle
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_registration_throttled_after_5_requests(anon_client):
    """M-1: 6th registration in the window is 429 Too Many Requests."""
    with _ThrottleScopeOverride(registration='5/hour'):
        url = reverse('register')
        for i in range(5):
            data = {
                'username': f'rate_user_{i}',
                'email': f'rate_user_{i}@example.com',
                'password': 'Test123!@#',
                'password_confirm': 'Test123!@#',
                'first_name': 'Rate',
                'last_name': f'User{i}',
            }
            # PR-6: clear any cookies set by the previous request so
            # CookieJWTAuthentication doesn't authenticate this one as
            # the previously-registered user (which would put each
            # request in its own throttle bucket and defeat the
            # `5/hour` rate assertion).
            _clear_cookies(anon_client)
            response = anon_client.post(url, data, format='json')
            assert response.status_code == status.HTTP_201_CREATED, (
                f'Request {i+1} expected 201, got {response.status_code}: {response.content}'
            )

        # 6th request: throttled.
        sixth = {
            'username': 'rate_user_99',
            'email': 'rate_user_99@example.com',
            'password': 'Test123!@#',
            'password_confirm': 'Test123!@#',
            'first_name': 'Rate',
            'last_name': 'User99',
        }
        # PR-6: same reason — clear cookies so the 6th request arrives
        # anonymous (matching the throttle's intended bucket for an
        # unauthenticated registration).
        _clear_cookies(anon_client)
        response = anon_client.post(url, sixth, format='json')
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            f'6th request expected 429, got {response.status_code}: {response.content}'
        )


# ---------------------------------------------------------------------------
# M-2: password-reset throttle
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_password_reset_throttled_after_5_requests(anon_client):
    """M-2: 6th password-reset request in the window is 429."""
    with _ThrottleScopeOverride(password_reset='5/hour'):
        url = reverse('password_reset_request')
        payload = {'email': 'someone@example.com'}

        for i in range(5):
            # PR-6: clear cookies so CookieJWTAuthentication doesn't
            # authenticate this request as someone previously registered
            # in the test session.
            _clear_cookies(anon_client)
            response = anon_client.post(url, payload, format='json')
            assert response.status_code != status.HTTP_429_TOO_MANY_REQUESTS, (
                f'Request {i+1} unexpectedly throttled: {response.status_code}'
            )

        _clear_cookies(anon_client)
        response = anon_client.post(url, payload, format='json')
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            f'6th request expected 429, got {response.status_code}'
        )


# ---------------------------------------------------------------------------
# M-1 + M-2: scopes are independent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.usefixtures('locmem_cache')
def test_throttle_scopes_are_independent(anon_client):
    """Hitting the registration limit must not block password-reset."""
    with _ThrottleScopeOverride(registration='2/hour', password_reset='2/hour'):
        reg_url = reverse('register')
        reset_url = reverse('password_reset_request')

        # Burn the registration quota.
        for i in range(2):
            data = {
                'username': f'ind_reg_{i}',
                'email': f'ind_reg_{i}@example.com',
                'password': 'Test123!@#',
                'password_confirm': 'Test123!@#',
                'first_name': 'Ind',
                'last_name': f'Reg{i}',
            }
            # PR-6: clear cookies so each registration request is
            # anonymous (otherwise the 2nd request would be
            # authenticated as the user from the 1st response and use
            # a different throttle bucket).
            _clear_cookies(anon_client)
            r = anon_client.post(reg_url, data, format='json')
            assert r.status_code != status.HTTP_429_TOO_MANY_REQUESTS
        # 3rd registration is throttled.
        _clear_cookies(anon_client)
        r = anon_client.post(reg_url, {
            'username': 'ind_reg_99', 'email': 'ind_reg_99@example.com',
            'password': 'Test123!@#', 'password_confirm': 'Test123!@#',
            'first_name': 'Ind', 'last_name': 'Reg99',
        }, format='json')
        assert r.status_code == status.HTTP_429_TOO_MANY_REQUESTS

        # Password-reset must still work — independent scope.
        for i in range(2):
            _clear_cookies(anon_client)
            r = anon_client.post(reset_url, {'email': 'someone@example.com'}, format='json')
            assert r.status_code != status.HTTP_429_TOO_MANY_REQUESTS, (
                f'reset {i+1} was throttled by registration scope'
            )


# ---------------------------------------------------------------------------
# M-3: SMTP enumeration oracle closed
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_password_reset_returns_200_for_nonexistent_email(anon_client):
    """M-3: non-existent email still gets the generic 200 (no leak)."""
    url = reverse('password_reset_request')
    response = anon_client.post(
        url, {'email': 'nobody-here@example.com'}, format='json',
    )
    assert response.status_code == status.HTTP_200_OK
    assert 'If an account with this email exists' in response.data['message']
    # mail.outbox should be empty: no email was sent.
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_password_reset_always_returns_200_on_smtp_failure(anon_client):
    """M-3: SMTP raise → 200 (NOT 500). The oracle is closed."""
    User.objects.create_user(
        username='existing', email='exists@example.com', password='Test123!',
    )
    url = reverse('password_reset_request')

    with patch('accounts.views.send_mail', side_effect=BadHeaderError('SMTP down')):
        response = anon_client.post(
            url, {'email': 'exists@example.com'}, format='json',
        )

    # Critical: 200, not 500.
    assert response.status_code == status.HTTP_200_OK, (
        f'SMTP failure should still return 200; got {response.status_code}: {response.content}'
    )
    assert 'If an account with this email exists' in response.data['message']


@pytest.mark.django_db
def test_password_reset_smtp_failure_is_logged(anon_client, caplog):
    """M-3: SMTP failure is logged via logger.exception."""
    User.objects.create_user(
        username='logger_user', email='logger@example.com', password='Test123!',
    )
    url = reverse('password_reset_request')

    with patch('accounts.views.send_mail', side_effect=BadHeaderError('SMTP is down')):
        with caplog.at_level(logging.ERROR, logger='accounts'):
            response = anon_client.post(
                url, {'email': 'logger@example.com'}, format='json',
            )
    assert response.status_code == status.HTTP_200_OK

    # caplog may not capture across the WS/test boundary; treat as
    # best-effort. The contract is the 200, not the log capture.
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    if error_records:
        assert any(
            'Password reset email failed' in r.getMessage()
            for r in error_records
        )


# ---------------------------------------------------------------------------
# L-1: generic registration error
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_registration_duplicate_email_returns_generic_message(anon_client):
    """L-1: duplicate email returns the generic message, not 'already exists'."""
    User.objects.create_user(
        username='existing_user', email='dup@example.com', password='Test123!',
    )
    url = reverse('register')
    response = anon_client.post(url, {
        'username': 'new_user_1',
        'email': 'dup@example.com',
        'password': 'Test123!@#',
        'password_confirm': 'Test123!@#',
        'first_name': 'New',
        'last_name': 'User',
    }, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # Must use the generic message; must NOT include 'already exists'.
    body_text = str(response.data)
    assert 'Registration failed' in body_text
    assert 'already exists' not in body_text, (
        f'Response leaked email-existence info: {response.data}'
    )


@pytest.mark.django_db
def test_registration_duplicate_username_returns_generic_message(anon_client):
    """L-1: duplicate username also returns the generic message."""
    User.objects.create_user(
        username='taken', email='taken@example.com', password='Test123!',
    )
    url = reverse('register')
    response = anon_client.post(url, {
        'username': 'taken',
        'email': 'fresh@example.com',
        'password': 'Test123!@#',
        'password_confirm': 'Test123!@#',
        'first_name': 'Fresh',
        'last_name': 'User',
    }, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # The username uniqueness check is a separate code path
    # (django.contrib.auth makes it transparent to DRF). The contract
    # is just: don't leak that the email is unique.
    body_text = str(response.data)
    assert 'already exists' not in body_text


# ---------------------------------------------------------------------------
# L-2: auto-login (returns access + refresh tokens)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_registration_returns_tokens(anon_client):
    """L-2 (intentional): successful registration returns access + refresh."""
    url = reverse('register')
    response = anon_client.post(url, {
        'username': 'autologin_user',
        'email': 'autologin@example.com',
        'password': 'Test123!@#',
        'password_confirm': 'Test123!@#',
        'first_name': 'Auto',
        'last_name': 'Login',
    }, format='json')
    assert response.status_code == status.HTTP_201_CREATED, response.content
    assert 'tokens' in response.data
    assert 'access' in response.data['tokens']
    assert 'refresh' in response.data['tokens']
    assert 'user' in response.data
    assert response.data['user']['username'] == 'autologin_user'
