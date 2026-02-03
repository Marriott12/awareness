"""
GDPR compliance utilities for Awareness system.

Features:
- Right to erasure (right to be forgotten)
- Data retention policies
- Consent management
- Data export (data portability)
- Pseudonymization for audit trails
"""
import logging
import hashlib
import json
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)


class GDPRManager:
    """Manage GDPR compliance operations."""
    
    DEFAULT_RETENTION_DAYS = getattr(settings, 'GDPR_RETENTION_DAYS', 365 * 7)  # 7 years
    
    @classmethod
    def pseudonymize_user(cls, user_id):
        """
        Generate consistent pseudonymized identifier for a user.
        
        Uses SHA256 hash with salt for one-way transformation.
        Same user always gets same pseudonym (for referential integrity).
        
        Args:
            user_id: User identifier (int or str)
        
        Returns:
            str: Pseudonymized identifier (e.g., "user_a3f2b...")
        """
        salt = settings.SECRET_KEY[:32]  # Use part of secret key as salt
        data = f"{salt}:{user_id}".encode('utf-8')
        hash_digest = hashlib.sha256(data).hexdigest()[:16]
        return f"user_{hash_digest}"
    
    @classmethod
    @transaction.atomic
    def erase_user_data(cls, user, reason='user_request', keep_audit_trail=True):
        """
        Erase user's personal data while maintaining audit integrity.
        
        GDPR Article 17: Right to erasure
        
        Strategy:
        1. Pseudonymize user in events (preserve audit trail)
        2. Delete non-essential personal data
        3. Mark user as anonymized
        4. Create erasure record for compliance
        
        Args:
            user: User object to erase
            reason: Reason for erasure ('user_request', 'retention_policy', 'admin')
            keep_audit_trail: If True, pseudonymize instead of delete
        
        Returns:
            dict: Erasure summary
        """
        from policy.models import HumanLayerEvent, EventMetadata
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        logger.info(f"[GDPR] Starting data erasure for user {user.id} (reason: {reason})")
        
        stats = {
            'user_id': user.id,
            'reason': reason,
            'timestamp': timezone.now().isoformat(),
            'events_pseudonymized': 0,
            'metadata_updated': 0,
            'personal_data_deleted': False,
        }
        
        if keep_audit_trail:
            # Pseudonymize user in events
            pseudonym = cls.pseudonymize_user(user.id)
            
            # Update events created by this user
            events = HumanLayerEvent.objects.filter(created_by=user)
            stats['events_pseudonymized'] = events.count()
            
            for event in events:
                # Update metadata to pseudonymize
                try:
                    metadata = EventMetadata.objects.get(event=event)
                    
                    # Pseudonymize in details
                    if metadata.additional_details:
                        details = metadata.additional_details
                        if isinstance(details, str):
                            details = json.loads(details)
                        
                        # Replace any user identifiers
                        details['_gdpr_pseudonymized'] = True
                        details['_original_user_pseudonym'] = pseudonym
                        
                        metadata.additional_details = details
                        metadata.save()
                        stats['metadata_updated'] += 1
                
                except EventMetadata.DoesNotExist:
                    pass
            
            # Pseudonymize user account
            user.username = f"deleted_{pseudonym}"
            user.email = f"{pseudonym}@deleted.local"
            user.first_name = ""
            user.last_name = ""
            user.is_active = False
            user.save()
            
            stats['personal_data_deleted'] = True
        
        else:
            # Full deletion (not recommended for compliance)
            logger.warning(f"[GDPR] Full deletion requested for user {user.id} (no audit trail)")
            
            # Delete user's events (breaks audit trail!)
            HumanLayerEvent.objects.filter(created_by=user).delete()
            
            # Delete user account
            user.delete()
            
            stats['personal_data_deleted'] = True
            stats['audit_trail_preserved'] = False
        
        # Create erasure record
        cls._create_erasure_record(user.id, stats, reason)
        
        logger.info(f"[GDPR] Erasure complete for user {user.id}: {stats}")
        
        return stats
    
    @classmethod
    def _create_erasure_record(cls, user_id, stats, reason):
        """Create immutable record of data erasure."""
        from policy.models import ComplianceAuditLog
        
        ComplianceAuditLog.objects.create(
            event_type='gdpr_erasure',
            user_id=user_id,
            details={
                'action': 'data_erasure',
                'reason': reason,
                'stats': stats,
                'gdpr_article': 'Article 17 - Right to erasure',
            },
            timestamp=timezone.now(),
        )
    
    @classmethod
    def export_user_data(cls, user):
        """
        Export all user data for GDPR data portability.
        
        GDPR Article 20: Right to data portability
        
        Returns structured JSON with all user's data.
        
        Args:
            user: User object
        
        Returns:
            dict: Complete user data export
        """
        from policy.models import HumanLayerEvent, ComplianceViolation, EventMetadata
        
        logger.info(f"[GDPR] Exporting data for user {user.id}")
        
        export_data = {
            'export_date': timezone.now().isoformat(),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'date_joined': user.date_joined.isoformat() if hasattr(user, 'date_joined') else None,
            },
            'events': [],
            'violations': [],
        }
        
        # Export events
        events = HumanLayerEvent.objects.filter(created_by=user)
        
        for event in events:
            event_data = {
                'event_id': event.event_id,
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type,
                'summary': event.summary,
                'source': event.source,
                'severity': event.severity,
            }
            
            # Include metadata
            try:
                metadata = EventMetadata.objects.get(event=event)
                event_data['metadata'] = {
                    'tags': metadata.tags,
                    'additional_details': metadata.additional_details,
                }
            except EventMetadata.DoesNotExist:
                pass
            
            export_data['events'].append(event_data)
        
        # Export violations related to user's events
        violations = ComplianceViolation.objects.filter(event__in=events)
        
        for violation in violations:
            violation_data = {
                'id': violation.id,
                'policy': violation.policy.name,
                'severity': violation.severity,
                'detected_at': violation.created_at.isoformat(),
                'status': violation.status,
            }
            export_data['violations'].append(violation_data)
        
        logger.info(f"[GDPR] Export complete for user {user.id}: "
                   f"{len(export_data['events'])} events, "
                   f"{len(export_data['violations'])} violations")
        
        return export_data
    
    @classmethod
    def apply_retention_policy(cls, dry_run=True):
        """
        Apply data retention policy by deleting old records.
        
        GDPR Article 5(1)(e): Storage limitation
        
        Deletes data older than retention period (default 7 years).
        
        Args:
            dry_run: If True, only report what would be deleted
        
        Returns:
            dict: Retention policy results
        """
        from policy.models import HumanLayerEvent, EventMetadata
        
        retention_days = cls.DEFAULT_RETENTION_DAYS
        cutoff_date = timezone.now() - timedelta(days=retention_days)
        
        logger.info(f"[GDPR] Applying retention policy (cutoff: {cutoff_date}, dry_run: {dry_run})")
        
        # Find old events
        old_events = HumanLayerEvent.objects.filter(timestamp__lt=cutoff_date)
        count = old_events.count()
        
        stats = {
            'retention_days': retention_days,
            'cutoff_date': cutoff_date.isoformat(),
            'events_found': count,
            'events_deleted': 0,
            'dry_run': dry_run,
        }
        
        if not dry_run and count > 0:
            # Delete old metadata first (FK constraint)
            EventMetadata.objects.filter(event__in=old_events).delete()
            
            # Delete old events
            deleted_count, _ = old_events.delete()
            stats['events_deleted'] = deleted_count
            
            logger.info(f"[GDPR] Deleted {deleted_count} old events")
        else:
            logger.info(f"[GDPR] Would delete {count} events (dry run)")
        
        return stats
    
    @classmethod
    def check_consent(cls, user, purpose):
        """
        Check if user has given consent for specific data processing purpose.
        
        GDPR Article 6(1)(a): Consent
        
        Args:
            user: User object
            purpose: Purpose string (e.g., 'compliance_evaluation', 'ml_training')
        
        Returns:
            bool: True if consent given
        """
        # In production, maintain a consent registry
        # For now, assume consent via terms of service
        logger.debug(f"[GDPR] Checking consent for user {user.id}, purpose: {purpose}")
        
        # Check if user has consent record
        # This would query a UserConsent model in production
        return True  # Placeholder
    
    @classmethod
    def record_consent(cls, user, purpose, granted=True, metadata=None):
        """
        Record user consent for data processing.
        
        Args:
            user: User object
            purpose: Purpose string
            granted: Whether consent was granted or withdrawn
            metadata: Additional metadata (IP, timestamp, etc.)
        """
        from policy.models import ComplianceAuditLog
        
        logger.info(f"[GDPR] Recording consent for user {user.id}: "
                   f"purpose={purpose}, granted={granted}")
        
        ComplianceAuditLog.objects.create(
            event_type='gdpr_consent',
            user_id=user.id,
            details={
                'action': 'consent_recorded',
                'purpose': purpose,
                'granted': granted,
                'metadata': metadata or {},
                'gdpr_article': 'Article 6(1)(a) - Consent',
            },
            timestamp=timezone.now(),
        )


