from rest_framework.test import APITestCase
from django.urls import reverse

from projects.tests.factories import ProjectFactory


class AnonymousProjectPermissionRegressionTest(APITestCase):
    """B7: unauthenticated requests must 401/403, never 500 (AnonymousUser has no .role)."""

    def test_add_member_anonymous_returns_401_not_500(self):
        project = ProjectFactory()
        url = reverse('project-add-member', kwargs={'slug': project.slug})
        response = self.client.post(url, {'user_id': 1, 'role': 'MEMBER'}, format='json')
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 500)

    def test_destroy_project_anonymous_returns_401_not_500(self):
        project = ProjectFactory()
        url = reverse('project-detail', kwargs={'slug': project.slug})
        response = self.client.delete(url)
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 500)
