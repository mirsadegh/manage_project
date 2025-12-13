
from .models import ActivityLog, ActivityFeed
from projects.models import ProjectMember


def log_activity(user, action, content_object, description, changes=None, request=None):
    """
    Log an activity and create feed items for relevant users.
    
    Args:
        user: User who performed the action
        action: Action type
        content_object: Object affected
        description: Description of action
        changes: Dict of changes (optional)
        request: HTTP request (optional)
    
    Returns:
        ActivityLog instance
    """
    # Create activity log
    activity = ActivityLog.log_activity(
        user=user,
        action=action,
        content_object=content_object,
        description=description,
        changes=changes,
        request=request
    )
    
    # Create feed items for relevant users
    create_feed_items(activity, content_object)
    
    return activity


def create_feed_items(activity, content_object):
    """
    Create activity feed items for users who should see this activity.
    
    Args:
        activity: ActivityLog instance
        content_object: The object affected by the activity
    """
    relevant_users = get_relevant_users(content_object)
    
    feed_items = []
    for user in relevant_users:
        # Don't create feed item for the user who performed the action
        if user != activity.user:
            feed_items.append(
                ActivityFeed(
                    user=user,
                    activity=activity,
                    is_important=is_important_for_user(activity, user)
                )
            )
    
    # Bulk create for efficiency
    if feed_items:
        ActivityFeed.objects.bulk_create(feed_items, ignore_conflicts=True)


def get_relevant_users(content_object):
    """
    Get users who should see activity related to this object.
    
    Args:
        content_object: The object to find relevant users for
    
    Returns:
        QuerySet of users
    """
    from accounts.models import CustomUser
    
    # Determine object type and get relevant users
    model_name = content_object.__class__.__name__
    
    if model_name == 'Task':
        # Task: assignee, creator, project members
        project = content_object.project
        user_ids = set()
        
        if content_object.assignee:
            user_ids.add(content_object.assignee.id)
        if content_object.created_by:
            user_ids.add(content_object.created_by.id)
        
        # Add project members
        member_ids = ProjectMember.objects.filter(
            project=project
        ).values_list('user_id', flat=True)
        user_ids.update(member_ids)
        
        return CustomUser.objects.filter(id__in=user_ids)
    
    elif model_name == 'Project':
        # Project: owner, manager, all members
        user_ids = {content_object.owner.id}
        
        if content_object.manager:
            user_ids.add(content_object.manager.id)
        
        member_ids = content_object.members.all().values_list('user_id', flat=True)
        user_ids.update(member_ids)
        
        return CustomUser.objects.filter(id__in=user_ids)
    
    elif model_name == 'Comment':
        # Comment: content object's relevant users + mentioned users
        return get_relevant_users(content_object.content_object)
    
    else:
        # Default: return empty queryset
        return CustomUser.objects.none()


def is_important_for_user(activity, user):
    """
    Determine if an activity is important for a specific user.
    
    Args:
        activity: ActivityLog instance
        user: User to check importance for
    
    Returns:
        bool: Whether activity is important
    """
    # Activities directly involving the user are important
    important_actions = [
        ActivityLog.Action.ASSIGNED,
        ActivityLog.Action.INVITED,
        ActivityLog.Action.COMMENTED
    ]
    
    if activity.action in important_actions:
        return True
    
    # Check if user is directly related to the content object
    content_object = activity.content_object
    if hasattr(content_object, 'assignee') and content_object.assignee == user:
        return True
    if hasattr(content_object, 'owner') and content_object.owner == user:
        return True
    
    return False