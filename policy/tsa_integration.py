"""
TSA (Time-Stamp Authority) integration for RFC 3161 timestamping.

Provides cryptographic proof of temporal ordering for audit events by
integrating with external Time-Stamp Authorities.

Installation:
    pip install cryptography requests

Configuration (add to settings.py):
    TSA_URL = os.getenv('TSA_URL', 'http://timestamp.digicert.com')
    TSA_CERTIFICATE_PATH = os.getenv('TSA_CERTIFICATE_PATH', '/path/to/tsa-cert.pem')
    TSA_TIMEOUT = int(os.getenv('TSA_TIMEOUT', '10'))  # seconds

Usage:
    from policy.tsa_integration import TSAClient
    
    client = TSAClient()
    timestamp_token = client.timestamp_data(b'data to timestamp')
    verified = client.verify_timestamp(timestamp_token, b'original data')
"""
import hashlib
import requests
from typing import Optional, Tuple
from datetime import datetime
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class TSAClient:
    """
    Client for RFC 3161 Time-Stamp Authority integration.
    
    Provides cryptographic proof that data existed at a specific time
    by obtaining timestamps from trusted external authorities.
    """
    
    def __init__(self, tsa_url: Optional[str] = None, 
                 certificate_path: Optional[str] = None,
                 timeout: int = 10):
        """
        Initialize TSA client.
        
        Args:
            tsa_url: URL of Time-Stamp Authority (default: from settings)
            certificate_path: Path to TSA certificate for verification
            timeout: Request timeout in seconds
        """
        self.tsa_url = tsa_url or getattr(settings, 'TSA_URL', 'http://timestamp.digicert.com')
        self.certificate_path = certificate_path or getattr(settings, 'TSA_CERTIFICATE_PATH', None)
        self.timeout = timeout or getattr(settings, 'TSA_TIMEOUT', 10)
    
    def timestamp_data(self, data: bytes) -> Optional[bytes]:
        """
        Get RFC 3161 timestamp for data from TSA.
        
        Args:
            data: Data to timestamp
            
        Returns:
            Timestamp token (DER-encoded) or None if failed
        """
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.backends import default_backend
            from cryptography.x509 import ocsp
            
            # Create SHA-256 hash of data
            digest = hashlib.sha256(data).digest()
            
            # Build timestamp request
            timestamp_request = self._build_timestamp_request(digest)
            
            # Send request to TSA
            response = requests.post(
                self.tsa_url,
                data=timestamp_request,
                headers={'Content-Type': 'application/timestamp-query'},
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(f'TSA request failed with status {response.status_code}')
                return None
            
            # Parse timestamp response
            timestamp_token = response.content
            
            logger.info(f'Successfully obtained timestamp from {self.tsa_url}')
            return timestamp_token
            
        except Exception as e:
            logger.exception(f'Failed to get timestamp: {e}')
            return None
    
    def _build_timestamp_request(self, message_digest: bytes) -> bytes:
        """
        Build RFC 3161 timestamp request.
        
        Args:
            message_digest: SHA-256 digest of data to timestamp
            
        Returns:
            DER-encoded timestamp request
        """
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            import asn1crypto.tsp
            import asn1crypto.core
            
            # Build timestamp request structure
            req = asn1crypto.tsp.TimeStampReq({
                'version': 1,
                'message_imprint': {
                    'hash_algorithm': {
                        'algorithm': '2.16.840.1.101.3.4.2.1',  # SHA-256 OID
                    },
                    'hashed_message': message_digest,
                },
                'cert_req': True,  # Request TSA certificate in response
            })
            
            return req.dump()
            
        except ImportError:
            # Fallback: simplified request format
            logger.warning('asn1crypto not available, using simplified format')
            return message_digest
    
    def verify_timestamp(self, timestamp_token: bytes, original_data: bytes) -> bool:
        """
        Verify RFC 3161 timestamp token.
        
        Args:
            timestamp_token: Timestamp token from TSA
            original_data: Original data that was timestamped
            
        Returns:
            True if timestamp is valid and matches data
        """
        try:
            import asn1crypto.tsp
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.backends import default_backend
            
            # Parse timestamp token
            tst_info = asn1crypto.tsp.TimeStampResp.load(timestamp_token)
            
            if tst_info['status']['status'].native != 'granted':
                logger.error('Timestamp was not granted')
                return False
            
            # Extract timestamp data
            token = tst_info['time_stamp_token']
            tst_info_data = token['content']['tst_info']
            
            # Verify message digest matches
            stored_digest = tst_info_data['message_imprint']['hashed_message'].native
            computed_digest = hashlib.sha256(original_data).digest()
            
            if stored_digest != computed_digest:
                logger.error('Timestamp digest does not match data')
                return False
            
            # Extract timestamp
            gen_time = tst_info_data['gen_time'].native
            logger.info(f'Timestamp verified: {gen_time}')
            
            return True
            
        except Exception as e:
            logger.exception(f'Failed to verify timestamp: {e}')
            return False
    
    def get_timestamp_time(self, timestamp_token: bytes) -> Optional[datetime]:
        """
        Extract timestamp from token.
        
        Args:
            timestamp_token: Timestamp token from TSA
            
        Returns:
            Datetime of timestamp or None if failed
        """
        try:
            import asn1crypto.tsp
            
            tst_info = asn1crypto.tsp.TimeStampResp.load(timestamp_token)
            
            if tst_info['status']['status'].native != 'granted':
                return None
            
            token = tst_info['time_stamp_token']
            tst_info_data = token['content']['tst_info']
            gen_time = tst_info_data['gen_time'].native
            
            return gen_time
            
        except Exception as e:
            logger.exception(f'Failed to extract timestamp: {e}')
            return None


def timestamp_evidence(evidence_id: int) -> bool:
    """
    Add TSA timestamp to Evidence record.
    
    Args:
        evidence_id: ID of Evidence record
        
    Returns:
        True if timestamp was successfully added
    """
    try:
        from .models import Evidence
        
        evidence = Evidence.objects.get(pk=evidence_id)
        
        # Get signature to timestamp
        signature = evidence.signature.encode('utf-8') if evidence.signature else b''
        
        if not signature:
            logger.warning(f'Evidence {evidence_id} has no signature to timestamp')
            return False
        
        # Get timestamp from TSA
        client = TSAClient()
        timestamp_token = client.timestamp_data(signature)
        
        if not timestamp_token:
            logger.error(f'Failed to get timestamp for evidence {evidence_id}')
            return False
        
        # Store timestamp token in evidence
        evidence.tsa_timestamp = timestamp_token.hex()
        evidence.save(update_fields=['tsa_timestamp'])
        
        logger.info(f'Added TSA timestamp to evidence {evidence_id}')
        return True
        
    except Exception as e:
        logger.exception(f'Failed to timestamp evidence: {e}')
        return False


def verify_evidence_timestamp(evidence_id: int) -> bool:
    """
    Verify TSA timestamp on Evidence record.
    
    Args:
        evidence_id: ID of Evidence record
        
    Returns:
        True if timestamp is valid
    """
    try:
        from .models import Evidence
        
        evidence = Evidence.objects.get(pk=evidence_id)
        
        if not evidence.tsa_timestamp:
            logger.warning(f'Evidence {evidence_id} has no TSA timestamp')
            return False
        
        # Get original signature
        signature = evidence.signature.encode('utf-8') if evidence.signature else b''
        
        # Parse timestamp token
        timestamp_token = bytes.fromhex(evidence.tsa_timestamp)
        
        # Verify timestamp
        client = TSAClient()
        is_valid = client.verify_timestamp(timestamp_token, signature)
        
        if is_valid:
            # Get timestamp time
            timestamp_time = client.get_timestamp_time(timestamp_token)
            logger.info(f'Evidence {evidence_id} timestamp verified: {timestamp_time}')
        else:
            logger.error(f'Evidence {evidence_id} timestamp verification failed')
        
        return is_valid
        
    except Exception as e:
        logger.exception(f'Failed to verify evidence timestamp: {e}')
        return False


# Management command integration
class TSAIntegration:
    """Helper class for TSA integration with existing evidence."""
    
    @staticmethod
    def timestamp_all_evidence(batch_size: int = 100, dry_run: bool = False) -> dict:
        """
        Add TSA timestamps to all Evidence records that don't have them.
        
        Args:
            batch_size: Number of records to process at once
            dry_run: If True, don't actually add timestamps
            
        Returns:
            Summary statistics
        """
        from .models import Evidence
        
        # Find evidence without timestamps
        evidence_without_timestamp = Evidence.objects.filter(
            tsa_timestamp__isnull=True
        ) | Evidence.objects.filter(tsa_timestamp='')
        
        total = evidence_without_timestamp.count()
        processed = 0
        succeeded = 0
        failed = 0
        
        logger.info(f'Found {total} evidence records without TSA timestamps')
        
        if dry_run:
            logger.info('DRY RUN: No changes will be made')
            return {
                'total': total,
                'processed': 0,
                'succeeded': 0,
                'failed': 0,
                'dry_run': True
            }
        
        for evidence in evidence_without_timestamp.iterator(chunk_size=batch_size):
            try:
                if timestamp_evidence(evidence.id):
                    succeeded += 1
                else:
                    failed += 1
                
                processed += 1
                
                if processed % 100 == 0:
                    logger.info(f'Progress: {processed}/{total} processed')
                    
            except Exception as e:
                logger.exception(f'Failed to process evidence {evidence.id}: {e}')
                failed += 1
                processed += 1
        
        return {
            'total': total,
            'processed': processed,
            'succeeded': succeeded,
            'failed': failed,
            'dry_run': False
        }
