"""API Serializers for all models."""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from policy.models import (
    Policy, Control, Rule, Violation, HumanLayerEvent,
    PolicyHistory, DetectionMetric
)
from training.models import TrainingModule, TrainingProgress
from quizzes.models import Quiz, Question, Choice, QuizAttempt, QuizResponse
from case_studies.models import CaseStudy

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """User serializer with role information."""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 
                  'is_staff', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class PolicySerializer(serializers.ModelSerializer):
    """Policy serializer with nested controls."""
    
    controls_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Policy
        fields = ['id', 'name', 'description', 'version', 'effective_date',
                  'state', 'controls_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_controls_count(self, obj):
        return obj.controls.count()


class ControlSerializer(serializers.ModelSerializer):
    """Control serializer."""
    
    rules_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Control
        fields = ['id', 'policy', 'name', 'description', 'control_id',
                  'rules_count', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_rules_count(self, obj):
        return obj.rules.count()


class RuleSerializer(serializers.ModelSerializer):
    """Rule serializer."""
    
    class Meta:
        model = Rule
        fields = ['id', 'control', 'description', 'left_operand', 
                  'operator', 'right_value', 'threshold', 'window_days',
                  'severity', 'created_at']
        read_only_fields = ['id', 'created_at']


class ViolationSerializer(serializers.ModelSerializer):
    """Violation serializer with nested data."""
    
    rule_description = serializers.CharField(source='rule.description', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = Violation
        fields = ['id', 'rule', 'rule_description', 'user', 'user_username',
                  'detected_at', 'severity', 'status', 'evidence', 
                  'acknowledged_at', 'acknowledged_by', 'notes']
        read_only_fields = ['id', 'detected_at']


class HumanLayerEventSerializer(serializers.ModelSerializer):
    """Human layer event serializer."""
    
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = HumanLayerEvent
        fields = ['id', 'user', 'user_username', 'event_type', 'timestamp',
                  'source', 'success', 'detail', 'summary', 'ip_address',
                  'user_agent', 'processed']
        read_only_fields = ['id', 'timestamp', 'processed']


class PolicyHistorySerializer(serializers.ModelSerializer):
    """Policy history serializer."""
    
    class Meta:
        model = PolicyHistory
        fields = ['id', 'policy', 'version', 'changed_by', 'change_type',
                  'changed_at', 'diff', 'signature', 'immutable_hash']
        read_only_fields = ['id', 'changed_at', 'signature', 'immutable_hash']


class DetectionMetricSerializer(serializers.ModelSerializer):
    """Detection metric serializer."""
    
    class Meta:
        model = DetectionMetric
        fields = ['id', 'experiment', 'true_positives', 'false_positives',
                  'true_negatives', 'false_negatives', 'precision', 
                  'recall', 'f1_score', 'accuracy', 'timestamp']
        read_only_fields = ['id', 'timestamp', 'precision', 'recall', 
                           'f1_score', 'accuracy']


class TrainingModuleSerializer(serializers.ModelSerializer):
    """Training module serializer."""
    
    completion_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = TrainingModule
        fields = ['id', 'title', 'slug', 'description', 'content',
                  'duration_minutes', 'order', 'is_published', 
                  'completion_rate', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']
    
    def get_completion_rate(self, obj):
        total = User.objects.filter(is_active=True).count()
        if total == 0:
            return 0
        completed = obj.trainingprogress_set.filter(completed=True).count()
        return round((completed / total) * 100, 2)


class TrainingProgressSerializer(serializers.ModelSerializer):
    """User progress serializer."""
    
    module_title = serializers.CharField(source='module.title', read_only=True)
    
    class Meta:
        model = TrainingProgress
        fields = ['id', 'user', 'module', 'module_title', 'started_at',
                  'completed', 'completed_at', 'progress_percentage']
        read_only_fields = ['id', 'started_at', 'completed_at']


class QuizSerializer(serializers.ModelSerializer):
    """Quiz serializer."""
    
    questions_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Quiz
        fields = ['id', 'title', 'slug', 'description', 'passing_score',
                  'time_limit_minutes', 'max_attempts', 'is_published',
                  'questions_count', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']
    
    def get_questions_count(self, obj):
        return obj.questions.count()


class QuestionSerializer(serializers.ModelSerializer):
    """Question serializer."""
    
    class Meta:
        model = Question
        fields = ['id', 'quiz', 'text', 'question_type', 'choices',
                  'correct_answer', 'explanation', 'points', 'order']
        read_only_fields = ['id']


class QuizAttemptSerializer(serializers.ModelSerializer):
    """Quiz attempt serializer."""
    
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = QuizAttempt
        fields = ['id', 'quiz', 'quiz_title', 'user', 'user_username',
                  'started_at', 'completed_at', 'score', 'passed',
                  'time_taken_seconds']
        read_only_fields = ['id', 'started_at', 'completed_at', 'score', 
                           'passed', 'time_taken_seconds']


class QuizResponseSerializer(serializers.ModelSerializer):
    """Answer serializer."""
    
    class Meta:
        model = QuizResponse
        fields = ['id', 'attempt', 'question', 'selected_answer',
                  'is_correct', 'points_earned']
        read_only_fields = ['id', 'is_correct', 'points_earned']


class CaseStudySerializer(serializers.ModelSerializer):
    """Case study serializer."""
    
    class Meta:
        model = CaseStudy
        fields = ['id', 'title', 'slug', 'category', 'summary', 'content',
                  'lessons_learned', 'is_published', 'created_at', 'updated_at']
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
