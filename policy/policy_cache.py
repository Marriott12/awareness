"""Policy caching layer for improved performance.

Implements:
- Redis-backed policy cache
- Active policy caching
- Rule caching
- Cache invalidation on updates
- TTL management
"""
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
import logging
import hashlib
import json
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Cache TTL settings
POLICY_CACHE_TTL = 3600  # 1 hour
RULE_CACHE_TTL = 3600
ACTIVE_POLICIES_TTL = 300  # 5 minutes


class PolicyCache:
    """Redis-backed caching for policies and rules."""
    
    @staticmethod
    def get_cache_key(prefix: str, identifier: Any) -> str:
        """Generate cache key."""
        if isinstance(identifier, (dict, list)):
            identifier = hashlib.md5(json.dumps(identifier, sort_keys=True).encode()).hexdigest()
        return f'policy_cache:{prefix}:{identifier}'
    
    @classmethod
    def get_active_policies(cls):
        """Get all active policies from cache or DB."""
        cache_key = cls.get_cache_key('active_policies', 'all')
        
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f'Cache HIT: active_policies')
            return cached
        
        # Load from database
        from policy.models import Policy
        policies = list(Policy.objects.filter(lifecycle_state='ACTIVE').prefetch_related('controls', 'controls__rules'))
        
        # Cache for 5 minutes
        cache.set(cache_key, policies, ACTIVE_POLICIES_TTL)
        logger.debug(f'Cache MISS: active_policies, loaded {len(policies)} policies')
        
        return policies
    
    @classmethod
    def get_policy(cls, policy_id: int):
        """Get single policy from cache or DB."""
        cache_key = cls.get_cache_key('policy', policy_id)
        
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f'Cache HIT: policy {policy_id}')
            return cached
        
        # Load from database
        from policy.models import Policy
        try:
            policy = Policy.objects.prefetch_related('controls', 'controls__rules').get(id=policy_id)
            cache.set(cache_key, policy, POLICY_CACHE_TTL)
            logger.debug(f'Cache MISS: policy {policy_id}')
            return policy
        except Policy.DoesNotExist:
            # Cache negative result for 1 minute
            cache.set(cache_key, None, 60)
            return None
    
    @classmethod
    def get_rule(cls, rule_id: int):
        """Get single rule from cache or DB."""
        cache_key = cls.get_cache_key('rule', rule_id)
        
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f'Cache HIT: rule {rule_id}')
            return cached
        
        # Load from database
        from policy.models import Rule
        try:
            rule = Rule.objects.select_related('control', 'control__policy').get(id=rule_id)
            cache.set(cache_key, rule, RULE_CACHE_TTL)
            logger.debug(f'Cache MISS: rule {rule_id}')
            return rule
        except Rule.DoesNotExist:
            cache.set(cache_key, None, 60)
            return None
    
    @classmethod
    def get_user_violations(cls, user_id: int, include_resolved: bool = False):
        """Get user violations from cache or DB."""
        cache_key = cls.get_cache_key('user_violations', f'{user_id}_{include_resolved}')
        
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f'Cache HIT: user_violations {user_id}')
            return cached
        
        # Load from database
        from policy.models import Violation
        violations = Violation.objects.filter(user_id=user_id)
        if not include_resolved:
            violations = violations.filter(resolved=False)
        violations = list(violations.select_related('policy', 'rule'))
        
        # Cache for 1 minute (violations change frequently)
        cache.set(cache_key, violations, 60)
        logger.debug(f'Cache MISS: user_violations {user_id}, loaded {len(violations)} violations')
        
        return violations
    
    @classmethod
    def invalidate_policy(cls, policy_id: int):
        """Invalidate policy cache."""
        cache.delete(cls.get_cache_key('policy', policy_id))
        cache.delete(cls.get_cache_key('active_policies', 'all'))
        logger.info(f'Invalidated cache for policy {policy_id}')
    
    @classmethod
    def invalidate_rule(cls, rule_id: int):
        """Invalidate rule cache."""
        cache.delete(cls.get_cache_key('rule', rule_id))
        logger.info(f'Invalidated cache for rule {rule_id}')
    
    @classmethod
    def invalidate_user_violations(cls, user_id: int):
        """Invalidate user violations cache."""
        cache.delete(cls.get_cache_key('user_violations', f'{user_id}_True'))
        cache.delete(cls.get_cache_key('user_violations', f'{user_id}_False'))
        logger.info(f'Invalidated violation cache for user {user_id}')
    
    @classmethod
    def clear_all(cls):
        """Clear all policy-related caches."""
        cache.delete_pattern('policy_cache:*')
        logger.info('Cleared all policy caches')


# Auto-invalidate cache on model changes
@receiver(post_save, sender='policy.Policy')
def invalidate_policy_cache(sender, instance, **kwargs):
    """Invalidate policy cache when policy is updated."""
    PolicyCache.invalidate_policy(instance.id)


@receiver(post_delete, sender='policy.Policy')
def invalidate_policy_cache_on_delete(sender, instance, **kwargs):
    """Invalidate policy cache when policy is deleted."""
    PolicyCache.invalidate_policy(instance.id)


@receiver(post_save, sender='policy.Rule')
def invalidate_rule_cache(sender, instance, **kwargs):
    """Invalidate rule cache when rule is updated."""
    PolicyCache.invalidate_rule(instance.id)
    # Also invalidate parent policy
    if instance.control and instance.control.policy:
        PolicyCache.invalidate_policy(instance.control.policy.id)


@receiver(post_delete, sender='policy.Rule')
def invalidate_rule_cache_on_delete(sender, instance, **kwargs):
    """Invalidate rule cache when rule is deleted."""
    PolicyCache.invalidate_rule(instance.id)
    if instance.control and instance.control.policy:
        PolicyCache.invalidate_policy(instance.control.policy.id)


@receiver(post_save, sender='policy.Violation')
def invalidate_violation_cache(sender, instance, **kwargs):
    """Invalidate violation cache when violation is updated."""
    if instance.user_id:
        PolicyCache.invalidate_user_violations(instance.user_id)


@receiver(post_delete, sender='policy.Violation')
def invalidate_violation_cache_on_delete(sender, instance, **kwargs):
    """Invalidate violation cache when violation is deleted."""
    if instance.user_id:
        PolicyCache.invalidate_user_violations(instance.user_id)
