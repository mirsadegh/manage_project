from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from django.http import FileResponse, Http404
from django.utils import timezone
from .models import Attachment
from .serializers import AttachmentSerializer, AttachmentUploadSerializer
from .permissions import CanAccessAttachment
import mimetypes


class AttachmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for file attachments with security.
    
    Endpoints:
    - GET /attachments/ - List attachments
    - POST /attachments/ - Upload file
    - GET /attachments/{id}/ - Get attachment details
    - GET /attachments/{id}/download/ - Download file
    - DELETE /attachments/{id}/ - Delete attachment
    - GET /attachments/{id}/preview/ - Preview image (if applicable)
    """
    
    queryset = Attachment.objects.all()
    permission_classes = [IsAuthenticated, CanAccessAttachment]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return AttachmentUploadSerializer
        return AttachmentSerializer
    
    def get_queryset(self):
        """Filter attachments by content type and object"""
        queryset = Attachment.objects.select_related('uploaded_by')
        
        # Filter by content type and object
        content_type = self.request.query_params.get('content_type')
        object_id = self.request.query_params.get('object_id')
        
        if content_type and object_id:
            try:
                ct = ContentType.objects.get(model=content_type.lower())
                queryset = queryset.filter(content_type=ct, object_id=object_id)
            except ContentType.DoesNotExist:
                queryset = queryset.none()
        
        # Filter by user's uploads
        if self.request.query_params.get('my_uploads') == 'true':
            queryset = queryset.filter(uploaded_by=self.request.user)
        
        # Filter by file type
        file_type = self.request.query_params.get('file_type')
        if file_type:
            if file_type == 'images':
                queryset = queryset.filter(is_image=True)
            elif file_type == 'documents':
                queryset = queryset.filter(
                    file_type__in=[
                        'application/pdf',
                        'application/msword',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    ]
                )
        
        return queryset
    
    def perform_create(self, serializer):
        """Save attachment with uploader and log activity"""
        attachment = serializer.save(uploaded_by=self.request.user)
        
        # Log activity
        from activity.models import ActivityLog
        ActivityLog.log_activity(
            user=self.request.user,
            action=ActivityLog.Action.UPLOADED,
            content_object=attachment.content_object,
            description=f'Uploaded file "{attachment.original_filename}"',
            request=self.request
        )
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download file with security checks.
        Increments download counter.
        """
        attachment = self.get_object()
        
        # Check if file is safe
        if not attachment.is_safe:
            return Response(
                {'error': 'This file has been flagged as unsafe and cannot be downloaded'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if file exists
        if not attachment.file:
            raise Http404('File not found')
        
        # Increment download counter
        attachment.increment_download_count()
        
        # Log activity
        from activity.models import ActivityLog
        ActivityLog.log_activity(
            user=request.user,
            action=ActivityLog.Action.DOWNLOADED,
            content_object=attachment,
            description=f'Downloaded file "{attachment.original_filename}"',
            request=request
        )
        
        # Serve file
        response = FileResponse(
            attachment.file.open('rb'),
            content_type=attachment.file_type
        )
        
        # Set content disposition to trigger download
        response['Content-Disposition'] = f'attachment; filename="{attachment.original_filename}"'
        
        return response
    
    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """
        Preview file (for images and PDFs).
        Returns file for inline display.
        """
        attachment = self.get_object()
        
        # Only allow preview for images and PDFs
        if not (attachment.is_image or attachment.file_type == 'application/pdf'):
            return Response(
                {'error': 'Preview not available for this file type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if file is safe
        if not attachment.is_safe:
            return Response(
                {'error': 'This file has been flagged as unsafe'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Serve file for inline display
        response = FileResponse(
            attachment.file.open('rb'),
            content_type=attachment.file_type
        )
        
        # Set content disposition for inline display
        response['Content-Disposition'] = f'inline; filename="{attachment.original_filename}"'
        
        return response
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get file upload statistics"""
        user = request.user
        
        total_files = Attachment.objects.filter(uploaded_by=user).count()
        total_size = Attachment.objects.filter(uploaded_by=user).aggregate(
            total=models.Sum('file_size')
        )['total'] or 0
        
        stats = {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'images': Attachment.objects.filter(uploaded_by=user, is_image=True).count(),
            'documents': Attachment.objects.filter(
                uploaded_by=user,
                file_type__in=[
                    'application/pdf',
                    'application/msword',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                ]
            ).count(),
        }
        
        return Response(stats)
    
    def perform_destroy(self, instance):
        """Log file deletion before removing"""
        from activity.models import ActivityLog
        
        ActivityLog.log_activity(
            user=self.request.user,
            action=ActivityLog.Action.DELETED,
            content_object=instance.content_object,
            description=f'Deleted file "{instance.original_filename}"',
            request=self.request
        )
        
        instance.delete()
        
    
    def perform_create(self, serializer):
        """Save attachment, log activity, and trigger virus scan"""
        attachment = serializer.save(uploaded_by=self.request.user)
        
        # Log activity
        from activity.models import ActivityLog
        ActivityLog.log_activity(
            user=self.request.user,
            action=ActivityLog.Action.UPLOADED,
            content_object=attachment.content_object,
            description=f'Uploaded file "{attachment.original_filename}"',
            request=self.request
        )
        
        # Trigger async virus scan
        from .tasks import scan_uploaded_file
        scan_uploaded_file.delay(attachment.id)    
        
        
        
        
        