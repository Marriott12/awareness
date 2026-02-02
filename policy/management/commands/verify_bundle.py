"""Verify signed bundle integrity and signature."""
from django.core.management.base import BaseCommand
from policy import signing
import json
import os
import hashlib


class Command(BaseCommand):
    help = 'Verify signed bundle (manifest + signature)'

    def add_arguments(self, parser):
        parser.add_argument('bundle_dir', help='Path to bundle directory')

    def handle(self, *args, **options):
        bundle_dir = options['bundle_dir']

        if not os.path.isdir(bundle_dir):
            self.stdout.write(self.style.ERROR(f'Bundle directory not found: {bundle_dir}'))
            raise SystemExit(1)

        manifest_path = os.path.join(bundle_dir, 'manifest.json')
        sig_path = os.path.join(bundle_dir, 'bundle.sig')

        if not os.path.exists(manifest_path):
            self.stdout.write(self.style.ERROR('manifest.json not found'))
            raise SystemExit(1)

        if not os.path.exists(sig_path):
            self.stdout.write(self.style.ERROR('bundle.sig not found'))
            raise SystemExit(1)

        # Load signature doc
        with open(sig_path, 'r', encoding='utf-8') as f:
            sig_doc = json.load(f)

        expected_hash = sig_doc['manifest_hash']
        signature = sig_doc['signature']

        # Compute actual manifest hash
        with open(manifest_path, 'rb') as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()

        if actual_hash != expected_hash:
            self.stdout.write(self.style.ERROR('FAIL: Manifest hash mismatch'))
            self.stdout.write(f'  Expected: {expected_hash}')
            self.stdout.write(f'  Actual:   {actual_hash}')
            raise SystemExit(2)

        # Verify signature
        computed_sig = signing.sign_text(actual_hash)

        if computed_sig != signature:
            self.stdout.write(self.style.ERROR('FAIL: Signature verification failed'))
            self.stdout.write(f'  Expected: {signature}')
            self.stdout.write(f'  Computed: {computed_sig}')
            raise SystemExit(3)

        # Verify file hashes from manifest
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        for filename, meta in manifest.get('files', {}).items():
            file_path = os.path.join(bundle_dir, filename)
            if not os.path.exists(file_path):
                self.stdout.write(self.style.WARNING(f'File not found: {filename}'))
                continue

            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            expected_file_hash = meta.get('sha256')
            if file_hash != expected_file_hash:
                self.stdout.write(self.style.ERROR(f'FAIL: File hash mismatch for {filename}'))
                self.stdout.write(f'  Expected: {expected_file_hash}')
                self.stdout.write(f'  Actual:   {file_hash}')
                raise SystemExit(4)

            self.stdout.write(self.style.SUCCESS(f'✓ {filename}: hash OK'))

        self.stdout.write(self.style.SUCCESS('✓ Manifest hash: OK'))
        self.stdout.write(self.style.SUCCESS('✓ Signature: OK'))
        self.stdout.write(self.style.SUCCESS('PASS: Bundle verification successful'))
