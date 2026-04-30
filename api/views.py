"""API ViewSets for REST endpoints."""
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Count, Q, Avg

from policy.models import (
    Policy, Control, Rule, Violation, HumanLayerEvent,
    PolicyHistory, DetectionMetric
)
from training.models import TrainingModule, TrainingProgress
from quizzes.models import Quiz, Question, Choice, QuizAttempt, QuizResponse
from case_studies.models import CaseStudy

from .serializers import (
    UserSerializer, PolicySerializer, ControlSerializer, RuleSerializer,
    ViolationSerializer, HumanLayerEventSerializer, PolicyHistorySerializer,
    DetectionMetricSerializer, TrainingModuleSerializer,
    TrainingProgressSerializer, QuizSerializer, QuestionSerializer,
    QuizAttemptSerializer, QuizResponseSerializer, CaseStudySerializer
)
from .permissions import IsAdminOrReadOnly, IsOwnerOrAdmin

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """API endpoint for users."""
    
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined']
    ordering = ['-date_joined']
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user profile."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get user statistics."""
        user = self.get_object()
        
        stats = {
            'training_completed': TrainingProgress.objects.filter(
                user=user, completed=True
            ).count(),
            'quizzes_passed': QuizAttempt.objects.filter(
                user=user, passed=True
            ).count(),
            'violations': Violation.objects.filter(user=user).count(),
            'last_login': user.last_login,
        }
        return Response(stats)


