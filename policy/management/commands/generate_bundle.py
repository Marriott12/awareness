"""Generate signed bundle with data.csv, report.txt, and manifest.json."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from policy.models import Violation, ExportAudit
from policy import signing
import tempfile
import json
import os
import hashlib


class Command(BaseCommand):
    help = 'Generate signed report bundle (CSV + report + manifest) for governance'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=None, help='Output directory (default: temp)')
        parser.add_argument('--policy', help='Filter violations by policy name')
        parser.add_argument('--format', default='csv', choices=['csv', 'json'], help='Data format')

    def handle(self, *args, **options):
        output_dir = options.get('output_dir') or tempfile.mkdtemp()
        policy_filter = options.get('policy')
        data_format = options.get('format')

        # Query violations
        qs = Violation.objects.all()
        if policy_filter:
            qs = qs.filter(policy__name=policy_filter)

        violations = list(qs.select_related('policy', 'control', 'rule', 'user'))

        if not violations:
            self.stdout.write(self.style.WARNING('No violations found'))
            raise SystemExit(1)

        # Generate data file
        data_filename = f'violations.{data_format}'
        data_path = os.path.join(output_dir, data_filename)

        if data_format == 'csv':
            import csv
            with open(data_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'timestamp', 'policy', 'control', 'rule', 'severity', 'user', 'resolved'])
                for v in violations:
                    writer.writerow([
                        v.id,
                        v.timestamp.isoformat(),
                        v.policy.name,
                        v.control.name,
                        v.rule.name if v.rule else '',
                        v.severity,
                        v.user.username if v.user else '',
                        v.resolved,
                    ])
        else:  # json
            with open(data_path, 'w', encoding='utf-8') as f:
                data = [{
                    'id': v.id,
                    'timestamp': v.timestamp.isoformat(),
                    'policy': v.policy.name,
                    'control': v.control.name,
                    'rule': v.rule.name if v.rule else None,
                    'severity': v.severity,
                    'user': v.user.username if v.user else None,
                    'resolved': v.resolved,
                } for v in violations]
                json.dump(data, f, indent=2)

        # Generate report
        report_path = os.path.join(output_dir, 'report.txt')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('Violation Report\n')
            f.write('=' * 60 + '\n')
            f.write(f'Generated: {timezone.now().isoformat()}\n')
            f.write(f'Total Violations: {len(violations)}\n')
            f.write(f'Policy Filter: {policy_filter or "None"}\n\n')

            # Aggregations
            by_policy = {}
            by_severity = {}
            for v in violations:
                by_policy[v.policy.name] = by_policy.get(v.policy.name, 0) + 1
                by_severity[v.severity] = by_severity.get(v.severity, 0) + 1

            f.write('Violations by Policy:\n')
            for p, count in sorted(by_policy.items(), key=lambda x: -x[1]):
                f.write(f'  {p}: {count}\n')

            f.write('\nViolations by Severity:\n')
            for sev, count in sorted(by_severity.items(), key=lambda x: -x[1]):
                f.write(f'  {sev}: {count}\n')

        # Hash files
        def hash_file(path):
            with open(path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()

        data_hash = hash_file(data_path)
        report_hash = hash_file(report_path)

        # Generate manifest
        manifest = {
            'generated_at': timezone.now().isoformat(),
            'policy_filter': policy_filter,
            'violation_count': len(violations),
            'files': {
                data_filename: {'sha256': data_hash},
                'report.txt': {'sha256': report_hash},
            }
        }

        manifest_path = os.path.join(output_dir, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

        # Sign manifest
        manifest_hash = hash_file(manifest_path)
        sig = signing.sign_text(manifest_hash)

        signature_doc = {
            'manifest_hash': manifest_hash,
            'signature': sig,
            'timestamp': timezone.now().isoformat(),
            'algorithm': 'HMAC-SHA256',
        }

        sig_path = os.path.join(output_dir, 'bundle.sig')
        with open(sig_path, 'w', encoding='utf-8') as f:
            json.dump(signature_doc, f, indent=2)

        # Create export audit record
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # For CLI, no request user; use system user or None
        ExportAudit.objects.create(
            user=None,
            object_type='violation_bundle',
            object_count=len(violations),
            details={
                'bundle_path': output_dir,
                'manifest_hash': manifest_hash,
                'signature': sig[:16] + '...',
            }
        )

        self.stdout.write(self.style.SUCCESS(f'✓ Bundle generated: {output_dir}'))
        self.stdout.write(f'  Data: {data_filename}')
        self.stdout.write(f'  Report: report.txt')
        self.stdout.write(f'  Manifest: manifest.json')
        self.stdout.write(f'  Signature: bundle.sig')
        self.stdout.write(f'  Manifest Hash: {manifest_hash}')