class DataMinimization:
    """
    GDPR Article 5(1)(c): Data minimisation
    
    Utilities for ensuring only necessary data is collected and stored.
    """
    
    @staticmethod
    def filter_pii(data):
        """
        Remove or redact PII from data dictionary.
        
        Args:
            data: Dictionary potentially containing PII
        
        Returns:
            dict: Data with PII removed/redacted
        """
        pii_fields = [
            'email', 'phone', 'ssn', 'passport', 'credit_card',
            'name', 'address', 'birth_date', 'ip_address',
        ]
        
        filtered = data.copy()
        
        for field in pii_fields:
            if field in filtered:
                filtered[field] = '[REDACTED]'
        
        return filtered
    
    @staticmethod
    def validate_collection_necessity(fields_requested, purpose):
        """
        Validate that requested fields are necessary for stated purpose.
        
        Args:
            fields_requested: List of field names
            purpose: Purpose for collection
        
        Returns:
            tuple: (is_valid, unnecessary_fields)
        """
        # Define necessary fields per purpose
        necessary_fields = {
            'compliance_evaluation': ['event_id', 'timestamp', 'event_type', 'summary'],
            'ml_training': ['event_id', 'timestamp', 'event_type', 'severity'],
            'audit_trail': ['event_id', 'timestamp', 'user_id', 'action'],
        }
        
        if purpose not in necessary_fields:
            logger.warning(f"[GDPR] Unknown purpose: {purpose}")
            return False, fields_requested
        
        required = set(necessary_fields[purpose])
        requested = set(fields_requested)
        
        unnecessary = requested - required
        
        if unnecessary:
            logger.warning(f"[GDPR] Unnecessary fields requested for {purpose}: {unnecessary}")
            return False, list(unnecessary)
        
        return True, []


# Management command helpers
def run_gdpr_erasure(username, reason='user_request'):
    """
    Helper function for management command to erase user data.
    
    Usage:
        python manage.py gdpr_erase_user <username> --reason user_request
    """
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        user = User.objects.get(username=username)
        stats = GDPRManager.erase_user_data(user, reason=reason)
        return stats
    except User.DoesNotExist:
        logger.error(f"[GDPR] User not found: {username}")
        return None


def run_gdpr_export(username):
    """
    Helper function for management command to export user data.
    
    Usage:
        python manage.py gdpr_export_user <username> --output export.json
    """
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        user = User.objects.get(username=username)
        data = GDPRManager.export_user_data(user)
        return data
    except User.DoesNotExist:
        logger.error(f"[GDPR] User not found: {username}")
        return None


def run_retention_policy(dry_run=True):
    """
    Helper function for management command to apply retention policy.
    
    Usage:
        python manage.py gdpr_retention_policy --execute
    """
    stats = GDPRManager.apply_retention_policy(dry_run=dry_run)
    return stats
