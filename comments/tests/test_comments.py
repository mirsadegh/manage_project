import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from .factories import (
    CommentFactory, TaskCommentFactory, ProjectCommentFactory,
    ReplyCommentFactory, EditedCommentFactory, DeletedCommentFactory,
    CommentReactionFactory, CommentMentionFactory,
    CommentWithReactionsFactory, ThreadedCommentFactory
)
from accounts.tests.factories import UserFactory
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import TaskFactory

User = get_user_model()


@pytest.mark.django_db
class TestCommentCreation:
    """Test comment creation"""
    
    def test_create_comment_on_task(self, authenticated_client, task, user):
        """Test creating a comment on a task"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        data = {
            'text': 'This is a test comment on a task',
            'content_type': 'task',
            'object_id': task.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        from .models import Comment
        assert Comment.objects.count() == 1
        assert Comment.objects.first().author == user
        assert Comment.objects.first().text == 'This is a test comment on a task'
    
    def test_create_comment_on_project(self, authenticated_client, project, user):
        """Test creating a comment on a project"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=project, user=user, role='MEMBER')
        
        data = {
            'text': 'This is a test comment on a project',
            'content_type': 'project',
            'object_id': project.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        from .models import Comment
        assert Comment.objects.count() == 1
        assert Comment.objects.first().content_object == project
    
    def test_non_member_cannot_comment(self, authenticated_client, task):
        """Test non-member cannot comment"""
        data = {
            'text': 'This should fail',
            'content_type': 'task',
            'object_id': task.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_comment_validation(self, authenticated_client, task, user):
        """Test comment validation"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        data = {
            'text': '',  # Empty comment
            'content_type': 'task',
            'object_id': task.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'text' in response.data


@pytest.mark.django_db
class TestCommentReplies:
    """Test comment threading"""
    
    def test_create_reply_comment(self, authenticated_client, task, user):
        """Test creating a reply to a comment"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        # Create parent comment
        parent_comment = TaskCommentFactory(content_object=task)
        
        data = {
            'text': 'This is a reply',
            'content_type': 'task',
            'object_id': task.id,
            'parent': parent_comment.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        from .models import Comment
        reply = Comment.objects.get(text='This is a reply')
        assert reply.parent == parent_comment
        assert reply.is_reply
    
    def test_reply_to_reply_creplies_thread(self, authenticated_client, task, user):
        """Test replying to a reply creates a thread"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        # Create comment and reply
        parent = TaskCommentFactory(content_object=task)
        reply = ReplyCommentFactory(parent=parent, content_object=task)
        
        data = {
            'text': 'This is a reply to a reply',
            'content_type': 'task',
            'object_id': task.id,
            'parent': reply.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        from .models import Comment
        deep_reply = Comment.objects.get(text='This is a reply to a reply')
        assert deep_reply.parent == reply
        assert deep_reply.get_thread_root() == parent
    
    def test_get_comment_thread(self, authenticated_client, task):
        """Test retrieving a comment thread"""
        # Create threaded comments
        parent = ThreadedCommentFactory(content_object=task)
        
        response = authenticated_client.get(
            reverse('comment-detail', kwargs={'pk': parent.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert 'replies' in response.data
        assert len(response.data['replies']) >= 1


@pytest.mark.django_db
class TestCommentEditing:
    """Test comment editing"""
    
    def test_edit_own_comment(self, authenticated_client, task, user):
        """Test user can edit their own comment"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        comment = TaskCommentFactory(content_object=task, author=user)
        
        data = {'text': 'This is the edited comment'}
        response = authenticated_client.patch(
            reverse('comment-detail', kwargs={'pk': comment.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_200_OK
        comment.refresh_from_db()
        assert comment.text == 'This is the edited comment'
        assert comment.is_edited
    
    def test_cannot_edit_others_comment(self, authenticated_client, task):
        """Test user cannot edit someone else's comment"""
        other_user = UserFactory()
        comment = TaskCommentFactory(content_object=task, author=other_user)
        
        data = {'text': 'This should fail'}
        response = authenticated_client.patch(
            reverse('comment-detail', kwargs={'pk': comment.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_edit_history_tracked(self, authenticated_client, task, user):
        """Test that edit history is tracked"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        comment = TaskCommentFactory(content_object=task, author=user)
        original_updated_at = comment.updated_at
        
        data = {'text': 'First edit'}
        response = authenticated_client.patch(
            reverse('comment-detail', kwargs={'pk': comment.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_200_OK
        comment.refresh_from_db()
        assert comment.updated_at > original_updated_at


@pytest.mark.django_db
class TestCommentDeletion:
    """Test comment deletion"""
    
    def test_soft_delete_own_comment(self, authenticated_client, task, user):
        """Test user can soft delete their own comment"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        comment = TaskCommentFactory(content_object=task, author=user)
        
        response = authenticated_client.delete(
            reverse('comment-detail', kwargs={'pk': comment.id})
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        comment.refresh_from_db()
        assert comment.is_deleted
        assert comment.text == '[This comment has been deleted]'
    
    def test_admin_can_delete_any_comment(self, admin_client, task):
        """Test admin can delete any comment"""
        other_user = UserFactory()
        comment = TaskCommentFactory(content_object=task, author=other_user)
        
        response = admin_client.delete(
            reverse('comment-detail', kwargs={'pk': comment.id})
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        comment.refresh_from_db()
        assert comment.is_deleted


@pytest.mark.django_db
class TestCommentReactions:
    """Test comment reactions"""
    
    def test_add_reaction_to_comment(self, authenticated_client, task, user):
        """Test adding a reaction to a comment"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        comment = TaskCommentFactory(content_object=task)
        
        data = {'reaction_type': 'LIKE'}
        response = authenticated_client.post(
            reverse('comment-react', kwargs={'pk': comment.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        from .models import CommentReaction
        assert CommentReaction.objects.count() == 1
        assert CommentReaction.objects.first().user == user
        assert CommentReaction.objects.first().reaction_type == 'LIKE'
    
    def test_change_reaction(self, authenticated_client, task, user):
        """Test changing an existing reaction"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        comment = TaskCommentFactory(content_object=task)
        
        # Add initial reaction
        CommentReactionFactory(comment=comment, user=user, reaction_type='LIKE')
        
        # Change to different reaction
        data = {'reaction_type': 'HEART'}
        response = authenticated_client.post(
            reverse('comment-react', kwargs={'pk': comment.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_200_OK
        from .models import CommentReaction
        reaction = CommentReaction.objects.get(user=user, comment=comment)
        assert reaction.reaction_type == 'HEART'
    
    def test_remove_reaction(self, authenticated_client, task, user):
        """Test removing a reaction"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        comment = TaskCommentFactory(content_object=task)
        reaction = CommentReactionFactory(comment=comment, user=user, reaction_type='LIKE')
        
        response = authenticated_client.delete(
            reverse('comment-react', kwargs={'pk': comment.id})
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        from .models import CommentReaction
        assert not CommentReaction.objects.filter(id=reaction.id).exists()
    
    def test_get_comment_reactions(self, authenticated_client, task):
        """Test getting reactions for a comment"""
        comment = CommentWithReactionsFactory(content_object=task)
        
        response = authenticated_client.get(
            reverse('comment-reactions', kwargs={'pk': comment.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2  # Should have at least 2 reactions


@pytest.mark.django_db
class TestCommentMentions:
    """Test comment mentions"""
    
    def test_mention_creates_notification(self, authenticated_client, task, user):
        """Test mentioning a user creates a notification"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        mentioned_user = UserFactory()
        
        data = {
            'text': f'Hey @{mentioned_user.username}, check this out!',
            'content_type': 'task',
            'object_id': task.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Check mention was created
        from .models import CommentMention
        mention = CommentMention.objects.first()
        assert mention.mentioned_user == mentioned_user
        assert mention.mentioned_by == user
        
        # Check notification was created
        from notifications.models import Notification
        notification = Notification.objects.filter(
            recipient=mentioned_user,
            notification_type='MENTION'
        ).first()
        assert notification is not None
    
    def test_multiple_mentions(self, authenticated_client, task, user):
        """Test mentioning multiple users"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        mentioned_users = [UserFactory() for _ in range(3)]
        mentions_text = ' '.join([f'@{u.username}' for u in mentioned_users])
        
        data = {
            'text': f'{mentions_text} check this out!',
            'content_type': 'task',
            'object_id': task.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        
        from .models import CommentMention
        assert CommentMention.objects.count() == 3
    
    def test_invalid_mention_ignored(self, authenticated_client, task, user):
        """Test that invalid mentions are ignored"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        data = {
            'text': 'Hey @nonexistentuser, check this out!',
            'content_type': 'task',
            'object_id': task.id
        }
        response = authenticated_client.post(reverse('comment-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Should not create mention for nonexistent user
        from .models import CommentMention
        assert CommentMention.objects.count() == 0


@pytest.mark.django_db
class TestCommentPermissions:
    """Test comment permissions"""
    
    def test_project_members_can_view_comments(self, authenticated_client, task, user):
        """Test project members can view comments"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        # Create some comments
        TaskCommentFactory.create_batch(3, content_object=task)
        
        response = authenticated_client.get(reverse('comment-list'))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 3
    
    def test_non_members_cannot_view_comments(self, authenticated_client, task):
        """Test non-members cannot view comments"""
        TaskCommentFactory.create_batch(3, content_object=task)
        
        response = authenticated_client.get(reverse('comment-list'))
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_comment_author_can_edit_own_comment(self, authenticated_client, task, user):
        """Test comment author can edit their own comment"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        comment = TaskCommentFactory(content_object=task, author=user)
        
        data = {'text': 'Updated text'}
        response = authenticated_client.patch(
            reverse('comment-detail', kwargs={'pk': comment.id}), 
            data
        )
        
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestCommentFiltering:
    """Test comment filtering and search"""
    
    def test_filter_by_content_type(self, authenticated_client, project, user):
        """Test filtering comments by content type"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=project, user=user, role='MEMBER')
        
        # Create comments on different objects
        ProjectCommentFactory(content_object=project)
        task = TaskFactory(project=project)
        TaskCommentFactory(content_object=task)
        
        url = f"{reverse('comment-list')}?content_type=project"
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        for comment in response.data['results']:
            assert comment['content_type'] == 'project'
    
    def test_search_comments(self, authenticated_client, task, user):
        """Test searching comments"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=task.project, user=user, role='MEMBER')
        
        # Create comments with specific text
        TaskCommentFactory(content_object=task, text="Unique search term here")
        TaskCommentFactory(content_object=task, text="Another comment")
        
        url = f"{reverse('comment-list')}?search=Unique search term"
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
        assert "Unique search term" in response.data['results'][0]['text']


@pytest.mark.django_db
class TestCommentStatistics:
    """Test comment statistics and analytics"""
    
    def test_comment_count_per_object(self, authenticated_client, project, user):
        """Test getting comment count per object"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=project, user=user, role='MEMBER')
        
        # Create comments on project
        ProjectCommentFactory.create_batch(3, content_object=project)
        
        task = TaskFactory(project=project)
        TaskCommentFactory.create_batch(2, content_object=task)
        
        response = authenticated_client.get(
            reverse('comment-statistics', kwargs={'object_type': 'project', 'object_id': project.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['total_comments'] == 5
    
    def test_most_active_commenters(self, authenticated_client, project, user):
        """Test getting most active commenters"""
        # Add user as project member
        from projects.tests.factories import ProjectMemberFactory
        ProjectMemberFactory(project=project, user=user, role='MEMBER')
        
        # Create comments from different users
        active_user = UserFactory()
        TaskCommentFactory.create_batch(5, content_object=project, author=active_user)
        TaskCommentFactory.create_batch(2, content_object=project, author=UserFactory())
        
        response = authenticated_client.get(
            reverse('comment-statistics', kwargs={'object_type': 'project', 'object_id': project.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert 'top_commenters' in response.data
        assert len(response.data['top_commenters']) >= 1
