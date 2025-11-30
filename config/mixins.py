from rest_framework.exceptions import PermissionDenied
from projects.models import ProjectMember

class ProjectAccessMixin:
    """
    Mixin to check project access permissions.
    """
    
    def check_project_access(self, project, user, required_role=None):
        """
        Check if user has access to project.
        
        Args:
            project: Project instance
            user: User instance
            required_role: Required role (e.g., 'OWNER', 'MANAGER')
        
        Returns:
            bool: True if user has access
        
        Raises:
            PermissionDenied: If user doesn't have access
        """
        # Admins have access to everything
        if user.role == 'ADMIN' or user.is_superuser:
            return True
        
        # Check if user is owner or manager
        if project.owner == user or project.manager == user:
            return True
        
        # Check if user is a member
        try:
            membership = ProjectMember.objects.get(project=project, user=user)
            
            # If specific role is required, check it
            if required_role:
                if membership.role == required_role:
                    return True
                raise PermissionDenied(
                    f"You need {required_role} role to perform this action."
                )
            
            return True
        except ProjectMember.DoesNotExist:
            # Check if project is public (for read-only access)
            if project.is_public:
                return True
            
            raise PermissionDenied("You don't have access to this project.")
    
    def get_user_role_in_project(self, project, user):
        """
        Get user's role in a project.
        
        Args:
            project: Project instance
            user: User instance
        
        Returns:
            str: Role name ('OWNER', 'MANAGER', 'MEMBER', 'VIEWER') or None
        """
        if user.is_superuser or user.role == 'ADMIN':
            return 'ADMIN'
        
        if project.owner == user:
            return 'OWNER'
        
        if project.manager == user:
            return 'MANAGER'
        
        try:
            membership = ProjectMember.objects.get(project=project, user=user)
            return membership.role
        except ProjectMember.DoesNotExist:
            if project.is_public:
                return 'VIEWER'
            return None
    
    def is_project_manager(self, project, user):
        """
        Check if user can manage the project.
        
        Returns:
            bool: True if user is owner, manager, or admin
        """
        return (
            user.is_superuser or
            user.role == 'ADMIN' or
            project.owner == user or
            project.manager == user
        )


