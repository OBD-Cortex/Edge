import os
import hmac
import hashlib
import secrets
import datetime
import logging
from pathlib import Path
from core.config import BASE_DIR

logger = logging.getLogger(__name__)

KEYS_DIR = BASE_DIR / ".keys"
SECRET_PATH = KEYS_DIR / "device_secret"

def is_provisioned() -> bool:
    """Returns True if the shared secret exists on disk."""
    return SECRET_PATH.exists()

def generate_secret() -> str:
    """
    Generates a 32-byte hex secret and saves it to .keys/device_secret.
    """
    secret = secrets.token_hex(32)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    with os.fdopen(os.open(str(SECRET_PATH), flags, 0o600), "w") as f:
        f.write(secret)
    logger.info("[✓] Device secret saved securely to disk.")
    return secret

def load_secret() -> str:
    """Loads the shared secret from disk."""
    if not is_provisioned():
        raise RuntimeError("Device is not provisioned (device_secret missing).")
    with open(SECRET_PATH, "r") as f:
        return f.read().strip()

def sign_payload(payload_bytes: bytes) -> tuple:
    """
    Signs the raw payload bytes concatenated with a UTC timestamp.
    Returns (signature_hex, timestamp_str).
    """
    secret = load_secret().encode("utf-8")
    timestamp_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    data_to_sign = timestamp_str.encode("utf-8") + payload_bytes
    signature = hmac.new(secret, data_to_sign, hashlib.sha256).hexdigest()
    
    return signature, timestamp_str
