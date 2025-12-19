import factory
from factory import fuzzy, SubFactory
from django.utils import timezone
from accounts.tests.factories import UserFactory
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import TaskFactory
from ..models import Comment, CommentReaction, CommentMention


class CommentFactory(factory.django.DjangoModelFactory):
    """Factory for Comment model."""
    
    class Meta:
        model = Comment
    
    content_type = factory.LazyAttribute(lambda obj: obj._get_content_type())
    object_id = fuzzy.FuzzyInteger(1, 1000)
    author = SubFactory(UserFactory)
    text = factory.Faker("paragraph", nb_sentences=3)
    parent = None
    is_edited = False
    is_deleted = False
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)
    
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


class TaskCommentFactory(CommentFactory):
    """Factory for comments on tasks."""
    
    content_object = SubFactory(TaskFactory)


class ProjectCommentFactory(CommentFactory):
    """Factory for comments on projects."""
    
    content_object = SubFactory(ProjectFactory)


class ReplyCommentFactory(CommentFactory):
    """Factory for reply comments."""
    
    parent = SubFactory(CommentFactory)
    content_object = factory.LazyAttribute(lambda obj: obj.parent.content_object)


class EditedCommentFactory(CommentFactory):
    """Factory for edited comments."""
    
    is_edited = True
    updated_at = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(hours=1)
    )


class DeletedCommentFactory(CommentFactory):
    """Factory for deleted comments."""
    
    is_deleted = True
    text = "[This comment has been deleted]"


class CommentReactionFactory(factory.django.DjangoModelFactory):
    """Factory for CommentReaction model."""
    
    class Meta:
        model = CommentReaction
    
    comment = SubFactory(CommentFactory)
    user = SubFactory(UserFactory)
    reaction_type = fuzzy.FuzzyChoice(
        [CommentReaction.ReactionType.LIKE, 
         CommentReaction.ReactionType.DISLIKE,
         CommentReaction.ReactionType.LAUGH,
         CommentReaction.ReactionType.HEART,
         CommentReaction.ReactionType.ANGRY]
    )
    created_at = factory.LazyFunction(timezone.now)


class CommentMentionFactory(factory.django.DjangoModelFactory):
    """Factory for CommentMention model."""
    
    class Meta:
        model = CommentMention
    
    comment = SubFactory(CommentFactory)
    mentioned_user = SubFactory(UserFactory)
    mentioned_by = SubFactory(UserFactory)
    created_at = factory.LazyFunction(timezone.now)
    
    @factory.post_generation
    def notify(self, create, extracted, **kwargs):
        """Create notification for mentioned user."""
        if create:
            from notifications.models import Notification
            Notification.objects.create(
                recipient=self.mentioned_user,
                sender=self.mentioned_by,
                notification_type=Notification.NotificationType.MENTION,
                title=f"You were mentioned in a comment",
                message=f"{self.mentioned_by.get_full_name()} mentioned you in a comment",
                content_object=self.comment
            )


class CommentWithReactionsFactory(CommentFactory):
    """Factory that creates a comment with multiple reactions."""
    
    @factory.post_generation
    def reactions(self, create, extracted, **kwargs):
        if create:
            # Create 2-5 reactions
            reaction_count = fuzzy.FuzzyInteger(2, 5).fuzz()
            for _ in range(reaction_count):
                CommentReactionFactory(comment=self)


class ThreadedCommentFactory(CommentFactory):
    """Factory that creates a comment with replies."""
    
    @factory.post_generation
    def replies(self, create, extracted, **kwargs):
        if create:
            # Create 1-3 replies
            reply_count = fuzzy.FuzzyInteger(1, 3).fuzz()
            for _ in range(reply_count):
                ReplyCommentFactory(
                    parent=self,
                    content_object=self.content_object,
                    author=UserFactory()
                )
        if extracted:
            # Add specified replies
            for reply in extracted:
                reply.parent = self
                reply.content_object = self.content_object
                reply.save()
