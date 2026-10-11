"""Authentication / session views for the accounts app."""
import logging

from rest_framework import generics, status, permissions
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes, force_str

from ..models import CustomUser
from ..serializers import (
    UserRegistrationSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    LogoutSerializer,
    CustomTokenObtainPairSerializer,
)
from config.auth_cookies import set_auth_cookies, clear_auth_cookies, ACCESS_COOKIE, REFRESH_COOKIE
from config.token_blacklist import blacklist_access_token
from config.throttling import LoginRateThrottle

from .common import _blacklist_user_tokens

User = get_user_model()

logger = logging.getLogger('accounts')


@method_decorator(ensure_csrf_cookie, name='create')
class RegisterView(generics.CreateAPIView):
    """User registration endpoint."""
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegistrationSerializer
    # PR-4 M-1: cap registration to 5/hour per IP to deter mass-signup abuse.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'registration'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # PR-4 L-2 (intentional): return access + refresh tokens here so
        # the user is auto-logged-in after registration. The frontend
        # benefits from fewer round-trips; the trade-off is a 7-day
        # refresh token created without an explicit consent step.
        # Documented as an accepted risk; revisit if user feedback
        # changes.
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        refresh_str = str(refresh)

        # PR-6: also set the tokens as HttpOnly cookies so the
        # WebSocket upgrade can authenticate without ?token=. M-2: the
        # token values are NOT returned in the JSON body; they are
        # XSS-theft-prone and the cookie is the auth channel. Set
        # RETURN_TOKENS_IN_BODY=true to restore body tokens for legacy
        # tooling/debugging.
        response = Response({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            },
            'tokens': {
                'refresh': refresh_str,
                'access': access,
            }
        }, status=status.HTTP_201_CREATED)
        set_auth_cookies(response, access=access, refresh=refresh_str)
        if not settings.RETURN_TOKENS_IN_BODY:
            response.data.pop('tokens', None)
        return response


