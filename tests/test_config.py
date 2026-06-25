import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import momir_config


class ConfigTests(unittest.TestCase):
    def test_json_printer_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            config.write_text(
                json.dumps(
                    {
                        "printer": {
                            "bluetooth_address": "aa:bb:cc:dd:ee:ff",
                            "channel": "7",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"MOMIR_CONFIG_PATH": str(config)},
                clear=True,
            ):
                self.assertEqual(
                    momir_config.get_printer_address(),
                    "AA:BB:CC:DD:EE:FF",
                )
                self.assertEqual(momir_config.get_printer_channel(), "7")

    def test_environment_overrides_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            config.write_text(
                json.dumps(
                    {
                        "printer": {
                            "bluetooth_address": "11:22:33:44:55:66",
                            "channel": "4",
                        },
                        "web": {
                            "host": "127.0.0.1",
                            "port": 5001,
                            "local_base_url": "http://example.local:5001",
                        },
                    }
                ),
                encoding="utf-8",
            )
            environment = {
                "MOMIR_CONFIG_PATH": str(config),
                "MOMIR_PRINTER_ADDRESS": "AA:BB:CC:DD:EE:FF",
                "MOMIR_PRINTER_CHANNEL": "9",
                "MOMIR_HOST": "0.0.0.0",
                "MOMIR_PORT": "5050",
                "MOMIR_LOCAL_BASE_URL": "http://momir.test:5050/",
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(
                    momir_config.get_printer_address(),
                    "AA:BB:CC:DD:EE:FF",
                )
                self.assertEqual(momir_config.get_printer_channel(), "9")
                self.assertEqual(momir_config.get_web_host(), "0.0.0.0")
                self.assertEqual(momir_config.get_web_port(), 5050)
                self.assertEqual(
                    momir_config.get_local_base_url(),
                    "http://momir.test:5050",
                )

    def test_invalid_printer_address_is_rejected(self):
        with patch.dict(
            os.environ,
            {"MOMIR_PRINTER_ADDRESS": "not-an-address"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                momir_config.get_printer_address()


if __name__ == "__main__":
    unittest.main()
