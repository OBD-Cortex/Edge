import os
import sys
import unittest
import shutil
import hmac
import hashlib
from pathlib import Path

# Adjust sys.path to find src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import core.crypto

class TestCrypto(unittest.TestCase):
    def setUp(self):
        # Override key directory for testing to prevent overwriting production keys
        self.test_keys_dir = Path(__file__).parent / "test_keys"
        self.original_keys_dir = core.crypto.KEYS_DIR
        self.original_secret_path = core.crypto.SECRET_PATH
        
        core.crypto.KEYS_DIR = self.test_keys_dir
        core.crypto.SECRET_PATH = self.test_keys_dir / "device_secret"
        
        # Clean up any leftover test keys
        if self.test_keys_dir.exists():
            shutil.rmtree(self.test_keys_dir)

    def tearDown(self):
        # Restore original paths
        core.crypto.KEYS_DIR = self.original_keys_dir
        core.crypto.SECRET_PATH = self.original_secret_path
        
        # Clean up test files
        if self.test_keys_dir.exists():
            shutil.rmtree(self.test_keys_dir)

    def test_is_provisioned_initially_false(self):
        self.assertFalse(core.crypto.is_provisioned())

    def test_generate_secret(self):
        # Generate secret
        secret = core.crypto.generate_secret()
        
        # Verify secret length and hex encoding
        self.assertEqual(len(secret), 64) # 32 bytes = 64 hex chars
        
        # Verify files were created
        self.assertTrue(core.crypto.is_provisioned())
        self.assertTrue(core.crypto.SECRET_PATH.exists())
        
        # Verify file permissions (0600 / owner read-write only)
        if os.name == 'posix':
            stat_info = os.stat(core.crypto.SECRET_PATH)
            permissions = stat_info.st_mode & 0o777
            self.assertEqual(permissions, 0o600)

    def test_load_secret_fails_if_unprovisioned(self):
        with self.assertRaises(RuntimeError):
            core.crypto.load_secret()

    def test_load_secret_success(self):
        original_secret = core.crypto.generate_secret()
        loaded_secret = core.crypto.load_secret()
        self.assertEqual(original_secret, loaded_secret)

    def test_sign_and_verify(self):
        secret = core.crypto.generate_secret()
        payload = b"hello test telemetry payload"
        
        # Sign payload
        sig_hex, timestamp = core.crypto.sign_payload(payload)
        
        self.assertIsInstance(sig_hex, str)
        self.assertIsInstance(timestamp, str)
        
        # Reconstruct signed data and verify
        signed_data = timestamp.encode('utf-8') + payload
        expected_sig = hmac.new(secret.encode('utf-8'), signed_data, hashlib.sha256).hexdigest()
        
        self.assertEqual(sig_hex, expected_sig)

if __name__ == "__main__":
    unittest.main()
