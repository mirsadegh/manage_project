from rest_framework import viewsets, status, permissions
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
from django.db.models import Q



class ProjectViewSet(viewsets.ModelViewSet):
    """Project CRUD operations"""
    queryset = Project.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'priority', 'is_active', 'owner', 'manager']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'due_date', 'priority']
    lookup_field = 'slug'
    
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
        if user.is_superuser:
            return Project.objects.all()
        
        # Users see projects they own, manage, or are members of
        return Project.objects.filter(
            Q(owner=user) |
            Q(manager=user) |
            Q(members__user=user) |
            Q(is_public=True)
        ).distinct()
    
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
        serializer.save(project=project)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_path='remove_member/(?P<member_id>[^/.]+)')
    def remove_member(self, request, slug=None, member_id=None):
        """Remove member from project"""
        project = self.get_object()
        try:
            member = project.members.get(id=member_id)
            member.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProjectMember.DoesNotExist:
            return Response(
                {'error': 'Member not found'},
                status=status.HTTP_404_NOT_FOUND
            )

