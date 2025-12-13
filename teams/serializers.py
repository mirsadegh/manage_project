# teams/serializers.py

from rest_framework import serializers
from .models import Team, TeamMembership, TeamInvitation
from accounts.serializers import UserSerializer


class TeamMembershipSerializer(serializers.ModelSerializer):
    """Serializer for team memberships"""
    
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = TeamMembership
        fields = ['id', 'user', 'user_id', 'role', 'joined_at', 'is_active']
        read_only_fields = ['id', 'joined_at']


class TeamSerializer(serializers.ModelSerializer):
    """Serializer for teams"""
    
    lead = UserSerializer(read_only=True)
    lead_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    member_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Team
        fields = [
            'id', 'name', 'description', 'lead', 'lead_id',
            'is_active', 'member_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TeamDetailSerializer(TeamSerializer):
    """Detailed serializer with members"""
    
    memberships = TeamMembershipSerializer(many=True, read_only=True)
    
    class Meta(TeamSerializer.Meta):
        fields = TeamSerializer.Meta.fields + ['memberships']


class TeamInvitationSerializer(serializers.ModelSerializer):
    """Serializer for team invitations"""
    
    team = TeamSerializer(read_only=True)
    team_id = serializers.IntegerField(write_only=True)
    invited_user = UserSerializer(read_only=True)
    invited_user_id = serializers.IntegerField(write_only=True)
    invited_by = UserSerializer(read_only=True)
    
    class Meta:
        model = TeamInvitation
        fields = [
            'id', 'team', 'team_id', 'invited_user', 'invited_user_id',
            'invited_by', 'role', 'status', 'message',
            'created_at', 'responded_at'
        ]
        read_only_fields = ['id', 'invited_by', 'status', 'created_at', 'responded_at']