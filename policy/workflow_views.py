"""
Policy workflow UI - dedicated approval interface for policy lifecycle.

Provides a clean, dedicated UI for policy approval workflow separate from
Django admin, with version diffing and approval tracking.

Features:
- Policy submission and review workflow
- Visual diff between policy versions
- Approval/rejection with comments
- Email notifications
- Audit trail

URL Configuration (add to urls.py):
    path('policy-workflow/', include('policy.workflow_urls')),

Templates required:
    - policy/workflow/dashboard.html
    - policy/workflow/policy_detail.html
    - policy/workflow/policy_diff.html
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from typing import Dict, Any, List
import difflib
import json
import logging

logger = logging.getLogger(__name__)


def is_policy_reviewer(user) -> bool:
    """Check if user has policy review permissions."""
    return user.is_staff or user.groups.filter(name='Policy Reviewers').exists()


@login_required
@user_passes_test(is_policy_reviewer)
def workflow_dashboard(request):
    """Dashboard showing all policies needing review."""
    from .models import Policy, PolicyHistory
    
    # Policies in review state
    pending_reviews = Policy.objects.filter(lifecycle='review').order_by('-created_at')
    
    # Recently approved
    recently_approved = Policy.objects.filter(
        lifecycle='active'
    ).order_by('-updated_at')[:10]
    
    # Draft policies
    drafts = Policy.objects.filter(lifecycle='draft').order_by('-created_at')
    
    # My pending approvals
    from .models import PolicyApproval
    my_pending = PolicyApproval.objects.filter(
        approver=request.user,
        approved_at__isnull=True,
        rejected_at__isnull=True
    ).select_related('policy')
    
    context = {
        'pending_reviews': pending_reviews,
        'recently_approved': recently_approved,
        'drafts': drafts,
        'my_pending': my_pending,
        'stats': {
            'pending_count': pending_reviews.count(),
            'draft_count': drafts.count(),
            'my_pending_count': my_pending.count(),
        }
    }
    
    return render(request, 'policy/workflow/dashboard.html', context)


@login_required
@user_passes_test(is_policy_reviewer)
def policy_detail(request, policy_id: int):
    """Detailed view of policy with approval actions."""
    from .models import Policy, PolicyHistory, PolicyApproval
    
    policy = get_object_or_404(Policy, pk=policy_id)
    
    # Get approval history
    approvals = PolicyApproval.objects.filter(
        policy=policy
    ).order_by('-created_at')
    
    # Get version history
    versions = PolicyHistory.objects.filter(
        policy=policy
    ).order_by('-version')
    
    # Check if current user can approve
    can_approve = (
        policy.lifecycle == 'review' and
        not approvals.filter(approver=request.user).exists()
    )
    
    # Get related controls and rules
    controls = policy.controls.all().prefetch_related('rules')
    
    context = {
        'policy': policy,
        'approvals': approvals,
        'versions': versions,
        'can_approve': can_approve,
        'controls': controls,
    }
    
    return render(request, 'policy/workflow/policy_detail.html', context)


@login_required
@user_passes_test(is_policy_reviewer)
def approve_policy(request, policy_id: int):
    """Approve a policy."""
    if request.method != 'POST':
        return redirect('policy_detail', policy_id=policy_id)
    
    from .models import Policy, PolicyApproval
    from .lifecycle import transition_policy
    
    policy = get_object_or_404(Policy, pk=policy_id)
    comment = request.POST.get('comment', '')
    
    try:
        with transaction.atomic():
            # Create approval record
            approval = PolicyApproval.objects.create(
                policy=policy,
                approver=request.user,
                approved_at=timezone.now(),
                comments=comment
            )
            
            # Check if enough approvals
            required_approvals = getattr(policy, 'required_approvals', 1)
            approval_count = PolicyApproval.objects.filter(
                policy=policy,
                approved_at__isnull=False
            ).count()
            
            if approval_count >= required_approvals:
                # Transition to active
                transition_policy(policy, 'activate', request.user)
                messages.success(request, f'Policy "{policy.name}" approved and activated!')
            else:
                messages.success(
                    request,
                    f'Approval recorded. {required_approvals - approval_count} more required.'
                )
            
            # Send notification
            _send_approval_notification(policy, request.user, approved=True)
            
    except Exception as e:
        logger.exception(f'Failed to approve policy {policy_id}: {e}')
        messages.error(request, f'Approval failed: {str(e)}')
    
    return redirect('policy_detail', policy_id=policy_id)


@login_required
@user_passes_test(is_policy_reviewer)
def reject_policy(request, policy_id: int):
    """Reject a policy."""
    if request.method != 'POST':
        return redirect('policy_detail', policy_id=policy_id)
    
    from .models import Policy, PolicyApproval
    from .lifecycle import transition_policy
    
    policy = get_object_or_404(Policy, pk=policy_id)
    comment = request.POST.get('comment', '')
    
    if not comment:
        messages.error(request, 'Rejection reason is required')
        return redirect('policy_detail', policy_id=policy_id)
    
    try:
        with transaction.atomic():
            # Create rejection record
            PolicyApproval.objects.create(
                policy=policy,
                approver=request.user,
                rejected_at=timezone.now(),
                comments=comment
            )
            
            # Transition back to draft
            transition_policy(policy, 'draft', request.user)
            
            messages.warning(request, f'Policy "{policy.name}" rejected and returned to draft')
            
            # Send notification
            _send_approval_notification(policy, request.user, approved=False, reason=comment)
            
    except Exception as e:
        logger.exception(f'Failed to reject policy {policy_id}: {e}')
        messages.error(request, f'Rejection failed: {str(e)}')
    
    return redirect('policy_detail', policy_id=policy_id)


@login_required
@user_passes_test(is_policy_reviewer)
def compare_versions(request, policy_id: int, version1: int, version2: int):
    """Visual diff between two policy versions."""
    from .models import Policy, PolicyHistory
    
    policy = get_object_or_404(Policy, pk=policy_id)
    
    hist1 = get_object_or_404(PolicyHistory, policy=policy, version=version1)
    hist2 = get_object_or_404(PolicyHistory, policy=policy, version=version2)
    
    # Generate diff
    diff = _generate_policy_diff(hist1, hist2)
    
    context = {
        'policy': policy,
        'version1': hist1,
        'version2': hist2,
        'diff': diff,
    }
    
    return render(request, 'policy/workflow/policy_diff.html', context)


def _generate_policy_diff(version1, version2) -> Dict[str, Any]:
    """
    Generate visual diff between two policy versions.
    
    Returns:
        Dictionary with diff results for each field
    """
    diffs = {}
    
    # Compare name
    if version1.snapshot.get('name') != version2.snapshot.get('name'):
        diffs['name'] = {
            'old': version1.snapshot.get('name'),
            'new': version2.snapshot.get('name')
        }
    
    # Compare description
    desc1 = version1.snapshot.get('description', '')
    desc2 = version2.snapshot.get('description', '')
    
    if desc1 != desc2:
        diff_lines = list(difflib.unified_diff(
            desc1.splitlines(),
            desc2.splitlines(),
            lineterm='',
            fromfile=f'Version {version1.version}',
            tofile=f'Version {version2.version}'
        ))
        diffs['description'] = diff_lines
    
    # Compare controls (simplified)
    controls1 = version1.snapshot.get('controls', [])
    controls2 = version2.snapshot.get('controls', [])
    
    if json.dumps(controls1, sort_keys=True) != json.dumps(controls2, sort_keys=True):
        diffs['controls'] = {
            'added': len(controls2) - len(controls1),
            'modified': True
        }
    
    return diffs


def _send_approval_notification(policy, approver, approved: bool, reason: str = ''):
    """Send email notification about policy approval/rejection."""
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        
        subject = f'Policy {"Approved" if approved else "Rejected"}: {policy.name}'
        
        if approved:
            message = f"""
