# Deployment Guide

## Production Readiness Checklist

### 1. Environment Variables (Required)

Set these environment variables before deploying:

```bash
# Django Core
AWARENESS_SECRET_KEY=<your-secret-key>  # REQUIRED in production
AWARENESS_DEBUG=False
AWARENESS_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database
DATABASE_URL=postgres://user:password@host:5432/dbname

# Static Files
AWARENESS_STATICFILES_STORAGE=whitenoise.storage.CompressedManifestStaticFilesStorage

# Email
AWARENESS_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
AWARENESS_DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Security (Production)
AWARENESS_SECURE_SSL_REDIRECT=True
AWARENESS_SECURE_HSTS_SECONDS=31536000
AWARENESS_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
AWARENESS_CSRF_TRUSTED_ORIGINS=https://yourdomain.com

# Signing & Evidence
EVIDENCE_SIGNING_KEY=<your-hmac-key>  # For local HMAC signing
# OR use AWS KMS / Vault:
SIGNING_PROVIDER=aws_kms  # or 'vault' or 'local' (default)
AWS_KMS_KEY_ID=alias/your-kms-key  # if using aws_kms
VAULT_URL=https://vault:8200  # if using vault
VAULT_TOKEN=s.xxxxx
VAULT_TRANSIT_KEY=transit-key-name

# Logging
AWARENESS_LOG_LEVEL=INFO
```

### 2. Database Setup

```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

### 3. Docker Deployment

#### Build and Run with Docker Compose

```bash
# Build image
docker-compose build

# Start services (Postgres + web)
docker-compose up -d

# Run migrations in container
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static
docker-compose exec web python manage.py collectstatic --noinput
```

#### Production docker-compose.yml

Update `docker-compose.yml` with production settings:

```yaml
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: awareness
      POSTGRES_USER: awareness
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # use secrets
    volumes:
      - db_data:/var/lib/postgresql/data
    restart: always

  web:
    build: .
    command: gunicorn awareness_portal.wsgi:application --bind 0.0.0.0:8000 --workers 4
    volumes:
      - ./staticfiles:/app/staticfiles
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgres://awareness:${DB_PASSWORD}@db:5432/awareness
      AWARENESS_SECRET_KEY: ${SECRET_KEY}
      AWARENESS_DEBUG: "False"
      AWARENESS_ALLOWED_HOSTS: ${ALLOWED_HOSTS}
      EVIDENCE_SIGNING_KEY: ${SIGNING_KEY}
    depends_on:
      - db
    restart: always

volumes:
  db_data:
```

### 4. Signing Provider Validation

Validate your configured signing provider:

```bash
# Validate all providers
python manage.py validate_signing_providers

# Validate specific provider
python manage.py validate_signing_providers --provider aws_kms
python manage.py validate_signing_providers --provider vault
```

Expected output:
- Exit code 0: all OK
- Exit code 2: one or more providers misconfigured

### 5. Policy Lifecycle Management

Only policies with `lifecycle='active'` are evaluated by the compliance engine.

**Lifecycle States:** DRAFT → REVIEW → ACTIVE → RETIRED

**Constraint:** Only one ACTIVE policy per `name` is allowed.

**Admin Actions:**
1. Create policy in DRAFT
2. Move to REVIEW for approval
3. Promote to ACTIVE (system enforces uniqueness)
4. RETIRE when superseded

### 6. Verification Steps

#### Test Signing

```bash
python manage.py shell
>>> from policy import signing
>>> sig = signing.sign_text('test')
>>> print(sig)
```

#### Run Tests

```bash
python manage.py test policy
```

#### Check Concurrency

```bash
python manage.py test policy.tests_concurrency
```

#### Validate Control Expressions

```bash
python manage.py validate_expressions
```

### 7. Management Commands

#### Export Evidence

```bash
python manage.py export_evidence --output /path/to/export.ndjson
```

#### Generate Signed Bundle

```bash
python manage.py generate_bundle --output-dir /path/to/bundle --policy "Policy Name"
```

#### Verify Bundle

```bash
python manage.py verify_bundle /path/to/bundle
```

Expected: `PASS: Bundle verification successful`

#### Run Experiment (Research)

```bash
# Create experiment first via admin or shell
python manage.py run_experiment --experiment 1 --seed 42 --scale 10
```

Output: signed bundle with metrics (precision, recall, FPR, latency)

#### Validate Scorer

```bash
python manage.py validate_scorer --experiment-id 1 --scorer-name default --scorer-version 1.0
```

### 8. Permissions & RBAC

- **Export Evidence:** Requires `policy.export_evidence` permission
- **Admin Access:** Requires `is_staff=True`
- **Superuser:** Full access to all models

Assign permissions via Django admin: Users → Permissions

### 9. Database Triggers (Postgres Only)

Migration `0006_append_only_triggers` installs triggers to enforce immutability on:
- `Evidence` (reject UPDATE/DELETE)
- `HumanLayerEvent` (reject UPDATE/DELETE)

**Note:** Triggers are Postgres-only. SQLite allows model-level checks only.

To verify triggers are active:

```sql
-- Connect to Postgres
\d policy_evidence
-- Check for triggers: prevent_evidence_update, prevent_evidence_delete
```

### 10. Monitoring & Health Checks

#### Add Health Check Endpoint

Create `dashboard/views.py` endpoint:

```python
from django.http import JsonResponse
from django.db import connection

