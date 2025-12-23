from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import timedelta


class Team(models.Model):
    """
    Teams for collaboration and project management.
    """
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='TeamMembership',
        through_fields=('team', 'user')
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Team'
        verbose_name_plural = 'Teams'
    
    def __str__(self):
        return self.name
    
    def add_member(self, user, role, added_by=None):
        """
        Add a member to the team.
        """
        TeamMembership.objects.create(
            team=self,
            user=user,
            role=role,
            added_by=added_by
        )
    
    def remove_member(self, user):
        """
        Remove a member from the team.
        """
        TeamMembership.objects.filter(team=self, user=user).delete()


class TeamMembership(models.Model):
    """
    Team membership with roles and performance tracking.
    """
    
    class Role(models.TextChoices):
        MEMBER = 'MEMBER', 'Member'
        CO_LEAD = 'CO_LEAD', 'Co-Lead'
        LEAD = 'LEAD', 'Lead'
    
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
    left_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this membership is currently active"
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='added_team_members'
    )
    
    # Performance tracking
    performance_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Performance rating (0-5)"
    )
    tasks_completed = models.IntegerField(
        default=0,
        help_text="Number of tasks completed as team member"
    )
    contributions = models.TextField(
        blank=True,
        help_text="Notable contributions to the team"
    )
    
    # Settings
    receive_notifications = models.BooleanField(
        default=True,
        help_text="Receive team notifications"
    )
    
    class Meta:
        unique_together = ['team', 'user']
        ordering = ['-joined_at']
        verbose_name = 'Team Membership'
        verbose_name_plural = 'Team Memberships'
    
    def __str__(self):
        return f"{self.user.username} - {self.team.name} ({self.role})"
    
    @property
    def days_in_team(self):
        """Get number of days in team"""
        if self.left_at:
            return (self.left_at - self.joined_at).days
        return (timezone.now() - self.joined_at).days
    
    @property
    def is_leader(self):
        """Check if member is a leader"""
        return self.role in [self.Role.LEAD, self.Role.CO_LEAD]


class TeamInvitation(models.Model):
    """
    Enhanced team invitations with expiration.
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        DECLINED = 'DECLINED', 'Declined'
        CANCELLED = 'CANCELLED', 'Cancelled'
        EXPIRED = 'EXPIRED', 'Expired'
    
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
    
    # Expiration
    expires_at = models.DateTimeField(
        help_text="When invitation expires"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['team', 'invited_user', 'status']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invited_user', 'status']),
            models.Index(fields=['expires_at', 'status']),
        ]
        verbose_name = 'Team Invitation'
        verbose_name_plural = 'Team Invitations'
    
    def __str__(self):
        return f"Invitation to {self.invited_user.username} for {self.team.name}"
    
    def save(self, *args, **kwargs):
        # Set expiration date if not set (7 days from now)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        """Check if invitation has expired"""
        return timezone.now() > self.expires_at and self.status == self.Status.PENDING
    
    def accept(self):
        """Accept the invitation"""
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending invitations can be accepted")
        
        if self.is_expired:
            self.status = self.Status.EXPIRED
            self.save()
            raise ValueError("This invitation has expired")
        
        self.status = self.Status.ACCEPTED
        self.responded_at = timezone.now()
        self.save()
        
        # Create team membership
        self.team.add_member(
            user=self.invited_user,
            role=self.role,
            added_by=self.invited_by
        )
        
        # Send notification
        from notifications.models import Notification
        Notification.objects.create(
            recipient=self.invited_by,
            notification_type='STATUS_CHANGE',
            title='Invitation Accepted',
            message=f'{self.invited_user.get_full_name()} accepted your invitation to join {self.team.name}',
            content_object=self.team
        )
    
    def decline(self):
        """Decline the invitation"""
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending invitations can be declined")
        
        self.status = self.Status.DECLINED
        self.responded_at = timezone.now()
        self.save()
        
        # Notify sender
        from notifications.models import Notification
        Notification.objects.create(
            recipient=self.invited_by,
            notification_type='STATUS_CHANGE',
            title='Invitation Declined',
            message=f'{self.invited_user.get_full_name()} declined your invitation to join {self.team.name}',
            content_object=self.team
        )
    
    def cancel(self):
        """Cancel the invitation"""
        if self.status != self.Status.PENDING:
            raise ValueError("Only pending invitations can be cancelled")
        
        self.status = self.Status.CANCELLED
        self.save()


class TeamProject(models.Model):
    """
    Link teams to projects for collaboration.
    """
    
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='team_projects'
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='assigned_teams'
    )
    
    # Assignment details
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    
    is_primary = models.BooleanField(
        default=False,
        help_text="Whether this is the primary team for the project"
    )
    
    class Meta:
        unique_together = ['team', 'project']
        ordering = ['-assigned_at']
    
    def __str__(self):
        return f"{self.team.name} - {self.project.name}"


class TeamMeeting(models.Model):
    """
    Team meetings and standups.
    """
    
    class MeetingType(models.TextChoices):
        STANDUP = 'STANDUP', 'Daily Standup'
        WEEKLY = 'WEEKLY', 'Weekly Sync'
        PLANNING = 'PLANNING', 'Sprint Planning'
        RETROSPECTIVE = 'RETRO', 'Retrospective'
        ONE_ON_ONE = '1ON1', 'One-on-One'
        ALL_HANDS = 'ALL_HANDS', 'All Hands'
    
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='meetings'
    )
    
    title = models.CharField(max_length=200)
    meeting_type = models.CharField(
        max_length=20,
        choices=MeetingType.choices,
        default=MeetingType.STANDUP
    )
    description = models.TextField(blank=True)
    
    # Schedule
    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(480)]
    )
    
    # Location
    location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Physical location or video call link"
    )
    
    # Attendees
    attendees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='team_meetings',
        blank=True
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='organized_meetings'
    )
    
    # Meeting notes
    agenda = models.TextField(
        blank=True,
        help_text="Meeting agenda"
    )
    notes = models.TextField(
        blank=True,
        help_text="Meeting notes"
    )
    action_items = models.JSONField(
        default=list,
        blank=True,
        help_text="Action items from meeting"
    )
    
    # Status
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['team', 'scheduled_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.team.name}"
    
    @property
    def is_upcoming(self):
        """Check if meeting is upcoming"""
        return not self.is_completed and self.scheduled_at > timezone.now()
    
    @property
    def is_past(self):
        """Check if meeting is in the past"""
        return self.scheduled_at < timezone.now()


class TeamGoal(models.Model):
    """
    Team goals and objectives.
    """
    
    class Status(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Not Started'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        ON_HOLD = 'ON_HOLD', 'On Hold'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='goals'
    )
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED
    )
    progress = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Progress percentage (0-100)"
    )
    
    # Timeline
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    
    # Assignment
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='owned_team_goals'
    )
    
    # Metrics
    target_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target metric value"
    )
    current_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current metric value"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.team.name}"
    
    @property
    def is_overdue(self):
        """Check if goal is overdue"""
        if not self.target_date or self.status == self.Status.COMPLETED:
            return False
        return timezone.now().date() > self.target_date
