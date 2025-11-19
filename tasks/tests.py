from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from accounts.models import CustomUser
from projects.models import Project, ProjectMember
from .models import Task, TaskList


class TaskCreationTests(APITestCase):
    """Test task creation"""
    
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='Owner123!',
            role='PM'
        )
        self.member = CustomUser.objects.create_user(
            username='member',
            email='member@example.com',
            password='Member123!',
            role='DEV'
        )
        self.non_member = CustomUser.objects.create_user(
            username='nonmember',
            email='nonmember@example.com',
            password='NonMember123!',
            role='DEV'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.owner,
            status='IN_PROGRESS'
        )
        
        ProjectMember.objects.create(
            project=self.project,
            user=self.member,
            role='MEMBER'
        )
        
        self.task_list_url = reverse('task-list')
    
    def test_member_can_create_task(self):
        """Test project member can create tasks"""
        self.client.force_authenticate(user=self.member)
        data = {
            'title': 'New Task',
            'description': 'Test task',
            'project': self.project.id,
            'status': 'TODO',
            'priority': 'MEDIUM'
        }
        response = self.client.post(self.task_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(Task.objects.first().created_by, self.member)
    
    def test_non_member_cannot_create_task(self):
        """Test non-member cannot create tasks"""
        self.client.force_authenticate(user=self.non_member)
        data = {
            'title': 'New Task',
            'description': 'Test task',
            'project': self.project.id,
            'status': 'TODO',
            'priority': 'MEDIUM'
        }
        response = self.client.post(self.task_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TaskAssignmentTests(APITestCase):
    """Test task assignment"""
    
    def setUp(self):
        self.manager = CustomUser.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='Manager123!',
            role='PM'
        )
        self.developer = CustomUser.objects.create_user(
            username='developer',
            email='dev@example.com',
            password='Dev123!',
            role='DEV'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.manager,
            status='IN_PROGRESS'
        )
        
        ProjectMember.objects.create(
            project=self.project,
            user=self.developer,
            role='MEMBER'
        )
        
        self.task = Task.objects.create(
            title='Test Task',
            project=self.project,
            created_by=self.manager,
            status='TODO'
        )
        
        self.assign_url = reverse('task-assign', kwargs={'pk': self.task.id})
    
    def test_manager_can_assign_task(self):
        """Test manager can assign tasks"""
        self.client.force_authenticate(user=self.manager)
        data = {'user_id': self.developer.id}
        response = self.client.post(self.assign_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee, self.developer)
    
    def test_developer_cannot_reassign_task(self):
        """Test developer cannot reassign tasks"""
        self.task.assignee = self.developer
        self.task.save()
        
        self.client.force_authenticate(user=self.developer)
        data = {'user_id': self.manager.id}
        response = self.client.post(self.assign_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TaskStatusChangeTests(APITestCase):
    """Test task status changes"""
    
    def setUp(self):
        self.assignee = CustomUser.objects.create_user(
            username='assignee',
            email='assignee@example.com',
            password='Assignee123!',
            role='DEV'
        )
        self.other_user = CustomUser.objects.create_user(
            username='other',
            email='other@example.com',
            password='Other123!',
            role='DEV'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.assignee,
            status='IN_PROGRESS'
        )
        
        self.task = Task.objects.create(
            title='Test Task',
            project=self.project,
            created_by=self.assignee,
            assignee=self.assignee,
            status='TODO'
        )
        
        self.change_status_url = reverse('task-change-status', kwargs={'pk': self.task.id})
    
    def test_assignee_can_change_status(self):
        """Test assignee can change task status"""
        self.client.force_authenticate(user=self.assignee)
        data = {'status': 'IN_PROGRESS'}
        response = self.client.post(self.change_status_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'IN_PROGRESS')
    
    def test_non_assignee_cannot_change_status(self):
        """Test non-assignee cannot change task status"""
        self.client.force_authenticate(user=self.other_user)
        data = {'status': 'IN_PROGRESS'}
        response = self.client.post(self.change_status_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TaskPaginationTests(APITestCase):
    """Test task pagination with statistics"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!',
            role='PM'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user,
            status='IN_PROGRESS'
        )
        
        # Create 30 tasks
        for i in range(1, 31):
            Task.objects.create(
                title=f'Task {i:02d}',
                project=self.project,
                created_by=self.user,
                status=['TODO', 'IN_PROGRESS', 'COMPLETED'][i % 3]
            )
        
        self.task_list_url = reverse('task-list')
    
    def test_task_pagination_includes_statistics(self):
        """Test task pagination includes statistics"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.task_list_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('statistics', response.data)
        self.assertIn('total_tasks', response.data['statistics'])
        self.assertEqual(response.data['statistics']['total_tasks'], 30)