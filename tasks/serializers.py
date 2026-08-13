from rest_framework  import serializers
from .models import Task, TaskLabel, TaskLabelAssignment, TaskDependency, TaskList
from accounts.serializers import UserSerializer
from comments.serializers import CommentSerializer
from files.serializers import AttachmentSerializer



class TaskLabelSerializer(serializers.ModelSerializer):
    """Task label serializer"""
    
    class Meta:
        model = TaskLabel
        fields = [
            'id', 'name', 'color', 'project'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class TaskListSerializer(serializers.ModelSerializer):
    """Task list serializer"""
    
    task_count = serializers.SerializerMethodField()
    
    
    class Meta:
        model = TaskList
        fields = ['id', 'project', 'name', 'description', 'created_by', 'is_active',
                  'order', 'position', 'task_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
        
    def get_task_count(self, obj):
        return obj.tasks.count()
    


class TaskSerializer(serializers.ModelSerializer):
    """Task serializer"""
    
    assignee = UserSerializer(read_only=True)
    assignee_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    created_by = UserSerializer(read_only=True)
    labels = TaskLabelSerializer(source='label_assignments',many=True, read_only=True)
    depends_on = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(),
        many=True,
        write_only=True,
        required=False,
        allow_empty=True,
    )
    
    is_overdue = serializers.ReadOnlyField()
    
    class Meta:
        model = Task
        fields = [
                    'id', 'title', 'description', 'project', 'task_list',
                    'parent_task', 'assignee', 'assignee_id', 'created_by',
                    'status', 'priority', 'start_date', 'due_date',
                    'completed_at', 'estimated_hours', 'actual_hours',
                    'position', 'order', 'is_active', 'depends_on',
                    'labels', 'is_overdue', 'created_at', 'updated_at'
                  ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def validate(self, attrs):
        start_date = attrs.get('start_date')
        due_date = attrs.get('due_date')
        if start_date and due_date and start_date > due_date:
            raise serializers.ValidationError({
                'due_date': 'Due date must be after start date.'
            })
        return attrs



class TaskDetailSerializer(TaskSerializer):
    """Task detail serializer"""
    
    subtasks = serializers.SerializerMethodField()
    dependencies = serializers.SerializerMethodField()
    
    comments = CommentSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    
    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + ['subtasks', 'dependencies','comments', 'attachments']
    
    def get_subtasks(self, obj):
        subtasks = obj.subtasks.all()
        return TaskSerializer(subtasks, many=True).data
    
    def get_dependencies(self, obj):
        deps = obj.dependencies.all()
        return [{
            'id': dep.id,
            'depends_on': TaskSerializer(dep.depends_on).data,
            'dependency_type': dep.dependency_type
        } for dep in deps]


class TaskDependencySerializer(serializers.ModelSerializer):
    """Task dependency serializer"""
    
    class Meta:
        model = TaskDependency
        fields = ['id', 'task', 'depends_on', 'dependency_type']
        read_only_fields = ['id']
    
    
    
    
    
       
     