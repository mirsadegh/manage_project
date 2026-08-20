# teams/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count, Avg
from django.utils import timezone
from .models import (
    Team, TeamMembership, TeamInvitation,
    TeamProject
)
from .serializers import (
    TeamSerializer, TeamDetailSerializer, TeamCreateSerializer,
    TeamMembershipSerializer, TeamInvitationSerializer,
    TeamProjectSerializer, TeamMeetingSerializer,
    TeamGoalSerializer
)
from .permissions import IsTeamLeader, IsTeamMember


class TeamViewSet(viewsets.ModelViewSet):
    """
    Complete team management viewset.
    
    Endpoints:
    - GET /teams/ - List all teams
    - POST /teams/ - Create a team
    - GET /teams/{id}/ - Get team detail
    - PUT/PATCH /teams/{id}/ - Update team
    - DELETE /teams/{id}/ - Delete team
    - POST /teams/{id}/add_member/ - Add member
    - DELETE /teams/{id}/remove_member/{membership_id}/ - Remove member
    - POST /teams/{id}/invite/ - Send invitation
    - POST /teams/{id}/join/ - Join team (if self-join allowed)
    - GET /teams/{id}/projects/ - Get team projects
    - POST /teams/{id}/assign_project/ - Assign project to team
    - GET /teams/{id}/meetings/ - Get team meetings
    - POST /teams/{id}/schedule_meeting/ - Schedule meeting
    - GET /teams/{id}/goals/ - Get team goals
    - POST /teams/{id}/create_goal/ - Create team goal
    - GET /teams/{id}/performance/ - Get performance report
    """
    
    queryset = Team.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return TeamCreateSerializer
        if self.action == 'retrieve':
            return TeamDetailSerializer
        return TeamSerializer
    
    def get_queryset(self):
        """Filter teams based on user access"""
        user = self.request.user
        
        if user.is_superuser or user.role == 'ADMIN':
            return Team.objects.all()
        
        # Users see teams they're members of
        return Team.objects.filter(
            Q(members=user)
        ).distinct()
    
    
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        """➕ Add a member to the team"""
        team = self.get_object()
        
        # 🔐 Check if user is team leader
        if not team.is_leader(request.user):
            return Response(
                {'error': '❌ Only team leaders can add members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # 📊 Check if team is full
        if team.is_full:
            return Response(
                {'error': '⚠️ Team has reached maximum capacity'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = TeamMembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_id = serializer.validated_data['user_id']
        
        # ✅ Check if user is already a member
        if TeamMembership.objects.filter(
            team=team,
            user_id=user_id,
            is_active=True
        ).exists():
            return Response(
                {'error': '⚠️ User is already a team member'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 💾 Add member
                
        from accounts.models import CustomUser
        user = CustomUser.objects.get(id=user_id)
        membership = team.add_member(
            user=user,
            role=serializer.validated_data['role'],
            added_by=request.user
        )
        
        # 📧 Send notification
        from notifications.models import Notification
        Notification.objects.create(
            recipient=membership.user,
            notification_type='INVITED',
            title='✅ Added to Team',
            message=f'You have been added to team "{team.name}"',
            content_object=team
        )
        
        return Response(
            TeamMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['delete'], url_path='remove_member/(?P<membership_id>[^/.]+)')
    def remove_member(self, request, slug=None, membership_id=None):
        """➖ Remove a member from the team"""
        team = self.get_object()
        
        # 🔐 Check permissions
        if not team.is_leader(request.user):
            return Response(
                {'error': '❌ Only team leaders can remove members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            membership = team.memberships.get(id=membership_id)
            
            # 🚫 Prevent removing the team lead
            if membership.user == team.lead:
                return Response(
                    {'error': '⚠️ Cannot remove team lead'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 🗑️ Remove member
            team.remove_member(membership.user)
            
            # 📧 Notify removed member
            from notifications.models import Notification
            Notification.objects.create(
                recipient=membership.user,
                notification_type='STATUS_CHANGE',
                title='Removed from Team',
                message=f'You have been removed from team "{team.name}"',
                content_object=team
            )
            
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        except TeamMembership.DoesNotExist:
            return Response(
                {'error': '❌ Member not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """📨 Send invitation to join team"""
        team = self.get_object()
        
        # 🔐 Check permissions
        if not team.is_leader(request.user):
            return Response(
                {'error': '❌ Only team leaders can send invitations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        data = request.data.copy()
        data['team_id'] = team.id
        serializer = TeamInvitationSerializer(data=data)
        serializer.is_valid(raise_exception=True)   
        
        
        # 📊 Check if team is full
        if team.is_full:
            return Response(
                {'error': '⚠️ Team has reached maximum capacity'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invitation = serializer.save(
            team=team,
            invited_by=request.user
        )
        
        # 📧 Send notification
        from notifications.models import Notification
        Notification.objects.create(
            recipient=invitation.invited_user,
            notification_type='PROJECT_INVITE',
            title='📨 Team Invitation',
            message=f'{request.user.get_full_name()} invited you to join team "{team.name}"',
            content_object=invitation
        )
        
        return Response(
            TeamInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def join(self, request, slug=None):
        """🤝 Join team (if self-join is allowed)"""
        team = self.get_object()
        
        # ✅ Check if self-join is allowed
        if not team.allow_self_join:
            return Response(
                {'error': '⚠️ This team requires an invitation to join'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # 📊 Check if team is full
        if team.is_full:
            return Response(
                {'error': '⚠️ Team has reached maximum capacity'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # ✅ Check if already a member
        if TeamMembership.objects.filter(
            team=team,
            user=request.user,
            is_active=True
        ).exists():
            return Response(
                {'error': '⚠️ You are already a member of this team'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 💾 Add user to team
        membership = team.add_member(
            user=request.user,
            role=TeamMembership.Role.MEMBER
        )
        
        # 📧 Notify team lead
        from notifications.models import Notification
        if team.lead:
            Notification.objects.create(
                recipient=team.lead,
                notification_type='JOINED',
                title='👤 New Team Member',
                message=f'{request.user.get_full_name()} joined team "{team.name}"',
                content_object=team
            )
        
        return Response({
            'message': f'✅ Successfully joined team "{team.name}"',
            'membership': TeamMembershipSerializer(membership).data
        })
    
    @action(detail=True, methods=['get'])
    def projects(self, request, slug=None):
        """📊 Get team projects"""
        team = self.get_object()
        team_projects = team.team_projects.all()
        
        serializer = TeamProjectSerializer(
            team_projects,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def assign_project(self, request, slug=None):
        """🎯 Assign project to team"""
        team = self.get_object()
        
        # 🔐 Check permissions
        if not team.is_leader(request.user):
            return Response(
                {'error': '❌ Only team leaders can assign projects'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        project_id = request.data.get('project_id')
        is_primary = request.data.get('is_primary', False)
        
        if not project_id:
            return Response(
                {'error': '⚠️ project_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from projects.models import Project
            project = Project.objects.get(id=project_id)
            
            # ✅ Check if already assigned
            if TeamProject.objects.filter(team=team, project=project).exists():
                return Response(
                    {'error': '⚠️ Project already assigned to this team'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 💾 Create assignment
            team_project = TeamProject.objects.create(
                team=team,
                project=project,
                assigned_by=request.user,
                is_primary=is_primary
            )
            
            # 📊 Update team stats
            team.total_projects += 1
            team.save(update_fields=['total_projects'])
            
            return Response(
                TeamProjectSerializer(team_project).data,
                status=status.HTTP_201_CREATED
            )
            
        except Project.DoesNotExist:
            return Response(
                {'error': '❌ Project not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def meetings(self, request, slug=None):
        """📅 Get team meetings"""
        team = self.get_object()
        
        # 🔍 Filter by status
        status_filter = request.query_params.get('status')
        meetings = team.meetings.all()
        
        if status_filter == 'upcoming':
            meetings = meetings.filter(
                scheduled_at__gt=timezone.now(),
                is_completed=False
            )
        elif status_filter == 'past':
            meetings = meetings.filter(
                Q(scheduled_at__lt=timezone.now()) | Q(is_completed=True)
            )
        
        serializer = TeamMeetingSerializer(
            meetings,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def schedule_meeting(self, request, slug=None):
        """📅 Schedule a team meeting"""
        team = self.get_object()
        
        # 🔐 Check permissions
        if not team.is_leader(request.user):
            return Response(
                {'error': '❌ Only team leaders can schedule meetings'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = TeamMeetingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        meeting = serializer.save(
            team=team,
            organizer=request.user
        )
        
        # 📧 Notify attendees
        from notifications.models import Notification
        attendee_ids = request.data.get('attendee_ids', [])
        from accounts.models import CustomUser
        
        for user_id in attendee_ids:
            try:
                user = CustomUser.objects.get(id=user_id)
                Notification.objects.create(
                    recipient=user,
                    notification_type='STATUS_CHANGE',
                    title='📅 Meeting Scheduled',
                    message=f'New meeting: {meeting.title}',
                    content_object=meeting
                )
            except CustomUser.DoesNotExist:
                pass
        
        return Response(
            TeamMeetingSerializer(meeting).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def goals(self, request, slug=None):
        """🎯 Get team goals"""
        team = self.get_object()
        
        # 🔍 Filter by status
        status_filter = request.query_params.get('status')
        goals = team.goals.all()
        
        if status_filter:
            goals = goals.filter(status=status_filter)
        
        serializer = TeamGoalSerializer(
            goals,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def create_goal(self, request, slug=None):
        """🎯 Create a team goal"""
        team = self.get_object()
        
        # 🔐 Check permissions
        if not team.is_leader(request.user):
            return Response(
                {'error': '❌ Only team leaders can create goals'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = TeamGoalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        goal = serializer.save(team=team)
        
        return Response(
            TeamGoalSerializer(goal).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['get'])
    def performance(self, request, slug=None):
        """📊 Get team performance report"""
        team = self.get_object()
        
        stats = team.get_performance_stats()
        
        # 📈 Additional metrics
        memberships = team.memberships.filter(is_active=True)
        
        # 👥 Top performers
        top_performers = memberships.order_by('-tasks_completed')[:5]
        
        # 📅 Recent activity
        from activity.models import ActivityLog
        recent_activities = ActivityLog.objects.filter(
            user__in=team.members.all()
        ).select_related('user')[:10]
        
        return Response({
            'team_stats': stats,
            'top_performers': TeamMembershipSerializer(top_performers, many=True).data,
            'recent_activities': [{
                'user': activity.user.username,
                'action': activity.action,
                'description': activity.description,
                'created_at': activity.created_at
            } for activity in recent_activities]
        })
    
    @action(detail=False, methods=['get'])
    def my_teams(self, request):
        """👤 Get current user's teams"""
        teams = Team.objects.filter(
            members=request.user
        ).annotate(
            active_members=Count('memberships', filter=Q(memberships__is_active=True))
        )
        
        serializer = TeamSerializer(teams, many=True)
        return Response(serializer.data)


class TeamInvitationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    📨 Team invitation management.
    
    Endpoints:
    - GET /team-invitations/ - List user's invitations
    - GET /team-invitations/{id}/ - Get invitation detail
    - POST /team-invitations/{id}/accept/ - Accept invitation
    - POST /team-invitations/{id}/decline/ - Decline invitation
    """
    
    serializer_class = TeamInvitationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get user's pending invitations"""
        return TeamInvitation.objects.filter(
            invited_user=self.request.user,
            status=TeamInvitation.Status.PENDING
        ).select_related('team', 'invited_by')
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """✅ Accept team invitation"""
        invitation = self.get_object()
        
        try:
            invitation.accept()
            return Response({
                'message': f'✅ You have joined team "{invitation.team.name}"'
            })
        except ValueError as e:
            return Response(
                {'error': f'⚠️ {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        """❌ Decline team invitation"""
        invitation = self.get_object()
        
        try:
            invitation.decline()
            return Response({
                'message': '❌ Invitation declined'
            })
        except ValueError as e:
            return Response(
                {'error': f'⚠️ {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
