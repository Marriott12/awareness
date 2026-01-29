from django.views.decorators.http import require_GET

# ...existing code...

import logging

@require_GET
def session_test(request):
    # Set a value in the session and return it
    logger = logging.getLogger(__name__)
    if 'test_counter' in request.session:
        request.session['test_counter'] += 1
    else:
        request.session['test_counter'] = 1
    # Force session save for debugging
    request.session.modified = True
    request.session.save()
    logger.debug(f"Session key: {request.session.session_key}, test_counter: {request.session['test_counter']}, session_data: {dict(request.session.items())}")
    return JsonResponse({
        'session_key': request.session.session_key,
        'test_counter': request.session['test_counter'],
        'session_data': dict(request.session.items()),
        'cookies': dict(request.COOKIES),
    })
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.contrib.sessions.models import Session

@csrf_exempt
def debug_auth_status(request):
    """Return session, cookie, and user status for debugging login issues."""
    info = {
        'method': request.method,
        'cookies': dict(request.COOKIES),
        'session_key': request.session.session_key,
        'session_data': dict(request.session.items()),
        'user_authenticated': request.user.is_authenticated,
        'user_username': getattr(request.user, 'username', None),
        'user_is_active': getattr(request.user, 'is_active', None),
        'user_is_staff': getattr(request.user, 'is_staff', None),
        'user_is_superuser': getattr(request.user, 'is_superuser', None),
    }
    # Try authenticating with admin credentials if provided
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        info['auth_attempt'] = bool(user)
        if user:
            info['auth_user_is_active'] = user.is_active
            info['auth_user_is_staff'] = user.is_staff
            info['auth_user_is_superuser'] = user.is_superuser
    return JsonResponse(info)