from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from .models import Project, ProjectMember
from .serializers import (
    ProjectSerializer,
    ProjectDetailSerializer,
    ProjectCreateSerializer,
    ProjectMemberSerializer
)

from .permissions import (
    CanManageProject,
    IsProjectOwnerOrManager,
    IsProjectMember,
    CanManageProjectMembers,
    CanModifyCompletedProject,
    CanDeleteProject
)

from config.pagination import ProjectPagination
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from config.mixins import ProjectAccessMixin
from config.throttling import ProjectCreationThrottle

from config.decorators import (
    require_project_manager,
    require_project_member,
    require_role
)
from notifications.utils import notify_project_members, broadcast_project_update
from django.utils import timezone

class ProjectViewSet(viewsets.ModelViewSet):
    """Project CRUD operations"""
    queryset = Project.objects.all()
    pagination_class = ProjectPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'is_active', 'owner', 'manager']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'due_date', 'priority']
    lookup_field = 'slug'
    
    
    def get_permissions(self):
        """Custom permissions based on action."""
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated, IsProjectMember]
        elif self.action == 'create':
            permission_classes = [CanManageProject]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [IsProjectOwnerOrManager, CanModifyCompletedProject]
        elif self.action == 'destroy':
            permission_classes = [CanDeleteProject]
        elif self.action in ['add_member', 'remove_member']:
            permission_classes = [CanManageProjectMembers]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ProjectCreateSerializer
        elif self.action == 'retrieve':
            return ProjectDetailSerializer
        return ProjectSerializer
    
    def get_queryset(self):
        """Filter projects user has access to"""
        user = self.request.user
        
        base_qs = Project.objects.all()
        
        # Annotate task stats for list pagination to avoid N+1
        if self.action == 'list':
            from tasks.models import Task
            base_qs = base_qs.annotate(
                total_tasks=Count('tasks'),
                completed_tasks=Count('tasks', filter=Q(tasks__status=Task.Status.COMPLETED))
            )
        
        # Superusers see all projects
        if user.is_superuser or getattr(user, 'role', None) == 'ADMIN':
            return base_qs
        
        # Users see projects they own, manage, or are members of
        if self.action in ['list', 'retrieve']:
            return base_qs.filter(
                Q(owner=user) |
                Q(manager=user) |
                Q(members__user=user) |
                Q(is_public=True)
            ).distinct()
            
        return base_qs
    
    
    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        slug = self.kwargs.get(lookup_url_kwarg)
        obj = get_object_or_404(Project.objects.all(), slug=slug)
        self.check_object_permissions(self.request, obj)
        return obj
   
    
    
    def perform_create(self, serializer):
        """Set current user as project owner"""
        project = serializer.save(owner=self.request.user)
        
        # Add owner as project member with OWNER role
        ProjectMember.objects.create(
            project=project,
            user=self.request.user,
            role=ProjectMember.Role.OWNER
        )
    
    @action(detail=True, methods=['get'])
    def members(self, request, slug=None):
        """Get project members"""
        project = self.get_object()
        members = project.members.all()
        serializer = ProjectMemberSerializer(members, many=True)
        return Response(serializer.data)
    
  
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, slug=None):
        """Add member to project"""
        project = self.get_object()
        serializer = ProjectMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Check if user is already a member
        user_id = serializer.validated_data['user_id']
        if ProjectMember.objects.filter(project=project, user_id=user_id).exists():
            return Response(
                {'error': 'User is already a member of this project'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        member = serializer.save(project=project)
          # Notify the new member
        notification_data = {
            'type': 'PROJECT_INVITE',
            'title': 'Added to Project',
            'message': f'You have been added to project "{project.name}"',
            'project_slug': project.slug
        }
        # Import here to avoid circular imports
        from notifications.utils import send_realtime_notification
        send_realtime_notification(member.user, notification_data)
        
        # Notify existing members
        notify_project_members(
            project.slug,
            f'{member.user.get_full_name()} joined the project',
            'info',
            self.request.user
        )
        
        # Broadcast to project watchers
        update_data = {
            'member_id': member.id,
            'member_name': member.user.get_full_name(),
               'member_role': member.role
        }
        broadcast_project_update(project.slug, update_data, self.request.user)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        
        
    @action(detail=True, methods=['delete'], url_path='remove_member/(?P<member_id>[^/.]+)')
    def remove_member(self, request, slug=None, member_id=None):
        """Remove member from project"""
        project = self.get_object()
        try:
            member = project.members.get(id=member_id)
            
            # Prevent removing the owner
            if member.user == project.owner:
                return Response(
                    {'error': 'Cannot remove project owner'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            member.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProjectMember.DoesNotExist:
            return Response(
                {'error': 'Member not found'},
                status=status.HTTP_404_NOT_FOUND
            )
            
            
    @action(detail=True, methods=['get'])
    def statistics(self, request, slug=None):
        """Get project statistics using optimized single query."""
        project = self.get_object()

        # Use optimized aggregation method (single query instead of 6+)
        task_stats = project.get_task_statistics()

        stats = {
            'total_tasks': task_stats['total'],
            'completed_tasks': task_stats['completed'],
            'in_progress_tasks': task_stats['in_progress'],
            'todo_tasks': task_stats['todo'],
            'blocked_tasks': task_stats['blocked'],
            'in_review_tasks': task_stats['in_review'],
            'overdue_tasks': task_stats['overdue'],
            'total_members': project.members.count(),
        }

        return Response(stats)
    
    
    @action(detail=True, methods=['post'])
    @require_role('ADMIN', 'PM')
    def archive(self, request, slug=None):
        """
        Archive a project - only admins and PMs can do this.
        The decorator automatically checks the user's role.
        """
        project = self.get_object()
        project.is_active = False
        project.save()
        
        return Response({
            'message': f'Project {project.name} archived successfully'
            })
        
    
    @action(detail=True, methods=['get'])
    @require_project_member
    def reports(self, request, slug=None, project=None):
        """
        Get project reports - only for project members.
        Note: 'project' is added to kwargs by the decorator.
        """
        # The decorator already verified membership and passed the project
        tasks = project.tasks.all()
        
        report_data = {
            'project_name': project.name,
            'total_tasks': tasks.count(),
            'completed': tasks.filter(status='COMPLETED').count(),
            'in_progress': tasks.filter(status='IN_PROGRESS').count(),
            'members': project.members.count(),
        }
        
        return Response(report_data)
    
    @action(detail=True, methods=['post'])
    @require_project_manager
    def close_project(self, request, slug=None, project=None):
        """
        Close a project - only owner or manager.
        The decorator passes the project object.
        """
        project.status = 'COMPLETED'
        project.is_active = False
        from django.utils import timezone
        project.completed_date = timezone.now().date()
        project.save()
        
        return Response({
            'message': f'Project "{project.name}" closed successfully',
            'completed_date': project.completed_date
        })
    
    @action(detail=True, methods=['delete'])
    @require_role('ADMIN')
    def force_delete(self, request, slug=None):
        """
        Force delete a project - only admins.
        This bypasses normal deletion rules.
        """
        project = self.get_object()
        project_name = project.name
        project.delete()
        
        return Response({
            'message': f'Project "{project_name}" permanently deleted'
        })    
    
    
    @action(detail=True, methods=['get'])
    def team_info(self, request, slug=None):
        """Get team information - requires project access"""
        project = self.get_object()
        
        # Check project access
        try:
            self.check_project_access(project, request.user)
        except PermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN 
                
                )
        
        # Get user's role in project
        user_role = self.get_user_role_in_project(project, request.user)
        
        # Get team members
        members = project.members.all()
        
        return Response({
            'your_role': user_role,
            'total_members': members.count(),
            'members': ProjectMemberSerializer(members, many=True).data
        }) 
        
        
    def get_throttles(self):
        """
        Apply different throttles based on action.
        """
        if self.action == 'create':
            throttle_classes = [ProjectCreationThrottle]
        else:
            throttle_classes = self.throttle_classes
        
        return [throttle() for throttle in throttle_classes]



    @action(detail=True, methods=['get'])
    def comments(self, request, slug=None):
        """Get all comments for this project"""
        project = self.get_object()
        comments = project.comments.filter(parent__isnull=True)  # Top-level only
        
        from comments.serializers import CommentSerializer
        serializer = CommentSerializer(comments, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_comment(self, request, slug=None):
        """Add a comment to this project"""
        project = self.get_object()
        
        from comments.serializers import CommentCreateSerializer
        serializer = CommentCreateSerializer(
            data={
                **request.data,
                'content_type': 'project',
                'object_id': project.id
            },
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        from comments.serializers import CommentSerializer
        return Response(
            CommentSerializer(comment, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def attachments(self, request, slug=None):
        """Get all attachments for this project"""
        project = self.get_object()
        attachments = project.attachments.all()
        
        from files.serializers import AttachmentSerializer
        serializer = AttachmentSerializer(
            attachments,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def upload_file(self, request, slug=None):
        """Upload a file to this project"""
        project = self.get_object()
        
        from files.serializers import AttachmentUploadSerializer
        serializer = AttachmentUploadSerializer(
            data={
                **request.data,
                'content_type': 'project',
                'object_id': project.id
            },
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        attachment = serializer.save()
        
        from files.serializers import AttachmentSerializer
        return Response(
            AttachmentSerializer(attachment, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )
                