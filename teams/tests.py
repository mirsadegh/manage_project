# teams/tests.py

from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from accounts.models import CustomUser
from .models import Team, TeamMembership, TeamInvitation


class TeamModelTests(TestCase):
    """Test Team model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!',
            role='PM'
        )
        self.team = Team.objects.create(
            name='Development Team',
            description='Main dev team',
            lead=self.user
        )
    
    def test_team_creation(self):
        """Test creating a team"""
        self.assertEqual(self.team.name, 'Development Team')
        self.assertEqual(self.team.lead, self.user)
        self.assertTrue(self.team.is_active)
    
    def test_team_str(self):
        """Test team string representation"""
        self.assertEqual(str(self.team), 'Development Team')
    
    def test_member_count(self):
        """Test member count property"""
        # Add members
        user2 = CustomUser.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='Test123!'
        )
        TeamMembership.objects.create(team=self.team, user=user2)
        
        self.assertEqual(self.team.member_count, 1)


class TeamMembershipTests(TestCase):
    """Test TeamMembership model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!'
        )
        self.team = Team.objects.create(name='Test Team')
    
    def test_membership_creation(self):
        """Test creating a membership"""
        membership = TeamMembership.objects.create(
            team=self.team,
            user=self.user,
            role=TeamMembership.Role.MEMBER
        )
        
        self.assertEqual(membership.team, self.team)
        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.role, TeamMembership.Role.MEMBER)
        self.assertTrue(membership.is_active)
    
    def test_unique_membership(self):
        """Test that a user can't join the same team twice"""
        TeamMembership.objects.create(team=self.team, user=self.user)
        
        with self.assertRaises(Exception):
            TeamMembership.objects.create(team=self.team, user=self.user)


class TeamAPITests(APITestCase):
    """Test Team API endpoints"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!',
            role='PM'
        )
        self.client.force_authenticate(user=self.user)
        
        self.team = Team.objects.create(
            name='Test Team',
            lead=self.user
        )
        TeamMembership.objects.create(team=self.team, user=self.user)
        
        self.team_list_url = reverse('team-list')
        self.team_detail_url = reverse('team-detail', kwargs={'pk': self.team.id})
    
    def test_list_teams(self):
        """Test listing teams"""
        response = self.client.get(self.team_list_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_create_team(self):
        """Test creating a team"""
        data = {
            'name': 'New Team',
            'description': 'A new team',
            'lead_id': self.user.id
        }
        response = self.client.post(self.team_list_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Team.objects.count(), 2)
    
    def test_get_team_detail(self):
        """Test getting team details"""
        response = self.client.get(self.team_detail_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Team')
    
    def test_add_member(self):
        """Test adding a member to team"""
        new_user = CustomUser.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='Test123!'
        )
        
        url = reverse('team-add-member', kwargs={'pk': self.team.id})
        data = {
            'user_id': new_user.id,
            'role': 'MEMBER'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.team.memberships.count(), 2)


class TeamInvitationTests(APITestCase):
    """Test TeamInvitation functionality"""
    
    def setUp(self):
        self.inviter = CustomUser.objects.create_user(
            username='inviter',
            email='inviter@example.com',
            password='Test123!',
            role='PM'
        )
        self.invitee = CustomUser.objects.create_user(
            username='invitee',
            email='invitee@example.com',
            password='Test123!'
        )
        self.team = Team.objects.create(name='Test Team', lead=self.inviter)
        
        self.client.force_authenticate(user=self.inviter)
    
    def test_send_invitation(self):
        """Test sending a team invitation"""
        url = reverse('team-invite', kwargs={'pk': self.team.id})
        data = {
            'invited_user_id': self.invitee.id,
            'role': 'MEMBER',
            'message': 'Join our team!'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TeamInvitation.objects.count(), 1)
    
    def test_accept_invitation(self):
        """Test accepting an invitation"""
        invitation = TeamInvitation.objects.create(
            team=self.team,
            invited_user=self.invitee,
            invited_by=self.inviter,
            role=TeamMembership.Role.MEMBER
        )
        
        self.client.force_authenticate(user=self.invitee)
        url = reverse('team-invitation-accept', kwargs={'pk': invitation.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, TeamInvitation.Status.ACCEPTED)
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=self.invitee).exists())