from django.db import models
from django.conf import settings
from projects.models import Project

class TaskList(models.Model):
    """Task lists/boards within projects (like Kanban columns)"""
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='task_lists'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    position = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['position', 'created_at']
        unique_together = ['project', 'name']
    
    def __str__(self):
        return f"{self.project.name} - {self.name}"


class Task(models.Model):
    """Individual tasks"""
    
    class Status(models.TextChoices):
        TODO = 'TODO', 'To Do'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        IN_REVIEW = 'IN_REVIEW', 'In Review'
        COMPLETED = 'COMPLETED', 'Completed'
        BLOCKED = 'BLOCKED', 'Blocked'
    
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'
    
    # Basic info
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    
    # Relationships
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    task_list = models.ForeignKey(
        TaskList,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks'
    )
    parent_task = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subtasks'
    )
    
    # Assignment
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tasks'
    )
    
    # Status and priority
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.TODO
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )
    
    # Timeline
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Effort estimation
    estimated_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    actual_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Position in list
    position = models.IntegerField(default=0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['position', '-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def is_overdue(self):
        """Check if task is overdue"""
        from django.utils import timezone
        if self.due_date and self.status != self.Status.COMPLETED:
            return timezone.now().date() > self.due_date
        return False


class TaskLabel(models.Model):
    """Labels/tags for tasks"""
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='labels'
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    
    class Meta:
        unique_together = ['project', 'name']
        ordering = ['name']
    
    def __str__(self):
        return self.name


class TaskLabelAssignment(models.Model):
    """Many-to-many relationship between tasks and labels"""
    
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='label_assignments'
    )
    label = models.ForeignKey(
        TaskLabel,
        on_delete=models.CASCADE,
        related_name='task_assignments'
    )
    
    class Meta:
        unique_together = ['task', 'label']
    
    def __str__(self):
        return f"{self.task.title} - {self.label.name}"


class TaskDependency(models.Model):
    """Task dependencies (Task A must be completed before Task B)"""
    
    class DependencyType(models.TextChoices):
        FINISH_TO_START = 'FS', 'Finish to Start'
        START_TO_START = 'SS', 'Start to Start'
        FINISH_TO_FINISH = 'FF', 'Finish to Finish'
    
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='dependencies'
    )
    depends_on = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='dependent_tasks'
    )
    dependency_type = models.CharField(
        max_length=2,
        choices=DependencyType.choices,
        default=DependencyType.FINISH_TO_START
    )
    
    class Meta:
        unique_together = ['task', 'depends_on']
        verbose_name_plural = 'Task dependencies'
    
    def __str__(self):
        return f"{self.task.title} depends on {self.depends_on.title}"