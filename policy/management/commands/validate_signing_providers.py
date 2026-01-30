from django.core.management.base import BaseCommand
from policy import signing


class Command(BaseCommand):
    help = 'Validate configured signing providers (local, aws_kms, vault).'

    def add_arguments(self, parser):
        parser.add_argument('--provider', help='Only validate this provider')

    def handle(self, *args, **options):
        prov = options.get('provider')
        providers = [prov] if prov else ['local', 'aws_kms', 'vault']
        overall_ok = True
        for p in providers:
            try:
                ok, msg = signing.validate_provider(p)
                if ok:
                    self.stdout.write(self.style.SUCCESS(f'{p}: OK - {msg}'))
                else:
                    overall_ok = False
                    self.stdout.write(self.style.WARNING(f'{p}: WARN - {msg}'))
            except Exception as e:
                overall_ok = False
                self.stdout.write(self.style.ERROR(f'{p}: ERROR - {e}'))

        if not overall_ok:
            raise SystemExit(2)