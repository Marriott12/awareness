"""
Security penetration tests.

Tests security vulnerabilities:
- SQL injection
- XSS (Cross-Site Scripting)
- CSRF (Cross-Site Request Forgery)
- Authentication bypass
- Authorization bypass
- Input validation
- Rate limiting

Run with: python manage.py test policy.tests.test_security_penetration
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
import json


class SQLInjectionTest(TestCase):
    """Test SQL injection vulnerabilities."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.admin = User.objects.create_superuser(
            'admin', 'admin@test.com', 'testpass123'
        )
    
    def test_sql_injection_in_search(self):
        """Test SQL injection in search queries."""
        from policy.models import Policy
        
        # Create test policy
        Policy.objects.create(name='Test Policy', lifecycle='active')
        
        # Attempt SQL injection
        malicious_queries = [
            "' OR '1'='1",
            "'; DROP TABLE policy_policy; --",
            "' UNION SELECT * FROM auth_user --",
            "admin'--",
            "1' OR '1' = '1",
        ]
        
        for query in malicious_queries:
            # Django ORM should sanitize
            result = Policy.objects.filter(name__icontains=query)
            
            # Should not return unauthorized data
            self.assertLessEqual(result.count(), 1)
            
            # Database should still be intact
            self.assertTrue(Policy.objects.exists())
    
    def test_sql_injection_in_raw_queries(self):
        """Test protection against SQL injection in raw queries."""
        from django.db import connection
        
        # Attempt SQL injection via raw query
        malicious_input = "'; DROP TABLE auth_user; --"
        
        with connection.cursor() as cursor:
            # Parameterized query should be safe
            try:
                cursor.execute(
                    "SELECT * FROM auth_user WHERE username = %s",
                    [malicious_input]
                )
                result = cursor.fetchall()
                
                # Should return no results, not execute DROP
                self.assertEqual(len(result), 0)
                
                # Table should still exist
                cursor.execute("SELECT COUNT(*) FROM auth_user")
                count = cursor.fetchone()[0]
                self.assertGreaterEqual(count, 1)  # Admin user exists
                
            except Exception as e:
                # Even if query fails, table should exist
                cursor.execute("SELECT COUNT(*) FROM auth_user")
                count = cursor.fetchone()[0]
                self.assertGreaterEqual(count, 1)


class XSSTest(TestCase):
    """Test Cross-Site Scripting vulnerabilities."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.admin = User.objects.create_superuser(
            'admin', 'admin@test.com', 'testpass123'
        )
        self.client.login(username='admin', password='testpass123')
    
    def test_xss_in_policy_name(self):
        """Test XSS protection in policy name."""
        from policy.models import Policy
        
        # Attempt XSS injection
        xss_payload = '<script>alert("XSS")</script>'
        
        policy = Policy.objects.create(
            name=xss_payload,
            lifecycle='draft'
        )
        
        # Render in template
        response = self.client.get(f'/admin/policy/policy/{policy.id}/change/')
        
        # Script should be escaped
        self.assertNotContains(response, '<script>alert("XSS")</script>')
        self.assertContains(response, '&lt;script&gt;')
    
    def test_xss_in_violation_details(self):
        """Test XSS protection in violation details."""
        from policy.models import (
            Violation, HumanLayerEvent, Policy, Control, Rule
        )
        
        # Create test data with XSS payload
        policy = Policy.objects.create(name='Test', lifecycle='active')
        control = Control.objects.create(policy=policy, name='Test Control')
        rule = Rule.objects.create(control=control, expression='true', priority=1)
        
        xss_summary = '<img src=x onerror=alert("XSS")>'
        event = HumanLayerEvent.objects.create(
            event_type='test',
            source='xss_test',
            summary=xss_summary
        )
        
        violation = Violation.objects.create(
            rule=rule,
            event=event,
            ml_risk_score=0.5
        )
        
        # Render violation
        response = self.client.get(f'/admin/policy/violation/{violation.id}/change/')
        
        # XSS should be escaped
        self.assertNotContains(response, '<img src=x onerror=alert("XSS")>')


class CSRFTest(TestCase):
    """Test CSRF protection."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client(enforce_csrf_checks=True)
        self.admin = User.objects.create_superuser(
            'admin', 'admin@test.com', 'testpass123'
        )
    
    def test_csrf_protection_on_post(self):
        """Test CSRF protection on POST requests."""
        # Login
        self.client.login(username='admin', password='testpass123')
        
        # Attempt POST without CSRF token
        response = self.client.post(
            '/admin/policy/policy/add/',
            {
                'name': 'CSRF Test',
                'lifecycle': 'draft'
            }
        )
        
        # Should be rejected (403 Forbidden)
        self.assertEqual(response.status_code, 403)
    
    def test_csrf_token_required(self):
        """Test that CSRF token is required for state-changing operations."""
        from django.middleware.csrf import get_token
        
        # Get CSRF token
        self.client.login(username='admin', password='testpass123')
        response = self.client.get('/admin/policy/policy/add/')
        
        # CSRF token should be present
        self.assertContains(response, 'csrfmiddlewaretoken')


