"""
Health check endpoints for production monitoring.

Provides:
- Liveness probe (is app running?)
- Readiness probe (is app ready to serve traffic?)
- Dependency status (database, cache, Celery, TSA)
"""
import time
import logging
from django.http import JsonResponse
from django.conf import settings
from django.db import connection
from django.core.cache import cache
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def liveness(request):
    """
    Liveness probe - basic "is the app alive?" check.
    
    Returns 200 if Django process is running.
    Should be used for Kubernetes liveness probe.
    
    Usage:
        GET /health/live
    """
    return JsonResponse({
        'status': 'alive',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    })


def readiness(request):
    """
    Readiness probe - comprehensive "ready to serve?" check.
    
    Checks:
    - Database connectivity
    - Cache connectivity
    - Critical tables exist
    - ML model loaded (if enabled)
    
    Returns:
    - 200: All checks passed, ready for traffic
    - 503: One or more checks failed, not ready
    
    Usage:
        GET /health/ready
    """
    checks = {}
    overall_status = 'ready'
    status_code = 200
    
    # 1. Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks['database'] = {'status': 'ok', 'latency_ms': None}
    except Exception as e:
        checks['database'] = {'status': 'error', 'message': str(e)}
        overall_status = 'not_ready'
        status_code = 503
    
    # 2. Cache check (Redis)
    try:
        cache_key = 'health_check_test'
        test_value = f'test_{time.time()}'
        cache.set(cache_key, test_value, timeout=10)
        retrieved = cache.get(cache_key)
        
        if retrieved == test_value:
            checks['cache'] = {'status': 'ok'}
        else:
            checks['cache'] = {'status': 'error', 'message': 'Value mismatch'}
            overall_status = 'not_ready'
            status_code = 503
    except Exception as e:
        checks['cache'] = {'status': 'error', 'message': str(e)}
        overall_status = 'not_ready'
        status_code = 503
    
    # 3. Critical tables check
    try:
        from policy.models import Policy, Control
        policy_count = Policy.objects.count()
        control_count = Control.objects.count()
        
        checks['tables'] = {
            'status': 'ok',
            'policies': policy_count,
            'controls': control_count,
        }
    except Exception as e:
        checks['tables'] = {'status': 'error', 'message': str(e)}
        overall_status = 'not_ready'
        status_code = 503
    
    # 4. ML model check (if enabled)
    if getattr(settings, 'ML_ENABLED', False):
        try:
            from policy.ml_scorer import get_ml_scorer
            scorer = get_ml_scorer()
            
            if scorer.model is not None:
                checks['ml_model'] = {'status': 'ok', 'version': scorer.version}
            else:
                checks['ml_model'] = {'status': 'warning', 'message': 'No model loaded'}
        except Exception as e:
            checks['ml_model'] = {'status': 'error', 'message': str(e)}
            # ML failure is not critical for basic operation
            # overall_status remains 'ready'
    
    return JsonResponse({
        'status': overall_status,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'checks': checks,
    }, status=status_code)


