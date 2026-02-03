"""Enhanced compliance engine with safety limits and protections.

Improvements:
- Expression depth limiting
- ReDoS protection
- Evaluation timeouts
- Circuit breaker integration
- Rate limiting per user
"""
import re
import time
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from policy.resilience import circuit_breaker

logger = logging.getLogger(__name__)

# Safety limits
MAX_EXPRESSION_DEPTH = getattr(settings, 'COMPLIANCE_MAX_EXPRESSION_DEPTH', 10)
EVALUATION_TIMEOUT = getattr(settings, 'COMPLIANCE_EVALUATION_TIMEOUT', 1.0)  # seconds
MAX_REGEX_LENGTH = getattr(settings, 'COMPLIANCE_MAX_REGEX_LENGTH', 1000)
SAFE_REGEX_TIMEOUT = 0.1  # seconds


class ExpressionDepthExceeded(Exception):
    """Raised when expression nesting is too deep."""
    pass


class EvaluationTimeout(Exception):
    """Raised when expression evaluation takes too long."""
    pass


class UnsafeRegexError(Exception):
    """Raised when regex pattern is potentially dangerous."""
    pass


def validate_regex_safety(pattern: str) -> None:
    """Validate regex pattern for ReDoS vulnerabilities.
    
    Args:
        pattern: Regex pattern to validate
        
    Raises:
        UnsafeRegexError: If pattern is potentially dangerous
    """
    if len(pattern) > MAX_REGEX_LENGTH:
        raise UnsafeRegexError(f'Regex pattern too long: {len(pattern)} > {MAX_REGEX_LENGTH}')
    
    # Check for catastrophic backtracking patterns
    dangerous_patterns = [
        r'(\w+)+',  # Nested quantifiers
        r'(\w*)*',  # Nested quantifiers
        r'(\w+)*',  # Nested quantifiers
        r'(\w*)+',  # Nested quantifiers
        r'(a+)+',   # Exponential backtracking
        r'(a|a)*',  # Alternation with overlap
    ]
    
    for dangerous in dangerous_patterns:
        if re.search(dangerous, pattern):
            logger.warning(f'Potentially dangerous regex pattern detected: {pattern}')
            raise UnsafeRegexError(f'Pattern contains potentially dangerous construct: {dangerous}')
    
    # Test regex compilation with timeout
    try:
        test_string = 'a' * 100  # Test against simple string
        start = time.time()
        compiled = re.compile(pattern)
        compiled.search(test_string)
        elapsed = time.time() - start
        
        if elapsed > SAFE_REGEX_TIMEOUT:
            raise UnsafeRegexError(f'Regex evaluation too slow: {elapsed:.3f}s > {SAFE_REGEX_TIMEOUT}s')
    except re.error as e:
        raise UnsafeRegexError(f'Invalid regex pattern: {e}')


def check_expression_depth(expr: Dict[str, Any], current_depth: int = 0) -> int:
    """Check expression nesting depth.
    
    Args:
        expr: Expression dictionary
        current_depth: Current nesting depth
        
    Returns:
        Maximum depth found
        
    Raises:
        ExpressionDepthExceeded: If depth exceeds limit
    """
    if current_depth > MAX_EXPRESSION_DEPTH:
        raise ExpressionDepthExceeded(f'Expression depth {current_depth} exceeds limit {MAX_EXPRESSION_DEPTH}')
    
    max_depth = current_depth
    
    # Check nested expressions
    if isinstance(expr, dict):
        for key, value in expr.items():
            if key in ('and', 'or', 'not'):
                if isinstance(value, list):
                    for sub_expr in value:
                        depth = check_expression_depth(sub_expr, current_depth + 1)
                        max_depth = max(max_depth, depth)
                elif isinstance(value, dict):
                    depth = check_expression_depth(value, current_depth + 1)
                    max_depth = max(max_depth, depth)
    
    return max_depth


