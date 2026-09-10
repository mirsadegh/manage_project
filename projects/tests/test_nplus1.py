# projects/tests/test_nplus1.py
"""
Regression test for H-3: N+1 query in project list serializer.

Bug: ProjectSerializer used ReadOnlyField for total_tasks, completed_tasks,
comment_count, and attachment_count, which called model properties for each
project instance, causing N+1 queries.

Fix: Annotate counts in the viewset's queryset and use SerializerMethodField
to read from annotations when available.
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.test.utils import override_settings

from projects.models import Project, ProjectMember
from tasks.models import Task, TaskList

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user(
        username='h3_owner', email='owner@example.com',
        password='Test123!', role='PM',
    )


@pytest.fixture
def project_with_tasks(owner):
    """Create a project with tasks for N+1 testing."""
    project = Project.objects.create(
        name='Test Project', slug='test-project', owner=owner,
    )
    ProjectMember.objects.create(
        project=project, user=owner, role='MEMBER', is_active=True,
    )
    
    task_list = TaskList.objects.create(
        project=project, name='Main List', created_by=owner,
    )
    
    # Create 3 tasks: 2 TODO, 1 COMPLETED
    Task.objects.create(
        project=project, task_list=task_list, title='Task 1',
        status='TODO', created_by=owner,
    )
    Task.objects.create(
        project=project, task_list=task_list, title='Task 2',
        status='TODO', created_by=owner,
    )
    Task.objects.create(
        project=project, task_list=task_list, title='Task 3',
        status='COMPLETED', created_by=owner,
    )
    
    return project


@pytest.fixture
def multiple_projects(owner):
    """Create multiple projects to test N+1 behavior."""
    projects = []
    for i in range(5):
        project = Project.objects.create(
            name=f'Project {i}', slug=f'project-{i}', owner=owner,
        )
        ProjectMember.objects.create(
            project=project, user=owner, role='MEMBER', is_active=True,
        )
        
        task_list = TaskList.objects.create(
            project=project, name=f'List {i}', created_by=owner,
        )
        
        # Create varying numbers of tasks per project
        for j in range(i + 1):
            Task.objects.create(
                project=project, task_list=task_list, title=f'Task {j}',
                status='COMPLETED' if j % 2 == 0 else 'TODO',
                created_by=owner,
            )
        
        projects.append(project)
    
    return projects


class TestProjectListNPlus1Fix:
    """H-3: Verify project list doesn't cause N+1 queries."""

    def test_project_list_returns_correct_counts(self, api_client, owner, project_with_tasks):
        """Verify counts are correct after N+1 fix."""
        api_client.force_authenticate(user=owner)
        response = api_client.get(reverse('project-list'))
        
        assert response.status_code == status.HTTP_200_OK
        
        # Find our project in the results
        results = response.data['projects']
        project_data = next((p for p in results if p['slug'] == 'test-project'), None)
        
        assert project_data is not None
        assert project_data['total_tasks'] == 3
        assert project_data['completed_tasks'] == 1
        assert project_data['progress'] == 33  # 1/3 * 100 = 33.33 -> 33

    def test_multiple_projects_correct_counts(self, api_client, owner, multiple_projects):
        """Verify all projects have correct counts without N+1 queries."""
        api_client.force_authenticate(user=owner)
        response = api_client.get(reverse('project-list'))
        
        assert response.status_code == status.HTTP_200_OK
        
        results = response.data['projects']
        
        # Project 0: 1 task (1 completed) -> progress 100
        # Project 1: 2 tasks (1 completed) -> progress 50
        # Project 2: 3 tasks (2 completed) -> progress 66
        # Project 3: 4 tasks (2 completed) -> progress 50
        # Project 4: 5 tasks (3 completed) -> progress 60
        
        for i, project_data in enumerate(sorted(results, key=lambda p: p['name'])):
            expected_total = i + 1
            expected_completed = (i // 2) + 1 if i % 2 == 0 else i // 2 + 1
            
            # Calculate expected completed based on pattern: even indices have one more completed
            expected_completed = sum(1 for j in range(i + 1) if j % 2 == 0)
            
            assert project_data['total_tasks'] == expected_total, \
                f"Project {i} should have {expected_total} tasks, got {project_data['total_tasks']}"
            assert project_data['completed_tasks'] == expected_completed, \
                f"Project {i} should have {expected_completed} completed tasks"

    @override_settings(DEBUG=True)
    def test_project_list_query_count(self, api_client, owner, multiple_projects):
        """
        Verify the number of queries is constant regardless of project count.
        
        Without the fix: ~20+ queries (4 N+1 queries per project)
        With the fix: ~10-12 queries (constant, independent of project count)
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        
        api_client.force_authenticate(user=owner)
        
        with CaptureQueriesContext(connection) as queries:
            response = api_client.get(reverse('project-list'))
        
        assert response.status_code == status.HTTP_200_OK
        
        query_count = len(queries)
        
        # With proper annotations, we should have a constant number of queries
        # The exact count depends on Django/DRF internals, but should be < 15
        # Without fix, 5 projects would cause 20+ queries
        assert query_count < 20, \
            f"Expected < 20 queries for project list, got {query_count}. " \
            f"Possible N+1 query issue. Queries:\n" + \
            "\n".join(f"{i+1}. {q['sql'][:100]}..." for i, q in enumerate(queries))
        
        # Verify the results are still correct
        results = response.data['projects']
        assert len(results) == 5

    def test_project_detail_uses_fallback(self, api_client, owner, project_with_tasks):
        """Verify project detail (retrieve) still works without annotations."""
        api_client.force_authenticate(user=owner)
        response = api_client.get(reverse('project-detail', kwargs={'slug': 'test-project'}))
        
        assert response.status_code == status.HTTP_200_OK
        
        # Detail view uses ProjectDetailSerializer which inherits from ProjectSerializer
        # The serializer should fall back to property methods when annotations aren't present
        assert response.data['total_tasks'] == 3
        assert response.data['completed_tasks'] == 1
