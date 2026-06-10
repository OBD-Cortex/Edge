import os
import sys
from pathlib import Path

# Dynamically calculate the EDGE_ROOT based on this script's location
# Assuming the script is run from the Edge root or Testing folder
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

# Now import the correctly separated services
from services.cloud_sync import decode_vin
from services.provisioning import provision_device

def main():
    # Use a real valid VIN for testing (e.g., a 2018 Ford Mustang GT)
    valid_test_vin = "1FA6P8CF0J5100001" 
    
    print("==================================================")
    print("Starting Embedded Edge VIN Decoding & Sync Test")
    print("==================================================")
    
    # 1. Test NHTSA API Decoding (Component 2.4)
    brand, model, year = decode_vin(valid_test_vin)
    print(f"\n[1] NHTSA Decoding Result:")
    print(f"    VIN:   {valid_test_vin}")
    print(f"    Brand: {brand}")
    print(f"    Model: {model}")
    print(f"    Year:  {year}")
    
    if brand == "Unknown" and model == "Unknown":
        print("[!] Warning: NHTSA API query failed or returned 'Unknown'. Ensure your Edge device has internet access.")
    else:
        print("[✓] Successfully decoded VIN locally!")

    # 2. Test Zero-Trust Provisioning Handshake (Component 2.3)
    print(f"\n[2] Device Registration Test:")
    
    # Verify environment variables were loaded
    rag_api_url = os.getenv("RAG_API_URL")
    device_token = os.getenv("DEVICE_TOKEN")
    
    print(f"    Target RAG API URL: {rag_api_url}")
    print(f"    Device Token:       {device_token}")
    
    if not rag_api_url:
        print("[!] Error: RAG_API_URL environment variable is not set.")
        return
    if not device_token:
        print("[!] Error: DEVICE_TOKEN environment variable is not set. Cannot provision.")
        return

    try:
        # Note: provision_device relies on the config.py pulling the env vars automatically
        device_id = provision_device(vin=valid_test_vin, brand=brand, model=model, year=year)
        print(f"\n[✓] TEST PASSED: Handshake successful! The Backend assigned Device ID: {device_id}")
        print(f"    Check the '.keys' folder to see the newly generated device_secret and device_id files.")
    except Exception as e:
        print(f"\n[✗] TEST FAILED: Unable to register the device. {e}")

if __name__ == "__main__":
    main()
