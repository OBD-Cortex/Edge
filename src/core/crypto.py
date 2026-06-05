import os
import datetime
import logging
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from core.config import BASE_DIR

logger = logging.getLogger(__name__)

KEYS_DIR = BASE_DIR / ".keys"
PRIVATE_KEY_PATH = KEYS_DIR / "private.pem"

def is_provisioned() -> bool:
    """
    Returns True if the private key file exists on disk.
    """
    return PRIVATE_KEY_PATH.exists()

def generate_key_pair() -> str:
    """
    Generates a secp256r1 (NIST P-256) key pair.
    Saves the private key to .keys/private.pem with 0600 permissions.
    Returns the PEM-encoded public key as a string.
    """
    try:
        logger.info("Generating secp256r1 ECDSA key pair...")
        private_key = ec.generate_private_key(ec.SECP256R1())
        
        # Serialize private key to PEM
        pem_private = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Serialize public key to PEM
        pem_public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")
        
        # Ensure the .keys directory exists
        KEYS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Write private key PEM with 0600 (owner read/write) permissions
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        with os.fdopen(os.open(str(PRIVATE_KEY_PATH), flags, mode), "wb") as f:
            f.write(pem_private)
            
        logger.info("[✓] Private key saved securely to disk.")
        return pem_public
    except Exception as e:
        logger.error(f"[!] Failed to generate or save key pair: {e}")
        raise

def load_private_key():
    """
    Loads the private key from disk.
    Raises RuntimeError if the file is missing.
    """
    if not is_provisioned():
        raise RuntimeError("Device is not provisioned (private.pem is missing).")
        
    try:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            pem_data = f.read()
        return serialization.load_pem_private_key(pem_data, password=None)
    except Exception as e:
        logger.error(f"[!] Failed to load private key from disk: {e}")
        raise RuntimeError(f"Failed to load private key: {e}")

def sign_payload(payload_bytes: bytes) -> tuple:
    """
    Signs the raw payload bytes concatenated with a newly generated UTC timestamp.
    The data to sign is: timestamp_str.encode('utf-8') + payload_bytes
    Returns a tuple of (signature_hex, timestamp_str).
    """
    private_key = load_private_key()
    timestamp_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Concatenate timestamp string and raw payload bytes
    data_to_sign = timestamp_str.encode("utf-8") + payload_bytes
    
    try:
        signature = private_key.sign(
            data_to_sign,
            ec.ECDSA(hashes.SHA256())
        )
        signature_hex = signature.hex()
        return signature_hex, timestamp_str
    except Exception as e:
        logger.error(f"[!] Failed to sign payload: {e}")
        raise RuntimeError(f"Signing operation failed: {e}")
