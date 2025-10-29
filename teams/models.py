from django.db import models
from django.conf import settings

class Team(models.Model):
    """Teams within organization"""
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Team lead
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='led_teams'
    )
    
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='TeamMembership',
        related_name='teams'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    """Team membership details"""
    
    class Role(models.TextChoices):
        LEAD = 'LEAD', 'Team Lead'
        MEMBER = 'MEMBER', 'Member'
    
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
    
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['team', 'user']
    
    def __str__(self):
        return f"{self.user.username} - {self.team.name}"