from django.shortcuts import render


def case_studies_list(request):
    return render(request, "case_studies_list.html")
