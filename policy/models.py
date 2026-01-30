from django.db import models
from django.conf import settings
from django.utils import timezone


class Policy(models.Model):
    """Top-level policy grouping multiple controls and rules.

    Designed for governance/audit use; immutable audit trail is built via Violations.
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)
    version = models.CharField(max_length=64, default='1.0')
    # lifecycle: draft -> review -> active -> retired
    LIFECYCLE_CHOICES = (('draft','Draft'), ('review','Review'), ('active','Active'), ('retired','Retired'))
    lifecycle = models.CharField(max_length=16, choices=LIFECYCLE_CHOICES, default='draft', help_text='Policy lifecycle state')

    def __str__(self):
        return self.name


class PolicyHistory(models.Model):
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='history')
    version = models.CharField(max_length=64)
    changelog = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        permissions = (('export_evidence', 'Can export evidence'),)

    class Meta:
        permissions = (('export_evidence', 'Can export evidence'),)

    def __str__(self):
        return f"{self.policy.name} v{self.version} @ {self.created_at.isoformat()}"


class Control(models.Model):
    """Controls group related rules and may carry thresholds/severity.

    Examples: "Password Policy", "Data Exfil Prevention".
    """

    SEVERITY_CHOICES = (('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical'))

    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='controls')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES, default='medium')
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    combination = models.CharField(max_length=8, choices=(('any','Any'),('all','All')), default='any', help_text='How to combine rule results: any=OR, all=AND')
    # optional JSON expression to express nested boolean logic over rules. Example:
    # {"op":"and","items":[{"rule":"Rule A"},{"op":"or","items":[{"rule":"Rule B"},{"rule":"Rule C"}]}]}
    expression = models.JSONField(null=True, blank=True, help_text='Optional composite boolean expression over rule names or ids')

    class Meta:
        ordering = ('policy', 'order', 'id')

    def __str__(self):
        return f"{self.policy.name} / {self.name}"


class Rule(models.Model):
    """Deterministic rule definition.

    - `left_operand` is a dotted path key into the evaluation context (e.g. 'request.ip', 'file.size').
    - `operator` is one of a set of supported deterministic operators.
    - `right_value` stored as JSON for types (string, number, list) to make rules auditable.
    """

    OPERATOR_CHOICES = (
        ('==', 'equals'),
        ('!=', 'not_equals'),
        ('>', 'gt'),
        ('<', 'lt'),
        ('>=', 'gte'),
        ('<=', 'lte'),
        ('in', 'in'),
        ('not_in', 'not_in'),
        ('regex', 'regex'),
    )

    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='rules')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    left_operand = models.CharField(max_length=512)
    operator = models.CharField(max_length=16, choices=OPERATOR_CHOICES)
    right_value = models.JSONField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ('control', 'order', 'id')

    def __str__(self):
        return f"{self.control} / {self.name}"


class Threshold(models.Model):
    """Optional threshold attached to a control.

    Examples:
    - count-based: more than N events in T seconds
    - percent-based: > 50% of attempts in window
    The evaluation engine will perform threshold calculations deterministically using stored data.
    """

    THRESHOLD_TYPE_CHOICES = (('count', 'Count'), ('percent', 'Percent'), ('time_window', 'TimeWindow'))

    control = models.OneToOneField(Control, on_delete=models.CASCADE, related_name='threshold', null=True)
    threshold_type = models.CharField(max_length=32, choices=THRESHOLD_TYPE_CHOICES)
    value = models.FloatField(help_text='Primary threshold value (meaning depends on type)')
    window_seconds = models.PositiveIntegerField(null=True, blank=True, help_text='Window duration for time-based thresholds')

    def __str__(self):
        return f"{self.control} threshold ({self.threshold_type}={self.value})"


class Violation(models.Model):
    """Records policy violations with evidence for audit.

    - timestamp: when the violation was recorded
    - user: optional user associated with the violation
    - policy/control/rule: references for governance traceability
    - evidence: JSON blob capturing the inputs and computed values used to reach the decision
    """

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='violations')
    control = models.ForeignKey(Control, on_delete=models.CASCADE, related_name='violations')
    rule = models.ForeignKey(Rule, null=True, blank=True, on_delete=models.SET_NULL, related_name='violations')
    severity = models.CharField(max_length=16, blank=True)
    evidence = models.JSONField()
    # deduplication key to ensure idempotent synthesis
    dedup_key = models.CharField(max_length=128, null=True, blank=True, db_index=True, unique=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='acknowledged_violations', on_delete=models.SET_NULL)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='resolved_violations', on_delete=models.SET_NULL)

    class Meta:
        ordering = ('-timestamp',)

    def __str__(self):
        return f"Violation {self.policy.name}:{self.control.name} @ {self.timestamp.isoformat()}"


class Evidence(models.Model):
    """Immutable evidence artifact linked to policies and violations.

    - `policy` optional: the policy this evidence relates to
    - `violation` optional: link to a `Violation` if evidence originated from a recorded violation
    - `payload`: JSON field containing explainable forensic data (inputs, computed values, signatures)
    Evidence objects are immutable once created (application-level enforcement).
    """

    policy = models.ForeignKey(Policy, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence')
    violation = models.OneToOneField(Violation, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_obj')
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        # Enforce immutability: cannot update an existing record
        if not getattr(self, '_state', None) or not getattr(self._state, 'adding', True):
            raise ValueError('Evidence objects are immutable and cannot be updated')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Evidence objects are immutable and cannot be deleted')

    def __str__(self):
        target = self.policy.name if self.policy else (self.violation and str(self.violation))
        return f"Evidence for {target} @ {self.created_at.isoformat()}"


import uuid


class HumanLayerEvent(models.Model):
    """Captures human interactions and telemetry for forensic review.

    Fields:
    - `id`: UUID primary key for global uniqueness and easier tracing across systems
    - `timestamp`: event time
    - `user`: optional actor
    - `event_type`: categorical type (authentication, quiz_attempt, training_progress, etc.)
    - `source`: application or subsystem that produced the event
    - `summary`: short human-readable summary
    - `details`: structured JSON with explainable context for the event
    - `related_policy` / `related_control` / `related_violation`: optional links for correlation
    """

    EVENT_TYPES = (
        ('auth', 'Authentication'),
        ('quiz', 'Quiz'),
        ('training', 'Training'),
        ('admin', 'Admin'),
        ('other', 'Other'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=32, choices=EVENT_TYPES, default='other')
    source = models.CharField(max_length=128, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    details = models.JSONField(help_text='Explainable structured payload for forensic review')
    related_policy = models.ForeignKey(Policy, null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    related_control = models.ForeignKey(Control, null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    related_violation = models.ForeignKey(Violation, null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    processed = models.BooleanField(default=False, db_index=True)
    # Cryptographic chaining & provenance
    prev_hash = models.CharField(max_length=128, null=True, blank=True)
    signature = models.CharField(max_length=256, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ('-timestamp',)

    def save(self, *args, **kwargs):
        # HumanLayerEvent should be append-only; allow initial create.
        adding = getattr(self, '_state', None) and getattr(self._state, 'adding', True)
        if adding:
            return super().save(*args, **kwargs)

        # On updates, only allow setting `processed` and/or `related_violation` while leaving other fields unchanged.
        try:
            existing = HumanLayerEvent.objects.get(pk=self.pk)
        except Exception:
            raise ValueError('Cannot update HumanLayerEvent: original record not found')

        immutable_fields = ['timestamp', 'user_id', 'event_type', 'source', 'summary', 'details', 'related_policy_id', 'related_control_id']
        for f in immutable_fields:
            # compare using attribute or _id fields
            existing_val = getattr(existing, f) if hasattr(existing, f) else getattr(existing, f.replace('_id', ''), None)
            new_val = getattr(self, f) if hasattr(self, f) else getattr(self, f.replace('_id', ''), None)
            if existing_val != new_val:
                raise ValueError('HumanLayerEvent objects are append-only and cannot be updated')

        # allow updating processed from False->True
        if existing.processed and self.processed != existing.processed:
            raise ValueError('HumanLayerEvent objects are append-only and cannot be updated')

        # allow setting related_violation only if it was previously None
        if existing.related_violation is not None and self.related_violation != existing.related_violation:
            raise ValueError('HumanLayerEvent objects are append-only and cannot be updated')

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('HumanLayerEvent objects are immutable and cannot be deleted')

    def __str__(self):
        return f"{self.get_event_type_display()} by {self.user} @ {self.timestamp.isoformat()}"


class Experiment(models.Model):
    """Defines a reproducible experiment run for telemetry evaluation."""
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    config = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Experiment {self.name} ({self.created_at.isoformat()})"


class SyntheticUser(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='synthetic_users')
    username = models.CharField(max_length=200)
    attributes = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"SyntheticUser {self.username} for {self.experiment.name}"


class GroundTruthLabel(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='labels')
    event = models.ForeignKey('HumanLayerEvent', on_delete=models.CASCADE)
    is_violation = models.BooleanField()

    class Meta:
        ordering = ('-event__timestamp',)


class DetectionMetric(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='metrics')
    name = models.CharField(max_length=200)
    value = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)


class ExportAudit(models.Model):
    """Record exports for RBAC and auditability."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    object_type = models.CharField(max_length=200)
    object_count = models.PositiveIntegerField(default=0)
    details = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"Export by {self.user} {self.object_type} x{self.object_count} @ {self.created_at.isoformat()}"


class ScorerArtifact(models.Model):
    """Store deterministic scoring artifact metadata and config with content hash."""
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=64)
    config = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sha256 = models.CharField(max_length=128, blank=True)

    class Meta:
        unique_together = (('name', 'version'),)

    def __str__(self):
        return f"Scorer {self.name} v{self.version} ({self.sha256})"

