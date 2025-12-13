from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from notifications.utils import send_realtime_notification, broadcast_project_update
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
    """
    Task CRUD operations

    This class-based view provides functionality for creating, reading, updating, and deleting tasks.
    It utilizes Django Rest Framework's ModelViewSet to handle these operations.

    Attributes:
        queryset (Task.objects.all()): A queryset containing all tasks.
        pagination_class (TaskPagination): The pagination class used for paginating tasks.
        filter_backends ([DjangoFilterBackend]): A list of filter backends used for filtering tasks.
        filterset_fields (['project', 'task_list', 'status', 'priority', 'assignee']): A list of fields that can be used for filtering tasks.
        search_fields (['title', 'description']): A list of fields that can be used for searching tasks.
        ordering_fields (['created_at', 'due_date', 'priority', 'position']): A list of fields that can be used for ordering tasks.

    """
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
        """
        Called when a new Task instance is created via this viewset.

        This method sets the 'created_by' field of the Task to the current user
        making the request, ensuring that the creator of the task is recorded.

        Args:
            serializer: The serializer instance containing validated data for the new Task.
        """
        task = serializer.save(created_by=self.request.user)
        
        if task.assignee:
            notification_data = {
                'type': 'TASK_ASSIGNED',
                'title': 'New Task Assigned',
                'message': f'You have been assigned to task "{task.title}"',
                'task_id': task.id,
                'project_slug': task.project.slug
            }
            send_realtime_notification(task.assignee, notification_data)
        
        # Broadcast to all project watchers
        update_data = {
            'task_id': task.id,
            'task_title': task.title,
            'status': task.status,
            'assignee': task.assignee.username if task.assignee else None,
            'created_by': task.created_by.username
        }
        broadcast_project_update(task.project.slug, 'task_update', update_data)
        
        
        
        
    
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
        """Change task status and broadcast update"""
        task = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(Task.Status.choices):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = task.status
        task.status = new_status
        
        # Set completed_at when marking as completed
        if new_status == Task.Status.COMPLETED:
            from django.utils import timezone
            task.completed_at = timezone.now()
        elif task.completed_at and new_status != Task.Status.COMPLETED:
            task.completed_at = None
        
        task.save()
        
        # Notify task creator if status changed
        if task.created_by != request.user:
            notification_data = {
                'type': 'STATUS_CHANGE',
                'title': 'Task Status Changed',
                'message': f'Task "{task.title}" status changed from {old_status} to {new_status}',
                'task_id': task.id
            }
            send_realtime_notification(task.created_by, notification_data)
        
        # Broadcast to project
        update_data = {
            'task_id': task.id,
            'task_title': task.title,
            'old_status': old_status,
            'new_status': new_status,
            'updated_by': request.user.username
        }
        broadcast_project_update(task.project.slug, 'task_update', update_data)
        
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
        Log time spent on task - only assignee can log time.

        This endpoint allows the task assignee to log time spent working on a task.
        It accepts a POST request with an 'hours' parameter specifying the time spent.
        The hours are added to the task's actual_hours field, which accumulates
        total time spent on the task. The decorator @require_task_assignee ensures
        only the assigned user can log time for the task.

        Parameters:
        - hours (float): Number of hours spent on the task (required)

        Returns:
        - Success: Message with logged hours and updated total hours
        - Error: 400 if hours not provided or invalid
        """
        hours = request.data.get('hours')

        if not hours:
            return Response(
                {'error': 'Hours required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            hours_float = float(hours)
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid hours value'},
                status=status.HTTP_400_BAD_REQUEST
            )

        task.actual_hours = (task.actual_hours or 0) + hours_float
        task.save()

        return Response({
            'message': f'Logged {hours_float} hours',
            'total_hours': task.actual_hours
        })
    
    @action(detail=False, methods=['post'])
    @require_role('ADMIN', 'PM', 'TL')
    def bulk_assign(self, request):
        """
        Bulk assign tasks to users - only managers.

        This endpoint allows administrators (ADMIN), project managers (PM), and team leads (TL) 
        to assign multiple tasks to a single user in one operation. The endpoint expects:
        - task_ids: List of task IDs to be assigned (required)
        - assignee_id: The ID of the user to assign tasks to (required)

        Returns:
        - Success: Message with count of updated tasks and assignee username
        - Error: 400 if required parameters missing, 404 if user not found
        """
        # Extract task IDs and assignee ID from request data
        task_ids = request.data.get('task_ids', [])
        assignee_id = request.data.get('assignee_id')

        # Validate required parameters
        if not task_ids or not assignee_id:
            return Response(
                {'error': 'task_ids and assignee_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Import user model dynamically
        from accounts.models import CustomUser

        try:
            # Fetch target user by ID
            assignee = CustomUser.objects.get(id=assignee_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Update all matching tasks with new assignee
        tasks = Task.objects.filter(id__in=task_ids)
        updated_count = tasks.update(assignee=assignee)

        # Return success response with operation details
        return Response({
            'message': f'Assigned {updated_count} tasks to {assignee.username}',
            'updated_tasks': updated_count
        })
    
    
    
class TaskLabelViewSet(viewsets.ModelViewSet):
    """
    TaskLabel ViewSet for managing task labels within projects.
    This ViewSet provides CRUD operations for TaskLabel objects, allowing users to:
    - Create new labels for projects - List all available labels (can be filtered by project)
    - Retrieve, update, or delete specific labels By default, only authenticated users can access these endpoints.
    Labels can be filtered by project using the 'project' query parameter.
    Example usage:
    - GET /api/labels/ - List all labels - GET /api/labels/?project=1 - List labels for project with ID1 - POST /api/labels/ - Create a new label - PUT /api/labels/{id}/ - Update a label - DELETE /api/labels/{id}/ - Delete a label """
    queryset = TaskLabel.objects.all()
    serializer_class = TaskLabelSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['project']
    
       
   
    
    