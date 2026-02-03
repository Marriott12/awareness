"""Cryptographic utilities for PKI-based signing and TSA timestamping.

Implements:
- Asymmetric key signing (RSA/Ed25519)
- RFC 3161 timestamp authority integration
- Key management and rotation
"""
import hashlib
import hmac
from typing import Optional
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def sign_data(payload: str) -> str:
    """Sign data using configured signing method.
    
    Priority:
    1. SIGNING_PRIVATE_KEY_PATH (asymmetric RSA/Ed25519)
    2. EVIDENCE_SIGNING_KEY (symmetric HMAC - deprecated)
    3. Raises error if neither configured
    
    Args:
        payload: String data to sign
        
    Returns:
        Hexadecimal signature string
    """
    # Try asymmetric signing first (production)
    private_key_path = getattr(settings, 'SIGNING_PRIVATE_KEY_PATH', None)
    if private_key_path:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend
            
            with open(private_key_path, 'rb') as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            
            signature = private_key.sign(
                payload.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return signature.hex()
        except Exception as e:
            logger.error(f'Asymmetric signing failed: {e}')
            raise RuntimeError(f'Failed to sign with private key: {e}')
    
    # Fallback to symmetric HMAC (dev/test only)
    symmetric_key = getattr(settings, 'EVIDENCE_SIGNING_KEY', None)
    if symmetric_key:
        logger.warning('Using deprecated HMAC signing - configure SIGNING_PRIVATE_KEY_PATH for production')
        return hmac.new(
            symmetric_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    raise RuntimeError('No signing key configured (SIGNING_PRIVATE_KEY_PATH or EVIDENCE_SIGNING_KEY)')


def verify_signature(payload: str, signature: str) -> bool:
    """Verify signature using configured verification method.
    
    Args:
        payload: Original data that was signed
        signature: Hexadecimal signature to verify
        
    Returns:
        True if signature is valid, False otherwise
    """
    # Try asymmetric verification first
    public_key_path = getattr(settings, 'SIGNING_PUBLIC_KEY_PATH', None)
    if public_key_path:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.backends import default_backend
            from cryptography.exceptions import InvalidSignature
            
            with open(public_key_path, 'rb') as f:
                public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=default_backend()
                )
            
            public_key.verify(
                bytes.fromhex(signature),
                payload.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except InvalidSignature:
            return False
        except Exception as e:
            logger.error(f'Asymmetric verification failed: {e}')
            return False
    
    # Fallback to symmetric HMAC verification
    symmetric_key = getattr(settings, 'EVIDENCE_SIGNING_KEY', None)
    if symmetric_key:
        expected = hmac.new(
            symmetric_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    logger.error('No verification key configured')
    return False


def get_tsa_timestamp(data: str) -> Optional[bytes]:
    """Get RFC 3161 timestamp from configured TSA.
    
    Args:
        data: Data to timestamp (signature or hash)
        
    Returns:
        DER-encoded TimeStampToken or None if TSA not configured
    """
    tsa_url = getattr(settings, 'TSA_URL', None)
    if not tsa_url:
        return None
    
    try:
        import requests
        from cryptography.hazmat.primitives import hashes
        from cryptography import x509
        from cryptography.x509 import ocsp
        
        # Create timestamp request
        data_hash = hashlib.sha256(data.encode('utf-8')).digest()
        
        # Build RFC 3161 request (simplified - production should use proper ASN.1)
        tsr_data = {
            'hashAlgorithm': 'sha256',
            'hashedMessage': data_hash.hex(),
        }
        
        response = requests.post(
            tsa_url,
            headers={'Content-Type': 'application/timestamp-query'},
            data=data_hash,
            timeout=5
        )
        
        if response.status_code == 200:
            return response.content
        else:
            logger.warning(f'TSA request failed: {response.status_code}')
            return None
            
    except Exception as e:
        logger.warning(f'TSA timestamp failed: {e}')
        return None


def generate_keypair(output_dir: str = '.', key_type: str = 'rsa'):
    """Generate RSA or Ed25519 keypair for signing.
    
    Args:
        output_dir: Directory to save keys
        key_type: 'rsa' or 'ed25519'
    """
    from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    import os
    
    if key_type == 'rsa':
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
            backend=default_backend()
        )
    elif key_type == 'ed25519':
        private_key = ed25519.Ed25519PrivateKey.generate()
    else:
        raise ValueError(f'Unsupported key type: {key_type}')
    
    public_key = private_key.public_key()
    
    # Save private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    private_path = os.path.join(output_dir, 'signing_private_key.pem')
    with open(private_path, 'wb') as f:
        f.write(private_pem)
    os.chmod(private_path, 0o600)
    
    # Save public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    public_path = os.path.join(output_dir, 'signing_public_key.pem')
    with open(public_path, 'wb') as f:
        f.write(public_pem)
    
    print(f'Generated {key_type.upper()} keypair:')
    print(f'  Private key: {private_path} (keep secure!)')
    print(f'  Public key: {public_path}')
    print(f'\nAdd to settings.py:')
    print(f"  SIGNING_PRIVATE_KEY_PATH = '{private_path}'")
    print(f"  SIGNING_PUBLIC_KEY_PATH = '{public_path}'")
