import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from unittest.mock import patch
from .factories import (
    NotificationFactory, ReadNotificationFactory, EmailSentNotificationFactory,
    MentionNotificationFactory, AssignmentNotificationFactory,
    NotificationPreferenceFactory, UserWithNotificationsFactory,
    NotificationBatchFactory
)
from accounts.tests.factories import UserFactory
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import TaskFactory

User = get_user_model()


@pytest.mark.django_db
class TestNotificationCreation:
    """Notification creation is server-side (signals/tasks).
    The public API no longer exposes POST. These tests verify the
    ORM-level creation contract that the signal/task code relies on.
    """

    def test_create_notification(self, authenticated_client, user):
        """Test creating a notification via ORM (server-side path)."""
        from notifications.models import Notification
        sender = UserFactory()
        notification = Notification.objects.create(
            recipient=user,
            sender=sender,
            notification_type=Notification.NotificationType.MENTION,
            title='Test Notification',
            message='This is a test notification',
        )
        assert notification.id is not None
        assert Notification.objects.count() == 1
        assert Notification.objects.first().recipient == user
        # Public POST endpoint must be disabled
        response = authenticated_client.post(reverse('notification-list'), {})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_notification_auto_timestamps(self, authenticated_client, user):
        """Test notification timestamps are set automatically via ORM."""
        from notifications.models import Notification
        sender = UserFactory()
        notification = Notification.objects.create(
            recipient=user,
            sender=sender,
            notification_type=Notification.NotificationType.COMMENT,
            title='Test Notification',
            message='This is a test notification',
        )
        assert notification.created_at is not None
        assert notification.read_at is None  # unread by default

    def test_notification_validation(self, authenticated_client):
        """POST endpoint is removed; verify 405 instead of validation errors."""
        user = UserFactory()
        data = {'recipient': user.id}
        response = authenticated_client.post(reverse('notification-list'), data)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
class TestNotificationRetrieval:
    """Test notification retrieval and filtering"""
    
    def test_list_notifications(self, authenticated_client):
        """Test listing user's notifications"""
        # Create notifications for user
        user_with_notifications = UserWithNotificationsFactory()
        
        # Authenticate as the user with notifications
        authenticated_client.force_authenticate(user=user_with_notifications)
        
        response = authenticated_client.get(reverse('notification-list'))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 5
    
    def test_filter_unread_notifications(self, authenticated_client):
        """Test filtering unread notifications"""
        # Create mix of read and unread notifications
        user = UserFactory()
        NotificationFactory.create_batch(3, recipient=user)
        ReadNotificationFactory.create_batch(2, recipient=user)
        
        authenticated_client.force_authenticate(user=user)
        
        url = f"{reverse('notification-list')}?is_read=false"
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        for notification in response.data['results']:
            assert notification['is_read'] is False
    
    def test_filter_by_type(self, authenticated_client):
        """Test filtering notifications by type"""
        user = UserFactory()
        NotificationFactory(recipient=user, notification_type='MENTION')
        NotificationFactory(recipient=user, notification_type='ASSIGNMENT')
        NotificationFactory(recipient=user, notification_type='COMMENT')
        
        authenticated_client.force_authenticate(user=user)
        
        url = f"{reverse('notification-list')}?notification_type=MENTION"
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        for notification in response.data['results']:
            assert notification['notification_type'] == 'MENTION'
    
    def test_pagination(self, authenticated_client):
        """Test notification pagination"""
        user = UserFactory()
        NotificationFactory.create_batch(25, recipient=user)
        
        authenticated_client.force_authenticate(user=user)
        
        response = authenticated_client.get(reverse('notification-list'))
        
        assert response.status_code == status.HTTP_200_OK
        assert 'count' in response.data
        assert 'next' in response.data
        assert 'previous' in response.data
        assert len(response.data['results']) <= 20  # Default page size


