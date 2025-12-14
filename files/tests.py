# files/tests.py

from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import CustomUser
from projects.models import Project
from tasks.models import Task
from .models import Attachment


class FileUploadTests(APITestCase):
    """Test file upload functionality"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!'
        )
        self.client.force_authenticate(user=self.user)
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user
        )
        
        self.upload_url = reverse('attachment-list')
    
    def test_upload_file_to_project(self):
        """Test uploading a file to a project"""
        # Create a test file
        file_content = b'This is a test PDF file'
        test_file = SimpleUploadedFile(
            'test.pdf',
            file_content,
            content_type='application/pdf'
        )
        
        data = {
            'file': test_file,
            'description': 'Test file',
            'content_type': 'project',
            'object_id': self.project.id
        }
        
        response = self.client.post(self.upload_url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Attachment.objects.count(), 1)
        
        attachment = Attachment.objects.first()
        self.assertEqual(attachment.original_filename, 'test.pdf')
        self.assertEqual(attachment.uploaded_by, self.user)
    
    def test_file_size_validation(self):
        """Test that large files are rejected"""
        # Create a file larger than 10MB
        large_file = SimpleUploadedFile(
            'large.pdf',
            b'x' * (11 * 1024 * 1024),  # 11 MB
            content_type='application/pdf'
        )
        
        data = {
            'file': large_file,
            'content_type': 'project',
            'object_id': self.project.id
        }
        
        response = self.client.post(self.upload_url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Attachment.objects.count(), 0)
    
    def test_download_file(self):
        """Test downloading a file"""
        # Create attachment
        attachment = Attachment.objects.create(
            content_object=self.project,
            uploaded_by=self.user,
            file=SimpleUploadedFile('test.txt', b'test content')
        )
        
        url = reverse('attachment-download', kwargs={'pk': attachment.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test.txt"')
        
        # Check download count increased
        attachment.refresh_from_db()
        self.assertEqual(attachment.download_count, 1)


class CommentIntegrationTests(APITestCase):
    """Test comments on tasks and projects"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!'
        )
        self.client.force_authenticate(user=self.user)
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user
        )
        
        self.task = Task.objects.create(
            title='Test Task',
            project=self.project,
            created_by=self.user
        )
    
    def test_add_comment_to_task(self):
        """Test adding a comment to a task"""
        url = reverse('task-add-comment', kwargs={'pk': self.task.id})
        data = {'text': 'This is a test comment'}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.task.comments.count(), 1)
    
    def test_get_task_comments(self):
        """Test retrieving task comments"""
        # Create some comments
        from comments.models import Comment
        Comment.objects.create(
            content_object=self.task,
            author=self.user,
            text='Comment 1'
        )
        Comment.objects.create(
            content_object=self.task,
            author=self.user,
            text='Comment 2'
        )
        
        url = reverse('task-comments', kwargs={'pk': self.task.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
    
    def test_comment_mention_notification(self):
        """Test that mentioning a user creates a notification"""
        other_user = CustomUser.objects.create_user(
        username='otheruser',
        email='other@example.com',
        password='Test123!'
        )
    
        url = reverse('task-add-comment', kwargs={'pk': self.task.id})
        data = {'text': 'Hey @otheruser check this out'}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check notification was created
        from notifications.models import Notification
        notification_exists = Notification.objects.filter(
            recipient=other_user,
            notification_type='MENTION'
        ).exists()
        
        self.assertTrue(notification_exists) 
        
        
        
          