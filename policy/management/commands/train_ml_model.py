"""Management command to train ML risk scoring model.

Usage:
    python manage.py train_ml_model --experiment-id 123
    python manage.py train_ml_model --use-all-labels --algorithm gradient_boosting
"""
from django.core.management.base import BaseCommand
from policy.models import GroundTruthLabel, Experiment, ScorerArtifact
from policy.ml_scorer import MLRiskScorer, SKLEARN_AVAILABLE
from django.utils import timezone
import sys


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
            '--version',
            default=None,
            help='Model version tag (default: auto-generated)'
        )
        parser.add_argument(
            '--cv-folds',
            type=int,
            default=5,
            help='Cross-validation folds (default: 5)'
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
        version = options['version']
        cv_folds = options['cv_folds']
        
        if not exp_id and not use_all:
            self.stdout.write(self.style.ERROR(
                'Specify --experiment-id or --use-all-labels'
            ))
            sys.exit(1)
        
        # Gather labeled data
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
        
        if labels.count() < 20:
            self.stdout.write(self.style.WARNING(
                f'Only {labels.count()} samples - ML may not perform well (recommend 100+)'
            ))
        
        # Prepare training data
        training_data = [(label.event, 1 if label.is_violation else 0) for label in labels]
        
        # Train model
        self.stdout.write(f'\nTraining {algorithm} model...')
        scorer = MLRiskScorer()
        
        metrics = scorer.train(
            training_data=training_data,
            algorithm=algorithm,
            tune_hyperparameters=tune,
            cv_folds=cv_folds
        )
        
        # Display results
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
        
        # Save model
        if version is None:
            version = f'v{timezone.now().strftime("%Y%m%d_%H%M%S")}'
        
        scorer.save_model(version=version)
        self.stdout.write(self.style.SUCCESS(f'\nModel saved with version: {version}'))
        
        # Show usage instructions
        self.stdout.write(self.style.WARNING('\nTo use this model in production:'))
        self.stdout.write(f'  1. Set ML_ENABLED=True in settings.py')
        self.stdout.write(f'  2. Set ML_MODEL_VERSION="{version}" (or use "latest")')
        self.stdout.write(f'  3. Restart Django application')
        self.stdout.write(f'\nTo validate:')
        self.stdout.write(f'  python manage.py validate_ml_model --version {version}')