@method_decorator(ensure_csrf_cookie, name='post')
class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom login view with rate limiting.
    The throttle is applied at the view level to ensure it works correctly.

    PR-6: on a successful login, the access and refresh tokens are also
    set as HttpOnly cookies so the WebSocket upgrade can authenticate
    without ?token=. The JSON body still contains the tokens for
    backward compatibility with existing tools.
    """
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        # Throttling is automatically applied by DRF before this method runs
        response = super().post(request, *args, **kwargs)
        # Only set cookies on a successful login. A 401/400 response has
        # no 'access' field, and setting a cookie there would confuse
        # any tooling that probes for Set-Cookie on errors.
        if response.status_code == status.HTTP_200_OK and 'access' in response.data:
            set_auth_cookies(
                response,
                access=response.data.get('access'),
                refresh=response.data.get('refresh'),
            )
            # M-2: tokens stay in HttpOnly cookies only unless the
            # legacy body-mode env flag is set.
            if not settings.RETURN_TOKENS_IN_BODY:
                response.data.pop('access', None)
                response.data.pop('refresh', None)
        return response


class LogoutView(APIView):
    """
    Logout endpoint that blacklists the refresh token.
    Supports both single token logout and logout from all devices.

    PR-6: also clears the auth cookies so the browser drops them.
    The force_disconnect signal (PR-3 Fix #1) closes any open WS
    connections immediately.

    Access-token blacklist: SimpleJWT's OutstandingToken table only
    tracks refresh tokens, so without this the ws_access cookie would
    stay valid until its natural TTL. On every logout we also write the
    presented access token's jti to the Redis cache for its remaining
    lifetime, which both WS and HTTP auth consult on every request. The
    cache entry expires on its own at exactly the moment the token
    stops being verifiable, so it cannot outlive the threat.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _resolve_access_token(self, request):
        """Extract the access token from header or cookie.

        Mirrors config.auth_jwt.CookieJWTAuthentication's lookup so the
        token we blacklist is the same one the client is authenticating
        with, whatever transport carried it.
        """
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:]
        return request.COOKIES.get(ACCESS_COOKIE)

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data.get('refresh')
        logout_all = serializer.validated_data.get('logout_all', False)

        if logout_all:
            # Blacklist the calling device's access token FIRST. The
            # BlacklistedToken post_save signal fires force_disconnect;
            # if the refresh side ran first, a client reconnecting in
            # that window could slip past the not-yet-written access
            # token. Other devices' access tokens are not individually
            # tracked and expire within ACCESS_TOKEN_LIFETIME — they
            # cannot obtain new tokens once every refresh is revoked.
            access_token = self._resolve_access_token(request)
            if access_token and not blacklist_access_token(access_token):
                logger.error(
                    "logout_all: access-token blacklist write failed for "
                    "user_id=%s; token may remain valid beyond expected TTL",
                    request.user.id,
                )
            # PR-4: shared helper. Runs after the access token so the
            # signal it triggers sees the jti already revoked.
            _blacklist_user_tokens(request.user)
            response = Response({'message': 'Successfully logged out from all devices'})
            clear_auth_cookies(response)
            return response

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
            except TokenError:
                return Response(
                    {'error': 'Invalid or expired token'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Access token outlives the refresh token by design, so
            # revoke it BEFORE the refresh blacklist: the post_save
            # signal force-disconnects live sockets, and a client
            # reconnecting immediately must find the jti already
            # revoked. The RefreshToken constructor above still runs
            # first, so an invalid refresh still returns the same 400
            # with nothing revoked.
            access_token = self._resolve_access_token(request)
            if access_token and not blacklist_access_token(access_token):
                logger.error(
                    "single logout: access-token blacklist write failed "
                    "for user_id=%s; token may remain valid beyond "
                    "expected TTL",
                    request.user.id,
                )
            token.blacklist()
            response = Response({'message': 'Successfully logged out'})
            clear_auth_cookies(response)
            return response
        return Response(
            {'error': 'Refresh token is required'},
            status=status.HTTP_400_BAD_REQUEST
        )


class PasswordResetRequestView(APIView):
    """
    Request a password reset email.
    """
    permission_classes = [permissions.AllowAny]
    # `throttle_scope = 'password_reset'` actually applies (5/hour per IP).
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']

        # PR-4 M-3: never raise from this endpoint. SMTP failure must not
        # leak which email exists (would be an enumeration oracle). Log
        # the error and always return 200 with the generic message.
        try:
            user = User.objects.get(email=email)

            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

            try:
                send_mail(
                    subject='Password Reset Request',
                    message=f'Click the link to reset your password: {reset_url}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=True,
                )
            except Exception as exc:
                logger.exception(
                    'Password reset email failed for uid=%s: %s', user.pk, exc,
                )
        except User.DoesNotExist:
            pass

        return Response({
            'message': 'If an account with this email exists, a password reset link has been sent.'
        })


class PasswordResetConfirmView(APIView):
    """
    Confirm password reset with token and set new password.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uid = serializer.validated_data['uid']
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {'error': 'Invalid reset link'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'Invalid or expired reset link'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        # PR-4: use the shared helper to invalidate other sessions.
        _blacklist_user_tokens(user)

        return Response({'message': 'Password has been reset successfully'})


@method_decorator(ensure_csrf_cookie, name='post')
class CookieTokenRefreshView(TokenRefreshView):
    """
    Token refresh endpoint that re-issues HttpOnly cookies.

    PR-6: when the request arrives with the `ws_refresh` cookie (set
    on login), we read the refresh token from the cookie and use it to
    rotate. We then set the new access (and rotated refresh) cookies
    on the response. The JSON body still includes the new tokens so
    client code that reads the body keeps working.

    Clients that still send the refresh token in the JSON body also
    continue to work — we accept either channel.
    """
    # Allow this view to be reached without an Authorization header
    # (the default TokenRefreshView is permission_classes=()).
    authentication_classes = []

    def _get_refresh_data(self, request):
        """Return refresh token data for the serializer.

        - If request.data contains a truthy 'refresh' field, return request.data.
        - If request.data has no truthy 'refresh' and request.COOKIES contains
          'ws_refresh', return {'refresh': cookie_refresh}.
        - Otherwise return request.data (empty or with non-refresh fields).
        """
        try:
            if request.data.get('refresh'):
                return request.data
        except Exception:
            pass

        cookie_refresh = request.COOKIES.get(REFRESH_COOKIE)
        if cookie_refresh:
            return {'refresh': cookie_refresh}

        return request.data

    def post(self, request, *args, **kwargs):
        data = self._get_refresh_data(request)
        serializer = self.get_serializer(data=data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        if 'access' in response.data:
            set_auth_cookies(
                response,
                access=response.data.get('access'),
                refresh=response.data.get('refresh'),
            )

            if not settings.RETURN_TOKENS_IN_BODY:
                response.data.pop('access', None)
                response.data.pop('refresh', None)

        return response
