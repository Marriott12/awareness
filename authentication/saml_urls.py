"""URL configuration for SAML authentication."""
from django.urls import path
from authentication import saml_views

app_name = 'saml'

urlpatterns = [
    path('login/', saml_views.saml_login, name='login'),
    path('acs/', saml_views.saml_acs, name='acs'),
    path('metadata/', saml_views.saml_metadata, name='metadata'),
    path('logout/', saml_views.saml_logout, name='logout'),
]
