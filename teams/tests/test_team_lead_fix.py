import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from teams.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def users():
    lead = User.objects.create_user(email='lead@example.com', username='lead',
                                    password='pw', role='TL')
    member = User.objects.create_user(email='m@example.com', username='m',
                                        password='pw', role='DEV')
    return lead, member


@pytest.fixture
def team(users):
    lead, _ = users
    t = Team.objects.create(name='T1')
    TeamMembership.objects.create(team=t, user=lead, role=TeamMembership.Role.LEAD,
                                    is_active=True)
    return t


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c

@pytest.mark.django_db
def test_remove_normal_member_returns_204(team, users):
    lead, member = users
    TeamMembership.objects.create(team=team, user=member,
                                    role=TeamMembership.Role.MEMBER, is_active=True)
    membership_id = team.memberships.get(user=member).id
    resp = _client(lead).delete(f'/api/teams/teams/{team.id}/remove_member/{membership_id}/')
    assert resp.status_code == 204

@pytest.mark.django_db  
def test_cannot_remove_team_lead(team, users):
    lead, _ = users
    lead_membership_id = team.memberships.get(user=lead).id
    resp = _client(lead).delete(f'/api/teams/teams/{team.id}/remove_member/{lead_membership_id}/')
    assert resp.status_code == 400

@pytest.mark.django_db 
def test_join_notifies_leads_and_returns_200(users):
    lead, _ = users
    joiner = User.objects.create_user(email='j@example.com', username='j',
                                        password='pw', role='DEV')
    t = Team.objects.create(name='T2', allow_self_join=True)
    TeamMembership.objects.create(team=t, user=lead, role=TeamMembership.Role.LEAD,
                                    is_active=True)
    resp = _client(joiner).post(f'/api/teams/teams/{t.id}/join/')
    assert resp.status_code == 200
    
    
    