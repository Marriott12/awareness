from django.urls import path
from . import views

urlpatterns = [
    path('', views.module_list, name='training_list'),
    path('<slug:slug>/', views.module_detail, name='module_detail'),
]
