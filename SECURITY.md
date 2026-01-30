# Security and Key Management

This project signs exported Evidence and telemetry using an HMAC key. Follow these guidelines:

- Store the signing key in a secure secret store (GitHub Actions `secrets.EVIDENCE_SIGNING_KEY`, Vault, or KMS).
- Rotate keys regularly: create a new key, update the secret, and re-run exports as needed.
- Keep a signer identifier in `EVIDENCE_SIGNER` or pass `--signer` to `export_evidence`.
- Never commit keys to the repository.

Key rotation policy (suggested):
- Rotate every 90 days or on suspicion of compromise.
- Maintain an audit log of key changes.
- When rotating, update CI secrets and securely distribute the new key to operators.
