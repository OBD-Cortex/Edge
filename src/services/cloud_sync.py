import datetime
import requests
import logging
from core.config import RAG_API_URL

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