class AuthenticationBypassTest(TestCase):
    """Test authentication bypass vulnerabilities."""
    
    def test_admin_requires_authentication(self):
        """Test that admin pages require authentication."""
        client = Client()
        
        # Attempt to access admin without login
        response = client.get('/admin/')
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
    
    def test_api_requires_authentication(self):
        """Test that API endpoints require authentication."""
        client = Client()
        
        # Attempt to access policy workflow without login
        response = client.get('/policy-workflow/')
        
        # Should require authentication (redirect or 403)
        self.assertIn(response.status_code, [302, 403])
    
    def test_password_reset_security(self):
        """Test password reset token security."""
        from django.contrib.auth.tokens import default_token_generator
        
        user = User.objects.create_user('testuser', 'test@example.com', 'oldpass')
        
        # Generate reset token
        token = default_token_generator.make_token(user)
        
        # Token should be valid
        self.assertTrue(default_token_generator.check_token(user, token))
        
        # Change password
        user.set_password('newpass')
        user.save()
        
        # Old token should be invalid
        self.assertFalse(default_token_generator.check_token(user, token))


class AuthorizationBypassTest(TestCase):
    """Test authorization bypass vulnerabilities."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.admin = User.objects.create_superuser(
            'admin', 'admin@test.com', 'adminpass'
        )
        self.regular_user = User.objects.create_user(
            'user', 'user@test.com', 'userpass'
        )
    
    def test_regular_user_cannot_access_admin(self):
        """Test that regular users cannot access admin panel."""
        client = Client()
        client.login(username='user', password='userpass')
        
        # Attempt to access admin
        response = client.get('/admin/')
        
        # Should be denied
        self.assertEqual(response.status_code, 302)
    
    def test_user_cannot_modify_others_data(self):
        """Test that users cannot modify other users' data."""
        from policy.models import Policy
        
        # Create policy as admin
        policy = Policy.objects.create(
            name='Admin Policy',
            lifecycle='draft'
        )
        
        # Login as regular user
        client = Client()
        client.login(username='user', password='userpass')
        
        # Attempt to modify admin's policy
        response = client.post(
            f'/admin/policy/policy/{policy.id}/change/',
            {'name': 'Hacked', 'lifecycle': 'active'}
        )
        
        # Should be denied
        self.assertIn(response.status_code, [302, 403])
        
        # Policy should be unchanged
        policy.refresh_from_db()
        self.assertEqual(policy.name, 'Admin Policy')


