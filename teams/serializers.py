# teams/serializers.py

from rest_framework import serializers
from django.db.models import Count, Q
from .models import (
    Team, TeamMembership, TeamInvitation,
    TeamProject, TeamMeeting, TeamGoal
)
from accounts.serializers import UserSerializer
from projects.serializers import ProjectSerializer


class TeamMembershipSerializer(serializers.ModelSerializer):
    """Serializer for team memberships"""
    
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    days_in_team = serializers.ReadOnlyField()
    is_leader = serializers.ReadOnlyField()
    
    class Meta:
        model = TeamMembership
        fields = [
            'id', 'user', 'user_id', 'role', 'joined_at', 'left_at',
            'is_active', 'performance_rating', 'tasks_completed',
            'contributions', 'receive_notifications', 'days_in_team',
            'is_leader'
        ]
        read_only_fields = ['id', 'joined_at']


class TeamSerializer(serializers.ModelSerializer):
    """Serializer for teams (read)."""
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            'id', 'name', 'description', 'member_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.members.count()


class TeamCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a team (name + description)."""

    class Meta:
        model = Team
        fields = ['id', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TeamDetailSerializer(TeamSerializer):
    """Detailed team serializer with members and stats."""
    memberships = TeamMembershipSerializer(many=True, read_only=True)
    members = TeamMembershipSerializer(source='memberships', many=True, read_only=True)
    performance_stats = serializers.SerializerMethodField()

    class Meta(TeamSerializer.Meta):
        fields = TeamSerializer.Meta.fields + ['members', 'memberships', 'performance_stats']

    def get_performance_stats(self, obj):
        try:
            return obj.get_performance_stats()
        except Exception:
            return {}


class TeamInvitationSerializer(serializers.ModelSerializer):
    """Serializer for team invitations"""
    
    team = TeamSerializer(read_only=True)
    team_id = serializers.IntegerField(write_only=True)
    invited_user = UserSerializer(read_only=True)
    invited_user_id = serializers.IntegerField(write_only=True)
    invited_by = UserSerializer(read_only=True)
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = TeamInvitation
        fields = [
            'id', 'team', 'team_id', 'invited_user', 'invited_user_id',
            'invited_by', 'role', 'status', 'message', 'expires_at',
            'is_expired', 'created_at', 'responded_at'
        ]
        read_only_fields = ['id', 'invited_by', 'status', 'created_at', 'responded_at']


class TeamProjectSerializer(serializers.ModelSerializer):
    """Serializer for team-project assignments"""
    
    team = TeamSerializer(read_only=True)
    project = ProjectSerializer(read_only=True)
    assigned_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = TeamProject
        fields = [
            'id', 'team', 'project', 'assigned_at', 'assigned_by',
            'assigned_by_name', 'is_primary'
        ]
        read_only_fields = ['id', 'assigned_at']
    
    def get_assigned_by_name(self, obj):
        if obj.assigned_by:
            return obj.assigned_by.get_full_name()
        return None


class TeamMeetingSerializer(serializers.ModelSerializer):
    """Serializer for team meetings"""
    
    team = TeamSerializer(read_only=True)
    organizer = UserSerializer(read_only=True)
    attendees = UserSerializer(many=True, read_only=True)
    attendee_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    is_upcoming = serializers.ReadOnlyField()
    is_past = serializers.ReadOnlyField()
    
    class Meta:
        model = TeamMeeting
        fields = [
            'id', 'team', 'title', 'meeting_type', 'description',
            'scheduled_at', 'duration_minutes', 'location',
            'attendees', 'attendee_ids', 'organizer', 'agenda',
            'notes', 'action_items', 'is_completed', 'completed_at',
            'is_upcoming', 'is_past', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TeamGoalSerializer(serializers.ModelSerializer):
    """Serializer for team goals"""
    
    team = TeamSerializer(read_only=True)
    owner = UserSerializer(read_only=True)
    owner_id = serializers.IntegerField(write_only=True, required=False)
    is_overdue = serializers.ReadOnlyField()
    
    class Meta:
        model = TeamGoal
        fields = [
            'id', 'team', 'title', 'description', 'status', 'progress',
            'start_date', 'target_date', 'completed_date',
            'owner', 'owner_id', 'target_value', 'current_value',
            'is_overdue', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']