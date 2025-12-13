# files/permissions.py

from rest_framework import permissions


class CanAccessAttachment(permissions.BasePermission):
    """
    Permission to check if user can access an attachment.
    Users can access attachments if they have access to the parent object.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admins can access everything
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return True
        
        # Uploader can always access their own files
        if obj.uploaded_by == request.user:
            return True
        
        # Check access to parent object
        content_object = obj.content_object
        
        if content_object.__class__.__name__ == 'Task':
            # Check if user has access to the task's project
            from projects.models import ProjectMember
            project = content_object.project
            
            return (
                project.owner == request.user or
                project.manager == request.user or
                content_object.assignee == request.user or
                content_object.created_by == request.user or
                ProjectMember.objects.filter(project=project, user=request.user).exists()
            )
        
        elif content_object.__class__.__name__ == 'Project':
            # Check if user is project member
            from projects.models import ProjectMember
            
            return (
                content_object.owner == request.user or
                content_object.manager == request.user or
                ProjectMember.objects.filter(project=content_object, user=request.user).exists() or
                content_object.is_public
            )
        
        elif content_object.__class__.__name__ == 'Comment':
            # Check if user has access to comment's parent object
            return self.has_object_permission(request, view, content_object.content_object)
        
        # Default: deny access
        return False