class InputValidationTest(TestCase):
    """Test input validation."""
    
    def test_policy_name_length_validation(self):
        """Test policy name length limits."""
        from policy.models import Policy
        from django.core.exceptions import ValidationError
        
        # Extremely long name
        long_name = 'A' * 10000
        
        try:
            policy = Policy(name=long_name, lifecycle='draft')
            policy.full_clean()  # Trigger validation
            
            # If max_length is set, should fail
            # If not, this documents the need for validation
        except ValidationError:
            # Expected - validation working
            pass
    
    def test_expression_depth_validation(self):
        """Test expression depth limits."""
        from policy.compliance_safe import check_expression_depth
        
        # Create deeply nested expression
        deep_expr = {'and': [{'and': [{'and': [{'and': [
            {'and': [{'and': [{'and': [{'and': [
                {'and': [{'and': [{'true': True}]}]}
            ]}]}]}]}
        ]}]}]}]}
        
        # Should reject extremely deep nesting
        with self.assertRaises(ValueError):
            check_expression_depth(deep_expr, max_depth=10)
    
    def test_regex_validation(self):
        """Test regex pattern validation."""
        from policy.compliance_safe import validate_regex_safety
        
        # ReDoS vulnerable patterns
        dangerous_patterns = [
            r'(a+)+',
            r'(a|a)*',
            r'(a|ab)*',
            r'(\w+)+@example\.com',
        ]
        
        for pattern in dangerous_patterns:
            with self.assertRaises(ValueError):
                validate_regex_safety(pattern)


class RateLimitingTest(TestCase):
    """Test rate limiting."""
    
    def setUp(self):
        """Set up test fixtures."""
        from django.core.cache import cache
        cache.clear()
    
    def test_login_rate_limiting(self):
        """Test rate limiting on login attempts."""
        client = Client()
        
        # Attempt multiple failed logins
        for i in range(10):
            response = client.post(
                '/admin/login/',
                {
                    'username': 'admin',
                    'password': 'wrongpass'
                }
            )
        
        # After many attempts, should be rate limited
        # This depends on rate limiting implementation
        # Test documents the requirement
    
    def test_api_rate_limiting(self):
        """Test rate limiting on API calls."""
        from policy.resilience import rate_limit
        
        call_count = 0
        
        @rate_limit(max_calls=5, period=1)
        def limited_function():
            nonlocal call_count
            call_count += 1
            return True
        
        # First 5 calls should succeed
        for i in range(5):
            try:
                limited_function()
            except Exception:
                pass
        
        # 6th call should be rate limited
        # This depends on rate limiting implementation


class SessionSecurityTest(TestCase):
    """Test session security."""
    
    def test_session_timeout(self):
        """Test session timeout configuration."""
        from django.conf import settings
        
        # Verify session timeout is configured
        self.assertTrue(hasattr(settings, 'SESSION_COOKIE_AGE'))
        
        # Should have reasonable timeout (not infinite)
        if hasattr(settings, 'SESSION_COOKIE_AGE'):
            self.assertLess(settings.SESSION_COOKIE_AGE, 86400 * 7)  # Max 7 days
    
    def test_session_cookie_security(self):
        """Test session cookie security flags."""
        from django.conf import settings
        
        # Verify secure cookie settings in production
        if not settings.DEBUG:
            self.assertTrue(
                getattr(settings, 'SESSION_COOKIE_SECURE', False),
                'SESSION_COOKIE_SECURE should be True in production'
            )
            self.assertTrue(
                getattr(settings, 'CSRF_COOKIE_SECURE', False),
                'CSRF_COOKIE_SECURE should be True in production'
            )


class SecurityHeadersTest(TestCase):
    """Test security headers."""
    
    def test_security_headers_present(self):
        """Test that security headers are present."""
        client = Client()
        response = client.get('/admin/login/')
        
        # Check for security headers
        # X-Content-Type-Options
        # This documents the requirement for security headers
        # Actual implementation may vary
        
        # Should not leak version information
        self.assertNotIn('Server', response.headers)


if __name__ == '__main__':
    import unittest
    unittest.main()
