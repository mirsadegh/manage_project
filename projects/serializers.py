from rest_framework import serializers
from django.core.validators import MaxLengthValidator
from .models import Project, ProjectMember
from accounts.serializers import UserSerializer, UserPublicSerializer
from comments.serializers import CommentSerializer
from files.serializers import AttachmentSerializer


class ProjectMemberSerializer(serializers.ModelSerializer):
    """Project member serializer"""
    
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = ProjectMember
        fields = ['id', 'user', 'user_id', 'role', 'joined_at']
        read_only_fields = ['id', 'joined_at']
        
class ProjectSerializer(serializers.ModelSerializer):
    """Project list serializer"""

    owner = UserPublicSerializer(read_only=True)
    manager = UserPublicSerializer(read_only=True)
    manager_id = serializers.IntegerField(write_only=True, required=False)

    name = serializers.CharField(max_length=200, validators=[MaxLengthValidator(200)])
    description = serializers.CharField(max_length=1000, validators=[MaxLengthValidator(1000)], required=False, allow_blank=True)

    is_overdue = serializers.ReadOnlyField()
    total_tasks = serializers.ReadOnlyField()
    completed_tasks = serializers.ReadOnlyField()
    progress = serializers.SerializerMethodField()
    comment_count = serializers.ReadOnlyField()
    attachment_count = serializers.ReadOnlyField()

    def get_progress(self, obj):
        total = obj.total_tasks  # calls the @property
        if total == 0:
            return 0
        completed = obj.completed_tasks  # calls the @property
        return int((completed / total) * 100)

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'slug', 'description', 'owner', 'manager', 
            'manager_id', 'status', 'priority', 'progress', 'start_date', 
            'due_date', 'completed_date', 'budget', 'is_active', 'is_public',
            'is_overdue', 'total_tasks', 'completed_tasks', 'created_at', 'updated_at',
            'comment_count', 'attachment_count'  
            ]
        read_only_fields = ['id', 'slug', 'owner','created_at','updated_at']
        
    
class ProjectDetailSerializer(ProjectSerializer): 
    """Detailed project serializer with members"""  
    
    members = ProjectMemberSerializer(many=True, read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    
    
    class Meta(ProjectSerializer.Meta) :
        fields = ProjectSerializer.Meta.fields + ['members', 'comments', 'attachments']    
        
class ProjectCreateSerializer(serializers.ModelSerializer):
    """Create project serializer"""
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'manager_id', 'status',
            'priority', 'start_date', 'due_date', 'budget',
            'is_public'
        ]



