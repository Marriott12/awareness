from django.core.management.base import BaseCommand
from policy.models import Control
from django.conf import settings
try:
    import jsonschema
except Exception:
    jsonschema = None
from policy.expression_schema import EXPRESSION_SCHEMA


class Command(BaseCommand):
    help = 'Validate all Control.expression JSON against the expression schema.'

    def handle(self, *args, **options):
        if not jsonschema:
            self.stderr.write('jsonschema package is required to validate expressions')
            raise SystemExit(2)

        bad = []
        for c in Control.objects.all():
            expr = getattr(c, 'expression', None)
            if expr is None:
                continue
            try:
                jsonschema.validate(instance=expr, schema=EXPRESSION_SCHEMA)
            except Exception as e:
                bad.append((c.pk, str(e)))

        if bad:
            for pk, err in bad:
                self.stderr.write(f'Control {pk} invalid: {err}')
            raise SystemExit(1)

        self.stdout.write('All Control.expression values are valid')