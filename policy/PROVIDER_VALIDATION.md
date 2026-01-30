Signing provider validation
==========================

Use the management command to validate signing providers and connectivity:

```
python manage.py validate_signing_providers
python manage.py validate_signing_providers --provider aws_kms
python manage.py validate_signing_providers --provider vault
```

Providers and required settings:

- local: set `EVIDENCE_SIGNING_KEY` in Django settings (string). This uses HMAC-SHA256.
- aws_kms: set `SIGNING_PROVIDER='aws_kms'` and `AWS_KMS_KEY_ID`. Install `boto3` and ensure AWS credentials are available (env vars, shared credentials, or IAM role). The validator calls `DescribeKey` on the configured key id.
- vault: set `SIGNING_PROVIDER='vault'`, `VAULT_URL`, `VAULT_TOKEN`, and `VAULT_TRANSIT_KEY`. Install `hvac`. The validator calls the Transit `read_key` endpoint to check accessibility.

Exit codes:
- 0: all validated ok
- 2: one or more providers misconfigured or unreachable

If a provider reports missing Python dependency (boto3 or hvac), install it in your environment.
