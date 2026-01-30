from django import forms
from django.core.exceptions import ValidationError
from .models import Control
from .expression_schema import EXPRESSION_SCHEMA
try:
    import jsonschema
except Exception:
    jsonschema = None


class ControlForm(forms.ModelForm):
    class Meta:
        model = Control
        fields = '__all__'

    def clean_expression(self):
        expr = self.cleaned_data.get('expression')
        if expr is None:
            return expr
        if not jsonschema:
            raise ValidationError('jsonschema package is required to validate expression in admin')
        try:
            jsonschema.validate(instance=expr, schema=EXPRESSION_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValidationError(f'Expression validation failed: {e.message}')
        return expr
