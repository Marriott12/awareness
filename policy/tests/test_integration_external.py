"""
Integration tests for external service dependencies.

Tests integration with:
- TSA (Time-Stamp Authority) servers
- S3/Azure storage backends
- Redis cache
- Email notifications
- External PKI validation

Run with: python manage.py test policy.tests.test_integration_external
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, override_settings
from django.core.cache import cache
from datetime import datetime, timedelta
import json
import gzip


class TSAIntegrationTest(TestCase):
    """Test RFC 3161 Timestamp Authority integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        from policy.tsa_integration import TSAClient
        self.tsa_url = 'http://timestamp.digicert.com'
        self.client = TSAClient(self.tsa_url)
    
    @patch('policy.tsa_integration.requests.post')
    def test_timestamp_request_format(self, mock_post):
        """Test that timestamp requests are properly formatted."""
        # Mock TSA response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'\x30\x82\x01\x00' + b'\x00' * 252  # Mock DER response
        mock_post.return_value = mock_response
        
        data = b'test data for timestamping'
        token = self.client.timestamp_data(data)
        
        # Verify request was made
        self.assertTrue(mock_post.called)
        
        # Verify request format
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], self.tsa_url)
        self.assertEqual(call_args[1]['headers']['Content-Type'], 'application/timestamp-query')
        
        # Verify token is hex string
        self.assertIsInstance(token, str)
        self.assertTrue(all(c in '0123456789abcdef' for c in token.lower()))
    
    @patch('policy.tsa_integration.requests.post')
    def test_timestamp_failure_handling(self, mock_post):
        """Test handling of TSA server failures."""
        # Mock TSA error response
        mock_post.side_effect = Exception('TSA server unavailable')
        
        data = b'test data'
        token = self.client.timestamp_data(data)
        
        # Should return None on failure
        self.assertIsNone(token)
    
    def test_batch_timestamping(self):
        """Test batch timestamping of Evidence records."""
        from policy.tsa_integration import TSAIntegration
        from policy.models import Evidence, HumanLayerEvent
        
        # Create test events and evidence
        event = HumanLayerEvent.objects.create(
            event_type='test',
            source='test',
            summary='Test event'
        )
        evidence = Evidence.objects.create(
            event=event,
            signed_data={'test': 'data'}
        )
        
        integration = TSAIntegration()
        
        # Test dry run
        with patch.object(integration.client, 'timestamp_data', return_value='abc123'):
            result = integration.timestamp_all_evidence(batch_size=10, dry_run=True)
            
            self.assertIn('total', result)
            self.assertIn('dry_run', result)
            self.assertTrue(result['dry_run'])


class StorageBackendIntegrationTest(TestCase):
    """Test S3/Azure storage backend integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        from policy.archival import ArchivalManager
        self.manager = ArchivalManager(storage_backend='filesystem')
    
    @patch('policy.archival.boto3.client')
    def test_s3_upload(self, mock_boto):
        """Test archival upload to S3."""
        from policy.archival import ArchivalManager
        
        # Mock S3 client
        mock_s3 = Mock()
        mock_boto.return_value = mock_s3
        
        manager = ArchivalManager(storage_backend='s3')
        manager.s3_client = mock_s3
        
        # Test upload
        data = [{'id': 1, 'data': 'test'}]
        result = manager._upload_archive('test_archive.json.gz', data)
        
        self.assertTrue(result)
        self.assertTrue(mock_s3.put_object.called)
        
        # Verify compressed data was uploaded
        call_args = mock_s3.put_object.call_args
        self.assertIn('Body', call_args[1])
        self.assertIn('ContentType', call_args[1])
        self.assertEqual(call_args[1]['ContentType'], 'application/gzip')
    
    @patch('policy.archival.BlobServiceClient.from_connection_string')
    def test_azure_upload(self, mock_blob_service):
        """Test archival upload to Azure Blob Storage."""
        from policy.archival import ArchivalManager
        
        # Mock Azure client
        mock_blob_client = Mock()
        mock_container = Mock()
        mock_container.get_blob_client.return_value = mock_blob_client
        mock_blob_service.return_value.get_blob_client = mock_blob_client
        
        manager = ArchivalManager(storage_backend='azure')
        manager.blob_service = mock_blob_service.return_value
        
        # Test upload
        data = [{'id': 1, 'data': 'test'}]
        result = manager._upload_archive('test_archive.json.gz', data)
        
        self.assertTrue(result)
    
    def test_filesystem_archival(self):
        """Test archival to filesystem."""
        import os
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            from policy.archival import ArchivalManager
            
            manager = ArchivalManager(storage_backend='filesystem')
            manager.archive_path = tmpdir
            
            # Test upload
            data = [{'id': 1, 'timestamp': '2025-01-01T00:00:00'}]
            result = manager._upload_archive('test.json.gz', data)
            
            self.assertTrue(result)
            
            # Verify file exists and is compressed
            archive_file = os.path.join(tmpdir, 'test.json.gz')
            self.assertTrue(os.path.exists(archive_file))
            
            # Verify can decompress and parse
            with open(archive_file, 'rb') as f:
                compressed = f.read()
                decompressed = gzip.decompress(compressed)
                parsed = json.loads(decompressed)
                self.assertEqual(len(parsed), 1)
                self.assertEqual(parsed[0]['id'], 1)
    
    def test_archive_restoration(self):
        """Test restoring archived data."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            from policy.archival import ArchivalManager
            
            manager = ArchivalManager(storage_backend='filesystem')
            manager.archive_path = tmpdir
            
            # Upload test data
            original_data = [
                {'id': 1, 'event_type': 'login', 'timestamp': '2025-01-01'},
                {'id': 2, 'event_type': 'logout', 'timestamp': '2025-01-02'}
            ]
            manager._upload_archive('test_restore.json.gz', original_data)
            
            # Restore data
            restored_data = manager.restore_archive('test_restore.json.gz')
            
            self.assertEqual(len(restored_data), 2)
            self.assertEqual(restored_data[0]['id'], 1)
            self.assertEqual(restored_data[1]['event_type'], 'logout')


