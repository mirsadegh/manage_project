from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator


class CustomUserManager(BaseUserManager):
    """Custom user manager for email authentication."""
    
    def create_user(self, email, username, password=None, **extra_fields):
        """Create and save a regular user"""
        if not email:
            raise ValueError('Users must have an email address')
        email = self.normalize_email(email)
        user = self.model(email=email,username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, username, password=None, **extra_fields):
        """Create and save a superuser"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', CustomUser.Role.ADMIN)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, username, password, **extra_fields)




class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    objects = CustomUserManager()
    
    # User roles
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        PROJECT_MANAGER = 'PM', 'Project Manager'
        TEAM_LEAD = 'TL', 'Team Lead'
        DEVELOPER = 'DEV', 'Developer'
        DESIGNER = 'DES', 'Designer'
        CLIENT = 'CLIENT', 'Client'
    # Additional field for user role    
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.DEVELOPER,
    )
    
    phone_number = models.CharField(
    max_length=15,
    blank=True,
    null=True,
    validators=[
        RegexValidator(
            # این Regex با فرمت 09123456789 و +989123456789 مطابقت دارد
            regex=r'^(\+98|0)9\d{9}$',
            message="Phone number must be entered in the format: '09123456789' or '+989123456789'."
        )
    ]
)
    
    bio = models.TextField(max_length=500, blank=True)
    
    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True
    ) 
    job_title = models.CharField(max_length=100, blank=True)
    
    department = models.CharField(max_length=100, blank=True)
    
    # Availablity status
    is_available = models.BooleanField(default=True)
    
    # professional info
    skills = models.JSONField(default=list, blank=True)
    
    hourly_rate = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True
    )  
    
    # Timestamps
    # date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']
        
    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"
    
    
    def get_full_name(self):
        """Return the user's full name."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.username
    
    @property
    def is_manager(self):
        """Check if user is a manager."""
        return self.role in [self.Role.ADMIN, self.Role.PROJECT_MANAGER, self.Role.TEAM_LEAD]
        
    @property
    def is_client(self):
        """Check if user is a client."""
        return self.role == self.Role.CLIENT

