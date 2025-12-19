import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from .factories import (
    TaskFactory, TaskListFactory, ProjectWithTasksFactory,
    CompletedTaskFactory, HighPriorityTaskFactory, OverdueTaskFactory
)
from accounts.tests.factories import UserFactory, ManagerUserFactory

User = get_user_model()


@pytest.mark.django_db
class TestTaskCreation:
    """Test task creation"""
    
    def test_member_can_create_task(self, authenticated_client, project, task_list, user):
        """Test project member can create tasks"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=project, user=user, role='MEMBER')
        
        data = {
            'title': 'New Task',
            'description': 'Test task',
            'project': project.id,
            'task_list': task_list.id,
            'status': 'TODO',
            'priority': 'MEDIUM'
        }
        response = authenticated_client.post(reverse('task-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        from .models import Task
        assert Task.objects.count() == 1
        assert Task.objects.first().created_by == user
    
    def test_non_member_cannot_create_task(self, authenticated_client, project, task_list):
        """Test non-member cannot create tasks"""
        data = {
            'title': 'New Task',
            'description': 'Test task',
            'project': project.id,
            'task_list': task_list.id,
            'status': 'TODO',
            'priority': 'MEDIUM'
        }
        response = authenticated_client.post(reverse('task-list'), data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTaskAssignment:
    """Test task assignment"""
    
    def test_manager_can_assign_task(self, manager_client, task):
        """Test manager can assign tasks"""
        assignee = UserFactory()
        data = {'user_id': assignee.id}
        response = manager_client.post(reverse('task-assign', kwargs={'pk': task.id}), data)
        
        assert response.status_code == status.HTTP_200_OK
        task.refresh_from_db()
        assert task.assignee == assignee
    
    def test_developer_cannot_reassign_task(self, developer_client, task, developer_user):
        """Test developer cannot reassign tasks"""
        task.assignee = developer_user
        task.save()
        
        other_user = UserFactory()
        data = {'user_id': other_user.id}
        response = developer_client.post(reverse('task-assign', kwargs={'pk': task.id}), data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTaskStatusChange:
    """Test task status changes"""
    
    def test_assignee_can_change_status(self, developer_client, task, developer_user):
        """Test assignee can change task status"""
        task.assignee = developer_user
        task.save()
        
        data = {'status': 'IN_PROGRESS'}
        response = developer_client.post(reverse('task-change-status', kwargs={'pk': task.id}), data)
        
        assert response.status_code == status.HTTP_200_OK
        task.refresh_from_db()
        assert task.status == 'IN_PROGRESS'
    
    def test_non_assignee_cannot_change_status(self, authenticated_client, task):
        """Test non-assignee cannot change task status"""
        data = {'status': 'IN_PROGRESS'}
        response = authenticated_client.post(reverse('task-change-status', kwargs={'pk': task.id}), data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTaskPagination:
    """Test task pagination with statistics"""
    
    def test_task_pagination_includes_statistics(self, manager_client, project_with_tasks):
        """Test task pagination includes statistics"""
        response = manager_client.get(reverse('task-list'))
        
        assert response.status_code == status.HTTP_200_OK
        assert 'statistics' in response.data
        assert 'total_tasks' in response.data['statistics']
        assert response.data['statistics']['total_tasks'] >= 5


@pytest.mark.django_db
class TestTaskFilters:
    """Test task filtering and search"""
    
    def test_filter_by_status(self, manager_client, multiple_tasks):
        """Test filtering tasks by status"""
        # Mark some tasks as completed
        from .models import Task
        for task in Task.objects.all()[:2]:
            task.status = Task.Status.COMPLETED
            task.save()
        
        url = f"{reverse('task-list')}?status=COMPLETED"
        response = manager_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        for task_data in response.data['results']:
            assert task_data['status'] == 'COMPLETED'
    
    def test_filter_by_priority(self, manager_client, multiple_tasks):
        """Test filtering tasks by priority"""
        # Create high priority tasks
        from .models import Task
        for task in Task.objects.all()[:2]:
            task.priority = Task.Priority.HIGH
            task.save()
        
        url = f"{reverse('task-list')}?priority=HIGH"
        response = manager_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        for task_data in response.data['results']:
            assert task_data['priority'] == 'HIGH'
    
    def test_search_tasks(self, manager_client, multiple_tasks):
        """Test searching tasks"""
        # Update a task title for search testing
        from .models import Task
        task = Task.objects.first()
        task.title = "Unique Search Term"
        task.save()
        
        url = f"{reverse('task-list')}?search=Unique Search Term"
        response = manager_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
        assert "Unique Search Term" in response.data['results'][0]['title']


@pytest.mark.django_db
class TestTaskDependencies:
    """Test task dependencies"""
    
    def test_create_task_with_dependencies(self, manager_client, project, task_list, manager_user):
        """Test creating a task with dependencies"""
        dependency_task = TaskFactory(
            project=project,
            task_list=task_list,
            created_by=manager_user
        )
        
        data = {
            'title': 'Task with Dependencies',
            'project': project.id,
            'task_list': task_list.id,
            'depends_on': [dependency_task.id]
        }
        response = manager_client.post(reverse('task-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        
        from .models import TaskDependency
        assert TaskDependency.objects.filter(
            task_id=response.data['id'],
            depends_on_id=dependency_task.id
        ).exists()
    
    def test_cannot_complete_task_with_incomplete_dependencies(self, developer_client, task_with_dependencies, developer_user):
        """Test cannot complete task with incomplete dependencies"""
        task_with_dependencies.assignee = developer_user
        task_with_dependencies.save()
        
        data = {'status': 'COMPLETED'}
        response = developer_client.post(
            reverse('task-change-status', kwargs={'pk': task_with_dependencies.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTaskTimeTracking:
    """Test task time tracking"""
    
    def test_update_actual_hours(self, developer_client, task, developer_user):
        """Test updating actual hours worked"""
        task.assignee = developer_user
        task.save()
        
        data = {'actual_hours': 5.5}
        response = developer_client.patch(
            reverse('task-detail', kwargs={'pk': task.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_200_OK
        task.refresh_from_db()
        assert float(task.actual_hours) == 5.5
    
    def test_time_tracking_statistics(self, manager_client, project_with_tasks):
        """Test time tracking statistics"""
        response = manager_client.get(reverse('task-list'))
        
        assert response.status_code == status.HTTP_200_OK
        stats = response.data['statistics']
        assert 'total_estimated_hours' in stats
        assert 'total_actual_hours' in stats
        assert 'completion_rate' in stats


@pytest.mark.django_db
class TestTaskValidation:
    """Test task validation"""
    
    def test_due_date_after_start_date(self, manager_client, project, task_list, manager_user):
        """Test that due date must be after start date"""
        from datetime import date, timedelta
        
        data = {
            'title': 'Invalid Task',
            'project': project.id,
            'task_list': task_list.id,
            'start_date': date.today(),
            'due_date': date.today() - timedelta(days=1)  # Due date before start date
        }
        response = manager_client.post(reverse('task-list'), data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'due_date' in response.data
    
    def test_required_fields_validation(self, manager_client, project, task_list):
        """Test required fields validation"""
        data = {
            'project': project.id,
            'task_list': task_list.id,
            # Missing title and description
        }
        response = manager_client.post(reverse('task-list'), data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'title' in response.data


@pytest.mark.django_db
class TestTaskListOperations:
    """Test task list operations"""
    
    def test_create_task_list(self, manager_client, project, manager_user):
        """Test creating a task list"""
        data = {
            'name': 'New Task List',
            'description': 'Test task list',
            'project': project.id
        }
        response = manager_client.post(reverse('tasklist-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        from .models import TaskList
        assert TaskList.objects.count() == 1
        assert TaskList.objects.first().created_by == manager_user
    
    def test_reorder_tasks(self, manager_client, multiple_tasks):
        """Test reordering tasks within a list"""
        # Get task IDs and reorder them
        from .models import Task
        tasks = list(Task.objects.all())
        task_ids = [task.id for task in tasks]
        
        # Reverse the order
        reversed_ids = list(reversed(task_ids))
        
        data = {'task_orders': [{'id': tid, 'order': i} for i, tid in enumerate(reversed_ids)]}
        response = manager_client.post(reverse('task-reorder', kwargs={'pk': tasks[0].task_list.id}), data)
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify order changed
        for i, task_id in enumerate(reversed_ids):
            task = Task.objects.get(id=task_id)
            assert task.order == i


@pytest.mark.django_db
class TestTaskPerformance:
    """Test task-related performance metrics"""
    
    def test_task_completion_rate_calculation(self, manager_client, project_with_tasks):
        """Test completion rate is calculated correctly"""
        from .models import Task
        
        # Mark half the tasks as completed
        tasks = list(Task.objects.all())
        for task in tasks[:len(tasks)//2]:
            task.status = Task.Status.COMPLETED
            task.save()
        
        response = manager_client.get(reverse('task-list'))
        
        assert response.status_code == status.HTTP_200_OK
        stats = response.data['statistics']
        expected_rate = (len(tasks)//2) / len(tasks) * 100
        assert abs(stats['completion_rate'] - expected_rate) < 0.1
    
    def test_overdue_tasks_count(self, manager_client, overdue_task):
        """Test overdue tasks are counted"""
        response = manager_client.get(reverse('task-list'))
        
        assert response.status_code == status.HTTP_200_OK
        stats = response.data['statistics']
        assert 'overdue_tasks' in stats
        assert stats['overdue_tasks'] >= 1
