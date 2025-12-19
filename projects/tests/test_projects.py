# projects/tests/test_projects.py

import pytest
from django.urls import reverse
from rest_framework import status
from projects.models import Project, ProjectMember


@pytest.mark.django_db
class TestProjectCreation:
    """Test project creation permissions"""
    
    def test_admin_can_create_project(self, api_client, admin_user):
        api_client.force_authenticate(user=admin_user)
        data = {
            'name': 'Admin Project',
            'description': 'Test project',
            'status': 'PLANNING',
            'priority': 'HIGH'
        }
        response = api_client.post(reverse('project-list'), data)
        assert response.status_code == status.HTTP_201_CREATED
        assert Project.objects.count() == 1
    
    def test_manager_can_create_project(self, api_client, manager_user):
        api_client.force_authenticate(user=manager_user)
        data = {
            'name': 'Manager Project',
            'description': 'Test project',
            'status': 'PLANNING',
            'priority': 'MEDIUM'
        }
        response = api_client.post(reverse('project-list'), data)
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_developer_cannot_create_project(self, api_client, developer_user):
        api_client.force_authenticate(user=developer_user)
        data = {
            'name': 'Dev Project',
            'description': 'Test project',
            'status': 'PLANNING',
            'priority': 'LOW'
        }
        response = api_client.post(reverse('project-list'), data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Project.objects.count() == 0


@pytest.mark.django_db
class TestProjectAccess:
    """Test project access permissions"""
    
    def test_owner_can_view_project(self, api_client, project):
        api_client.force_authenticate(user=project.owner)
        url = reverse('project-detail', kwargs={'slug': project.slug})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
    
    def test_member_can_view_project(self, api_client, project_with_members, member_user):
        api_client.force_authenticate(user=member_user)
        url = reverse('project-detail', kwargs={'slug': project_with_members.slug})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK