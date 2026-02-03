"""GDPR compliance utilities for data management.

Implements:
- Right to erasure (data deletion)
- Data retention policies
- Anonymization
- Export in standard formats
- Audit trail preservation
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import logging
import json
import csv
from pathlib import Path

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'GDPR compliance operations: delete, anonymize, or export user data'
    
    def add_arguments(self, parser):
        parser.add_argument('operation', type=str, choices=['delete', 'anonymize', 'export', 'cleanup'])
        parser.add_argument('--user-id', type=int, help='User ID to operate on')
        parser.add_argument('--retention-days', type=int, default=2555, help='Data retention period (7 years default)')
        parser.add_argument('--format', type=str, default='json', choices=['json', 'csv'], help='Export format')
        parser.add_argument('--output', type=str, help='Output file path')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    
    def handle(self, *args, **options):
        operation = options['operation']
        
        if operation == 'delete':
            self._delete_user_data(options)
        elif operation == 'anonymize':
            self._anonymize_user_data(options)
        elif operation == 'export':
            self._export_user_data(options)
        elif operation == 'cleanup':
            self._cleanup_old_data(options)
    
    @transaction.atomic
    def _delete_user_data(self, options):
        """Delete user data while preserving audit trail integrity."""
        user_id = options['user_id']
        dry_run = options['dry_run']
        
        if not user_id:
            self.stdout.write(self.style.ERROR('--user-id required for delete operation'))
            return
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {user_id} not found'))
            return
        
        self.stdout.write(f'Deleting data for user: {user.username} (ID: {user_id})')
        
        # Track what will be deleted
        from policy.models import Violation, HumanLayerEvent, GDPRDeletionLog
        from training.models import TrainingProgress
        from quizzes.models import QuizAttempt
        
        violations = Violation.objects.filter(user=user)
        events = HumanLayerEvent.objects.filter(user=user)
        progress = TrainingProgress.objects.filter(user=user)
        attempts = QuizAttempt.objects.filter(user=user)
        
        self.stdout.write(f'  Violations: {violations.count()}')
        self.stdout.write(f'  Events: {events.count()}')
        self.stdout.write(f'  Training progress: {progress.count()}')
        self.stdout.write(f'  Quiz attempts: {attempts.count()}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes made'))
            return
        
        # Create deletion log BEFORE deleting (for audit trail)
        deletion_log = GDPRDeletionLog.objects.create(
            user_id=user_id,
            username=user.username,
            email=user.email,
            deleted_at=timezone.now(),
            violations_count=violations.count(),
            events_count=events.count(),
            reason='GDPR Right to Erasure Request'
        )
        
        # Delete user data (cascade will handle related records)
        violations.delete()
        progress.delete()
        attempts.delete()
        
        # Anonymize events instead of deleting (preserve audit trail)
        events.update(user=None, anonymized=True)
        
        # Delete user account
        user.delete()
        
        self.stdout.write(self.style.SUCCESS(f'User data deleted. Deletion log ID: {deletion_log.id}'))
    
    @transaction.atomic
    def _anonymize_user_data(self, options):
        """Anonymize user data while keeping statistical value."""
        user_id = options['user_id']
        dry_run = options['dry_run']
        
        if not user_id:
            self.stdout.write(self.style.ERROR('--user-id required for anonymize operation'))
            return
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {user_id} not found'))
            return
        
        self.stdout.write(f'Anonymizing data for user: {user.username} (ID: {user_id})')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes made'))
            return
        
        # Generate pseudonym
        import hashlib
        pseudonym = hashlib.sha256(f'{user_id}{timezone.now().isoformat()}'.encode()).hexdigest()[:16]
        
        # Anonymize user account
        user.username = f'anon_{pseudonym}'
        user.email = f'{pseudonym}@anonymized.local'
        user.first_name = ''
        user.last_name = ''
        user.is_active = False
        user.save()
        
        # Mark all related events as anonymized
        from policy.models import HumanLayerEvent
        HumanLayerEvent.objects.filter(user_id=user_id).update(anonymized=True)
        
        self.stdout.write(self.style.SUCCESS(f'User anonymized as: {user.username}'))
    
    def _export_user_data(self, options):
        """Export all user data in standard format."""
        user_id = options['user_id']
        format = options['format']
        output = options['output']
        
        if not user_id:
            self.stdout.write(self.style.ERROR('--user-id required for export operation'))
            return
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {user_id} not found'))
            return
        
        # Collect all user data
        data = self._collect_user_data(user)
        
        # Determine output path
        if not output:
            output = f'user_{user_id}_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.{format}'
        
        # Export in requested format
        if format == 'json':
            self._export_json(data, output)
        elif format == 'csv':
            self._export_csv(data, output)
        
        self.stdout.write(self.style.SUCCESS(f'User data exported to: {output}'))
    
    def _collect_user_data(self, user):
        """Collect all data for a user."""
        from policy.models import Violation, HumanLayerEvent
        from training.models import TrainingProgress
        from quizzes.models import QuizAttempt
        
        data = {
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'date_joined': user.date_joined.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
            },
            'violations': list(Violation.objects.filter(user=user).values()),
            'events': list(HumanLayerEvent.objects.filter(user=user).values()),
            'training_progress': list(TrainingProgress.objects.filter(user=user).values()),
            'quiz_attempts': list(QuizAttempt.objects.filter(user=user).values()),
        }
        
        return data
    
    def _export_json(self, data, output):
        """Export data as JSON."""
        with open(output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def _export_csv(self, data, output):
        """Export data as CSV (multiple files)."""
        base_path = Path(output).stem
        
        # Export each data type to separate CSV
        for key, records in data.items():
            if key == 'user':
                continue
            
            if not records:
                continue
            
            csv_path = f'{base_path}_{key}.csv'
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
            
            self.stdout.write(f'  Exported {len(records)} {key} to {csv_path}')
    
    @transaction.atomic
    def _cleanup_old_data(self, options):
        """Delete data older than retention period."""
        retention_days = options['retention_days']
        dry_run = options['dry_run']
        cutoff_date = timezone.now() - timedelta(days=retention_days)
        
        self.stdout.write(f'Cleaning up data older than {retention_days} days (before {cutoff_date})')
        
        from policy.models import HumanLayerEvent, Violation
        
        old_events = HumanLayerEvent.objects.filter(timestamp__lt=cutoff_date, anonymized=True)
        old_violations = Violation.objects.filter(detected_at__lt=cutoff_date, resolved=True)
        
        self.stdout.write(f'  Old events to delete: {old_events.count()}')
        self.stdout.write(f'  Old resolved violations to delete: {old_violations.count()}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes made'))
            return
        
        deleted_events = old_events.delete()
        deleted_violations = old_violations.delete()
        
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted_events[0]} events and {deleted_violations[0]} violations'))
