import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import momir_config


class PrinterTypeConfigTests(unittest.TestCase):
    def test_photo_remains_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            with patch.dict(
                os.environ,
                {"MOMIR_CONFIG_PATH": str(config)},
                clear=True,
            ):
                self.assertEqual(momir_config.get_printer_type(), "photo")

    def test_thermal_settings_load_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            config.write_text(
                json.dumps(
                    {
                        "printer": {
                            "type": "thermal_58mm",
                            "thermal": {
                                "columns": 42,
                                "paper_width_pixels": 384,
                                "qr_size_pixels": 128,
                                "transport": "mock",
                            },
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
                    momir_config.get_printer_type(),
                    "thermal_58mm",
                )
                settings = momir_config.get_thermal_printer_settings()
                self.assertEqual(settings["columns"], 42)
                self.assertEqual(settings["qr_size_pixels"], 128)

    def test_save_preserves_existing_photo_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            config.write_text(
                json.dumps(
                    {
                        "printer": {
                            "bluetooth_address": "AA:BB:CC:DD:EE:FF",
                            "channel": "4",
                            "margins": {
                                "left": 25,
                                "top": 45,
                                "right": 25,
                                "bottom": 40,
                            },
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
                saved = momir_config.save_printer_settings(
                    {
                        "type": "thermal_58mm",
                        "thermal": {
                            "columns": 32,
                            "paper_width_pixels": 384,
                            "qr_size_pixels": 144,
                            "transport": "mock",
                        },
                    }
                )

            loaded = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(saved["type"], "thermal_58mm")
            self.assertEqual(
                loaded["printer"]["bluetooth_address"],
                "AA:BB:CC:DD:EE:FF",
            )
            self.assertIn("margins", loaded["printer"])
            self.assertEqual(
                loaded["printer"]["thermal"]["columns"],
                32,
            )

    def test_invalid_printer_type_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            with patch.dict(
                os.environ,
                {"MOMIR_CONFIG_PATH": str(config)},
                clear=True,
            ):
                with self.assertRaises(RuntimeError):
                    momir_config.save_printer_settings({"type": "laser"})


if __name__ == "__main__":
    unittest.main()
