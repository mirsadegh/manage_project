# tasks/tests/test_pagination_stats.py
"""
Regression tests for H-2: TaskPagination global stats bug.

Bug: get_paginated_response() aggregated over the entire unfiltered Task
table, so requesting tasks filtered by ?project=X returned site-wide
statistics — leaking cross-project data (counts, completion rate, hours).

Fix: aggregate over self.page.paginator.object_list (the filtered queryset).

Also covers removal of the duplicate 'tasks' payload key.
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model

from projects.models import Project, ProjectMember
from tasks.models import Task, TaskList

User = get_user_model()

pytestmark = pytest.mark.django_db


# ─── Fixtures ───

@pytest.fixture
def owner():
    return User.objects.create_user(
        username='h2_owner', email='owner@example.com',
        password='Test123!', role='PM',
    )


@pytest.fixture
def project_a(owner):
    return Project.objects.create(
        name='Project Alpha', slug='project-alpha', owner=owner,
    )


@pytest.fixture
def project_b(owner):
    return Project.objects.create(
        name='Project Beta', slug='project-beta', owner=owner,
    )


def _make_list(project):
    return TaskList.objects.create(
        project=project, name=f"List for {project.name}", created_by=project.owner,
    )


def _make_task(project, task_list, title, status='TODO'):
    return Task.objects.create(
        project=project, task_list=task_list, title=title,
        status=status, created_by=project.owner,
        estimated_hours=10, actual_hours=5,
    )


# ─── H-2: statistics must respect the filtered queryset ───

class TestPaginationStatsScoping:
    """H-2: stats must reflect the filtered queryset, not the global Task table."""

    def test_stats_scoped_to_project_filter(self, api_client, owner, project_a, project_b):
        ProjectMember.objects.create(
            project=project_a, user=owner, role='MEMBER', is_active=True,
        )
        ProjectMember.objects.create(
            project=project_b, user=owner, role='MEMBER', is_active=True,
        )

        # Project A: 2 tasks, 1 completed, 1 overdue would be complex — keep simple:
        # 2 TODO tasks in A, plus 2 completed tasks in B.
        list_a = _make_list(project_a)
        list_b = _make_list(project_b)
        _make_task(project_a, list_a, 'A task 1')
        _make_task(project_a, list_a, 'A task 2')
        _make_task(project_b, list_b, 'B task 1', status='COMPLETED')
        _make_task(project_b, list_b, 'B task 2', status='COMPLETED')

        api_client.force_authenticate(user=owner)
        response = api_client.get(
            reverse('task-list'), {'project': project_a.id}
        )
        assert response.status_code == status.HTTP_200_OK

        stats = response.data['statistics']
        # Stats must count ONLY Project A's tasks — not Project B's.
        assert stats['total_tasks'] == 2
        assert stats['completed_tasks'] == 0
        assert stats['in_progress_tasks'] == 0
        assert stats['todo_tasks'] == 2
        assert stats['completion_rate'] == 0
        # Hours also scoped: only A's 2 tasks at 10h estimated each.
        assert float(stats['total_estimated_hours']) == 20

    def test_stats_scoped_to_status_filter(self, api_client, owner, project_a):
        ProjectMember.objects.create(
            project=project_a, user=owner, role='MEMBER', is_active=True,
        )
        task_list = _make_list(project_a)
        _make_task(project_a, task_list, 'TODO one')
        _make_task(project_a, task_list, 'TODO two')
        _make_task(project_a, task_list, 'DONE one', status='COMPLETED')

        api_client.force_authenticate(user=owner)
        response = api_client.get(
            reverse('task-list'), {'project': project_a.id, 'status': 'COMPLETED'}
        )
        assert response.status_code == status.HTTP_200_OK

        stats = response.data['statistics']
        # Filter is ?status=COMPLETED, so the queryset holds 1 task and stats
        # must reflect that queryset: total 1, completed 1, 100% completion.
        assert stats['total_tasks'] == 1
        assert stats['completed_tasks'] == 1
        assert stats['todo_tasks'] == 0
        assert stats['completion_rate'] == 100

    def test_stats_match_pagination_count(self, api_client, owner, project_a, project_b):
        """The stats 'total_tasks' must equal the filtered pagination count."""
        ProjectMember.objects.create(
            project=project_a, user=owner, role='MEMBER', is_active=True,
        )
        list_a = _make_list(project_a)
        list_b = _make_list(project_b)
        for i in range(3):
            _make_task(project_a, list_a, f'A {i}')
        for i in range(7):
            _make_task(project_b, list_b, f'B {i}')

        api_client.force_authenticate(user=owner)
        response = api_client.get(
            reverse('task-list'), {'project': project_a.id}
        )
        assert response.status_code == status.HTTP_200_OK

        assert response.data['count'] == 3
        assert response.data['statistics']['total_tasks'] == 3


class TestPaginationPayloadShape:
    """H-2 cleanup: no duplicate 'tasks' key alongside 'results'."""

    def test_no_duplicate_tasks_key(self, api_client, owner, project_a):
        ProjectMember.objects.create(
            project=project_a, user=owner, role='MEMBER', is_active=True,
        )
        task_list = _make_list(project_a)
        _make_task(project_a, task_list, 'Payload shape task')

        api_client.force_authenticate(user=owner)
        response = api_client.get(
            reverse('task-list'), {'project': project_a.id}
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        assert 'results' in body
        assert 'tasks' not in body
        assert 'statistics' in body
        # M-4: pagination keys are now top-level (not nested under 'pagination')
        assert 'count' in body
        assert body['count'] == 1
        assert 'pagination' not in body
        assert len(body['results']) == 1
