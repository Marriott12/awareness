"""User-facing policy governance views."""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Policy, Control, Violation
from django.db.models import Count, Q
from django.conf import settings


@login_required
def policies_list(request):
    """List all active policies visible to regular users."""
    policies = Policy.objects.filter(active=True, lifecycle='active').prefetch_related('controls')
    return render(request, 'policy/policies_list.html', {'policies': policies})


@login_required
def policy_detail(request, pk):
    """Show details of a specific policy including controls and user's violations."""
    policy = get_object_or_404(Policy, pk=pk, active=True)
    controls = policy.controls.filter(active=True).prefetch_related('rules')
    
    # Show user's own violations for this policy
    my_violations = Violation.objects.filter(
        policy=policy,
        user=request.user
    ).order_by('-timestamp')[:20]
    
    # Get ML risk score if available
    ml_score = None
    ml_enabled = getattr(settings, 'ML_ENABLED', False)
    if ml_enabled:
        try:
            from .ml_scorer import MLPolicyScorer
            scorer = MLPolicyScorer()
            if scorer.is_ready():
                # Calculate risk based on user's violation history
                user_features = {
                    'total_violations': Violation.objects.filter(user=request.user).count(),
                    'policy_violations': my_violations.count(),
                    'high_severity_violations': my_violations.filter(severity='high').count(),
                    'critical_violations': my_violations.filter(severity='critical').count(),
                    'unresolved_violations': my_violations.filter(resolved=False).count(),
                }
                ml_score = scorer.predict_risk(user_features)
        except Exception:
            pass  # Fail gracefully if ML not available
    
    return render(request, 'policy/policy_detail.html', {
        'policy': policy,
        'controls': controls,
        'my_violations': my_violations,
        'ml_score': ml_score,
    })


@login_required
def my_violations(request):
    """Show all violations for the current user."""
    violations = Violation.objects.filter(user=request.user).select_related(
        'policy', 'control', 'rule'
    ).order_by('-timestamp')[:100]
    
    # Group by status
    unresolved = violations.filter(resolved=False)
    resolved = violations.filter(resolved=True)
    
    # Get ML recommendations if enabled
    ml_recommendations = []
    ml_enabled = getattr(settings, 'ML_ENABLED', False)
    if ml_enabled and violations.exists():
        try:
            from .ml_scorer import MLPolicyScorer
            scorer = MLPolicyScorer()
            if scorer.is_ready():
                # Get top controls that user violates
                top_controls = violations.values('control__name').annotate(
                    count=Count('id')
                ).order_by('-count')[:3]
                
                ml_recommendations = [
                    f"Focus on {ctrl['control__name']} (violated {ctrl['count']} times)"
                    for ctrl in top_controls
                ]
        except Exception:
            pass
    
    return render(request, 'policy/my_violations.html', {
        'violations': violations,
        'unresolved': unresolved,
        'resolved': resolved,
        'ml_recommendations': ml_recommendations,
    })


@login_required
def ml_evaluation(request):
    """ML-powered policy evaluation and risk assessment for current user."""
    ml_enabled = getattr(settings, 'ML_ENABLED', False)
    
    if not ml_enabled:
        return render(request, 'policy/ml_evaluation.html', {
            'ml_enabled': False,
            'message': 'ML evaluation is not enabled on this system.'
        })
    
    try:
        from .ml_scorer import MLPolicyScorer
        scorer = MLPolicyScorer()
        
        if not scorer.is_ready():
            return render(request, 'policy/ml_evaluation.html', {
                'ml_enabled': True,
                'ml_ready': False,
                'message': 'ML models are being trained. Please check back later.'
            })
        
        # Get user's violation statistics
        total_violations = Violation.objects.filter(user=request.user).count()
        violations_by_severity = Violation.objects.filter(user=request.user).values(
            'severity'
        ).annotate(count=Count('id'))
        
        # Build feature vector
        user_features = {
            'total_violations': total_violations,
            'high_severity_violations': Violation.objects.filter(
                user=request.user, severity__in=['high', 'critical']
            ).count(),
            'recent_violations': Violation.objects.filter(
                user=request.user,
                timestamp__gte=timezone.now() - timedelta(days=30)
            ).count(),
            'unresolved_violations': Violation.objects.filter(
                user=request.user, resolved=False
            ).count(),
        }
        
        # Get ML prediction
        risk_score = scorer.predict_risk(user_features)
        risk_level = 'Low' if risk_score < 0.3 else 'Medium' if risk_score < 0.7 else 'High'
        
        # Get recommendations
        recommendations = scorer.get_recommendations(user_features, risk_score)
        
        # Get top violated policies
        top_policies = Violation.objects.filter(user=request.user).values(
            'policy__name'
        ).annotate(count=Count('id')).order_by('-count')[:5]
        
        return render(request, 'policy/ml_evaluation.html', {
            'ml_enabled': True,
            'ml_ready': True,
            'risk_score': round(risk_score * 100, 1),
            'risk_level': risk_level,
            'recommendations': recommendations,
            'user_features': user_features,
            'violations_by_severity': violations_by_severity,
            'top_policies': top_policies,
        })
        
    except Exception as e:
        return render(request, 'policy/ml_evaluation.html', {
            'ml_enabled': True,
            'ml_ready': False,
            'message': f'Error loading ML evaluation: {str(e)}'
        })


from django.utils import timezone
from datetime import timedelta
