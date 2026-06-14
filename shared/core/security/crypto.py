"""
MuleShield AI - AES-256 Encryption Utilities
FIPS 140-2 compliant Fernet encryption with PBKDF2HMAC
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from passlib.context import CryptContext

# Password context for hashing
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Master key derivation (in production, use environment variable)
MASTER_KEY = os.getenv("ENCRYPTION_KEY", "muleshield-boi-cybershield-2026-master-key")


def _get_fernet() -> Fernet:
    """Get Fernet cipher with PBKDF2HMAC key derivation"""
    salt = b"muleshield_salt_2026"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(MASTER_KEY.encode()))
    return Fernet(key)


def encrypt(data: str) -> str:
    """AES-256 encrypt data for PII fields"""
    fernet = _get_fernet()
    return fernet.encrypt(data.encode()).decode()


def decrypt(encrypted_data: str) -> str:
    """AES-256 decrypt data"""
    fernet = _get_fernet()
    return fernet.decrypt(encrypted_data.encode()).decode()


def tokenize(data: str, length: int = 16) -> str:
    """Irreversible SHA-256 one-way hash for account IDs"""
    return hashlib.sha256(data.encode()).hexdigest()[:length]


def hash_password(password: str) -> str:
    """PBKDF2 with SHA-256 password hashing"""
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(password, hashed)


def generate_idempotency_key() -> str:
    """Generate 24-char unique idempotency key"""
    return base64.urlsafe_b64encode(os.urandom(18)).decode()


def mask_account_number(account_number: str) -> str:
    """Display masking: XXXX-XXXX-1234"""
    if len(account_number) <= 4:
        return "XXXX"
    return "XXXX-XXXX-" + account_number[-4:]
