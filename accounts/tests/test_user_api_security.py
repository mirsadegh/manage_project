"""
PR-4 Commit 1 regression tests.

Covers:
  H-1 / H-2 / H-3: UserViewSet.get_permissions
  H-4: UserPublicSerializer excludes sensitive fields
  M-4: deactivated users (is_active=False) are denied
  M-5: change_password and deactivate_account invalidate tokens
  M-6: JWT _user_claims does NOT include email
  H-5: _blacklist_user_tokens helper
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


User = get_user_model()


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _user_list_url():
    return reverse('user-list')


def _user_detail_url(pk):
    return reverse('user-detail', args=[pk])


def _user_me_url():
    return reverse('user-me')


def _change_password_url():
    return reverse('user-change-password')


def _deactivate_url():
    return reverse('user-deactivate-account')


def _activate_url(pk):
    return reverse('user-activate', args=[pk])


def _login_url():
    return reverse('token_obtain_pair')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role, username=None, email=None, password='Test123!',
               is_active=True, **extra):
    """Create a user with a given role. Caller can override any field."""
    if username is None:
        username = f'{role.lower()}_{User.objects.count()}'
    if email is None:
        email = f'{username}@example.com'
    user = User.objects.create_user(
        username=username, email=email, password=password,
    )
    user.role = role
    user.is_active = is_active
    for k, v in extra.items():
        setattr(user, k, v)
    user.save()
    return user


def _login(client, user):
    return client.post(_login_url(), {
        'email': user.email, 'password': 'Test123!',
    }, format='json')


# ---------------------------------------------------------------------------
# Authorization tests (H-1 / H-2 / H-3)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_developer_list_users_returns_403(dev_user, api_client):
    """H-1: a developer is denied the list endpoint."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_list_users_returns_200(admin_user, api_client):
    """H-1: admin can list users."""
    api_client.force_authenticate(user=admin_user)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_pm_list_users_returns_200(api_client):
    """H-1: project manager (PM) can list users (IsAdminOrManager)."""
    pm = _make_user(User.Role.PROJECT_MANAGER)
    api_client.force_authenticate(user=pm)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_tl_list_users_returns_200(api_client):
    """H-1: team lead (TL) can list users (IsAdminOrManager)."""
    tl = _make_user(User.Role.TEAM_LEAD)
    api_client.force_authenticate(user=tl)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_developer_retrieve_other_user_returns_403(dev_user, api_client):
    """H-2: a developer cannot retrieve another user's detail."""
    other = _make_user(User.Role.DEVELOPER, username='other_dev')
    api_client.force_authenticate(user=dev_user)
    response = api_client.get(_user_detail_url(other.id))
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_retrieve_user_returns_200(admin_user, api_client):
    """H-2: admin can retrieve any user."""
    other = _make_user(User.Role.DEVELOPER, username='other_dev2')
    api_client.force_authenticate(user=admin_user)
    response = api_client.get(_user_detail_url(other.id))
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_developer_me_returns_200(dev_user, api_client):
    """Owner can always read their own profile via /me/."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.get(_user_me_url())
    assert response.status_code == status.HTTP_200_OK
    assert response.data['id'] == dev_user.id


# ---------------------------------------------------------------------------
# Serializer tests (H-4)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_public_serializer_excludes_sensitive_fields():
    """H-4: UserPublicSerializer must not include sensitive fields."""
    from accounts.serializers import UserPublicSerializer

    fields = set(UserPublicSerializer.Meta.fields)
    forbidden = {'email', 'phone_number', 'bio', 'last_login', 'hourly_rate'}
    leaked = fields & forbidden
    assert not leaked, f'UserPublicSerializer leaks: {leaked}'


@pytest.mark.django_db
def test_developer_me_returns_email_via_user_detail(dev_user, api_client):
    """
    /me/ returns the full UserDetailSerializer (incl. email) for the
    owner, even when list/retrieve is otherwise denied for the role.
    """
    api_client.force_authenticate(user=dev_user)
    response = api_client.get(_user_me_url())
    assert response.status_code == status.HTTP_200_OK
    assert 'email' in response.data
    assert response.data['email'] == dev_user.email


@pytest.mark.django_db
def test_admin_detail_includes_email(admin_user, api_client):
    """Admin can see email when retrieving a user."""
    target = _make_user(User.Role.DEVELOPER, username='admin_target')
    api_client.force_authenticate(user=admin_user)
    response = api_client.get(_user_detail_url(target.id))
    assert response.status_code == status.HTTP_200_OK
    assert response.data['email'] == 'admin_target@example.com'


# ---------------------------------------------------------------------------
# JWT tests (M-6)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_jwt_login_response_payload_excludes_email(api_client):
    """
    M-6: the login endpoint's response shape drops email from the
    user-data sub-dict. The /me/ endpoint is the canonical way to
    fetch email.
    """
    user = _make_user(User.Role.DEVELOPER, username='jwt_user')
    response = _login(api_client, user)
    assert response.status_code == status.HTTP_200_OK, response.content
    user_block = response.data.get('user', {})
    assert 'email' not in user_block, (
        f'login response.user should not include email; got: {user_block}'
    )
    assert user_block.get('username') == user.username
    assert user_block.get('role') == user.role


@pytest.mark.django_db
def test_jwt_access_token_payload_excludes_email(api_client):
    """
    M-6 (token): the access JWT issued by the project serializer
    contains username and role but no email claim. We decode the
    token from the login response and inspect its payload.
    """
    user = _make_user(User.Role.DEVELOPER, username='jwt_user2')
    response = _login(api_client, user)
    assert response.status_code == status.HTTP_200_OK
    access = response.data['access']
    payload = AccessToken(access).payload
    assert 'username' in payload
    assert 'role' in payload
    assert 'email' not in payload, (
        f'JWT payload should not include email; got keys: {list(payload)}'
    )


# ---------------------------------------------------------------------------
# Token invalidation tests (M-5, H-5)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_change_password_invalidates_tokens():
    """M-5: change_password blacklists all outstanding tokens."""
    user = _make_user(User.Role.DEVELOPER, username='cp_user')
    refresh = RefreshToken.for_user(user)
    OutstandingToken.objects.get_or_create(
        user=user, jti=refresh['jti'],
        defaults={'token': str(refresh), 'expires_at': refresh['exp']},
    )
    assert OutstandingToken.objects.filter(user=user).count() == 1

    api_client = APIClient()
    api_client.force_authenticate(user=user)
    response = api_client.post(_change_password_url(), {
        'old_password': 'Test123!',
        'new_password': 'NewPass456!',
        'new_password_confirm': 'NewPass456!',
    }, format='json')
    assert response.status_code == status.HTTP_200_OK, response.content

    out = OutstandingToken.objects.get(user=user, jti=refresh['jti'])
    assert BlacklistedToken.objects.filter(token=out).exists(), (
        "change_password should have blacklisted the user's refresh token"
    )


@pytest.mark.django_db
def test_deactivate_account_invalidates_tokens():
    """deactivate_account blacklists all outstanding tokens."""
    user = _make_user(User.Role.DEVELOPER, username='deact_user')
    refresh = RefreshToken.for_user(user)
    OutstandingToken.objects.get_or_create(
        user=user, jti=refresh['jti'],
        defaults={'token': str(refresh), 'expires_at': refresh['exp']},
    )

    api_client = APIClient()
    api_client.force_authenticate(user=user)
    response = api_client.post(_deactivate_url(), {
        'password': 'Test123!',
    }, format='json')
    assert response.status_code == status.HTTP_200_OK, response.content

    user.refresh_from_db()
    assert user.is_active is False
    out = OutstandingToken.objects.get(user=user, jti=refresh['jti'])
    assert BlacklistedToken.objects.filter(token=out).exists(), (
        "deactivate_account should have blacklisted the user's refresh token"
    )


@pytest.mark.django_db
def test_password_reset_confirm_invalidates_tokens():
    """H-5 / M-5: password-reset-confirm blacklists all tokens."""
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes

    user = _make_user(User.Role.DEVELOPER, username='reset_user')
    refresh = RefreshToken.for_user(user)
    OutstandingToken.objects.get_or_create(
        user=user, jti=refresh['jti'],
        defaults={'token': str(refresh), 'expires_at': refresh['exp']},
    )

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    api_client = APIClient()
    response = api_client.post(
        reverse('password_reset_confirm'),
        {
            'uid': uid,
            'token': token,
            'new_password': 'Reset789!',
            'new_password_confirm': 'Reset789!',
        },
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK, response.content

    out = OutstandingToken.objects.get(user=user, jti=refresh['jti'])
    assert BlacklistedToken.objects.filter(token=out).exists(), (
        'password reset confirm should have blacklisted the user\'s tokens'
    )


# ---------------------------------------------------------------------------
# Deactivated-user permission tests (M-4)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_deactivated_admin_denied_on_list():
    """M-4: admin with is_active=False is denied by IsAdminOrManager."""
    admin = _make_user(User.Role.ADMIN, username='dead_admin', is_active=False)

    api_client = APIClient()
    api_client.force_authenticate(user=admin)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_deactivated_pm_denied_on_list():
    """M-4: PM with is_active=False is denied by IsAdminOrManager."""
    pm = _make_user(User.Role.PROJECT_MANAGER, username='dead_pm', is_active=False)

    api_client = APIClient()
    api_client.force_authenticate(user=pm)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_deactivated_admin_cannot_activate_user():
    """M-4: a deactivated admin can't run admin-only actions."""
    admin = _make_user(User.Role.ADMIN, username='dead_adm2', is_active=False)
    target = _make_user(
        User.Role.DEVELOPER, username='inactive_target', is_active=False,
    )

    api_client = APIClient()
    api_client.force_authenticate(user=admin)
    response = api_client.post(_activate_url(target.id))
    assert response.status_code == status.HTTP_403_FORBIDDEN
    target.refresh_from_db()
    assert target.is_active is False, 'target must remain deactivated'
