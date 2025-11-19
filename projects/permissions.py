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




class CanModifyCompletedProject(permissions.BasePermission):
    """
    Permission to prevent modifying completed projects.
    Only admins can modify completed projects.
    """
    
    message = "Cannot modify completed projects. Contact an administrator if changes are needed."
    
    def has_object_permission(self, request, view, obj):
        project = obj if hasattr(obj, 'status') else obj.project
        
        # Allow read operations
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # If project is completed, only admin can modify
        if project.status == 'COMPLETED':
            return request.user.role == 'ADMIN' or request.user.is_superuser
        
        # If project is cancelled, only admin can modify
        if project.status == 'CANCELLED':
            return request.user.role == 'ADMIN' or request.user.is_superuser
        
        return True


class CanDeleteProject(permissions.BasePermission):
    """
    Permission for project deletion.
    Only owner or admin can delete, and only if no tasks exist.
    """
    
    def has_object_permission(self, request, view, obj):
        project = obj
        
        # Only DELETE method
        if request.method != 'DELETE':
            return True
        
        # Check if user is owner or admin
        if not (project.owner == request.user or 
                request.user.role == 'ADMIN' or 
                request.user.is_superuser):
            self.message = "Only project owner or admin can delete projects."
            return False
        
        # Check if project has tasks
        if project.tasks.exists():
            self.message = "Cannot delete project with existing tasks. Delete or move tasks first."
            return False
        
        return True















