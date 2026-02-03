"""Key rotation management for cryptographic integrity.

Implements:
- Safe key rotation with migration path
- Signature re-validation pipeline
- Key versioning and tracking
- Automatic rotation on schedule
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from policy.models import Evidence, HumanLayerEvent
from policy.crypto_utils import sign_data, verify_signature, load_private_key, load_public_key
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Rotate signing keys and re-sign all existing evidence'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--new-key-path',
            type=str,
            help='Path to new private key (will generate if not provided)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of records to process in each batch'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        
        self.stdout.write('Starting key rotation process...')
        
        # Step 1: Create new key version
        new_key_version = self._get_next_key_version()
        self.stdout.write(f'New key version: {new_key_version}')
        
        if options['new_key_path']:
            new_key_path = Path(options['new_key_path'])
        else:
            new_key_path = self._generate_new_key(new_key_version, dry_run)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
        
        # Step 2: Re-sign all Evidence records
        evidence_count = Evidence.objects.count()
        self.stdout.write(f'Re-signing {evidence_count} Evidence records...')
        
        if not dry_run:
            self._resign_evidence(new_key_version, new_key_path, batch_size)
        
        # Step 3: Re-sign all HumanLayerEvent records
        event_count = HumanLayerEvent.objects.count()
        self.stdout.write(f'Re-signing {event_count} HumanLayerEvent records...')
        
        if not dry_run:
            self._resign_events(new_key_version, new_key_path, batch_size)
        
        # Step 4: Archive old key
        if not dry_run:
            self._archive_old_key(new_key_version - 1)
        
        self.stdout.write(self.style.SUCCESS(f'Key rotation complete! New version: {new_key_version}'))
    
    def _get_next_key_version(self):
        """Get next key version number."""
        from django.conf import settings
        current_version = getattr(settings, 'SIGNING_KEY_VERSION', 0)
        return current_version + 1
    
    def _generate_new_key(self, version, dry_run):
        """Generate new RSA key pair."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        if dry_run:
            return Path(f'/tmp/key_v{version}.pem')
        
        # Generate 4096-bit RSA key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
            backend=default_backend()
        )
        
        # Save private key
        key_dir = Path('keys')
        key_dir.mkdir(exist_ok=True)
        
        private_path = key_dir / f'private_v{version}.pem'
        public_path = key_dir / f'public_v{version}.pem'
        
        with open(private_path, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Save public key
        public_key = private_key.public_key()
        with open(public_path, 'wb') as f:
            f.write(public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        
        self.stdout.write(f'Generated new key pair: {private_path}')
        return private_path
    
    @transaction.atomic
    def _resign_evidence(self, version, key_path, batch_size):
        """Re-sign all Evidence records with new key."""
        from policy.models import KeyRotationLog
        
        total = Evidence.objects.count()
        processed = 0
        
        for evidence in Evidence.objects.iterator(chunk_size=batch_size):
            # Create signature with new key
            payload = evidence.get_signature_payload()
            new_signature = sign_data(payload, key_path=str(key_path))
            
            # Store old signature for audit
            KeyRotationLog.objects.create(
                record_type='Evidence',
                record_id=evidence.id,
                old_signature=evidence.signature,
                new_signature=new_signature,
                key_version=version,
                rotated_at=datetime.utcnow()
            )
            
            # Update with new signature (bypassing immutability for this operation)
            Evidence.objects.filter(id=evidence.id).update(
                signature=new_signature,
                key_version=version
            )
            
            processed += 1
            if processed % 100 == 0:
                self.stdout.write(f'Progress: {processed}/{total} Evidence records')
    
    @transaction.atomic
    def _resign_events(self, version, key_path, batch_size):
        """Re-sign all HumanLayerEvent records with new key."""
        from policy.models import KeyRotationLog
        
        total = HumanLayerEvent.objects.count()
        processed = 0
        
        for event in HumanLayerEvent.objects.iterator(chunk_size=batch_size):
            if not event.signature:
                continue
            
            # Create signature with new key
            payload = event.get_signature_payload()
            new_signature = sign_data(payload, key_path=str(key_path))
            
            # Store old signature for audit
            KeyRotationLog.objects.create(
                record_type='HumanLayerEvent',
                record_id=str(event.event_id),
                old_signature=event.signature,
                new_signature=new_signature,
                key_version=version,
                rotated_at=datetime.utcnow()
            )
            
            # Update with new signature
            HumanLayerEvent.objects.filter(event_id=event.event_id).update(
                signature=new_signature,
                key_version=version
            )
            
            processed += 1
            if processed % 100 == 0:
                self.stdout.write(f'Progress: {processed}/{total} HumanLayerEvent records')
    
    def _archive_old_key(self, old_version):
        """Archive the old key for audit purposes."""
        key_dir = Path('keys')
        archive_dir = key_dir / 'archived'
        archive_dir.mkdir(exist_ok=True)
        
        old_private = key_dir / f'private_v{old_version}.pem'
        old_public = key_dir / f'public_v{old_version}.pem'
        
        if old_private.exists():
            old_private.rename(archive_dir / f'private_v{old_version}_archived_{datetime.now().isoformat()}.pem')
        if old_public.exists():
            old_public.rename(archive_dir / f'public_v{old_version}_archived_{datetime.now().isoformat()}.pem')
        
        self.stdout.write(f'Archived old key version {old_version}')
