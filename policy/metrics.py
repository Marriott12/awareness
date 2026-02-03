"""
Prometheus metrics for production monitoring.

Metrics:
- Event ingestion rate
- Compliance evaluation latency
- Violation counts by severity
- ML model prediction latency
- Rate limiter hits
- Circuit breaker state changes
"""
from prometheus_client import Counter, Histogram, Gauge, Summary, Enum
import time
import functools

# Event metrics
events_ingested_total = Counter(
    'awareness_events_ingested_total',
    'Total number of events ingested',
    ['source', 'event_type']
)

event_ingestion_duration = Histogram(
    'awareness_event_ingestion_duration_seconds',
    'Time to ingest and store an event',
    ['source'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)

# Compliance metrics
compliance_evaluations_total = Counter(
    'awareness_compliance_evaluations_total',
    'Total number of compliance evaluations',
    ['result']  # 'pass', 'violation', 'error'
)

compliance_violations_total = Counter(
    'awareness_compliance_violations_total',
    'Total number of compliance violations detected',
    ['severity', 'policy']
)

compliance_evaluation_duration = Histogram(
    'awareness_compliance_evaluation_duration_seconds',
    'Time to evaluate compliance for an event',
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0)
)

# ML metrics
ml_predictions_total = Counter(
    'awareness_ml_predictions_total',
    'Total number of ML model predictions',
    ['model_version']
)

ml_prediction_duration = Histogram(
    'awareness_ml_prediction_duration_seconds',
    'Time to generate ML prediction',
    ['model_version'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
)

ml_risk_score = Summary(
    'awareness_ml_risk_score',
    'Distribution of ML risk scores (0-100)',
)

ml_model_accuracy = Gauge(
    'awareness_ml_model_accuracy',
    'Current ML model accuracy (F1 score)',
    ['model_version']
)

ml_training_duration = Histogram(
    'awareness_ml_training_duration_seconds',
    'Time to train ML model',
    ['algorithm'],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0)
)

# Rate limiting metrics
rate_limit_hits_total = Counter(
    'awareness_rate_limit_hits_total',
    'Total number of rate limit hits (429 responses)',
    ['limit_type']  # 'user', 'ip', 'global'
)

rate_limit_allowed_total = Counter(
    'awareness_rate_limit_allowed_total',
    'Total number of allowed requests after rate limit check',
    ['limit_type']
)

# Circuit breaker metrics
circuit_breaker_state = Enum(
    'awareness_circuit_breaker_state',
    'Current state of circuit breaker',
    ['service'],
    states=['closed', 'open', 'half_open']
)

circuit_breaker_failures_total = Counter(
    'awareness_circuit_breaker_failures_total',
    'Total number of circuit breaker failures',
    ['service']
)

circuit_breaker_successes_total = Counter(
    'awareness_circuit_breaker_successes_total',
    'Total number of circuit breaker successes',
    ['service']
)

# Policy metrics
active_policies_count = Gauge(
    'awareness_active_policies_count',
    'Number of active policies',
)

policy_state_transitions_total = Counter(
    'awareness_policy_state_transitions_total',
    'Total policy state transitions',
    ['from_state', 'to_state', 'transition']
)

# Database metrics
database_query_duration = Histogram(
    'awareness_database_query_duration_seconds',
    'Time to execute database queries',
    ['operation'],  # 'select', 'insert', 'update'
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
)

# Signature verification metrics
signature_verifications_total = Counter(
    'awareness_signature_verifications_total',
    'Total signature verifications',
    ['result']  # 'valid', 'invalid', 'error'
)

signature_verification_duration = Histogram(
    'awareness_signature_verification_duration_seconds',
    'Time to verify cryptographic signature',
    ['signature_type'],  # 'rsa', 'ed25519'
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
)

# TSA metrics
tsa_requests_total = Counter(
    'awareness_tsa_requests_total',
    'Total timestamp authority requests',
    ['result']  # 'success', 'failure', 'timeout'
)

