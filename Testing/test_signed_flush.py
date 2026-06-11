import os
import sys
import json
import sqlite3
import datetime
import shutil
import unittest
import hmac
import hashlib
from unittest.mock import patch, MagicMock
from pathlib import Path

# Adjust sys.path to find src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import core.config
import core.crypto
import core.telemetry_buffer
from main import build_telemetry_document

class TestSignedFlush(unittest.TestCase):
    def setUp(self):
        # Establish test directories
        self.test_dir = Path(__file__).parent / "test_env_flush"
        self.test_keys_dir = self.test_dir / ".keys"
        self.test_db_path = self.test_dir / "test_telemetry_buffer.db"
        
        # Save original states
        self.original_base_dir = core.config.BASE_DIR
        self.original_crypto_keys_dir = core.crypto.KEYS_DIR
        self.original_secret_path = core.crypto.SECRET_PATH
        self.original_db_path = core.telemetry_buffer.SQLITE_DB_PATH
        self.original_api_url = core.config.EDGE_SERVICE_URL
        
        # Inject test configs
        core.config.BASE_DIR = self.test_dir
        core.crypto.KEYS_DIR = self.test_keys_dir
        core.crypto.SECRET_PATH = self.test_keys_dir / "device_secret"
        core.telemetry_buffer.SQLITE_DB_PATH = self.test_db_path
        core.config.EDGE_SERVICE_URL = "http://mockapi.local"
        
        # Clean up test directories
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize buffer DB and generate test keys
        core.telemetry_buffer.init_buffer()
        self.secret = core.crypto.generate_secret()
        
        # Write mock device ID (42) to keys directory
        with open(self.test_keys_dir / "device_id", "w") as f:
            f.write("42")

    def tearDown(self):
        # Restore original states
        core.config.BASE_DIR = self.original_base_dir
        core.crypto.KEYS_DIR = self.original_crypto_keys_dir
        core.crypto.SECRET_PATH = self.original_secret_path
        core.telemetry_buffer.SQLITE_DB_PATH = self.original_db_path
        core.config.EDGE_SERVICE_URL = self.original_api_url
        
        # Clean up test directories
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch('httpx.post')
    def test_signed_flush_to_cloud(self, mock_post):
        # Configure mocked response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # 1. Build and store mock telemetry document
        mock_raw_scan = {"mil_active": False, "confirmed_dtcs": [], "pending_dtcs": []}
        telem = build_telemetry_document("12345678901234567", mock_raw_scan)
        core.telemetry_buffer.save_to_buffer(telem)
        
        # Verify it exists in DB
        self.assertEqual(len(core.telemetry_buffer.get_buffered_entries()), 1)
        
        # 2. Trigger flush
        core.telemetry_buffer.flush_to_cloud()
        
        # Verify requests.post was called
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Verify URL
        self.assertEqual(args[0], "http://mockapi.local/api/telemetry")
        
        # Verify expected headers exist
        headers = kwargs["headers"]
        self.assertEqual(headers["X-Device-ID"], "42")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertTrue("X-Signature" in headers)
        self.assertTrue("X-Timestamp" in headers)
        
        # Verify signature is cryptographically valid against the payloads
        signature_hex = headers["X-Signature"]
        timestamp_str = headers["X-Timestamp"]
        payload_bytes = kwargs["content"]
        
        signed_data = timestamp_str.encode('utf-8') + payload_bytes
        
        expected_sig = hmac.new(self.secret.encode('utf-8'), signed_data, hashlib.sha256).hexdigest()
        self.assertEqual(signature_hex, expected_sig)
            
        # Verify entries were successfully removed from database after upload
        self.assertEqual(len(core.telemetry_buffer.get_buffered_entries()), 0)

if __name__ == "__main__":
    unittest.main()
