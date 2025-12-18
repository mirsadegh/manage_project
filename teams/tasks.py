# teams/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import TeamInvitation, Team, TeamMeeting


@shared_task
def expire_old_invitations():
    """
    ⏰ Expire old team invitations.
    Runs daily to clean up expired invitations.
    """
    expired_count = TeamInvitation.objects.filter(
        status=TeamInvitation.Status.PENDING,
        expires_at__lt=timezone.now()
    ).update(status=TeamInvitation.Status.EXPIRED)
    
    return f'✅ Expired {expired_count} team invitations'


@shared_task
def send_meeting_reminders():
    """
    📧 Send meeting reminders 1 hour before meeting.
    Runs every hour.
    """
    one_hour_from_now = timezone.now() + timedelta(hours=1)
    two_hours_from_now = timezone.now() + timedelta(hours=2)
    
    upcoming_meetings = TeamMeeting.objects.filter(
        scheduled_at__gte=one_hour_from_now,
        scheduled_at__lt=two_hours_from_now,
        is_completed=False
    )
    
    reminders_sent = 0
    
    for meeting in upcoming_meetings:
        from notifications.models import Notification
        
        for attendee in meeting.attendees.all():
            Notification.objects.create(
                recipient=attendee,
                notification_type='STATUS_CHANGE',
                title='📅 Meeting Reminder',
                message=f'Meeting "{meeting.title}" starts in 1 hour',
                content_object=meeting
            )
            reminders_sent += 1
    
    return f'📧 Sent {reminders_sent} meeting reminders'


@shared_task
def update_team_stats():
    """
    📊 Update team statistics.
    Runs weekly to update performance metrics.
    """
    teams = Team.objects.filter(is_active=True)
    
    for team in teams:
        # Update project counts
        from projects.models import Project
        
        total_projects = Project.objects.filter(
            assigned_teams__team=team
        ).count()
        
        completed_projects = Project.objects.filter(
            assigned_teams__team=team,
            status='COMPLETED'
        ).count()
        
        team.total_projects = total_projects
        team.completed_projects = completed_projects
        team.save(update_fields=['total_projects', 'completed_projects'])
    
    return f'📊 Updated stats for {teams.count()} teams'