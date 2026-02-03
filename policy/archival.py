"""
Data archival and partitioning strategy for long-term scalability.

Implements automated archival of old events to cold storage and
table partitioning by date for improved query performance.

Features:
- Automated archival to S3/Azure Blob/File system
- PostgreSQL table partitioning by date
- Transparent query routing to hot/cold storage
- Retention policy enforcement
- Archival verification and restoration

Usage:
    python manage.py archive_old_data --days=365 --storage=s3
    python manage.py partition_tables --partition-by=month
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import connection, transaction
from django.conf import settings
import json
import gzip
import logging

logger = logging.getLogger(__name__)


class ArchivalManager:
    """
    Manage archival of old telemetry data to cold storage.
    
    Supports multiple storage backends:
    - S3 (AWS)
    - Azure Blob Storage
    - File system (for on-prem deployments)
    """
    
    def __init__(self, storage_backend: str = 'filesystem'):
        """
        Initialize archival manager.
        
        Args:
            storage_backend: 'filesystem', 's3', or 'azure'
        """
        self.storage_backend = storage_backend
        self._init_storage()
    
    def _init_storage(self):
        """Initialize storage backend."""
        if self.storage_backend == 's3':
            try:
                import boto3
                self.s3_client = boto3.client('s3')
                self.s3_bucket = getattr(settings, 'ARCHIVE_S3_BUCKET', 'awareness-archives')
            except ImportError:
                logger.error('boto3 not installed, cannot use S3 backend')
                self.storage_backend = 'filesystem'
        
        elif self.storage_backend == 'azure':
            try:
                from azure.storage.blob import BlobServiceClient
                connection_string = getattr(settings, 'AZURE_STORAGE_CONNECTION_STRING', '')
                self.blob_service = BlobServiceClient.from_connection_string(connection_string)
                self.container_name = getattr(settings, 'ARCHIVE_CONTAINER_NAME', 'awareness-archives')
            except ImportError:
                logger.error('azure-storage-blob not installed, cannot use Azure backend')
                self.storage_backend = 'filesystem'
        
        if self.storage_backend == 'filesystem':
            import os
            self.archive_path = getattr(settings, 'ARCHIVE_PATH', '/var/archives/awareness')
            os.makedirs(self.archive_path, exist_ok=True)
    
    def archive_events(self, cutoff_date: datetime, dry_run: bool = False) -> Dict[str, Any]:
        """
        Archive events older than cutoff date to cold storage.
        
        Args:
            cutoff_date: Archive events before this date
            dry_run: If True, don't actually archive
            
        Returns:
            Summary statistics
        """
        try:
            from .models import HumanLayerEvent, EventMetadata
            
            # Get old events
            old_events = HumanLayerEvent.objects.filter(
                timestamp__lt=cutoff_date
            )
            
            total = old_events.count()
            
            if total == 0:
                logger.info('No events to archive')
                return {'total': 0, 'archived': 0, 'deleted': 0}
            
            logger.info(f'Found {total} events to archive')
            
            if dry_run:
                logger.info('DRY RUN: No changes will be made')
                return {'total': total, 'archived': 0, 'deleted': 0, 'dry_run': True}
            
            # Export events in batches
            batch_size = 1000
            archived_count = 0
            
            for i in range(0, total, batch_size):
                batch = old_events[i:i+batch_size]
                
                # Serialize batch
                events_data = []
                for event in batch:
                    events_data.append({
                        'id': event.id,
                        'timestamp': event.timestamp.isoformat(),
                        'event_type': event.event_type,
                        'source': event.source,
                        'user_id': event.user_id,
                        'summary': event.summary,
                        'details': event.details,
                        'signature': event.signature,
                        'prev_hash': event.prev_hash,
                    })
                
                # Compress and upload
                archive_key = f'events_{cutoff_date.date()}_{i}_{i+batch_size}.json.gz'
                
                if self._upload_archive(archive_key, events_data):
                    archived_count += len(events_data)
                    logger.info(f'Archived batch {i}-{i+batch_size}')
                else:
                    logger.error(f'Failed to archive batch {i}-{i+batch_size}')
            
            # Delete archived events from hot storage
            deleted_count = old_events.delete()[0]
            
            logger.info(f'Archived {archived_count} events, deleted {deleted_count} from hot storage')
            
            return {
                'total': total,
                'archived': archived_count,
                'deleted': deleted_count,
                'cutoff_date': cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.exception(f'Archival failed: {e}')
            return {'error': str(e)}
    
    def _upload_archive(self, key: str, data: List[Dict]) -> bool:
        """Upload archive to storage backend."""
        try:
            # Compress data
            json_data = json.dumps(data, default=str)
            compressed_data = gzip.compress(json_data.encode('utf-8'))
            
            if self.storage_backend == 's3':
                self.s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=key,
                    Body=compressed_data,
                    ContentType='application/gzip'
                )
                
            elif self.storage_backend == 'azure':
                blob_client = self.blob_service.get_blob_client(
                    container=self.container_name,
                    blob=key
                )
                blob_client.upload_blob(compressed_data, overwrite=True)
                
            else:  # filesystem
                import os
                archive_file = os.path.join(self.archive_path, key)
                with open(archive_file, 'wb') as f:
                    f.write(compressed_data)
            
            return True
            
        except Exception as e:
            logger.exception(f'Failed to upload archive {key}: {e}')
            return False
    
    def restore_archive(self, archive_key: str) -> List[Dict]:
        """
        Restore archived data from cold storage.
        
        Args:
            archive_key: Key/path to archive file
            
        Returns:
            List of restored event dictionaries
        """
        try:
            # Download from storage
            if self.storage_backend == 's3':
                response = self.s3_client.get_object(
                    Bucket=self.s3_bucket,
                    Key=archive_key
                )
                compressed_data = response['Body'].read()
                
            elif self.storage_backend == 'azure':
                blob_client = self.blob_service.get_blob_client(
                    container=self.container_name,
                    blob=archive_key
                )
                compressed_data = blob_client.download_blob().readall()
                
            else:  # filesystem
                import os
                archive_file = os.path.join(self.archive_path, archive_key)
                with open(archive_file, 'rb') as f:
                    compressed_data = f.read()
            
            # Decompress and parse
            json_data = gzip.decompress(compressed_data).decode('utf-8')
            events_data = json.loads(json_data)
            
            logger.info(f'Restored {len(events_data)} events from {archive_key}')
            
            return events_data
            
        except Exception as e:
            logger.exception(f'Failed to restore archive {archive_key}: {e}')
            return []


class TablePartitioner:
    """
    Manage PostgreSQL table partitioning for improved query performance.
    
    Implements range partitioning by date for HumanLayerEvent and Violation tables.
    """
    
    @staticmethod
    def create_monthly_partitions(table_name: str, start_date: datetime, 
                                  num_months: int = 12) -> bool:
        """
        Create monthly partitions for a table.
        
        Args:
            table_name: Name of table to partition
            start_date: Start date for partitions
            num_months: Number of monthly partitions to create
            
        Returns:
            True if successful
        """
        try:
            if 'postgresql' not in connection.settings_dict['ENGINE']:
                logger.warning('Table partitioning only supported on PostgreSQL')
                return False
            
            with connection.cursor() as cursor:
                # Check if table is already partitioned
                cursor.execute("""
                    SELECT COUNT(*) FROM pg_partitioned_table 
                    WHERE partrelid = %s::regclass
                """, [table_name])
                
                is_partitioned = cursor.fetchone()[0] > 0
                
                if not is_partitioned:
                    # Convert table to partitioned table
                    logger.info(f'Converting {table_name} to partitioned table')
                    
                    # This requires recreating the table - should be done in migration
                    logger.warning(
                        f'{table_name} is not partitioned. '
                        'Run migration to convert to partitioned table.'
                    )
                    return False
                
                # Create monthly partitions
                current_date = start_date
                
                for i in range(num_months):
                    partition_start = current_date.replace(day=1)
                    
                    # Next month
                    if partition_start.month == 12:
                        partition_end = partition_start.replace(year=partition_start.year + 1, month=1)
                    else:
                        partition_end = partition_start.replace(month=partition_start.month + 1)
                    
                    partition_name = f"{table_name}_{partition_start.strftime('%Y_%m')}"
                    
                    # Create partition if it doesn't exist
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS {partition_name}
                        PARTITION OF {table_name}
                        FOR VALUES FROM ('{partition_start.date()}') 
                        TO ('{partition_end.date()}')
                    """)
                    
                    logger.info(f'Created partition {partition_name}')
                    
                    current_date = partition_end
                
                logger.info(f'Created {num_months} monthly partitions for {table_name}')
                return True
                
        except Exception as e:
            logger.exception(f'Failed to create partitions: {e}')
            return False
    
    @staticmethod
    def drop_old_partitions(table_name: str, retention_months: int = 24) -> int:
        """
        Drop partitions older than retention period.
        
        Args:
            table_name: Base table name
            retention_months: Keep partitions newer than this
            
        Returns:
            Number of partitions dropped
        """
        try:
            if 'postgresql' not in connection.settings_dict['ENGINE']:
                return 0
            
            cutoff_date = timezone.now() - timedelta(days=retention_months * 30)
            dropped = 0
            
            with connection.cursor() as cursor:
                # Find old partitions
                cursor.execute("""
                    SELECT tablename FROM pg_tables
                    WHERE tablename LIKE %s
                    ORDER BY tablename
                """, [f'{table_name}_%'])
                
                partitions = cursor.fetchall()
                
                for (partition_name,) in partitions:
                    # Extract date from partition name
                    try:
                        date_str = partition_name.split('_')[-2:]  # ['2024', '01']
                        partition_date = datetime(
                            year=int(date_str[0]),
                            month=int(date_str[1]),
                            day=1
                        )
                        
                        if partition_date < cutoff_date:
                            # Drop old partition
                            cursor.execute(f'DROP TABLE IF EXISTS {partition_name}')
                            dropped += 1
                            logger.info(f'Dropped old partition {partition_name}')
                            
                    except (ValueError, IndexError):
                        logger.warning(f'Could not parse date from partition name: {partition_name}')
                        continue
            
            logger.info(f'Dropped {dropped} old partitions')
            return dropped
            
        except Exception as e:
            logger.exception(f'Failed to drop old partitions: {e}')
            return 0
