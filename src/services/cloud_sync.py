import datetime
import requests
import logging
from core.config import RAG_API_URL, DEVICE_TOKEN

logger = logging.getLogger(__name__)

def decode_vin(vin: str) -> tuple:
    """
    Decodes the VIN using the NHTSA vPIC API.
    Returns a tuple of (brand, model, year).
    If the API call fails or is invalid, returns ("Unknown", "Unknown", "Unknown").
    """
    if not vin or len(vin) != 17:
        logger.warning(f"Invalid VIN length or structure: {vin}")
        return "Unknown", "Unknown", "Unknown"

    logger.info(f"Decoding VIN [{vin}] via NHTSA vPIC API...")
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
    
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "OBD-Cortex/1.0"})
        resp.raise_for_status()
        res_data = resp.json()
        results = res_data.get("Results", [])
        if results:
            car_info = results[0]
            brand = car_info.get("Make", "").strip() or "Unknown"
            model = car_info.get("Model", "").strip() or "Unknown"
            year = car_info.get("ModelYear", "").strip() or "Unknown"
            return brand, model, year
    except Exception as e:
        logger.error(f"OBD-II: Failed to decode VIN from API: {e}")

    # Fallback to generic metadata
    return "Unknown", "Unknown", "Unknown"

def register_device(device_token, vin, brand, model, year):
    """
    Registers the device with the RAG API, binding it to the vehicle VIN.
    """
    if not RAG_API_URL or not device_token:
        logger.error("Missing RAG_API_URL or DEVICE_TOKEN.")
        return False
        
    try:
        url = f"{RAG_API_URL}/api/device/register"
        headers = {"X-Device-Token": device_token}
        payload = {
            "vin": vin,
            "brand": brand,
            "model": model,
            "year": year
        }
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            redacted_token = f"{device_token[:8]}..." if device_token else "None"
            logger.info(f"Cloud Registry: Token [{redacted_token}] mapped to VIN [{vin}] ({brand} {model} {year}).")
            return True
        else:
            logger.warning(f"Cloud Registry Warning: API returned {res.status_code}: {res.text}")
            return False
    except Exception as e:
        logger.error(f"Cloud Registry: Failed to sync device binding: {e}")
        return False
