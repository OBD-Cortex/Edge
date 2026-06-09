import requests
import logging

logger = logging.getLogger(__name__)

def decode_vin(vin: str) -> tuple:
    """Decodes VIN via NHTSA vPIC API. Returns (brand, model, year)."""
    if not vin or len(vin) != 17:
        logger.warning(f"Invalid VIN length or structure: {vin}")
        return "Unknown", "Unknown", "Unknown"

    logger.info(f"Decoding VIN [{vin}] via NHTSA vPIC API...")
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
    
    try:
        res = requests.get(url, timeout=5, headers={"User-Agent": "OBD-Cortex/1.0"}).json()
        if results := res.get("Results"):
            info = results[0]
            return (
                info.get("Make", "").strip() or "Unknown",
                info.get("Model", "").strip() or "Unknown",
                info.get("ModelYear", "").strip() or "Unknown"
            )
    except Exception as e:
        logger.error(f"OBD-II: Failed to decode VIN from API: {e}")

    return "Unknown", "Unknown", "Unknown"
