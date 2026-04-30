"""Elasticsearch document definitions for full-text search.

Defines searchable documents for policies, training modules, and case studies.
"""
from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from policy.models import Policy, Control, Rule
from training.models import TrainingModule
from case_studies.models import CaseStudy


@registry.register_document
class PolicyDocument(Document):
    """Elasticsearch document for Policy model."""
    
    # Define searchable fields
    name = fields.TextField(
        attr='name',
        fields={
            'raw': fields.KeywordField(),
            'suggest': fields.CompletionField(),
        }
    )
    description = fields.TextField(attr='description')
    version = fields.KeywordField(attr='version')
    state = fields.KeywordField(attr='state')
    created_at = fields.DateField(attr='created_at')
    
    # Related fields
    created_by = fields.TextField(
        attr='created_by.username',
        fields={'raw': fields.KeywordField()}
    )
    
    class Index:
        name = 'policies'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
        }
    
    class Django:
        model = Policy
        fields = []
        related_models = []


@registry.register_document
class ControlDocument(Document):
    """Elasticsearch document for Control model."""
    
    name = fields.TextField(
        attr='name',
        fields={
            'raw': fields.KeywordField(),
            'suggest': fields.CompletionField(),
        }
    )
    description = fields.TextField(attr='description')
    category = fields.KeywordField(attr='category')
    
    # Related policy
    policy_name = fields.TextField(
        attr='policy.name',
        fields={'raw': fields.KeywordField()}
    )
    
    class Index:
        name = 'controls'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
        }
    
    class Django:
        model = Control
        fields = []
        related_models = [Policy]


@registry.register_document
class TrainingModuleDocument(Document):
    """Elasticsearch document for TrainingModule model."""
    
    title = fields.TextField(
        attr='title',
        fields={
            'raw': fields.KeywordField(),
            'suggest': fields.CompletionField(),
        }
    )
    description = fields.TextField(attr='description')
    content = fields.TextField(attr='content')
    duration_minutes = fields.IntegerField(attr='duration_minutes')
    created_at = fields.DateField(attr='created_at')
    
    class Index:
        name = 'training_modules'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
        }
    
    class Django:
        model = TrainingModule
        fields = []


@registry.register_document
class CaseStudyDocument(Document):
    """Elasticsearch document for CaseStudy model."""
    
    title = fields.TextField(
        attr='title',
        fields={
            'raw': fields.KeywordField(),
            'suggest': fields.CompletionField(),
        }
    )
    summary = fields.TextField(attr='summary')
    content = fields.TextField(attr='content')
    lessons_learned = fields.TextField(attr='lessons_learned')
    incident_type = fields.KeywordField(attr='incident_type')
    severity = fields.KeywordField(attr='severity')
    created_at = fields.DateField(attr='created_at')
    
    class Index:
        name = 'case_studies'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
        }
    
    class Django:
        model = CaseStudy
        fields = []
