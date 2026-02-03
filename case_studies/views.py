from django.shortcuts import render
from .models import CaseStudy


def case_studies_list(request):
    case_studies = CaseStudy.objects.filter(published=True)
    return render(request, "case_studies_list.html", {"case_studies": case_studies})
