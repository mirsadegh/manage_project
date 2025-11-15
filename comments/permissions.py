from rest_framework import permissions

class IsCommentAuthorOrReadOnly(permissions.BasePermission):
    """
    Permission to only allow authors to edit/delete comments.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for anyone
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to author or admin
        return obj.author == request.user or request.user.role == 'ADMIN'