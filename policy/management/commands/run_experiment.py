from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from policy.models import Experiment, SyntheticUser, HumanLayerEvent, GroundTruthLabel, DetectionMetric
from policy.compliance import ComplianceEngine
import json, random
import subprocess
import platform
import tempfile
import os
import sys
import time
from policy import signing
import django


class Command(BaseCommand):
    help = 'Run a reproducible experiment: generate synthetic events for SyntheticUser, run compliance, and compute canonical metrics.'

    def add_arguments(self, parser):
        parser.add_argument('--experiment', required=True, help='Experiment name or id')
        parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility')
        parser.add_argument('--events-per-user', type=int, default=10)
        parser.add_argument('--scale', type=int, default=1, help='Scale factor for number of events')

    def handle(self, *args, **options):
        seed = options['seed']
        scale = options['scale']
        random.seed(seed)
        ex_q = options['experiment']
        try:
            exp = Experiment.objects.get(pk=ex_q)
        except Exception:
            exp = Experiment.objects.filter(name=ex_q).first()
        if not exp:
            self.stderr.write('Experiment not found')
            return

        users = list(exp.synthetic_users.all())
        if not users:
            self.stderr.write('No synthetic users attached to experiment')
            return

        # generate synthetic events (scaled)
        events_per_user = options['events_per_user'] * scale
        latencies = []
        
        for su in users:
            for i in range(events_per_user):
                details = {
                    'remote_addr': f'10.0.0.{random.randint(1,254)}',
                    'user_agent': random.choice(['bot','chrome','curl']),
                    'iteration': i,
                    'scale': scale,
                }
                ev = HumanLayerEvent.objects.create(
                    user=None,
                    event_type='auth',
                    source='synthetic',
                    summary=f'synth-{su.username}-{i}',
                    details=details,
                    related_policy=None
                )
                # optionally label ground truth if SyntheticUser attributes indicate violation
                is_violation = su.attributes.get('always_violate', False) if su.attributes else False
                GroundTruthLabel.objects.create(experiment=exp, event=ev, is_violation=is_violation)

        # run compliance against ACTIVE policies (timing)
        engine = ComplianceEngine()
        policies = []
        from policy.models import Policy
        for p in Policy.objects.filter(lifecycle='active'):
            policies.append(p)
            start = time.time()
            engine.evaluate_unprocessed(p, limit=10000)
            latencies.append(time.time() - start)

        # compute canonical metrics per-experiment
        labels = GroundTruthLabel.objects.filter(experiment=exp)
        tp = fp = tn = fn = 0
        for lbl in labels:
            detected = lbl.event.related_violation is not None
            if lbl.is_violation and detected:
                tp += 1
            elif lbl.is_violation and not detected:
                fn += 1
            elif not lbl.is_violation and detected:
                fp += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        # Store canonical metrics
        DetectionMetric.objects.create(experiment=exp, name='precision', value=precision)
        DetectionMetric.objects.create(experiment=exp, name='recall', value=recall)
        DetectionMetric.objects.create(experiment=exp, name='fpr', value=fpr)
        DetectionMetric.objects.create(experiment=exp, name='avg_policy_latency_s', value=avg_latency)
        DetectionMetric.objects.create(experiment=exp, name='seed', value=seed)
        DetectionMetric.objects.create(experiment=exp, name='scale', value=scale)
        DetectionMetric.objects.create(experiment=exp, name='events_generated', value=len(users) * events_per_user)

        # capture full environment metadata for reproducibility
        meta = {
            'experiment_id': exp.id,
            'experiment_name': exp.name,
            'seed': seed,
            'scale': scale,
            'timestamp': timezone.now().isoformat(),
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'django_version': django.get_version(),
            'python_executable': sys.executable,
        }
        
        # git commit (best-effort)
        try:
            meta['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd='.', stderr=subprocess.DEVNULL).decode().strip()
            meta['git_branch'] = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd='.', stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            meta['git_commit'] = None
            meta['git_branch'] = None
        
        # pip freeze (best-effort)
        try:
            meta['pip_freeze'] = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], stderr=subprocess.DEVNULL).decode()
        except Exception:
            meta['pip_freeze'] = None
        
        # container image ID (best-effort, check CONTAINER_IMAGE_ID env var or docker)
        meta['container_image_id'] = os.environ.get('CONTAINER_IMAGE_ID', None)
        if not meta['container_image_id']:
            try:
                # attempt to read /proc/self/cgroup for container ID
                with open('/proc/self/cgroup', 'r') as f:
                    for line in f:
                        if 'docker' in line:
                            meta['container_image_id'] = line.split('/')[-1].strip()
                            break
            except Exception:
                pass

        # write bundle and sign
        tmp = tempfile.mkdtemp()
        bundle_path = os.path.join(tmp, f"experiment_{exp.id}_bundle.json")
        bundle = {
            'meta': meta,
            'metrics': {
                'precision': precision,
                'recall': recall,
                'fpr': fpr,
                'avg_policy_latency_s': avg_latency,
                'tp': tp,
                'fp': fp,
                'tn': tn,
                'fn': fn,
            },
            'policies': [p.name for p in policies],
        }
        with open(bundle_path, 'w', encoding='utf-8') as bf:
            json.dump(bundle, bf, indent=2)

        # sign the bundle
        try:
            with open(bundle_path, 'rb') as bf:
                sig = signing.sign_bytes(bf.read())
            sig_path = bundle_path + '.sig'
            with open(sig_path, 'w', encoding='utf-8') as sf:
                json.dump({
                    'signature': sig,
                    'signer': getattr(settings, 'EVIDENCE_SIGNER', 'experiment-runner'),
                    'timestamp': timezone.now().isoformat(),
                    'algorithm': 'HMAC-SHA256'
                }, sf)
        except Exception as e:
            self.stderr.write(f'Failed to sign bundle: {e}')
            sig_path = None

        self.stdout.write(self.style.SUCCESS(f'Experiment {exp} completed successfully'))
        self.stdout.write(f'  Seed: {seed}, Scale: {scale}')
        self.stdout.write(f'  Events: {len(users) * events_per_user}, Labels: {labels.count()}')
        self.stdout.write(f'  Precision: {precision:.4f}, Recall: {recall:.4f}, FPR: {fpr:.4f}')
        self.stdout.write(f'  Avg Latency: {avg_latency:.4f}s')
        self.stdout.write(f'  Bundle: {bundle_path}')
        if sig_path:
            self.stdout.write(f'  Signature: {sig_path}')
        self.stdout.write(self.style.SUCCESS('✓ Metrics saved to DetectionMetric table'))
        self.stdout.write(self.style.SUCCESS('✓ Environment snapshot captured in bundle'))
