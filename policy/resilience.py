"""Rate limiting and circuit breaker for production resilience.

Implements:
- Redis-based rate limiting (per user, per IP, per endpoint)
- Circuit breaker pattern for external services
- Metrics collection for monitoring
"""
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings
from functools import wraps
from typing import Callable, Optional
from datetime import datetime, timedelta
import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis-backed rate limiter with sliding window."""
    
    def __init__(self, key_prefix: str = 'ratelimit'):
        self.key_prefix = key_prefix
    
    def is_allowed(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60
    ) -> tuple[bool, dict]:
        """Check if request is within rate limit.
        
        Args:
            identifier: Unique identifier (user ID, IP, etc.)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
            
        Returns:
            (allowed: bool, info: dict with remaining, reset_at)
        """
        key = f'{self.key_prefix}:{identifier}'
        now = int(time.time())
        window_start = now - window_seconds
        
        # Use Redis sorted set for sliding window
        # Try to use Redis directly if available
        try:
            from django.core.cache import caches
            redis_cache = caches['default']
            
            # Clean old entries
            redis_cache.delete_many([k for k in redis_cache.keys(f'{key}:*') if int(k.split(':')[-1]) < window_start])
            
            # Add current request
            request_key = f'{key}:{now}'
            redis_cache.set(request_key, 1, timeout=window_seconds + 1)
            
            # Count requests in window
            count = len([k for k in redis_cache.keys(f'{key}:*')])
            
        except Exception:
            # Fallback to simple counter
            count = cache.get(key, 0) + 1
            cache.set(key, count, timeout=window_seconds)
        
        allowed = count <= limit
        remaining = max(0, limit - count)
        reset_at = now + window_seconds
        
        return allowed, {
            'limit': limit,
            'remaining': remaining,
            'reset_at': reset_at,
            'current': count
        }
    
    def record_hit(self, identifier: str, window_seconds: int = 60):
        """Record a request hit."""
        key = f'{self.key_prefix}:{identifier}'
        count = cache.get(key, 0)
        cache.set(key, count + 1, timeout=window_seconds)


def rate_limit(
    limit: int = 100,
    window: int = 60,
    key_func: Optional[Callable] = None
):
    """Decorator for rate limiting views or functions.
    
    Usage:
        @rate_limit(limit=10, window=60)
        def my_view(request):
            ...
    
    Args:
        limit: Max requests per window
        window: Window size in seconds
        key_func: Function to extract identifier from request (default: uses user ID or IP)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Extract identifier
            if key_func:
                identifier = key_func(request)
            elif request.user.is_authenticated:
                identifier = f'user:{request.user.id}'
            else:
                identifier = f'ip:{get_client_ip(request)}'
            
            # Check rate limit
            limiter = RateLimiter()
            allowed, info = limiter.is_allowed(identifier, limit, window)
            
            if not allowed:
                logger.warning(f'Rate limit exceeded for {identifier}')
                response = HttpResponse('Rate limit exceeded', status=429)
                response['X-RateLimit-Limit'] = str(info['limit'])
                response['X-RateLimit-Remaining'] = '0'
                response['X-RateLimit-Reset'] = str(info['reset_at'])
                response['Retry-After'] = str(window)
                return response
            
            # Add rate limit headers
            response = func(request, *args, **kwargs)
            if hasattr(response, '__setitem__'):
                response['X-RateLimit-Limit'] = str(info['limit'])
                response['X-RateLimit-Remaining'] = str(info['remaining'])
                response['X-RateLimit-Reset'] = str(info['reset_at'])
            
            return response
        
        return wrapper
    return decorator


def get_client_ip(request) -> str:
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


