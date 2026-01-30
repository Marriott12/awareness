from django.urls import path
from . import views_gov as gov

app_name = 'policy'

urlpatterns = [
    path('gov/', gov.compliance_dashboard, name='compliance_dashboard'),
    path('gov/violations/', gov.violations_list, name='violations_list'),
    path('gov/violation/<int:pk>/', gov.violation_detail, name='violation_detail'),
]
