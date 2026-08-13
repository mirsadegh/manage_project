from rest_framework import permissions
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from projects.models import Project, ProjectMember


class CanAccessProjectComments(permissions.BasePermission):
    """
    Only project members can list/create comments on a project's content.
    """

    message = "You must be a project member to view or comment on this content."

    def _get_project(self, content_type, object_id):
        if not content_type or not object_id:
            return None
        try:
            ct = ContentType.objects.get(model=content_type.lower())
            model_class = ct.model_class()
            if model_class is None:
                return None
            content_object = model_class.objects.get(id=object_id)
        except (ContentType.DoesNotExist, Project.DoesNotExist):
            return None
        except Exception:
            return None

        if hasattr(content_object, 'owner') and hasattr(content_object, 'members'):
            return content_object
        return getattr(content_object, 'project', None)

    def _is_member(self, user, project):
        if project is None:
            return False
        if user.role in ['ADMIN', 'PM'] or user.is_superuser:
            return True
        return (
            project.owner == user or
            project.manager == user or
            ProjectMember.objects.filter(
                project=project, user=user, is_active=True
            ).exists()
        )

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS and view.action == 'list':
            project = self._get_project(
                request.query_params.get('content_type'),
                request.query_params.get('object_id'),
            )
            if project is not None:
                return self._is_member(request.user, project)
            # Without filter params, require the user to have access to
            # at least one project.
            return (
                request.user.role in ['ADMIN', 'PM'] or
                request.user.is_superuser or
                ProjectMember.objects.filter(
                    user=request.user, is_active=True
                ).exists() or
                Project.objects.filter(
                    Q(owner=request.user) | Q(manager=request.user)
                ).exists()
            )

        if view.action == 'create':
            project = self._get_project(
                request.data.get('content_type'),
                request.data.get('object_id'),
            )
            return self._is_member(request.user, project)

        return True


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