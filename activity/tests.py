from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from accounts.models import CustomUser
from projects.models import Project
from tasks.models import Task
from .models import ActivityLog, ActivityFeed


class ActivityLogModelTests(TestCase):
    """Test ActivityLog model"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!',
            role='PM'
        )
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user
        )
    
    def test_log_activity(self):
        """Test creating an activity log"""
        activity = ActivityLog.log_activity(
            user=self.user,
            action=ActivityLog.Action.CREATED,
            content_object=self.project,
            description='Created test project'
        )
        
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.action, ActivityLog.Action.CREATED)
        self.assertEqual(activity.content_object, self.project)
        self.assertEqual(activity.description, 'Created test project')
    
    def test_activity_with_changes(self):
        """Test activity log with change tracking"""
        changes = {
            'field': 'status',
            'old_value': 'TODO',
            'new_value': 'IN_PROGRESS'
        }
        
        activity = ActivityLog.log_activity(
            user=self.user,
            action=ActivityLog.Action.STATUS_CHANGED,
            content_object=self.project,
            description='Changed status',
            changes=changes
        )
        
        self.assertEqual(activity.changes, changes)
    
    def test_activity_str(self):
        """Test string representation"""
        activity = ActivityLog.log_activity(
            user=self.user,
            action=ActivityLog.Action.CREATED,
            content_object=self.project,
            description='Test'
        )
        
        expected = f"{self.user.username} CREATED {self.project}"
        self.assertEqual(str(activity), expected)


class ActivitySignalTests(TestCase):
    """Test that signals create activity logs"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!'
        )
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user
        )
    
    def test_project_creation_logs_activity(self):
        """Test that creating a project logs activity"""
        # Project was created in setUp, check log exists
        activity_exists = ActivityLog.objects.filter(
            action=ActivityLog.Action.CREATED,
            content_type__model='project',
            object_id=self.project.id
        ).exists()
        
        self.assertTrue(activity_exists)
    
    def test_task_creation_logs_activity(self):
        """Test that creating a task logs activity"""
        task = Task.objects.create(
            title='Test Task',
            project=self.project,
            created_by=self.user
        )
        
        activity_exists = ActivityLog.objects.filter(
            action=ActivityLog.Action.CREATED,
            content_type__model='task',
            object_id=task.id
        ).exists()
        
        self.assertTrue(activity_exists)
    
    def test_task_status_change_logs_activity(self):
        """Test that changing task status logs activity"""
        task = Task.objects.create(
            title='Test Task',
            project=self.project,
            created_by=self.user,
            status='TODO'
        )
        
        # Clear existing logs
        ActivityLog.objects.all().delete()
        
        # Change status
        task.status = 'IN_PROGRESS'
        task.save()
        
        # Check status change was logged
        activity_exists = ActivityLog.objects.filter(
            action=ActivityLog.Action.STATUS_CHANGED,
            content_type__model='task',
            object_id=task.id
        ).exists()
        
        self.assertTrue(activity_exists)


class ActivityAPITests(APITestCase):
    """Test Activity API endpoints"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!',
            role='PM'
        )
        self.client.force_authenticate(user=self.user)
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user
        )
        
        # Create some activities
        for i in range(5):
            ActivityLog.log_activity(
                user=self.user,
                action=ActivityLog.Action.CREATED,
                content_object=self.project,
                description=f'Test activity {i}'
            )
        
        self.activity_list_url = reverse('activity-log-list')
    
    def test_list_activities(self):
        """Test listing activity logs"""
        response = self.client.get(self.activity_list_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data['results']), 5)
    
    def test_filter_by_action(self):
        """Test filtering activities by action"""
        url = f'{self.activity_list_url}?action=CREATED'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for activity in response.data['results']:
            self.assertEqual(activity['action'], 'CREATED')
    
    def test_my_activity(self):
        """Test getting current user's activities"""
        url = reverse('activity-log-my-activity')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)


class ActivityFeedTests(APITestCase):
    """Test Activity Feed functionality"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!'
        )
        self.other_user = CustomUser.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='Test123!'
        )
        self.client.force_authenticate(user=self.user)
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user
        )
        
        # Create activity
        self.activity = ActivityLog.log_activity(
            user=self.other_user,
            action=ActivityLog.Action.CREATED,
            content_object=self.project,
            description='Other user did something'
        )
        
        # Create feed item
        self.feed_item = ActivityFeed.objects.create(
            user=self.user,
            activity=self.activity
        )
        
        self.feed_list_url = reverse('activity-feed-list')
    
    def test_list_feed(self):
        """Test listing user's activity feed"""
        response = self.client.get(self.feed_list_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_mark_as_read(self):
        """Test marking feed item as read"""
        url = reverse('activity-feed-mark-read', kwargs={'pk': self.feed_item.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.feed_item.refresh_from_db()
        self.assertTrue(self.feed_item.is_read)
    
    def test_mark_all_read(self):
        """Test marking all feed items as read"""
        # Create more feed items
        for i in range(3):
            activity = ActivityLog.log_activity(
                user=self.other_user,
                action=ActivityLog.Action.UPDATED,
                content_object=self.project,
                description=f'Update {i}'
            )
            ActivityFeed.objects.create(user=self.user, activity=activity)
        
        url = reverse('activity-feed-mark-all-read')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Marked 4 items as read')
        
        # Verify all are read
        unread_count = ActivityFeed.objects.filter(
            user=self.user,
            is_read=False
        ).count()
        self.assertEqual(unread_count, 0)
    
    def test_unread_count(self):
        """Test getting unread count"""
        url = reverse('activity-feed-unread-count')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread_count'], 1)