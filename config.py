import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Required configuration
MONGO_URI = os.getenv("MONGO_URI")
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "OBD-DEV-MOCK")

# Optional configuration
SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "60.0"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "1800.0")) # 30 min
RECONNECT_COOLDOWN = float(os.getenv("RECONNECT_COOLDOWN", "30.0"))   # 30 seconds

# Program execution modes
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "0") == "1" or "--offline" in sys.argv

# For backward compatibility if someone still uses UNAME, PW, C_URL
if not MONGO_URI and os.getenv("C_URL"):
    import urllib.parse
    username = os.getenv("UNAME")
    password = os.getenv("PW")
    cluster_url = os.getenv("C_URL")
    clean_cluster_url = cluster_url.replace("mongodb+srv://", "").split("/")[0]
    user = urllib.parse.quote_plus(username or "")
    pw = urllib.parse.quote_plus(password or "")
    MONGO_URI = f"mongodb+srv://{user}:{pw}@{clean_cluster_url}/?retryWrites=true&w=majority"
elif not MONGO_URI:
    MONGO_URI = "mongodb://localhost:27017/rag_db"
