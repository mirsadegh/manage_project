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
    total_tasks = serializers.SerializerMethodField()
    completed_tasks = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    attachment_count = serializers.SerializerMethodField()

    def get_total_tasks(self, obj):
        # Use annotated count if available (list action), fallback to property (detail)
        if hasattr(obj, 'total_tasks_count'):
            return obj.total_tasks_count or 0
        return obj.total_tasks

    def get_completed_tasks(self, obj):
        # Use annotated count if available (list action), fallback to property (detail)
        if hasattr(obj, 'completed_tasks_count'):
            return obj.completed_tasks_count or 0
        return obj.completed_tasks

    def get_progress(self, obj):
        total = self.get_total_tasks(obj)
        if total == 0:
            return 0
        completed = self.get_completed_tasks(obj)
        return int((completed / total) * 100)

    def get_comment_count(self, obj):
        # Use annotated count if available (list action), fallback to property (detail)
        if hasattr(obj, 'comment_count_ann'):
            return obj.comment_count_ann or 0
        return obj.comment_count

    def get_attachment_count(self, obj):
        # Use annotated count if available (list action), fallback to property (detail)
        if hasattr(obj, 'attachment_count_ann'):
            return obj.attachment_count_ann or 0
        return obj.attachment_count

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
    # Write-only alias for the `manager` FK. Without this declaration the
    # auto-generated field resolves to ReadOnlyField (there is no
    # `manager_id` model attribute), so any incoming manager_id is
    # silently dropped and created projects can never have a manager.
    # Mirrors the explicit declaration already used in ProjectSerializer.
    manager_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Project
        fields = [
            'name', 'description', 'manager_id', 'status',
            'priority', 'start_date', 'due_date', 'budget',
            'is_public'
        ]




