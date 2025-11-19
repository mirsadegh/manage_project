from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
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
from django.db.models import Q
from django.shortcuts import get_object_or_404
from config.mixins import ProjectAccessMixin
from config.throttling import ProjectCreationThrottle

from config.decorators import (
    require_project_manager,
    require_project_member,
    require_role
)

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
        
        # Superusers see all projects
        if user.is_superuser  or getattr(user, 'role', None) == 'ADMIN':
            return Project.objects.all()
        
        
        
        # Users see projects they own, manage, or are members of
        if self.action in ['list', 'retrieve']:
            return Project.objects.filter(
                Q(owner=user) |
                Q(manager=user) |
                Q(members__user=user) |
                Q(is_public=True)
            ).distinct()
            
        return Project.objects.all()    
    
    
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
        
        serializer.save(project=project)
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
        """Get project statistics"""
        project = self.get_object()
        
        stats = {
            'total_tasks': project.tasks.count(),
            'completed_tasks': project.tasks.filter(status='COMPLETED').count(),
            'in_progress_tasks': project.tasks.filter(status='IN_PROGRESS').count(),
            'todo_tasks': project.tasks.filter(status='TODO').count(),
            'blocked_tasks': project.tasks.filter(status='BLOCKED').count(),
            'overdue_tasks': project.tasks.filter(
                due_date__lt=models.functions.Now(),
                status__in=['TODO', 'IN_PROGRESS']
            ).count(),
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
        
        
            
