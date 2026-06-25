import tempfile
import unittest
from pathlib import Path

import db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / "momir.db"

    def tearDown(self):
        db.DB_PATH = self.original_path
        self.tempdir.cleanup()

    def insert_card(self, conn, card_id="card-1", oracle_id="oracle-1"):
        conn.execute(
            """
            INSERT INTO cards(
                id, oracle_id, name, mana_value, mana_cost, type_line,
                oracle_text, power, toughness, storage_letter
            )
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                card_id,
                oracle_id,
                "Test Creature",
                3,
                "{2}{G}",
                "Creature — Test",
                "Test rules.",
                "3",
                "3",
                "T",
            ),
        )
        conn.commit()

    def test_mark_and_reset_printed(self):
        conn = db.connect()
        try:
            self.insert_card(conn)
            db.mark_printed(conn, "card-1")
            card = db.get_card(conn, "card-1")
            self.assertEqual(card["printed_count"], 1)
            self.assertEqual(db.printed_card_count(conn), 1)

            db.reset_printed(conn, reset_history=True)
            card = db.get_card(conn, "card-1")
            self.assertEqual(card["printed_count"], 0)
            self.assertEqual(db.printed_card_count(conn), 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
