"""Tests for REST API endpoints."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from policy.models import Policy, Control, Rule, Violation
from training.models import TrainingModule, TrainingProgress
from quizzes.models import Quiz, Question, QuizAttempt
from case_studies.models import CaseStudy

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client."""
    return APIClient()


@pytest.fixture
def admin_user(db):
    """Create admin user."""
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin123'
    )


@pytest.fixture
def regular_user(db):
    """Create regular user."""
    return User.objects.create_user(
        username='user',
        email='user@example.com',
        password='user123'
    )


@pytest.fixture
def admin_token(admin_user):
    """Get JWT token for admin user."""
    refresh = RefreshToken.for_user(admin_user)
    return str(refresh.access_token)


@pytest.fixture
def user_token(regular_user):
    """Get JWT token for regular user."""
    refresh = RefreshToken.for_user(regular_user)
    return str(refresh.access_token)


@pytest.fixture
def sample_policy(db, admin_user):
    """Create sample policy."""
    return Policy.objects.create(
        name="Test Policy",
        description="Test Description",
        version="1.0",
        state="draft",
        created_by=admin_user
    )


@pytest.fixture
def sample_training(db):
    """Create sample training module."""
    return TrainingModule.objects.create(
        title="Test Training",
        description="Test Description",
        content="Test Content",
        duration_minutes=30
    )


@pytest.fixture
def sample_quiz(db, sample_training):
    """Create sample quiz."""
    return Quiz.objects.create(
        training_module=sample_training,
        title="Test Quiz",
        description="Test Description",
        pass_percentage=70
    )


class TestAuthentication:
    """Test API authentication."""
    
    def test_obtain_token(self, api_client, regular_user):
        """Test JWT token generation."""
        url = reverse('api:token_obtain_pair')
        response = api_client.post(url, {
            'username': 'user',
            'password': 'user123'
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
    
    def test_refresh_token(self, api_client, user_token, regular_user):
        """Test JWT token refresh."""
        refresh = RefreshToken.for_user(regular_user)
        url = reverse('api:token_refresh')
        response = api_client.post(url, {
            'refresh': str(refresh)
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
    
    def test_unauthenticated_access(self, api_client):
        """Test that unauthenticated requests are rejected."""
        url = reverse('api:user-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPolicyAPI:
    """Test policy API endpoints."""
    
    def test_list_policies(self, api_client, user_token, sample_policy):
        """Test listing policies."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:policy-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
    
    def test_get_policy_detail(self, api_client, user_token, sample_policy):
        """Test getting policy details."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:policy-detail', args=[sample_policy.id])
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == sample_policy.name
    
    def test_create_policy_admin_only(self, api_client, admin_token, admin_user):
        """Test that only admins can create policies."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_token}')
        url = reverse('api:policy-list')
        response = api_client.post(url, {
            'name': 'New Policy',
            'description': 'New Description',
            'version': '1.0',
            'state': 'draft'
        })
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Policy.objects.filter(name='New Policy').exists()
    
    def test_approve_policy(self, api_client, admin_token, sample_policy):
        """Test policy approval action."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_token}')
        url = reverse('api:policy-approve', args=[sample_policy.id])
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        sample_policy.refresh_from_db()
        assert sample_policy.state == 'approved'


class TestViolationAPI:
    """Test violation API endpoints."""
    
    def test_list_violations(self, api_client, user_token, sample_policy, regular_user):
        """Test listing violations."""
        # Create a violation
        Violation.objects.create(
            user=regular_user,
            policy=sample_policy,
            severity='medium',
            description='Test violation',
            detected_by='manual'
        )
        
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:violation-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) > 0
    
    def test_violation_statistics(self, api_client, admin_token):
        """Test violation statistics endpoint."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_token}')
        url = reverse('api:violation-statistics')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'total' in response.data
        assert 'by_severity' in response.data


class TestTrainingAPI:
    """Test training API endpoints."""
    
    def test_list_training_modules(self, api_client, user_token, sample_training):
        """Test listing training modules."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:trainingmodule-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) > 0
    
    def test_start_training(self, api_client, user_token, sample_training, regular_user):
        """Test starting a training module."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:trainingmodule-start', args=[sample_training.id])
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert TrainingProgress.objects.filter(
            user=regular_user,
            training_module=sample_training
        ).exists()
    
    def test_complete_training(self, api_client, user_token, sample_training, regular_user):
        """Test completing a training module."""
        # First start the training
        progress = TrainingProgress.objects.create(
            user=regular_user,
            training_module=sample_training
        )
        
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:trainingmodule-complete', args=[sample_training.id])
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        progress.refresh_from_db()
        assert progress.completed_at is not None


class TestQuizAPI:
    """Test quiz API endpoints."""
    
    def test_list_quizzes(self, api_client, user_token, sample_quiz):
        """Test listing quizzes."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:quiz-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) > 0
    
    def test_start_quiz(self, api_client, user_token, sample_quiz, regular_user):
        """Test starting a quiz."""
        # Add some questions first
        Question.objects.create(
            quiz=sample_quiz,
            text="Test question?",
            choice_a="A",
            choice_b="B",
            choice_c="C",
            choice_d="D",
            correct_answer="A"
        )
        
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:quiz-start', args=[sample_quiz.id])
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert QuizAttempt.objects.filter(
            user=regular_user,
            quiz=sample_quiz
        ).exists()


class TestCaseStudyAPI:
    """Test case study API endpoints."""
    
    def test_list_case_studies(self, api_client, user_token):
        """Test listing case studies."""
        # Create a case study
        CaseStudy.objects.create(
            title="Test Case Study",
            summary="Test Summary",
            content="Test Content",
            lessons_learned="Test Lessons",
            incident_type="breach"
        )
        
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:casestudy-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) > 0


class TestFiltering:
    """Test API filtering and search."""
    
    def test_filter_policies_by_state(self, api_client, user_token, sample_policy):
        """Test filtering policies by state."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:policy-list')
        response = api_client.get(url, {'state': 'draft'})
        
        assert response.status_code == status.HTTP_200_OK
        for policy in response.data['results']:
            assert policy['state'] == 'draft'
    
    def test_search_training_modules(self, api_client, user_token, sample_training):
        """Test searching training modules."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:trainingmodule-list')
        response = api_client.get(url, {'search': 'Test'})
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) > 0


class TestPermissions:
    """Test API permissions."""
    
    def test_regular_user_cannot_create_policy(self, api_client, user_token):
        """Test that regular users cannot create policies."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:policy-list')
        response = api_client.post(url, {
            'name': 'New Policy',
            'description': 'Description',
            'version': '1.0',
            'state': 'draft'
        })
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_user_can_view_own_violations(self, api_client, user_token, regular_user, sample_policy):
        """Test that users can view their own violations."""
        violation = Violation.objects.create(
            user=regular_user,
            policy=sample_policy,
            severity='low',
            description='Test',
            detected_by='manual'
        )
        
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')
        url = reverse('api:violation-detail', args=[violation.id])
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
