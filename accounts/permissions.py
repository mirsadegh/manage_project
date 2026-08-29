from rest_framework import permissions
from .models import CustomUser


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner
        return obj == request.user


class IsAdminOrManager(permissions.BasePermission):
    """
    Permission for admin and manager roles (ADMIN, PROJECT_MANAGER, TEAM_LEAD).
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role in {
                CustomUser.Role.ADMIN,
                CustomUser.Role.PROJECT_MANAGER,
                CustomUser.Role.TEAM_LEAD,
            }
        )


class IsAdmin(permissions.BasePermission):
    """
    Permission for admin role only.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role == CustomUser.Role.ADMIN
        )
