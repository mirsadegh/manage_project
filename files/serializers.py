
from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import Attachment
from accounts.serializers import UserSerializer


class AttachmentSerializer(serializers.ModelSerializer):
    """Serializer for file attachments"""
    
    uploaded_by = UserSerializer(read_only=True)
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    file_size_mb = serializers.ReadOnlyField()
    file_extension = serializers.ReadOnlyField()
    
    class Meta:
        model = Attachment
        fields = [
            'id', 'file', 'file_url', 'original_filename', 'file_size',
            'file_size_mb', 'file_type', 'file_extension', 'file_hash',
            'is_image', 'image_width', 'image_height', 'thumbnail',
            'thumbnail_url', 'description', 'uploaded_by', 'uploaded_at',
            'download_count', 'last_downloaded_at'
        ]
        read_only_fields = [
            'id', 'original_filename', 'file_size', 'file_type', 'file_hash',
            'is_image', 'image_width', 'image_height', 'thumbnail',
            'uploaded_by', 'uploaded_at', 'download_count', 'last_downloaded_at'
        ]
    
    def get_file_url(self, obj):
        """Get secure file URL"""
        request = self.context.get('request')
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return None
    
    def get_thumbnail_url(self, obj):
        """Get thumbnail URL for images"""
        request = self.context.get('request')
        if request and obj.thumbnail:
            return request.build_absolute_uri(obj.thumbnail.url)
        return None


class AttachmentUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading files"""
    
    content_type = serializers.CharField(write_only=True)
    object_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Attachment
        fields = ['file', 'description', 'content_type', 'object_id']
    
    def validate_content_type(self, value):
        """Validate content type exists"""
        allowed_models = ['task', 'project', 'comment']
        
        if value.lower() not in allowed_models:
            raise serializers.ValidationError(
                f'Attachments not allowed on {value}. Allowed: {", ".join(allowed_models)}'
            )
        
        try:
            if value == 'task':
                return ContentType.objects.get(app_label='tasks', model='task')
            elif value == 'project':
                return ContentType.objects.get(app_label='projects', model='project')
            elif value == 'comment':
                return ContentType.objects.get(app_label='comments', model='comment')
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(f'Content type "{value}" not found')
    
    def validate_file(self, value):
        """Additional file validation"""
        # Check if duplicate file (same hash)
        if value:
            from hashlib import sha256
            file_hash = sha256(value.read()).hexdigest()
            value.seek(0)
            
            # Check if file with same hash exists
            duplicate = Attachment.objects.filter(file_hash=file_hash).first()
            if duplicate:
                raise serializers.ValidationError(
                    f'This file already exists (uploaded by {duplicate.uploaded_by.username} '
                    f'on {duplicate.uploaded_at.strftime("%Y-%m-%d")})'
                )
        
        return value
    
    def create(self, validated_data):
        """Create attachment with uploader"""
        validated_data['uploaded_by'] = self.context['request'].user
        return super().create(validated_data)