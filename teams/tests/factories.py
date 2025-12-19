import factory
from factory import fuzzy, SubFactory
from django.utils import timezone
from accounts.tests.factories import UserFactory, ManagerUserFactory
from ..models import Team, TeamMembership, TeamInvitation


class TeamFactory(factory.django.DjangoModelFactory):
    """Factory for Team model."""
    
    class Meta:
        model = Team
    
    name = factory.Faker("company")
    description = factory.Faker("paragraph", nb_sentences=3)
    lead = SubFactory(ManagerUserFactory)
    is_active = True
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)
    
    @factory.post_generation
    def members(self, create, extracted, **kwargs):
        if create and extracted:
            # Add specified members
            for user in extracted:
                TeamMembershipFactory(team=self, user=user)


class TeamWithMembersFactory(TeamFactory):
    """Factory that creates a team with multiple members."""
    
    @factory.post_generation
    def with_members(self, create, extracted, **kwargs):
        if create:
            # Create 3-8 members
            member_count = extracted if extracted is not None else fuzzy.FuzzyInteger(3, 8).fuzz()
            for _ in range(member_count):
                TeamMembershipFactory(team=self)


class InactiveTeamFactory(TeamFactory):
    """Factory for inactive teams."""
    
    is_active = False


class TeamMembershipFactory(factory.django.DjangoModelFactory):
    """Factory for TeamMembership model."""
    
    class Meta:
        model = TeamMembership
    
    team = SubFactory(TeamFactory)
    user = SubFactory(UserFactory)
    role = fuzzy.FuzzyChoice(
        [TeamMembership.Role.MEMBER, 
         TeamMembership.Role.LEAD,
         TeamMembership.Role.VIEWER]
    )
    is_active = True
    joined_at = factory.LazyFunction(timezone.now)
    left_at = None


class TeamLeadMembershipFactory(TeamMembershipFactory):
    """Factory for team lead memberships."""
    
    role = TeamMembership.Role.LEAD


class TeamViewerMembershipFactory(TeamMembershipFactory):
    """Factory for team viewer memberships."""
    
    role = TeamMembership.Role.VIEWER


class InactiveTeamMembershipFactory(TeamMembershipFactory):
    """Factory for inactive team memberships."""
    
    is_active = False
    left_at = factory.LazyFunction(timezone.now)


class TeamInvitationFactory(factory.django.DjangoModelFactory):
    """Factory for TeamInvitation model."""
    
    class Meta:
        model = TeamInvitation
    
    team = SubFactory(TeamFactory)
    invited_user = SubFactory(UserFactory)
    invited_by = SubFactory(UserFactory)
    role = fuzzy.FuzzyChoice(
        [TeamMembership.Role.MEMBER, 
         TeamMembership.Role.LEAD,
         TeamMembership.Role.VIEWER]
    )
    status = TeamInvitation.Status.PENDING
    message = factory.Faker("paragraph", nb_sentences=2)
    invited_at = factory.LazyFunction(timezone.now)
    responded_at = None
    
    @factory.post_generation
    def send_notification(self, create, extracted, **kwargs):
        """Create notification for invited user."""
        if create and self.status == TeamInvitation.Status.PENDING:
            from notifications.models import Notification
            from notifications.tests.factories import NotificationFactory
            
            NotificationFactory(
                recipient=self.invited_user,
                sender=self.invited_by,
                content_object=self.team,
                notification_type=Notification.NotificationType.PROJECT_INVITE,
                title=f"Team Invitation: {self.team.name}",
                message=f"{self.invited_by.get_full_name()} invited you to join team: {self.team.name}"
            )


class AcceptedTeamInvitationFactory(TeamInvitationFactory):
    """Factory for accepted team invitations."""
    
    status = TeamInvitation.Status.ACCEPTED
    responded_at = factory.LazyFunction(timezone.now)
    
    @factory.post_generation
    def create_membership(self, create, extracted, **kwargs):
        """Create team membership after acceptance."""
        if create:
            TeamMembershipFactory(
                team=self.team,
                user=self.invited_user,
                role=self.role
            )


class DeclinedTeamInvitationFactory(TeamInvitationFactory):
    """Factory for declined team invitations."""
    
    status = TeamInvitation.Status.DECLINED
    responded_at = factory.LazyFunction(timezone.now)


class ExpiredTeamInvitationFactory(TeamInvitationFactory):
    """Factory for expired team invitations."""
    
    status = TeamInvitation.Status.EXPIRED
    invited_at = factory.LazyFunction(
        lambda: timezone.now() - timezone.timedelta(days=8)
    )


class TeamInvitationByEmailFactory(TeamInvitationFactory):
    """Factory for team invitations by email (user not yet registered)."""
    
    invited_user = None
    email = factory.Faker("email")
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Handle email-based invitations
        if 'invited_user' not in kwargs and 'email' in kwargs:
            kwargs['invited_user'] = None
        return super()._create(model_class, *args, **kwargs)


class TeamWorkflowFactory:
    """Factory for creating team-related workflows."""
    
    @staticmethod
    def create_team_with_workflow(lead=None, member_count=5):
        """Create a complete team with lead, members, and invitations."""
        if lead is None:
            lead = ManagerUserFactory()
        
        # Create team
        team = TeamFactory(lead=lead)
        
        # Add lead as member
        TeamLeadMembershipFactory(team=team, user=lead)
        
        # Add regular members
        members = []
        for _ in range(member_count):
            user = UserFactory()
            membership = TeamMembershipFactory(team=team, user=user)
            members.append(user)
        
        # Create some pending invitations
        for _ in range(2):
            TeamInvitationFactory(team=team, invited_by=lead)
        
        return team, [lead] + members
    
    @staticmethod
    def create_team_invitation_flow(team, inviter, invitee_count=3):
        """Create multiple invitations and simulate acceptance flow."""
        invitations = []
        
        # Create invitations
        for _ in range(invitee_count):
            invitee = UserFactory()
            invitation = TeamInvitationFactory(
                team=team,
                invited_by=inviter,
                invited_user=invitee
            )
            invitations.append(invitation)
        
        # Accept first half
        for i, invitation in enumerate(invitations[:invitee_count//2]):
            invitation.status = TeamInvitation.Status.ACCEPTED
            invitation.responded_at = timezone.now()
            invitation.save()
            
            # Create membership
            TeamMembershipFactory(
                team=team,
                user=invitation.invited_user,
                role=invitation.role
            )
        
        # Decline second half
        for invitation in invitations[invitee_count//2:]:
            invitation.status = TeamInvitation.Status.DECLINED
            invitation.responded_at = timezone.now()
            invitation.save()
        
        return invitations


class UserWithTeamsFactory(UserFactory):
    """Factory that creates a user with multiple team memberships."""
    
    @factory.post_generation
    def teams(self, create, extracted, **kwargs):
        if create:
            # Create 2-4 team memberships
            team_count = fuzzy.FuzzyInteger(2, 4).fuzz()
            for _ in range(team_count):
                team = TeamFactory()
                TeamMembershipFactory(team=team, user=self)
        if extracted:
            # Add specified team memberships
            for team in extracted:
                TeamMembershipFactory(team=team, user=self)
