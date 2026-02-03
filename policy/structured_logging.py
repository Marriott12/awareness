"""
Structured JSON logging for log aggregation integration.

Provides JSON-formatted logging suitable for ELK, Splunk, CloudWatch, etc.
"""
import logging
import json
import traceback
from datetime import datetime
from typing import Any, Dict, Optional
from django.conf import settings


class JSONFormatter(logging.Formatter):
    """
    Format log records as JSON for structured logging.
    
    Output format compatible with ELK, Splunk, CloudWatch, and other log aggregators.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: Python logging record
            
        Returns:
            JSON string with structured log data
        """
        log_data = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'process': record.process,
            'thread': record.thread,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields from record
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'ip_address'):
            log_data['ip_address'] = record.ip_address
        if hasattr(record, 'event_type'):
            log_data['event_type'] = record.event_type
        if hasattr(record, 'policy'):
            log_data['policy'] = record.policy
        if hasattr(record, 'severity'):
            log_data['severity'] = record.severity
        
        # Add environment info
        log_data['environment'] = getattr(settings, 'ENVIRONMENT', 'production')
        log_data['service'] = 'awareness-portal'
        
        return json.dumps(log_data, default=str)


class StructuredLogger:
    """
    Wrapper for Python logger with structured logging support.
    
    Usage:
        logger = StructuredLogger(__name__)
        logger.info('User logged in', user_id=123, ip_address='192.168.1.1')
    """
    
    def __init__(self, name: str):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name (usually __name__)
        """
        self.logger = logging.getLogger(name)
    
    def _log(self, level: int, message: str, **kwargs):
        """
        Log message with extra structured fields.
        
        Args:
            level: Logging level (logging.INFO, logging.ERROR, etc.)
            message: Log message
            **kwargs: Additional structured fields
        """
        extra = {k: v for k, v in kwargs.items() if k not in ['exc_info']}
        self.logger.log(
            level,
            message,
            extra=extra,
            exc_info=kwargs.get('exc_info')
        )
    
    def debug(self, message: str, **kwargs):
        """Log debug message with structured fields."""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message with structured fields."""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with structured fields."""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message with structured fields."""
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message with structured fields."""
        self._log(logging.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, **kwargs):
        """Log exception with structured fields and traceback."""
        kwargs['exc_info'] = True
        self._log(logging.ERROR, message, **kwargs)


# Pre-configured loggers for common use cases
def get_security_logger() -> StructuredLogger:
    """Get logger for security events."""
    return StructuredLogger('security')


def get_compliance_logger() -> StructuredLogger:
    """Get logger for compliance events."""
    return StructuredLogger('compliance')


def get_audit_logger() -> StructuredLogger:
    """Get logger for audit trail."""
    return StructuredLogger('audit')


# Middleware to add request context to logs
class LoggingMiddleware:
    """
    Django middleware to add request context to all logs.
    
    Adds request_id, user_id, and ip_address to log context.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Generate request ID if not present
        if not hasattr(request, 'request_id'):
            import uuid
            request.request_id = str(uuid.uuid4())
        
        # Add to logging context
        import logging
        old_factory = logging.getLogRecordFactory()
        
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.request_id = request.request_id
            if hasattr(request, 'user') and request.user.is_authenticated:
                record.user_id = request.user.id
            record.ip_address = self._get_client_ip(request)
            return record
        
        logging.setLogRecordFactory(record_factory)
        
        response = self.get_response(request)
        
        # Restore old factory
        logging.setLogRecordFactory(old_factory)
        
        return response
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# Example logging configuration for settings.py
STRUCTURED_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'policy.structured_logging.JSONFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/awareness/app.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'formatter': 'json',
        },
    },
    'loggers': {
        'security': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'compliance': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'audit': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
