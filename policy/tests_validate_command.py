from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from policy.models import Policy, Control
import json


class ValidateExpressionsCommandTests(TestCase):
    def test_invalid_expression_reports_error(self):
        p = Policy.objects.create(name='P')
        # invalid expression: missing op
        c = Control.objects.create(policy=p, name='C', severity='low', expression={'items': []})
        # run command and expect SystemExit with non-zero
        try:
            call_command('validate_expressions')
        except SystemExit as e:
            self.assertNotEqual(e.code, 0)
        else:
            self.fail('validate_expressions did not exit with non-zero for invalid expression')
