import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from .factories import (
    TaskFactory, TaskListFactory, ProjectWithTasksFactory,
    CompletedTaskFactory, HighPriorityTaskFactory, OverdueTaskFactory
)
from accounts.tests.factories import UserFactory, ManagerUserFactory
from projects.tests.factories import ProjectFactory

User = get_user_model()


@pytest.fixture
def api_client():
    """Provide an API client for testing."""
    return APIClient()


@pytest.fixture
def user():
    """Create a regular user."""
    return UserFactory()


@pytest.fixture
def admin_user():
    """Create an admin user."""
    return UserFactory(role=User.Role.ADMIN)


@pytest.fixture
def manager_user():
    """Create a manager user."""
    return ManagerUserFactory()


@pytest.fixture
def developer_user():
    """Create a developer user."""
    return UserFactory(role=User.Role.DEVELOPER)


@pytest.fixture
def authenticated_client(api_client, user):
    """Provide an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """Provide an admin authenticated API client."""
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def manager_client(api_client, manager_user):
    """Provide a manager authenticated API client."""
    api_client.force_authenticate(user=manager_user)
    return api_client


@pytest.fixture
def developer_client(api_client, developer_user):
    """Provide a developer authenticated API client."""
    api_client.force_authenticate(user=developer_user)
    return api_client


@pytest.fixture
def project(manager_user):
    """Create a test project."""
    return ProjectFactory(owner=manager_user)


@pytest.fixture
def task_list(project):
    """Create a test task list."""
    return TaskListFactory(project=project, created_by=project.owner)


@pytest.fixture
def task(project, task_list, manager_user):
    """Create a test task."""
    return TaskFactory(
        project=project,
        task_list=task_list,
        created_by=manager_user,
        assignee=UserFactory()
    )


@pytest.fixture
def completed_task(project, task_list):
    """Create a completed task."""
    return CompletedTaskFactory(
        project=project,
        task_list=task_list
    )


@pytest.fixture
def high_priority_task(project, task_list):
    """Create a high priority task."""
    return HighPriorityTaskFactory(
        project=project,
        task_list=task_list
    )


@pytest.fixture
def overdue_task(project, task_list):
    """Create an overdue task."""
    return OverdueTaskFactory(
        project=project,
        task_list=task_list
    )


@pytest.fixture
def project_with_tasks(manager_user):
    """Create a project with multiple tasks."""
    return ProjectWithTasksFactory(owner=manager_user, with_tasks=5)


@pytest.fixture
def multiple_tasks(project, task_list, manager_user):
    """Create multiple test tasks."""
    return [
        TaskFactory(
            project=project,
            task_list=task_list,
            created_by=manager_user,
            assignee=UserFactory()
        )
        for _ in range(5)
    ]


@pytest.fixture
def task_with_dependencies(project, task_list):
    """Create a task with dependencies."""
    from .factories import TaskDependencyFactory
    
    main_task = TaskFactory(project=project, task_list=task_list)
    dependency_task = TaskFactory(project=project, task_list=task_list)
    
    TaskDependencyFactory(
        task=main_task,
        depends_on=dependency_task
    )
    
    return main_task


@pytest.fixture
def task_list_url():
    """URL for task list endpoint."""
    from django.urls import reverse
    return reverse('task-list')


@pytest.fixture
def task_detail_url(task):
    """URL for task detail endpoint."""
    from django.urls import reverse
    return reverse('task-detail', kwargs={'pk': task.id})


@pytest.fixture
def task_assign_url(task):
    """URL for task assignment endpoint."""
    from django.urls import reverse
    return reverse('task-assign', kwargs={'pk': task.id})


@pytest.fixture
def task_change_status_url(task):
    """URL for task status change endpoint."""
    from django.urls import reverse
    return reverse('task-change-status', kwargs={'pk': task.id})


@pytest.fixture
def task_list_with_tasks(project, manager_user):
    """Create a task list with multiple tasks."""
    from .factories import TaskListWithTasksFactory
    return TaskListWithTasksFactory(
        project=project,
        created_by=manager_user
    )


@pytest.fixture
def user_tasks(developer_user, manager_user):
    """Create tasks assigned to a specific user."""
    project = ProjectFactory(owner=manager_user)
    task_list = TaskListFactory(project=project, created_by=manager_user)
    
    return [
        TaskFactory(
            project=project,
            task_list=task_list,
            created_by=manager_user,
            assignee=developer_user
        )
        for _ in range(3)
    ]


@pytest.fixture
def project_members(project):
    """Create project members for testing permissions."""
    from projects.tests.factories import ProjectMemberFactory
    
    members = []
    for _ in range(3):
        user = UserFactory()
        ProjectMemberFactory(project=project, user=user)
        members.append(user)
    
    return members
