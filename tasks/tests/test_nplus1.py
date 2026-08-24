import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from tasks.tests.factories import TaskListFactory, TaskFactory
from accounts.tests.factories import UserFactory

User = get_user_model()


def _list_tasklists(client):
    with CaptureQueriesContext(connection) as ctx:
        resp = client.get('/api/tasks/task-lists/')
    return len(ctx.captured_queries), resp


@pytest.mark.django_db
def test_tasklist_list_no_nplus1():
    """Listing task lists must not trigger one query per list (task_count)."""
    # Small set
    for _ in range(2):
        tl = TaskListFactory()
        TaskFactory(task_list=tl)
    client = APIClient()
    client.force_authenticate(UserFactory())
    q_small, resp = _list_tasklists(client)
    assert resp.status_code == 200

    # Larger set sharing the same authenticated client/DB
    for _ in range(8):
        tl = TaskListFactory()
        TaskFactory(task_list=tl)
    q_large, resp = _list_tasklists(client)
    assert resp.status_code == 200

    # Query count must not scale with the number of task lists (N+1 fixed).
    assert q_large - q_small <= 2
