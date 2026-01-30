#!/usr/bin/env python
"""Key rotation helper for evidence signing key.

This script provides a template for rotating the `EVIDENCE_SIGNING_KEY` using
either AWS KMS, HashiCorp Vault, or direct CLI injection into GitHub Actions
secrets. It intentionally does not perform any rotation without operator
credentials — it instead provides the operations an operator should perform.

Usage patterns (operator-run):
- Generate a new key locally or via KMS.
- Update your secret store (Vault/KMS/GitHub Secrets) using their CLIs/SDKs.
- Optionally export a snapshot of previous keys with rotation metadata.

Note: This script is a helper; running it requires external credentials and
secure environment access. It will not auto-rotate keys by itself.
"""
import argparse
import os
import subprocess
import json
from datetime import datetime


def rotate_with_aws_kms(key_alias, new_plaintext_key_path):
    # Example: use AWS KMS to encrypt a new key and store encrypted blob elsewhere
    raise NotImplementedError('Implement KMS rotation with boto3 or CLI')


def rotate_with_vault(vault_addr, secret_path, new_key):
    # Example: use `vault kv put` to update a secret path.
    cmd = ['vault', 'kv', 'put', secret_path, f'EVIDENCE_SIGNING_KEY={new_key}']
    subprocess.check_call(cmd)
    print('Updated Vault at', secret_path)


def update_github_secret(repo, secret_name, new_key):
    # Requires gh CLI with appropriate permissions
    # Example: echo -n "secret" | gh secret set NAME -R owner/repo
    cmd = ['gh', 'secret', 'set', secret_name, '-R', repo]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    p.communicate(input=new_key.encode('utf-8'))
    if p.returncode != 0:
        raise RuntimeError('Failed to set GitHub secret')
    print('Updated GitHub secret', secret_name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vault', help='vault address or CLI usage', required=False)
    parser.add_argument('--vault-path', help='vault secret path', required=False)
    parser.add_argument('--gh-repo', help='GitHub repo (owner/repo) to update secret', required=False)
    parser.add_argument('--gh-secret', default='EVIDENCE_SIGNING_KEY')
    parser.add_argument('--new-key-file', help='Path to plaintext new key', required=False)
    args = parser.parse_args()

    if args.new_key_file is None:
        new_key = input('Paste new signing key (PEM or secret): ').strip()
    else:
        with open(args.new_key_file, 'r') as fh:
            new_key = fh.read().strip()

    if args.vault and args.vault_path:
        rotate_with_vault(args.vault, args.vault_path, new_key)

    if args.gh_repo:
        update_github_secret(args.gh_repo, args.gh_secret, new_key)

    print('Rotation operations completed at', datetime.utcnow().isoformat() + 'Z')


if __name__ == '__main__':
    main()
