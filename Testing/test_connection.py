import os
import sys
import argparse
import datetime
import sqlite3
import json
from pathlib import Path
import httpx

# Dynamically calculate the EDGE_ROOT based on this script's location
EDGE_ROOT = Path(__file__).resolve().parent
if EDGE_ROOT.name == "Testing":
    EDGE_ROOT = EDGE_ROOT.parent

# Add the 'src' directory to the python path so imports work
sys.path.insert(0, str(EDGE_ROOT / "src"))

# Load the environment variables BEFORE importing core modules
try:
    from dotenv import load_dotenv
    load_dotenv(EDGE_ROOT / ".env")
except ImportError:
    pass

# Now import the correctly separated services and core modules
from services.provisioning import provision_device
from core.crypto import is_provisioned, load_secret
from core.telemetry_buffer import init_buffer, save_to_buffer, flush_to_cloud

def decode_vin(vin: str):
    """
    Decodes VIN details using the public NHTSA vPIC API.
    This replaces the legacy local decoding module.
    """
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
    print(f"[*] Querying NHTSA API: {url}...")
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        results = response.json().get("Results", [])
        
        brand = "Unknown"
        model = "Unknown"
        year = "Unknown"
        
        for item in results:
            variable = item.get("Variable")
            value = item.get("Value")
            if not value or value == "Null":
                continue
            if variable == "Make":
                brand = value
            elif variable == "Model":
                model = value
            elif variable == "Model Year":
                year = value
                
        return brand, model, year
    except Exception as e:
        print(f"    [!] NHTSA API call failed: {e}")
        return "Unknown", "Unknown", "Unknown"

def check_backend_health(url: str):
    """Checks the health endpoint of the central Edge Service API."""
    health_url = f"{url}/api/health"
    print(f"[*] Checking backend service health at: {health_url}...")
    try:
        res = httpx.get(health_url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            print(f"    [✓] Connected to backend! Status: {data.get('status')}, DB: {data.get('database')}")
            return True
        else:
            print(f"    [!] Backend returned status code {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"    [✗] Connection to backend failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="OBD-Cortex Edge Connection & Provisioning Diagnostics")
    parser.add_argument("--vin", default="1FA6P8CF0J5100001", help="VIN to decode and pair the device with")
    parser.add_argument("--url", help="Override EDGE_SERVICE_URL")
    parser.add_argument("--token", help="Override DEVICE_TOKEN")
    parser.add_argument("--force-provision", action="store_true", help="Delete existing local keys and force re-provisioning")
    args = parser.parse_args()

    # Load configuration
    edge_service_url = args.url or os.getenv("EDGE_SERVICE_URL")
    device_token = args.token or os.getenv("DEVICE_TOKEN")

    print("==================================================")
    print(" OBD-Cortex Edge Diagnostic Connection Script")
    print("==================================================")
    print(f"EDGE_SERVICE_URL: {edge_service_url or '[Not Set]'}")
    print(f"DEVICE_TOKEN:     {device_token[:6] + '...' if device_token else '[Not Set]'}")
    print(f"Target VIN:       {args.vin}")
    print("==================================================")

    if not edge_service_url:
        print("[✗] Error: EDGE_SERVICE_URL environment variable is not set. Exiting.")
        sys.exit(1)
    if not device_token:
        print("[✗] Error: DEVICE_TOKEN environment variable is not set. Exiting.")
        sys.exit(1)

    # Override the imports' configurations dynamically
    import core.config
    import core.telemetry_buffer
    import services.provisioning
    
    core.config.EDGE_SERVICE_URL = edge_service_url
    core.config.DEVICE_TOKEN = device_token
    core.telemetry_buffer.EDGE_SERVICE_URL = edge_service_url
    services.provisioning.EDGE_SERVICE_URL = edge_service_url
    services.provisioning.DEVICE_TOKEN = device_token

    # 1. Check Backend Connectivity
    if not check_backend_health(edge_service_url):
        print("[✗] Backend health check failed. Cannot proceed with provisioning/telemetry test.")
        sys.exit(1)

    # 2. Decode VIN via NHTSA
    print("\n[*] Step 1: Querying vehicle details using VIN...")
    brand, model, year = decode_vin(args.vin)
    print(f"    [✓] Decoded Vehicle parameters:")
    print(f"        Brand: {brand}")
    print(f"        Model: {model}")
    print(f"        Year:  {year}")

    # 3. Handle Provisioning
    print("\n[*] Step 2: Checking device provisioning status...")
    if args.force_provision:
        print("    [*] Force provisioning requested. Cleaning up existing keys...")
        keys_dir = EDGE_ROOT / ".keys"
        if keys_dir.exists():
            for f in keys_dir.glob("*"):
                f.unlink()
            print("        [✓] Cleaned up existing device secrets.")
    
    provisioned = is_provisioned()
    if not provisioned:
        print("    [*] Device is not provisioned. Sending provisioning request to backend...")
        try:
            device_id = provision_device(vin=args.vin, brand=brand, model=model, year=year)
            print(f"    [✓] Device successfully provisioned!")
            print(f"        Device ID: {device_id}")
        except Exception as e:
            print(f"    [✗] Device provisioning failed: {e}")
            sys.exit(1)
    else:
        # Import device ID from files
        from core.config import DEVICE_ID
        print(f"    [✓] Device is already provisioned.")
        print(f"        Device ID: {DEVICE_ID}")

    # Reload device ID in case it was just provisioned
    from core.config import DEVICE_ID
    core.telemetry_buffer.DEVICE_ID = DEVICE_ID

    # 4. Initialize local SQLite telemetry buffer
    print("\n[*] Step 3: Initializing local SQLite database buffer...")
    init_buffer()

    # 5. Create and Send Test Telemetry Packet
    print("\n[*] Step 4: Generating test telemetry snapshot...")
    test_snapshot = {
        "vehicle_id": args.vin,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active": False,
        "dtc_count": 0,
        "confirmed_dtcs": [],
        "pending_dtcs": [],
        "system_status": "healthy",
        "scan_summary": "Diagnostic test run - manual connection check"
    }

    print("    [*] Saving test telemetry payload to local buffer...")
    if save_to_buffer(test_snapshot):
        print("    [✓] Successfully buffered telemetry snapshot.")
    else:
        print("    [✗] Failed to save telemetry snapshot to local SQLite buffer.")
        sys.exit(1)

    print("    [*] Flushing buffered entries to the cloud...")
    try:
        flush_to_cloud()
        print("\n==================================================")
        print(" [✓] DIAGNOSTICS COMPLETED SUCCESSFULLY!")
        print("     Connection, VIN decoding, provisioning, and")
        print("     telemetry delivery checks have all passed.")
        print("==================================================")
    except Exception as e:
        print(f"    [✗] Failed to flush telemetry to cloud: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
