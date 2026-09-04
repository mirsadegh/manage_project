from rest_framework import viewsets, generics, status, permissions
from rest_framework.throttling import ScopedRateThrottle
import logging
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from .models import CustomUser
from .serializers import (
    UserSerializer, UserDetailSerializer, UserRegistrationSerializer,
    ChangePasswordSerializer, PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer, LogoutSerializer,
    CustomTokenObtainPairSerializer, UserPublicSerializer,
)
from .permissions import IsAdminOrManager, IsAdmin
from config.pagination import StandardResultsSetPagination
from config.throttling import LoginRateThrottle
from config.auth_cookies import set_auth_cookies, clear_auth_cookies
User = get_user_model()
logger = logging.getLogger('accounts')


def _blacklist_user_tokens(user):
    """PR-4: helper — blacklist all outstanding refresh tokens for a user.

    Called on password change, password reset, and account deactivation
    so other-device sessions are forced to re-authenticate. Errors on
    individual rows are swallowed (best-effort) so a single bad row
    cannot block the call.
    """
    for token in OutstandingToken.objects.filter(user=user):
        try:
            BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            pass


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
        # WebSocket upgrade can authenticate without ?token=. The JSON
        # body is preserved for backward compatibility with existing
        # tools and tests.
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
        return response


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
        return response


class LogoutView(APIView):
    """
    Logout endpoint that blacklists the refresh token.
    Supports both single token logout and logout from all devices.

    PR-6: also clears the auth cookies so the browser drops them.
    This complements the existing JWT blacklisting; the
    force_disconnect signal (PR-3 Fix #1) takes care of any open
    WebSocket connections.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data.get('refresh')
        logout_all = serializer.validated_data.get('logout_all', False)

        if logout_all:
            # PR-4: use the shared helper instead of inlining the loop.
            _blacklist_user_tokens(request.user)
            response = Response({'message': 'Successfully logged out from all devices'})
            clear_auth_cookies(response)
            return response

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
                response = Response({'message': 'Successfully logged out'})
                clear_auth_cookies(response)
                return response
            except TokenError:
                return Response(
                    {'error': 'Invalid or expired token'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(
            {'error': 'Refresh token is required'},
            status=status.HTTP_400_BAD_REQUEST
        )


class PasswordResetRequestView(APIView):
    """
    Request a password reset email.
    """
    permission_classes = [permissions.AllowAny]
    # PR-4 M-2: attach ScopedRateThrottle so the existing
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


class UserViewSet(viewsets.ModelViewSet):
    """User CRUD operations."""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['role', 'department', 'is_available']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'job_title']
    ordering_fields = ['date_joined', 'username']
    ordering = ['-date_joined']

    def get_permissions(self):
        """Custom permissions based on action.

        PR-4: list/retrieve now require admin/manager role. Reads from
        the role context still work because the WebSocket and other
        in-process consumers are unaffected; this only changes the
        HTTP API.
        """
        permission_map = {
            'list': [IsAdminOrManager],
            'retrieve': [IsAdminOrManager],
            'me': [permissions.IsAuthenticated],
            'change_password': [permissions.IsAuthenticated],
            'deactivate_account': [permissions.IsAuthenticated],
            'create': [IsAdmin],
            'update': [IsAdmin],
            'partial_update': [IsAdmin],
            'destroy': [IsAdmin],
            'activate': [IsAdmin],
        }
        permission_classes = permission_map.get(self.action, [permissions.IsAuthenticated])
        return [permission() for permission in permission_classes]

    def _user_can_see_private(self, request, obj=None):
        """PR-4: helper to decide if the requester can see the full
        UserDetailSerializer (email/phone/bio/last_login). True for
        admin/manager, or the user viewing their own record.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role in {
            CustomUser.Role.ADMIN,
            CustomUser.Role.PROJECT_MANAGER,
            CustomUser.Role.TEAM_LEAD,
        }:
            return True
        # Owner can always see their own full profile.
        if obj is not None and obj == request.user:
            return True
        if obj is None:
            # No specific obj (e.g. /me/): always allow.
            return True
        return False

    def get_serializer_class(self):
        # PR-4: list and retrieve return the public serializer to
        # non-privileged callers; admin/manager get the full
        # UserDetailSerializer. The /me/ endpoint always returns
        # UserDetailSerializer (caller is the owner).
        if self.action == 'me':
            return UserDetailSerializer
        if self.action in ('list', 'retrieve'):
            request = self.request
            obj = None
            if self.action == 'retrieve':
                try:
                    obj = self.get_object()
                except Exception:
                    obj = None
            if self._user_can_see_private(request, obj):
                return UserDetailSerializer
            return UserPublicSerializer
        return UserSerializer

    @action(detail=False, methods=['get', 'put', 'patch'])
    def me(self, request):
        """Get or update current user profile."""
        if request.method == 'GET':
            serializer = UserDetailSerializer(request.user)
            return Response(serializer.data)

        serializer = UserDetailSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change user password."""
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'old_password': ['Wrong password.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        # PR-4 Fix M-5: blacklist other sessions before changing the
        # password, so other devices must re-authenticate.
        _blacklist_user_tokens(user)

        user.set_password(serializer.validated_data['new_password'])
        user.save()

        return Response({'message': 'Password updated successfully'})

    @action(detail=False, methods=['post'])
    def deactivate_account(self, request):
        """Allow user to deactivate their own account."""
        password = request.data.get('password')

        if not password:
            return Response(
                {'password': ['Password is required to deactivate account.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not request.user.check_password(password):
            return Response(
                {'password': ['Wrong password.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        request.user.is_active = False
        request.user.save()

        # PR-4: use the shared helper instead of inlining.
        _blacklist_user_tokens(request.user)

        return Response({'message': 'Account deactivated successfully'})

    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def activate(self, request, pk=None):
        """Admin endpoint to activate a user account."""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({'message': f'User {user.username} activated successfully'})


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

    def post(self, request, *args, **kwargs):
        # If the JSON body has no `refresh`, fall back to the cookie.
        # We do this by wrapping the request in a fresh Request whose
        # body contains the cookie-derived refresh token. This avoids
        # mutating the cached `_full_data` on the original request,
        # which Django REST Framework may have already parsed.
        from rest_framework.request import Request
        from rest_framework.parsers import JSONParser

        body_refresh = None
        try:
            body_refresh = request.data.get('refresh') if hasattr(request.data, 'get') else None
        except Exception:
            body_refresh = None

        if not body_refresh:
            cookie_refresh = request.COOKIES.get('ws_refresh')
            if cookie_refresh:
                # Rebuild the request body with the cookie value.
                # TokenRefreshView's serializer reads `refresh` from
                # validated input; this gives it the cookie-derived
                # value while leaving the original request untouched.
                rebuilt = Request(
                    request._request,
                    parsers=[JSONParser()],
                )
                rebuilt._data = {'refresh': cookie_refresh}
                rebuilt._files = {}
                rebuilt._full_data = {'refresh': cookie_refresh}
                request = rebuilt

        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK and 'access' in response.data:
            set_auth_cookies(
                response,
                access=response.data.get('access'),
                refresh=response.data.get('refresh'),
            )
        return response