tsa_request_duration = Histogram(
    'awareness_tsa_request_duration_seconds',
    'Time to get TSA timestamp',
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

# Celery task metrics
celery_task_duration = Histogram(
    'awareness_celery_task_duration_seconds',
    'Time to execute Celery task',
    ['task_name', 'status'],  # status: 'success', 'failure', 'retry'
    buckets=(0.1, 1.0, 5.0, 10.0, 60.0, 300.0, 600.0)
)

celery_tasks_total = Counter(
    'awareness_celery_tasks_total',
    'Total Celery tasks executed',
    ['task_name', 'status']
)


# Decorator for timing metrics
def time_metric(metric_histogram, labels=None):
    """
    Decorator to automatically time function execution and record to histogram.
    
    Args:
        metric_histogram: Prometheus Histogram metric
        labels: Dict of label values (optional)
    
    Usage:
        @time_metric(ml_prediction_duration, labels={'model_version': 'v1'})
        def predict(event):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                if labels:
                    metric_histogram.labels(**labels).observe(duration)
                else:
                    metric_histogram.observe(duration)
        return wrapper
    return decorator


# Helper functions for common metric patterns
def record_event_ingestion(source, event_type, duration):
    """Record successful event ingestion."""
    events_ingested_total.labels(source=source, event_type=event_type).inc()
    event_ingestion_duration.labels(source=source).observe(duration)


def record_compliance_violation(severity, policy_name):
    """Record a compliance violation."""
    compliance_violations_total.labels(severity=severity, policy=policy_name).inc()


def record_ml_prediction(model_version, risk_score, duration):
    """Record ML prediction metrics."""
    ml_predictions_total.labels(model_version=model_version).inc()
    ml_prediction_duration.labels(model_version=model_version).observe(duration)
    ml_risk_score.observe(risk_score)


def record_rate_limit_hit(limit_type):
    """Record rate limit enforcement."""
    rate_limit_hits_total.labels(limit_type=limit_type).inc()


def update_circuit_breaker_state(service, state):
    """Update circuit breaker state gauge."""
    circuit_breaker_state.labels(service=service).state(state)


def record_policy_transition(from_state, to_state, transition):
    """Record policy state transition."""
    policy_state_transitions_total.labels(
        from_state=from_state,
        to_state=to_state,
        transition=transition
    ).inc()


def record_signature_verification(signature_type, result, duration):
    """Record signature verification metrics."""
    signature_verifications_total.labels(result=result).inc()
    signature_verification_duration.labels(signature_type=signature_type).observe(duration)


def record_tsa_request(result, duration):
    """Record TSA request metrics."""
    tsa_requests_total.labels(result=result).inc()
    tsa_request_duration.observe(duration)


# Context managers for timing
class TimedOperation:
    """
    Context manager for timing operations with automatic metric recording.
    
    Usage:
        with TimedOperation(database_query_duration, labels={'operation': 'insert'}):
            # database operation
            ...
    """
    def __init__(self, metric_histogram, labels=None):
        self.metric = metric_histogram
        self.labels = labels or {}
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if self.labels:
            self.metric.labels(**self.labels).observe(duration)
        else:
            self.metric.observe(duration)
        return False  # Don't suppress exceptions


# Export metrics endpoint helper
def get_metrics_view():
    """
    Returns a Django view function for Prometheus metrics endpoint.
    
    Usage in urls.py:
        from policy.metrics import get_metrics_view
        urlpatterns = [
            path('metrics/', get_metrics_view()),
        ]
    """
    from prometheus_client import generate_latest
    from django.http import HttpResponse
    
    def metrics(request):
        """Prometheus metrics endpoint."""
        metrics_output = generate_latest()
        return HttpResponse(
            metrics_output,
            content_type='text/plain; version=0.0.4; charset=utf-8'
        )
    
    return metrics
