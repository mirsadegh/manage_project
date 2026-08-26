# files/tests.py

from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import CustomUser
from projects.models import Project
from tasks.models import Task
from files.models import Attachment


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
            file=SimpleUploadedFile('test.txt', b'test content'),
            is_scanned=True,
            is_safe=True,
        )
        
        url = reverse('attachment-download', kwargs={'pk': attachment.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test.txt"')
        
        # Check download count increased
        attachment.refresh_from_db()
        self.assertEqual(attachment.download_count, 1)


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
        
        
          