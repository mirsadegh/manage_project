import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()


class TestUserRegistration:
    """Test user registration endpoint."""

    def test_user_registration_success(self, api_client, register_url):
        """Test successful user registration."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'TestPass123!',
            'password2': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'DEV'  # Adjust role as needed
        }
        response = api_client.post(register_url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.count() == 1
        assert User.objects.get().username == 'testuser'

    def test_user_registration_password_mismatch(self, api_client, register_url):
        """Test registration with mismatched passwords."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'TestPass123!',
            'password2': 'DifferentPass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'DEV'
        }
        response = api_client.post(register_url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert User.objects.count() == 0

    def test_user_registration_duplicate_username(self, api_client, register_url, user):
        """Test registration with a duplicate username."""
        # The 'user' fixture provides an existing user in the database.
        data = {
            'username': user.username,  # Use the username from the fixture
            'email': 'new_test@example.com',
            'password': 'TestPass123!',
            'password2': 'TestPass123!',
            'first_name': 'New',
            'last_name': 'User',
            'role': 'DEV'
        }
        response = api_client.post(register_url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestUserAuthentication:
    """Test user authentication (login) endpoint."""

    def test_user_login_success(self, api_client, login_url, user):
        """Test successful login with correct credentials."""
        data = {
            'email': user.email,
            'password': 'password'  # Default password from Factory Boy is 'password'
        }
        response = api_client.post(login_url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_user_login_wrong_password(self, api_client, login_url, user):
        """Test login with an incorrect password."""
        data = {
            'email': user.email,
            'password': 'wrongpassword'
        }
        response = api_client.post(login_url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_login_nonexistent_email(self, api_client, login_url):
        """Test login with an email that does not exist."""
        data = {
            'email': 'nonexistent@example.com',
            'password': 'anypassword'
        }
        response = api_client.post(login_url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
    def test_login_with_username_instead_of_email_fails(self, api_client, login_url):
        """Test that logging in with username instead of email returns a 400 error."""
        data = {
            'username': 'someuser',  # Incorrect field name
            'password': 'anypassword'
        }
        response = api_client.post(login_url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestUserPermissions:
    """Test permissions for different user roles on user endpoints."""

    def test_admin_can_list_users(self, admin_client, user_list_url):
        """Test that an admin can list all users."""
        response = admin_client.get(user_list_url)
        assert response.status_code == status.HTTP_200_OK

    def test_developer_can_list_users(self, dev_client, user_list_url):
        """Test that a developer can list all users."""
        response = dev_client.get(user_list_url)
        assert response.status_code == status.HTTP_200_OK
    
    def test_unauthenticated_cannot_list_users(self, api_client, user_list_url):
        """Test that an unauthenticated user cannot list users."""
        response = api_client.get(user_list_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_developer_cannot_create_user(self, dev_client, user_list_url):
        """Test that a developer is forbidden from creating new users."""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'NewPass123!',
            'password2': 'NewPass123!',
            'role': 'DEV'
        }
        response = dev_client.post(user_list_url, data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create_user(self, admin_client, user_list_url):
        """Test that an admin can create new users."""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'NewPass123!',
            'password2': 'NewPass123!',
            'role': 'DEV'
        }
        response = admin_client.post(user_list_url, data)
        assert response.status_code == status.HTTP_201_CREATED