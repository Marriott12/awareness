import json
from django.core.management.base import BaseCommand, CommandError
from policy.models import Policy
from policy.compliance import ComplianceEngine


class Command(BaseCommand):
    help = 'Evaluate unprocessed HumanLayerEvent telemetry against a named policy.'

    def add_arguments(self, parser):
        parser.add_argument('policy_name', help='Policy name to evaluate')
        parser.add_argument('--limit', type=int, default=100, help='Max events to process')

    def handle(self, *args, **options):
        pname = options['policy_name']
        try:
            policy = Policy.objects.get(name=pname)
        except Policy.DoesNotExist:
            raise CommandError(f'Policy not found: {pname}')

        engine = ComplianceEngine()
        results = engine.evaluate_unprocessed(policy, limit=options['limit'])
        self.stdout.write(json.dumps(results, indent=2, default=str))
