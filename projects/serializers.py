from rest_framework import serializers
from .models import Project, ProjectMember
from accounts.serializers import UserSerializer


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
    
    owner = UserSerializer(read_only=True)
    manager = UserSerializer(read_only=True)
    manager_id = serializers.IntegerField(write_only=True, required=False)
    
    is_overdue = serializers.ReadOnlyField()
    total_tasks = serializers.ReadOnlyField()
    completed_tasks = serializers.ReadOnlyField()
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'slug', 'description', 'owner', 'manager', 
            'manager_id', 'status', 'priority', 'progress', 'start_date', 
            'due_date', 'completed_date', 'budget', 'is_active', 'is_public',
            'is_overdue', 'total_tasks', 'completed_tasks', 'created_at', 'updated_at'
            ]
        read_only_fields = ['id', 'slug', 'owner','created_at','updated_at']
        
    
class ProjectDetailSerializer(ProjectSerializer): 
    """Detailed project serializer with members"""  
    
    members = ProjectMemberSerializer(many=True, read_only=True)
    
    
    class Meta(ProjectSerializer.Meta) :
        fields = ProjectSerializer.Meta.fields + ['members']    
        
class ProjectCreateSerializer(serializers.ModelSerializer):
    """Create project serializer"""
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'manager_id', 'status',
            'priority', 'start_date', 'due_date', 'budget',
            'is_public'
        ]



