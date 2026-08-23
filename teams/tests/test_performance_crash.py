import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from teams.tests.factories import TeamFactory, TeamMembershipFactory

User = get_user_model()


@pytest.mark.django_db
def test_team_performance_returns_200():
    """Team performance endpoint must not 500 on a missing model method."""
    user = User.objects.create_user(
        email='u@example.com', username='u', password='pw', role='DEV'
    )
    team = TeamFactory()
    TeamMembershipFactory(team=team, user=user)
    client = APIClient()
    client.force_authenticate(user)
    resp = client.get(f'/api/teams/teams/{team.id}/performance/')
    assert resp.status_code == 200
    assert 'team_stats' in resp.data
