import os
import sys
import shutil
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Adjust sys.path to find src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import core.config
import core.crypto
import services.provisioning

class TestProvisioning(unittest.TestCase):
    def setUp(self):
        # Establish test directories
        self.test_dir = Path(__file__).parent / "test_env_prov"
        self.test_keys_dir = self.test_dir / ".keys"
        
        # Save original states
        self.original_base_dir = core.config.BASE_DIR
        self.original_crypto_keys_dir = core.crypto.KEYS_DIR
        self.original_crypto_key_path = core.crypto.SECRET_PATH
        self.original_prov_keys_dir = services.provisioning.KEYS_DIR
        self.original_prov_device_id_path = services.provisioning.DEVICE_ID_PATH
        self.original_api_url = services.provisioning.RAG_API_URL
        self.original_token = services.provisioning.DEVICE_TOKEN
        
        # Inject test directories
        core.config.BASE_DIR = self.test_dir
        core.crypto.KEYS_DIR = self.test_keys_dir
        core.crypto.SECRET_PATH = self.test_keys_dir / "device_secret"
        services.provisioning.KEYS_DIR = self.test_keys_dir
        services.provisioning.DEVICE_ID_PATH = self.test_keys_dir / "device_id"
        services.provisioning.RAG_API_URL = "http://mock-rag-api.local"
        services.provisioning.DEVICE_TOKEN = "TEST_TOKEN"
        
        # Clean up any leftover test directories
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def tearDown(self):
        # Restore original states
        core.config.BASE_DIR = self.original_base_dir
        core.crypto.KEYS_DIR = self.original_crypto_keys_dir
        core.crypto.SECRET_PATH = self.original_crypto_key_path
        services.provisioning.KEYS_DIR = self.original_prov_keys_dir
        services.provisioning.DEVICE_ID_PATH = self.original_prov_device_id_path
        services.provisioning.RAG_API_URL = self.original_api_url
        services.provisioning.DEVICE_TOKEN = self.original_token
        
        # Clean up test directories
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch('requests.post')
    def test_provision_success(self, mock_post):
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "device_id": 42}
        mock_post.return_value = mock_response
        
        # Call provisioning
        device_id = services.provisioning.provision_device(
            vin="12345678901234567",
            brand="Toyota",
            model="Prius",
            year="2018"
        )
        
        # Verify returned ID
        self.assertEqual(device_id, 42)
        
        # Verify keys and device_id files exist on disk
        self.assertTrue(core.crypto.SECRET_PATH.exists())
        self.assertTrue(services.provisioning.DEVICE_ID_PATH.exists())
        
        # Verify correct device ID is saved in file
        with open(services.provisioning.DEVICE_ID_PATH, "r") as f:
            saved_id = f.read().strip()
        self.assertEqual(saved_id, "42")
        
        # Verify config.DEVICE_ID loads it dynamically
        self.assertEqual(core.config.DEVICE_ID, 42)
        
        # Verify request contents
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://mock-rag-api.local/api/device/provision")
        self.assertEqual(kwargs["headers"]["X-Device-Token"], "TEST_TOKEN")
        self.assertEqual(kwargs["json"]["vin"], "12345678901234567")
        self.assertTrue("device_secret" in kwargs["json"])

    @patch('requests.post')
    def test_provision_http_error(self, mock_post):
        # Mock failed HTTP code
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_post.return_value = mock_response
        
        with self.assertRaises(RuntimeError) as context:
            services.provisioning.provision_device(
                vin="12345678901234567",
                brand="Toyota",
                model="Prius",
                year="2018"
            )
            
        self.assertIn("Server rejected provisioning request", str(context.exception))
        # Ensure device_id wasn't created
        self.assertFalse(services.provisioning.DEVICE_ID_PATH.exists())

    @patch('requests.post')
    def test_provision_missing_device_id_in_response(self, mock_post):
        # Mock 200 response but missing device_id
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_post.return_value = mock_response
        
        with self.assertRaises(RuntimeError) as context:
            services.provisioning.provision_device(
                vin="12345678901234567",
                brand="Toyota",
                model="Prius",
                year="2018"
            )
            
        self.assertIn("response did not contain 'device_id'", str(context.exception))
        self.assertFalse(services.provisioning.DEVICE_ID_PATH.exists())

if __name__ == "__main__":
    unittest.main()
