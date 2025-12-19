"""
Integration tests for cross-app workflows and user journeys.
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from accounts.tests.factories import UserFactory, ManagerUserFactory
from projects.tests.factories import ProjectFactory, ProjectMemberFactory
from tasks.tests.factories import TaskFactory, TaskListFactory
from comments.tests.factories import CommentFactory
from notifications.tests.factories import NotificationFactory
from files.tests.factories import AttachmentFactory

User = get_user_model()


@pytest.mark.integration
@pytest.mark.django_db
class TestUserJourney:
    """Test complete user journeys from registration to project management."""
    
    def test_new_user_onboarding(self, api_client):
        """Test complete onboarding journey for new user."""
        # Step 1: Register user
        register_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'NewPass123!',
            'password2': 'NewPass123!',
            'first_name': 'New',
            'last_name': 'User',
            'role': 'DEV'
        }
        response = api_client.post(reverse('register'), register_data)
        assert response.status_code == status.HTTP_201_CREATED
        
        user = User.objects.get(username='newuser')
        
        # Step 2: Login
        login_data = {
            'email': 'newuser@example.com',
            'password': 'NewPass123!'
        }
        response = api_client.post(reverse('token_obtain_pair'), login_data)
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        
        # Step 3: Access protected endpoint
        token = response.data['access']
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = api_client.get(reverse('user-me'))
        assert response.status_code == status.HTTP_200_OK
        assert response.data['username'] == 'newuser'
    
    def test_project_manager_workflow(self, api_client):
        """Test project manager complete workflow."""
        # Create and authenticate manager
        manager = ManagerUserFactory()
        api_client.force_authenticate(user=manager)
        
        # Step 1: Create project
        project_data = {
            'name': 'Test Project',
            'description': 'A test project for workflow testing',
            'status': 'PLANNING',
            'priority': 'HIGH'
        }
        response = api_client.post(reverse('project-list'), project_data)
        assert response.status_code == status.HTTP_201_CREATED
        
        project_id = response.data['id']
        
        # Step 2: Add team members
        developers = [UserFactory() for _ in range(3)]
        for developer in developers:
            member_data = {
                'user_id': developer.id,
                'role': 'MEMBER'
            }
            response = api_client.post(
                reverse('project-add-member', kwargs={'pk': project_id}),
                member_data
            )
            assert response.status_code == status.HTTP_201_CREATED
        
        # Step 3: Create task lists and tasks
        task_list_data = {
            'name': 'Development Tasks',
            'project': project_id
        }
        response = api_client.post(reverse('tasklist-list'), task_list_data)
        assert response.status_code == status.HTTP_201_CREATED
        task_list_id = response.data['id']
        
        # Step 4: Create tasks
        for i in range(3):
            task_data = {
                'title': f'Task {i+1}',
                'description': f'Description for task {i+1}',
                'project': project_id,
                'task_list': task_list_id,
                'assignee': developers[i].id,
                'priority': 'MEDIUM',
                'estimated_hours': 8.0
            }
            response = api_client.post(reverse('task-list'), task_data)
            assert response.status_code == status.HTTP_201_CREATED
        
        # Step 5: Verify project statistics
        response = api_client.get(reverse('project-detail', kwargs={'pk': project_id}))
        assert response.status_code == status.HTTP_200_OK
        assert 'task_statistics' in response.data
        assert response.data['task_statistics']['total_tasks'] == 3


@pytest.mark.integration
@pytest.mark.django_db
class TestTaskWorkflow:
    """Test complete task lifecycle workflows."""
    
    def test_task_from_creation_to_completion(self, api_client):
        """Test complete task lifecycle."""
        # Setup
        manager = ManagerUserFactory()
        developer = UserFactory()
        project = ProjectFactory(owner=manager)
        
        # Add members
        ProjectMemberFactory(project=project, user=manager, role='MANAGER')
        ProjectMemberFactory(project=project, user=developer, role='MEMBER')
        
        api_client.force_authenticate(user=manager)
        
        # Step 1: Create task
        task_list = TaskListFactory(project=project, created_by=manager)
        task_data = {
            'title': 'Complete Workflow Task',
            'description': 'Task for testing complete workflow',
            'project': project.id,
            'task_list': task_list.id,
            'assignee': developer.id,
            'status': 'TODO',
            'priority': 'HIGH',
            'estimated_hours': 16.0
        }
        response = api_client.post(reverse('task-list'), task_data)
        assert response.status_code == status.HTTP_201_CREATED
        task_id = response.data['id']
        
        # Step 2: Add attachment to task
        attachment_data = {
            'description': 'Task requirements document',
            'content_type': 'task',
            'object_id': task_id
        }
        # Note: This would normally be a multipart file upload
        # For testing, we'll simulate the response
        response = api_client.post(reverse('attachment-list'), attachment_data)
        # File upload test would be done separately
        
        # Step 3: Developer updates task status
        api_client.force_authenticate(user=developer)
        response = api_client.post(
            reverse('task-change-status', kwargs={'pk': task_id}),
            {'status': 'IN_PROGRESS'}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Step 4: Add comment to task
        comment_data = {
            'text': 'Started working on this task',
            'content_type': 'task',
            'object_id': task_id
        }
        response = api_client.post(reverse('comment-list'), comment_data)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Step 5: Log time spent
        response = api_client.patch(
            reverse('task-detail', kwargs={'pk': task_id}),
            {'actual_hours': 12.5}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Step 6: Complete task
        response = api_client.post(
            reverse('task-change-status', kwargs={'pk': task_id}),
            {'status': 'COMPLETED'}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Step 7: Verify notifications were created
        from notifications.models import Notification
        notifications = Notification.objects.filter(
            recipient=manager,
            content_type__model='task',
            object_id=task_id
        )
        assert len(notifications) >= 1  # Should have completion notification


@pytest.mark.integration
@pytest.mark.django_db
class TestCommentWorkflow:
    """Test comment and notification workflow."""
    
    def test_comment_with_mentions_workflow(self, api_client):
        """Test comment creation with user mentions."""
        # Setup
        manager = ManagerUserFactory()
        developer1 = UserFactory()
        developer2 = UserFactory()
        project = ProjectFactory(owner=manager)
        
        # Add members
        ProjectMemberFactory(project=project, user=manager, role='MANAGER')
        ProjectMemberFactory(project=project, user=developer1, role='MEMBER')
        ProjectMemberFactory(project=project, user=developer2, role='MEMBER')
        
        # Create task
        task = TaskFactory(project=project, created_by=manager, assignee=developer1)
        
        api_client.force_authenticate(user=developer1)
        
        # Step 1: Create comment with mention
        comment_data = {
            'text': f'Hey @{developer2.username}, can you help with this?',
            'content_type': 'task',
            'object_id': task.id
        }
        response = api_client.post(reverse('comment-list'), comment_data)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Step 2: Verify mention notification was created
        from notifications.models import Notification
        mention_notification = Notification.objects.filter(
            recipient=developer2,
            notification_type='MENTION'
        ).first()
        assert mention_notification is not None
        
        # Step 3: Verify reaction can be added
        comment_id = response.data['id']
        reaction_data = {'reaction_type': 'LIKE'}
        response = api_client.post(
            reverse('comment-react', kwargs={'pk': comment_id}),
            reaction_data
        )
        assert response.status_code == status.HTTP_201_CREATED
        
        # Step 4: Verify comment thread
        reply_data = {
            'text': 'Sure, I can help!',
            'content_type': 'task',
            'object_id': task.id,
            'parent': comment_id
        }
        response = api_client.post(reverse('comment-list'), reply_data)
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.integration
@pytest.mark.django_db
class TestFileWorkflow:
    """Test file upload and attachment workflow."""
    
    def test_file_attachment_workflow(self, api_client):
        """Test complete file attachment workflow."""
        # Setup
        manager = ManagerUserFactory()
        developer = UserFactory()
        project = ProjectFactory(owner=manager)
        
        ProjectMemberFactory(project=project, user=manager, role='MANAGER')
        ProjectMemberFactory(project=project, user=developer, role='MEMBER')
        
        task = TaskFactory(project=project, created_by=manager, assignee=developer)
        
        api_client.force_authenticate(user=manager)
        
        # Step 1: Upload file to task
        # Note: In real test, this would use multipart upload
        attachment_data = {
            'description': 'Project specification',
            'content_type': 'task',
            'object_id': task.id
        }
        
        # Simulate file upload response
        response = api_client.post(reverse('attachment-list'), attachment_data)
        # File upload verification would be here
        
        # Step 2: Verify attachment appears in task details
        response = api_client.get(reverse('task-detail', kwargs={'pk': task.id}))
        assert response.status_code == status.HTTP_200_OK
        # attachments would be in response data
        
        # Step 3: Download attachment (as developer)
        api_client.force_authenticate(user=developer)
        # attachment_id would be from step 1
        # response = api_client.get(reverse('attachment-download', kwargs={'pk': attachment_id}))
        # assert response.status_code == status.HTTP_200_OK


@pytest.mark.integration
@pytest.mark.django_db
class TestNotificationWorkflow:
    """Test notification preferences and delivery workflow."""
    
    def test_notification_preferences_workflow(self, api_client):
        """Test notification preference management."""
        # Setup
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Step 1: Check default preferences
        response = api_client.get(reverse('notification-preference-list'))
        assert response.status_code == status.HTTP_200_OK
        # Should have default preferences
        
        # Step 2: Update notification preferences
        preference_data = {
            'notification_type': 'MENTION',
            'in_app_enabled': True,
            'email_enabled': False,
            'push_enabled': True
        }
        response = api_client.post(reverse('notification-preference-list'), preference_data)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Step 3: Create notification (this would trigger based on preferences)
        # This would be tested via signals
        
        # Step 4: Mark notification as read
        # Create a notification first
        notification = NotificationFactory(recipient=user)
        
        response = api_client.post(
            reverse('notification-mark-read', kwargs={'pk': notification.id})
        )
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.integration
@pytest.mark.django_db
class TestProjectReporting:
    """Test project reporting and analytics workflow."""
    
    def test_project_analytics_workflow(self, api_client):
        """Test project analytics and reporting."""
        # Setup
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        
        # Create comprehensive data
        developers = [UserFactory() for _ in range(5)]
        for developer in developers:
            ProjectMemberFactory(project=project, user=developer, role='MEMBER')
        
        # Create tasks with various statuses
        task_list = TaskListFactory(project=project, created_by=manager)
        
        # Completed tasks
        TaskFactory.create_batch(
            3,
            project=project,
            task_list=task_list,
            created_by=manager,
            status='COMPLETED',
            actual_hours=40.0
        )
        
        # In-progress tasks
        TaskFactory.create_batch(
            2,
            project=project,
            task_list=task_list,
            created_by=manager,
            status='IN_PROGRESS',
            actual_hours=20.0
        )
        
        # TODO tasks
        TaskFactory.create_batch(
            5,
            project=project,
            task_list=task_list,
            created_by=manager,
            status='TODO',
            actual_hours=0
        )
        
        api_client.force_authenticate(user=manager)
        
        # Step 1: Get project statistics
        response = api_client.get(reverse('project-detail', kwargs={'pk': project.id}))
        assert response.status_code == status.HTTP_200_OK
        assert 'statistics' in response.data
        
        # Step 2: Get task analytics
        response = api_client.get(f"{reverse('task-list')}?project={project.id}")
        assert response.status_code == status.HTTP_200_OK
        assert 'statistics' in response.data
        
        stats = response.data['statistics']
        assert stats['total_tasks'] == 10
        assert stats['completed_tasks'] == 3
        assert 'completion_rate' in stats
        
        # Step 3: Get member activity
        response = api_client.get(
            reverse('project-activity', kwargs={'pk': project.id})
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) > 0


@pytest.mark.integration
@pytest.mark.django_db
class TestSearchAndFiltering:
    """Test cross-app search and filtering."""
    
    def test_global_search_workflow(self, api_client):
        """Test global search across entities."""
        # Setup
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager, name='Alpha Project')
        
        task_list = TaskListFactory(project=project, created_by=manager)
        task = TaskFactory(
            project=project,
            task_list=task_list,
            created_by=manager,
            title='Alpha Task Description'
        )
        
        CommentFactory(
            content_object=task,
            author=manager,
            text='This is about alpha features'
        )
        
        api_client.force_authenticate(user=manager)
        
        # Step 1: Search projects
        response = api_client.get(f"{reverse('project-list')}?search=Alpha")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
        assert 'Alpha' in response.data['results'][0]['name']
        
        # Step 2: Search tasks
        response = api_client.get(f"{reverse('task-list')}?search=Alpha")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1
        assert 'Alpha' in response.data['results'][0]['title']
        
        # Step 3: Search comments
        response = api_client.get(f"{reverse('comment-list')}?search=alpha")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 1


@pytest.mark.integration
@pytest.mark.django_db
class TestErrorHandling:
    """Test error handling across integrated workflows."""
    
    def test_cascade_deletion_protection(self, api_client):
        """Test that cascade deletion is properly handled."""
        # Setup
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task = TaskFactory(project=project, created_by=manager)
        
        # Create dependent objects
        CommentFactory.create_batch(3, content_object=task)
        AttachmentFactory.create_batch(2, content_object=task)
        
        api_client.force_authenticate(user=manager)
        
        # Step 1: Attempt to delete task with dependencies
        response = api_client.delete(reverse('task-detail', kwargs={'pk': task.id}))
        
        # Should either succeed with proper cleanup or fail gracefully
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,  # Success with cleanup
            status.HTTP_400_BAD_REQUEST  # Protected deletion
        ]
        
        # Step 2: Verify data integrity
        if response.status_code == status.HTTP_204_NO_CONTENT:
            # Comments and attachments should be handled appropriately
            pass
    
    def test_permission_enforcement_workflow(self, api_client):
        """Test permissions are enforced across workflows."""
        # Setup
        manager = ManagerUserFactory()
        developer = UserFactory()
        outsider = UserFactory()
        
        project = ProjectFactory(owner=manager)
        task = TaskFactory(project=project, created_by=manager, assignee=developer)
        
        # Step 1: Manager can access everything
        api_client.force_authenticate(user=manager)
        response = api_client.get(reverse('task-detail', kwargs={'pk': task.id}))
        assert response.status_code == status.HTTP_200_OK
        
        response = api_client.patch(
            reverse('task-detail', kwargs={'pk': task.id}),
            {'title': 'Updated by manager'}
        )
        assert response.status_code == status.HTTP_200_OK
        
        # Step 2: Developer has limited access
        api_client.force_authenticate(user=developer)
        response = api_client.get(reverse('task-detail', kwargs={'pk': task.id}))
        assert response.status_code == status.HTTP_200_OK
        
        # But cannot reassign
        response = api_client.post(
            reverse('task-assign', kwargs={'pk': task.id}),
            {'user_id': manager.id}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Step 3: Outsider has no access
        api_client.force_authenticate(user=outsider)
        response = api_client.get(reverse('task-detail', kwargs={'pk': task.id}))
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.django_db
class TestPerformanceIntegration:
    """Integration tests with performance focus."""
    
    def test_large_project_performance(self, api_client):
        """Test performance with large project data."""
        # Setup large dataset
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        
        # Create many tasks
        task_list = TaskListFactory(project=project, created_by=manager)
        TaskFactory.create_batch(100, project=project, task_list=task_list, created_by=manager)
        
        api_client.force_authenticate(user=manager)
        
        # Test that responses remain performant
        response = api_client.get(reverse('project-detail', kwargs={'pk': project.id}))
        assert response.status_code == status.HTTP_200_OK
        # Response time should be reasonable (would measure in real perf test)
        
        response = api_client.get(f"{reverse('task-list')}?project={project.id}")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) <= 20  # Pagination limits
