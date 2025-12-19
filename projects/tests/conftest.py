import pytest
from rest_framework.test import APIClient
from .factories import ProjectFactory, ProjectMemberFactory
from accounts.tests.factories import UserFactory
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def admin_user():
    return UserFactory(role=User.Role.ADMIN)


@pytest.fixture
def manager_user():
    return UserFactory(role=User.Role.PROJECT_MANAGER)


@pytest.fixture
def developer_user():
    return UserFactory(role=User.Role.DEVELOPER)


@pytest.fixture
def member_user():
    return UserFactory(role=User.Role.DEVELOPER)


@pytest.fixture
def project(manager_user):
    return ProjectFactory(owner=manager_user)


@pytest.fixture
def project_with_members(project, member_user):
    ProjectMemberFactory(project=project, user=member_user, role='MEMBER')
    return project
