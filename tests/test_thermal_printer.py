import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import thermal_printer


SAMPLE_CARD = {
    "id": "sample-card-id",
    "name": "Verdant Test Creature",
    "mana_cost": "{4}{G}{G}",
    "mana_value": 6,
    "type_line": "Creature — Beast",
    "oracle_text": "Trample\nWhen this creature enters, draw a card.",
    "power": "6",
    "toughness": "6",
    "set": "TST",
    "collector_number": "123",
    "rarity": "rare",
}


class ThermalPrinterTests(unittest.TestCase):
    def test_receipt_contains_only_selected_card_fields(self):
        lines = thermal_printer.format_thermal_lines(SAMPLE_CARD, columns=32)
        output = "\n".join(lines)

        self.assertIn("Verdant Test Creature", output)
        self.assertIn("4GG", output)
        self.assertIn("Creature - Beast", output)
        self.assertIn("Trample", output)
        self.assertIn("6/6", output)

        self.assertNotIn("{", output)
        self.assertNotIn("}", output)
        self.assertNotIn("Mana Value", output)
        self.assertNotIn("TST", output)
        self.assertNotIn("123", output)
        self.assertNotIn("rare", output)

    def test_long_text_wraps_to_configured_width(self):
        card = dict(SAMPLE_CARD)
        card["oracle_text"] = (
            "Whenever another creature enters the battlefield under your "
            "control, investigate."
        )
        lines = thermal_printer.format_thermal_lines(card, columns=28)
        self.assertTrue(all(len(line) <= 28 for line in lines))

    def test_header_keeps_mana_cost_and_name(self):
        lines = thermal_printer.format_thermal_lines(SAMPLE_CARD, columns=32)
        self.assertIn("Verdant Test Creature", lines[0])
        self.assertTrue(any("4GG" in line for line in lines))

    def test_braces_are_removed_from_cost_and_rules_text(self):
        card = dict(SAMPLE_CARD)
        card["mana_cost"] = "{4}{U}{B}"
        card["oracle_text"] = (
            "{U}, Sacrifice an Island: This creature can't be blocked this turn.\n"
            "{B}, Sacrifice a Swamp: You gain 1 life and draw a card.\n"
            "{U}{B}: Return this card from your graveyard to your hand."
        )
        output = "\n".join(
            thermal_printer.format_thermal_lines(card, columns=32)
        )

        self.assertIn("4UB", output)
        self.assertIn("U, Sacrifice an Island", output)
        self.assertIn("B, Sacrifice a Swamp", output)
        self.assertIn("UB: Return this card", output)
        self.assertNotIn("{", output)
        self.assertNotIn("}", output)

    def test_rules_paragraphs_have_no_added_blank_lines(self):
        card = dict(SAMPLE_CARD)
        card["oracle_text"] = (
            "First ability.\n"
            "Second ability.\n"
            "Third ability."
        )
        columns = 32
        lines = thermal_printer.format_thermal_lines(card, columns=columns)
        divider = "-" * columns
        first_divider = lines.index(divider)
        second_divider = lines.index(divider, first_divider + 1)
        rules_lines = lines[first_divider + 1:second_divider]

        self.assertNotIn("", rules_lines)
        self.assertEqual(
            rules_lines,
            ["First ability.", "Second ability.", "Third ability."],
        )

    def test_preview_is_monochrome_and_expected_width(self):
        settings = {
            "columns": 32,
            "paper_width_pixels": 384,
            "qr_size_pixels": 144,
            "transport": "mock",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "preview.png"
            path = thermal_printer.render_thermal_preview(
                SAMPLE_CARD,
                output,
                settings=settings,
                force=True,
            )
            with Image.open(path) as image:
                self.assertEqual(image.mode, "1")
                self.assertEqual(image.width, 384)
                self.assertGreater(image.height, 144)

    def test_preview_qr_shares_row_with_power_toughness(self):
        settings = {
            "columns": 32,
            "paper_width_pixels": 384,
            "qr_size_pixels": 144,
            "transport": "mock",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "side-by-side.png"
            path = thermal_printer.render_thermal_preview(
                SAMPLE_CARD,
                output,
                settings=settings,
                force=True,
            )
            with Image.open(path) as image:
                old_stacked_height = (
                    16
                    + len(
                        thermal_printer.format_thermal_lines(
                            SAMPLE_CARD,
                            columns=32,
                        )
                    )
                    * 29
                    + 18
                    + 144
                    + 18
                )
                self.assertLess(image.height, old_stacked_height)

    def test_mock_job_writes_text_and_preview_without_hardware(self):
        settings = {
            "columns": 32,
            "paper_width_pixels": 384,
            "qr_size_pixels": 144,
            "transport": "mock",
        }
        with tempfile.TemporaryDirectory() as tmp:
            mock_dir = Path(tmp)
            with patch.object(thermal_printer, "THERMAL_MOCK_DIR", mock_dir):
                result = thermal_printer.write_mock_thermal_job(
                    SAMPLE_CARD,
                    settings,
                )
            self.assertTrue(result["ok"])
            self.assertTrue(Path(result["text_path"]).exists())
            self.assertTrue(Path(result["preview_path"]).exists())


if __name__ == "__main__":
    unittest.main()
