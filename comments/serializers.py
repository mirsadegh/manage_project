# comments/serializers.py

from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import Comment, CommentMention, CommentReaction
from accounts.serializers import UserSerializer


class CommentReactionSerializer(serializers.ModelSerializer):
    """Serializer for comment reactions"""
    
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = CommentReaction
        fields = ['id', 'user', 'reaction_type', 'created_at']
        read_only_fields = ['id', 'created_at']


class CommentSerializer(serializers.ModelSerializer):
    """Serializer for comments"""
    
    author = UserSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    reactions = CommentReactionSerializer(many=True, read_only=True)
    reply_count = serializers.ReadOnlyField()
    is_reply = serializers.ReadOnlyField()
    
    # For writing
    content_type_id = serializers.IntegerField(write_only=True, required=False)
    object_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = Comment
        fields = [
            'id', 'author', 'text', 'parent', 'content_type_id', 'object_id',
            'is_edited', 'created_at', 'updated_at', 'replies', 'reactions',
            'reply_count', 'is_reply'
        ]
        read_only_fields = ['id', 'author', 'is_edited', 'created_at', 'updated_at']
    
    def get_replies(self, obj):
        """Get direct replies to this comment"""
        if obj.replies.exists():
            return CommentSerializer(obj.replies.all(), many=True).data
        return []
    
    def validate(self, attrs):
        """Validate that parent comment exists if provided"""
        parent = attrs.get('parent')
        if parent:
            # Ensure parent is not a reply itself (limit nesting to 1 level)
            if parent.parent:
                raise serializers.ValidationError({
                    'parent': 'Cannot reply to a reply. Reply to the parent comment instead.'
                })
        return attrs


class CommentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating comments"""
    
    content_type = serializers.CharField(write_only=True)
    object_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Comment
        fields = ['text', 'parent', 'content_type', 'object_id']
    
    def validate_content_type(self, value):
        """Validate that content type exists and is allowed"""
        allowed_models = ['task', 'project']  # Add more as needed
        
        if value.lower() not in allowed_models:
            raise serializers.ValidationError(
                f'Comments not allowed on {value}. Allowed: {", ".join(allowed_models)}'
            )
        
        try:
            app_label = 'tasks' if value == 'task' else 'projects'
            return ContentType.objects.get(app_label=app_label, model=value.lower())
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(f'Content type "{value}" not found')
    
    def create(self, validated_data):
        """Create comment with author"""
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class CommentMentionSerializer(serializers.ModelSerializer):
    """Serializer for comment mentions"""
    
    mentioned_user = UserSerializer(read_only=True)
    
    class Meta:
        model = CommentMention
        fields = ['id', 'mentioned_user', 'created_at']
        read_only_fields = ['id', 'created_at']