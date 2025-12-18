# teams/permissions.py

from rest_framework import permissions


class IsTeamLeader(permissions.BasePermission):
    """
    🔐 Permission to check if user is a team leader.
    """
    
    message = "❌ Only team leaders can perform this action."
    
    def has_object_permission(self, request, view, obj):
        # Admins bypass check
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return True
        
        # Get team object
        if hasattr(obj, 'team'):
            team = obj.team
        else:
            team = obj
        
        # Check if user is team leader
        return team.is_leader(request.user)


class IsTeamMember(permissions.BasePermission):
    """
    👥 Permission to check if user is a team member.
    """
    
    message = "❌ You must be a team member to access this resource."
    
    def has_object_permission(self, request, view, obj):
        # Admins bypass check
        if request.user.is_superuser or request.user.role == 'ADMIN':
            return True
        
        # Get team object
        if hasattr(obj, 'team'):
            team = obj.team
        else:
            team = obj
        
        # Check if user is member or team is public
        return team.members.filter(id=request.user.id).exists() or team.is_public


class CanManageTeamMeeting(permissions.BasePermission):
    """
    📅 Permission to manage team meetings.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions
        if request.method in permissions.SAFE_METHODS:
            return IsTeamMember().has_object_permission(request, view, obj)
        
        # Write permissions - organizer or team leader
        return (
            obj.organizer == request.user or
            obj.team.is_leader(request.user) or
            request.user.role == 'ADMIN'
        )