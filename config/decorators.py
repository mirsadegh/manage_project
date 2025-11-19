from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied

def require_role(*roles):
    """
    Decorator to require specific user roles.
    
    Usage:
        @action(detail=True, methods=['post'])
        @require_role('ADMIN', 'PM')
        def my_action(self, request, pk=None):
            # Only ADMIN and PM can access this
            ...
    
    Args:
        *roles: Variable number of role strings (e.g., 'ADMIN', 'PM', 'TL')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(self, request, *args, **kwargs):
            # Check authentication
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Superusers bypass role check
            if request.user.is_superuser:
                return view_func(self, request, *args, **kwargs)
            
            # Check if user has required role
            if request.user.role not in roles:
                return Response(
                    {
                        'error': f'This action requires one of these roles: {", ".join(roles)}',
                        'your_role': request.user.role
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
            
            return view_func(self, request, *args, **kwargs)
        return wrapper
    return decorator


def require_project_member(view_func):
    """
    Decorator to require user to be a project member.
    The view must have a 'slug' or 'pk' parameter that identifies the project.
    
    Usage:
        @action(detail=True, methods=['get'])
        @require_project_member
        def my_action(self, request, slug=None):
            # Only project members can access this
            ...
    """
    @wraps(view_func)
    def wrapper(self, request, *args, **kwargs):
        from projects.models import Project, ProjectMember
        
        # Get project identifier from URL
        project_slug = kwargs.get('slug')
        project_id = kwargs.get('pk')
        
        # Find the project
        try:
            if project_slug:
                project = Project.objects.get(slug=project_slug)
            elif project_id:
                project = Project.objects.get(id=project_id)
            else:
                return Response(
                    {'error': 'Project identifier not found in URL'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Superusers bypass member check
        if request.user.is_superuser:
            return view_func(self, request, *args, **kwargs)
        
        # Check if user is member, owner, or manager
        is_member = (
            project.owner == request.user or
            project.manager == request.user or
            ProjectMember.objects.filter(
                project=project,
                user=request.user
            ).exists()
        )
        
        if not is_member:
            return Response(
                {
                    'error': 'You are not a member of this project',
                    'project': project.name
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Add project to kwargs for use in view
        kwargs['project'] = project
        
        return view_func(self, request, *args, **kwargs)
    return wrapper


def require_project_manager(view_func):
    """
    Decorator to require user to be a project owner or manager.
    
    Usage:
        @action(detail=True, methods=['post'])
        @require_project_manager
        def my_action(self, request, slug=None):
            # Only project owner/manager can access this
            ...
    """
    @wraps(view_func)
    def wrapper(self, request, *args, **kwargs):
        from projects.models import Project
        
        # Get project identifier
        project_slug = kwargs.get('slug')
        project_id = kwargs.get('pk')
        
        # Find the project
        try:
            if project_slug:
                project = Project.objects.get(slug=project_slug)
            elif project_id:
                project = Project.objects.get(id=project_id)
            else:
                return Response(
                    {'error': 'Project identifier not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Project.DoesNotExist:
            return Response(
                {'error': 'Project not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Superusers and admins bypass check
        if request.user.is_superuser or request.user.role == 'ADMIN':
            kwargs['project'] = project
            return view_func(self, request, *args, **kwargs)
        
        # Check if user is owner or manager
        if project.owner != request.user and project.manager != request.user:
            return Response(
                {
                    'error': 'Only project owner or manager can perform this action',
                    'project': project.name
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        kwargs['project'] = project
        return view_func(self, request, *args, **kwargs)
    return wrapper


def require_task_assignee(view_func):
    """
    Decorator to require user to be the task assignee.
    
    Usage:
        @action(detail=True, methods=['post'])
        @require_task_assignee
        def complete_task(self, request, pk=None):
            # Only task assignee can complete
            ...
    """
    @wraps(view_func)
    def wrapper(self, request, *args, **kwargs):
        from tasks.models import Task
        
        task_id = kwargs.get('pk')
        
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return Response(
                {'error': 'Task not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Admins and project managers bypass check
        if (request.user.is_superuser or 
            request.user.role == 'ADMIN' or
            task.project.owner == request.user or
            task.project.manager == request.user):
            kwargs['task'] = task
            return view_func(self, request, *args, **kwargs)
        
        # Check if user is assignee
        if task.assignee != request.user:
            return Response(
                {
                    'error': 'Only the task assignee can perform this action',
                    'task': task.title,
                    'assignee': task.assignee.username if task.assignee else None
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        kwargs['task'] = task
        return view_func(self, request, *args, **kwargs)
    return wrapper