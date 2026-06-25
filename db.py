import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "momir.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    oracle_id TEXT,
    name TEXT NOT NULL,
    mana_value INTEGER NOT NULL,
    mana_cost TEXT,
    type_line TEXT,
    oracle_text TEXT,
    power TEXT,
    toughness TEXT,
    loyalty TEXT,
    scryfall_uri TEXT,
    storage_letter TEXT,
    printed_count INTEGER NOT NULL DEFAULT 0,
    first_printed_at TEXT,
    last_printed_at TEXT,
    layout TEXT,
    back_face_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_cards_mv ON cards(mana_value);
CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS summon_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    summoned_at TEXT NOT NULL,
    mana_value INTEGER NOT NULL,
    printed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(card_id) REFERENCES cards(id)
);
"""

NEW_COLUMNS = {
    "mana_cost": "TEXT",
    "loyalty": "TEXT",
    "scryfall_uri": "TEXT",
    "layout": "TEXT",
    "back_face_json": "TEXT",
}

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    migrate(conn)
    return conn

def migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cards)")}
    for name, coltype in NEW_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE cards ADD COLUMN {name} {coltype}")
    conn.commit()

def get_setting(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()

def card_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM cards").fetchone()["c"]


def printed_card_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM cards WHERE printed_count > 0").fetchone()["c"]

def back_face_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM cards WHERE back_face_json IS NOT NULL AND back_face_json != ''"
    ).fetchone()["c"]

def total_print_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COALESCE(SUM(printed_count),0) AS c FROM cards").fetchone()["c"]

def mana_values(conn: sqlite3.Connection) -> List[int]:
    return [r[0] for r in conn.execute("SELECT DISTINCT mana_value FROM cards ORDER BY mana_value")]

def random_card(conn: sqlite3.Connection, mana_value: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM cards WHERE mana_value=? ORDER BY RANDOM() LIMIT 1", (mana_value,)).fetchone()
    return dict(row) if row else None

def get_card(conn: sqlite3.Connection, card_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    return dict(row) if row else None

def mark_summoned(conn: sqlite3.Connection, card_id: str, mana_value: int) -> int:
    cur = conn.execute(
        "INSERT INTO summon_history(card_id, summoned_at, mana_value, printed) VALUES(?, datetime('now','localtime'), ?, 0)",
        (card_id, mana_value),
    )
    conn.commit()
    return int(cur.lastrowid)

def mark_printed(conn: sqlite3.Connection, card_id: str, history_id: Optional[int] = None) -> None:
    conn.execute(
        """
        UPDATE cards
        SET printed_count = 1,
            first_printed_at = COALESCE(first_printed_at, datetime('now','localtime')),
            last_printed_at = datetime('now','localtime')
        WHERE id=?
        """,
        (card_id,),
    )
    if history_id is not None:
        conn.execute("UPDATE summon_history SET printed=1 WHERE id=?", (history_id,))
    conn.commit()

def unmark_printed(conn: sqlite3.Connection, card_id: str) -> None:
    conn.execute(
        "UPDATE cards SET printed_count=0, first_printed_at=NULL, last_printed_at=NULL WHERE id=?",
        (card_id,),
    )
    conn.commit()

def owned_cards(conn: sqlite3.Connection, letter: Optional[str] = None):
    if letter:
        return [dict(r) for r in conn.execute(
            """
            SELECT * FROM cards
            WHERE printed_count > 0 AND storage_letter = ?
            ORDER BY name
            """,
            (letter.upper(),),
        )]
    return [dict(r) for r in conn.execute(
        """
        SELECT * FROM cards
        WHERE printed_count > 0
        ORDER BY storage_letter, name
        """
    )]

def missing_cards(conn: sqlite3.Connection, mana_value: Optional[int] = None, limit: int = 200):
    if mana_value is None:
        return [dict(r) for r in conn.execute(
            """
            SELECT * FROM cards
            WHERE printed_count = 0
            ORDER BY mana_value, name
            LIMIT ?
            """,
            (limit,),
        )]
    return [dict(r) for r in conn.execute(
        """
        SELECT * FROM cards
        WHERE printed_count = 0 AND mana_value = ?
        ORDER BY name
        LIMIT ?
        """,
        (mana_value, limit),
    )]

def progress_by_mana_value(conn: sqlite3.Connection):
    return [dict(r) for r in conn.execute(
        """
        SELECT mana_value,
               COUNT(*) AS total,
               SUM(CASE WHEN printed_count > 0 THEN 1 ELSE 0 END) AS owned
        FROM cards
        GROUP BY mana_value
        ORDER BY mana_value
        """
    )]

def reset_printed(conn: sqlite3.Connection, reset_history: bool = False) -> None:
    conn.execute("UPDATE cards SET printed_count=0, first_printed_at=NULL, last_printed_at=NULL")
    if reset_history:
        conn.execute("UPDATE summon_history SET printed=0")
    conn.commit()


def search_cards(conn: sqlite3.Connection, term: str, limit: int = 50):
    like = f"%{term}%"
    return [dict(r) for r in conn.execute("SELECT * FROM cards WHERE name LIKE ? ORDER BY name LIMIT ?", (like, limit))]
