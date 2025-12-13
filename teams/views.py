# teams/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Team, TeamMembership, TeamInvitation
from .serializers import (
    TeamSerializer, TeamDetailSerializer,
    TeamMembershipSerializer, TeamInvitationSerializer
)


class TeamViewSet(viewsets.ModelViewSet):
    """
    ViewSet for teams.
    
    Endpoints:
    - GET /teams/ - List all teams
    - POST /teams/ - Create a team
    - GET /teams/{id}/ - Get team detail
    - PUT/PATCH /teams/{id}/ - Update team
    - DELETE /teams/{id}/ - Delete team
    - POST /teams/{id}/add_member/ - Add member
    - DELETE /teams/{id}/remove_member/{membership_id}/ - Remove member
    - POST /teams/{id}/invite/ - Send invitation
    """
    
    queryset = Team.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TeamDetailSerializer
        return TeamSerializer
    
    def get_queryset(self):
        """Filter teams based on user access"""
        user = self.request.user
        
        if user.is_superuser or user.role == 'ADMIN':
            return Team.objects.all()
        
        # Users see teams they're members of
        return Team.objects.filter(members=user)
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        """Add a member to the team"""
        team = self.get_object()
        serializer = TeamMembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Check if user is already a member
        user_id = serializer.validated_data['user_id']
        if TeamMembership.objects.filter(team=team, user_id=user_id).exists():
            return Response(
                {'error': 'User is already a team member'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        membership = serializer.save(team=team)
        return Response(
            TeamMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['delete'], url_path='remove_member/(?P<membership_id>[^/.]+)')
    def remove_member(self, request, pk=None, membership_id=None):
        """Remove a member from the team"""
        team = self.get_object()
        
        try:
            membership = team.memberships.get(id=membership_id)
            membership.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except TeamMembership.DoesNotExist:
            return Response(
                {'error': 'Membership not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """Send invitation to join team"""
        team = self.get_object()
        serializer = TeamInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        invitation = serializer.save(
            team=team,
            invited_by=request.user
        )
        
        # Send notification
        from notifications.models import Notification
        Notification.objects.create(
            recipient_id=invitation.invited_user_id,
            notification_type='PROJECT_INVITE',
            title='Team Invitation',
            message=f'{request.user.get_full_name()} invited you to join team "{team.name}"',
            content_object=invitation
        )
        
        return Response(
            TeamInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED
        )


class TeamInvitationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for team invitations.
    
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
        )
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Accept team invitation"""
        invitation = self.get_object()
        try:
            invitation.accept()
            return Response({
                'message': f'You have joined team "{invitation.team.name}"'
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

@action(detail=True, methods=['post'])
def decline(self, request, pk=None):
    """Decline team invitation"""
    invitation = self.get_object()
    
    try:
        invitation.decline()
        return Response({
            'message': 'Invitation declined'
        })
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )