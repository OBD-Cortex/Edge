import os
import datetime
import urllib.request
import json
import requests
from requests.auth import HTTPDigestAuth
from core.config import ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY, ATLAS_PROJECT_ID

# Whitelist duration (in hours)
WHITELIST_DURATION_HOURS = 2

def get_public_ip():
    """Fetches the current public IP of the device."""
    try:
        req = urllib.request.Request(
            "https://api.ipify.org",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read().decode("utf-8").strip()
    except Exception as e:
        print(f"[!] Whitelist: Failed to resolve device public IP: {e}")
        return None

def whitelist_device_ip():
    """
    Programmatically whitelists the device's public IP in MongoDB Atlas
    with an automatic expiration (deleteAfter) of 24 hours.
    """
    if not ATLAS_PUBLIC_KEY or not ATLAS_PRIVATE_KEY or not ATLAS_PROJECT_ID:
        print("[!] Whitelist: Missing Atlas API key configuration. Skipping automatic whitelisting.")
        return False

    ip = get_public_ip()
    if not ip:
        print("[!] Whitelist: Could not resolve public IP. Skipping whitelisting.")
        return False

    print(f"📡 Whitelist: Detected device public IP: {ip}")

    # Calculate expiration time in ISO 8601 format (UTC)
    expiry_time = (datetime.datetime.now(datetime.timezone.utc) + 
                   datetime.timedelta(hours=WHITELIST_DURATION_HOURS))
    expiry_str = expiry_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    url = f"https://cloud.mongodb.com/api/atlas/v1.0/groups/{ATLAS_PROJECT_ID}/accessList"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # Access List Payload with auto-delete after duration
    payload = [{
        "ipAddress": ip,
        "comment": "Auto-generated for OBD-Cortex Gateway",
        "deleteAfterDate": expiry_str
    }]

    try:
        response = requests.post(
            url,
            auth=HTTPDigestAuth(ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY),
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code in [200, 201]:
            print(f"[✓] Whitelist: Whitelisted {ip} on Atlas. Will auto-delete at {expiry_str}")
            return True
        elif response.status_code == 409:
            # 409 Conflict: Already exists
            print(f"[✓] Whitelist: IP {ip} is already whitelisted on Atlas.")
            return True
        elif response.status_code == 400 and "PERMANENT_ENTITY_CANNOT_BE_MADE_TEMPORARY" in response.text:
            print(f"[✓] Whitelist: IP {ip} is already whitelisted permanently on Atlas.")
            return True
        else:
            print(f"[!] Whitelist: Atlas API rejected request (Status {response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"[!] Whitelist: Atlas API connection error: {e}")
        return False

if __name__ == "__main__":
    whitelist_device_ip()
