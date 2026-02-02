"""Management command to validate RiskScorer on labeled synthetic dataset.

Emits precision, recall, FPR, and latency metrics.
"""
from django.core.management.base import BaseCommand
from policy.models import Experiment, GroundTruthLabel, DetectionMetric, ScorerArtifact, HumanLayerEvent
from policy.risk import RiskScorer
from django.utils import timezone
import time
import hashlib
import json


class Command(BaseCommand):
    help = 'Run offline scorer validation on labeled synthetic dataset and emit metrics'

    def add_arguments(self, parser):
        parser.add_argument('--experiment-id', type=int, help='Experiment ID with ground truth labels')
        parser.add_argument('--scorer-name', default='default', help='Scorer artifact name')
        parser.add_argument('--scorer-version', default='1.0', help='Scorer artifact version')

    def handle(self, *args, **options):
        exp_id = options.get('experiment_id')
        scorer_name = options.get('scorer_name')
        scorer_version = options.get('scorer_version')

        if not exp_id:
            self.stdout.write(self.style.ERROR('--experiment-id is required'))
            raise SystemExit(1)

        try:
            experiment = Experiment.objects.get(id=exp_id)
        except Experiment.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Experiment {exp_id} not found'))
            raise SystemExit(1)

        labels = GroundTruthLabel.objects.filter(experiment=experiment).select_related('event')
        if not labels.exists():
            self.stdout.write(self.style.WARNING(f'No ground truth labels found for experiment {exp_id}'))
            raise SystemExit(2)

        scorer = RiskScorer()
        
        # Capture scorer config and hash
        scorer_config = {
            'name': scorer_name,
            'version': scorer_version,
            'params': scorer.weights,  # assuming weights is accessible
        }
        config_hash = hashlib.sha256(json.dumps(scorer_config, sort_keys=True).encode('utf-8')).hexdigest()

        # Get or create scorer artifact
        artifact, created = ScorerArtifact.objects.get_or_create(
            name=scorer_name,
            version=scorer_version,
            defaults={'config': scorer_config, 'sha256': config_hash}
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created scorer artifact: {artifact}'))
        else:
            self.stdout.write(f'Using existing scorer artifact: {artifact}')

        # Run scorer on all events
        tp = 0  # true positive
        fp = 0  # false positive
        tn = 0  # true negative
        fn = 0  # false negative
        latencies = []

        threshold = 0.5  # Risk threshold for binary classification

        for label in labels:
            event = label.event
            start = time.time()
            risk_score = scorer.score(event)
            latency = time.time() - start
            latencies.append(latency)

            predicted_violation = risk_score['score'] > threshold
            actual_violation = label.is_violation

            if predicted_violation and actual_violation:
                tp += 1
            elif predicted_violation and not actual_violation:
                fp += 1
            elif not predicted_violation and actual_violation:
                fn += 1
            else:
                tn += 1

        # Compute metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        # Store metrics
        DetectionMetric.objects.create(experiment=experiment, name='precision', value=precision)
        DetectionMetric.objects.create(experiment=experiment, name='recall', value=recall)
        DetectionMetric.objects.create(experiment=experiment, name='fpr', value=fpr)
        DetectionMetric.objects.create(experiment=experiment, name='avg_latency_ms', value=avg_latency * 1000)

        # Output
        self.stdout.write(self.style.SUCCESS(f'Scorer Validation Results (Experiment {exp_id}):'))
        self.stdout.write(f'  Scorer: {scorer_name} v{scorer_version} (hash: {config_hash[:16]}...)')
        self.stdout.write(f'  Labels: {labels.count()}')
        self.stdout.write(f'  Precision: {precision:.4f}')
        self.stdout.write(f'  Recall: {recall:.4f}')
        self.stdout.write(f'  FPR: {fpr:.4f}')
        self.stdout.write(f'  Avg Latency: {avg_latency*1000:.2f} ms')
        self.stdout.write(self.style.SUCCESS('Metrics saved to DetectionMetric table'))
