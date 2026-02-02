from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from .models import Policy, Violation, Evidence
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta


@staff_member_required
def compliance_dashboard(request):
    # summary: counts of violations by policy and risk trends
    by_policy = Violation.objects.values('policy__name').annotate(total=Count('id')).order_by('-total')[:20]
    
    # Violations over time (last 30 days, daily)
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    violations_by_day = []
    for i in range(30):
        day_start = thirty_days_ago + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        count = Violation.objects.filter(timestamp__gte=day_start, timestamp__lt=day_end).count()
        violations_by_day.append({'date': day_start.date().isoformat(), 'count': count})
    
    # Risk distribution by severity
    by_severity = Violation.objects.values('severity').annotate(total=Count('id')).order_by('-total')
    
    # Risk distribution by user (top 10)
    by_user = Violation.objects.filter(user__isnull=False).values('user__username').annotate(total=Count('id')).order_by('-total')[:10]
    
    recent = Violation.objects.order_by('-timestamp')[:50]
    return render(request, 'policy/compliance_dashboard.html', {
        'by_policy': by_policy,
        'by_severity': by_severity,
        'by_user': by_user,
        'violations_by_day': violations_by_day,
        'recent': recent,
    })


@staff_member_required
def violations_list(request):
    qs = Violation.objects.order_by('-timestamp')[:200]
    return render(request, 'policy/violations_list.html', {'violations': qs})


@staff_member_required
def violation_detail(request, pk):
    v = get_object_or_404(Violation, pk=pk)
    evidence = getattr(v, 'evidence', {})
    # Get action log for this violation
    action_log = v.action_log.all().order_by('-timestamp')
    return render(request, 'policy/violation_detail.html', {
        'violation': v,
        'evidence': evidence,
        'action_log': action_log,
    })
