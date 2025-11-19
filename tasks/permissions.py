from rest_framework import permissions
from projects.models import ProjectMember


class CanManageTask(permissions.BasePermission):
    """
    Permission برای ایجاد و ویرایش تسک
    فقط اعضای پروژه می‌توانند تسک بسازند
    """
    
    def has_permission(self, request, view):
        # برای action های create باید عضو پروژه باشد
        if view.action == 'create':
            project_id = request.data.get('project')
            if not project_id:
                return False
            
            try:
                from projects.models import Project, ProjectMember
                project = Project.objects.get(id=project_id)
                
                # چک کنیم کاربر عضو پروژه است
                is_member = (
                    project.owner == request.user or
                    project.manager == request.user or
                    ProjectMember.objects.filter(
                        project=project, 
                        user=request.user
                    ).exists()
                )
                
                return is_member
                
            except Project.DoesNotExist:
                return False
        
        return True  # برای سایر actionها در has_object_permission چک می‌شود
    
    def has_object_permission(self, request, view, obj):
        """
        برای update/partial_update
        """
        from projects.models import ProjectMember
        
        project = obj.project
        user = request.user
        
        # Admin و PM همه جا دسترسی دارند
        if user.role in ['ADMIN', 'PM']:
            return True
        
        # Team Lead اگر عضو پروژه باشد
        if user.role == 'TL':
            return ProjectMember.objects.filter(
                project=project, 
                user=user
            ).exists()
        
        # Owner و Manager پروژه
        if project.owner == user or project.manager == user:
            return True
        
        # سازنده تسک
        if obj.created_by == user:
            return True
        
        return False


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
    
  
  


class IsProjectMember(permissions.BasePermission):
    """
    کاربر باید عضو پروژه باشد
    """
    def has_permission(self, request, view):
        project_id = request.data.get('project')
        if not project_id:
            return False
        
        from projects.models import Project
        try:
            project = Project.objects.get(id=project_id)
            return project.members.filter(id=request.user.id).exists()
        except Project.DoesNotExist:
            return False

    def has_object_permission(self, request, view, obj):
        return obj.project.members.filter(id=request.user.id).exists()    
    
    
    
class CanModifyBlockedTask(permissions.BasePermission):
    """
    Permission to handle blocked tasks.
    Regular users can't modify blocked tasks.
    """
    
    message = "This task is blocked. Resolve blockers first or contact project manager."
    
    def has_object_permission(self, request, view, obj):
        task = obj
        
        # Allow read operations
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # If task is blocked, only PM or admin can modify
        if task.status == 'BLOCKED':
            return (
                request.user.role in ['ADMIN', 'PM'] or
                request.user.is_superuser or
                task.project.owner == request.user or
                task.project.manager == request.user
            )
        
        return True


class CanModifyBlockedTask(permissions.BasePermission):
    """
    Permission to handle blocked tasks.
    Regular users can't modify blocked tasks.
    """
    
    message = "This task is blocked. Resolve blockers first or contact project manager."
    
    def has_object_permission(self, request, view, obj):
        task = obj
        
        # Allow read operations
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # If task is blocked, only PM or admin can modify
        if task.status == 'BLOCKED':
            return (
                request.user.role in ['ADMIN', 'PM'] or
                request.user.is_superuser or
                task.project.owner == request.user or
                task.project.manager == request.user
            )
        
        return True

class CanModifyCompletedTask(permissions.BasePermission):
    """
    Permission to prevent modifying completed tasks.
    """
    
    message = "Cannot modify completed tasks. Contact project manager to reopen if needed."
    
    def has_object_permission(self, request, view, obj):
        task = obj
        
        # Allow read operations
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # If task is completed, only PM or admin can modify
        if task.status == 'COMPLETED':
            return (
                request.user.role in ['ADMIN', 'PM'] or
                request.user.is_superuser or
                task.project.owner == request.user or
                task.project.manager == request.user
                )   
    
        return True
    
class CanDeleteTask(permissions.BasePermission):
    """
    Permission for task deletion.
    Only task creator, project manager, or admin can delete.
    """ 
    def has_object_permission(self, request, view, obj):
        task = obj
        
        # Only DELETE method
        if request.method != 'DELETE':
            return True
        
        # Check if user can delete
        can_delete = (
            task.created_by == request.user or
            task.project.owner == request.user or
            task.project.manager == request.user or
            request.user.role == 'ADMIN' or
            request.user.is_superuser
        )
        
        if not can_delete:
            self.message = "Only task creator, project manager, or admin can delete tasks."
            return False
        
        # Prevent deleting tasks with subtasks
        if task.subtasks.exists():
            self.message = "Cannot delete task with subtasks. Delete or reassign subtasks first."
            return False
        
        return True   


class CanReassignTask(permissions.BasePermission):
    """
    Permission for reassigning tasks.
    Only project managers can reassign tasks.
    """
    message = "Only project managers can reassign tasks."

    def has_permission(self, request, view):
        # This is for the 'assign' action
        if view.action == 'assign':
            return request.user.is_authenticated
        return True

    def has_object_permission(self, request, view, obj):
        task = obj
        
        return (
            request.user.role in ['ADMIN', 'PM', 'TL'] or
            request.user.is_superuser or
            task.project.owner == request.user or
            task.project.manager == request.user or
            task.created_by == request.user
        )        