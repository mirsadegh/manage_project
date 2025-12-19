import factory
from factory import fuzzy, SubFactory
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from accounts.tests.factories import UserFactory
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import TaskFactory
from comments.tests.factories import CommentFactory
from ..models import ActivityLog, ActivityFeed


class ActivityLogFactory(factory.django.DjangoModelFactory):
    """Factory for ActivityLog model."""
    
    class Meta:
        model = ActivityLog
    
    user = SubFactory(UserFactory)
    action = fuzzy.FuzzyChoice(
        [ActivityLog.Action.CREATED,
         ActivityLog.Action.UPDATED,
         ActivityLog.Action.DELETED,
         ActivityLog.Action.STATUS_CHANGED,
         ActivityLog.Action.ASSIGNED,
         ActivityLog.Action.COMMENTED,
         ActivityLog.Action.ATTACHED,
         ActivityLog.Action.MENTIONED]
    )
    description = factory.Faker("sentence", nb_words=8)
    content_type = factory.LazyAttribute(lambda obj: obj._get_content_type())
    object_id = fuzzy.FuzzyInteger(1, 1000)
    changes = None
    timestamp = factory.LazyFunction(timezone.now)
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Handle content_object properly
        content_object = kwargs.pop('content_object', None)
        
        if content_object:
            instance = model_class(**kwargs)
            instance.content_object = content_object
            instance.save()
            return instance
        return super()._create(model_class, *args, **kwargs)


class ProjectActivityFactory(ActivityLogFactory):
    """Factory for project activities."""
    
    content_object = SubFactory(ProjectFactory)


class TaskActivityFactory(ActivityLogFactory):
    """Factory for task activities."""
    
    content_object = SubFactory(TaskFactory)


class CommentActivityFactory(ActivityLogFactory):
    """Factory for comment activities."""
    
    content_object = SubFactory(CommentFactory)


class StatusChangeActivityFactory(ActivityLogFactory):
    """Factory for status change activities."""
    
    action = ActivityLog.Action.STATUS_CHANGED
    changes = factory.LazyAttribute(lambda obj: {
        'field': 'status',
        'old_value': fuzzy.FuzzyChoice(['TODO', 'IN_PROGRESS']),
        'new_value': fuzzy.FuzzyChoice(['IN_PROGRESS', 'COMPLETED'])
    })


class AssignmentActivityFactory(ActivityLogFactory):
    """Factory for assignment activities."""
    
    action = ActivityLog.Action.ASSIGNED
    changes = factory.LazyAttribute(lambda obj: {
        'field': 'assignee',
        'old_value': None,
        'new_value': f"User {fuzzy.FuzzyInteger(1, 100).fuzz()}"
    })


class CommentActivityLogFactory(ActivityLogFactory):
    """Factory for comment activities."""
    
    action = ActivityLog.Action.COMMENTED


class AttachmentActivityFactory(ActivityLogFactory):
    """Factory for attachment activities."""
    
    action = ActivityLog.Action.ATTACHED


class MentionActivityFactory(ActivityLogFactory):
    """Factory for mention activities."""
    
    action = ActivityLog.Action.MENTIONED
    description = factory.LazyAttribute(
        lambda obj: f"{obj.user.get_full_name()} mentioned someone"
    )


class ActivityFeedFactory(factory.django.DjangoModelFactory):
    """Factory for ActivityFeed model."""
    
    class Meta:
        model = ActivityFeed
    
    user = SubFactory(UserFactory)
    activity = SubFactory(ActivityLogFactory)
    is_read = False
    created_at = factory.LazyFunction(timezone.now)
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Ensure activity doesn't belong to the same user (don't notify yourself)
        if 'user' in kwargs and 'activity' in kwargs:
            if kwargs['user'].id == kwargs['activity'].user.id:
                # Create a different activity for this user
                from accounts.tests.factories import UserFactory
                different_user = UserFactory()
                kwargs['activity'].user = different_user
                kwargs['activity'].save()
        
        return super()._create(model_class, *args, **kwargs)


class ReadActivityFeedFactory(ActivityFeedFactory):
    """Factory for read activity feed items."""
    
    is_read = True
    read_at = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(minutes=fuzzy.FuzzyInteger(5, 60).fuzz())
    )


