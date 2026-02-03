"""
Two-Factor Authentication (2FA) integration for Django admin.

Provides TOTP-based 2FA using django-otp for enhanced security.

Installation:
    pip install django-otp qrcode

Configuration (add to settings.py):
    INSTALLED_APPS = [
        ...
        'django_otp',
        'django_otp.plugins.otp_totp',
        'policy.two_factor',
    ]
    
    MIDDLEWARE = [
        ...
        'django_otp.middleware.OTPMiddleware',
        'policy.two_factor.TwoFactorMiddleware',
    ]

Usage:
    # Enforce 2FA for all admin accounts
    python manage.py enable_2fa --all-admins
    
    # Enable for specific user
    python manage.py enable_2fa --username=admin
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponseForbidden
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TwoFactorMiddleware:
    """
    Middleware to enforce 2FA for admin users.
    
    Redirects to 2FA setup page if admin user doesn't have 2FA enabled.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.enforce_for_staff = getattr(
            settings,
            'TWO_FACTOR_ENFORCE_STAFF',
            True
        )
    
    def __call__(self, request):
        # Check if accessing admin panel
        if request.path.startswith('/admin/') and request.user.is_authenticated:
            # Require 2FA for staff users
            if self.enforce_for_staff and request.user.is_staff:
                if not self._user_has_2fa(request.user):
                    # Exclude 2FA setup URLs
                    if not request.path.startswith('/admin/two-factor/'):
                        messages.warning(
                            request,
                            'Two-factor authentication is required for admin access. '
                            'Please set up 2FA.'
                        )
                        return redirect('two_factor_setup')
        
        response = self.get_response(request)
        return response
    
    def _user_has_2fa(self, user) -> bool:
        """Check if user has 2FA device configured."""
        try:
            from django_otp import user_has_device
            return user_has_device(user)
        except ImportError:
            logger.warning('django-otp not installed, 2FA check skipped')
            return True  # Don't block if package not installed


@login_required
def two_factor_setup(request):
    """
    View for setting up TOTP 2FA device.
    
    Displays QR code for scanning with authenticator app.
    """
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.util import random_hex
        import qrcode
        import qrcode.image.svg
        from io import BytesIO
        import base64
    except ImportError:
        return HttpResponseForbidden(
            'Two-factor authentication requires django-otp package. '
            'Install with: pip install django-otp qrcode'
        )
    
    user = request.user
    
    # Check if user already has device
    existing_device = TOTPDevice.objects.filter(
        user=user,
        confirmed=True
    ).first()
    
    if request.method == 'POST':
        # Verify token
        token = request.POST.get('token')
        device_key = request.POST.get('device_key')
        
        if not token or not device_key:
            messages.error(request, 'Please enter the verification code.')
        else:
            # Get unconfirmed device
            device = TOTPDevice.objects.filter(
                user=user,
                key=device_key,
                confirmed=False
            ).first()
            
            if device and device.verify_token(token):
                device.confirmed = True
                device.save()
                
                messages.success(request, 'Two-factor authentication enabled successfully!')
                
                # Log security event
                from .structured_logging import get_security_logger
                sec_logger = get_security_logger()
                sec_logger.info(
                    '2FA enabled',
                    user_id=user.id,
                    event_type='2fa_enabled'
                )
                
                return redirect('admin:index')
            else:
                messages.error(request, 'Invalid verification code. Please try again.')
    
    # Generate new device if user doesn't have one
    if existing_device:
        device = existing_device
        qr_svg = None
    else:
        # Create unconfirmed device
        device, created = TOTPDevice.objects.get_or_create(
            user=user,
            name='default',
            defaults={'confirmed': False}
        )
        
        if created:
            device.key = random_hex(20)
            device.save()
        
        # Generate QR code
        provisioning_uri = device.config_url
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 for embedding in HTML
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        qr_image = base64.b64encode(buffer.getvalue()).decode()
        qr_svg = f'data:image/png;base64,{qr_image}'
    
    context = {
        'device': device,
        'qr_code': qr_svg,
        'secret_key': device.key if not existing_device else None,
        'has_2fa': existing_device is not None,
    }
    
    return render(request, 'two_factor/setup.html', context)


@login_required
def two_factor_disable(request):
    """
    View for disabling 2FA.
    
    Requires password confirmation for security.
    """
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django.contrib.auth import authenticate
    except ImportError:
        return HttpResponseForbidden('Two-factor authentication not available.')
    
    user = request.user
    
    if request.method == 'POST':
        password = request.POST.get('password')
        
        # Verify password
        auth_user = authenticate(
            username=user.username,
            password=password
        )
        
        if auth_user:
            # Delete all devices
            deleted_count = TOTPDevice.objects.filter(user=user).delete()[0]
            
            messages.success(
                request,
                f'Two-factor authentication disabled. {deleted_count} device(s) removed.'
            )
            
            # Log security event
            from .structured_logging import get_security_logger
            sec_logger = get_security_logger()
            sec_logger.warning(
                '2FA disabled',
                user_id=user.id,
                event_type='2fa_disabled'
            )
            
            return redirect('admin:index')
        else:
            messages.error(request, 'Incorrect password. Cannot disable 2FA.')
    
    return render(request, 'two_factor/disable.html')


# Management command helpers
def enable_2fa_for_user(user, force: bool = False) -> bool:
    """
    Enable 2FA requirement for a user.
    
    Args:
        user: User object
        force: Force enable even if user already has device
        
    Returns:
        True if 2FA was enabled, False otherwise
    """
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.util import random_hex
    except ImportError:
        logger.error('django-otp not installed')
        return False
    
    # Check if user already has device
    if not force and TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        logger.info(f'User {user.username} already has 2FA enabled')
        return False
    
    # Create device
    device, created = TOTPDevice.objects.get_or_create(
        user=user,
        name='default',
        defaults={
            'confirmed': False,
            'key': random_hex(20)
        }
    )
    
    if created:
        logger.info(f'2FA device created for user {user.username}')
        return True
    else:
        logger.info(f'2FA device already exists for user {user.username}')
        return False


def is_2fa_enabled(user) -> bool:
    """Check if user has 2FA enabled."""
    try:
        from django_otp import user_has_device
        return user_has_device(user)
    except ImportError:
        return False


# Settings to add to settings.py
TWO_FACTOR_SETTINGS = {
    # Enforce 2FA for all staff users
    'TWO_FACTOR_ENFORCE_STAFF': True,
    
    # Enforce 2FA for superusers
    'TWO_FACTOR_ENFORCE_SUPERUSER': True,
    
    # Allow users to disable 2FA (set to False for maximum security)
    'TWO_FACTOR_ALLOW_DISABLE': False,
    
    # Token validity period in seconds (30 seconds is standard)
    'TWO_FACTOR_TOKEN_VALIDITY': 30,
    
    # Number of backup tokens to generate
    'TWO_FACTOR_BACKUP_TOKENS': 10,
}
