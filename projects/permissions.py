from rest_framework import permissions
from .models import ProjectMember

class IsProjectOwnerOrManager(permissions.BasePermission):
    """
    Permission to check if user is project owner or manager.
    """
    
    message = "You must be the project owner or manager to perform this action."
    
    def has_object_permission(self, request, view, obj):
        # Get the project object
        project = obj if hasattr(obj, 'owner') else obj.project
        
        # Owners and managers have full access
        return project.owner == request.user or project.manager == request.user


class IsProjectMember(permissions.BasePermission):
    """
    Permission to check if user is a project member.
    """
    
    message = "You must be a project member to access this resource."
    
    def has_object_permission(self, request, view, obj):
        # Get the project object
        project = obj if hasattr(obj, 'owner') else obj.project
        
        # Check if user is a member
        is_member = ProjectMember.objects.filter(
            project=project,
            user=request.user
        ).exists()
        
        return is_member or project.owner == request.user or project.is_public


class CanManageProject(permissions.BasePermission):
    """
    Permission for project management actions (create, update, delete).
    """
    
    def has_permission(self, request, view):
        # Anyone authenticated can view
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Only managers and admins can create projects
        return request.user and request.user.is_authenticated and \
               request.user.role in ['ADMIN', 'PM', 'TL']
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            return IsProjectMember().has_object_permission(request, view, obj)
        
        # Write permissions - owner, manager, or admin
        return obj.owner == request.user or \
               obj.manager == request.user or \
               request.user.role == 'ADMIN'


class CanManageProjectMembers(permissions.BasePermission):
    """
    Permission to add/remove project members.
    """
    
    message = "Only project owner or manager can manage members."
    
    def has_object_permission(self, request, view, obj):
        project = obj if hasattr(obj, 'owner') else obj.project
        
        return project.owner == request.user or \
               project.manager == request.user or \
               request.user.role == 'ADMIN'




















