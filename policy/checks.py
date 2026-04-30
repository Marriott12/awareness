from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Warning, register

from .ml_scorer import SKLEARN_AVAILABLE


@register()
def ml_readiness_check(app_configs, **kwargs):
    issues = []

    if not getattr(settings, "ML_ENABLED", False):
        return issues

    strict = getattr(settings, "ML_STRICT_READINESS", False)
    issue_cls = Error if strict else Warning

    if not SKLEARN_AVAILABLE:
        issues.append(
            issue_cls(
                "ML is enabled but scikit-learn is not available.",
                hint="Install requirements-core.txt and keep ML_ENABLED disabled until dependencies are present.",
                id="policy.E001" if strict else "policy.W001",
            )
        )
        return issues

    model_dir = Path(getattr(settings, "ML_MODEL_DIR", "ml_models"))
    model_version = getattr(settings, "ML_MODEL_VERSION", "1.0")
    model_path = model_dir / f"risk_model_{model_version}.pkl"

    if not model_path.exists():
        issues.append(
            issue_cls(
                f"ML model file is missing for configured version '{model_version}'.",
                hint=f"Train and save a model, or set ML_MODEL_VERSION to an existing artifact. Expected file: {model_path}",
                id="policy.E002" if strict else "policy.W002",
            )
        )

    try:
        from .models import GroundTruthLabel

        total_labels = GroundTruthLabel.objects.count()
        positive_labels = GroundTruthLabel.objects.filter(is_violation=True).count()
        negative_labels = GroundTruthLabel.objects.filter(is_violation=False).count()

        min_labels = getattr(settings, "ML_MIN_LABELS", 50)
        min_positive = getattr(settings, "ML_MIN_POSITIVE_LABELS", 10)
        min_negative = getattr(settings, "ML_MIN_NEGATIVE_LABELS", 10)

        if total_labels < min_labels:
            issues.append(
                Warning(
                    f"Only {total_labels} labeled events are available for ML training.",
                    hint=f"Label more HumanLayerEvent records in the admin. Recommended minimum: {min_labels}.",
                    id="policy.W003",
                )
            )
        if positive_labels < min_positive or negative_labels < min_negative:
            issues.append(
                Warning(
                    f"ML labels are imbalanced ({positive_labels} positive, {negative_labels} negative).",
                    hint="Collect both violation and non-violation labels before retraining.",
                    id="policy.W004",
                )
            )
    except Exception:
        pass

    return issues
