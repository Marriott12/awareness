from django.contrib import admin, messages
from .models import Policy, Control, Rule, Threshold, Violation, ViolationActionLog
from .models import Evidence, HumanLayerEvent
from .models import ExportAudit
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from .forms import ControlForm


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'active', 'created_at')
    search_fields = ('name',)


@admin.register(Control)
class ControlAdmin(admin.ModelAdmin):
    form = ControlForm
    list_display = ('name', 'policy', 'severity', 'active', 'expression_valid')
    list_filter = ('severity', 'active')

    actions = ('validate_selected_expressions',)

    def expression_valid(self, obj):
        # quick validation indicator; non-invasive
        expr = getattr(obj, 'expression', None)
        if expr is None:
            return True
        try:
            from .expression_schema import EXPRESSION_SCHEMA
            import jsonschema
            jsonschema.validate(instance=expr, schema=EXPRESSION_SCHEMA)
            return True
        except Exception:
            return False
    expression_valid.boolean = True
    expression_valid.short_description = 'Expression Valid'

    def validate_selected_expressions(self, request, queryset):
        try:
            import jsonschema
        except Exception:
            self.message_user(request, 'jsonschema is required to validate expressions', level=messages.ERROR)
            return
        errors = []
        from .expression_schema import EXPRESSION_SCHEMA
        for c in queryset:
            expr = getattr(c, 'expression', None)
            if expr is None:
                continue
            try:
                jsonschema.validate(instance=expr, schema=EXPRESSION_SCHEMA)
            except Exception as e:
                errors.append((c, str(e)))
        if errors:
            for c, err in errors:
                self.message_user(request, f'Control {c.pk} invalid: {err}', level=messages.ERROR)
        else:
            self.message_user(request, 'All selected expressions are valid', level=messages.INFO)
    validate_selected_expressions.short_description = 'Validate expression for selected controls'

    def save_model(self, request, obj, form, change):
        # Validate composite expression against schema if present
        expr = getattr(obj, 'expression', None)
        if expr is not None:
            if not jsonschema:
                raise ValidationError('jsonschema package required to validate Control.expression')
            try:
                jsonschema.validate(instance=expr, schema=EXPRESSION_SCHEMA)
            except jsonschema.ValidationError as e:
                raise ValidationError(f'Control.expression validation failed: {str(e)}')
        super().save_model(request, obj, form, change)


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'control', 'operator', 'enabled')
    list_filter = ('operator', 'enabled')
    search_fields = ('name', 'left_operand', 'right_value')


@admin.register(Threshold)
class ThresholdAdmin(admin.ModelAdmin):
    list_display = ('control', 'threshold_type', 'value', 'window_seconds')


@admin.register(Violation)
class ViolationAdmin(admin.ModelAdmin):
    list_display = ('policy', 'control', 'rule', 'timestamp', 'user', 'severity', 'resolved')
    list_filter = ('severity', 'resolved')
    readonly_fields = ('evidence',)
    actions = ('acknowledge_selected', 'resolve_selected')

    def acknowledge_selected(self, request, queryset):
        from django.utils import timezone
        from .models import ViolationActionLog

        updated = queryset.filter(acknowledged=False).update(acknowledged=True, acknowledged_at=timezone.now(), acknowledged_by=request.user)
        # Log action to immutable action log
        for v in queryset.filter(acknowledged=True):
            ViolationActionLog.objects.create(
                violation=v,
                action='acknowledge',
                actor=request.user,
                details={'source': 'admin_bulk_action'}
            )
        self.message_user(request, f"Acknowledged {updated} violations")
    acknowledge_selected.short_description = 'Acknowledge selected violations'

    def resolve_selected(self, request, queryset):
        from django.utils import timezone
        from .models import ViolationActionLog

        updated = queryset.filter(resolved=False).update(resolved=True, resolved_at=timezone.now(), resolved_by=request.user)
        for v in queryset.filter(resolved=True):
            ViolationActionLog.objects.create(
                violation=v,
                action='resolve',
                actor=request.user,
                details={'source': 'admin_bulk_action'}
            )
        self.message_user(request, f"Resolved {updated} violations")
    resolve_selected.short_description = 'Resolve selected violations'

    def export_selected(self, request, queryset):
        """Export selected violations as NDJSON with detached signature file written to a temp dir.

        For large exports or production use, prefer running `manage.py export_evidence` with filters.
        """
        import tempfile, os, json, hmac, hashlib
        from django.conf import settings
        # require export permission
        if not request.user.has_perm('policy.export_evidence') and not request.user.is_superuser:
            self.message_user(request, 'You do not have permission to export evidence', level='error')
            return
        tmpd = tempfile.mkdtemp()
        out_path = os.path.join(tmpd, 'violations.ndjson')
        sig_path = out_path + '.sig'
        key = getattr(settings, 'EVIDENCE_SIGNING_KEY', settings.SECRET_KEY)
        signer = getattr(settings, 'EVIDENCE_SIGNER', request.user.username if request.user else 'unknown')
        with open(out_path, 'w', encoding='utf-8') as of:
            sigs = []
            for v in queryset.order_by('timestamp'):
                line = json.dumps({'policy': v.policy.name, 'control': v.control.name, 'rule': v.rule and v.rule.name, 'timestamp': v.timestamp.isoformat(), 'user': v.user and v.user.username, 'evidence': v.evidence}, default=str)
                of.write(line + '\n')
                mac = hmac.new(key.encode('utf-8'), line.encode('utf-8'), hashlib.sha256).hexdigest()
                sigs.append({'violation_id': v.pk, 'sig': mac})
        with open(sig_path, 'w', encoding='utf-8') as sf:
            sf.write(json.dumps({'meta': {'signer': signer, 'timestamp': timezone.now().isoformat(), 'file': out_path}}) + '\n')
            for s in sigs:
                sf.write(json.dumps(s) + '\n')
        # record audit
        ExportAudit.objects.create(user=request.user, object_type='violation', object_count=queryset.count(), details={'out_path': out_path, 'sig_path': sig_path})
        self.message_user(request, f"Exported {queryset.count()} violations to {out_path} (signature {sig_path})")
    export_selected.short_description = 'Export selected violations (NDJSON + detached sig)'


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('policy', 'violation', 'created_at')
    readonly_fields = ('policy', 'violation', 'payload', 'created_at')
    search_fields = ('policy__name', 'violation__id')


@admin.register(ViolationActionLog)
class ViolationActionLogAdmin(admin.ModelAdmin):
    list_display = ('violation', 'action', 'actor', 'timestamp')
    list_filter = ('action',)
    readonly_fields = ('violation', 'action', 'actor', 'timestamp', 'details')
    search_fields = ('violation__id', 'actor__username')

    def has_add_permission(self, request):
        # Action log is append-only from application logic
        return False

    def has_delete_permission(self, request, obj=None):
        # Immutable
        return False


@admin.register(HumanLayerEvent)
class HumanLayerEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'summary', 'user', 'timestamp', 'source')
    readonly_fields = ('id', 'timestamp', 'user', 'event_type', 'source', 'summary', 'details', 'related_policy', 'related_control', 'related_violation')
    search_fields = ('summary', 'user__username', 'source')
