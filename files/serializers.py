
from rest_framework import serializers
from .models import Attachment
from accounts.serializers import UserSerializer


class AttachmentSerializer(serializers.ModelSerializer):
    """Serializer for file attachments"""
    
    uploaded_by = UserSerializer(read_only=True)
    file_size_mb = serializers.ReadOnlyField()
    
    # For writing
    content_type_id = serializers.IntegerField(write_only=True, required=False)
    object_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = Attachment
        fields = [
            'id', 'file', 'filename', 'file_size', 'file_size_mb',
            'file_type', 'description', 'uploaded_by', 'uploaded_at',
            'content_type_id', 'object_id'
        ]
        read_only_fields = ['id', 'filename', 'file_size', 'file_type', 'uploaded_at']