"""
Shared test configuration and fixtures for all apps.
"""
import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from accounts.tests.factories import (
    UserFactory, AdminUserFactory, ManagerUserFactory,
    DeveloperUserFactory, ClientUserFactory
)
from projects.tests.factories import ProjectFactory, ProjectMemberFactory
from tasks.tests.factories import TaskFactory, TaskListFactory

User = get_user_model()


@pytest.fixture(scope="session")
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
    return AdminUserFactory()


@pytest.fixture
def manager_user():
    """Create a manager user."""
    return ManagerUserFactory()


@pytest.fixture
def developer_user():
    """Create a developer user."""
    return DeveloperUserFactory()


@pytest.fixture
def client_user():
    """Create a client user."""
    return ClientUserFactory()


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
def client_auth_client(api_client, client_user):
    """Provide a client authenticated API client."""
    api_client.force_authenticate(user=client_user)
    return api_client


@pytest.fixture
def project(manager_user):
    """Create a test project."""
    return ProjectFactory(owner=manager_user)


@pytest.fixture
def project_with_members(project):
    """Create a project with members."""
    members = [UserFactory() for _ in range(3)]
    for member in members:
        ProjectMemberFactory(project=project, user=member)
    return project, members


@pytest.fixture
def task(project):
    """Create a test task."""
    task_list = TaskListFactory(project=project, created_by=project.owner)
    return TaskFactory(project=project, task_list=task_list, created_by=project.owner)


@pytest.fixture
def multiple_users():
    """Create multiple test users."""
    return [UserFactory() for _ in range(5)]


@pytest.fixture
def multiple_projects(manager_user):
    """Create multiple test projects."""
    return [ProjectFactory(owner=manager_user) for _ in range(3)]


@pytest.fixture
def multiple_tasks(project):
    """Create multiple test tasks."""
    task_list = TaskListFactory(project=project, created_by=project.owner)
    return [
        TaskFactory(project=project, task_list=task_list, created_by=project.owner)
        for _ in range(5)
    ]


# URL fixtures
@pytest.fixture
def login_url():
    """URL for login."""
    from django.urls import reverse
    return reverse('token_obtain_pair')


@pytest.fixture
def register_url():
    """URL for registration."""
    from django.urls import reverse
    return reverse('register')


@pytest.fixture
def logout_url():
    """URL for logout."""
    from django.urls import reverse
    return reverse('logout')


@pytest.fixture
def user_list_url():
    """URL for user list."""
    from django.urls import reverse
    return reverse('user-list')


@pytest.fixture
def project_list_url():
    """URL for project list."""
    from django.urls import reverse
    return reverse('project-list')


@pytest.fixture
def task_list_url():
    """URL for task list."""
    from django.urls import reverse
    return reverse('task-list')


@pytest.fixture
def notification_list_url():
    """URL for notification list."""
    from django.urls import reverse
    return reverse('notification-list')


@pytest.fixture
def comment_list_url():
    """URL for comment list."""
    from django.urls import reverse
    return reverse('comment-list')


# Performance testing fixtures
@pytest.fixture
def large_dataset():
    """Create a large dataset for performance testing."""
    projects = [ProjectFactory() for _ in range(10)]
    
    for project in projects:
        task_list = TaskListFactory(project=project)
        TaskFactory.create_batch(50, project=project, task_list=task_list)
    
    return projects


@pytest.fixture
def concurrent_users():
    """Create users for concurrent testing."""
    return [UserFactory() for _ in range(20)]


# Security testing fixtures
@pytest.fixture
def malicious_user():
    """Create a user for security testing."""
    return UserFactory(username="malicious_user", email="malicious@test.com")


@pytest.fixture
def test_password():
    """Standard test password."""
    return "TestPassword123!"


# Markers for different test types
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.security = pytest.mark.security
pytest.mark.slow = pytest.mark.slow
