"""accounts.views package.

Public view classes are re-exported here so existing imports keep working:

    from accounts.views import UserViewSet
    from accounts.views import RegisterView
    from accounts.views import CustomTokenObtainPairView
    from accounts.views import LogoutView
    from accounts.views import PasswordResetRequestView
    from accounts.views import PasswordResetConfirmView
    from accounts.views import CookieTokenRefreshView

Module-level names that tests patch via the `accounts.views.<name>`
path (e.g. `patch('accounts.views.send_mail', ...)`) are also
re-exported so they keep resolving to the same objects the views
reference.

The implementation lives in submodules:
    - accounts.views.common  : shared helpers (_blacklist_user_tokens)
    - accounts.views.auth     : auth/session views
    - accounts.views.users    : UserViewSet
"""
from .common import _blacklist_user_tokens  # noqa: F401
from .auth import (  # noqa: F401
    RegisterView,
    CustomTokenObtainPairView,
    LogoutView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    CookieTokenRefreshView,
    logger,
    send_mail,
    default_token_generator,
    urlsafe_base64_encode,
    urlsafe_base64_decode,
    force_bytes,
    force_str,
    RefreshToken,
    TokenError,
    set_auth_cookies,
    clear_auth_cookies,
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    blacklist_access_token,
    LoginRateThrottle,
    ScopedRateThrottle,
    CustomTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    UserRegistrationSerializer,
    ChangePasswordSerializer,
)
from .users import (  # noqa: F401
    UserViewSet,
    UserSerializer,
    UserDetailSerializer,
    UserSelfUpdateSerializer,
    UserPublicSerializer,
)
from ..permissions import IsAdminOrManager, IsAdmin  # noqa: F401
from ..models import CustomUser  # noqa: F401
from django.contrib.auth import get_user_model  # noqa: F401
User = get_user_model()

__all__ = [
    '_blacklist_user_tokens',
    'RegisterView',
    'CustomTokenObtainPairView',
    'LogoutView',
    'PasswordResetRequestView',
    'PasswordResetConfirmView',
    'CookieTokenRefreshView',
    'UserViewSet',
    'UserSerializer',
    'UserDetailSerializer',
    'UserSelfUpdateSerializer',
    'UserPublicSerializer',
    'IsAdminOrManager',
    'IsAdmin',
    'CustomUser',
    'User',
    'logger',
    'send_mail',
    'default_token_generator',
    'urlsafe_base64_encode',
    'urlsafe_base64_decode',
    'force_bytes',
    'force_str',
    'RefreshToken',
    'TokenError',
    'set_auth_cookies',
    'clear_auth_cookies',
    'ACCESS_COOKIE',
    'REFRESH_COOKIE',
    'blacklist_access_token',
    'LoginRateThrottle',
    'ScopedRateThrottle',
    'CustomTokenObtainPairSerializer',
    'LogoutSerializer',
    'PasswordResetRequestSerializer',
    'PasswordResetConfirmSerializer',
    'UserRegistrationSerializer',
    'ChangePasswordSerializer',
]
