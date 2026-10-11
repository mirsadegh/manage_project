"""
Regression tests for user API security.

Covers permission checks, serializer privacy, token invalidation,
deactivated-user denial, and JWT payload privacy.
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
import datetime


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
# Authorization tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_developer_list_users_returns_403(dev_user, api_client):
    """A developer is denied the list endpoint."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_list_users_returns_200(admin_user, api_client):
    """An admin can list users."""
    api_client.force_authenticate(user=admin_user)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_pm_list_users_returns_200(api_client):
    """A project manager (PM) can list users."""
    pm = _make_user(User.Role.PROJECT_MANAGER)
    api_client.force_authenticate(user=pm)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_tl_list_users_returns_200(api_client):
    """A team lead (TL) can list users."""
    tl = _make_user(User.Role.TEAM_LEAD)
    api_client.force_authenticate(user=tl)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_developer_retrieve_other_user_returns_403(dev_user, api_client):
    """A developer cannot retrieve another user's detail."""
    other = _make_user(User.Role.DEVELOPER, username='other_dev')
    api_client.force_authenticate(user=dev_user)
    response = api_client.get(_user_detail_url(other.id))
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_retrieve_user_returns_200(admin_user, api_client):
    """An admin can retrieve any user."""
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
# Serializer tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_public_serializer_excludes_sensitive_fields():
    """UserPublicSerializer must not include sensitive fields."""
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
# JWT tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_jwt_login_response_payload_excludes_email(api_client):
    """
    The login endpoint's response shape drops email from the
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
    The access JWT issued by the project serializer contains
    username and role but no email claim. We decode the token from
    the login response and inspect its payload.
    """
    user = _make_user(User.Role.DEVELOPER, username='jwt_user2')
    response = _login(api_client, user)
    assert response.status_code == status.HTTP_200_OK
    # The access token is no longer in the JSON body by default;
    # it is delivered exclusively via the HttpOnly ws_access cookie.
    # RETURN_TOKENS_IN_BODY legacy flag restores the body token.
    from django.conf import settings
    from config.auth_cookies import ACCESS_COOKIE
    if settings.RETURN_TOKENS_IN_BODY:
        access = response.data['access']
    else:
        assert 'access' not in response.data, (
            'access token must not be in response body unless '
            'RETURN_TOKENS_IN_BODY is enabled'
        )
        access = response.cookies[ACCESS_COOKIE].value
    payload = AccessToken(access).payload
    assert 'username' in payload
    assert 'role' in payload
    assert 'email' not in payload, (
        f'JWT payload should not include email; got keys: {list(payload)}'
    )