Policy "{policy.name}" has been approved by {approver.get_full_name() or approver.username}.

The policy is now active and will be enforced.

View policy: {settings.BASE_URL}/policy-workflow/policy/{policy.id}/
            """
        else:
            message = f"""
Policy "{policy.name}" has been rejected by {approver.get_full_name() or approver.username}.

Reason: {reason}

The policy has been returned to draft status.

View policy: {settings.BASE_URL}/policy-workflow/policy/{policy.id}/
            """
        
        # Get recipients (policy author + reviewers)
        recipients = [policy.created_by.email] if hasattr(policy, 'created_by') and policy.created_by else []
        
        if recipients:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                fail_silently=True
            )
            
    except Exception as e:
        logger.exception(f'Failed to send notification: {e}')


@login_required
def submit_policy_for_review(request, policy_id: int):
    """Submit policy from draft to review."""
    from .models import Policy
    from .lifecycle import transition_policy
    
    policy = get_object_or_404(Policy, pk=policy_id)
    
    # Check ownership or admin
    if not (request.user.is_staff or 
            (hasattr(policy, 'created_by') and policy.created_by == request.user)):
        messages.error(request, 'You do not have permission to submit this policy')
        return redirect('workflow_dashboard')
    
    try:
        transition_policy(policy, 'submit_for_review', request.user)
        messages.success(request, f'Policy "{policy.name}" submitted for review')
    except Exception as e:
        logger.exception(f'Failed to submit policy: {e}')
        messages.error(request, f'Submission failed: {str(e)}')
    
    return redirect('policy_detail', policy_id=policy_id)
