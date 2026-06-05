import os
import stat
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
INTEGRITY_PATH = KEYS_DIR / "device_secret.sha256"


# ----------------------------------------------------------
# PERMISSION ENFORCEMENT
# ----------------------------------------------------------

def _enforce_permissions():
    """
    Verifies and enforces filesystem permissions on the .keys/ directory
    and device_secret file. Logs warnings if permissions are too open.
    """
    if KEYS_DIR.exists():
        dir_mode = KEYS_DIR.stat().st_mode & 0o777
        if dir_mode != 0o700:
            logger.warning(
                f"[!] .keys/ directory has mode {oct(dir_mode)}, "
                f"expected 0o700. Fixing permissions."
            )
            os.chmod(str(KEYS_DIR), 0o700)

    if SECRET_PATH.exists():
        file_mode = SECRET_PATH.stat().st_mode & 0o777
        if file_mode != 0o600:
            logger.warning(
                f"[!] device_secret has mode {oct(file_mode)}, "
                f"expected 0o600. Fixing permissions."
            )
            os.chmod(str(SECRET_PATH), 0o600)


def _compute_integrity_hash(secret: str) -> str:
    """Computes a SHA-256 hash of the secret for integrity verification."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _save_integrity_hash(secret: str):
    """Saves the integrity hash alongside the secret file."""
    integrity_hash = _compute_integrity_hash(secret)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    with os.fdopen(os.open(str(INTEGRITY_PATH), flags, 0o600), "w") as f:
        f.write(integrity_hash)


def _verify_integrity(secret: str) -> bool:
    """
    Verifies the device secret has not been tampered with by comparing
    its SHA-256 hash against the stored integrity hash.
    Returns True if integrity is intact, False if tampered.
    """
    if not INTEGRITY_PATH.exists():
        # No integrity file yet -- create one (first run after upgrade)
        logger.info("[*] Creating integrity hash for device secret.")
        _save_integrity_hash(secret)
        return True

    with open(INTEGRITY_PATH, "r") as f:
        stored_hash = f.read().strip()

    current_hash = _compute_integrity_hash(secret)
    return hmac.compare_digest(stored_hash, current_hash)


# ----------------------------------------------------------
# CORE FUNCTIONS
# ----------------------------------------------------------

def is_provisioned() -> bool:
    """Returns True if the shared secret exists on disk."""
    return SECRET_PATH.exists()

def generate_secret() -> str:
    """
    Generates a 32-byte hex secret and saves it to .keys/device_secret.
    """
    secret = secrets.token_hex(32)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(str(KEYS_DIR), 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    with os.fdopen(os.open(str(SECRET_PATH), flags, 0o600), "w") as f:
        f.write(secret)
    _save_integrity_hash(secret)
    logger.info("[*] Device secret saved securely to disk.")
    return secret

def load_secret() -> str:
    """
    Loads the shared secret from disk with permission and integrity checks.
    Raises RuntimeError if the device is not provisioned or if tampering
    is detected.
    """
    if not is_provisioned():
        raise RuntimeError("Device is not provisioned (device_secret missing).")

    # Enforce correct filesystem permissions on every load
    _enforce_permissions()

    with open(SECRET_PATH, "r") as f:
        secret = f.read().strip()

    # Integrity verification -- detect secret file tampering
    if not _verify_integrity(secret):
        logger.error(
            "[!!!] TAMPER ALERT: device_secret integrity check failed. "
            "The secret file may have been modified externally."
        )
        raise RuntimeError("Device secret integrity check failed -- possible tampering.")

    return secret

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

