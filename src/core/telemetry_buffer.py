import os
import json
import sqlite3
import datetime
from pathlib import Path
from core.config import BASE_DIR

SQLITE_DB_PATH = BASE_DIR / "telemetry_buffer.db"
ARCHIVE_DIR = BASE_DIR / "archive"

class DateTimeEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to support serializing datetime objects.
    """
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return {"__datetime__": obj.isoformat()}
        return super().default(obj)

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

def init_buffer():
    """
    Initializes the SQLite database schema if it does not exist.
    """
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS buffered_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        print("[✓] SQLite buffer database initialized.")
    except Exception as e:
        print(f"[!] SQLite initialization error: {e}")

def save_to_buffer(telemetry_dict):
    """
    Serializes and stores a telemetry snapshot to the SQLite database.
    """
    try:
        payload_str = json.dumps(telemetry_dict, cls=DateTimeEncoder)
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO buffered_telemetry (payload, created_at) VALUES (?, ?)",
                (payload_str, timestamp)
            )
            conn.commit()
        
        summary = telemetry_dict.get("scan_summary", "No Summary")
        print(f"[SQLite] Buffered 1 snapshot | Summary: {summary[:50]}...")
        return True
    except Exception as e:
        print(f"[!] SQLite failed to save snapshot: {e}")
        return False

def get_buffered_entries():
    """
    Retrieves all buffered telemetry snapshots.
    Returns a list of tuples: (id, payload_dict)
    """
    entries = []
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, payload FROM buffered_telemetry ORDER BY id ASC")
            rows = cursor.fetchall()
            
            for row in rows:
                entry_id, payload_str = row
                payload_dict = json.loads(payload_str, object_hook=datetime_decoder)
                entries.append((entry_id, payload_dict))
    except Exception as e:
        print(f"[!] SQLite failed to read buffered entries: {e}")
    return entries

def remove_entries(ids):
    """
    Removes entries from SQLite by list of IDs.
    """
    if not ids:
        return
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            cursor = conn.cursor()
            # SQLite parameters formatting for IN clause
            placeholders = ",".join("?" for _ in ids)
            cursor.execute(f"DELETE FROM buffered_telemetry WHERE id IN ({placeholders})", tuple(ids))
            conn.commit()
        print(f"[SQLite] Cleared {len(ids)} uploaded entries from buffer.")
    except Exception as e:
        print(f"[!] SQLite failed to delete entries: {e}")

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
            json.dump(entries, f, cls=DateTimeEncoder, indent=2)
            
        print(f"[Archive] Saved {len(entries)} snapshots to backup: {archive_file.name}")
    except Exception as e:
        print(f"[!] Failed to archive snapshots: {e}")

def flush_to_mongodb(col_telemetry):
    """
    Tries to upload all buffered entries to MongoDB.
    On success, archives them locally and deletes them from SQLite.
    """
    if col_telemetry is None:
        return
        
    entries = get_buffered_entries()
    if not entries:
        return

    print(f"[Database] Flushing {len(entries)} buffered entries to MongoDB...")
    
    uploaded_ids = [entry_id for entry_id, _ in entries]
    payloads = [payload for _, payload in entries]
    
    try:
        # Use insert_many for high network efficiency
        col_telemetry.insert_many(payloads)
        
        # Remove any MongoDB internal ID (_id) generated by insertion before archiving
        archived_payloads = []
        for payload in payloads:
            payload_copy = dict(payload)
            if "_id" in payload_copy:
                del payload_copy["_id"]
            archived_payloads.append(payload_copy)
            
        # Archive first for safety
        archive_entries(archived_payloads)
        # Clear from SQLite
        remove_entries(uploaded_ids)
        print(f"[Database] Successfully flushed {len(uploaded_ids)} entries.")
    except Exception as e:
        print(f"[!] Failed to batch upload buffered entries: {e}")
