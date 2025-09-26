"""
URL configuration for awareness_portal project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.urls import reverse


def index(request):
    # landing page should be the login screen; if authenticated, go to dashboard
    if request.user.is_authenticated:
        return redirect(reverse('dashboard:home'))
    return redirect(reverse('login'))


urlpatterns = [
    path('', index, name='index'),
    path('admin/', admin.site.urls),
    path('dashboard/', include('dashboard.urls')),
    path('training/', include('training.urls')),
    path('quizzes/', include('quizzes.urls')),
    path('case-studies/', include('case_studies.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]
