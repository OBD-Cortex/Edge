import json
import sqlite3
import datetime
import requests
import logging
from core.config import BASE_DIR, RAG_API_URL, DEVICE_ID
from core.crypto import sign_payload

logger = logging.getLogger(__name__)

SQLITE_DB_PATH = BASE_DIR / "telemetry_buffer.db"
ARCHIVE_DIR = BASE_DIR / "archive"

def init_buffer():
    """Initializes the SQLite database schema if it does not exist."""
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS buffered_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        logger.info("[✓] SQLite buffer database initialized.")
    except Exception as e:
        logger.error(f"SQLite initialization error: {e}")

def save_to_buffer(telemetry_dict):
    """Serializes and stores a telemetry snapshot to the SQLite database."""
    try:
        payload_str = json.dumps(telemetry_dict)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO buffered_telemetry (payload, created_at) VALUES (?, ?)",
                (payload_str, timestamp)
            )
        
        summary = telemetry_dict.get("scan_summary", "No Summary")
        logger.info(f"Buffered 1 snapshot | Summary: {summary[:50]}...")
        return True
    except Exception as e:
        logger.error(f"SQLite failed to save snapshot: {e}")
        return False

def get_buffered_entries():
    """Retrieves up to 100 buffered telemetry snapshots. Returns [(id, payload_dict)]."""
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            rows = conn.execute("SELECT id, payload FROM buffered_telemetry ORDER BY id ASC LIMIT 100").fetchall()
            return [(row[0], json.loads(row[1])) for row in rows]
    except Exception as e:
        logger.error(f"SQLite failed to read buffered entries: {e}")
        return []

def format_datetime(obj):
    """Format datetime objects as ISO-8601 strings for the cloud API."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def remove_entries(ids):
    """Removes entries from SQLite by list of IDs."""
    if not ids:
        return
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM buffered_telemetry WHERE id IN ({placeholders})", tuple(ids))
        logger.info(f"Cleared {len(ids)} uploaded entries from buffer.")
    except Exception as e:
        logger.error(f"SQLite failed to delete entries: {e}")



def flush_to_cloud():
    """Tries to upload all buffered entries to the Central RAG API."""
    if not RAG_API_URL or DEVICE_ID is None:
        logger.warning("RAG_API_URL missing or Device not provisioned. Skipping flush.")
        return
        
    entries = get_buffered_entries()
    if not entries:
        return

    logger.info(f"Flushing {len(entries)} buffered entries to Cloud API...")
    
    uploaded_ids = [e[0] for e in entries]
    payloads = [e[1] for e in entries]
    
    try:
        serialized_payloads = json.dumps(payloads, default=format_datetime)
        payload_bytes = serialized_payloads.encode("utf-8")
        signature_hex, timestamp_str = sign_payload(payload_bytes)
        
        headers = {
            "X-Device-ID": str(DEVICE_ID),
            "X-Signature": signature_hex,
            "X-Timestamp": timestamp_str,
            "Content-Type": "application/json"
        }
        
        res = requests.post(f"{RAG_API_URL}/api/telemetry", data=payload_bytes, headers=headers, timeout=10)
        
        if res.status_code == 200:
            remove_entries(uploaded_ids)
            logger.info(f"Successfully flushed {len(uploaded_ids)} entries.")
        else:
            logger.error(f"Failed to batch upload buffered entries: API returned {res.status_code}: {res.text}")
    except Exception as e:
        logger.error(f"Failed to batch upload buffered entries: {e}")
