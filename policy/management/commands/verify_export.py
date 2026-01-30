from django.core.management.base import BaseCommand
from django.conf import settings
import json, hmac, hashlib

class Command(BaseCommand):
    help = 'Verify an NDJSON export against a detached .sig produced by the export command.'

    def add_arguments(self, parser):
        parser.add_argument('ndjson', help='Path to NDJSON export')
        parser.add_argument('sig', help='Path to detached signature file')

    def handle(self, *args, **options):
        nd = options['ndjson']
        sig = options['sig']
        key = getattr(settings, 'EVIDENCE_SIGNING_KEY', None)
        if not key:
            self.stderr.write('No EVIDENCE_SIGNING_KEY configured')
            return
        with open(sig, 'r', encoding='utf-8') as sf:
            meta = json.loads(sf.readline())
            sigs = [json.loads(line) for line in sf]
        ok = True
        with open(nd, 'r', encoding='utf-8') as nf:
            for i, line in enumerate(nf):
                line = line.rstrip('\n')
                mac = hmac.new(key.encode('utf-8'), line.encode('utf-8'), hashlib.sha256).hexdigest()
                expected = sigs[i].get('sig') if i < len(sigs) else None
                if mac != expected:
                    self.stderr.write(f'Mismatch at line {i}: expected {expected} got {mac}')
                    ok = False
        if ok:
            self.stdout.write('Verification OK')
        else:
            self.stderr.write('Verification FAILED')
