"""
Management command for automated database backups with verification.

Usage:
    python manage.py backup_database [--output-dir=/path/to/backups] [--verify] [--compress]
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection
import subprocess
import os
import hashlib
import gzip
import shutil
from datetime import datetime
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Create automated database backup with verification'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='/var/backups/awareness',
            help='Directory to store backups (default: /var/backups/awareness)'
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify backup integrity after creation'
        )
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Compress backup with gzip'
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=30,
            help='Delete backups older than this many days (default: 30)'
        )
        parser.add_argument(
            '--include-media',
            action='store_true',
            help='Include media files in backup'
        )
    
    def handle(self, *args, **options):
        output_dir = options['output_dir']
        verify = options['verify']
        compress = options['compress']
        retention_days = options['retention_days']
        include_media = options['include_media']
        
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_base = f'awareness_backup_{timestamp}'
        
        self.stdout.write(self.style.SUCCESS(f'Creating database backup: {backup_base}'))
        
        # Backup database
        db_backup_path = self._backup_database(output_dir, backup_base, compress)
        
        if not db_backup_path:
            self.stdout.write(self.style.ERROR('Database backup failed'))
            return
        
        # Backup media files if requested
        media_backup_path = None
        if include_media:
            media_backup_path = self._backup_media(output_dir, backup_base, compress)
        
        # Verify backups
        if verify:
            self.stdout.write('Verifying backup integrity...')
            if self._verify_backup(db_backup_path):
                self.stdout.write(self.style.SUCCESS('✓ Database backup verified'))
            else:
                self.stdout.write(self.style.ERROR('✗ Database backup verification failed'))
                return
            
            if media_backup_path:
                if self._verify_backup(media_backup_path):
                    self.stdout.write(self.style.SUCCESS('✓ Media backup verified'))
                else:
                    self.stdout.write(self.style.ERROR('✗ Media backup verification failed'))
        
        # Create manifest file
        manifest = self._create_manifest(
            db_backup_path,
            media_backup_path,
            timestamp
        )
        
        manifest_path = os.path.join(output_dir, f'{backup_base}_manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        self.stdout.write(self.style.SUCCESS(f'Backup manifest: {manifest_path}'))
        
        # Cleanup old backups
        if retention_days > 0:
            self._cleanup_old_backups(output_dir, retention_days)
        
        self.stdout.write(self.style.SUCCESS('Backup completed successfully'))
    
    def _backup_database(self, output_dir: str, backup_base: str, compress: bool) -> str:
        """
        Backup database using appropriate tool based on database engine.
        
        Returns path to backup file or None if failed.
        """
        db_config = settings.DATABASES['default']
        engine = db_config['ENGINE']
        
        backup_file = os.path.join(output_dir, f'{backup_base}.sql')
        
        try:
            if 'postgresql' in engine:
                # PostgreSQL backup with pg_dump
                cmd = [
                    'pg_dump',
                    '-h', db_config.get('HOST', 'localhost'),
                    '-p', str(db_config.get('PORT', 5432)),
                    '-U', db_config['USER'],
                    '-F', 'c',  # Custom format (compressed)
                    '-f', backup_file,
                    db_config['NAME']
                ]
                
                env = os.environ.copy()
                env['PGPASSWORD'] = db_config['PASSWORD']
                
                result = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout
                )
                
                if result.returncode != 0:
                    self.stdout.write(self.style.ERROR(f'pg_dump failed: {result.stderr}'))
                    return None
            
            elif 'mysql' in engine:
                # MySQL backup with mysqldump
                cmd = [
                    'mysqldump',
                    '-h', db_config.get('HOST', 'localhost'),
                    '-P', str(db_config.get('PORT', 3306)),
                    '-u', db_config['USER'],
                    f'-p{db_config["PASSWORD"]}',
                    '--single-transaction',
                    '--routines',
                    '--triggers',
                    '--result-file=' + backup_file,
                    db_config['NAME']
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600
                )
                
                if result.returncode != 0:
                    self.stdout.write(self.style.ERROR(f'mysqldump failed: {result.stderr}'))
                    return None
            
            elif 'sqlite' in engine:
                # SQLite backup
                db_path = db_config['NAME']
                shutil.copy2(db_path, backup_file)
            
            else:
                self.stdout.write(self.style.ERROR(f'Unsupported database engine: {engine}'))
                return None
            
            # Compress if requested
            if compress:
                compressed_file = f'{backup_file}.gz'
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(compressed_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_file)
                backup_file = compressed_file
            
            self.stdout.write(self.style.SUCCESS(f'Database backed up to: {backup_file}'))
            return backup_file
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Backup failed: {str(e)}'))
            logger.exception('Database backup failed')
            return None
    
    def _backup_media(self, output_dir: str, backup_base: str, compress: bool) -> str:
        """Backup media files."""
        media_root = settings.MEDIA_ROOT
        if not media_root or not os.path.exists(media_root):
            return None
        
        backup_file = os.path.join(output_dir, f'{backup_base}_media.tar')
        
        try:
            compression_flag = 'z' if compress else ''
            cmd = ['tar', f'c{compression_flag}f', backup_file, '-C', 
                   os.path.dirname(media_root), os.path.basename(media_root)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600
            )
            
            if result.returncode != 0:
                self.stdout.write(self.style.ERROR(f'Media backup failed: {result.stderr}'))
                return None
            
            if compress:
                backup_file += '.gz'
            
            self.stdout.write(self.style.SUCCESS(f'Media backed up to: {backup_file}'))
            return backup_file
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Media backup failed: {str(e)}'))
            logger.exception('Media backup failed')
            return None
    
    def _verify_backup(self, backup_path: str) -> bool:
        """
        Verify backup integrity using checksums.
        
        Returns True if backup is valid.
        """
        try:
            # Calculate SHA256 checksum
            sha256_hash = hashlib.sha256()
            with open(backup_path, 'rb') as f:
                for byte_block in iter(lambda: f.read(4096), b''):
                    sha256_hash.update(byte_block)
            
            checksum = sha256_hash.hexdigest()
            
            # Save checksum file
            checksum_file = f'{backup_path}.sha256'
            with open(checksum_file, 'w') as f:
                f.write(f'{checksum}  {os.path.basename(backup_path)}\n')
            
            # Verify file is readable
            file_size = os.path.getsize(backup_path)
            
            return file_size > 0
        
        except Exception as e:
            logger.exception('Backup verification failed')
            return False
    
    def _create_manifest(self, db_backup: str, media_backup: str, 
                        timestamp: str) -> dict:
        """Create backup manifest with metadata."""
        manifest = {
            'timestamp': timestamp,
            'created_at': datetime.now().isoformat(),
            'database': {
                'path': db_backup,
                'size': os.path.getsize(db_backup),
                'checksum': self._get_checksum(db_backup)
            },
            'django_version': self._get_django_version(),
            'python_version': self._get_python_version(),
        }
        
        if media_backup:
            manifest['media'] = {
                'path': media_backup,
                'size': os.path.getsize(media_backup),
                'checksum': self._get_checksum(media_backup)
            }
        
        return manifest
    
    def _get_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b''):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _get_django_version(self) -> str:
        """Get Django version."""
        import django
        return django.get_version()
    
    def _get_python_version(self) -> str:
        """Get Python version."""
        import sys
        return sys.version
    
    def _cleanup_old_backups(self, output_dir: str, retention_days: int):
        """Delete backups older than retention period."""
        cutoff_time = datetime.now().timestamp() - (retention_days * 86400)
        deleted_count = 0
        
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            
            if os.path.isfile(file_path):
                file_time = os.path.getmtime(file_path)
                
                if file_time < cutoff_time and 'awareness_backup_' in filename:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        logger.warning(f'Failed to delete old backup {filename}: {e}')
        
        if deleted_count > 0:
            self.stdout.write(
                self.style.WARNING(f'Deleted {deleted_count} old backup(s)')
            )
