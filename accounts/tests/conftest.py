import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from accounts.tests.factories import UserFactory, AdminUserFactory, ManagerUserFactory

User = get_user_model()


@pytest.fixture
def api_client():
    """Provide an API client for testing."""
    return APIClient()


@pytest.fixture
def user():
    """Create a regular user (defaults to DEV role)."""
    return UserFactory()


@pytest.fixture
def dev_user(user):
    """Ensure the user fixture has a DEV role for clarity."""
    # Assuming UserFactory creates a user with a default role, we set it explicitly.
    user.role = User.Role.DEVELOPER  # Use the correct role enum value
    user.save()
    return user


@pytest.fixture
def admin_user():
    """Create an admin user."""
    return AdminUserFactory()


@pytest.fixture
def manager_user():
    """Create a manager user."""
    return ManagerUserFactory()


@pytest.fixture
def authenticated_client(api_client, user):
    """Provide an authenticated API client for a regular user."""
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

# New fixture for a developer client
@pytest.fixture
def dev_client(api_client, dev_user):
    """Provide a developer authenticated API client."""
    api_client.force_authenticate(user=dev_user)
    return api_client


@pytest.fixture
def multiple_users():
    """Create multiple test users."""
    return [
        UserFactory(username=f'user{i}', email=f'user{i}@example.com')
        for i in range(5)
    ]

# Fixtures for common URLs
@pytest.fixture
def register_url():
    """URL for user registration."""
    return reverse('register')


@pytest.fixture
def login_url():
    """URL for obtaining a token."""
    return reverse('token_obtain_pair')


@pytest.fixture
def user_list_url():
    """URL for the user list endpoint."""
    return reverse('user-list')