@pytest.mark.django_db
class TestNotificationActions:
    """Test notification actions (mark as read, delete)"""
    
    def test_mark_notification_as_read(self, authenticated_client):
        """Test marking a notification as read"""
        user = UserFactory()
        notification = NotificationFactory(recipient=user)
        
        authenticated_client.force_authenticate(user=user)
        
        response = authenticated_client.post(
            reverse('notification-mark-read', kwargs={'pk': notification.id})
        )
        
        assert response.status_code == status.HTTP_200_OK
        notification.refresh_from_db()
        assert notification.is_read is True
        assert notification.read_at is not None
    
    def test_cannot_mark_others_notification_as_read(self, authenticated_client):
        """Test cannot mark someone else's notification as read"""
        other_user = UserFactory()
        notification = NotificationFactory(recipient=other_user)
        
        response = authenticated_client.post(
            reverse('notification-mark-read', kwargs={'pk': notification.id})
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_mark_all_as_read(self, authenticated_client):
        """Test marking all notifications as read"""
        user = UserFactory()
        NotificationFactory.create_batch(5, recipient=user)
        
        authenticated_client.force_authenticate(user=user)
        
        response = authenticated_client.post(reverse('notification-mark-all-read'))
        
        assert response.status_code == status.HTTP_200_OK
        from notifications.models import Notification
        unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
        assert unread_count == 0
    
    def test_delete_notification(self, authenticated_client):
        """DELETE is no longer exposed; verify 405 (intentional lockdown)."""
        user = UserFactory()
        notification = NotificationFactory(recipient=user)
        authenticated_client.force_authenticate(user=user)
        response = authenticated_client.delete(
            reverse('notification-detail', kwargs={'pk': notification.id})
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        # The notification row is still intact
        from notifications.models import Notification
        assert Notification.objects.filter(id=notification.id).exists()

    def test_get_preferences(self, authenticated_client):
        """Test getting user's notification preferences"""
        user = UserFactory()
        # Use distinct notification_type values (M-1 added unique_together)
        for n_type in ('MENTION', 'COMMENT', 'ASSIGNMENT'):
            NotificationPreferenceFactory(user=user, notification_type=n_type)
        authenticated_client.force_authenticate(user=user)
        response = authenticated_client.get(reverse('notification-preference-list'))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 3
    
    def test_update_preference(self, authenticated_client):
        """Test updating notification preference"""
        user = UserFactory()
        preference = NotificationPreferenceFactory(user=user)
        
        authenticated_client.force_authenticate(user=user)
        
        data = {
            'notification_type': preference.notification_type,
            'in_app_enabled': False,
            'email_enabled': True,
            'push_enabled': False
        }
        response = authenticated_client.patch(
            reverse('notification-preference-detail', kwargs={'pk': preference.id}),
            data
        )
        
        assert response.status_code == status.HTTP_200_OK
        preference.refresh_from_db()
        assert preference.in_app_enabled is False
        assert preference.email_enabled is True
    
    def test_create_preference(self, authenticated_client):
        """Test creating notification preference"""
        user = UserFactory()
        
        authenticated_client.force_authenticate(user=user)
        
        data = {
            'notification_type': 'MENTION',
            'in_app_enabled': True,
            'email_enabled': False,
            'push_enabled': False
        }
        response = authenticated_client.post(reverse('notification-preference-list'), data)
        
        assert response.status_code == status.HTTP_201_CREATED
        from notifications.models import NotificationPreference
        assert NotificationPreference.objects.count() == 1


@pytest.mark.django_db
class TestNotificationGeneration:
    """Test automatic notification generation"""
    
    def test_mention_notification_creation(self):
        """Test that mentioning a user creates notification"""
        from comments.tests.factories import CommentMentionFactory
        
        user = UserFactory()
        mention = CommentMentionFactory(mentioned_user=user)
        
        from notifications.models import Notification
        notification = Notification.objects.filter(
            recipient=user,
            notification_type='MENTION'
        ).first()
        
        assert notification is not None
        assert notification.sender == mention.mentioned_by
    
    def test_assignment_notification_creation(self):
        """Test that task assignment creates notification"""
        task = TaskFactory()
        assignee = UserFactory()
        
        # Simulate task assignment
        from notifications.models import Notification
        notification = Notification.objects.create(
            recipient=assignee,
            sender=task.created_by,
            content_object=task,
            notification_type='ASSIGNMENT',
            title=f'Assigned to task: {task.title}',
            message=f'You have been assigned to task: {task.title}'
        )
        
        assert notification is not None
        assert notification.content_object == task
    
    def test_project_invite_notification(self):
        """Test that project invitation creates notification"""
        from teams.tests.factories import TeamInvitationFactory
        
        user = UserFactory()
        invitation = TeamInvitationFactory(invited_user=user)
        
        from notifications.models import Notification
        notification = Notification.objects.filter(
            recipient=user,
            notification_type='PROJECT_INVITE'
        ).first()
        
        assert notification is not None
        assert notification.content_object == invitation.team


@pytest.mark.django_db
class TestEmailNotifications:
    """Test email notification functionality"""
    
    @patch('notifications.tasks.send_email_notification.delay')
    def test_email_notification_triggered(self, mock_send_email):
        """Test that email notification is triggered"""
        user = UserFactory()
        NotificationPreferenceFactory(
            user=user,
            notification_type='MENTION',
            email_enabled=True
        )
        
        notification = MentionNotificationFactory(recipient=user)
        
        # Check if email task was triggered
        mock_send_email.assert_called_once()
    
    @patch('notifications.tasks.send_email_notification.delay')
    def test_email_not_triggered_when_disabled(self, mock_send_email):
        """Test that email is not triggered when disabled"""
        user = UserFactory()
        NotificationPreferenceFactory(
            user=user,
            notification_type='MENTION',
            email_enabled=False
        )
        
        notification = MentionNotificationFactory(recipient=user)
        
        # Check if email task was not triggered
        mock_send_email.assert_not_called()


@pytest.mark.django_db
class TestNotificationStatistics:
    """Test notification statistics and analytics"""
    
    def test_unread_count(self, authenticated_client):
        """Test getting unread notification count"""
        user = UserFactory()
        NotificationFactory.create_batch(5, recipient=user)
        ReadNotificationFactory.create_batch(2, recipient=user)
        
        authenticated_client.force_authenticate(user=user)
        
        response = authenticated_client.get(reverse('notification-unread-count'))
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['unread_count'] == 5
    
    def test_notification_stats(self, authenticated_client):
        """Test getting notification statistics"""
        user = UserFactory()
        NotificationFactory.create_batch(3, recipient=user, notification_type='MENTION')
        NotificationFactory.create_batch(2, recipient=user, notification_type='ASSIGNMENT')
        ReadNotificationFactory.create_batch(1, recipient=user, notification_type='COMMENT')
        
        authenticated_client.force_authenticate(user=user)
        
        response = authenticated_client.get(reverse('notification-statistics'))
        
        assert response.status_code == status.HTTP_200_OK
        assert 'total_notifications' in response.data
        assert 'unread_count' in response.data
        assert 'by_type' in response.data
        assert response.data['total_notifications'] == 6
        assert response.data['unread_count'] == 5


@pytest.mark.django_db
class TestBatchNotifications:
    """Test batch notification creation"""
    
    def test_create_project_notifications(self):
        """Test creating notifications for project members"""
        project = ProjectFactory()
        members = [UserFactory() for _ in range(5)]
        
        # Add members to project
        from projects.tests.factories import ProjectMemberFactory
        for member in members:
            ProjectMemberFactory(project=project, user=member)
        
        # Create batch notifications
        notifications = NotificationBatchFactory.create_for_project(
            project, members, project.owner, 'PROJECT_UPDATE'
        )
        
        assert len(notifications) == 5
        from notifications.models import Notification
        assert Notification.objects.filter(notification_type='PROJECT_UPDATE').count() == 5
    
    def test_create_task_notifications(self):
        """Test creating notifications for task assignment"""
        task = TaskFactory()
        assignees = [UserFactory() for _ in range(3)]
        
        # Create batch notifications
        notifications = NotificationBatchFactory.create_for_task(
            task, assignees, task.created_by, 'ASSIGNMENT'
        )
        
        assert len(notifications) == 3
        from notifications.models import Notification
        for notification in notifications:
            assert notification.content_object == task


@pytest.mark.django_db
class TestNotificationSecurity:
    """Test notification security and permissions"""
    
    def test_user_cannot_access_others_notifications(self, authenticated_client):
        """Test user cannot access someone else's notifications"""
        other_user = UserFactory()
        NotificationFactory(recipient=other_user)
        
        authenticated_client.force_authenticate(user=UserFactory())
        
        response = authenticated_client.get(reverse('notification-list'))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 0
    
    def test_notification_recipient_validation(self, authenticated_client):
        """POST is no longer exposed; verify 405 (security fix).

        The original test verified that creating a notification with
        a non-existent recipient returned 400. Since the public POST
        endpoint was removed (N-1), the validation no longer applies
        at the API layer; recipient validation now happens server-side
        in signals/tasks. This test now documents the lockdown.
        """
        response = authenticated_client.post(reverse('notification-list'), {})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
class TestRealTimeNotifications:
    """Test real-time notification delivery"""
    
    def test_websocket_notification_sent(self):
        """Test that WebSocket notification is sent"""
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        user = UserFactory()
        notification = NotificationFactory(recipient=user)
        
        # Mock WebSocket send
        channel_layer = get_channel_layer()
        with patch.object(channel_layer, 'group_send') as mock_send:
            # Trigger WebSocket notification (this would normally be done via signal)
            async_to_sync(channel_layer.group_send)(
                f"user_{user.id}",
                {
                    'type': 'notification',
                    'notification_id': notification.id,
                    'title': notification.title,
                    'message': notification.message
                }
            )
            
            mock_send.assert_called_once()
    
    def test_notification_channel_group(self):
        """Test notification channel group naming"""
        user = UserFactory()
        
        expected_group = f"user_{user.id}"
        assert expected_group.startswith("user_")
        assert str(user.id) in expected_group
