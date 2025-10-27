from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    """Form for creating new users"""
    
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'role')

class CustomUserChangeForm(UserChangeForm):
    """Form for updating users"""
    
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 
                 'phone_number', 'bio', 'profile_picture', 'job_title', 
                 'department', 'is_available', 'skills', 'hourly_rate')





