"""User CRUD viewset for the accounts app."""
from rest_framework import viewsets, status, permissions
from rest_framework.exceptions import (
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import Http404

from ..models import CustomUser
from ..serializers import (
    UserSerializer, UserDetailSerializer, UserSelfUpdateSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer, UserPublicSerializer,
)
from ..permissions import IsAdminOrManager, IsAdmin
from config.pagination import StandardResultsSetPagination
from .common import _blacklist_user_tokens


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
            # OPTIONS (metadata) keeps the plain authenticated check.
            'metadata': [permissions.IsAuthenticated],
            'create': [IsAdmin],
            'update': [IsAdmin],
            'partial_update': [IsAdmin],
            'destroy': [IsAdmin],
            'activate': [IsAdmin],
        }
        # Deny-by-default: any action not listed above (e.g. a future
        # action that forgot to register itself) falls back to IsAdmin
        # instead of the old IsAuthenticated fallback, which granted
        # every authenticated user access.
        permission_classes = permission_map.get(self.action, [IsAdmin])
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
        # Non-privileged requester with no owner relationship: the
        # caller must NOT see private data. (The previous `obj is None`
        # early-return-True was fail-open and is deliberately removed.)
        return False

    def get_object(self):
        """Cache the resolved object so retrieve's serializer selection
        and the mixin's own lookup issue a single query.
        """
        if getattr(self, '_object_cache', None) is not None:
            return self._object_cache
        obj = super().get_object()
        self._object_cache = obj
        return obj

    def get_serializer_class(self):
        # PR-4: list and retrieve return the public serializer to
        # non-privileged callers; admin/manager get the full
        # UserDetailSerializer. The /me/ endpoint always returns
        # UserDetailSerializer (caller is the owner).
        if self.action == 'me':
            return UserDetailSerializer
        if self.action in ('list', 'retrieve'):
            request = self.request
            obj = getattr(self, '_object_cache', None)
            if obj is None and self.action == 'retrieve':
                # Fail closed: a missing object or a permission denial
                # must never upgrade the response to UserDetailSerializer.
                try:
                    obj = self.get_object()
                except (Http404, PermissionDenied, NotAuthenticated):
                    return UserPublicSerializer
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

        serializer = UserSelfUpdateSerializer(
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

        # PR-4 Fix M-5: blacklist other sessions only AFTER the new
        # password is persisted, so a failing save never leaves the
        # user's other devices logged out of a half-changed account.
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        _blacklist_user_tokens(user)

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
        if self._is_last_active_admin(request.user):
            return Response(
                {'detail': [
                    'You are the last remaining active admin and cannot '
                    'deactivate your account. Promote another admin first.'
                ]},
                status=status.HTTP_400_BAD_REQUEST
            )

        request.user.is_active = False
        request.user.save()

        # PR-4: use the shared helper instead of inlining.
        _blacklist_user_tokens(request.user)

        return Response({'message': 'Account deactivated successfully'})

    @staticmethod
    def _is_last_active_admin(user):
        """True if ``user`` is an active admin and the only one left.

        Prevents deleting, demoting or deactivating the last active
        admin, which would lock everybody out of the admin surface
        (there is no other way to grant ADMIN via the API).
        """
        if user.role != CustomUser.Role.ADMIN or not user.is_active:
            return False
        return not CustomUser.objects.filter(
            role=CustomUser.Role.ADMIN,
            is_active=True,
        ).exclude(pk=user.pk).exists()

    def perform_destroy(self, instance):
        """Guard the hard delete before it runs.

        - an admin cannot delete their own account through this
          endpoint (use deactivate_account for self-service);
        - the last active admin cannot be deleted.
        The delete itself stays a hard delete (unchanged semantics).
        """
        if instance == self.request.user:
            raise ValidationError({
                'detail': (
                    'You cannot delete your own account through this '
                    'endpoint. Use the deactivate-account endpoint '
                    'instead.'
                )
            })
        # Unreachable over HTTP: the self-delete check above fires
        # first, because reaching this branch requires a caller who is
        # not the instance being deleted. Covered by tests that call
        # perform_destroy directly.
        if self._is_last_active_admin(instance):
            raise ValidationError({
                'detail': (
                    'Cannot delete the last remaining active admin. '
                    'Promote another admin first.'
                )
            })
        super().perform_destroy(instance)

    def perform_update(self, serializer):
        """Refuse to demote or deactivate the last remaining active admin.

        ``is_active`` is not a serializer field today, so the guard is
        defense-in-depth: it also pins the invariant for a future
        serializer that exposes it.
        """
        instance = serializer.instance
        if self._is_last_active_admin(instance):
            new_role = serializer.validated_data.get('role')
            if new_role is not None and new_role != CustomUser.Role.ADMIN:
                raise ValidationError({
                    'detail': (
                        'Cannot demote the last remaining active admin. '
                        'Promote another admin first.'
                    )
                })
            if serializer.validated_data.get('is_active') is False:
                raise ValidationError({
                    'detail': (
                        'Cannot deactivate the last remaining active '
                        'admin. Promote another admin first.'
                    )
                })
        super().perform_update(serializer)

    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def activate(self, request, pk=None):
        """Admin endpoint to activate a user account."""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({'message': f'User {user.username} activated successfully'})
