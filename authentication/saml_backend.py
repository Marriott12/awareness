"""SAML 2.0 authentication backend for SSO integration.

Integrates with SAML identity providers for enterprise single sign-on.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.conf import settings
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class SAMLAuthenticationBackend(BaseBackend):
    """SAML 2.0 authentication backend."""
    
    def authenticate(self, request, saml_attributes=None, **kwargs):
        """
        Authenticate user via SAML attributes.
        
        Args:
            request: Django request object
            saml_attributes: Dictionary of SAML attributes from IdP
        
        Returns:
            User object if authenticated, None otherwise
        """
        if not saml_attributes:
            return None
        
        try:
            # Extract user information from SAML attributes
            username = saml_attributes.get('uid', [None])[0]
            email = saml_attributes.get('email', [None])[0]
            first_name = saml_attributes.get('givenName', [None])[0]
            last_name = saml_attributes.get('sn', [None])[0]
            
            if not username or not email:
                logger.error('Missing required SAML attributes: uid or email')
                return None
            
            # Get or create user
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': first_name or '',
                    'last_name': last_name or '',
                }
            )
            
            # Update user information from SAML
            if not created:
                user.email = email
                user.first_name = first_name or user.first_name
                user.last_name = last_name or user.last_name
                user.save()
            
            logger.info(f'SAML authentication successful for user: {username}')
            return user
            
        except Exception as e:
            logger.error(f'SAML authentication error: {e}')
            return None
    
    def get_user(self, user_id):
        """Get user by ID."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class LDAPAuthenticationBackend(BaseBackend):
    """LDAP authentication backend for Active Directory integration."""
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user via LDAP/Active Directory.
        
        Args:
            request: Django request object
            username: User's username
            password: User's password
        
        Returns:
            User object if authenticated, None otherwise
        """
        if not username or not password:
            return None
        
        try:
            import ldap
            from django_auth_ldap.backend import LDAPBackend
            
            # Use django-auth-ldap's built-in backend
            ldap_backend = LDAPBackend()
            user = ldap_backend.authenticate(request, username=username, password=password)
            
            if user:
                logger.info(f'LDAP authentication successful for user: {username}')
                return user
            
            return None
            
        except ImportError:
            logger.warning('LDAP support not available (python-ldap not installed)')
            return None
        except Exception as e:
            logger.error(f'LDAP authentication error: {e}')
            return None
    
    def get_user(self, user_id):
        """Get user by ID."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
