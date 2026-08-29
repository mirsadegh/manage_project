# projects/tests/test_project_security.py
"""
Regression tests for PR-4 Commit 3 security fixes.

Covers:
- C-1: Project list no longer returns public projects to non-members
- C-2: get_object raises 403 instead of 404 for unauthorized access
- H-1: add_member blocks re-activation of users who left
- H-2: ProjectSerializer uses UserPublicSerializer for owner/manager
- M-1: remove_member returns 404 for inactive members
- C-3: Removed nonexistent team.is_public reference (no more 500)
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone

from projects.models import Project, ProjectMember
from teams.models import Team, TeamMembership

User = get_user_model()

pytestmark = pytest.mark.django_db


# ─── Fixtures ───

@pytest.fixture
def owner():
    return User.objects.create_user(
        username='proj_owner', email='owner@example.com',
        password='Test123!', role='PM',
    )


@pytest.fixture
def member_user(owner):
    user = User.objects.create_user(
        username='proj_member', email='member@example.com',
        password='Test123!', role='DEV',
    )
    project = Project.objects.create(
        name='Member Project', slug='member-project', owner=owner,
    )
    ProjectMember.objects.create(
        project=project, user=user, role='MEMBER', is_active=True,
    )
    return user


@pytest.fixture
def outsider():
    return User.objects.create_user(
        username='outsider', email='outsider@example.com',
        password='Test123!', role='DEV',
    )


@pytest.fixture
def admin_user():
    return User.objects.create_user(
        username='proj_admin', email='admin@example.com',
        password='Test123!', role='ADMIN',
    )


@pytest.fixture
def public_project(owner):
    return Project.objects.create(
        name='Public Project', slug='public-project',
        owner=owner, is_public=True,
    )


@pytest.fixture
def private_project(owner):
    return Project.objects.create(
        name='Private Project', slug='private-project',
        owner=owner, is_public=False,
    )


def _project_list(response_json):
    """ProjectPagination wraps data under 'projects' key."""
    return response_json.get('projects', response_json.get('results', []))


# ─── C-1: list does not enumerate public projects to non-members ───

class TestProjectListAccess:
    """C-1: Non-members must not see public projects in list."""

    def test_non_member_cannot_list_public_projects(
        self, api_client, outsider, public_project,
    ):
        api_client.force_authenticate(user=outsider)
        response = api_client.get(reverse('project-list'))
        assert response.status_code == status.HTTP_200_OK
        slugs = [p['slug'] for p in _project_list(response.json())]
        assert 'public-project' not in slugs

    def test_member_can_list_own_projects(self, api_client, member_user):
        api_client.force_authenticate(user=member_user)
        response = api_client.get(reverse('project-list'))
        assert response.status_code == status.HTTP_200_OK
        slugs = [p['slug'] for p in _project_list(response.json())]
        assert 'member-project' in slugs


# ─── C-2: get_object returns 403 for unauthorized access ───

class TestProjectObjectAccess:
    """C-2: get_object raises 403 for unauthorized, 404 for nonexistent."""

    def test_non_member_get_403_on_private_project(
        self, api_client, outsider, private_project,
    ):
        api_client.force_authenticate(user=outsider)
        response = api_client.get(
            reverse('project-detail', kwargs={'slug': private_project.slug})
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_get_404_on_nonexistent_project(self, api_client, outsider):
        api_client.force_authenticate(user=outsider)
        response = api_client.get(
            reverse('project-detail', kwargs={'slug': 'does-not-exist'})
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_public_project_accessible_by_slug(
        self, api_client, outsider, public_project,
    ):
        """Public projects are readable by slug but not enumerable in list."""
        api_client.force_authenticate(user=outsider)
        response = api_client.get(
            reverse('project-detail', kwargs={'slug': public_project.slug})
        )
        assert response.status_code == status.HTTP_200_OK

    def test_admin_bypasses_project_access(
        self, api_client, admin_user, private_project,
    ):
        api_client.force_authenticate(user=admin_user)
        response = api_client.get(
            reverse('project-detail', kwargs={'slug': private_project.slug})
        )
        assert response.status_code == status.HTTP_200_OK


# ─── H-1 + M-1: membership guards ───

class TestMembershipManagement:
    """H-1 + M-1: membership re-activation and removal guards."""

    def test_add_member_blocks_reactivation_of_left_user(
        self, api_client, owner, private_project,
    ):
        left_user = User.objects.create_user(
            username='left_user', email='left@example.com',
            password='Test123!', role='DEV',
        )
        ProjectMember.objects.create(
            project=private_project, user=left_user,
            role='MEMBER', is_active=False,
            left_at=timezone.now(),
        )
        api_client.force_authenticate(user=owner)
        response = api_client.post(
            reverse('project-add-member', kwargs={'slug': private_project.slug}),
            data={'user_id': left_user.id, 'role': 'MEMBER'},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_add_member_creates_new_membership(
        self, api_client, owner, private_project,
    ):
        new_user = User.objects.create_user(
            username='new_user', email='new@example.com',
            password='Test123!', role='DEV',
        )
        api_client.force_authenticate(user=owner)
        response = api_client.post(
            reverse('project-add-member', kwargs={'slug': private_project.slug}),
            data={'user_id': new_user.id, 'role': 'MEMBER'},
            format='json',
        )
        assert response.status_code == status.HTTP_201_CREATED
        membership = ProjectMember.objects.get(
            project=private_project, user=new_user,
        )
        assert membership.is_active is True

    def test_remove_member_inactive_returns_404(
        self, api_client, owner, private_project,
    ):
        inactive_user = User.objects.create_user(
            username='inactive_user', email='inactive@example.com',
            password='Test123!', role='DEV',
        )
        membership = ProjectMember.objects.create(
            project=private_project, user=inactive_user,
            role='MEMBER', is_active=False,
            left_at=timezone.now(),
        )
        api_client.force_authenticate(user=owner)
        response = api_client.delete(
            reverse('project-remove-member', kwargs={
                'slug': private_project.slug, 'member_id': membership.id,
            })
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_remove_member_active_succeeds(
        self, api_client, owner, private_project,
    ):
        active_user = User.objects.create_user(
            username='active_user', email='active@example.com',
            password='Test123!', role='DEV',
        )
        membership = ProjectMember.objects.create(
            project=private_project, user=active_user,
            role='MEMBER', is_active=True,
        )
        api_client.force_authenticate(user=owner)
        response = api_client.delete(
            reverse('project-remove-member', kwargs={
                'slug': private_project.slug, 'member_id': membership.id,
            })
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not ProjectMember.objects.filter(id=membership.id).exists()


# ─── H-2: ProjectSerializer uses UserPublicSerializer (no PII) ───

class TestProjectSerializerPII:
    """H-2: owner/manager fields must not leak email/phone/bio."""

    def test_project_list_owner_no_email(
        self, api_client, owner, public_project,
    ):
        api_client.force_authenticate(user=owner)
        response = api_client.get(reverse('project-list'))
        assert response.status_code == status.HTTP_200_OK
        project_data = next(
            p for p in _project_list(response.json())
            if p['slug'] == 'public-project'
        )
        assert 'email' not in project_data['owner']

    def test_project_list_manager_no_email(
        self, api_client, owner, public_project,
    ):
        public_project.manager = owner
        public_project.save()
        api_client.force_authenticate(user=owner)
        response = api_client.get(reverse('project-list'))
        project_data = next(
            p for p in _project_list(response.json())
            if p['slug'] == 'public-project'
        )
        assert 'email' not in project_data['manager']

    def test_project_detail_owner_has_public_fields(
        self, api_client, owner, public_project,
    ):
        api_client.force_authenticate(user=owner)
        response = api_client.get(
            reverse('project-detail', kwargs={'slug': public_project.slug})
        )
        owner_data = response.json()['owner']
        # Public fields present
        assert 'username' in owner_data
        assert 'first_name' in owner_data
        assert 'last_name' in owner_data
        assert 'role' in owner_data
        # PII fields absent
        assert 'email' not in owner_data
        assert 'phone_number' not in owner_data
        assert 'bio' not in owner_data


# ─── C-3: team detail no longer 500s for non-members ───

class TestTeamPermissionFix:
    """C-3: IsTeamMember no longer references nonexistent team.is_public."""

    def test_team_detail_non_member_no_500(
        self, api_client, owner, outsider,
    ):
        """Non-member accessing a team must not get a 500 error."""
        team = Team.objects.create(name='Test Team')
        TeamMembership.objects.create(
            team=team, user=owner, role='LEAD', is_active=True,
        )
        api_client.force_authenticate(user=outsider)
        response = api_client.get(
            reverse('team-detail', kwargs={'pk': team.id})
        )
        # Must not be a server error
        assert response.status_code != 500
        # Non-member gets 403 or 404 (both acceptable)
        assert response.status_code in (403, 404)

    def test_is_team_member_permission_no_attribute_error(
        self, owner, outsider,
    ):
        """Direct test: IsTeamMember.has_object_permission must not raise."""
        from rest_framework.test import APIRequestFactory
        from teams.permissions import IsTeamMember

        team = Team.objects.create(name='Permission Test Team')
        TeamMembership.objects.create(
            team=team, user=owner, role='LEAD', is_active=True,
        )

        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = outsider

        permission = IsTeamMember()
        # Must not raise AttributeError on team.is_public
        result = permission.has_object_permission(request, None, team)
        assert result is False
