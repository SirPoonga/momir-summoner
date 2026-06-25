import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import momir_config


class PrinterMarginSettingsTests(unittest.TestCase):
    def test_save_preserves_other_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            config.write_text(
                json.dumps(
                    {
                        "printer": {
                            "bluetooth_address": "AA:BB:CC:DD:EE:FF",
                            "channel": "4",
                        },
                        "web": {
                            "host": "127.0.0.1",
                            "port": 5051,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"MOMIR_CONFIG_PATH": str(config)},
                clear=True,
            ):
                saved = momir_config.save_printer_margins(
                    {"left": 30, "top": 50, "right": 28, "bottom": 42}
                )

            self.assertEqual(
                saved,
                {"left": 30, "top": 50, "right": 28, "bottom": 42},
            )
            loaded = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(
                loaded["printer"]["bluetooth_address"],
                "AA:BB:CC:DD:EE:FF",
            )
            self.assertEqual(loaded["printer"]["channel"], "4")
            self.assertEqual(loaded["printer"]["margins"], saved)
            self.assertEqual(loaded["web"]["port"], 5051)

    def test_save_rejects_unusable_horizontal_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            with patch.dict(
                os.environ,
                {"MOMIR_CONFIG_PATH": str(config)},
                clear=True,
            ):
                with self.assertRaises(RuntimeError):
                    momir_config.save_printer_margins(
                        {"left": 150, "top": 45, "right": 150, "bottom": 40}
                    )

    def test_save_rejects_missing_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.local.json"
            with patch.dict(
                os.environ,
                {"MOMIR_CONFIG_PATH": str(config)},
                clear=True,
            ):
                with self.assertRaises(RuntimeError):
                    momir_config.save_printer_margins(
                        {"left": 25, "top": 45, "right": 25}
                    )


if __name__ == "__main__":
    unittest.main()