def dependencies(request):
    """
    Dependency status check - detailed status of all external dependencies.
    
    Checks:
    - Database (latency)
    - Cache/Redis (latency)
    - Celery workers (active)
    - TSA service (if configured)
    - ML model (loaded, version, age)
    
    Returns:
    - 200: All dependencies operational
    - 207: Partial degradation
    - 503: Critical dependencies down
    
    Usage:
        GET /health/dependencies
    """
    deps = {}
    degraded_count = 0
    critical_down = False
    
    # 1. Database detailed check
    try:
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency_ms = (time.time() - start) * 1000
        
        deps['database'] = {
            'status': 'operational',
            'latency_ms': round(latency_ms, 2),
            'vendor': connection.vendor,
        }
    except Exception as e:
        deps['database'] = {
            'status': 'down',
            'error': str(e),
        }
        critical_down = True
    
    # 2. Cache/Redis detailed check
    try:
        start = time.time()
        cache_key = f'health_dep_test_{time.time()}'
        cache.set(cache_key, 'test', timeout=5)
        cache.get(cache_key)
        latency_ms = (time.time() - start) * 1000
        
        # Get Redis info if available
        cache_backend = cache._cache
        redis_info = {}
        if hasattr(cache_backend, 'info'):
            info = cache_backend.info()
            redis_info = {
                'version': info.get('redis_version'),
                'used_memory_mb': round(info.get('used_memory', 0) / 1024 / 1024, 2),
                'connected_clients': info.get('connected_clients'),
            }
        
        deps['cache'] = {
            'status': 'operational',
            'latency_ms': round(latency_ms, 2),
            'backend': settings.CACHES['default']['BACKEND'],
            **redis_info
        }
    except Exception as e:
        deps['cache'] = {
            'status': 'down',
            'error': str(e),
        }
        critical_down = True
    
    # 3. Celery workers check
    try:
        from awareness.celery import app
        
        # Inspect active workers
        inspect = app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers:
            worker_names = list(active_workers.keys())
            total_tasks = sum(len(tasks) for tasks in active_workers.values())
            
            deps['celery'] = {
                'status': 'operational',
                'workers': len(worker_names),
                'active_tasks': total_tasks,
                'worker_names': worker_names,
            }
        else:
            deps['celery'] = {
                'status': 'degraded',
                'message': 'No active workers',
            }
            degraded_count += 1
    except Exception as e:
        deps['celery'] = {
            'status': 'unknown',
            'error': str(e),
        }
        degraded_count += 1
    
    # 4. TSA service check (if configured)
    if hasattr(settings, 'TSA_URL') and settings.TSA_URL:
        try:
            import requests
            start = time.time()
            # Don't actually call TSA, just check if endpoint is reachable
            # In production, use a lightweight health endpoint
            response = requests.head(settings.TSA_URL, timeout=5)
            latency_ms = (time.time() - start) * 1000
            
            deps['tsa'] = {
                'status': 'operational' if response.status_code < 500 else 'degraded',
                'latency_ms': round(latency_ms, 2),
                'url': settings.TSA_URL,
            }
        except Exception as e:
            deps['tsa'] = {
                'status': 'down',
                'error': str(e),
            }
            degraded_count += 1
    
    # 5. ML model detailed check
    if getattr(settings, 'ML_ENABLED', False):
        try:
            from policy.ml_scorer import get_ml_scorer
            from policy.models import ScorerArtifact
            
            scorer = get_ml_scorer()
            
            if scorer.model:
                # Get model artifact info
                artifact = ScorerArtifact.objects.filter(
                    version=scorer.version
                ).first()
                
                model_age_days = None
                if artifact:
                    model_age_days = (datetime.now() - artifact.created_at.replace(tzinfo=None)).days
                
                deps['ml_model'] = {
                    'status': 'operational',
                    'version': scorer.version,
                    'algorithm': scorer.algorithm,
                    'age_days': model_age_days,
                    'cached': scorer._model_cache_key in cache,
                }
                
                # Warn if model is too old
                if model_age_days and model_age_days > 60:
                    deps['ml_model']['warning'] = f'Model is {model_age_days} days old'
            else:
                deps['ml_model'] = {
                    'status': 'not_loaded',
                    'message': 'No model loaded',
                }
                degraded_count += 1
        except Exception as e:
            deps['ml_model'] = {
                'status': 'error',
                'error': str(e),
            }
            degraded_count += 1
    
    # Determine overall status
    if critical_down:
        overall_status = 'critical'
        status_code = 503
    elif degraded_count > 0:
        overall_status = 'degraded'
        status_code = 207  # Multi-Status
    else:
        overall_status = 'operational'
        status_code = 200
    
    return JsonResponse({
        'status': overall_status,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'dependencies': deps,
        'summary': {
            'total': len(deps),
            'operational': sum(1 for d in deps.values() if d.get('status') == 'operational'),
            'degraded': sum(1 for d in deps.values() if d.get('status') in ['degraded', 'warning']),
            'down': sum(1 for d in deps.values() if d.get('status') == 'down'),
        }
    }, status=status_code)


def startup(request):
    """
    Startup probe - checks if app has completed initialization.
    
    Useful for slow-starting apps in Kubernetes.
    
    Usage:
        GET /health/startup
    """
    # For Django, if we're responding, we're started
    return JsonResponse({
        'status': 'started',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    })


# URLs configuration helper
def get_health_urls():
    """
    Returns URL patterns for health endpoints.
    
    Usage in urls.py:
        from policy.health import get_health_urls
        urlpatterns = [
            path('health/', include(get_health_urls())),
        ]
    """
    from django.urls import path
    
    return [
        path('live', liveness, name='health_live'),
        path('ready', readiness, name='health_ready'),
        path('startup', startup, name='health_startup'),
        path('dependencies', dependencies, name='health_dependencies'),
    ]
