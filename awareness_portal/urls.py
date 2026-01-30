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
from authentication.views import RoleLoginView
from authentication import debug_views


def index(request):
    # landing page should be the login screen; if authenticated, go to dashboard
    if request.user.is_authenticated:
        return redirect(reverse("dashboard:home"))
    return redirect(reverse("login"))


urlpatterns = [
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    path("dashboard/", include("dashboard.urls")),
    path("training/", include("training.urls")),
    path("quizzes/", include("quizzes.urls")),
    path("case-studies/", include("case_studies.urls")),
    # Use our custom login view but keep the rest of the auth URLs (logout, password reset)
    path(
        "accounts/login/",
        RoleLoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    # Debug endpoint for authentication/session/cookie issues
    path("debug/auth-status/", debug_views.debug_auth_status, name="debug_auth_status"),
    path("debug/session-test/", debug_views.session_test, name="debug_session_test"),
    # Policy governance views
    path("policy/", include("policy.urls", namespace="policy")),
]
