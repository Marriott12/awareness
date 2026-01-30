from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from .models import Policy, Violation, Evidence
from django.db.models import Count


@staff_member_required
def compliance_dashboard(request):
    # summary: counts of violations by policy and risk trends
    by_policy = Violation.objects.values('policy__name').annotate(total=Count('id')).order_by('-total')[:20]
    recent = Violation.objects.order_by('-timestamp')[:50]
    return render(request, 'policy/compliance_dashboard.html', {'by_policy': by_policy, 'recent': recent})


@staff_member_required
def violations_list(request):
    qs = Violation.objects.order_by('-timestamp')[:200]
    return render(request, 'policy/violations_list.html', {'violations': qs})


@staff_member_required
def violation_detail(request, pk):
    v = get_object_or_404(Violation, pk=pk)
    evidence = getattr(v, 'evidence', {})
    return render(request, 'policy/violation_detail.html', {'violation': v, 'evidence': evidence})
