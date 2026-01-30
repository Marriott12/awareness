"""Explainable risk scoring for HumanLayerEvent telemetry.

Features:
- Feature extraction from recent events for the same user
- Simple explainable scoring combining rule-violation counts and statistical anomalies
"""
from typing import Dict, Any
from django.utils import timezone
from .models import HumanLayerEvent, Violation
from .models import ScorerArtifact
import math


class RiskScorer:
    """Simple explainable scorer producing 0-100 score and contributing factors.

    Explanation: score = weighted sum of normalized features:
    - recent_violation_count (past 24h)
    - distinct_ip_count (past 24h)
    - unusual_hour (binary)
    - recent_failed_logins (past 1h)
    - novelty (source not seen before)
    """

    def __init__(self, now=None):
        self.now = now or timezone.now()

    def load_artifact(self, name: str, version: str = None):
        try:
            if version:
                return ScorerArtifact.objects.get(name=name, version=version)
            return ScorerArtifact.objects.filter(name=name).order_by('-created_at').first()
        except Exception:
            return None

    def extract_features(self, event: HumanLayerEvent, window_hours: int = 24) -> Dict[str, Any]:
        user = event.user
        if user is None:
            return {}
        window_start = self.now - timezone.timedelta(hours=window_hours)
        recent = HumanLayerEvent.objects.filter(user=user, timestamp__gte=window_start).order_by('-timestamp')
        # counts
        total = recent.count()
        violation_count = Violation.objects.filter(user=user, timestamp__gte=window_start).count()
        distinct_ips = set()
        recent_failed_logins = 0
        sources = set()
        for r in recent[:200]:
            if isinstance(r.details, dict):
                ip = r.details.get('remote_addr')
                if ip:
                    distinct_ips.add(ip)
                if r.event_type == 'auth' and r.summary == 'user_login_failed':
                    recent_failed_logins += 1
            sources.add(r.source)

        hour = event.timestamp.hour
        unusual_hour = 1 if (hour < 6 or hour > 22) else 0

        features = {
            'total_recent_events': total,
            'violation_count_24h': violation_count,
            'distinct_ip_count_24h': len(distinct_ips),
            'recent_failed_logins_1h': recent_failed_logins,
            'unusual_hour': unusual_hour,
            'source_novelty': 1 if event.source not in sources else 0,
        }
        return features

    def score(self, event: HumanLayerEvent) -> Dict[str, Any]:
        features = self.extract_features(event)
        # weights chosen for interpretability
        weights = {
            'violation_count_24h': 30.0,
            'distinct_ip_count_24h': 10.0,
            'recent_failed_logins_1h': 20.0,
            'unusual_hour': 10.0,
            'source_novelty': 15.0,
        }

        # normalize features to reasonable ranges
        v_count = features.get('violation_count_24h', 0)
        v_norm = min(1.0, v_count / 5.0)

        ip_norm = min(1.0, features.get('distinct_ip_count_24h', 0) / 3.0)
        fail_norm = min(1.0, features.get('recent_failed_logins_1h', 0) / 5.0)
        unusual = features.get('unusual_hour', 0)
        novelty = features.get('source_novelty', 0)

        raw = (
            weights['violation_count_24h'] * v_norm
            + weights['distinct_ip_count_24h'] * ip_norm
            + weights['recent_failed_logins_1h'] * fail_norm
            + weights['unusual_hour'] * unusual
            + weights['source_novelty'] * novelty
        )

        # map raw to 0-100
        max_raw = sum(weights.values())
        score = int(min(100, round((raw / max_raw) * 100)))

        factors = [
            {'name': 'violation_count_24h', 'value': v_count, 'contribution': int(weights['violation_count_24h'] * v_norm)},
            {'name': 'distinct_ip_count_24h', 'value': features.get('distinct_ip_count_24h', 0), 'contribution': int(weights['distinct_ip_count_24h'] * ip_norm)},
            {'name': 'recent_failed_logins_1h', 'value': features.get('recent_failed_logins_1h', 0), 'contribution': int(weights['recent_failed_logins_1h'] * fail_norm)},
            {'name': 'unusual_hour', 'value': unusual, 'contribution': int(weights['unusual_hour'] * unusual)},
            {'name': 'source_novelty', 'value': novelty, 'contribution': int(weights['source_novelty'] * novelty)},
        ]

        return {'score': score, 'raw': raw, 'max_raw': max_raw, 'factors': factors, 'features': features}
