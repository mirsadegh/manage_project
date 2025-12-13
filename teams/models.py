
from django.db import models
from django.conf import settings


class Team(models.Model):
    """
    Teams within the organization.
    Groups of users working together on multiple projects.
    """
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Team name"
    )
    description = models.TextField(
        blank=True,
        help_text="Team description and purpose"
    )
    
    # Team leadership
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_teams',
        help_text="Team lead/manager"
    )
    
    # Team settings
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this team is active"
    )
    
    # Many-to-many relationship with users through TeamMembership
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='TeamMembership',
        related_name='teams',
        help_text="Team members"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Team'
        verbose_name_plural = 'Teams'
    
    def __str__(self):
        return self.name
    
    @property
    def member_count(self):
        """Get total number of team members"""
        return self.memberships.count()
    
    @property
    def active_projects(self):
        """Get active projects assigned to this team"""
        from projects.models import Project
        # Projects where team members are involved
        return Project.objects.filter(
            members__user__in=self.members.all(),
            is_active=True
        ).distinct()


class TeamMembership(models.Model):
    """
    Team membership with roles.
    Intermediate model for Team <-> User relationship.
    """
    
    class Role(models.TextChoices):
        LEAD = 'LEAD', 'Team Lead'
        SENIOR = 'SENIOR', 'Senior Member'
        MEMBER = 'MEMBER', 'Member'
        JUNIOR = 'JUNIOR', 'Junior Member'
    
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_memberships'
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER
    )
    
    # Membership details
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this membership is currently active"
    )
    
    class Meta:
        unique_together = ['team', 'user']
        ordering = ['joined_at']
        verbose_name = 'Team Membership'
        verbose_name_plural = 'Team Memberships'
    
    def __str__(self):
        return f"{self.user.username} - {self.team.name} ({self.role})"


class TeamInvitation(models.Model):
    """
    Invitations to join teams.
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        DECLINED = 'DECLINED', 'Declined'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='invitations'
    )
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_invitations'
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_team_invitations'
    )
    
    role = models.CharField(
        max_length=10,
        choices=TeamMembership.Role.choices,
        default=TeamMembership.Role.MEMBER
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    message = models.TextField(
        blank=True,
        help_text="Optional invitation message"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['team', 'invited_user', 'status']
        ordering = ['-created_at']
        verbose_name = 'Team Invitation'
        verbose_name_plural = 'Team Invitations'
    
    def __str__(self):
        return f"Invitation to {self.invited_user.username} for {self.team.name} - {self.status}"
    
    def accept(self):
        """Accept the invitation and create membership"""
        from django.utils import timezone
        
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending invitations can be accepted")
        
        self.status = self.Status.ACCEPTED
        self.responded_at = timezone.now()
        self.save()
        
        # Create team membership
        TeamMembership.objects.create(
            team=self.team,
            user=self.invited_user,
            role=self.role
        )
    
    def decline(self):
        """Decline the invitation"""
        from django.utils import timezone
        
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending invitations can be declined")
        
        self.status = self.Status.DECLINED
        self.responded_at = timezone.now()
        self.save()