"""API URL Configuration."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

from . import views

# API Router
router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'policies', views.PolicyViewSet, basename='policy')
router.register(r'controls', views.ControlViewSet, basename='control')
router.register(r'rules', views.RuleViewSet, basename='rule')
router.register(r'violations', views.ViolationViewSet, basename='violation')
router.register(r'events', views.HumanLayerEventViewSet, basename='event')
router.register(r'policy-history', views.PolicyHistoryViewSet, basename='policy-history')
router.register(r'metrics', views.DetectionMetricViewSet, basename='metric')
router.register(r'training', views.TrainingModuleViewSet, basename='training')
router.register(r'progress', views.TrainingProgressViewSet, basename='progress')
router.register(r'quizzes', views.QuizViewSet, basename='quiz')
router.register(r'quiz-attempts', views.QuizAttemptViewSet, basename='quiz-attempt')
router.register(r'case-studies', views.CaseStudyViewSet, basename='case-study')

# Swagger/OpenAPI Schema
schema_view = get_schema_view(
    openapi.Info(
        title="Awareness Portal API",
        default_version='v1',
        description="""
# Awareness Web Portal API

Enterprise-grade security awareness training platform with ML-powered policy governance.

## Features

- **Policy Management**: CRUD operations for policies, controls, and rules
- **Violation Tracking**: Monitor and manage policy violations
- **Training Modules**: Access training content and track progress
- **Quizzes**: Take quizzes and view results
- **Case Studies**: Browse security case studies
- **Analytics**: Get statistics and metrics

## Authentication

This API uses JWT (JSON Web Tokens) for authentication. To access protected endpoints:

1. Obtain a token pair: `POST /api/token/`
2. Include the access token in your requests: `Authorization: Bearer <access_token>`
3. Refresh expired tokens: `POST /api/token/refresh/`

## Rate Limiting

API endpoints are rate-limited to prevent abuse:
- 100 requests per hour for anonymous users
- 1000 requests per hour for authenticated users
- 5000 requests per hour for admin users
        """,
        terms_of_service="https://www.example.com/policies/terms/",
        contact=openapi.Contact(email="security@example.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

app_name = 'api'

urlpatterns = [
    # API root
    path('', include(router.urls)),
    
    # JWT Authentication
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # API Documentation
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
