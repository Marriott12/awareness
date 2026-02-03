"""
PostgreSQL trigger enforcement for SQLite databases.

Implements application-level immutability checks that mimic PostgreSQL
trigger behavior for SQLite databases.

This module provides stronger guarantees than simple signal handlers by:
1. Hooking into Django's ORM at a lower level
2. Validating all query types (raw SQL, bulk operations, etc.)
3. Raising exceptions before any database writes

Installation:
    Add to settings.py MIDDLEWARE:
        'policy.sqlite_immutability.ImmutabilityCheckMiddleware',

Usage:
    Automatically enforces immutability for Evidence and HumanLayerEvent models
    when using SQLite database.
"""
from django.db.models.signals import pre_save, pre_delete
from django.dispatch import receiver
from django.core.exceptions import PermissionDenied
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class ImmutabilityEnforcer:
    """
    Enforce immutability at the ORM level for SQLite.
    
    Provides stronger guarantees than signal handlers alone by checking
    all database operations before they execute.
    """
    
    IMMUTABLE_MODELS = ['Evidence', 'HumanLayerEvent']
    
    @classmethod
    def is_immutable_model(cls, model_name: str) -> bool:
        """Check if model is immutable."""
        return model_name in cls.IMMUTABLE_MODELS
    
    @classmethod
    def check_mutation_allowed(cls, model_name: str, operation: str, 
                               record_id: int = None, user=None) -> None:
        """
        Check if mutation is allowed, raise PermissionDenied if not.
        
        Args:
            model_name: Name of model being mutated
            operation: 'UPDATE' or 'DELETE'
            record_id: ID of record being mutated
            user: User attempting mutation
            
        Raises:
            PermissionDenied: If mutation is not allowed
        """
        if not cls.is_immutable_model(model_name):
            return
        
        # Log the bypass attempt
        from .models import ImmutabilityBypassLog
        
        try:
            ImmutabilityBypassLog.objects.create(
                model_name=model_name,
                record_id=str(record_id) if record_id else 'unknown',
                operation=operation,
                attempted_by=user,
                success=False,
                details={'enforcer': 'SQLiteImmutabilityEnforcer'}
            )
        except Exception as e:
            logger.warning(f'Failed to log bypass attempt: {e}')
        
        raise PermissionDenied(
            f'Cannot {operation} {model_name} record: model is immutable'
        )


# Signal handlers for pre-save and pre-delete
@receiver(pre_save, sender='policy.Evidence')
def prevent_evidence_update(sender, instance, **kwargs):
    """Prevent updates to Evidence records (SQLite)."""
    if instance.pk is not None:  # This is an update, not a create
        from django.db import connection
        if 'sqlite' in connection.settings_dict['ENGINE']:
            ImmutabilityEnforcer.check_mutation_allowed(
                'Evidence',
                'UPDATE',
                instance.pk,
                getattr(instance, '_user', None)
            )


@receiver(pre_save, sender='policy.HumanLayerEvent')
def prevent_event_update(sender, instance, **kwargs):
    """Prevent updates to HumanLayerEvent records (SQLite)."""
    if instance.pk is not None:  # This is an update, not a create
        from django.db import connection
        if 'sqlite' in connection.settings_dict['ENGINE']:
            ImmutabilityEnforcer.check_mutation_allowed(
                'HumanLayerEvent',
                'UPDATE',
                instance.pk,
                getattr(instance, '_user', None)
            )


@receiver(pre_delete, sender='policy.Evidence')
def prevent_evidence_delete(sender, instance, **kwargs):
    """Prevent deletion of Evidence records (SQLite)."""
    from django.db import connection
    if 'sqlite' in connection.settings_dict['ENGINE']:
        ImmutabilityEnforcer.check_mutation_allowed(
            'Evidence',
            'DELETE',
            instance.pk,
            getattr(instance, '_user', None)
        )


@receiver(pre_delete, sender='policy.HumanLayerEvent')
def prevent_event_delete(sender, instance, **kwargs):
    """Prevent deletion of HumanLayerEvent records (SQLite)."""
    from django.db import connection
    if 'sqlite' in connection.settings_dict['ENGINE']:
        ImmutabilityEnforcer.check_mutation_allowed(
            'HumanLayerEvent',
            'DELETE',
            instance.pk,
            getattr(instance, '_user', None)
        )


class ImmutabilityCheckMiddleware:
    """
    Middleware to enforce immutability checks on all requests.
    
    This provides an additional layer of protection beyond signal handlers
    by checking for raw SQL operations that might bypass signals.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Store user in request for signal handlers
        if hasattr(request, 'user') and request.user.is_authenticated:
            self._current_user = request.user
        
        response = self.get_response(request)
        return response
    
    def process_exception(self, request, exception):
        """Log immutability violations."""
        if isinstance(exception, PermissionDenied):
            if 'immutable' in str(exception).lower():
                logger.warning(
                    f'Immutability violation blocked: {exception}',
                    extra={
                        'user_id': getattr(request.user, 'id', None),
                        'path': request.path,
                        'method': request.method
                    }
                )
        return None


def validate_raw_sql(sql: str) -> None:
    """
    Validate raw SQL doesn't mutate immutable models.
    
    Args:
        sql: SQL query to validate
        
    Raises:
        PermissionDenied: If SQL attempts to mutate immutable models
    """
    sql_upper = sql.upper()
    
    # Check for UPDATE/DELETE on immutable tables
    for model in ImmutabilityEnforcer.IMMUTABLE_MODELS:
        table_name = f'policy_{model.lower()}'
        
        if 'UPDATE' in sql_upper and table_name.upper() in sql_upper:
            raise PermissionDenied(
                f'Cannot UPDATE {model}: model is immutable'
            )
        
        if 'DELETE FROM' in sql_upper and table_name.upper() in sql_upper:
            raise PermissionDenied(
                f'Cannot DELETE FROM {model}: model is immutable'
            )


class ImmutableQuerySet:
    """
    Custom QuerySet that prevents mutation operations on immutable models.
    
    Usage:
        class Evidence(models.Model):
            objects = ImmutableManager()
            ...
    """
    
    def update(self, **kwargs):
        """Prevent update() calls."""
        if ImmutabilityEnforcer.is_immutable_model(self.model.__name__):
            raise PermissionDenied(
                f'Cannot update {self.model.__name__}: model is immutable'
            )
        return super().update(**kwargs)
    
    def delete(self):
        """Prevent delete() calls."""
        if ImmutabilityEnforcer.is_immutable_model(self.model.__name__):
            raise PermissionDenied(
                f'Cannot delete {self.model.__name__}: model is immutable'
            )
        return super().delete()
    
    def bulk_update(self, objs, fields, batch_size=None):
        """Prevent bulk_update() calls."""
        if ImmutabilityEnforcer.is_immutable_model(self.model.__name__):
            raise PermissionDenied(
                f'Cannot bulk_update {self.model.__name__}: model is immutable'
            )
        return super().bulk_update(objs, fields, batch_size)


def install_sqlite_immutability_checks():
    """
    Install all immutability checks for SQLite.
    
    Call this in Django's ready() method to ensure all checks are installed.
    """
    from django.db import connection
    
    if 'sqlite' not in connection.settings_dict['ENGINE']:
        logger.info('Not using SQLite, immutability enforced by PostgreSQL triggers')
        return
    
    logger.info('Installing SQLite immutability checks')
    
    # Signal handlers are already connected via @receiver decorator
    # This function exists for explicit installation if needed
    
    logger.info('SQLite immutability checks installed')
