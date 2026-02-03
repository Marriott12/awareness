"""Policy lifecycle state machine with approval workflow.

Implements proper FSM with:
- State transition guards
- Approval requirements
- Audit trail
- Automated validation
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import PermissionDenied

User = get_user_model()


class PolicyApproval(models.Model):
    """Approval record for policy lifecycle transitions."""
    
    TRANSITION_CHOICES = (
        ('draft_to_review', 'Draft → Review'),
        ('review_to_active', 'Review → Active'),
        ('active_to_retired', 'Active → Retired'),
        ('review_to_draft', 'Review → Draft (rejected)'),
    )
    
    policy = models.ForeignKey('policy.Policy', on_delete=models.CASCADE, related_name='approvals')
    transition = models.CharField(max_length=32, choices=TRANSITION_CHOICES)
    from_state = models.CharField(max_length=16)
    to_state = models.CharField(max_length=16)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='policy_approvals')
    approved_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True, help_text='Justification for approval/rejection')
    metadata = models.JSONField(default=dict, help_text='Additional context (git commit, ticket ID, etc.)')
    
    class Meta:
        db_table = 'policy_policyapproval'
        ordering = ['-approved_at']
    
    def __str__(self):
        return f'{self.policy.name}: {self.from_state} → {self.to_state} by {self.approved_by}'


class PolicyLifecycleManager:
    """State machine manager for policy lifecycle transitions."""
    
    # Valid transitions
    TRANSITIONS = {
        'draft': ['review'],
        'review': ['active', 'draft'],  # Can approve or reject
        'active': ['retired'],
        'retired': []  # Terminal state
    }
    
    # Permissions required for each transition
    REQUIRED_PERMISSIONS = {
        'draft_to_review': 'policy.submit_policy',
        'review_to_active': 'policy.approve_policy',
        'review_to_draft': 'policy.reject_policy',
        'active_to_retired': 'policy.retire_policy',
    }
    
    @classmethod
    def can_transition(cls, policy, to_state: str, user: User = None) -> tuple[bool, str]:
        """Check if transition is allowed.
        
        Args:
            policy: Policy instance
            to_state: Target lifecycle state
            user: User attempting transition
            
        Returns:
            (allowed: bool, reason: str)
        """
        from_state = policy.lifecycle
        
        # Check if transition is valid
        if to_state not in cls.TRANSITIONS.get(from_state, []):
            return False, f'Invalid transition: {from_state} → {to_state}'
        
        # Check permission
        transition_key = f'{from_state}_to_{to_state}'
        required_perm = cls.REQUIRED_PERMISSIONS.get(transition_key)
        
        if required_perm and user and not user.has_perm(required_perm):
            return False, f'User lacks permission: {required_perm}'
        
        # Additional validation for review → active
        if from_state == 'review' and to_state == 'active':
            # Check for validation errors
            if policy.controls.count() == 0:
                return False, 'Policy has no controls'
            
            # Check expression validation
            for control in policy.controls.all():
                if control.expression:
                    from policy.expression import validate_expression
                    valid, errors = validate_expression(control.expression, control)
                    if not valid:
                        return False, f'Control {control.name} has invalid expression: {errors}'
            
            # Check for existing ACTIVE policy with same name
            from policy.models import Policy
            existing = Policy.objects.filter(
                name=policy.name,
                lifecycle='active'
            ).exclude(pk=policy.pk).exists()
            
            if existing:
                return False, f'Another policy with name "{policy.name}" is already ACTIVE'
        
        return True, 'Transition allowed'
    
    @classmethod
    def transition(
        cls,
        policy,
        to_state: str,
        user: User,
        reason: str = '',
        metadata: dict = None
    ) -> PolicyApproval:
        """Execute lifecycle transition with approval record.
        
        Args:
            policy: Policy instance
            to_state: Target state
            user: User performing transition
            reason: Justification text
            metadata: Additional context
            
        Returns:
            PolicyApproval record
            
        Raises:
            PermissionDenied if transition not allowed
        """
        from_state = policy.lifecycle
        
        # Validate transition
        allowed, msg = cls.can_transition(policy, to_state, user)
        if not allowed:
            raise PermissionDenied(msg)
        
        # Create approval record
        transition_key = f'{from_state}_to_{to_state}'
        approval = PolicyApproval.objects.create(
            policy=policy,
            transition=transition_key,
            from_state=from_state,
            to_state=to_state,
            approved_by=user,
            reason=reason,
            metadata=metadata or {}
        )
        
        # Update policy state
        policy.lifecycle = to_state
        policy.save(update_fields=['lifecycle'])
        
        # Create history entry
        from policy.models import PolicyHistory
        PolicyHistory.objects.create(
            policy=policy,
            changed_by=user,
            change_type='lifecycle',
            summary=f'Lifecycle: {from_state} → {to_state}',
            diff={'from': from_state, 'to': to_state, 'reason': reason}
        )
        
        return approval
    
    @classmethod
    def get_available_transitions(cls, policy, user: User = None) -> list[tuple[str, str]]:
        """Get list of available transitions for policy.
        
        Args:
            policy: Policy instance
            user: User to check permissions for
            
        Returns:
            List of (state, label) tuples for available transitions
        """
        current = policy.lifecycle
        available = []
        
        for next_state in cls.TRANSITIONS.get(current, []):
            allowed, reason = cls.can_transition(policy, next_state, user)
            if allowed:
                label = f'{current.title()} → {next_state.title()}'
                available.append((next_state, label))
        
        return available
