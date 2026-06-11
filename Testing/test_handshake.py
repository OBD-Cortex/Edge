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
from services.provisioning import provision_device

def main():
    # Use a real valid VIN for testing (e.g., a 2018 Ford Mustang GT)
    valid_test_vin = "1FA6P8CF0J5100001" 
    
    print("==================================================")
    print("Starting Embedded Edge Handshake & Sync Test")
    print("==================================================")
    
    # Verify environment variables were loaded
    edge_service_url = os.getenv("EDGE_API_URL") or os.getenv("EDGE_SERVICE_URL")
    device_token = os.getenv("DEVICE_TOKEN")
    
    print(f"    Target Service URL: {edge_service_url}")
    print(f"    Device Token:       {device_token[:6] + '...' if device_token else '[Not Set]'}")
    
    if not edge_service_url:
        print("[ERROR] EDGE_API_URL or EDGE_SERVICE_URL environment variable is not set.")
        return
    if not device_token:
        print("[ERROR] DEVICE_TOKEN environment variable is not set. Cannot provision.")
        return

    try:
        # Note: provision_device relies on the config.py pulling the env vars automatically
        # VIN decoding is handled server-side by the Edge-Service, so we register with default metadata.
        device_id = provision_device(
            vin=valid_test_vin, 
            brand="Unknown", 
            model="Unknown", 
            year="Unknown"
        )
        print(f"\n[OK] TEST PASSED: Handshake successful! The Backend assigned Device ID: {device_id}")
        print(f"    Check the '.keys' folder to see the newly generated device_secret and device_id files.")
    except Exception as e:
        print(f"\n[ERROR] TEST FAILED: Unable to register the device. {e}")

if __name__ == "__main__":
    main()
