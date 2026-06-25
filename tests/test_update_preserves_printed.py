import tempfile
import unittest
from pathlib import Path

import db
import update_cards


class UpdatePreservesPrintedTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / "momir.db"

    def tearDown(self):
        db.DB_PATH = self.original_path
        self.tempdir.cleanup()

    def test_printed_state_follows_oracle_id(self):
        conn = db.connect()
        try:
            conn.execute(
                """
                INSERT INTO cards(
                    id, oracle_id, name, mana_value, type_line,
                    storage_letter, printed_count
                )
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    "old-printing",
                    "shared-oracle",
                    "Test Creature",
                    2,
                    "Creature — Test",
                    "T",
                    1,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        replacement = {
            "id": "new-printing",
            "oracle_id": "shared-oracle",
            "name": "Test Creature",
            "lang": "en",
            "layout": "normal",
            "border_color": "black",
            "games": ["paper"],
            "cmc": 2,
            "type_line": "Creature — Test",
            "mana_cost": "{1}{G}",
            "oracle_text": "Updated rules.",
            "power": "2",
            "toughness": "2",
            "scryfall_uri": "https://example.invalid/card",
        }

        summary = update_cards.update_database([replacement])
        self.assertEqual(summary["preserved_printed"], 1)

        conn = db.connect()
        try:
            card = db.get_card(conn, "new-printing")
            self.assertIsNotNone(card)
            self.assertEqual(card["printed_count"], 1)
            self.assertIsNone(db.get_card(conn, "old-printing"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
