import json
import hmac
import hashlib
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from policy.models import Evidence, HumanLayerEvent


class Command(BaseCommand):
    help = 'Export Evidence and HumanLayerEvent records as NDJSON to stdout (optionally signed)'

    def add_arguments(self, parser):
        parser.add_argument('--since', help='ISO timestamp to filter records since', required=False)
        parser.add_argument('--event-type', help='Filter human events by event_type (auth/quiz/training)', required=False)
        parser.add_argument('--sign', action='store_true', help='Sign each line with HMAC using SECRET_KEY')
        parser.add_argument('--output-file', help='Write NDJSON to this file (and signature to file.sig)')
        parser.add_argument('--detached', action='store_true', help='Write a detached signature file alongside output file')
        parser.add_argument('--signer', help='Signer name to include in signature metadata', required=False)

    def _sign_line(self, line: str) -> str:
        key = getattr(settings, 'EVIDENCE_SIGNING_KEY', settings.SECRET_KEY)
        mac = hmac.new(key.encode('utf-8'), line.encode('utf-8'), hashlib.sha256).hexdigest()
        return f"{mac} {line}"

    def handle(self, *args, **options):
        since = options.get('since')
        etype = options.get('event_type')
        sign = options.get('sign')
        qs_e = Evidence.objects.all().order_by('created_at')
        qs_h = HumanLayerEvent.objects.all().order_by('timestamp')
        if since:
            from django.utils.dateparse import parse_datetime

            dt = parse_datetime(since)
            if dt:
                qs_e = qs_e.filter(created_at__gte=dt)
                qs_h = qs_h.filter(timestamp__gte=dt)
        if etype:
            qs_h = qs_h.filter(event_type=etype)

        # prepare output destination(s)
        output_path = options.get('output_file')
        detached = options.get('detached')
        signer = options.get('signer') or getattr(settings, 'EVIDENCE_SIGNER', None)

        if output_path:
            out_f = open(output_path, 'w', encoding='utf-8')
        else:
            out_f = self.stdout

        sig_lines = []
        for ev in qs_e.iterator():
            line = json.dumps({'type': 'evidence', 'id': ev.pk, 'created_at': ev.created_at.isoformat(), 'payload': ev.payload}, default=str)
            if sign and not detached:
                out_f.write(self._sign_line(line) + '\n')
            else:
                out_f.write(line + '\n')
            if sign and detached:
                mac = hmac.new((getattr(settings, 'EVIDENCE_SIGNING_KEY', settings.SECRET_KEY)).encode('utf-8'), line.encode('utf-8'), hashlib.sha256).hexdigest()
                sig_lines.append({'id': ev.pk, 'sig': mac})

        for he in qs_h.iterator():
            line = json.dumps({'type': 'human_event', 'id': str(he.pk), 'timestamp': he.timestamp.isoformat(), 'event_type': he.event_type, 'user': he.user and he.user.username, 'summary': he.summary, 'details': he.details}, default=str)
            if sign and not detached:
                out_f.write(self._sign_line(line) + '\n')
            else:
                out_f.write(line + '\n')
            if sign and detached:
                mac = hmac.new((getattr(settings, 'EVIDENCE_SIGNING_KEY', settings.SECRET_KEY)).encode('utf-8'), line.encode('utf-8'), hashlib.sha256).hexdigest()
                sig_lines.append({'id': str(he.pk), 'sig': mac})

        if output_path:
            out_f.close()

        # write detached signature file and metadata if requested
        if sign and detached and output_path:
            import os
            meta = {'signer': signer or 'unknown', 'timestamp': timezone.now().isoformat(), 'file': output_path}
            sig_path = output_path + '.sig'
            with open(sig_path, 'w', encoding='utf-8') as sf:
                sf.write(json.dumps({'meta': meta}) + '\n')
                for s in sig_lines:
                    sf.write(json.dumps(s) + '\n')