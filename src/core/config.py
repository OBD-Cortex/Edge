import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

RAG_API_URL = os.getenv("RAG_API_URL")
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN")

SCAN_INTERVAL = float(os.getenv("SCAN_INTERVAL", "60.0"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "1800.0"))

# ISO-TP Padding byte (0xAA or 0x55)
CAN_PADDING_BYTE = int(os.getenv("CAN_PADDING_BYTE", "0xAA"), 16)

def __getattr__(name):
    if name == "DEVICE_ID":
        path = BASE_DIR / ".keys" / "device_id"
        if path.exists():
            try:
                if val := path.read_text().strip():
                    return int(val)
            except Exception:
                pass
        return None
    raise AttributeError(f"module {__name__} has no attribute {name}")

