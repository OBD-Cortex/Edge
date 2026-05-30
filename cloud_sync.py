import json
import datetime
import urllib.request
import urllib.parse
import pymongo
import certifi
from config import OFFLINE_MODE

def connect_to_mongodb(uri):
    """
    Establishes connection to MongoDB Atlas or local MongoDB.
    Returns (client, col_telemetry, col_devices) or (None, None, None).
    """
    if OFFLINE_MODE or not uri:
        print("[*] Offline mode or missing URI. MongoDB connection skipped.")
        return None, None, None

    try:
        # Configuration settings for reliability
        client_options = {
            "tlsCAFile": certifi.where(),
            "serverSelectionTimeoutMS": 3000,
            "maxPoolSize": 5,
            "appName": "obd-cortex-edge",
        }
        client = pymongo.MongoClient(uri, **client_options)
        # Test connection by pinging
        client.admin.command('ping')
        
        db = client["rag_db"]
        col_telemetry = db["vehicle_telemetry"]
        col_devices = db["devices"]
        return client, col_telemetry, col_devices
    except Exception as e:
        # Strip credentials from printing for safety
        redacted_uri = uri
        if "@" in uri:
            prefix = uri.split("@")[0]
            if "://" in prefix:
                proto = prefix.split("://")[0]
                redacted_uri = f"{proto}://[REDACTED_USER_PASS]@{uri.split('@')[1]}"
            else:
                redacted_uri = f"[REDACTED_USER_PASS]@{uri.split('@')[1]}"
        print(f"[!] Database Connection Attempt Failed: {e} (URI: {redacted_uri})")
        return None, None, None

def decode_vin(vin: str) -> tuple:
    """
    Decodes the VIN using the NHTSA vPIC API.
    Returns a tuple of (brand, model, year).
    If the API call fails or is invalid, returns ("Unknown", "Unknown", "Unknown").
    """
    if not vin or len(vin) != 17:
        print(f"[!] Invalid VIN length or structure: {vin}")
        return "Unknown", "Unknown", "Unknown"

    print(f"🔍 Decoding VIN [{vin}] via NHTSA vPIC API...")
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
    
    try:
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0"}
        )
        # Timeout of 3 seconds to avoid blocking boot sequence
        with urllib.request.urlopen(req, timeout=3.0) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            results = res_data.get("Results", [])
            if results:
                car_info = results[0]
                brand = car_info.get("Make", "").strip() or "Unknown"
                model = car_info.get("Model", "").strip() or "Unknown"
                year = car_info.get("ModelYear", "").strip() or "Unknown"
                return brand, model, year
    except Exception as e:
        print(f"[!] OBD-II: Failed to decode VIN from API: {e}")

    # Fallback to generic metadata
    return "Unknown", "Unknown", "Unknown"

def register_device(col_devices, device_token, vin, brand, model, year):
    """
    Binds the device token to the vehicle VIN and metadata in the database.
    Preserves 'paired' status if an owner_id exists on the token.
    Uses 'is not None' for Collection truthiness safety.
    """
    if col_devices is None:
        return False
    try:
        device_record = col_devices.find_one({"device_token": device_token})
        if device_record:
            status = "registered" if not device_record.get("owner_id") else "paired"
            col_devices.update_one(
                {"device_token": device_token},
                {
                    "$set": {
                        "vin": vin,
                        "brand": brand,
                        "model": model,
                        "year": year,
                        "status": status,
                        "registered_at": datetime.datetime.now(datetime.timezone.utc)
                    }
                }
            )
            print(f"[✓] Cloud Registry: Token [{device_token}] mapped to VIN [{vin}] ({brand} {model} {year}) as '{status}'.")
            return True
        else:
            print(f"[!] Cloud Registry Warning: Token [{device_token}] not found in database.")
            return False
    except Exception as e:
        print(f"[!] Cloud Registry: Failed to sync device binding: {e}")
        return False

def upload_telemetry(col_telemetry, snapshot):
    """
    Uploads a single telemetry document directly to MongoDB.
    Uses 'is not None' for Collection truthiness safety.
    """
    if col_telemetry is None:
        return False
    try:
        col_telemetry.insert_one(snapshot)
        return True
    except Exception as e:
        print(f"[!] Direct Telemetry Upload failed: {e}")
        return False
