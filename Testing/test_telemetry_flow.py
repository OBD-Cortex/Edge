import os
import sys
import json
import sqlite3
import datetime
import unittest
from unittest.mock import patch, MagicMock

# Adjust sys.path to find src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from main import build_telemetry_document
from core.telemetry_buffer import init_buffer, save_to_buffer, get_buffered_entries, remove_entries, flush_to_cloud

class TestTelemetryFlow(unittest.TestCase):
    def setUp(self):
        # Override the SQLite DB path for testing to avoid overwriting production DB
        import core.telemetry_buffer
        self.original_db_path = core.telemetry_buffer.SQLITE_DB_PATH
        core.telemetry_buffer.SQLITE_DB_PATH = core.telemetry_buffer.BASE_DIR / "test_telemetry_buffer.db"
        self.test_db_path = core.telemetry_buffer.SQLITE_DB_PATH
        
        # Clean up any existing test DB
        if self.test_db_path.exists():
            os.remove(self.test_db_path)
            
        init_buffer()

    def tearDown(self):
        # Restore original DB path and clean up test DB
        import core.telemetry_buffer
        core.telemetry_buffer.SQLITE_DB_PATH = self.original_db_path
        if self.test_db_path.exists():
            os.remove(self.test_db_path)

    def test_build_and_serialization(self):
        # 1. Build telemetry document
        mock_raw_scan = {
            "mil_active": True,
            "confirmed_dtcs": ["P0300", "P0171"],
            "pending_dtcs": ["P0115"]
        }
        
        telemetry = build_telemetry_document("12345678901234567", mock_raw_scan)
        
        # Validate that the timestamp is a string (ISO-8601)
        self.assertIsInstance(telemetry["timestamp"], str)
        self.assertTrue(telemetry["mil_active"])
        self.assertEqual(telemetry["dtc_count"], 3)
        self.assertEqual(telemetry["system_status"], "critical")
        
        # 2. Save to SQLite buffer
        success = save_to_buffer(telemetry)
        self.assertTrue(success)
        
        # 3. Retrieve from buffer
        entries = get_buffered_entries()
        self.assertEqual(len(entries), 1)
        entry_id, retrieved_payload = entries[0]
        
        # Verify it has standard serializable string values
        self.assertEqual(retrieved_payload["vehicle_id"], "12345678901234567")
        self.assertEqual(retrieved_payload["timestamp"], telemetry["timestamp"])
        self.assertEqual(retrieved_payload["system_status"], "critical")
        
        # 4. Verify standard json.dumps is fully compatible and doesn't throw TypeError
        try:
            serialized = json.dumps([retrieved_payload])
            deserialized = json.loads(serialized)
            self.assertEqual(deserialized[0]["timestamp"], telemetry["timestamp"])
        except TypeError as e:
            self.fail(f"Serialization failed with: {e}")

    @patch('requests.post')
    @patch('core.telemetry_buffer.sign_payload')
    def test_flush_to_cloud(self, mock_sign, mock_post):
        # Configure mocked response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Configure mock sign_payload
        mock_sign.return_value = ("mock_signature_hex", "mock_timestamp_str")

        # Mock config in core.telemetry_buffer
        import core.telemetry_buffer
        core.telemetry_buffer.config.EDGE_SERVICE_URL = "http://mockapi.local"
        core.telemetry_buffer.config.DEVICE_ID = 99

        # 1. Build and store multiple mock documents
        mock_raw_scan_1 = {"mil_active": False, "confirmed_dtcs": [], "pending_dtcs": []}
        mock_raw_scan_2 = {"mil_active": True, "confirmed_dtcs": ["P0301"], "pending_dtcs": []}
        
        telem_1 = build_telemetry_document("12345678901234567", mock_raw_scan_1)
        telem_2 = build_telemetry_document("12345678901234567", mock_raw_scan_2)
        
        save_to_buffer(telem_1)
        save_to_buffer(telem_2)
        
        # Verify 2 entries exist in DB
        self.assertEqual(len(get_buffered_entries()), 2)
        
        # 2. Flush to cloud
        flush_to_cloud()
        
        # Verify requests.post was called with the correct args
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://mockapi.local/api/telemetry")
        self.assertEqual(kwargs["headers"], {
            "X-Device-ID": "99",
            "X-Signature": "mock_signature_hex",
            "X-Timestamp": "mock_timestamp_str",
            "Content-Type": "application/json"
        })
        
        # Verify the payloads JSON sent matches our buffered entries (both are lists)
        payloads_sent = json.loads(kwargs["data"])
        self.assertEqual(len(payloads_sent), 2)
        self.assertEqual(payloads_sent[0]["system_status"], "healthy")
        self.assertEqual(payloads_sent[1]["system_status"], "critical")
        
        # Verify entries were successfully removed from database after upload
        self.assertEqual(len(get_buffered_entries()), 0)

if __name__ == "__main__":
    unittest.main()
