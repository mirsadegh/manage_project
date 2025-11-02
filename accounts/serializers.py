from dataclasses import fields
from pyexpat import model
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    """"Basic User Serializer"""
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone_number', 'job_title', 'department',
            'profile_picture', 'is_available', 'data_joined'
        ]
        
        read_only_fields = ['id','data_joined']
        
 
class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed user serializer with more fields"""
    
    full_name = serializers.SerializerMethodField()
    is_manager = serializers.ReadOnlyField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'role', 'phone_number', 'bio', 'profile_picture',
            'job_title', 'department', 'is_available', 'skills',
            'hourly_rate', 'is_manager', 'date_joined', 'updated_at'
        ]
        read_only_fields = ['id','date_joined', 'updated_at']
        
        def get_full_name(self, obj):
            return obj.get_full_name()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """User registration serializer"""
    
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators= [validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = CustomUser
        fields = [
            'username', 'email', 'password', 'password2',
            'first_name', 'last_name', 'role'
        ]
        
    def validate(self, attrs):
        if attrs['password'] != attrs['password@']:
            raise serializers.ValidationError({
                "password": "Password fields didn't mathc."
            })
            
            return attrs
        
    def create(self, validated_data):
        validated_data.pop('password2')
        user = CustomUser.objects.create_user(**validated_data) 
        return user
    
class ChangePasswordSerializer(serializers.Serializer):
    """Change password serialzer"""
    
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)  
    new_password2 = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({
                "new_password": "Password fields didn't match."
            })
        return attrs     


