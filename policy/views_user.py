"""User-facing policy governance views."""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Control, Policy, Violation


@login_required
def policies_list(request):
    """List all active policies visible to regular users."""
    policies = Policy.objects.filter(active=True, lifecycle='active').prefetch_related('controls')
    return render(request, 'policy/policies_list.html', {'policies': policies})


@login_required
def policy_detail(request, pk):
    """Show details of a specific policy including controls and user's violations."""
    policy = get_object_or_404(Policy, pk=pk, active=True)
    controls = Control.objects.filter(policy=policy, active=True).prefetch_related('rules')
    
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
            from .ml_scorer import get_ml_scorer
            scorer = get_ml_scorer()
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
    violations_qs = Violation.objects.filter(user=request.user).select_related(
        'policy', 'control', 'rule'
    ).order_by('-timestamp')
    
    # Group by status (limit each group separately)
    unresolved = violations_qs.filter(resolved=False)[:50]
    resolved = violations_qs.filter(resolved=True)[:50]
    
    # All violations for display (limited to 100 most recent)
    violations = violations_qs[:100]
    
    # Get ML recommendations if enabled
    ml_recommendations = []
    ml_enabled = getattr(settings, 'ML_ENABLED', False)
    if ml_enabled and violations_qs.exists():
        try:
            from .ml_scorer import get_ml_scorer
            scorer = get_ml_scorer()
            if scorer.is_ready():
                user_features = {
                    'total_violations': violations_qs.count(),
                    'high_severity_violations': violations_qs.filter(severity__in=['high', 'critical']).count(),
                    'critical_violations': violations_qs.filter(severity='critical').count(),
                    'unresolved_violations': violations_qs.filter(resolved=False).count(),
                }
                ml_recommendations = scorer.get_recommendations(user_features, scorer.predict_risk(user_features))
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
        from .ml_scorer import get_ml_scorer
        scorer = get_ml_scorer()
        
        if not scorer.is_ready():
            return render(request, 'policy/ml_evaluation.html', {
                'ml_enabled': True,
                'ml_ready': False,
                'message': 'ML models are not ready yet. Label events in admin and train a model first.'
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
        risk_result = scorer.predict_risk(user_features)
        risk_score = risk_result['score']
        risk_level = risk_result['risk_level']
        
        # Get recommendations
        recommendations = scorer.get_recommendations(user_features, risk_result)
        
        # Get top violated policies
        top_policies = Violation.objects.filter(user=request.user).values(
            'policy__name'
        ).annotate(count=Count('id')).order_by('-count')[:5]
        
        return render(request, 'policy/ml_evaluation.html', {
            'ml_enabled': True,
            'ml_ready': True,
            'risk_score': risk_score,
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

