from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import CustomUser


class UserRegistrationTests(APITestCase):
    """Test user registration"""
    
    def setUp(self):
        self.register_url = reverse('register')
    
    def test_user_registration_success(self):
        """Test successful user registration"""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'TestPass123!',
            'password2': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'DEV'
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CustomUser.objects.count(), 1)
        self.assertEqual(CustomUser.objects.get().username, 'testuser')
    
    def test_user_registration_password_mismatch(self):
        """Test registration with mismatched passwords"""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'TestPass123!',
            'password2': 'DifferentPass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'DEV'
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CustomUser.objects.count(), 0)
    
    def test_user_registration_duplicate_username(self):
        """Test registration with duplicate username"""
        CustomUser.objects.create_user(
            username='testuser',
            email='existing@example.com',
            password='TestPass123!'
        )
        
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'TestPass123!',
            'password2': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'DEV'
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserAuthenticationTests(APITestCase):
    """Test user authentication"""
    
    def setUp(self):
        self.login_url = reverse('token_obtain_pair')
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPass123!',
            role='ADMIN'
        )
    
    def test_user_login_success(self):
        """Test successful login"""
        data = {
            'email': 'test@example.com',
            'password': 'TestPass123!'
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
    
    def test_user_login_wrong_password(self):
        """Test login with wrong password"""
        data = {
            'email': 'test@example.com',
            'password': 'WrongPass123!'
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_user_login_nonexistent_email(self):
        """تست ورود با ایمیلی که در سیستم وجود ندارد"""
        data = {
            'email': 'nonexistent@example.com',
            'password': 'anypassword'  # رمز عبور مهم نیست چون ایمیل وجود ندارد
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
    def test_login_with_username_instead_of_email_fails(self):
        """تست اینکه ورود با یوزرنیم به جای ایمیل با خطای 400 مواجه می‌شود"""
        data = {
            'username': 'testuser', # ارسال فیلد اشتباهی
            'password': 'anypassword'
        }
        response = self.client.post(self.login_url, data, format='json')
        # اینجا انتظار خطای Bad Request داریم چون فیلد email ارسال نشده
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)    


class UserPermissionTests(APITestCase):
    """Test user permissions"""
    
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='Admin123!',
            role='ADMIN'
        )
        self.dev = CustomUser.objects.create_user(
            username='developer',
            email='dev@example.com',
            password='Dev123!',
            role='DEV'
        )
        self.user_list_url = reverse('user-list')
    
    def test_admin_can_list_users(self):
        """Test admin can list users"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.user_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_developer_can_list_users(self):
        """Test developer can list users"""
        self.client.force_authenticate(user=self.dev)
        response = self.client.get(self.user_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_unauthenticated_cannot_list_users(self):
        """Test unauthenticated user cannot list users"""
        response = self.client.get(self.user_list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_developer_cannot_create_user(self):
        """Test developer cannot create users"""
        self.client.force_authenticate(user=self.dev)
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'NewPass123!',
            'role': 'DEV'
        }
        response = self.client.post(self.user_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_admin_can_create_user(self):
        """Test admin can create users"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'NewPass123!',
            'password2': 'NewPass123!',
            'role': 'DEV'
        }
        response = self.client.post(self.user_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)






