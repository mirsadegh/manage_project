from rest_framework import viewsets, generics, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
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
    UserSerializer,
    UserDetailSerializer,
    UserRegistrationSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from .permissions import IsOwnerOrReadOnly, IsAdminOrManager, IsAdmin
from config.pagination import StandardResultsSetPagination
from config.throttling import LoginRateThrottle

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """User registration endpoint."""
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegistrationSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate tokens for immediate login after registration
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            },
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom login view with rate limiting.
    The throttle is applied at the view level to ensure it works correctly.
    """
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]
    
    def post(self, request, *args, **kwargs):
        # Throttling is automatically applied by DRF before this method runs
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """
    Logout endpoint that blacklists the refresh token.
    Supports both single token logout and logout from all devices.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        refresh_token = serializer.validated_data.get('refresh')
        logout_all = serializer.validated_data.get('logout_all', False)
        
        if logout_all:
            # Blacklist all tokens for this user
            tokens = OutstandingToken.objects.filter(user=request.user)
            for token in tokens:
                try:
                    BlacklistedToken.objects.get_or_create(token=token)
                except Exception:
                    pass
            return Response({'message': 'Successfully logged out from all devices'})
        
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
                return Response({'message': 'Successfully logged out'})
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
    throttle_scope = 'password_reset'
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        
        try:
            user = User.objects.get(email=email)
            
            # Generate reset token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build reset URL (adjust based on your frontend)
            reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            
            # Send email
            send_mail(
                subject='Password Reset Request',
                message=f'Click the link to reset your password: {reset_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
        except User.DoesNotExist:
            # Don't reveal whether email exists
            pass
        
        # Always return success to prevent email enumeration
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
        
        # Blacklist all existing tokens for security
        tokens = OutstandingToken.objects.filter(user=user)
        for outstanding_token in tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=outstanding_token)
            except Exception:
                pass
        
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
        """Custom permissions based on action."""
        permission_map = {
            'list': [permissions.IsAuthenticated],
            'retrieve': [permissions.IsAuthenticated],
            'me': [permissions.IsAuthenticated],
            'change_password': [permissions.IsAuthenticated],
            'deactivate_account': [permissions.IsAuthenticated],
            'create': [IsAdmin],
            'update': [IsAdmin],
            'partial_update': [IsAdmin],
            'destroy': [IsAdmin],
        }
        permission_classes = permission_map.get(self.action, [permissions.IsAuthenticated])
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action in ['retrieve', 'me']:
            return UserDetailSerializer
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
        
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Optionally blacklist all tokens except current one
        # This forces re-login on other devices
        
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
        
        # Blacklist all tokens
        tokens = OutstandingToken.objects.filter(user=request.user)
        for token in tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                pass
        
        return Response({'message': 'Account deactivated successfully'})
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def activate(self, request, pk=None):
        """Admin endpoint to activate a user account."""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({'message': f'User {user.username} activated successfully'})
 