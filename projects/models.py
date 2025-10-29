from django.db import models
from django.conf import settings
from django.utils.text import slugify

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
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['due_date']),
        ] 
        
    def __str__(self):
        return self.name 
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
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
