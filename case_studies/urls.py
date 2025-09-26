from django.urls import path
from . import views

urlpatterns = [
    path("", views.case_studies_list, name="case_studies_list"),
]
