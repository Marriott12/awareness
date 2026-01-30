from django.test import TestCase, override_settings
from unittest.mock import MagicMock, patch


class SigningTests(TestCase):
    def test_local_sign(self):
        with override_settings(EVIDENCE_SIGNING_KEY='testkey'):
            from policy import signing
            sig = signing.sign_text('hello')
            # sha256 hex length 64
            self.assertEqual(len(sig), 64)

    def test_aws_kms_sign_mock(self):
        # Mock boto3 client generate_mac
        fake_mac = b'\x01\x02\x03'
        fake_client = MagicMock()
        fake_client.generate_mac.return_value = {'Mac': fake_mac}

        with override_settings(SIGNING_PROVIDER='aws_kms', AWS_KMS_KEY_ID='alias/test'):
            # inject fake boto3 into sys.modules so signing._aws_kms_sign can import it
            fake_boto3 = MagicMock()
            fake_boto3.client.return_value = fake_client
            with patch.dict('sys.modules', {'boto3': fake_boto3}):
                from policy import signing
                res = signing.sign_text('payload')
                self.assertEqual(res, fake_mac.hex())

    def test_vault_sign_mock(self):
        # Mock hvac client transit.generate_mac returning base64 mac
        import base64
        raw_mac = b'\x0a\x0b\x0c'
        mac_b64 = base64.b64encode(raw_mac).decode('ascii')

        class FakeTransit:
            def generate_mac(self, name, input):
                return {'data': {'mac': mac_b64}}

        class FakeClient:
            def __init__(self, url=None, token=None):
                self.secrets = MagicMock()
                self.secrets.transit = FakeTransit()

        with override_settings(SIGNING_PROVIDER='vault', VAULT_URL='http://x', VAULT_TOKEN='t', VAULT_TRANSIT_KEY='k'):
            fake_hvac = MagicMock()
            fake_hvac.Client.return_value = FakeClient()
            with patch.dict('sys.modules', {'hvac': fake_hvac}):
                from policy import signing
                res = signing.sign_text('payload')
                self.assertEqual(res, raw_mac.hex())
