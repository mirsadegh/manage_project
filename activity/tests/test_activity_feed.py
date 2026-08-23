import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from projects.models import Project, ProjectMember
from teams.models import Team, TeamMembership
from activity.models import ActivityLog

User = get_user_model()

# Base path for activity endpoints
ACTIVITY_BASE = '/api/activity/activity-logs'


@pytest.fixture
def users():
    admin = User.objects.create_user(email='admin@example.com', username='admin',
                                     password='pw', role='ADMIN')
    user1 = User.objects.create_user(email='u1@example.com', username='u1',
                                     password='pw', role='DEV')
    user2 = User.objects.create_user(email='u2@example.com', username='u2',
                                     password='pw', role='DEV')
    return admin, user1, user2


@pytest.fixture
def project(users):
    _, user1, _ = users
    p = Project.objects.create(name='P1', slug='p1', owner=user1)
    return p


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _make_activity(user, target, ip='192.168.1.100'):
    """Helper to create an ActivityLog with required content_type/object_id."""
    ct = ContentType.objects.get_for_model(target)
    return ActivityLog.objects.create(
        user=user,
        action='CREATE',
        description=f'Created {target.__class__.__name__}',
        content_type=ct,       # ← Required field
        object_id=target.id,   # ← Required field
        ip_address=ip
    )


# ─────────────────────────────────────────────
# PII leak tests: ip_address
# ─────────────────────────────────────────────

@pytest.mark.django_db
def test_non_admin_does_not_see_ip_address(project, users):
    """Non-admin users must NOT see ip_address in activity feed."""
    _, user1, _ = users
    _make_activity(user1, project)

    resp = _client(user1).get(f'{ACTIVITY_BASE}/recent/')
    assert resp.status_code == 200

    results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
    assert len(results) >= 1

    # IP address should be None for non-admin
    for activity in results:
        assert activity['ip_address'] is None


@pytest.mark.django_db
def test_admin_sees_ip_address(project, users):
    """Admin users CAN see ip_address in activity feed."""
    admin, user1, _ = users
    _make_activity(user1, project)

    resp = _client(admin).get(f'{ACTIVITY_BASE}/recent/')
    assert resp.status_code == 200

    results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
    assert len(results) >= 1

    # Admin should see the IP address
    ips = [a['ip_address'] for a in results if a['ip_address']]
    assert '192.168.1.100' in ips


# ─────────────────────────────────────────────
# Scoping tests: accessible projects only
# ─────────────────────────────────────────────

@pytest.mark.django_db
def test_feed_scoped_to_accessible_projects(users):
    """Users should only see activities on projects they can access."""
    _, user1, user2 = users

    # user1 creates a project
    p1 = Project.objects.create(name='P1', slug='p1', owner=user1)

    # user2 creates another project
    p2 = Project.objects.create(name='P2', slug='p2', owner=user2)

    _make_activity(user1, p1)
    _make_activity(user2, p2)

    # user1 should see only their own activity
    resp = _client(user1).get(f'{ACTIVITY_BASE}/recent/')
    assert resp.status_code == 200

    results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
    descriptions = [a['description'] for a in results]

    # Should see their own activity
    assert any('P1' in d or 'Project' in d for d in descriptions)

    # Should NOT see user2's activity on p2
    # (unless user1 is a member of p2, which they are not)
    for activity in results:
        if activity.get('object_id') == p2.id:
            pytest.fail("user1 should not see activities on p2")


@pytest.mark.django_db
def test_user_sees_own_activities(users):
    """Users should always see their own activities."""
    _, user1, _ = users

    # user1 creates a project they don't own (edge case)
    other = User.objects.create_user(email='other@example.com', username='other',
                                     password='pw', role='PM')
    p = Project.objects.create(name='P1', slug='p1', owner=other)

    # user1 performs an action on it
    _make_activity(user1, p)

    resp = _client(user1).get(f'{ACTIVITY_BASE}/recent/')
    assert resp.status_code == 200

    results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
    # user1 should see their own activity even if they don't own the project
    user_activities = [a for a in results if a.get('user', {}).get('username') == 'u1']
    assert len(user_activities) >= 1