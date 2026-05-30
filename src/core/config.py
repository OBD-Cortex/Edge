import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# Required configuration
RAG_API_URL = os.getenv("RAG_API_URL")
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN")

# Optional configuration
SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "60.0"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "1800.0")) # 30 min
RECONNECT_COOLDOWN = float(os.getenv("RECONNECT_COOLDOWN", "30.0"))   # 30 seconds

