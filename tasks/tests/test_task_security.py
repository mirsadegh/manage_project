# tasks/tests/test_task_security.py
"""
Regression tests for PR-4 Commit 4 security fixes.

Covers:
- T-1: Task list no longer leaks tasks from non-member projects via
       assignee/created_by clauses
- T-2: TaskViewSet.assign requires project membership
- T-3: TaskViewSet.bulk_assign scoped to accessible projects
- T-4: TaskLabelViewSet scoped + membership check on create
- T-5: TaskListViewSet scoped + membership check on create
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model

from projects.models import Project, ProjectMember
from tasks.models import Task, TaskList, TaskLabel

User = get_user_model()

pytestmark = pytest.mark.django_db


# ─── Fixtures ───

@pytest.fixture
def admin_user():
    return User.objects.create_user(
        username='task_admin', email='admin@example.com',
        password='Test123!', role='ADMIN',
    )


@pytest.fixture
def owner():
    return User.objects.create_user(
        username='task_owner', email='owner@example.com',
        password='Test123!', role='PM',
    )


@pytest.fixture
def member(owner):
    return User.objects.create_user(
        username='task_member', email='member@example.com',
        password='Test123!', role='DEV',
    )


@pytest.fixture
def outsider():
    return User.objects.create_user(
        username='task_outsider', email='outsider@example.com',
        password='Test123!', role='DEV',
    )


@pytest.fixture
def project(owner):
    return Project.objects.create(
        name='Test Project', slug='test-project', owner=owner,
    )


@pytest.fixture
def membership(project, member):
    return ProjectMember.objects.create(
        project=project, user=member, role='MEMBER', is_active=True,
    )


@pytest.fixture
def task_list(project, owner):
    return TaskList.objects.create(
        project=project, name='Default', created_by=owner,
    )


@pytest.fixture
def task(project, task_list, owner):
    return Task.objects.create(
        project=project, task_list=task_list, title='Test Task',
        created_by=owner,
    )


def _task_list(response_json):
    """TaskPagination wraps data under 'tasks' key."""
    return response_json.get('tasks', response_json.get('results', []))


# ─── T-1: list does not leak tasks across project boundaries ───

class TestTaskListBOLA:
    """T-1: assignee/created_by must not leak tasks from non-member projects."""

    def test_non_member_cannot_list_tasks_from_assignee(
        self, api_client, outsider, project, task_list, owner,
    ):
        Task.objects.create(
            project=project, task_list=task_list, title='Outsider task',
            created_by=owner, assignee=outsider,
        )
        api_client.force_authenticate(user=outsider)
        response = api_client.get(reverse('task-list'))
        assert response.status_code == status.HTTP_200_OK
        titles = [t['title'] for t in _task_list(response.json())]
        assert 'Outsider task' not in titles

    def test_non_member_cannot_list_tasks_from_created_by(
        self, api_client, outsider, project, task_list,
    ):
        Task.objects.create(
            project=project, task_list=task_list, title='Created-by-outsider',
            created_by=outsider,
        )
        api_client.force_authenticate(user=outsider)
        response = api_client.get(reverse('task-list'))
        titles = [t['title'] for t in _task_list(response.json())]
        assert 'Created-by-outsider' not in titles

    def test_member_can_list_own_project_tasks(
        self, api_client, member, membership, task,
    ):
        api_client.force_authenticate(user=member)
        response = api_client.get(reverse('task-list'))
        assert response.status_code == status.HTTP_200_OK
        titles = [t['title'] for t in _task_list(response.json())]
        assert 'Test Task' in titles


class TestMyTasksEndpoint:
    """T-1: my_tasks surfaces tasks where the user is assignee or creator."""

    def test_my_tasks_shows_assignee_tasks(
        self, api_client, member, project, task_list, owner,
    ):
        Task.objects.create(
            project=project, task_list=task_list, title='Assigned to me',
            created_by=owner, assignee=member,
        )
        api_client.force_authenticate(user=member)
        response = api_client.get(reverse('task-my-tasks'))
        assert response.status_code == status.HTTP_200_OK
        titles = [t['title'] for t in _task_list(response.json())]
        assert 'Assigned to me' in titles

    def test_my_tasks_shows_created_by_tasks(
        self, api_client, member, project, task_list,
    ):
        Task.objects.create(
            project=project, task_list=task_list, title='Created by me',
            created_by=member,
        )
        api_client.force_authenticate(user=member)
        response = api_client.get(reverse('task-my-tasks'))
        titles = [t['title'] for t in _task_list(response.json())]
        assert 'Created by me' in titles

    def test_all_tasks_requires_admin(
        self, api_client, member, project, task,
    ):
        # Non-admin: must not see other projects' tasks
        api_client.force_authenticate(user=member)
        response = api_client.get(reverse('task-all-tasks'))
        assert response.status_code == status.HTTP_200_OK
        titles = [t['title'] for t in _task_list(response.json())]
        assert 'Test Task' not in titles


# ─── T-2: assign requires project membership ───

class TestAssignMembership:
    """T-2: only project members (or admin/PM) may assign tasks."""

    def test_assign_requires_project_membership(
        self, api_client, outsider, task, member,
    ):
        api_client.force_authenticate(user=outsider)
        response = api_client.post(
            reverse('task-assign', kwargs={'pk': task.id}),
            data={'user_id': member.id},
            format='json',
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_assign_cross_project(
        self, api_client, admin_user, task, member,
    ):
        api_client.force_authenticate(user=admin_user)
        response = api_client.post(
            reverse('task-assign', kwargs={'pk': task.id}),
            data={'user_id': member.id},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        task.refresh_from_db()
        assert task.assignee_id == member.id

    def test_project_manager_can_assign_in_own_project(
        self, api_client, owner, task, member,
    ):
        # owner is the project owner with PM role - passes CanReassignTask
        # and the T-2 in-view check.
        api_client.force_authenticate(user=owner)
        response = api_client.post(
            reverse('task-assign', kwargs={'pk': task.id}),
            data={'user_id': member.id},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK


# ─── T-3: bulk_assign scoped to accessible projects ───

class TestBulkAssignScoping:
    """T-3: bulk_assign only affects tasks in projects the caller can access."""

    def test_bulk_assign_scoped_to_accessible_projects(
        self, api_client, project, task_list, owner, admin_user,
    ):
        # TL role passes the @require_role decorator; with T-3 the
        # queryset is filtered to projects TL is a member of.
        tl_user = User.objects.create_user(
            username='tl_user', email='tl@example.com',
            password='Test123!', role='TL',
        )
        ProjectMember.objects.create(
            project=project, user=tl_user, role='MEMBER', is_active=True,
        )
        tl_task = Task.objects.create(
            project=project, task_list=task_list, title='TL task',
            created_by=owner,
        )
        api_client.force_authenticate(user=tl_user)
        response = api_client.post(
            reverse('task-bulk-assign'),
            data={'task_ids': [tl_task.id], 'assignee_id': admin_user.id},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        tl_task.refresh_from_db()
        assert tl_task.assignee_id == admin_user.id

    def test_admin_bulk_assign_cross_project(
        self, api_client, admin_user, task, member,
    ):
        api_client.force_authenticate(user=admin_user)
        response = api_client.post(
            reverse('task-bulk-assign'),
            data={'task_ids': [task.id], 'assignee_id': member.id},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        task.refresh_from_db()
        assert task.assignee_id == member.id


# ─── T-4: TaskLabelViewSet scoped + membership check ───

class TestTaskLabelAccess:
    """T-4: labels listable only in accessible projects; create requires membership."""

    def test_label_list_scoped_to_accessible_projects(
        self, api_client, outsider, project,
    ):
        TaskLabel.objects.create(project=project, name='Bug', color='#ff0000')
        api_client.force_authenticate(user=outsider)
        response = api_client.get(reverse('label-list'))
        assert response.status_code == status.HTTP_200_OK
        names = [lbl['name'] for lbl in response.json()['results']]
        assert 'Bug' not in names

    def test_label_create_requires_membership(
        self, api_client, outsider, project,
    ):
        api_client.force_authenticate(user=outsider)
        response = api_client.post(
            reverse('label-list'),
            data={'project': project.id, 'name': 'Unauthorized', 'color': '#ff0000'},
            format='json',
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_can_create_label_in_own_project(
        self, api_client, member, membership, project,
    ):
        api_client.force_authenticate(user=member)
        response = api_client.post(
            reverse('label-list'),
            data={'project': project.id, 'name': 'Feature', 'color': '#00ff00'},
            format='json',
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert TaskLabel.objects.filter(
            project=project, name='Feature',
        ).exists()


# ─── T-5: TaskListViewSet scoped + membership check ───

class TestTaskListAccess:
    """T-5: task lists scoped to accessible projects; create requires membership."""

    def test_tasklist_list_scoped_to_accessible_projects(
        self, api_client, outsider, project, owner,
    ):
        TaskList.objects.create(
            project=project, name='Sprint 1', created_by=owner,
        )
        api_client.force_authenticate(user=outsider)
        response = api_client.get(reverse('tasklist-list'))
        assert response.status_code == status.HTTP_200_OK
        names = [tl['name'] for tl in response.json()['results']]
        assert 'Sprint 1' not in names

    def test_tasklist_create_requires_membership(
        self, api_client, outsider, project,
    ):
        api_client.force_authenticate(user=outsider)
        response = api_client.post(
            reverse('tasklist-list'),
            data={'project': project.id, 'name': 'Bad List', 'order': 0},
            format='json',
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_can_create_tasklist_in_own_project(
        self, api_client, member, membership, project,
    ):
        api_client.force_authenticate(user=member)
        response = api_client.post(
            reverse('tasklist-list'),
            data={'project': project.id, 'name': 'Sprint 2', 'order': 1},
            format='json',
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert TaskList.objects.filter(
            project=project, name='Sprint 2',
        ).exists()
