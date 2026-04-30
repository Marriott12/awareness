"""Full-text search views using Elasticsearch."""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Try to import Elasticsearch components - gracefully handle if not available
try:
    from elasticsearch_dsl import Q
    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    logger.warning('Elasticsearch packages not available. Install with: pip install -r requirements-optional.txt')
    ELASTICSEARCH_AVAILABLE = False
    Q = None

# Check if Elasticsearch is configured
ELASTICSEARCH_ENABLED = ELASTICSEARCH_AVAILABLE and bool(getattr(settings, 'ELASTICSEARCH_DSL', None))

if ELASTICSEARCH_ENABLED:
    try:
        from policy.search_indexes import (
            PolicyDocument, ControlDocument,
            TrainingModuleDocument, CaseStudyDocument
        )
    except ImportError:
        logger.warning('Elasticsearch documents not available')
        ELASTICSEARCH_ENABLED = False
        ELASTICSEARCH_ENABLED = False


@login_required
def global_search(request):
    """
    Global search across all content types.
    
    Searches policies, controls, training modules, and case studies.
    """
    query = request.GET.get('q', '').strip()
    
    if not ELASTICSEARCH_ENABLED:
        return render(request, 'policy/search_disabled.html', {
            'message': 'Full-text search is not enabled on this server.'
        })
    
    if not query:
        return render(request, 'policy/search_results.html', {
            'query': '',
            'results': {
                'policies': [],
                'controls': [],
                'training': [],
                'case_studies': [],
            },
            'total': 0,
        })
    
    try:
        # Build multi-match query
        search_query = Q('multi_match', query=query, fields=['*'])
        
        # Search policies
        policy_search = PolicyDocument.search().query(search_query)[:10]
        policies = policy_search.execute()
        
        # Search controls
        control_search = ControlDocument.search().query(search_query)[:10]
        controls = control_search.execute()
        
        # Search training modules
        training_search = TrainingModuleDocument.search().query(search_query)[:10]
        training = training_search.execute()
        
        # Search case studies
        case_study_search = CaseStudyDocument.search().query(search_query)[:10]
        case_studies = case_study_search.execute()
        
        # Calculate total results
        total = (
            policies.hits.total.value +
            controls.hits.total.value +
            training.hits.total.value +
            case_studies.hits.total.value
        )
        
        return render(request, 'policy/search_results.html', {
            'query': query,
            'results': {
                'policies': policies,
                'controls': controls,
                'training': training,
                'case_studies': case_studies,
            },
            'total': total,
        })
        
    except Exception as e:
        logger.error(f'Search error: {e}')
        return render(request, 'policy/search_error.html', {
            'error': str(e)
        })


@login_required
def search_suggestions(request):
    """
    Get autocomplete suggestions for search.
    
    Returns JSON with suggestions from all content types.
    """
    from django.http import JsonResponse
    
    query = request.GET.get('q', '').strip()
    
    if not ELASTICSEARCH_ENABLED or not query:
        return JsonResponse({'suggestions': []})
    
    try:
        suggestions = []
        
        # Get suggestions from each document type
        for DocumentClass in [PolicyDocument, ControlDocument, 
                              TrainingModuleDocument, CaseStudyDocument]:
            search = DocumentClass.search().suggest(
                'suggestions',
                query,
                completion={'field': 'name.suggest'}
            )
            response = search.execute()
            
            if hasattr(response.suggest, 'suggestions'):
                for option in response.suggest.suggestions[0].options[:5]:
                    suggestions.append({
                        'text': option.text,
                        'score': option._score,
                    })
        
        # Sort by score and remove duplicates
        suggestions = sorted(suggestions, key=lambda x: x['score'], reverse=True)
        unique_suggestions = []
        seen = set()
        
        for s in suggestions:
            if s['text'] not in seen:
                unique_suggestions.append(s['text'])
                seen.add(s['text'])
        
        return JsonResponse({
            'suggestions': unique_suggestions[:10]
        })
        
    except Exception as e:
        logger.error(f'Suggestion error: {e}')
        return JsonResponse({'suggestions': []})


@login_required
def search_policies(request):
    """Search policies only."""
    query = request.GET.get('q', '').strip()
    
    if not ELASTICSEARCH_ENABLED:
        from policy.models import Policy
        # Fallback to database search
        if query:
            policies = Policy.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )[:20]
        else:
            policies = Policy.objects.all()[:20]
        
        return render(request, 'policy/policy_search.html', {
            'query': query,
            'policies': policies,
        })
    
    try:
        search_query = Q('multi_match', query=query, fields=['name', 'description'])
        search = PolicyDocument.search().query(search_query)[:20]
        policies = search.execute()
        
        return render(request, 'policy/policy_search.html', {
            'query': query,
            'policies': policies,
        })
        
    except Exception as e:
        logger.error(f'Policy search error: {e}')
        # Fallback to database
        from policy.models import Policy
        policies = Policy.objects.filter(name__icontains=query)[:20]
        return render(request, 'policy/policy_search.html', {
            'query': query,
            'policies': policies,
        })
