
from django.contrib import admin
from .models import Team, TeamMembership, TeamInvitation


class TeamMembershipInline(admin.TabularInline):
    """Inline admin for team memberships"""
    model = TeamMembership
    extra = 1
    raw_id_fields = ['user']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'lead', 'is_active', 'member_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description', 'lead__username']
    raw_id_fields = ['lead']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [TeamMembershipInline]
    date_hierarchy = 'created_at'
    
    def member_count(self, obj):
        return obj.member_count
    member_count.short_description = 'Members'


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'team', 'role', 'is_active', 'joined_at']
    list_filter = ['role', 'is_active', 'joined_at']
    search_fields = ['user__username', 'team__name']
    raw_id_fields = ['user', 'team']
    readonly_fields = ['joined_at']
    date_hierarchy = 'joined_at'


@admin.register(TeamInvitation)
class TeamInvitationAdmin(admin.ModelAdmin):
    list_display = ['id', 'invited_user', 'team', 'status', 'invited_by', 'created_at']
    list_filter = ['status', 'role', 'created_at']
    search_fields = ['invited_user__username', 'team__name']
    raw_id_fields = ['invited_user', 'team', 'invited_by']
    readonly_fields = ['created_at', 'responded_at']
    date_hierarchy = 'created_at'