from rest_framework import permissions
from projects.models import ProjectMember

class CanManageTask(permissions.BasePermission):
    """
    Permission for task management.
    """
    
    def has_permission(self, request, view):
        # Anyone authenticated can view
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Only project members can create tasks
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        task = obj
        project = task.project
        
        # Read permissions - any project member
        if request.method in permissions.SAFE_METHODS:
            is_member = ProjectMember.objects.filter(
                project=project,
                user=request.user
            ).exists()
            return is_member or project.owner == request.user
        
        # Write permissions - task creator, assignee, project owner/manager, or admin
        return (
            task.created_by == request.user or
            task.assignee == request.user or
            project.owner == request.user or
            project.manager == request.user or
            request.user.role == 'ADMIN'
        )


class CanAssignTask(permissions.BasePermission):
    """
    Permission to assign tasks to users.
    """
    
    message = "Only project managers or task creator can assign tasks."
    
    def has_object_permission(self, request, view, obj):
        task = obj
        project = task.project
        
        return (
            task.created_by == request.user or
            project.owner == request.user or
            project.manager == request.user or
            request.user.role in ['ADMIN', 'PM', 'TL']
        )


class CanChangeTaskStatus(permissions.BasePermission):
    """
    Permission to change task status.
    """
    
    def has_object_permission(self, request, view, obj):
        task = obj
        project = task.project
        
        # Assignee can change status
        if task.assignee == request.user:
            return True
        
        # Project owner/manager can change status
        if project.owner == request.user or project.manager == request.user:
            return True
        
        # Admins can change status
        if request.user.role == 'ADMIN':
            return True
        
        return False


class IsTaskAssignee(permissions.BasePermission):
    """
    Permission to check if user is the task assignee.
    """
    
    message = "Only the task assignee can perform this action."
    
    def has_object_permission(self, request, view, obj):
        return obj.assignee == request.user