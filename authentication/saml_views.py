"""SAML authentication views."""
from django.conf import settings
from django.contrib.auth import login, logout
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
import logging

logger = logging.getLogger(__name__)

# Check if SAML is enabled
SAML_ENABLED = getattr(settings, 'SAML_ENABLED', False)

if SAML_ENABLED:
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        from onelogin.saml2.utils import OneLogin_Saml2_Utils
    except ImportError:
        logger.warning('python3-saml not installed, SAML SSO will not be available')
        SAML_ENABLED = False


def prepare_saml_request(request):
    """Prepare SAML request object."""
    if not SAML_ENABLED:
        return None
    
    return {
        'https': 'on' if request.is_secure() else 'off',
        'http_host': request.META['HTTP_HOST'],
        'script_name': request.META['PATH_INFO'],
        'server_port': request.META['SERVER_PORT'],
        'get_data': request.GET.copy(),
        'post_data': request.POST.copy(),
    }


def saml_login(request):
    """Initiate SAML SSO login."""
    if not SAML_ENABLED:
        return render(request, 'authentication/saml_disabled.html', {
            'message': 'SAML SSO is not enabled on this server.'
        })
    
    try:
        req = prepare_saml_request(request)
        auth = OneLogin_Saml2_Auth(req, custom_base_path=settings.SAML_FOLDER)
        
        # Redirect to SAML IdP for authentication
        return HttpResponseRedirect(auth.login())
        
    except Exception as e:
        logger.error(f'SAML login error: {e}')
        return render(request, 'authentication/saml_error.html', {
            'error': str(e)
        })


@csrf_exempt
def saml_acs(request):
    """SAML Assertion Consumer Service - handles IdP response."""
    if not SAML_ENABLED:
        return HttpResponse('SAML SSO is not enabled', status=400)
    
    try:
        req = prepare_saml_request(request)
        auth = OneLogin_Saml2_Auth(req, custom_base_path=settings.SAML_FOLDER)
        
        # Process SAML response
        auth.process_response()
        errors = auth.get_errors()
        
        if errors:
            logger.error(f'SAML ACS errors: {errors}')
            return render(request, 'authentication/saml_error.html', {
                'error': ', '.join(errors)
            })
        
        # Check if user is authenticated
        if not auth.is_authenticated():
            return render(request, 'authentication/saml_error.html', {
                'error': 'SAML authentication failed'
            })
        
        # Get SAML attributes
        attributes = auth.get_attributes()
        
        # Authenticate user via SAML backend
        from authentication.saml_backend import SAMLAuthenticationBackend
        backend = SAMLAuthenticationBackend()
        user = backend.authenticate(request, saml_attributes=attributes)
        
        if user:
            # Log user in
            login(request, user, backend='authentication.saml_backend.SAMLAuthenticationBackend')
            
            # Redirect to intended URL or dashboard
            relay_state = request.POST.get('RelayState', '/')
            if relay_state and OneLogin_Saml2_Utils.get_self_url(req) != relay_state:
                return HttpResponseRedirect(relay_state)
            return HttpResponseRedirect(reverse('dashboard:dashboard'))
        
        return render(request, 'authentication/saml_error.html', {
            'error': 'Failed to create or retrieve user account'
        })
        
    except Exception as e:
        logger.error(f'SAML ACS error: {e}')
        return render(request, 'authentication/saml_error.html', {
            'error': str(e)
        })


def saml_metadata(request):
    """Return SAML service provider metadata."""
    if not SAML_ENABLED:
        return HttpResponse('SAML SSO is not enabled', status=400)
    
    try:
        req = prepare_saml_request(request)
        auth = OneLogin_Saml2_Auth(req, custom_base_path=settings.SAML_FOLDER)
        
        settings_data = auth.get_settings()
        metadata = settings_data.get_sp_metadata()
        errors = settings_data.validate_metadata(metadata)
        
        if errors:
            logger.error(f'SAML metadata errors: {errors}')
            return HttpResponse('Invalid metadata', status=500)
        
        return HttpResponse(content=metadata, content_type='text/xml')
        
    except Exception as e:
        logger.error(f'SAML metadata error: {e}')
        return HttpResponse(f'Error generating metadata: {e}', status=500)


def saml_logout(request):
    """Initiate SAML logout."""
    if not SAML_ENABLED:
        logout(request)
        return HttpResponseRedirect(reverse('authentication:login'))
    
    try:
        req = prepare_saml_request(request)
        auth = OneLogin_Saml2_Auth(req, custom_base_path=settings.SAML_FOLDER)
        
        # Logout from Django
        logout(request)
        
        # Redirect to SAML IdP for logout
        return HttpResponseRedirect(auth.logout())
        
    except Exception as e:
        logger.error(f'SAML logout error: {e}')
        logout(request)
        return HttpResponseRedirect(reverse('authentication:login'))
