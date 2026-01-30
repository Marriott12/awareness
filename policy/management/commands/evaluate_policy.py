import json
from django.core.management.base import BaseCommand, CommandError
from policy.models import Policy
from policy.services import RuleEngine


class Command(BaseCommand):
    help = 'Evaluate a Policy JSON context against a named policy and print explainable results'

    def add_arguments(self, parser):
        parser.add_argument('policy_name', help='Policy name to evaluate')
        parser.add_argument('--context-file', help='Path to JSON file containing the evaluation context', required=False)

    def handle(self, *args, **options):
        pname = options['policy_name']
        try:
            policy = Policy.objects.get(name=pname)
        except Policy.DoesNotExist:
            raise CommandError(f'Policy not found: {pname}')

        ctx = {}
        cf = options.get('context_file')
        if cf:
            with open(cf, 'r', encoding='utf-8') as fh:
                ctx = json.load(fh)
        else:
            # read from stdin
            try:
                ctx = json.load(self.stdin)
            except Exception:
                ctx = {}

        engine = RuleEngine()
        res = engine.evaluate_policy(policy, ctx)
        self.stdout.write(json.dumps(res, indent=2, default=str))