import factory
from factory import fuzzy, SubFactory
from django.utils import timezone
from accounts.tests.factories import UserFactory
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import TaskFactory
from comments.tests.factories import CommentFactory
from ..models import Notification, NotificationPreference, NotificationTemplate


class NotificationFactory(factory.django.DjangoModelFactory):
    """Factory for Notification model."""
    
    class Meta:
        model = Notification
    
    recipient = SubFactory(UserFactory)
    sender = SubFactory(UserFactory)
    notification_type = fuzzy.FuzzyChoice(
        [Notification.NotificationType.MENTION,
         Notification.NotificationType.COMMENT,
         Notification.NotificationType.ASSIGNMENT,
         Notification.NotificationType.PROJECT_INVITE,
         Notification.NotificationType.TASK_COMPLETED,
         Notification.NotificationType.DEADLINE_REMINDER,
         Notification.NotificationType.PROJECT_UPDATE]
    )
    title = factory.Faker("sentence", nb_words=6)
    message = factory.Faker("paragraph", nb_sentences=2)
    is_read = False
    is_email_sent = False
    created_at = factory.LazyFunction(timezone.now)
    read_at = None
    email_sent_at = None
    
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


class ReadNotificationFactory(NotificationFactory):
    """Factory for read notifications."""
    
    is_read = True
    read_at = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(minutes=5)
    )


class EmailSentNotificationFactory(NotificationFactory):
    """Factory for notifications with email sent."""
    
    is_email_sent = True
    email_sent_at = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(minutes=1)
    )


class MentionNotificationFactory(NotificationFactory):
    """Factory for mention notifications."""
    
    notification_type = Notification.NotificationType.MENTION
    content_object = SubFactory(CommentFactory)
    title = factory.LazyAttribute(
        lambda obj: f"You were mentioned in a comment by {obj.sender.get_full_name()}"
    )


class AssignmentNotificationFactory(NotificationFactory):
    """Factory for assignment notifications."""
    
    notification_type = Notification.NotificationType.ASSIGNMENT
    content_object = SubFactory(TaskFactory)
    title = factory.LazyAttribute(
        lambda obj: f"You were assigned to task: {obj.content_object.title}"
    )


class ProjectInviteNotificationFactory(NotificationFactory):
    """Factory for project invite notifications."""
    
    notification_type = Notification.NotificationType.PROJECT_INVITE
    content_object = SubFactory(ProjectFactory)
    title = factory.LazyAttribute(
        lambda obj: f"You were invited to project: {obj.content_object.name}"
    )


class TaskCompletedNotificationFactory(NotificationFactory):
    """Factory for task completion notifications."""
    
    notification_type = Notification.NotificationType.TASK_COMPLETED
    content_object = SubFactory(TaskFactory)
    title = factory.LazyAttribute(
        lambda obj: f"Task completed: {obj.content_object.title}"
    )


class DeadlineReminderNotificationFactory(NotificationFactory):
    """Factory for deadline reminder notifications."""
    
    notification_type = Notification.NotificationType.DEADLINE_REMINDER
    content_object = SubFactory(TaskFactory)
    title = factory.LazyAttribute(
        lambda obj: f"Deadline approaching for task: {obj.content_object.title}"
    )


class NotificationPreferenceFactory(factory.django.DjangoModelFactory):
    """Factory for NotificationPreference model."""
    
    class Meta:
        model = NotificationPreference
    
    user = SubFactory(UserFactory)
    notification_type = fuzzy.FuzzyChoice(
        [Notification.NotificationType.MENTION,
         Notification.NotificationType.COMMENT,
         Notification.NotificationType.ASSIGNMENT,
         Notification.NotificationType.PROJECT_INVITE,
         Notification.NotificationType.TASK_COMPLETED,
         Notification.NotificationType.DEADLINE_REMINDER,
         Notification.NotificationType.PROJECT_UPDATE]
    )
    in_app_enabled = True
    email_enabled = True
    push_enabled = False
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)


class DisabledEmailPreferenceFactory(NotificationPreferenceFactory):
    """Factory for preferences with email disabled."""
    
    email_enabled = False


class DisabledInAppPreferenceFactory(NotificationPreferenceFactory):
    """Factory for preferences with in-app disabled."""
    
    in_app_enabled = False


class NotificationTemplateFactory(factory.django.DjangoModelFactory):
    """Factory for NotificationTemplate model."""
    
    class Meta:
        model = NotificationTemplate
    
    notification_type = fuzzy.FuzzyChoice(
        [Notification.NotificationType.MENTION,
         Notification.NotificationType.COMMENT,
         Notification.NotificationType.ASSIGNMENT,
         Notification.NotificationType.PROJECT_INVITE,
         Notification.NotificationType.TASK_COMPLETED,
         Notification.NotificationType.DEADLINE_REMINDER,
         Notification.NotificationType.PROJECT_UPDATE]
    )
    title_template = factory.Faker("sentence", nb_words=8)
    message_template = factory.Faker("paragraph", nb_sentences=3)
    email_subject_template = factory.Faker("sentence", nb_words=6)
    is_active = True
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)


class InactiveNotificationTemplateFactory(NotificationTemplateFactory):
    """Factory for inactive notification templates."""
    
    is_active = False


class UserWithNotificationsFactory(UserFactory):
    """Factory that creates a user with multiple notifications."""
    
    @factory.post_generation
    def notifications(self, create, extracted, **kwargs):
        if create:
            # Create 5-10 notifications
            notification_count = fuzzy.FuzzyInteger(5, 10).fuzz()
            for _ in range(notification_count):
                NotificationFactory(
                    recipient=self,
                    sender=UserFactory()
                )
        if extracted:
            # Add specified notifications
            for notification in extracted:
                notification.recipient = self
                notification.save()


class NotificationBatchFactory:
    """Factory for creating batches of notifications."""
    
    @staticmethod
    def create_for_project(project, recipients, sender=None, notification_type=None):
        """Create notifications for multiple recipients for a project."""
        if sender is None:
            sender = project.owner
        
        notifications = []
        for recipient in recipients:
            if recipient != sender:
                notification = NotificationFactory(
                    recipient=recipient,
                    sender=sender,
                    content_object=project,
                    notification_type=notification_type or Notification.NotificationType.PROJECT_UPDATE
                )
                notifications.append(notification)
        return notifications
    
    @staticmethod
    def create_for_task(task, recipients, sender=None, notification_type=None):
        """Create notifications for multiple recipients for a task."""
        if sender is None:
            sender = task.created_by
        
        notifications = []
        for recipient in recipients:
            if recipient != sender:
                notification = NotificationFactory(
                    recipient=recipient,
                    sender=sender,
                    content_object=task,
                    notification_type=notification_type or Notification.NotificationType.ASSIGNMENT
                )
                notifications.append(notification)
        return notifications
