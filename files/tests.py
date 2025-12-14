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




class FileSecurityTests(APITestCase):
    """Test file security features"""
    
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
        
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user
        )
        
        self.upload_url = reverse('attachment-list')
    
    def test_user_cannot_access_others_files(self):
        """Test that users cannot access files they don't have permission for"""
        # User 1 uploads file
        self.client.force_authenticate(user=self.user)
        
        test_file = SimpleUploadedFile('test.pdf', b'content', content_type='application/pdf')
        data = {
            'file': test_file,
            'content_type': 'project',
            'object_id': self.project.id
        }
        response = self.client.post(self.upload_url, data, format='multipart')
        attachment_id = response.data['id']
        
        # User 2 tries to download
        self.client.force_authenticate(user=self.other_user)
        download_url = reverse('attachment-download', kwargs={'pk': attachment_id})
        response = self.client.get(download_url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_file_hash_prevents_duplicates(self):
        """Test that duplicate files are detected by hash"""
        self.client.force_authenticate(user=self.user)
        
        # Upload same file twice
        file_content = b'This is unique content'
        
        test_file1 = SimpleUploadedFile('test1.pdf', file_content, content_type='application/pdf')
        data1 = {
            'file': test_file1,
            'content_type': 'project',
            'object_id': self.project.id
        }
        response1 = self.client.post(self.upload_url, data1, format='multipart')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        
        # Try to upload duplicate
        test_file2 = SimpleUploadedFile('test2.pdf', file_content, content_type='application/pdf')
        data2 = {
            'file': test_file2,
            'content_type': 'project',
            'object_id': self.project.id
        }
        response2 = self.client.post(self.upload_url, data2, format='multipart')
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_file_type_validation(self):
        """Test that invalid file types are rejected"""
        self.client.force_authenticate(user=self.user)
        
        # Try to upload an executable file (not allowed)
        exe_file = SimpleUploadedFile('test.exe', b'exe content', content_type='application/x-msdownload')
        data = {
            'file': exe_file,
            'content_type': 'project',
            'object_id': self.project.id
        }
        response = self.client.post(self.upload_url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_image_thumbnail_generation(self):
        """Test that thumbnails are created for images"""
        from PIL import Image
        from io import BytesIO
        
        self.client.force_authenticate(user=self.user)
        
        # Create a real image file
        image = Image.new('RGB', (800, 600), color='red')
        image_io = BytesIO()
        image.save(image_io, format='JPEG')
        image_io.seek(0)
        
        image_file = SimpleUploadedFile('test.jpg', image_io.read(), content_type='image/jpeg')
        data = {
            'file': image_file,
            'content_type': 'project',
            'object_id': self.project.id
        }
        response = self.client.post(self.upload_url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        attachment = Attachment.objects.get(id=response.data['id'])
        self.assertTrue(attachment.is_image)
        self.assertIsNotNone(attachment.thumbnail)
        self.assertEqual(attachment.image_width, 800)
        self.assertEqual(attachment.image_height, 600)


class CommentSystemTests(APITestCase):
    """Test comment system features"""
    
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
    
    def test_threaded_comments(self):
        """Test comment threading (replies)"""
        from comments.models import Comment
        
        # Create parent comment
        parent = Comment.objects.create(
            content_object=self.task,
            author=self.user,
            text='Parent comment'
        )
        
        # Create reply
        reply = Comment.objects.create(
            content_object=self.task,
            author=self.user,
            text='Reply comment',
            parent=parent
        )
        
        self.assertEqual(reply.parent, parent)
        self.assertTrue(reply.is_reply)
        self.assertEqual(parent.reply_count, 1)
    
    def test_comment_reactions(self):
        """Test adding reactions to comments"""
        from comments.models import Comment, CommentReaction
        
        comment = Comment.objects.create(
            content_object=self.task,
            author=self.user,
            text='Test comment'
        )
        
        # Add reaction
        url = reverse('comment-react', kwargs={'pk': comment.id})
        response = self.client.post(url, {'reaction_type': 'LIKE'})
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(comment.reactions.count(), 1)
    
    def test_edit_marks_comment_as_edited(self):
        """Test that editing a comment marks it as edited"""
        from comments.models import Comment
        
        comment = Comment.objects.create(
            content_object=self.task,
            author=self.user,
            text='Original text'
        )
        
        # Edit comment
        comment.text = 'Edited text'
        comment.save()
        
        comment.refresh_from_db()
        self.assertTrue(comment.is_edited)       
        
        
          