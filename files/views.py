from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from .models import Attachment
from .serializers import AttachmentSerializer


class AttachmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for file attachments.
    
    Endpoints:
    - GET /attachments/ - List attachments
    - POST /attachments/ - Upload file
    - GET /attachments/{id}/ - Get attachment
    - DELETE /attachments/{id}/ - Delete attachment
    """
    
    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter attachments by content type and object"""
        queryset = Attachment.objects.select_related('uploaded_by')
        
        content_type = self.request.query_params.get('content_type')
        object_id = self.request.query_params.get('object_id')
        
        if content_type and object_id:
            try:
                ct = ContentType.objects.get(model=content_type.lower())
                queryset = queryset.filter(content_type=ct, object_id=object_id)
            except ContentType.DoesNotExist:
                queryset = queryset.none()
        
        return queryset
    
    def perform_create(self, serializer):
        """Save attachment with uploader"""
        serializer.save(uploaded_by=self.request.user)