# ---------------------------------------------------------------------------
# Token invalidation tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_change_password_invalidates_tokens():
    """change_password blacklists all outstanding tokens."""
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
def test_deactivate_last_active_admin_returns_400():
    """The last active admin cannot deactivate themselves (lockout)."""
    admin = _make_user(User.Role.ADMIN, username='last_admin_deact')
    # Make this admin the only active one.
    User.objects.filter(
        role=User.Role.ADMIN, is_active=True,
    ).exclude(pk=admin.pk).update(is_active=False)

    api_client = APIClient()
    api_client.force_authenticate(user=admin)
    response = api_client.post(_deactivate_url(), {
        'password': 'Test123!',
    }, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    assert 'last' in str(response.data).lower()
    admin.refresh_from_db()
    assert admin.is_active is True, 'account must NOT be deactivated'


@pytest.mark.django_db
def test_deactivate_non_last_admin_allowed():
    """An admin can still deactivate themselves if another admin exists."""
    admin = _make_user(User.Role.ADMIN, username='deact_actor')
    _make_user(User.Role.ADMIN, username='deact_other_admin')

    api_client = APIClient()
    api_client.force_authenticate(user=admin)
    response = api_client.post(_deactivate_url(), {
        'password': 'Test123!',
    }, format='json')
    assert response.status_code == status.HTTP_200_OK, response.content
    admin.refresh_from_db()
    assert admin.is_active is False


@pytest.mark.django_db
def test_password_reset_confirm_invalidates_tokens():
    """password-reset-confirm blacklists all tokens."""
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
# Deactivated-user permission tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_deactivated_admin_denied_on_list():
    """An admin with is_active=False is denied by IsAdminOrManager."""
    admin = _make_user(User.Role.ADMIN, username='dead_admin', is_active=False)

    api_client = APIClient()
    api_client.force_authenticate(user=admin)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_deactivated_pm_denied_on_list():
    """A PM with is_active=False is denied by IsAdminOrManager."""
    pm = _make_user(User.Role.PROJECT_MANAGER, username='dead_pm', is_active=False)

    api_client = APIClient()
    api_client.force_authenticate(user=pm)
    response = api_client.get(_user_list_url())
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_deactivated_admin_cannot_activate_user():
    """A deactivated admin can't run admin-only actions."""
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


# ---------------------------------------------------------------------------
# UserViewSet hardening regression tests (this change)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unknown_action_denies_developer_by_default():
    """Deny-by-default: an unlisted action falls back to IsAdmin.

    Simulate a future action that forgot to register itself in
    get_permissions: a developer must NOT get the old
    IsAuthenticated fallback (which granted every authenticated
    user access).
    """
    from accounts.views import UserViewSet
    from accounts.permissions import IsAdmin

    dev = _make_user(User.Role.DEVELOPER, username='future_dev')
    view = UserViewSet()
    view.action = 'brand_new_action'  # not in the permission map
    perms = view.get_permissions()
    assert len(perms) == 1
    assert isinstance(perms[0], IsAdmin)

    # And the permission check itself denies the developer.
    from rest_framework.request import Request
    from django.test import RequestFactory
    rf = RequestFactory()
    django_request = rf.get('/')
    django_request.user = dev
    drf_request = Request(django_request)
    assert perms[0].has_permission(drf_request, view) is False


@pytest.mark.django_db
def test_metadata_action_requires_authentication():
    """OPTIONS (metadata) keeps IsAuthenticated, not the admin fallback."""
    from accounts.views import UserViewSet
    from rest_framework import permissions

    view = UserViewSet()
    view.action = 'metadata'
    perms = view.get_permissions()
    assert len(perms) == 1
    assert isinstance(perms[0], permissions.IsAuthenticated)


@pytest.mark.django_db
def test_retrieve_issues_single_query(admin_user, api_client):
    """retrieve must fetch the object exactly once (not twice)."""
    from django.test.utils import CaptureQueriesContext
    from django.db import connection

    target = _make_user(User.Role.DEVELOPER, username='single_query_user')
    api_client.force_authenticate(user=admin_user)

    with CaptureQueriesContext(connection) as ctx:
        response = api_client.get(_user_detail_url(target.id))
    assert response.status_code == status.HTTP_200_OK
    # Exactly one SELECT for the addressed user. Before the
    # fix, get_serializer_class() and retrieve() each called
    # get_object(), issuing the same query twice.
    assert len(ctx.captured_queries) == 1, (
        f'retrieve issued {len(ctx.captured_queries)} queries: '
        f'{[q["sql"] for q in ctx.captured_queries]}'
    )
    assert ctx.captured_queries[0]['sql'].lstrip().upper().startswith('SELECT')


@pytest.mark.django_db
def test_retrieve_serializer_selection_by_role():
    """Serializer choice: admin/manager/owner get detail, others public."""
    from accounts.serializers import UserDetailSerializer, UserPublicSerializer
    from accounts.views import UserViewSet

    target = _make_user(User.Role.DEVELOPER, username='ser_target')

    def _serializer_for(requester_user):
        view = UserViewSet()
        view.action = 'retrieve'
        view.request = type('R', (), {'user': requester_user})()
        view.kwargs = {'pk': target.pk}
        view._object_cache = target
        return view.get_serializer_class()

    # admin -> detail
    admin = _make_user(User.Role.ADMIN, username='ser_admin')
    assert _serializer_for(admin) is UserDetailSerializer
    # manager (PM) -> detail
    pm = _make_user(User.Role.PROJECT_MANAGER, username='ser_pm')
    assert _serializer_for(pm) is UserDetailSerializer
    # ordinary user viewing ANOTHER user's record -> public
    stranger = _make_user(User.Role.DEVELOPER, username='ser_stranger')
    assert _serializer_for(stranger) is UserPublicSerializer
    # owner viewing their OWN record -> detail
    assert _serializer_for(target) is UserDetailSerializer


@pytest.mark.django_db
def test_retrieve_serializer_owner_sees_own_detail():
    """A developer retrieving their own record gets UserDetailSerializer."""
    from accounts.serializers import UserDetailSerializer
    from accounts.views import UserViewSet

    owner = _make_user(User.Role.DEVELOPER, username='own_detail_user')
    view = UserViewSet()
    view.action = 'retrieve'
    view.request = type('R', (), {'user': owner})()
    view.kwargs = {'pk': owner.pk}
    view._object_cache = owner
    assert view.get_serializer_class() is UserDetailSerializer


@pytest.mark.django_db
def test_retrieve_serializer_fails_closed_on_missing_object():
    """A failed lookup must yield UserPublicSerializer, never detail.

    Exercises the real error path: the object is not pre-cached, so
    get_serializer_class()'s try/except actually calls get_object()
    and must swallow Http404 and return the public serializer.
    """
    from accounts.serializers import UserPublicSerializer
    from accounts.views import UserViewSet
    from rest_framework.test import APIRequestFactory
    from rest_framework.request import Request

    requester = _make_user(User.Role.DEVELOPER, username='fail_closed_user')
    factory = APIRequestFactory()
    view = UserViewSet()
    view.action = 'retrieve'
    view.request = Request(factory.get('/api/accounts/users/999999/'))
    view.request.user = requester
    view.kwargs = {'pk': 999999}  # does not exist -> Http404
    # NOTE: deliberately not setting view._object_cache.
    assert view.get_serializer_class() is UserPublicSerializer


@pytest.mark.django_db
def test_retrieve_serializer_fails_closed_on_permission_denied(monkeypatch):
    """An object-permission failure must yield UserPublicSerializer.

    DRF's check_object_permissions raises
    rest_framework.exceptions.PermissionDenied (which does NOT
    subclass django.core.exceptions.PermissionDenied), so the catch
    clause must name the DRF class.
    """
    from accounts.serializers import UserPublicSerializer
    from accounts.views import UserViewSet
    from rest_framework.test import APIRequestFactory
    from rest_framework.request import Request
    from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied

    requester = _make_user(User.Role.DEVELOPER, username='perm_denied_user')
    target = _make_user(User.Role.DEVELOPER, username='perm_denied_target')

    factory = APIRequestFactory()
    view = UserViewSet()
    view.action = 'retrieve'
    view.request = Request(factory.get(f'/api/accounts/users/{target.pk}/'))
    view.request.user = requester
    view.kwargs = {'pk': target.pk}

    def _deny(self, request, obj):
        raise DRFPermissionDenied()

    monkeypatch.setattr(UserViewSet, 'check_object_permissions', _deny)
    try:
        assert view.get_serializer_class() is UserPublicSerializer
    finally:
        monkeypatch.undo()


@pytest.mark.django_db
def test_retrieve_serializer_detail_not_leaked_on_missing_object(admin_user, api_client):
    """End-to-end: hitting a missing user gets public data + 404.

    Uses an admin (retrieve is admin-only at the class level) so the
    request reaches the object lookup, which raises Http404. The
    response must not leak detail fields.
    """
    api_client.force_authenticate(user=admin_user)
    response = api_client.get(_user_detail_url(999999))
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert 'email' not in response.data


@pytest.mark.django_db
def test_self_delete_returns_400(admin_user, api_client):
    """An admin cannot delete their own account via this endpoint."""
    api_client.force_authenticate(user=admin_user)
    response = api_client.delete(_user_detail_url(admin_user.id))
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'own account' in str(response.data).lower()
    assert User.objects.filter(pk=admin_user.pk).exists()


@pytest.mark.django_db
def test_delete_last_active_admin_returns_400():
    """Deleting the last remaining active admin is refused.

    When only one active admin exists, no other admin caller
    can be present, so exercise perform_destroy directly: the
    guard must raise before the delete runs.
    """
    from accounts.views import UserViewSet
    from rest_framework.exceptions import ValidationError

    target = _make_user(User.Role.ADMIN, username='sole_admin')
    # Make target the only active admin.
    User.objects.filter(
        role=User.Role.ADMIN, is_active=True,
    ).exclude(pk=target.pk).update(is_active=False)
    assert User.objects.filter(
        role=User.Role.ADMIN, is_active=True,
    ).count() == 1

    view = UserViewSet()
    view.action = 'destroy'
    view.request = type('R', (), {'user': target})()
    assert view._is_last_active_admin(target) is True

    with pytest.raises(ValidationError):
        view.perform_destroy(target)
    assert User.objects.filter(pk=target.pk).exists()


@pytest.mark.django_db
def test_delete_non_last_admin_allowed():
    """A non-last admin can still be deleted by another admin."""
    admin = _make_user(User.Role.ADMIN, username='delete_actor')
    target = _make_user(User.Role.ADMIN, username='delete_target')
    from accounts.views import UserViewSet
    view = UserViewSet()
    view.action = 'destroy'
    view.request = type('R', (), {'user': admin})()
    assert view._is_last_active_admin(target) is False
    view.perform_destroy(target)
    assert not User.objects.filter(pk=target.pk).exists()


@pytest.mark.django_db
def test_update_demote_last_admin_returns_400():
    """Demoting the last active admin via PATCH is refused."""
    admin = _make_user(User.Role.ADMIN, username='demote_last_admin')
    # Make admin the only active admin.
    api_client = APIClient()
    api_client.force_authenticate(user=admin)
    response = api_client.patch(
        _user_detail_url(admin.id), {'role': 'DEV'}, format='json',
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'last remaining active admin' in str(response.data).lower()
    admin.refresh_from_db()
    assert admin.role == User.Role.ADMIN


@pytest.mark.django_db
def test_update_deactivate_last_admin_is_guarded():
    """Deactivating the last active admin is refused (defense-in-depth).

    is_active is not a serializer field, so the HTTP API ignores
    it today; this exercises perform_update directly to pin the
    guard so a future serializer that exposes is_active cannot
    deactivate the last admin.
    """
    from accounts.views import UserViewSet
    from rest_framework.exceptions import ValidationError

    admin = _make_user(User.Role.ADMIN, username='deact_last_admin')
    User.objects.filter(
        role=User.Role.ADMIN, is_active=True,
    ).exclude(pk=admin.pk).update(is_active=False)

    from accounts.serializers import UserSerializer
    view = UserViewSet()
    view.action = 'partial_update'
    view.request = type('R', (), {'user': admin})()
    view.kwargs = {'pk': admin.pk}
    view._object_cache = admin
    serializer = UserSerializer(admin, data={}, partial=True)
    serializer.is_valid()
    # Simulate validated_data carrying is_active=False (what a
    # future serializer exposing is_active would produce).
    serializer.validated_data['is_active'] = False
    with pytest.raises(ValidationError):
        view.perform_update(serializer)
    admin.refresh_from_db()
    assert admin.is_active is True


@pytest.mark.django_db
def test_update_non_last_admin_demote_allowed():
    """Demoting an admin is allowed when another active admin exists."""
    admin_a = _make_user(User.Role.ADMIN, username='demote_actor')
    admin_b = _make_user(User.Role.ADMIN, username='demote_target')
    api_client = APIClient()
    api_client.force_authenticate(user=admin_a)
    response = api_client.patch(
        _user_detail_url(admin_b.id), {'role': 'DEV'}, format='json',
    )
    assert response.status_code == status.HTTP_200_OK
    admin_b.refresh_from_db()
    assert admin_b.role == User.Role.DEVELOPER


@pytest.mark.django_db
def test_change_password_no_blacklist_on_save_failure(monkeypatch):
    """Tokens are NOT blacklisted if saving the password fails."""
    user = _make_user(User.Role.DEVELOPER, username='cp_fail_user')
    refresh = RefreshToken.for_user(user)
    OutstandingToken.objects.get_or_create(
        user=user, jti=refresh['jti'],
        defaults={'token': str(refresh), 'expires_at': refresh['exp']},
    )

    api_client = APIClient()
    api_client.force_authenticate(user=user)

    from django.db import IntegrityError

    def _boom(*args, **kwargs):
        raise IntegrityError('forced save failure')

    # Patch User.save so the password save fails.
    monkeypatch.setattr(User, 'save', _boom)

    # The IntegrityError propagates out of the view (DRF does
    # not convert it to a 4xx/5xx response in tests); the
    # important assertion is that the token was NOT
    # blacklisted before the failing save.
    with pytest.raises(IntegrityError):
        api_client.post(_change_password_url(), {
            'old_password': 'Test123!',
            'new_password': 'NewPass456!',
            'new_password_confirm': 'NewPass456!',
        }, format='json')

    out = OutstandingToken.objects.get(user=user, jti=refresh['jti'])
    assert not BlacklistedToken.objects.filter(token=out).exists(), (
        'tokens must NOT be blacklisted when the password save fails'
    )

    monkeypatch.undo()


@pytest.mark.django_db
def test_change_password_blacklists_after_save():
    """Happy path: tokens blacklisted only after a successful save."""
    user = _make_user(User.Role.DEVELOPER, username='cp_ok_user')
    refresh = RefreshToken.for_user(user)
    OutstandingToken.objects.get_or_create(
        user=user, jti=refresh['jti'],
        defaults={'token': str(refresh), 'expires_at': refresh['exp']},
    )

    api_client = APIClient()
    api_client.force_authenticate(user=user)
    response = api_client.post(_change_password_url(), {
        'old_password': 'Test123!',
        'new_password': 'NewPass456!',
        'new_password_confirm': 'NewPass456!',
    }, format='json')
    assert response.status_code == status.HTTP_200_OK, response.content

    out = OutstandingToken.objects.get(user=user, jti=refresh['jti'])
    assert BlacklistedToken.objects.filter(token=out).exists()


@pytest.mark.django_db
def test_me_cannot_self_escalate_role(dev_user, api_client):
    """PATCH /me/ must not let a user change their own role."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(
        _user_me_url(), {'role': 'ADMIN'}, format='json',
    )
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.role == User.Role.DEVELOPER, (
        'self-service /me/ must not escalate role'
    )


@pytest.mark.django_db
def test_me_cannot_write_is_active(dev_user, api_client):
    """PATCH /me/ must not let a user change their own is_active."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(_user_me_url(), {'is_active': False}, format='json')
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.is_active is True, 'is_active must NOT be writable via /me/'


@pytest.mark.django_db
def test_me_cannot_write_is_staff(dev_user, api_client):
    """PATCH /me/ must not let a user change their own is_staff."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(_user_me_url(), {'is_staff': True}, format='json')
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.is_staff is False, 'is_staff must NOT be writable via /me/'


@pytest.mark.django_db
def test_me_cannot_write_is_superuser(dev_user, api_client):
    """PATCH /me/ must not let a user change their own is_superuser."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(_user_me_url(), {'is_superuser': True}, format='json')
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.is_superuser is False, 'is_superuser must NOT be writable via /me/'


@pytest.mark.django_db
def test_me_cannot_write_date_joined(dev_user, api_client):
    """PATCH /me/ must not let a user change their own date_joined."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(_user_me_url(), {'date_joined': '2020-01-01T00:00:00Z'}, format='json')
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.date_joined != datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc), 'date_joined must NOT be writable via /me/'


@pytest.mark.django_db
def test_me_cannot_write_username(dev_user, api_client):
    """PATCH /me/ must not let a user change their own username."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(_user_me_url(), {'username': 'new_username'}, format='json')
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.username != 'new_username', 'username must NOT be writable via /me/'


@pytest.mark.django_db
def test_me_cannot_write_phone_number(dev_user, api_client):
    """PATCH /me/ must not let a user change their own phone_number."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(_user_me_url(), {'phone_number': '09123456789'}, format='json')
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.phone_number != '09123456789', 'phone_number must NOT be writable via /me/'


@pytest.mark.django_db
def test_me_cannot_write_bio(dev_user, api_client):
    """PATCH /me/ must not let a user change their own bio."""
    api_client.force_authenticate(user=dev_user)
    response = api_client.patch(_user_me_url(), {'bio': 'new bio'}, format='json')
    assert response.status_code == status.HTTP_200_OK
    dev_user.refresh_from_db()
    assert dev_user.bio != 'new bio', 'bio must NOT be writable via /me/'


@pytest.mark.django_db

@pytest.mark.django_db
def test_admin_can_still_assign_role_via_update(admin_user, api_client):
    """Admins retain the ability to set roles through PATCH /users/{id}/."""
    target = _make_user(User.Role.DEVELOPER, username='role_assign_target')
    api_client.force_authenticate(user=admin_user)
    response = api_client.patch(
        _user_detail_url(target.id), {'role': 'PM'}, format='json',
    )
    assert response.status_code == status.HTTP_200_OK
    target.refresh_from_db()
    assert target.role == User.Role.PROJECT_MANAGER
