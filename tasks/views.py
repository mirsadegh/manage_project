from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Task, TaskList, TaskLabel
from .serializers import (
    TaskSerializer,
    TaskDetailSerializer,
    TaskListSerializer,
    TaskLabelSerializer
)


class TaskListViewSet(viewsets.ModelViewSet):
    """Task list CRUD operations"""
    queryset = TaskList.objects.all()
    serializer_class = TaskListSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['project']


class TaskViewSet(viewsets.ModelViewSet):
    """Task CRUD operations"""
    queryset = Task.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['project', 'task_list', 'status', 'priority', 'assignee']
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'due_date', 'priority', 'position']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TaskDetailSerializer
        return TaskSerializer
    
    def perform_create(self, serializer):
        """Set current user as task creator"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign task to user"""
        task = self.get_object()
        user_id = request.data.get('user_id')
        
        try:
            from accounts.models import CustomUser
            user = CustomUser.objects.get(id=user_id)
            task.assignee = user
            task.save()
            
            serializer = self.get_serializer(task)
            return Response(serializer.data)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        """Change task status"""
        task = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(Task.Status.choices):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task.status = new_status
        
        # Set completed_at when marking as completed
        if new_status == Task.Status.COMPLETED:
            from django.utils import timezone
            task.completed_at = timezone.now()
        
        task.save()
        serializer = self.get_serializer(task)
        return Response(serializer.data)


class TaskLabelViewSet(viewsets.ModelViewSet):
    """Task label CRUD operations"""
    queryset = TaskLabel.objects.all()
    serializer_class = TaskLabelSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['project']
    
    
    
    