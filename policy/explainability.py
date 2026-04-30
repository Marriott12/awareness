"""Model Explainability with SHAP and LIME.

Provides interpretable explanations for ML model predictions to support
human decision-making and regulatory compliance.
"""
import logging
from typing import Dict, Any, List, Optional
import numpy as np
from django.core.cache import cache

logger = logging.getLogger(__name__)

try:
    import shap
    import lime
    import lime.lime_tabular
    EXPLAINABILITY_AVAILABLE = True
except ImportError:
    EXPLAINABILITY_AVAILABLE = False
    logger.warning('SHAP/LIME not installed - explainability features disabled')


class ModelExplainer:
    """Provides explanations for ML model predictions using SHAP and LIME."""
    
    def __init__(self, model, feature_names: List[str], training_data: Optional[np.ndarray] = None):
        """
        Initialize model explainer.
        
        Args:
            model: Trained ML model (scikit-learn compatible)
            feature_names: List of feature names
            training_data: Training data for LIME explainer (optional)
        """
        if not EXPLAINABILITY_AVAILABLE:
            raise ImportError('SHAP and LIME required for model explainability')
        
        self.model = model
        self.feature_names = feature_names
        self.training_data = training_data
        
        # Initialize SHAP explainer
        try:
            self.shap_explainer = shap.TreeExplainer(model)
        except Exception as e:
            logger.warning(f'Failed to create SHAP TreeExplainer: {e}. Using KernelExplainer.')
            if training_data is not None:
                self.shap_explainer = shap.KernelExplainer(
                    model.predict_proba,
                    shap.sample(training_data, 100)
                )
            else:
                self.shap_explainer = None
        
        # Initialize LIME explainer
        if training_data is not None:
            self.lime_explainer = lime.lime_tabular.LimeTabularExplainer(
                training_data,
                feature_names=feature_names,
                class_names=['Normal', 'Violation'],
                mode='classification'
            )
        else:
            self.lime_explainer = None
    
    def explain_prediction_shap(self, instance: np.ndarray, top_k: int = 10) -> Dict[str, Any]:
        """
        Generate SHAP explanation for a single prediction.
        
        Args:
            instance: Feature vector for a single instance
            top_k: Number of top features to return
        
        Returns:
            Dictionary containing SHAP values and feature importance
        """
        if self.shap_explainer is None:
            raise ValueError('SHAP explainer not initialized')
        
        # Compute SHAP values
        shap_values = self.shap_explainer.shap_values(instance.reshape(1, -1))
        
        # Handle multi-class output
        if isinstance(shap_values, list):
            shap_values = shap_values[1]  # Use positive class
        
        # Get feature importance
        feature_importance = []
        for i, (feature, value) in enumerate(zip(self.feature_names, shap_values[0])):
            feature_importance.append({
                'feature': feature,
                'shap_value': float(value),
                'feature_value': float(instance[i]),
                'impact': 'increases' if value > 0 else 'decreases'
            })
        
        # Sort by absolute SHAP value
        feature_importance.sort(key=lambda x: abs(x['shap_value']), reverse=True)
        
        return {
            'method': 'SHAP',
            'top_features': feature_importance[:top_k],
            'base_value': float(self.shap_explainer.expected_value) if hasattr(self.shap_explainer, 'expected_value') else 0.0,
        }
    
    def explain_prediction_lime(self, instance: np.ndarray, top_k: int = 10) -> Dict[str, Any]:
        """
        Generate LIME explanation for a single prediction.
        
        Args:
            instance: Feature vector for a single instance
            top_k: Number of top features to return
        
        Returns:
            Dictionary containing LIME explanation
        """
        if self.lime_explainer is None:
            raise ValueError('LIME explainer not initialized')
        
        # Generate explanation
        explanation = self.lime_explainer.explain_instance(
            instance,
            self.model.predict_proba,
            num_features=top_k
        )
        
        # Extract feature weights
        feature_weights = []
        for feature, weight in explanation.as_list():
            feature_weights.append({
                'feature': feature,
                'weight': float(weight),
                'impact': 'increases' if weight > 0 else 'decreases'
            })
        
        return {
            'method': 'LIME',
            'top_features': feature_weights,
            'prediction_probability': float(explanation.predict_proba[1]),
        }
    
    def explain_prediction(self, instance: np.ndarray, method: str = 'both', top_k: int = 10) -> Dict[str, Any]:
        """
        Generate explanation for a prediction using SHAP and/or LIME.
        
        Args:
            instance: Feature vector for a single instance
            method: 'shap', 'lime', or 'both'
            top_k: Number of top features to return
        
        Returns:
            Dictionary containing explanations
        """
        result = {
            'prediction': int(self.model.predict(instance.reshape(1, -1))[0]),
            'probability': float(self.model.predict_proba(instance.reshape(1, -1))[0][1]),
        }
        
        if method in ('shap', 'both') and self.shap_explainer is not None:
            try:
                result['shap_explanation'] = self.explain_prediction_shap(instance, top_k)
            except Exception as e:
                logger.error(f'SHAP explanation failed: {e}')
        
        if method in ('lime', 'both') and self.lime_explainer is not None:
            try:
                result['lime_explanation'] = self.explain_prediction_lime(instance, top_k)
            except Exception as e:
                logger.error(f'LIME explanation failed: {e}')
        
        return result
    
    def get_global_feature_importance(self) -> List[Dict[str, Any]]:
        """
        Get global feature importance from the model.
        
        Returns:
            List of feature importance scores
        """
        importance_scores = []
        
        # Try to get feature importance from model
        if hasattr(self.model, 'feature_importances_'):
            for feature, importance in zip(self.feature_names, self.model.feature_importances_):
                importance_scores.append({
                    'feature': feature,
                    'importance': float(importance)
                })
        
        importance_scores.sort(key=lambda x: x['importance'], reverse=True)
        return importance_scores
    
    def generate_explanation_report(self, instance: np.ndarray, include_global: bool = True) -> str:
        """
        Generate a human-readable explanation report.
        
        Args:
            instance: Feature vector for a single instance
            include_global: Include global feature importance
        
        Returns:
            Formatted explanation text
        """
        explanation = self.explain_prediction(instance)
        
        report = []
        report.append("=" * 80)
        report.append("ML MODEL PREDICTION EXPLANATION")
        report.append("=" * 80)
        report.append("")
        
        # Prediction
        pred_label = "VIOLATION" if explanation['prediction'] == 1 else "NORMAL"
        report.append(f"Prediction: {pred_label}")
        report.append(f"Confidence: {explanation['probability']*100:.1f}%")
        report.append("")
        
        # SHAP explanation
        if 'shap_explanation' in explanation:
            report.append("SHAP Feature Contributions:")
            report.append("-" * 80)
            for feat in explanation['shap_explanation']['top_features'][:5]:
                report.append(f"  • {feat['feature']}: {feat['shap_value']:+.4f} ({feat['impact']} risk)")
            report.append("")
        
        # LIME explanation
        if 'lime_explanation' in explanation:
            report.append("LIME Feature Weights:")
            report.append("-" * 80)
            for feat in explanation['lime_explanation']['top_features'][:5]:
                report.append(f"  • {feat['feature']}: {feat['weight']:+.4f} ({feat['impact']} risk)")
            report.append("")
        
        # Global importance
        if include_global:
            global_importance = self.get_global_feature_importance()
            if global_importance:
                report.append("Global Feature Importance (Top 5):")
                report.append("-" * 80)
                for feat in global_importance[:5]:
                    report.append(f"  • {feat['feature']}: {feat['importance']:.4f}")
                report.append("")
        
        report.append("=" * 80)
        
        return "\n".join(report)


def explain_violation_prediction(violation_id: int) -> Dict[str, Any]:
    """
    Generate explanation for a violation prediction.
    
    Args:
        violation_id: ID of the violation to explain
    
    Returns:
        Explanation dictionary
    """
    from policy.models import Violation, HumanLayerEvent
    from policy.ml_scorer import MLRiskScorer
    
    # Get violation and associated event
    violation = Violation.objects.get(id=violation_id)
    
    # Find the event that triggered this violation
    event = HumanLayerEvent.objects.filter(
        user=violation.user,
        timestamp__lte=violation.detected_at
    ).order_by('-timestamp').first()
    
    if not event:
        return {'error': 'No associated event found'}
    
    # Load ML model
    scorer = MLRiskScorer()
    if scorer.model is None:
        return {'error': 'ML model not available'}
    
    # Extract features
    features = scorer.extract_features(event)
    
    # Create explainer
    explainer = ModelExplainer(
        model=scorer.model,
        feature_names=scorer.feature_names,
        training_data=None  # Could load training data from cache
    )
    
    # Generate explanation
    explanation = explainer.explain_prediction(features, method='both')
    explanation['violation_id'] = violation_id
    explanation['event_id'] = event.id
    explanation['user'] = violation.user.username
    
    return explanation
