import logging
import requests
from pathlib import Path
from core.config import BASE_DIR, RAG_API_URL, DEVICE_TOKEN
from core.crypto import generate_key_pair

logger = logging.getLogger(__name__)

KEYS_DIR = BASE_DIR / ".keys"
DEVICE_ID_PATH = KEYS_DIR / "device_id"

def provision_device(vin: str, brand: str, model: str, year: str) -> int:
    """
    Performs one-time device provisioning.
    1. Generates an ECDSA key pair and saves the private key.
    2. Sends the public key and vehicle info to the central API.
    3. Saves the returned device_id on success.
    
    Raises RuntimeError on any failure.
    """
    if not RAG_API_URL:
        raise RuntimeError("RAG_API_URL is not configured.")
        
    if not DEVICE_TOKEN:
        raise RuntimeError("DEVICE_TOKEN is not configured. Unable to provision new device.")

    logger.info("Starting one-time device provisioning flow...")
    
    # 1. Generate local key pair
    try:
        public_key_pem = generate_key_pair()
    except Exception as e:
        raise RuntimeError(f"Failed to generate key pair: {e}")

    # 2. Register public key with the central server
    url = f"{RAG_API_URL}/api/device/provision"
    headers = {
        "X-Device-Token": DEVICE_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "public_key": public_key_pem,
        "vin": vin,
        "brand": brand,
        "model": model,
        "year": year
    }
    
    try:
        logger.info(f"Sending provisioning request to RAG server at {url}...")
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if res.status_code != 200:
            logger.error(f"[!] Provisioning API returned status {res.status_code}: {res.text}")
            raise RuntimeError(f"Server rejected provisioning request (HTTP {res.status_code})")
            
        res_json = res.json()
        device_id = res_json.get("device_id")
        if device_id is None:
            # Check if nested in some other field or structure
            logger.error(f"[!] Unexpected provisioning response: {res.text}")
            raise RuntimeError("Provisioning response did not contain 'device_id'.")
            
        # 3. Persist the assigned device_id
        KEYS_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEVICE_ID_PATH, "w") as f:
            f.write(str(device_id))
            
        logger.info(f"[✓] Device successfully provisioned. Assigned Device ID: {device_id}")
        return int(device_id)
        
    except requests.RequestException as e:
        logger.error(f"[!] Network error during device provisioning: {e}")
        raise RuntimeError(f"Network error during provisioning: {e}")
    except Exception as e:
        if not isinstance(e, RuntimeError):
            logger.error(f"[!] Unexpected error during provisioning: {e}")
        raise
