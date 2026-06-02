from __future__ import annotations

import os
import platform
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "OrvilleFusionAddIn"))

from lib.secure_store import ENV_API_KEY, SecureStore, SecureStoreUnavailable, normalize_api_key


class SecureStoreTests(unittest.TestCase):
    def test_secure_store_prefers_environment_key(self):
        original = os.environ.get(ENV_API_KEY)
        os.environ[ENV_API_KEY] = "  gcad_env_test  "
        try:
            self.assertEqual(SecureStore().get_api_key(), "gcad_env_test")
        finally:
            if original is None:
                os.environ.pop(ENV_API_KEY, None)
            else:
                os.environ[ENV_API_KEY] = original

    def test_normalize_api_key_rejects_control_characters(self):
        with self.assertRaises(ValueError):
            normalize_api_key("gcad\nbad")

    def test_secure_store_reports_unsupported_platform_without_env(self):
        original_env = os.environ.pop(ENV_API_KEY, None)
        original_system = platform.system
        platform.system = lambda: "Linux"
        try:
            with self.assertRaises(SecureStoreUnavailable):
                SecureStore().get_api_key()
        finally:
            platform.system = original_system
            if original_env is not None:
                os.environ[ENV_API_KEY] = original_env


if __name__ == "__main__":
    unittest.main()
