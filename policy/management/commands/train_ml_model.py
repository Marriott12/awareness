"""Management command to train ML risk scoring model.

Usage:
    python manage.py train_ml_model --experiment-id 123
    python manage.py train_ml_model --use-all-labels --algorithm gradient_boosting
"""
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from policy.ml_scorer import MLRiskScorer, SKLEARN_AVAILABLE
from policy.models import Experiment, GroundTruthLabel


class Command(BaseCommand):
    help = 'Train ML model for risk scoring using labeled data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--experiment-id',
            type=int,
            help='Experiment ID with ground truth labels'
        )
        parser.add_argument(
            '--use-all-labels',
            action='store_true',
            help='Use all labeled data across experiments'
        )
        parser.add_argument(
            '--algorithm',
            default='random_forest',
            choices=['random_forest', 'gradient_boosting'],
            help='ML algorithm to use'
        )
        parser.add_argument(
            '--no-tuning',
            action='store_true',
            help='Skip hyperparameter tuning (faster)'
        )
        parser.add_argument(
            '--model-version',
            dest='model_version',
            default=None,
            help='Model version tag (default: settings.ML_MODEL_VERSION)'
        )
        parser.add_argument(
            '--cv-folds',
            type=int,
            default=5,
            help='Cross-validation folds (default: 5)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Allow training even when label counts are below recommended thresholds'
        )

    def handle(self, *args, **options):
        if not SKLEARN_AVAILABLE:
            self.stdout.write(self.style.ERROR(
                'scikit-learn not installed. Run: pip install scikit-learn'
            ))
            sys.exit(1)

        exp_id = options.get('experiment_id')
        use_all = options.get('use_all_labels')
        algorithm = options['algorithm']
        tune = not options['no_tuning']
        version = options['model_version'] or getattr(settings, 'ML_MODEL_VERSION', '1.0')
        cv_folds = options['cv_folds']
        force = options['force']

        if not exp_id and not use_all:
            self.stdout.write(self.style.ERROR(
                'Specify --experiment-id or --use-all-labels'
            ))
            sys.exit(1)

        if use_all:
            labels = GroundTruthLabel.objects.all().select_related('event')
            self.stdout.write(f'Using all {labels.count()} labeled samples')
        else:
            try:
                experiment = Experiment.objects.get(id=exp_id)
            except Experiment.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Experiment {exp_id} not found'))
                sys.exit(1)

            labels = GroundTruthLabel.objects.filter(experiment=experiment).select_related('event')
            self.stdout.write(f'Using {labels.count()} labels from experiment: {experiment.name}')

        total_labels = labels.count()
        positive_labels = labels.filter(is_violation=True).count()
        negative_labels = labels.filter(is_violation=False).count()
        min_labels = getattr(settings, 'ML_MIN_LABELS', 50)
        min_positive = getattr(settings, 'ML_MIN_POSITIVE_LABELS', 10)
        min_negative = getattr(settings, 'ML_MIN_NEGATIVE_LABELS', 10)

        if total_labels < min_labels or positive_labels < min_positive or negative_labels < min_negative:
            message = (
                f'Insufficient labeled data for reliable ML training: '
                f'{total_labels} total, {positive_labels} positive, {negative_labels} negative. '
                f'Required minimums: {min_labels} total, {min_positive} positive, {min_negative} negative.'
            )
            if not force:
                self.stdout.write(self.style.ERROR(message))
                self.stdout.write(self.style.WARNING('Label more HumanLayerEvent records in admin or rerun with --force for experimentation.'))
                sys.exit(1)
            self.stdout.write(self.style.WARNING(message))

        training_data = [(label.event, 1 if label.is_violation else 0) for label in labels]

        self.stdout.write(f'\nTraining {algorithm} model...')
        scorer = MLRiskScorer(model_version=version)

        metrics = scorer.train(
            training_data=training_data,
            algorithm=algorithm,
            tune_hyperparameters=tune,
            cv_folds=cv_folds
        )

        self.stdout.write(self.style.SUCCESS('\n=== Training Results ==='))
        self.stdout.write(f'Algorithm: {metrics["algorithm"]}')
        self.stdout.write(f'Samples: {metrics["n_samples"]} ({metrics["n_positive"]} positive, {metrics["n_negative"]} negative)')
        self.stdout.write(f'\nPerformance Metrics:')
        self.stdout.write(f'  Precision: {metrics["precision"]:.3f}')
        self.stdout.write(f'  Recall:    {metrics["recall"]:.3f}')
        self.stdout.write(f'  F1 Score:  {metrics["f1_score"]:.3f}')
        self.stdout.write(f'  ROC AUC:   {metrics["roc_auc"]:.3f}')
        self.stdout.write(f'\nCross-Validation ({cv_folds}-fold):')
        self.stdout.write(f'  F1 Mean:   {metrics["cv_f1_mean"]:.3f} ± {metrics["cv_f1_std"]:.3f}')

        if 'feature_importance' in metrics:
            self.stdout.write(f'\nTop Features:')
            for feat, imp in list(metrics['feature_importance'].items())[:5]:
                self.stdout.write(f'  {feat}: {imp:.4f}')

        if metrics['best_params']:
            self.stdout.write(f'\nBest Hyperparameters:')
            for param, value in metrics['best_params'].items():
                self.stdout.write(f'  {param}: {value}')

        scorer.save_model(version=version)
        self.stdout.write(self.style.SUCCESS(f'\nModel saved with version: {version}'))

        self.stdout.write(self.style.WARNING('\nTo use this model in production:'))
        self.stdout.write('  1. Keep ML_ENABLED=True in the environment')
        self.stdout.write(f'  2. Set ML_MODEL_VERSION="{version}"')
        self.stdout.write('  3. Restart Django application')
        self.stdout.write('\nTo validate:')
        self.stdout.write(f'  python manage.py validate_scorer --version {version}')
