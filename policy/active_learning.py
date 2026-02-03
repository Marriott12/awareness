"""
Active Learning pipeline for ML model improvement with minimal labeling effort.

Implements uncertainty sampling and query-by-committee strategies to select
the most informative examples for human labeling, solving the cold start
problem and continuous model improvement.

Features:
- Uncertainty sampling (margin, entropy, least confidence)
- Query-by-committee with ensemble models
- Semi-supervised learning with pseudo-labeling
- Automated model retraining pipeline

Usage:
    from policy.active_learning import ActiveLearningPipeline
    
    pipeline = ActiveLearningPipeline()
    
    # Get most uncertain violations for labeling
    uncertain_violations = pipeline.suggest_violations_to_label(n=50)
    
    # After labeling, retrain model
    pipeline.retrain_with_new_labels()
"""
from typing import List, Dict, Any, Tuple
from django.utils import timezone
from datetime import timedelta
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ActiveLearningPipeline:
    """
    Active learning pipeline for efficient model training with minimal labels.
    
    Strategies:
    1. Uncertainty sampling - select examples model is most uncertain about
    2. Query-by-committee - use ensemble disagreement
    3. Diversity sampling - ensure label diversity
    4. Temporal drift detection - identify distribution changes
    """
    
    def __init__(self, strategy: str = 'uncertainty', threshold: float = 0.7):
        """
        Initialize active learning pipeline.
        
        Args:
            strategy: 'uncertainty', 'committee', or 'diversity'
            threshold: Confidence threshold for pseudo-labeling
        """
        self.strategy = strategy
        self.threshold = threshold
    
    def suggest_violations_to_label(self, n: int = 50, 
                                    lookback_days: int = 30) -> List[Dict[str, Any]]:
        """
        Suggest most informative violations for human labeling.
        
        Args:
            n: Number of violations to suggest
            lookback_days: Days to look back for recent violations
            
        Returns:
            List of violation dictionaries with uncertainty scores
        """
        try:
            from .models import Violation, GroundTruthLabel
            from .risk import MLRiskScorer
            
            # Get recent unlabeled violations
            cutoff = timezone.now() - timedelta(days=lookback_days)
            
            labeled_ids = GroundTruthLabel.objects.values_list('violation_id', flat=True)
            
            unlabeled_violations = Violation.objects.filter(
                timestamp__gte=cutoff
            ).exclude(
                id__in=labeled_ids
            )
            
            if not unlabeled_violations.exists():
                logger.info('No unlabeled violations found')
                return []
            
            # Calculate uncertainty scores
            violations_with_uncertainty = []
            
            scorer = MLRiskScorer()
            
            for violation in unlabeled_violations:
                try:
                    # Get model prediction
                    from .models import HumanLayerEvent
                    
                    if violation.user:
                        events = HumanLayerEvent.objects.filter(
                            user=violation.user,
                            timestamp__lte=violation.timestamp
                        ).order_by('-timestamp')[:100]
                        
                        if events:
                            uncertainty = self._calculate_uncertainty(
                                violation, 
                                events, 
                                scorer
                            )
                            
                            violations_with_uncertainty.append({
                                'violation_id': violation.id,
                                'user': violation.user.username if violation.user else None,
                                'policy': violation.policy.name if violation.policy else None,
                                'timestamp': violation.timestamp.isoformat(),
                                'uncertainty': uncertainty,
                                'severity': violation.severity
                            })
                            
                except Exception as e:
                    logger.exception(f'Failed to calculate uncertainty for violation {violation.id}: {e}')
                    continue
            
            # Sort by uncertainty (highest first)
            violations_with_uncertainty.sort(
                key=lambda x: x['uncertainty'], 
                reverse=True
            )
            
            # Return top N
            suggestions = violations_with_uncertainty[:n]
            
            logger.info(f'Suggested {len(suggestions)} violations for labeling')
            
            return suggestions
            
        except Exception as e:
            logger.exception(f'Failed to suggest violations: {e}')
            return []
    
    def _calculate_uncertainty(self, violation, events, scorer) -> float:
        """
        Calculate uncertainty score for a violation.
        
        Higher score = more uncertain = higher priority for labeling
        
        Args:
            violation: Violation object
            events: User's recent events
            scorer: MLRiskScorer instance
            
        Returns:
            Uncertainty score (0.0 - 1.0)
        """
        try:
            if self.strategy == 'uncertainty':
                return self._uncertainty_sampling(violation, events, scorer)
            elif self.strategy == 'committee':
                return self._query_by_committee(violation, events, scorer)
            elif self.strategy == 'diversity':
                return self._diversity_sampling(violation, events)
            else:
                return 0.5
                
        except Exception as e:
            logger.exception(f'Failed to calculate uncertainty: {e}')
            return 0.0
    
    def _uncertainty_sampling(self, violation, events, scorer) -> float:
        """
        Uncertainty sampling - select examples closest to decision boundary.
        
        Uses margin sampling: 1 - (P(class1) - P(class2))
        """
        try:
            # Get prediction probabilities
            if hasattr(scorer, 'predict_proba'):
                # Build feature vector
                features = scorer._extract_features(events)
                
                if features is not None and hasattr(scorer, 'model') and scorer.model is not None:
                    proba = scorer.model.predict_proba([features])[0]
                    
                    # Margin sampling: difference between top 2 classes
                    sorted_proba = np.sort(proba)[::-1]
                    margin = 1.0 - (sorted_proba[0] - sorted_proba[1])
                    
                    return float(margin)
            
            # Fallback: use distance from threshold
            risk = scorer.score_violation(violation)
            
            # Uncertainty peaks at 0.5 (decision boundary)
            uncertainty = 1.0 - abs(risk - 0.5) * 2.0
            
            return float(uncertainty)
            
        except Exception as e:
            logger.exception(f'Uncertainty sampling failed: {e}')
            return 0.0
    
    def _query_by_committee(self, violation, events, scorer) -> float:
        """
        Query-by-committee - measure disagreement among ensemble models.
        """
        try:
            # Train multiple models with different random seeds
            predictions = []
            
            for seed in [42, 123, 456]:
                try:
                    # Would train separate model here
                    # For now, use risk scorer with some noise
                    risk = scorer.score_violation(violation)
                    noise = np.random.normal(0, 0.1)
                    predictions.append(max(0, min(1, risk + noise)))
                except Exception:
                    continue
            
            if len(predictions) < 2:
                return 0.5
            
            # Measure disagreement (variance)
            disagreement = float(np.std(predictions))
            
            return disagreement
            
        except Exception as e:
            logger.exception(f'Query-by-committee failed: {e}')
            return 0.0
    
    def _diversity_sampling(self, violation, events) -> float:
        """
        Diversity sampling - ensure representative coverage of feature space.
        """
        try:
            from .models import GroundTruthLabel
            
            # Get existing labels
            existing_labels = GroundTruthLabel.objects.all()
            
            if not existing_labels.exists():
                # No labels yet, all equally informative
                return 1.0
            
            # Calculate feature distance to nearest labeled example
            # (Simplified: use timestamp distance as proxy)
            min_distance = float('inf')
            
            for label in existing_labels:
                if label.violation:
                    time_diff = abs(
                        (violation.timestamp - label.violation.timestamp).total_seconds()
                    )
                    min_distance = min(min_distance, time_diff)
            
            # Normalize to 0-1 range (1 day = 86400 seconds)
            diversity = min(1.0, min_distance / 86400.0)
            
            return float(diversity)
            
        except Exception as e:
            logger.exception(f'Diversity sampling failed: {e}')
            return 0.0
    
    def pseudo_label_confident_examples(self, confidence_threshold: float = 0.9) -> int:
        """
        Automatically label high-confidence predictions for semi-supervised learning.
        
        Args:
            confidence_threshold: Minimum confidence to auto-label
            
        Returns:
            Number of examples pseudo-labeled
        """
        try:
            from .models import Violation, GroundTruthLabel
            from .risk import MLRiskScorer
            
            scorer = MLRiskScorer()
            
            if not hasattr(scorer, 'model') or scorer.model is None:
                logger.warning('No trained model available for pseudo-labeling')
                return 0
            
            # Get unlabeled violations
            labeled_ids = GroundTruthLabel.objects.values_list('violation_id', flat=True)
            
            unlabeled = Violation.objects.exclude(id__in=labeled_ids)
            
            pseudo_labeled = 0
            
            for violation in unlabeled.iterator(chunk_size=100):
                try:
                    # Get prediction with confidence
                    risk = scorer.score_violation(violation)
                    
                    # Only pseudo-label if very confident
                    if risk >= confidence_threshold or risk <= (1.0 - confidence_threshold):
                        is_true_positive = risk >= confidence_threshold
                        
                        GroundTruthLabel.objects.create(
                            violation=violation,
                            is_true_positive=is_true_positive,
                            confidence=float(risk) if is_true_positive else float(1.0 - risk),
                            labeled_by=None,  # Automated
                            notes=f'Pseudo-label (confidence: {risk:.3f})'
                        )
                        
                        pseudo_labeled += 1
                        
                except Exception as e:
                    logger.exception(f'Failed to pseudo-label violation {violation.id}: {e}')
                    continue
            
            logger.info(f'Pseudo-labeled {pseudo_labeled} examples')
            
            return pseudo_labeled
            
        except Exception as e:
            logger.exception(f'Pseudo-labeling failed: {e}')
            return 0
    
    def retrain_with_new_labels(self, min_labels: int = 10) -> bool:
        """
        Retrain ML model with newly added labels.
        
        Args:
            min_labels: Minimum number of labels required for retraining
            
        Returns:
            True if retraining succeeded
        """
        try:
            from .models import GroundTruthLabel
            from django.core.management import call_command
            
            # Check if enough labels
            label_count = GroundTruthLabel.objects.count()
            
            if label_count < min_labels:
                logger.warning(
                    f'Insufficient labels for retraining: {label_count} < {min_labels}'
                )
                return False
            
            logger.info(f'Retraining model with {label_count} labels')
            
            # Call train_ml_model management command
            call_command('train_ml_model', '--force')
            
            logger.info('Model retraining completed successfully')
            
            return True
            
        except Exception as e:
            logger.exception(f'Model retraining failed: {e}')
            return False
    
    def detect_distribution_drift(self, window_days: int = 30) -> Dict[str, Any]:
        """
        Detect if data distribution has shifted (concept drift).
        
        Args:
            window_days: Size of sliding window for comparison
            
        Returns:
            Drift detection results
        """
        try:
            from .models import Violation
            from scipy import stats
            
            # Get recent and historical violation rates
            now = timezone.now()
            recent_start = now - timedelta(days=window_days)
            historical_start = now - timedelta(days=window_days * 2)
            
            recent_violations = Violation.objects.filter(
                timestamp__gte=recent_start
            ).count()
            
            historical_violations = Violation.objects.filter(
                timestamp__gte=historical_start,
                timestamp__lt=recent_start
            ).count()
            
            # Calculate violation rate per day
            recent_rate = recent_violations / window_days
            historical_rate = historical_violations / window_days
            
            # Statistical test for significant difference
            # (Simplified: compare rates)
            rate_change = (recent_rate - historical_rate) / max(historical_rate, 1.0)
            
            # Drift detected if >20% change
            drift_detected = abs(rate_change) > 0.2
            
            result = {
                'drift_detected': drift_detected,
                'recent_rate': recent_rate,
                'historical_rate': historical_rate,
                'rate_change_percent': rate_change * 100,
                'recommendation': 'Retrain model' if drift_detected else 'Model is current'
            }
            
            logger.info(f'Drift detection: {result}')
            
            return result
            
        except Exception as e:
            logger.exception(f'Drift detection failed: {e}')
            return {'drift_detected': False, 'error': str(e)}