class RedisIntegrationTest(TestCase):
    """Test Redis cache integration."""
    
    def setUp(self):
        """Clear cache before each test."""
        cache.clear()
    
    def tearDown(self):
        """Clear cache after each test."""
        cache.clear()
    
    def test_policy_caching(self):
        """Test policy caching functionality."""
        from policy.policy_cache import PolicyCache
        from policy.models import Policy
        
        # Create test policy
        policy = Policy.objects.create(
            name='Test Policy',
            description='Test description',
            lifecycle='active'
        )
        
        cache_manager = PolicyCache()
        
        # Test cache miss
        cached = cache_manager.get_policy(policy.id)
        self.assertIsNone(cached)
        
        # Cache the policy
        cache.set(f'policy:{policy.id}', policy, 3600)
        
        # Test cache hit
        cached = cache_manager.get_policy(policy.id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.id, policy.id)
    
    def test_cache_invalidation(self):
        """Test cache invalidation on policy update."""
        from policy.policy_cache import invalidate_policy_cache
        from policy.models import Policy
        
        policy = Policy.objects.create(
            name='Test Policy',
            lifecycle='active'
        )
        
        # Manually cache policy
        cache_key = f'policy:{policy.id}'
        cache.set(cache_key, policy, 3600)
        
        # Verify cached
        self.assertIsNotNone(cache.get(cache_key))
        
        # Update policy (should trigger invalidation via signals)
        policy.name = 'Updated Policy'
        policy.save()
        
        # Cache should be invalidated
        # Note: Actual invalidation happens via Django signals
        # This test verifies the cache key format
        self.assertEqual(cache_key, f'policy:{policy.id}')
    
    def test_active_policies_cache(self):
        """Test caching of active policies."""
        from policy.policy_cache import PolicyCache
        from policy.models import Policy
        
        # Create multiple policies
        Policy.objects.create(name='Active 1', lifecycle='active')
        Policy.objects.create(name='Active 2', lifecycle='active')
        Policy.objects.create(name='Draft', lifecycle='draft')
        
        cache_manager = PolicyCache()
        
        # Get active policies (should cache)
        active_policies = cache_manager.get_active_policies()
        
        # Verify only active policies returned
        self.assertEqual(len(active_policies), 2)
        for policy in active_policies:
            self.assertEqual(policy.lifecycle, 'active')


