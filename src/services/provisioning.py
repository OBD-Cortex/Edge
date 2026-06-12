import logging
import httpx
from core.config import BASE_DIR, EDGE_SERVICE_URL, DEVICE_TOKEN
from core.crypto import generate_secret

logger = logging.getLogger(__name__)

KEYS_DIR = BASE_DIR / ".keys"
DEVICE_ID_PATH = KEYS_DIR / "device_id"
DEVICE_SECRET_PATH = KEYS_DIR / "device_secret"


def clear_provisioning_keys():
    """
    Removes the on-disk provisioning artefacts (device_secret and device_id).
    Called automatically when the server returns HTTP 403, indicating the
    locally stored HMAC secret is stale (e.g. after a device token rotation
    in the admin dashboard).
    After this call, is_provisioned() will return False and the next main
    loop iteration will trigger a fresh provisioning handshake.
    """
    removed = []
    for path in (DEVICE_SECRET_PATH, DEVICE_ID_PATH):
        if path.exists():
            try:
                path.unlink()
                removed.append(path.name)
            except OSError as e:
                logger.error(f"[!] Failed to remove {path.name}: {e}")

    if removed:
        logger.warning(f"[!] Provisioning keys cleared ({', '.join(removed)}). "
                       "Re-provisioning will occur on next loop iteration.")
    else:
        logger.info("[*] No provisioning keys were present to clear.")


def provision_device(vin: str, brand: str, model: str, year: str) -> int:
    """
    Performs one-time device provisioning.
    1. Generates a symmetric HMAC secret.
    2. Sends the secret and vehicle info to the central API.
    3. Saves the returned device_id on success.
    """
    if not EDGE_SERVICE_URL or not DEVICE_TOKEN:
        raise RuntimeError("EDGE_SERVICE_URL or DEVICE_TOKEN missing. Unable to provision.")

    logger.info("Starting one-time device provisioning flow...")
    secret = generate_secret()

    url = f"{EDGE_SERVICE_URL}/api/device/provision"
    headers = {"X-Device-Token": DEVICE_TOKEN, "Content-Type": "application/json"}
    payload = {"device_secret": secret, "vin": vin, "brand": brand, "model": model, "year": year}

    try:
        logger.info(f"Sending provisioning request to {url}...")
        res = httpx.post(url, json=payload, headers=headers, timeout=10)
        res.raise_for_status()

        device_id = res.json().get("device_id")
        if device_id is None:
            raise RuntimeError("Provisioning response missing 'device_id'.")

        KEYS_DIR.mkdir(parents=True, exist_ok=True)
        DEVICE_ID_PATH.write_text(str(device_id))

        logger.info(f"[+] Device successfully provisioned. Assigned Device ID: {device_id}")
        return int(device_id)

    except httpx.HTTPError as e:
        logger.error(f"[!] Network error during device provisioning: {e}")
        raise RuntimeError(f"Network error during provisioning: {e}")
