import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from accounts.tests.factories import UserFactory, ManagerUserFactory
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import TaskFactory, TaskListFactory

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