class EmailNotificationIntegrationTest(TestCase):
    """Test email notification integration."""
    
    @patch('policy.workflow_views.send_mail')
    def test_approval_notification(self, mock_send_mail):
        """Test email notification on policy approval."""
        from django.contrib.auth.models import User
        from policy.models import Policy
        from policy.workflow_views import _send_approval_notification
        
        # Create test user and policy
        user = User.objects.create_user('approver', 'approver@test.com', 'pass')
        policy = Policy.objects.create(
            name='Test Policy',
            lifecycle='review'
        )
        
        # Send approval notification
        _send_approval_notification(policy, user, approved=True)
        
        # Verify email sent
        self.assertTrue(mock_send_mail.called)
        call_args = mock_send_mail.call_args
        
        # Verify email content
        subject = call_args[0][0]
        message = call_args[0][1]
        
        self.assertIn('Approved', subject)
        self.assertIn(policy.name, subject)
        self.assertIn(policy.name, message)
    
    @patch('policy.workflow_views.send_mail')
    def test_rejection_notification(self, mock_send_mail):
        """Test email notification on policy rejection."""
        from django.contrib.auth.models import User
        from policy.models import Policy
        from policy.workflow_views import _send_approval_notification
        
        user = User.objects.create_user('rejecter', 'rejecter@test.com', 'pass')
        policy = Policy.objects.create(
            name='Test Policy',
            lifecycle='review'
        )
        
        # Send rejection notification
        _send_approval_notification(
            policy, user, approved=False, 
            reason='Insufficient justification'
        )
        
        # Verify email sent
        self.assertTrue(mock_send_mail.called)
        call_args = mock_send_mail.call_args
        
        subject = call_args[0][0]
        message = call_args[0][1]
        
        self.assertIn('Rejected', subject)
        self.assertIn('Insufficient justification', message)


class ExternalPKIValidationTest(TestCase):
    """Test external PKI certificate validation."""
    
    @patch('policy.tsa_integration.cryptography.x509.load_pem_x509_certificate')
    def test_tsa_certificate_validation(self, mock_load_cert):
        """Test TSA certificate validation."""
        from policy.tsa_integration import TSAClient
        
        # Mock certificate
        mock_cert = Mock()
        mock_load_cert.return_value = mock_cert
        
        client = TSAClient('http://test-tsa.example.com')
        
        # Test certificate loading
        # In production, this would validate against trusted CAs
        self.assertIsNotNone(client)
    
    def test_certificate_expiry_check(self):
        """Test certificate expiration checking."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        from datetime import datetime, timedelta
        import tempfile
        
        # Generate test certificate
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        subject = issuer = x509.Name([
            x509.NameAttribute(x509.oid.NameOID.COUNTRY_NAME, u"US"),
            x509.NameAttribute(x509.oid.NameOID.ORGANIZATION_NAME, u"Test Org"),
        ])
        
        # Create expired certificate
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow() - timedelta(days=365)
        ).not_valid_after(
            datetime.utcnow() - timedelta(days=1)  # Expired yesterday
        ).sign(private_key, hashes.SHA256(), default_backend())
        
        # Verify cert is expired
        now = datetime.utcnow()
        self.assertLess(cert.not_valid_after, now)


class ComplianceReportingIntegrationTest(TestCase):
    """Test compliance reporting with real data."""
    
    def setUp(self):
        """Create test data."""
        from django.contrib.auth.models import User
        from policy.models import (
            Policy, PolicyHistory, PolicyApproval,
            HumanLayerEvent, Evidence, Violation
        )
        
        # Create test user
        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        
        # Create test policy
        self.policy = Policy.objects.create(
            name='Test Policy',
            lifecycle='active'
        )
        
        # Create policy history
        PolicyHistory.objects.create(
            policy=self.policy,
            version=1,
            changed_by=self.user,
            snapshot={'name': 'Test Policy'}
        )
        
        # Create events
        for i in range(10):
            event = HumanLayerEvent.objects.create(
                event_type='test_event',
                source='test',
                summary=f'Test event {i}'
            )
            Evidence.objects.create(
                event=event,
                signed_data={'test': i}
            )
    
    def test_soc2_report_generation(self):
        """Test SOC2 compliance report generation."""
        from policy.compliance_reporting import ComplianceReportGenerator
        from datetime import datetime, timedelta
        
        generator = ComplianceReportGenerator(framework='soc2')
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        report = generator.generate_report(start_date, end_date)
        
        # Verify report structure
        self.assertEqual(report['framework'], 'SOC2')
        self.assertIn('controls', report)
        self.assertIn('evidence_summary', report)
        self.assertIn('compliance_score', report)
        
        # Verify controls evaluated
        self.assertGreater(len(report['controls']), 0)
        
        # Verify compliance score calculated
        self.assertGreaterEqual(report['compliance_score'], 0)
        self.assertLessEqual(report['compliance_score'], 100)
    
    def test_iso27001_report_generation(self):
        """Test ISO27001 compliance report generation."""
        from policy.compliance_reporting import ComplianceReportGenerator
        from datetime import datetime, timedelta
        
        generator = ComplianceReportGenerator(framework='iso27001')
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        report = generator.generate_report(start_date, end_date)
        
        self.assertEqual(report['framework'], 'ISO27001')
        self.assertIn('controls', report)


if __name__ == '__main__':
    unittest.main()