class PolicyViewSet(viewsets.ModelViewSet):
    """API endpoint for policies."""
    
    queryset = Policy.objects.all()
    serializer_class = PolicySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['state', 'version']
    search_fields = ['name', 'description']
    ordering_fields = ['effective_date', 'created_at']
    ordering = ['-effective_date']
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a policy."""
        policy = self.get_object()
        if policy.state != 'draft':
            return Response(
                {'error': 'Only draft policies can be approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        policy.approve(request.user)
        return Response({'status': 'approved'})
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a policy."""
        policy = self.get_object()
        if policy.state != 'approved':
            return Response(
                {'error': 'Only approved policies can be published'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        policy.publish(request.user)
        return Response({'status': 'published'})
    
    @action(detail=True, methods=['get'])
    def controls(self, request, pk=None):
        """Get all controls for a policy."""
        policy = self.get_object()
        controls = policy.controls.all()
        serializer = ControlSerializer(controls, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def violations(self, request, pk=None):
        """Get all violations for a policy."""
        policy = self.get_object()
        violations = Violation.objects.filter(rule__control__policy=policy)
        serializer = ViolationSerializer(violations, many=True)
        return Response(serializer.data)


class ControlViewSet(viewsets.ModelViewSet):
    """API endpoint for controls."""
    
    queryset = Control.objects.all()
    serializer_class = ControlSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['policy']
    search_fields = ['name', 'description', 'control_id']
    
    @action(detail=True, methods=['get'])
    def rules(self, request, pk=None):
        """Get all rules for a control."""
        control = self.get_object()
        rules = control.rules.all()
        serializer = RuleSerializer(rules, many=True)
        return Response(serializer.data)


class RuleViewSet(viewsets.ModelViewSet):
    """API endpoint for rules."""
    
    queryset = Rule.objects.all()
    serializer_class = RuleSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['control', 'severity']
    search_fields = ['description']
    
    @action(detail=True, methods=['get'])
    def violations(self, request, pk=None):
        """Get all violations for a rule."""
        rule = self.get_object()
        violations = rule.violations.all()
        serializer = ViolationSerializer(violations, many=True)
        return Response(serializer.data)


class ViolationViewSet(viewsets.ModelViewSet):
    """API endpoint for violations."""
    
    queryset = Violation.objects.select_related('rule', 'user').all()
    serializer_class = ViolationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['user', 'severity', 'status']
    search_fields = ['rule__description', 'evidence']
    ordering_fields = ['detected_at', 'severity']
    ordering = ['-detected_at']
    
    def get_queryset(self):
        """Filter violations based on user role."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Acknowledge a violation."""
        violation = self.get_object()
        notes = request.data.get('notes', '')
        
        violation.status = 'acknowledged'
        violation.acknowledged_at = timezone.now()
        violation.acknowledged_by = request.user
        violation.notes = notes
        violation.save()
        
        return Response({'status': 'acknowledged'})
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get violation statistics."""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'by_severity': {
                'critical': queryset.filter(severity='critical').count(),
                'high': queryset.filter(severity='high').count(),
                'medium': queryset.filter(severity='medium').count(),
                'low': queryset.filter(severity='low').count(),
            },
            'by_status': {
                'open': queryset.filter(status='open').count(),
                'acknowledged': queryset.filter(status='acknowledged').count(),
                'resolved': queryset.filter(status='resolved').count(),
            },
            'last_24h': queryset.filter(
                detected_at__gte=timezone.now() - timezone.timedelta(hours=24)
            ).count(),
        }
        return Response(stats)


class HumanLayerEventViewSet(viewsets.ModelViewSet):
    """API endpoint for human layer events."""
    
    queryset = HumanLayerEvent.objects.select_related('user').all()
    serializer_class = HumanLayerEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['user', 'event_type', 'success', 'processed']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']
    
    def get_queryset(self):
        """Filter events based on user role."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset


class PolicyHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for policy history (read-only)."""
    
    queryset = PolicyHistory.objects.select_related('policy', 'changed_by').all()
    serializer_class = PolicyHistorySerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['policy', 'change_type']
    ordering_fields = ['changed_at']
    ordering = ['-changed_at']


class DetectionMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for detection metrics (read-only)."""
    
    queryset = DetectionMetric.objects.select_related('experiment').all()
    serializer_class = DetectionMetricSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['experiment']
    ordering_fields = ['timestamp', 'f1_score', 'accuracy']
    ordering = ['-timestamp']


class TrainingModuleViewSet(viewsets.ModelViewSet):
    """API endpoint for training modules."""
    
    queryset = TrainingModule.objects.all()
    serializer_class = TrainingModuleSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'content']
    ordering_fields = ['order']
    ordering = ['order']
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a training module."""
        module = self.get_object()
        progress, created = TrainingProgress.objects.get_or_create(
            user=request.user,
            module=module
        )
        
        return Response({
            'status': 'started' if created else 'resumed',
            'progress_id': progress.id
        })
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark training module as complete."""
        module = self.get_object()
        progress, _ = TrainingProgress.objects.get_or_create(
            user=request.user,
            module=module
        )
        
        progress.mark_complete()
        
        return Response({'status': 'completed'})


class TrainingProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for user progress."""
    
    queryset = TrainingProgress.objects.select_related('user', 'module').all()
    serializer_class = TrainingProgressSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['user', 'module', 'completed']
    ordering_fields = ['started_at', 'completed_at']
    ordering = ['-started_at']
    
    def get_queryset(self):
        """Filter progress based on user role."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset


class QuizViewSet(viewsets.ModelViewSet):
    """API endpoint for quizzes."""
    
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    @action(detail=True, methods=['get'])
    def questions(self, request, pk=None):
        """Get all questions for a quiz."""
        quiz = self.get_object()
        questions = quiz.questions.all()
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a quiz attempt."""
        quiz = self.get_object()
        
        # Check max attempts
        attempts_count = QuizAttempt.objects.filter(
            user=request.user, quiz=quiz
        ).count()
        
        if quiz.max_attempts and attempts_count >= quiz.max_attempts:
            return Response(
                {'error': 'Maximum attempts reached'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        attempt = QuizAttempt.objects.create(
            user=request.user,
            quiz=quiz
        )
        
        return Response({
            'attempt_id': attempt.id,
            'started_at': attempt.started_at
        })


class QuizAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for quiz attempts."""
    
    queryset = QuizAttempt.objects.select_related('quiz', 'user').all()
    serializer_class = QuizAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['user', 'quiz', 'passed']
    ordering_fields = ['started_at', 'score']
    ordering = ['-started_at']
    
    def get_queryset(self):
        """Filter attempts based on user role."""
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset


class CaseStudyViewSet(viewsets.ModelViewSet):
    """API endpoint for case studies."""
    
    queryset = CaseStudy.objects.filter(published=True)
    serializer_class = CaseStudySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    filterset_fields = ['category']
    search_fields = ['title', 'summary', 'content']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
