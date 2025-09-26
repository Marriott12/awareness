from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('user/', views.user_dashboard, name='user'),
    path('admin/', views.admin_dashboard, name='admin'),
]
