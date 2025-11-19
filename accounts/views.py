from rest_framework import viewsets, generics, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from .models import CustomUser
from .serializers import (
    UserSerializer,
    UserDetailSerializer,
    UserRegistrationSerializer,
    ChangePasswordSerializer
)

from .permissions import IsOwnerOrReadOnly, IsAdminOrManager, IsAdmin
from config.pagination import StandardResultsSetPagination

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from config.throttling import LoginRateThrottle




User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """User registration endpoint"""
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegistrationSerializer


class UserViewSet(viewsets.ModelViewSet):
    """User CRUD operations"""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['role', 'department', 'is_available']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'job_title']
    ordering_fields = ['date_joined', 'username']
    
    def get_permissions(self):
        """
        Custom permissions based on action.
        """
        if self.action == 'list':
            # Anyone authenticated can list users
            permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'retrieve':
            # Anyone authenticated can view user details
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['me', 'change_password']:
            # User can update their own profile
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Only admins can create/update/delete users
            permission_classes = [IsAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UserDetailSerializer
        return UserSerializer
    
    @action(detail=False, methods=['get', 'put', 'patch'])
    def me(self, request):
        """Get or update current user profile"""
        if request.method == 'GET':
            serializer = UserDetailSerializer(request.user)
            return Response(serializer.data)
        else:
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
        """Change user password"""
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'old_password': ['Wrong password.']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        return Response({'message': 'Password updated successfully'})  
    
 

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer to add extra user data to token response.
    """
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add custom claims
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'role': self.user.role,
            'full_name': self.user.get_full_name(),
        }
        
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom login view with rate limiting.
    """
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]
 
 
 
 