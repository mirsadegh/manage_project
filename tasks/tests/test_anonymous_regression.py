from rest_framework.test import APITestCase
from django.urls import reverse

from tasks.tests.factories import TaskFactory


class AnonymousTaskPermissionRegressionTest(APITestCase):
    """B7: unauthenticated requests must 401/403, never 500 (AnonymousUser has no .role)."""

    def test_update_task_anonymous_returns_401_not_500(self):
        task = TaskFactory()
        url = reverse('task-detail', kwargs={'pk': task.pk})
        response = self.client.patch(url, {'title': 'x'}, format='json')
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 500)

    def test_destroy_task_anonymous_returns_401_not_500(self):
        task = TaskFactory()
        url = reverse('task-detail', kwargs={'pk': task.pk})
        response = self.client.delete(url)
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 500)
