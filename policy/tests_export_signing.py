import tempfile
import os
import json
import hmac
import hashlib
from django.test import TestCase
from django.core.management import call_command
from django.conf import settings


class ExportSigningTests(TestCase):
    def test_detached_signature_matches_lines(self):
        # run export_evidence to a temp file with detached signature
        td = tempfile.TemporaryDirectory()
        out = os.path.join(td.name, 'out.ndjson')
        # Set a known signing key in settings for test
        settings.EVIDENCE_SIGNING_KEY = 'test-signing-key'
        call_command('export_evidence', '--output-file', out, '--detached', '--sign')
        # verify signature file exists
        sig_path = out + '.sig'
        self.assertTrue(os.path.exists(out))
        self.assertTrue(os.path.exists(sig_path))
        # read ndjson and signature lines
        lines = [l.strip() for l in open(out, 'r', encoding='utf-8') if l.strip()]
        sigs = [json.loads(l) for l in open(sig_path, 'r', encoding='utf-8')]
        # first sig entry is meta; following are signatures
        self.assertIn('meta', sigs[0])
        sig_entries = sigs[1:]
        # compute macs and compare
        for i, line in enumerate(lines):
            mac = hmac.new(settings.EVIDENCE_SIGNING_KEY.encode('utf-8'), line.encode('utf-8'), hashlib.sha256).hexdigest()
            self.assertEqual(mac, sig_entries[i]['sig'])
