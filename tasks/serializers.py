from rest_framework  import serializers
from .models import Task, TaskLabel, TaskLabelAssignment, TaskDependency, TaskList
from accounts.serializers import UserSerializer


class TaskLabelSerializer(serializers.ModelSerializer):
    """Task label serializer"""
    
    class Meta:
        model = TaskLabel
        fields = ['id', 'name', 'color']
        read_only_fields = ['id']


class TaskListSerializer(serializers.ModelSerializer):
    """Task list serializer"""
    
    task_count = serializers.SerializerMethodField()
    
    
    class Meta:
        model = TaskList
        fields = ['id', 'name', 'description', 'position', 'task_count', 'created_at']
        read_only_fields = ['id', 'created_at']


class TaskSerializer(serializers.ModelSerializer):
    """Task serializer"""
    
    assignee = UserSerializer(read_only=True)
    assignee_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    created_by = UserSerializer(read_only=True)
    labels = TaskLabelSerializer(source='label_assignments',many=True, read_only=True)
    
    is_overdue = serializers.ReadOnlyField()
    
    class Meta:
        model = Task
        fields = [
                    'id', 'title', 'description', 'project', 'task_list',
                    'parent_task', 'assignee', 'assignee_id', 'created_by',
                    'status', 'priority', 'start_date', 'due_date',
                    'completed_at', 'estimated_hours', 'actual_hours',
                    'position', 'labels', 'is_overdue', 'created_at', 'updated_at'
                  ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']



class TaskDetailSerializer(TaskSerializer):
    """Task detail serializer"""
    
    subtasks = serializers.SerializerMethodField()
    dependencies = serializers.SerializerMethodField()
    
    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + ['subtasks', 'dependencies']
    
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
    
    
    
    
    
       
     