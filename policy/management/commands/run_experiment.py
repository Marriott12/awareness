from django.core.management.base import BaseCommand
from django.utils import timezone
from policy.models import Experiment, SyntheticUser, HumanLayerEvent, GroundTruthLabel, DetectionMetric
from policy.compliance import ComplianceEngine
import json, random
import subprocess
import platform
import tempfile
from policy import signing

class Command(BaseCommand):
    help = 'Run a reproducible experiment: generate synthetic events for SyntheticUser, run compliance, and compute basic metrics.'

    def add_arguments(self, parser):
        parser.add_argument('--experiment', required=True, help='Experiment name or id')
        parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility')
        parser.add_argument('--events-per-user', type=int, default=10)

    def handle(self, *args, **options):
        seed = options['seed']
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

        # generate synthetic events
        for su in users:
            for i in range(options['events_per_user']):
                details = {'remote_addr': f'10.0.0.{random.randint(1,254)}', 'user_agent': random.choice(['bot','chrome','curl'])}
                ev = HumanLayerEvent.objects.create(user=None, event_type='auth', source='synthetic', summary=f'synth-{su.username}-{i}', details=details, related_policy=None)
                # optionally label ground truth if SyntheticUser attributes indicate violation
                is_violation = su.attributes.get('always_violate', False) if su.attributes else False
                GroundTruthLabel.objects.create(experiment=exp, event=ev, is_violation=is_violation)

        # run compliance against policies
        engine = ComplianceEngine()
        policies = []
        from policy.models import Policy
        for p in Policy.objects.filter(active=True):
            policies.append(p)
            engine.evaluate_unprocessed(p, limit=1000)

        # compute simple metrics per-experiment
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

        DetectionMetric.objects.create(experiment=exp, name='precision', value=precision)
        DetectionMetric.objects.create(experiment=exp, name='recall', value=recall)
        DetectionMetric.objects.create(experiment=exp, name='fpr', value=fpr)
        DetectionMetric.objects.create(experiment=exp, name='seed', value=seed)

        # capture environment metadata
        meta = {
            'experiment': exp.id,
            'seed': seed,
            'timestamp': timezone.now().isoformat(),
            'platform': platform.platform(),
            'python_version': platform.python_version(),
        }
        # git commit and pip freeze (best-effort)
        try:
            meta['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd='.', stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            meta['git_commit'] = None
        try:
            meta['pip_freeze'] = subprocess.check_output(['pip', 'freeze'], stderr=subprocess.DEVNULL).decode()
        except Exception:
            meta['pip_freeze'] = None

        # write bundle and sign
        tmp = tempfile.mkdtemp()
        bundle_path = f"{tmp}/experiment_{exp.id}_bundle.json"
        bundle = {'meta': meta, 'metrics': {'precision': precision, 'recall': recall, 'fpr': fpr}}
        with open(bundle_path, 'w', encoding='utf-8') as bf:
            json.dump(bundle, bf)

        # sign the bundle
        try:
            with open(bundle_path, 'rb') as bf:
                sig = signing.sign_bytes(bf.read())
            sig_path = bundle_path + '.sig'
            with open(sig_path, 'w', encoding='utf-8') as sf:
                sf.write(json.dumps({'signature': sig, 'signer': getattr(settings, 'EVIDENCE_SIGNER', 'experiment-runner'), 'timestamp': timezone.now().isoformat()}))
        except Exception:
            sig_path = None

        self.stdout.write(f'Experiment {exp} done. precision={precision}, recall={recall}, fpr={fpr}. bundle={bundle_path} sig={sig_path}')
