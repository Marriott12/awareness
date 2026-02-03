from django.urls import path
from . import views_gov as gov
from . import views_user as user_views

app_name = 'policy'

urlpatterns = [
    # Staff/admin governance views
    path('gov/', gov.compliance_dashboard, name='compliance_dashboard'),
    path('gov/violations/', gov.violations_list, name='violations_list'),
    path('gov/violation/<int:pk>/', gov.violation_detail, name='violation_detail'),
    
    # User-facing policy views
    path('policies/', user_views.policies_list, name='policies_list'),
    path('policy/<int:pk>/', user_views.policy_detail, name='policy_detail'),
    path('my-violations/', user_views.my_violations, name='my_violations'),
    path('ml-evaluation/', user_views.ml_evaluation, name='ml_evaluation'),
]
