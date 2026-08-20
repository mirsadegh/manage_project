from rest_framework.test import APITestCase
from django.urls import reverse

from accounts.tests.factories import UserFactory
from files.models import Attachment


class AttachmentStatsRegressionTest(APITestCase):
    """B1: /api/files/attachments/stats/ must not 500 on a missing import."""

    def test_stats_endpoint_returns_200(self):
        user = UserFactory()
        self.client.force_authenticate(user=user)

        url = reverse("attachment-stats")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("total_files", response.data)
