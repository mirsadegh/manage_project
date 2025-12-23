# teams/admin.py

from django.contrib import admin
from django.db import models
from django.db.models import Count
from .models import (
    Team, TeamMembership, TeamInvitation,
    TeamProject, TeamMeeting, TeamGoal
)


class TeamMembershipInline(admin.TabularInline):
    """📋 Inline admin for team memberships"""
    model = TeamMembership
    extra = 1
    raw_id_fields = ['user', 'added_by']
    readonly_fields = ['joined_at', 'days_in_team']


class TeamProjectInline(admin.TabularInline):
    """📊 Inline admin for team projects"""
    model = TeamProject
    extra = 1
    raw_id_fields = ['project', 'assigned_by']
    readonly_fields = ['assigned_at']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'member_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [TeamMembershipInline, TeamProjectInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('🎯 Basic Information', {
            'fields': ('name', 'description')
        }),
        ('🕐 Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            member_count=Count('memberships', filter=models.Q(memberships__is_active=True))
        )
        return queryset

    def member_count(self, obj):
        return obj.member_count
    member_count.short_description = '👥 Members'
    member_count.admin_order_field = 'member_count'


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'team', 'role', 'is_active',
        'performance_rating', 'joined_at'
    ]
    list_filter = ['role', 'is_active', 'joined_at']
    search_fields = ['user__username', 'team__name']
    raw_id_fields = ['user', 'team', 'added_by']
    readonly_fields = ['joined_at', 'days_in_team']
    date_hierarchy = 'joined_at'


@admin.register(TeamInvitation)
class TeamInvitationAdmin(admin.ModelAdmin):
    list_display = [
        'invited_user', 'team', 'status', 'role',
        'invited_by', 'is_expired', 'created_at'
    ]
    list_filter = ['status', 'role', 'created_at']
    search_fields = ['invited_user__username', 'team__name']
    raw_id_fields = ['invited_user', 'team', 'invited_by']
    readonly_fields = ['created_at', 'responded_at', 'is_expired']
    date_hierarchy = 'created_at'
    
    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = '⏰ Expired'


@admin.register(TeamProject)
class TeamProjectAdmin(admin.ModelAdmin):
    list_display = [
        'team', 'project', 'is_primary',
        'assigned_by', 'assigned_at'
    ]
    list_filter = ['is_primary', 'assigned_at']
    search_fields = ['team__name', 'project__name']
    raw_id_fields = ['team', 'project', 'assigned_by']
    readonly_fields = ['assigned_at']
    date_hierarchy = 'assigned_at'


@admin.register(TeamMeeting)
class TeamMeetingAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'team', 'meeting_type', 'scheduled_at',
        'duration_minutes', 'is_completed', 'organizer'
    ]
    list_filter = ['meeting_type', 'is_completed', 'scheduled_at']
    search_fields = ['title', 'team__name', 'organizer__username']
    raw_id_fields = ['team', 'organizer']
    filter_horizontal = ['attendees']
    readonly_fields = ['created_at', 'updated_at', 'is_upcoming', 'is_past']
    date_hierarchy = 'scheduled_at'
    
    fieldsets = (
        ('📅 Meeting Details', {
            'fields': ('title', 'team', 'meeting_type', 'description')
        }),
        ('⏰ Schedule', {
            'fields': ('scheduled_at', 'duration_minutes', 'location')
        }),
        ('👥 Participants', {
            'fields': ('organizer', 'attendees')
        }),
        ('📝 Content', {
            'fields': ('agenda', 'notes', 'action_items'),
            'classes': ('collapse',)
            
        }),
        ('✅ Status', {
        'fields': ('is_completed', 'completed_at')
        }),
        ('🕐 Metadata', {
        'fields': ('created_at', 'updated_at', 'is_upcoming', 'is_past')
        }),
        ) 
    

@admin.register(TeamGoal)
class TeamGoalAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'team', 'status', 'progress',
        'target_date', 'is_overdue', 'owner'
    ]
    list_filter = ['status', 'created_at', 'target_date']
    search_fields = ['title', 'team__name', 'owner__username']
    raw_id_fields = ['team', 'owner']
    readonly_fields = ['created_at', 'updated_at', 'is_overdue']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('🎯 Goal Information', {
            'fields': ('title', 'team', 'description', 'owner')
        }),
        ('📊 Progress', {
            'fields': ('status', 'progress')
        }),
        ('📅 Timeline', {
            'fields': ('start_date', 'target_date', 'completed_date', 'is_overdue')
        }),
        ('📈 Metrics', {
            'fields': ('target_value', 'current_value'),
            'classes': ('collapse',)
        }),
        ('🕐 Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def is_overdue(self, obj):
        return obj.is_overdue
    is_overdue.boolean = True
    is_overdue.short_description = '⚠️ Overdue'            
            
            