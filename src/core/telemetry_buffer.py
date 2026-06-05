import os
import json
import sqlite3
import datetime
import requests
import logging
from pathlib import Path
from core.config import BASE_DIR
from core import config
from core.crypto import sign_payload

logger = logging.getLogger(__name__)

SQLITE_DB_PATH = BASE_DIR / "telemetry_buffer.db"
ARCHIVE_DIR = BASE_DIR / "archive"

def init_buffer():
    """
    Initializes the SQLite database schema if it does not exist.
    """
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS buffered_telemetry (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
        finally:
            conn.close()
        logger.info("[✓] SQLite buffer database initialized.")
    except Exception as e:
        logger.error(f"SQLite initialization error: {e}")

def save_to_buffer(telemetry_dict):
    """
    Serializes and stores a telemetry snapshot to the SQLite database.
    """
    try:
        payload_str = json.dumps(telemetry_dict)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        conn = sqlite3.connect(SQLITE_DB_PATH)
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO buffered_telemetry (payload, created_at) VALUES (?, ?)",
                    (payload_str, timestamp)
                )
        finally:
            conn.close()
        
        summary = telemetry_dict.get("scan_summary", "No Summary")
        logger.info(f"Buffered 1 snapshot | Summary: {summary[:50]}...")
        return True
    except Exception as e:
        logger.error(f"SQLite failed to save snapshot: {e}")
        return False

def get_buffered_entries():
    """
    Retrieves all buffered telemetry snapshots.
    Returns a list of tuples: (id, payload_dict)
    """
    entries = []
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        try:
            cursor = conn.cursor()
            # Limit to 100 entries to comply with Backend API batch limit
            cursor.execute("SELECT id, payload FROM buffered_telemetry ORDER BY id ASC LIMIT 100")
            rows = cursor.fetchall()
            
            for row in rows:
                entry_id, payload_str = row
                payload_dict = json.loads(payload_str)
                entries.append((entry_id, payload_dict))
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"SQLite failed to read buffered entries: {e}")
    return entries

def datetime_decoder(dct):
    """
    Custom JSON decoder to reconstruct datetime objects.
    """
    if "__datetime__" in dct:
        val = dct["__datetime__"]
        if val.endswith('Z'):
            val = val[:-1] + '+00:00'
        return datetime.datetime.fromisoformat(val)
    return dct

def format_datetime(obj):
    """
    Format datetime objects as ISO-8601 strings for the cloud API.
    """
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def remove_entries(ids):
    """
    Removes entries from SQLite by list of IDs.
    """
    if not ids:
        return
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        try:
            with conn:
                cursor = conn.cursor()
                # SQLite parameters formatting for IN clause
                placeholders = ",".join("?" for _ in ids)
                cursor.execute(f"DELETE FROM buffered_telemetry WHERE id IN ({placeholders})", tuple(ids))
        finally:
            conn.close()
        logger.info(f"Cleared {len(ids)} uploaded entries from buffer.")
    except Exception as e:
        logger.error(f"SQLite failed to delete entries: {e}")

def archive_entries(entries):
    """
    Saves successfully uploaded entries to a backup JSON file in the archive/ directory.
    """
    if not entries:
        return
    try:
        if not ARCHIVE_DIR.exists():
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = ARCHIVE_DIR / f"{timestamp_str}.json"
        
        with open(archive_file, "w") as f:
            json.dump(entries, f, indent=2)
            
        logger.info(f"Saved {len(entries)} snapshots to backup: {archive_file.name}")
    except Exception as e:
        logger.error(f"Failed to archive snapshots: {e}")

def flush_to_cloud():
    """
    Tries to upload all buffered entries to the Central RAG API.
    On success, archives them locally and deletes them from SQLite.
    """
    if not config.RAG_API_URL or config.DEVICE_ID is None:
        logger.warning("RAG_API_URL is missing or Device is not provisioned. Skipping flush.")
        return
        
    entries = get_buffered_entries()
    if not entries:
        return

    logger.info(f"Flushing {len(entries)} buffered entries to Cloud API...")
    
    uploaded_ids = [entry_id for entry_id, _ in entries]
    payloads = [payload for _, payload in entries]
    
    try:
        url = f"{config.RAG_API_URL}/api/telemetry"
        
        # Serialize the payloads list using a pure functional encoder
        serialized_payloads = json.dumps(payloads, default=format_datetime)
        payload_bytes = serialized_payloads.encode("utf-8")
        
        # Sign the serialized payload bytes
        signature_hex, timestamp_str = sign_payload(payload_bytes)
        
        headers = {
            "X-Device-ID": str(config.DEVICE_ID),
            "X-Signature": signature_hex,
            "X-Timestamp": timestamp_str,
            "Content-Type": "application/json"
        }
        
        res = requests.post(url, data=serialized_payloads, headers=headers, timeout=10)
        
        if res.status_code == 200:
            # Archive first for safety
            archive_entries(payloads)
            # Clear from SQLite
            remove_entries(uploaded_ids)
            logger.info(f"Successfully flushed {len(uploaded_ids)} entries.")
        else:
            logger.error(f"Failed to batch upload buffered entries: API returned {res.status_code}: {res.text}")
    except Exception as e:
        logger.error(f"Failed to batch upload buffered entries: {e}")
