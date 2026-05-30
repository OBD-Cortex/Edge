import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Required configuration
MONGO_URI = os.getenv("MONGO_URI")
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN")

# Optional configuration
SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "60.0"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "1800.0")) # 30 min
RECONNECT_COOLDOWN = float(os.getenv("RECONNECT_COOLDOWN", "30.0"))   # 30 seconds

# Atlas API Whitelisting configuration
ATLAS_PUBLIC_KEY = os.getenv("ATLAS_PUBLIC_KEY")
ATLAS_PRIVATE_KEY = os.getenv("ATLAS_PRIVATE_KEY")
ATLAS_PROJECT_ID = os.getenv("ATLAS_PROJECT_ID")