class ActivityFeedWithChangesFactory(ActivityFeedFactory):
    """Factory for activity feed with change details."""
    
    activity = SubFactory(StatusChangeActivityFactory)


class ActivityBatchFactory:
    """Factory for creating batches of activities."""
    
    @staticmethod
    def create_project_activities(project, user, count=5):
        """Create multiple activities for a project."""
        activities = []
        actions = [
            ActivityLog.Action.CREATED,
            ActivityLog.Action.UPDATED,
            ActivityLog.Action.STATUS_CHANGED,
            ActivityLog.Action.COMMENTED
        ]
        
        for i in range(count):
            activity = ActivityLogFactory(
                user=user,
                content_object=project,
                action=fuzzy.FuzzyChoice(actions),
                description=f"Project activity {i+1}"
            )
            activities.append(activity)
        return activities
    
    @staticmethod
    def create_task_activities(task, user, count=3):
        """Create multiple activities for a task."""
        activities = []
        actions = [
            ActivityLog.Action.CREATED,
            ActivityLog.Action.ASSIGNED,
            ActivityLog.Action.STATUS_CHANGED,
            ActivityLog.Action.COMMENTED,
            ActivityLog.Action.ATTACHED
        ]
        
        for i in range(count):
            activity = ActivityLogFactory(
                user=user,
                content_object=task,
                action=fuzzy.FuzzyChoice(actions),
                description=f"Task activity {i+1}"
            )
            activities.append(activity)
        return activities
    
    @staticmethod
    def create_user_feed(user, activity_count=10):
        """Create activity feed for a user."""
        feed_items = []
        
        for _ in range(activity_count):
            activity = ActivityLogFactory()
            feed_item = ActivityFeedFactory(
                user=user,
                activity=activity
            )
            feed_items.append(feed_item)
        
        return feed_items
    
    @staticmethod
    def create_workflow_activities(project, creator, assignee=None):
        """Create a realistic workflow of activities."""
        if assignee is None:
            assignee = UserFactory()
        
        activities = []
        
        # Project created
        activities.append(ActivityLogFactory(
            user=creator,
            content_object=project,
            action=ActivityLog.Action.CREATED,
            description=f"Created project: {project.name}"
        ))
        
        # Create some tasks
        for i in range(3):
            task = TaskFactory(project=project, created_by=creator)
            
            # Task created
            activities.append(ActivityLogFactory(
                user=creator,
                content_object=task,
                action=ActivityLog.Action.CREATED,
                description=f"Created task: {task.title}"
            ))
            
            # Task assigned
            activities.append(ActivityLogFactory(
                user=creator,
                content_object=task,
                action=ActivityLog.Action.ASSIGNED,
                description=f"Assigned task to {assignee.get_full_name()}",
                changes={
                    'field': 'assignee',
                    'old_value': None,
                    'new_value': assignee.get_full_name()
                }
            ))
            
            # Task status changed
            activities.append(ActivityLogFactory(
                user=assignee,
                content_object=task,
                action=ActivityLog.Action.STATUS_CHANGED,
                description=f"Changed task status to IN_PROGRESS",
                changes={
                    'field': 'status',
                    'old_value': 'TODO',
                    'new_value': 'IN_PROGRESS'
                }
            ))
        
        return activities


class ActivityFeedFactory:
    """Enhanced factory for activity feed management."""
    
    @staticmethod
    def create_feed_for_users(users, activities, include_own=False):
        """Create feed items for multiple users from activities."""
        feed_items = []
        
        for activity in activities:
            for user in users:
                # Don't create feed item for activity creator unless specified
                if not include_own and user.id == activity.user.id:
                    continue
                
                feed_item = ActivityFeedFactory(
                    user=user,
                    activity=activity
                )
                feed_items.append(feed_item)
        
        return feed_items
    
    @staticmethod
    def mark_some_as_read(feed_items, ratio=0.5):
        """Mark some feed items as read based on ratio."""
        import random
        items_to_mark = int(len(feed_items) * ratio)
        
        for item in random.sample(feed_items, items_to_mark):
            item.is_read = True
            item.read_at = timezone.now() - timezone.timedelta(minutes=random.randint(5, 60))
            item.save()
        
        return feed_items