@circuit_breaker(failure_threshold=10, timeout=60)
def evaluate_expression_safe(expr: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Safely evaluate compliance expression with all protections.
    
    Args:
        expr: Expression to evaluate
        context: Evaluation context
        
    Returns:
        Evaluation result
        
    Raises:
        ExpressionDepthExceeded: If expression is too deep
        EvaluationTimeout: If evaluation takes too long
        UnsafeRegexError: If regex is potentially dangerous
    """
    # Check expression depth
    check_expression_depth(expr)
    
    # Set timeout for evaluation
    start_time = time.time()
    
    def check_timeout():
        if time.time() - start_time > EVALUATION_TIMEOUT:
            raise EvaluationTimeout(f'Expression evaluation exceeded {EVALUATION_TIMEOUT}s timeout')
    
    # Evaluate with timeout checks
    result = _evaluate_with_timeout(expr, context, check_timeout)
    
    return result


def _evaluate_with_timeout(expr: Dict[str, Any], context: Dict[str, Any], check_timeout_fn) -> bool:
    """Evaluate expression with periodic timeout checks."""
    check_timeout_fn()  # Check before evaluation
    
    if not isinstance(expr, dict):
        return bool(expr)
    
    # Handle logical operators
    if 'and' in expr:
        check_timeout_fn()
        results = [_evaluate_with_timeout(sub, context, check_timeout_fn) for sub in expr['and']]
        return all(results)
    
    elif 'or' in expr:
        check_timeout_fn()
        results = [_evaluate_with_timeout(sub, context, check_timeout_fn) for sub in expr['or']]
        return any(results)
    
    elif 'not' in expr:
        check_timeout_fn()
        return not _evaluate_with_timeout(expr['not'], context, check_timeout_fn)
    
    # Handle regex operator with safety check
    elif 'regex' in expr:
        check_timeout_fn()
        pattern = expr['regex']['pattern']
        field = expr['regex']['field']
        
        # Validate regex safety before evaluation
        validate_regex_safety(pattern)
        
        value = context.get(field, '')
        compiled = re.compile(pattern, re.IGNORECASE)
        return bool(compiled.search(str(value)))
    
    # Handle rule reference
    elif 'rule' in expr:
        check_timeout_fn()
        rule_id = expr['rule']
        from policy.models import Rule
        
        try:
            rule = Rule.objects.get(id=rule_id)
            # Recursive evaluation with same timeout
            return _evaluate_with_timeout(rule.expression, context, check_timeout_fn)
        except Rule.DoesNotExist:
            logger.error(f'Rule {rule_id} not found in expression')
            return False
    
    # Handle comparison operators
    elif 'equals' in expr:
        check_timeout_fn()
        return context.get(expr['equals']['field']) == expr['equals']['value']
    
    elif 'contains' in expr:
        check_timeout_fn()
        value = str(context.get(expr['contains']['field'], ''))
        search = str(expr['contains']['value'])
        return search in value
    
    elif 'greater_than' in expr:
        check_timeout_fn()
        value = context.get(expr['greater_than']['field'], 0)
        threshold = expr['greater_than']['value']
        return float(value) > float(threshold)
    
    else:
        logger.warning(f'Unknown expression type: {expr}')
        return False


def evaluate_with_rate_limit(expr: Dict[str, Any], context: Dict[str, Any], user_id: int) -> bool:
    """Evaluate expression with per-user rate limiting.
    
    Args:
        expr: Expression to evaluate
        context: Evaluation context
        user_id: User ID for rate limiting
        
    Returns:
        Evaluation result
    """
    from policy.resilience import RateLimiter
    
    # Check rate limit (100 evaluations per minute per user)
    limiter = RateLimiter(key_prefix='compliance_eval')
    key = f'user_{user_id}'
    
    allowed, info = limiter.check(key, limit=100, window=60)
    
    if not allowed:
        logger.warning(f'User {user_id} exceeded compliance evaluation rate limit')
        raise Exception(f'Rate limit exceeded for compliance evaluations')
    
    # Evaluate with safety checks
    return evaluate_expression_safe(expr, context)