def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'detail': str(e)}, status=500)
```

Add to `awareness_portal/urls.py`:

```python
path('.well-known/health', dashboard.views.health),
```

#### Logging

Logs are written to stdout by default. Configure external log aggregation (Datadog, CloudWatch, etc.) as needed.

### 11. Backup & Recovery

#### Postgres Backup

```bash
docker-compose exec db pg_dump -U awareness awareness > backup.sql
```

#### Restore

```bash
cat backup.sql | docker-compose exec -T db psql -U awareness awareness
```

### 12. CI/CD Integration

Example GitHub Actions workflow (`.github/workflows/ci.yml`):

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python manage.py test
      - run: python manage.py validate_expressions
      - run: python manage.py validate_signing_providers --provider local
```

### 13. Security Hardening

- [ ] Rotate `SECRET_KEY` and `EVIDENCE_SIGNING_KEY` regularly
- [ ] Use managed secrets (AWS Secrets Manager, HashiCorp Vault)
- [ ] Enable HTTPS/TLS (use reverse proxy: nginx, Caddy, AWS ALB)
- [ ] Set `SECURE_HSTS_SECONDS=31536000` in production
- [ ] Use AWS KMS or Vault for signing (not local HMAC)
- [ ] Restrict database access (firewall, VPC)
- [ ] Enable audit logging for admin actions
- [ ] Review `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`

### 14. Troubleshooting

**Issue:** SECRET_KEY error in production

**Fix:** Set `AWARENESS_SECRET_KEY` env var

**Issue:** Signing validation fails

**Fix:** Check `EVIDENCE_SIGNING_KEY` or provider config with `validate_signing_providers`

**Issue:** Violations not created

**Fix:** Ensure policy `lifecycle='active'`

**Issue:** Postgres triggers not working

**Fix:** Verify migration `0006_append_only_triggers` applied; check Postgres version

---

## Quick Start (Local Dev)

```bash
# Clone repo
git clone https://github.com/Marriott12/awareness.git
cd awareness

# Create virtualenv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install deps
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run dev server
python manage.py runserver
```

Visit http://localhost:8000/admin

---

## Production Deployment Checklist

- [ ] Set `AWARENESS_SECRET_KEY` (unique, 50+ chars)
- [ ] Set `AWARENESS_DEBUG=False`
- [ ] Set `AWARENESS_ALLOWED_HOSTS`
- [ ] Configure `DATABASE_URL` (Postgres recommended)
- [ ] Set `EVIDENCE_SIGNING_KEY` or configure KMS/Vault
- [ ] Run `python manage.py migrate`
- [ ] Run `python manage.py collectstatic`
- [ ] Validate signing providers
- [ ] Validate Control expressions
- [ ] Run full test suite
- [ ] Set up monitoring/alerting
- [ ] Configure backups
- [ ] Enable HTTPS/TLS
- [ ] Review security settings
- [ ] Document incident response procedures

---

**For questions or issues, see:** https://github.com/Marriott12/awareness/issues
