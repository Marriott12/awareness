"""
Behavioral anomaly detection for insider threat monitoring.

Implements basic statistical anomaly detection to identify unusual user behavior
that may indicate insider threats or compromised accounts.
"""
from typing import Dict, Any, List, Optional
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.contrib.auth import get_user_model
import logging
import statistics

logger = logging.getLogger(__name__)
User = get_user_model()


class AnomalyDetector:
    """
    Detect behavioral anomalies that may indicate insider threats.
    
    Detection methods:
    - Unusual activity volume (spike in events)
    - Unusual timing (access outside normal hours)
    - Unusual violation patterns (sudden increase in policy violations)
    - Access to unusual resources
    - Geographic anomalies (if location data available)
    """
    
    def __init__(self, lookback_days: int = 30, z_score_threshold: float = 3.0):
        """
        Initialize anomaly detector.
        
        Args:
            lookback_days: Number of days to analyze for baseline
            z_score_threshold: Z-score threshold for anomaly detection (default: 3.0 = 99.7%)
        """
        self.lookback_days = lookback_days
        self.z_score_threshold = z_score_threshold
    
    def detect_volume_anomaly(self, user: User) -> Dict[str, Any]:
        """
        Detect unusual volume of events for a user.
        
        Returns:
            {
                'is_anomaly': bool,
                'current_count': int,
                'baseline_mean': float,
                'baseline_stddev': float,
                'z_score': float,
                'severity': str  # 'low', 'medium', 'high'
            }
        """
        from .models import HumanLayerEvent
        
        # Get current day's event count
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        current_count = HumanLayerEvent.objects.filter(
            user=user,
            timestamp__gte=today_start
        ).count()
        
        # Get historical daily counts for baseline
        lookback_start = timezone.now() - timedelta(days=self.lookback_days)
        daily_counts = []
        
        for i in range(self.lookback_days):
            day_start = lookback_start + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            
            count = HumanLayerEvent.objects.filter(
                user=user,
                timestamp__gte=day_start,
                timestamp__lt=day_end
            ).count()
            
            if count > 0:  # Only include days with activity
                daily_counts.append(count)
        
        # Calculate statistics
        if len(daily_counts) < 7:  # Need at least a week of data
            return {
                'is_anomaly': False,
                'current_count': current_count,
                'reason': 'insufficient_baseline_data'
            }
        
        baseline_mean = statistics.mean(daily_counts)
        baseline_stddev = statistics.stdev(daily_counts) if len(daily_counts) > 1 else 0
        
        # Calculate z-score
        if baseline_stddev == 0:
            z_score = 0
        else:
            z_score = (current_count - baseline_mean) / baseline_stddev
        
        # Determine severity
        severity = 'low'
        if abs(z_score) >= 5.0:
            severity = 'high'
        elif abs(z_score) >= 4.0:
            severity = 'medium'
        
        return {
            'is_anomaly': abs(z_score) >= self.z_score_threshold,
            'current_count': current_count,
            'baseline_mean': baseline_mean,
            'baseline_stddev': baseline_stddev,
            'z_score': z_score,
            'severity': severity
        }
    
    def detect_timing_anomaly(self, user: User) -> Dict[str, Any]:
        """
        Detect access outside normal working hours.
        
        Returns:
            {
                'is_anomaly': bool,
                'current_hour': int,
                'normal_hours': list,
                'recent_unusual_access': int
            }
        """
        from .models import HumanLayerEvent
        
        # Define normal working hours (can be customized per organization)
        NORMAL_HOURS = list(range(8, 18))  # 8 AM to 6 PM
        
        current_hour = timezone.now().hour
        
        # Count recent unusual access attempts
        lookback_start = timezone.now() - timedelta(days=7)
        unusual_access_count = HumanLayerEvent.objects.filter(
            user=user,
            timestamp__gte=lookback_start
        ).exclude(
            timestamp__hour__in=NORMAL_HOURS
        ).count()
        
        # Get user's typical working hours
        recent_events = HumanLayerEvent.objects.filter(
            user=user,
            timestamp__gte=lookback_start
        ).values_list('timestamp__hour', flat=True)
        
        if len(recent_events) < 10:
            return {
                'is_anomaly': False,
                'reason': 'insufficient_data'
            }
        
        # Most common hours for this user
        hour_counts = {}
        for hour in recent_events:
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        
        # User's normal hours (top 50% of their activity)
        sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
        total_events = sum(hour_counts.values())
        user_normal_hours = []
        cumulative = 0
        
        for hour, count in sorted_hours:
            user_normal_hours.append(hour)
            cumulative += count
            if cumulative >= total_events * 0.5:
                break
        
        # Is current access unusual?
        is_anomaly = current_hour not in user_normal_hours
        
        return {
            'is_anomaly': is_anomaly,
            'current_hour': current_hour,
            'user_normal_hours': user_normal_hours,
            'recent_unusual_access': unusual_access_count,
            'severity': 'high' if unusual_access_count > 5 else 'medium' if unusual_access_count > 2 else 'low'
        }
    
    def detect_violation_spike(self, user: User) -> Dict[str, Any]:
        """
        Detect sudden increase in policy violations.
        
        Returns:
            {
                'is_anomaly': bool,
                'current_violations': int,
                'baseline_mean': float,
                'z_score': float
            }
        """
        from .models import Violation
        
        # Current week's violations
        week_start = timezone.now() - timedelta(days=7)
        current_violations = Violation.objects.filter(
            user=user,
            timestamp__gte=week_start
        ).count()
        
        # Historical weekly violation counts
        lookback_start = timezone.now() - timedelta(days=self.lookback_days)
        weekly_counts = []
        
        for i in range(0, self.lookback_days, 7):
            period_start = lookback_start + timedelta(days=i)
            period_end = period_start + timedelta(days=7)
            
            count = Violation.objects.filter(
                user=user,
                timestamp__gte=period_start,
                timestamp__lt=period_end
            ).count()
            
            weekly_counts.append(count)
        
        if len(weekly_counts) < 3:
            return {
                'is_anomaly': False,
                'reason': 'insufficient_baseline_data'
            }
        
        baseline_mean = statistics.mean(weekly_counts[:-1])  # Exclude current week
        baseline_stddev = statistics.stdev(weekly_counts[:-1]) if len(weekly_counts) > 2 else 0
        
        if baseline_stddev == 0:
            z_score = 0
        else:
            z_score = (current_violations - baseline_mean) / baseline_stddev
        
        return {
            'is_anomaly': z_score >= self.z_score_threshold,
            'current_violations': current_violations,
            'baseline_mean': baseline_mean,
            'baseline_stddev': baseline_stddev,
            'z_score': z_score,
            'severity': 'high' if z_score >= 5.0 else 'medium' if z_score >= 4.0 else 'low'
        }
    
    def detect_all_anomalies(self, user: User) -> Dict[str, Any]:
        """
        Run all anomaly detection methods for a user.
        
        Returns:
            {
                'user_id': int,
                'username': str,
                'timestamp': str,
                'anomalies': {
                    'volume': {...},
                    'timing': {...},
                    'violations': {...}
                },
                'overall_risk': str,  # 'low', 'medium', 'high', 'critical'
                'is_threat': bool
            }
        """
        anomalies = {
            'volume': self.detect_volume_anomaly(user),
            'timing': self.detect_timing_anomaly(user),
            'violations': self.detect_violation_spike(user)
        }
        
        # Calculate overall risk
        anomaly_count = sum(1 for a in anomalies.values() if a.get('is_anomaly', False))
        high_severity_count = sum(
            1 for a in anomalies.values() 
            if a.get('severity') == 'high'
        )
        
        if anomaly_count >= 3 or high_severity_count >= 2:
            overall_risk = 'critical'
        elif anomaly_count >= 2 or high_severity_count >= 1:
            overall_risk = 'high'
        elif anomaly_count >= 1:
            overall_risk = 'medium'
        else:
            overall_risk = 'low'
        
        return {
            'user_id': user.id,
            'username': user.username,
            'timestamp': timezone.now().isoformat(),
            'anomalies': anomalies,
            'overall_risk': overall_risk,
            'is_threat': overall_risk in ['high', 'critical']
        }
    
    @classmethod
    def scan_all_users(cls, min_risk_level: str = 'medium') -> List[Dict[str, Any]]:
        """
        Scan all active users for anomalies.
        
        Args:
            min_risk_level: Minimum risk level to include in results
            
        Returns:
            List of users with detected anomalies
        """
        detector = cls()
        threats = []
        
        # Only scan users who have had activity in last 7 days
        week_ago = timezone.now() - timedelta(days=7)
        from .models import HumanLayerEvent
        
        active_users = User.objects.filter(
            humanlayerevent__timestamp__gte=week_ago,
            is_active=True
        ).distinct()
        
        for user in active_users:
            try:
                result = detector.detect_all_anomalies(user)
                
                # Filter by risk level
                risk_levels = ['low', 'medium', 'high', 'critical']
                min_index = risk_levels.index(min_risk_level)
                result_index = risk_levels.index(result['overall_risk'])
                
                if result_index >= min_index:
                    threats.append(result)
            except Exception as e:
                logger.exception(f'Failed to analyze user {user.id}: {e}')
        
        # Sort by risk level (critical first)
        risk_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        threats.sort(key=lambda x: risk_order.get(x['overall_risk'], 4))
        
        return threats
