from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q, F, Count
from django.utils.text import slugify
from django.contrib.contenttypes.fields import GenericRelation


class Project(models.Model):
    """Main project model"""
    
    class Status(models.TextChoices):
        PLANNING = 'PLANNING', 'Planning'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        ON_HOLD = 'ON_HOLD', 'On Hold'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        
        
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'   
        
    name = models.CharField(max_length=200) 
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField(blank=True)
    
    # Ownership and management
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='owned_projects'
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        related_name='managed_projects',
        null=True,
        blank=True
    )
    
    # Status and progress
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.PLANNING
    )
    priority = models.CharField(
        max_length=10, 
        choices=Priority.choices, 
        default=Priority.MEDIUM
    )
    progress = models.IntegerField(default=0)  # Percentage from 0 to 100
    
    # Timeline
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    
    # Budget (optional)
    budget = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True
    )
    
    # Settings
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=False)
    
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    comments = GenericRelation(
        'comments.Comment',
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='project'
    )
    attachments = GenericRelation(
        'files.Attachment',
        content_type_field='content_type',
        object_id_field='object_id',
        related_query_name='project'
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['due_date']),
        ]
        constraints = [
            # Ensure start_date is before or equal to due_date
            models.CheckConstraint(
                check=Q(start_date__isnull=True) | Q(due_date__isnull=True) | Q(start_date__lte=F('due_date')),
                name='project_start_date_before_due_date'
            ),
            # Ensure progress is between 0 and 100
            models.CheckConstraint(
                check=Q(progress__gte=0) & Q(progress__lte=100),
                name='project_progress_percentage_valid'
            ),
            # Ensure budget is positive if set
            models.CheckConstraint(
                check=Q(budget__isnull=True) | Q(budget__gte=0),
                name='project_budget_positive'
            ),
        ]

    def clean(self):
        """Model-level validation for business rules."""
        super().clean()
        errors = {}

        # Validate dates
        if self.start_date and self.due_date and self.start_date > self.due_date:
            errors['due_date'] = 'Due date must be after start date.'

        # Validate progress
        if self.progress < 0 or self.progress > 100:
            errors['progress'] = 'Progress must be between 0 and 100.'

        # Validate budget
        if self.budget is not None and self.budget < 0:
            errors['budget'] = 'Budget cannot be negative.'

        # Validate completed_date only set when status is COMPLETED
        if self.completed_date and self.status != self.Status.COMPLETED:
            errors['completed_date'] = 'Completed date can only be set when status is COMPLETED.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            # Generate slug from name, fallback to ID if slugify returns empty
            self.slug = slugify(self.name)
            if not self.slug:
                # Use name hash or ID as fallback
                import hashlib
                self.slug = f"project-{hashlib.md5(self.name.encode()).hexdigest()[:8]}"
        self.full_clean()
        super().save(*args, **kwargs)
        
    @property
    def is_overdue(self):
        """Check if the project is overdue based on due date"""
        from django.utils import timezone
        if self.due_date and self.status != self.Status.COMPLETED:
            return timezone.now().date() > self.due_date
        return False         


    @property
    def total_tasks(self):
        """Get total number of tasks"""
        return self.tasks.count()

    @property
    def completed_tasks(self):
        """Get number of completed tasks"""
        return self.tasks.filter(status='COMPLETED').count()

    def get_task_statistics(self):
        """
        Get all task statistics in a single optimized query.
        Returns dict with total, completed, in_progress, todo, blocked counts.
        """
        from django.utils import timezone

        stats = self.tasks.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
            in_progress=Count('id', filter=Q(status='IN_PROGRESS')),
            todo=Count('id', filter=Q(status='TODO')),
            blocked=Count('id', filter=Q(status='BLOCKED')),
            in_review=Count('id', filter=Q(status='IN_REVIEW')),
            overdue=Count(
                'id',
                filter=Q(
                    due_date__lt=timezone.now().date(),
                    status__in=['TODO', 'IN_PROGRESS']
                )
            ),
        )
        return stats

    @property
    def comment_count(self):
        """Get number of comments"""
        return self.comments.count()
    
    @property
    def attachment_count(self):
        """Get number of attachments"""
        return self.attachments.count()
    
    
class ProjectMember(models.Model):
    """Project team members"""
    
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        MANAGER = 'MANAGER', 'Manager'
        MEMBER = 'MEMBER', 'Member'
        VIEWER = 'VIEWER', 'Viewer'
        
        
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='members' 
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='project_memberships'
    )    
    
    role = models.CharField(
        max_length=10, 
        choices=Role.choices, 
        default=Role.MEMBER
    )  
    
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('project', 'user')
        ordering = ['joined_at']
        
    def __str__(self):
        return f"{self.user.username} - {self.project.name} ({self.role})"    
