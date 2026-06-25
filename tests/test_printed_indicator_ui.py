import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PrintedIndicatorUiTests(unittest.TestCase):
    def test_template_contains_small_green_printer_icon(self):
        text = (ROOT / "webapp/templates/index.html").read_text(encoding="utf-8")
        self.assertEqual(text.count('id="cardPrintedIcon"'), 1)
        self.assertIn('class="printed-icon hidden"', text)
        self.assertIn('aria-label="This card has already been printed"', text)
        self.assertIn("width:28px", text)
        self.assertIn("height:28px", text)
        self.assertIn("color:#b8b8b8", text)
        self.assertIn("stroke:currentColor", text)
        self.assertIn('d="M7 8V3h10v5"', text)
        self.assertIn('d="M7 14h10v7H7z"', text)
        self.assertNotIn('d="m5 12 4 4L19 6"', text)

    def test_javascript_controls_printed_icon_visibility(self):
        text = (ROOT / "webapp/static/app.js").read_text(encoding="utf-8")
        self.assertIn("function renderPrintedStatus(card)", text)
        self.assertIn('indicator.style.display = printed ? "inline-flex" : "none"', text)
        self.assertIn("card?.printed", text)
        self.assertIn("card?.printed_count", text)

if __name__ == "__main__":
    unittest.main()