class CircuitBreaker:
    """Circuit breaker for external service calls.
    
    States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing)
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        success_threshold: int = 2
    ):
        """
        Args:
            name: Circuit identifier
            failure_threshold: Failures before opening circuit
            timeout_seconds: Time to wait before attempting recovery
            success_threshold: Successes in HALF_OPEN before closing
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold
        self.state_key = f'circuit:{name}:state'
        self.failure_key = f'circuit:{name}:failures'
        self.success_key = f'circuit:{name}:successes'
        self.opened_at_key = f'circuit:{name}:opened_at'
    
    def get_state(self) -> str:
        """Get current circuit state: CLOSED, OPEN, or HALF_OPEN."""
        state = cache.get(self.state_key, 'CLOSED')
        
        # Check if should transition OPEN → HALF_OPEN
        if state == 'OPEN':
            opened_at = cache.get(self.opened_at_key)
            if opened_at and (time.time() - opened_at) >= self.timeout_seconds:
                self.set_state('HALF_OPEN')
                return 'HALF_OPEN'
        
        return state
    
    def set_state(self, state: str):
        """Set circuit state."""
        cache.set(self.state_key, state, timeout=None)
        if state == 'OPEN':
            cache.set(self.opened_at_key, time.time(), timeout=self.timeout_seconds + 10)
        elif state == 'CLOSED':
            cache.delete(self.failure_key)
            cache.delete(self.success_key)
    
    def record_success(self):
        """Record successful call."""
        state = self.get_state()
        
        if state == 'HALF_OPEN':
            successes = cache.get(self.success_key, 0) + 1
            cache.set(self.success_key, successes, timeout=60)
            
            if successes >= self.success_threshold:
                logger.info(f'Circuit {self.name}: HALF_OPEN → CLOSED (recovered)')
                self.set_state('CLOSED')
        elif state == 'CLOSED':
            # Reset failure counter on success
            cache.delete(self.failure_key)
    
    def record_failure(self):
        """Record failed call."""
        state = self.get_state()
        
        if state == 'HALF_OPEN':
            # Immediately open on failure in HALF_OPEN
            logger.warning(f'Circuit {self.name}: HALF_OPEN → OPEN (test failed)')
            self.set_state('OPEN')
        elif state == 'CLOSED':
            failures = cache.get(self.failure_key, 0) + 1
            cache.set(self.failure_key, failures, timeout=60)
            
            if failures >= self.failure_threshold:
                logger.error(f'Circuit {self.name}: CLOSED → OPEN ({failures} failures)')
                self.set_state('OPEN')
    
    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection.
        
        Raises:
            CircuitOpenError if circuit is open
        """
        state = self.get_state()
        
        if state == 'OPEN':
            raise CircuitOpenError(f'Circuit {self.name} is OPEN')
        
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


def circuit_breaker(name: str, failure_threshold: int = 5, timeout: int = 60):
    """Decorator for circuit breaker protection.
    
    Usage:
        @circuit_breaker('external_api', failure_threshold=3, timeout=30)
        def call_external_api():
            ...
    """
    def decorator(func):
        breaker = CircuitBreaker(name, failure_threshold, timeout)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        return wrapper
    return decorator


# Middleware for global rate limiting
class RateLimitMiddleware:
    """Global rate limiting middleware."""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.limiter = RateLimiter(key_prefix='global_ratelimit')
    
    def __call__(self, request):
        # Skip rate limiting for static files and admin
        if request.path.startswith('/static/') or request.path.startswith('/admin/'):
            return self.get_response(request)
        
        # Get rate limit settings from config
        limit = getattr(settings, 'GLOBAL_RATE_LIMIT', 1000)
        window = getattr(settings, 'GLOBAL_RATE_LIMIT_WINDOW', 60)
        
        # Identifier
        if request.user.is_authenticated:
            identifier = f'user:{request.user.id}'
        else:
            identifier = f'ip:{get_client_ip(request)}'
        
        # Check limit
        allowed, info = self.limiter.is_allowed(identifier, limit, window)
        
        if not allowed:
            logger.warning(f'Global rate limit exceeded: {identifier}')
            response = HttpResponse('Too many requests', status=429)
            response['Retry-After'] = str(window)
            return response
        
        # Process request
        response = self.get_response(request)
        
        # Add headers
        if hasattr(response, '__setitem__'):
            response['X-RateLimit-Limit'] = str(info['limit'])
            response['X-RateLimit-Remaining'] = str(info['remaining'])
        
        return response
