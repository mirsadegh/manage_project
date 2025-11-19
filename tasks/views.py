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

from .permissions import (
    CanManageTask,
    CanAssignTask,
    CanChangeTaskStatus,
    CanModifyBlockedTask,
    CanModifyCompletedTask,
    CanDeleteTask,
    CanReassignTask,
    IsProjectMember
)


from config.pagination import TaskPagination, StandardResultsSetPagination

from config.throttling import TaskCreationThrottle
from config.decorators import require_task_assignee, require_role


class TaskListViewSet(viewsets.ModelViewSet):
    """Task list CRUD operations"""
    queryset = TaskList.objects.all()
    serializer_class = TaskListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['project']


class TaskViewSet(viewsets.ModelViewSet):
    """Task CRUD operations"""
    queryset = Task.objects.all()
    pagination_class = TaskPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['project', 'task_list', 'status', 'priority', 'assignee']
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'due_date', 'priority', 'position']
   
   
    def get_permissions(self):
        """Custom permissions based on action."""
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'create':
            permission_classes = [CanManageTask]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [CanManageTask, CanModifyBlockedTask, CanModifyCompletedTask]
        elif self.action == 'destroy':
            permission_classes = [CanDeleteTask]
        elif self.action == 'assign':
            permission_classes = [CanReassignTask]
        elif self.action == 'change_status':
            permission_classes = [CanChangeTaskStatus]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TaskDetailSerializer
        return TaskSerializer
    
    def get_queryset(self):
        """Filter tasks based on user permissions"""
        user = self.request.user
        
        if user.is_superuser or user.role == 'ADMIN':
            return Task.objects.all()
        
        # Users see tasks from projects they have access to
        from projects.models import ProjectMember
        from django.db.models import Q
        
        return Task.objects.filter(
            Q(project__owner=user) |
            Q(project__manager=user) |
            Q(project__members__user=user) |
            Q(assignee=user) |
            Q(created_by=user)
        ).distinct()
    
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
            
            # Check if user is a project member
            from projects.models import ProjectMember
            if not ProjectMember.objects.filter(
                project=task.project,
                user=user
            ).exists() and task.project.owner != user:
                return Response(
                    {'error': 'User is not a member of this project'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
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
        
        # ابتدا تسک را بدون فیلتر queryset پیدا کن
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response(
                {'error': 'Task not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # حالا permission را چک کن (CanChangeTaskStatus)
        self.check_object_permissions(request, task)
        
        # بقیه کد...
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
        elif task.completed_at and new_status != Task.Status.COMPLETED:
            task.completed_at = None    
        
        task.save()
        serializer = self.get_serializer(task)
        return Response(serializer.data)
    
    
    @action(detail=False, methods=['get'])
    def my_tasks(self, request):
        """Get tasks assigned to current user"""
        tasks = self.get_queryset().filter(assignee=request.user)
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        
        page = self.paginate_queryset(tasks)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)


    @action(detail=False, methods=['get'])
    def all_tasks(self, request):
        """Get all tasks with limit/offset pagination"""
        from config.pagination import CustomLimitOffsetPagination
        
        tasks = self.get_queryset()
        paginator = CustomLimitOffsetPagination()
        result_page = paginator.paginate_queryset(tasks, request)
        serializer = self.get_serializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    def get_throttles(self):
        """
        Apply task creation throttle.
        """
        if self.action == 'create':
            throttle_classes = [TaskCreationThrottle]
        else:
            throttle_classes = self.throttle_classes
        
        return [throttle() for throttle in throttle_classes]
    


    @action(detail=True, methods=['post'])
    @require_task_assignee
    def mark_complete(self, request, pk=None, task=None):
        """
        Mark task as complete - only assignee can do this.
        The decorator passes the task object.
        """
        from django.utils import timezone
        
        task.status = 'COMPLETED'
        task.completed_at = timezone.now()
        task.actual_hours = request.data.get('actual_hours', task.actual_hours)
        task.save()
        
        serializer = self.get_serializer(task)
        return Response({
            'message': 'Task marked as complete',
            'task': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    @require_task_assignee
    def log_time(self, request, pk=None, task=None):
        """
        Log time spent on task - only assignee.
        """
        hours = request.data.get('hours')
        
        if not hours:
            return Response(
                {'error': 'Hours required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task.actual_hours = (task.actual_hours or 0) + float(hours)
        task.save()
        
        return Response({
            'message': f'Logged {hours} hours',
            'total_hours': task.actual_hours
        })
    
    @action(detail=False, methods=['post'])
    @require_role('ADMIN', 'PM', 'TL')
    def bulk_assign(self, request):
        """
        Bulk assign tasks to users - only managers.
        """
        task_ids = request.data.get('task_ids', [])
        assignee_id = request.data.get('assignee_id')
        
        if not task_ids or not assignee_id:
            return Response(
                {'error': 'task_ids and assignee_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from accounts.models import CustomUser
        
        try:
            assignee = CustomUser.objects.get(id=assignee_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        tasks = Task.objects.filter(id__in=task_ids)
        updated_count = tasks.update(assignee=assignee)
        
        return Response({
            'message': f'Assigned {updated_count} tasks to {assignee.username}',
            'updated_tasks': updated_count
        })       
    
    
    
    
class TaskLabelViewSet(viewsets.ModelViewSet):
    """Task label CRUD operations"""
    queryset = TaskLabel.objects.all()
    serializer_class = TaskLabelSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['project']
    
    
    
    