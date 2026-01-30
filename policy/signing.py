"""Signing wrappers for evidence and experiment bundles.

Supports three modes:
- aws_kms: uses AWS KMS GenerateMac (HMAC) if boto3 is available and configured
- vault: uses HashiCorp Vault transit sign (if hvac is available and configured)
- local: HMAC using `EVIDENCE_SIGNING_KEY` from Django settings (fallback)

This module provides `sign_bytes(payload: bytes) -> str` which returns a hex digest.
"""
from typing import Optional
from django.conf import settings
import hmac
import hashlib
import logging

logger = logging.getLogger(__name__)


def _local_sign(payload: bytes) -> str:
    key = getattr(settings, 'EVIDENCE_SIGNING_KEY', None)
    if not key:
        raise RuntimeError('No local signing key configured (EVIDENCE_SIGNING_KEY)')
    return hmac.new(key.encode('utf-8'), payload, hashlib.sha256).hexdigest()


def _aws_kms_sign(payload: bytes) -> str:
    try:
        import boto3
    except Exception:
        raise RuntimeError('boto3 is required for aws_kms provider')
    kms_key_id = getattr(settings, 'AWS_KMS_KEY_ID', None)
    if not kms_key_id:
        raise RuntimeError('AWS_KMS_KEY_ID not configured')
    client = boto3.client('kms')
    # Use GenerateMac API if available; fallback to Sign (RSA) is not appropriate for HMAC
    try:
        resp = client.generate_mac(KeyId=kms_key_id, Message=payload, MacAlgorithm='HMAC_SHA_256')
        mac = resp.get('Mac')
        # Mac is bytes; convert to hex
        return mac.hex()
    except Exception as e:
        logger.exception('AWS KMS signing failed')
        raise


def _vault_sign(payload: bytes) -> str:
    try:
        import hvac
    except Exception:
        raise RuntimeError('hvac is required for vault provider')
    vault_url = getattr(settings, 'VAULT_URL', None)
    vault_token = getattr(settings, 'VAULT_TOKEN', None)
    transit_key = getattr(settings, 'VAULT_TRANSIT_KEY', None)
    if not (vault_url and vault_token and transit_key):
        raise RuntimeError('VAULT_URL, VAULT_TOKEN, and VAULT_TRANSIT_KEY must be set for vault provider')
    client = hvac.Client(url=vault_url, token=vault_token)
    try:
        # Vault transit expects base64 input; use hvac convenience
        import base64
        b64 = base64.b64encode(payload).decode('ascii')
        resp = client.secrets.transit.generate_mac(name=transit_key, input=b64)
        mac_b64 = resp['data']['mac']
        mac = base64.b64decode(mac_b64)
        return mac.hex()
    except Exception:
        logger.exception('Vault signing failed')
        raise


def sign_bytes(payload: bytes) -> str:
    provider = getattr(settings, 'SIGNING_PROVIDER', 'local')
    if provider == 'aws_kms':
        return _aws_kms_sign(payload)
    if provider == 'vault':
        return _vault_sign(payload)
    # default local HMAC
    return _local_sign(payload)


def sign_text(text: str) -> str:
    return sign_bytes(text.encode('utf-8'))


def validate_provider(provider: str):
    """Validate the given provider configuration and connectivity.

    Returns (True, message) on success, (False, message) on non-fatal
    misconfiguration, and raises on unexpected errors.
    """
    provider = provider or getattr(settings, 'SIGNING_PROVIDER', 'local')
    if provider == 'aws_kms':
        try:
            import boto3  # noqa: F401
        except Exception:
            return False, 'boto3 is not installed'
        kms_key_id = getattr(settings, 'AWS_KMS_KEY_ID', None)
        if not kms_key_id:
            return False, 'AWS_KMS_KEY_ID not configured'
        try:
            client = boto3.client('kms')
            # Lightweight call: describe_key to validate access
            client.describe_key(KeyId=kms_key_id)
            return True, 'AWS KMS reachable and key accessible'
        except Exception as e:
            logger.exception('AWS KMS validation failed')
            return False, f'AWS KMS validation error: {e}'

    if provider == 'vault':
        try:
            import hvac  # noqa: F401
        except Exception:
            return False, 'hvac is not installed'
        vault_url = getattr(settings, 'VAULT_URL', None)
        vault_token = getattr(settings, 'VAULT_TOKEN', None)
        transit_key = getattr(settings, 'VAULT_TRANSIT_KEY', None)
        if not (vault_url and vault_token and transit_key):
            return False, 'VAULT_URL, VAULT_TOKEN, and VAULT_TRANSIT_KEY must be set'
        try:
            client = hvac.Client(url=vault_url, token=vault_token)
            # Lightweight call: read key metadata
            client.secrets.transit.read_key(name=transit_key)
            return True, 'Vault transit reachable and key accessible'
        except Exception as e:
            logger.exception('Vault validation failed')
            return False, f'Vault validation error: {e}'

    # local
    try:
        key = getattr(settings, 'EVIDENCE_SIGNING_KEY', None)
        if not key:
            return False, 'EVIDENCE_SIGNING_KEY not configured for local provider'
        return True, 'Local HMAC key present'
    except Exception as e:
        logger.exception('Local signing validation failed')
        return False, f'Local validation error: {e}'
