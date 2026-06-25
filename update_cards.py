#!/usr/bin/env python3
"""Refresh the local Momir card pool from Scryfall.

Only cards whose first/front face is a Creature are included. This excludes
Battles and other cards that become creatures only after transforming.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

import requests

from db import connect

API = "https://api.scryfall.com/cards/search"
HEADERS = {
    "User-Agent": "MomirPrinter/0.4 (local Raspberry Pi card database updater)",
    "Accept": "application/json",
}
QUERY = "type:creature lang:en game:paper -is:funny"
DOUBLE_FACE_LAYOUTS = {"transform", "modal_dfc", "reversible_card"}

EXCLUDED_LAYOUTS = {
    "token",
    "double_faced_token",
    "art_series",
    "scheme",
    "planar",
    "vanguard",
    "emblem",
}
CREATURE_WORD = re.compile(r"\bCreature\b")
ProgressCallback = Callable[[dict[str, int]], None]


def front_face(card: dict[str, Any]) -> dict[str, Any]:
    """Return Scryfall's first card face, or the card itself if single-faced."""
    faces = card.get("card_faces") or []
    if faces and isinstance(faces[0], dict):
        return faces[0]
    return card


def front_value(card: dict[str, Any], key: str, default: Any = None) -> Any:
    face = front_face(card)
    value = face.get(key)
    if value is not None and value != "":
        return value
    return card.get(key, default)


def get_front_name(card: dict[str, Any]) -> str:
    name = str(front_value(card, "name", "") or "").strip()
    return name.split(" // ", 1)[0].strip()


def get_front_type_line(card: dict[str, Any]) -> str:
    return str(front_value(card, "type_line", "") or "").strip()




def face_payload(face: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    """Keep all rules-relevant fields needed for offline play and printing."""
    return {
        "name": str(face.get("name") or "").strip(),
        "mana_cost": face.get("mana_cost") or "",
        "type_line": face.get("type_line") or "",
        "oracle_text": face.get("oracle_text") or "",
        "power": face.get("power"),
        "toughness": face.get("toughness"),
        "loyalty": face.get("loyalty"),
        "defense": face.get("defense"),
        "scryfall_uri": card.get("scryfall_uri") or "",
    }


def get_back_face_data(
    card: dict[str, Any], cards_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Return an actual reverse face, never an Adventure/split/flip component."""
    layout = str(card.get("layout") or "")
    faces = card.get("card_faces") or []

    if layout in DOUBLE_FACE_LAYOUTS and len(faces) > 1 and isinstance(faces[1], dict):
        payload = face_payload(faces[1], card)
        return payload if payload.get("name") else None

    # Meld cards store their combined reverse permanent as a related object
    # instead of card_faces. The creature search normally includes that result,
    # so connect it locally by Scryfall ID without extra network requests.
    if layout == "meld":
        for part in card.get("all_parts") or []:
            if part.get("component") != "meld_result":
                continue
            result = cards_by_id.get(str(part.get("id") or ""))
            if not result:
                continue
            payload = face_payload(front_face(result), result)
            return payload if payload.get("name") else None

    return None


def include_for_momir(
    card: dict[str, Any], seen_oracles: set[str]
) -> tuple[bool, str]:
    """Return whether a Scryfall card belongs in the local Momir pool."""
    if card.get("lang") != "en":
        return False, "not_english"
    if card.get("layout") in EXCLUDED_LAYOUTS:
        return False, "excluded_layout"
    if card.get("border_color") in {"silver", "acorn"}:
        return False, "funny_border"
    if "paper" not in (card.get("games") or []):
        return False, "not_paper"

    # Scryfall's type:creature query can match either face. The first/front face
    # is authoritative for this project.
    type_line = get_front_type_line(card)
    if not CREATURE_WORD.search(type_line):
        return False, "front_not_creature"
    if type_line.startswith("Token") or " Token" in type_line:
        return False, "token"
    if "Battle" in type_line:
        return False, "battle_front"

    mana_value = card.get("cmc")
    if mana_value is None:
        return False, "missing_mana_value"
    try:
        if int(mana_value) != mana_value:
            return False, "fractional_mana_value"
    except (TypeError, ValueError, OverflowError):
        return False, "invalid_mana_value"

    oracle_id = str(card.get("oracle_id") or card.get("id") or "")
    if not oracle_id:
        return False, "missing_id"
    if oracle_id in seen_oracles:
        return False, "duplicate_oracle"
    seen_oracles.add(oracle_id)
    return True, "included"


def request_json(
    session: requests.Session, url: str, attempts: int = 4
) -> dict[str, Any]:
    """Fetch JSON with bounded retries for transient network failures."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=60)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                time.sleep(max(1.0, retry_after))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"Unable to download Scryfall data: {last_error}")


def iter_scryfall_cards(
    progress_callback: ProgressCallback | None = None,
) -> Iterable[dict[str, Any]]:
    params = urlencode({"q": QUERY, "unique": "cards", "order": "name"})
    url: str | None = f"{API}?{params}"
    page = 1
    downloaded = 0
    session = requests.Session()
    downloaded_cards: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    while url:
        print(f"Fetching Scryfall page {page}...", flush=True)
        payload = request_json(session, url)
        page_cards = payload.get("data", [])
        downloaded += len(page_cards)

        total_cards = int(payload.get("total_cards") or downloaded)
        # Scryfall card-search list pages contain up to 175 cards.
        total_pages = max(1, math.ceil(total_cards / 175))
        if progress_callback:
            progress_callback(
                {
                    "page": page,
                    "total_pages": total_pages,
                    "downloaded": min(downloaded, total_cards),
                    "total_cards": total_cards,
                    "progress_percent": min(
                        100, round(downloaded * 100 / max(total_cards, 1))
                    ),
                }
            )

        for card in page_cards:
            downloaded_cards.append(card)
            card_id = str(card.get("id") or "")
            if card_id:
                seen_ids.add(card_id)
            yield card
        url = payload.get("next_page") if payload.get("has_more") else None
        page += 1
        if url:
            time.sleep(0.10)

    # Meld results are related card objects rather than card_faces. Fetch the
    # handful that were not included in the creature search so their complete
    # rules text is also available offline.
    for card in downloaded_cards:
        if card.get("layout") != "meld":
            continue
        for part in card.get("all_parts") or []:
            if part.get("component") != "meld_result":
                continue
            result_id = str(part.get("id") or "")
            result_uri = part.get("uri")
            if not result_id or result_id in seen_ids or not result_uri:
                continue
            result = request_json(session, result_uri)
            seen_ids.add(result_id)
            yield result
            time.sleep(0.10)


def iter_json_cards(path: Path) -> Iterable[dict[str, Any]]:
    """Read a Scryfall JSON array for testing or offline recovery."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in {path}")
    yield from payload


def load_existing_state(
    conn,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    columns = (
        "id, oracle_id, printed_count, first_printed_at, last_printed_at"
    )
    rows = [dict(row) for row in conn.execute(f"SELECT {columns} FROM cards")]
    by_id = {str(row["id"]): row for row in rows}
    by_oracle = {
        str(row["oracle_id"]): row for row in rows if row.get("oracle_id")
    }
    return by_id, by_oracle


def build_row(
    card: dict[str, Any],
    previous: dict[str, Any],
    cards_by_id: dict[str, dict[str, Any]],
) -> tuple[Any, ...] | None:
    name = get_front_name(card)
    if not name:
        return None

    card_id = str(card["id"])
    oracle_id = str(card.get("oracle_id") or card_id)
    storage_letter = name[:1].upper() if name else "#"

    back_face = get_back_face_data(card, cards_by_id)
    back_face_json = (
        json.dumps(back_face, ensure_ascii=False, separators=(",", ":"))
        if back_face
        else None
    )

    return (
        card_id,
        oracle_id,
        name,
        int(card["cmc"]),
        front_value(card, "mana_cost"),
        get_front_type_line(card),
        front_value(card, "oracle_text"),
        front_value(card, "power"),
        front_value(card, "toughness"),
        front_value(card, "loyalty"),
        card.get("scryfall_uri"),
        storage_letter,
        int(previous.get("printed_count") or 0),
        previous.get("first_printed_at"),
        previous.get("last_printed_at"),
        card.get("layout"),
        back_face_json,
    )


def update_database(
    cards: Iterable[dict[str, Any]], dry_run: bool = False
) -> dict[str, int]:
    all_cards = list(cards)
    cards_by_id = {str(card.get("id") or ""): card for card in all_cards}

    conn = connect()
    existing_by_id, existing_by_oracle = load_existing_state(conn)
    old_oracles = set(existing_by_oracle)

    seen_oracles: set[str] = set()
    eligible_cards: list[dict[str, Any]] = []
    skip_counts: dict[str, int] = {}

    for card in all_cards:
        include, reason = include_for_momir(card, seen_oracles)
        if include:
            eligible_cards.append(card)
        else:
            skip_counts[reason] = skip_counts.get(reason, 0) + 1

    rows: list[tuple[Any, ...]] = []
    id_changes: list[tuple[str, str]] = []
    preserved_printed = 0

    for card in eligible_cards:
        card_id = str(card["id"])
        oracle_id = str(card.get("oracle_id") or card_id)
        previous = existing_by_oracle.get(oracle_id) or existing_by_id.get(card_id) or {}
        row = build_row(card, previous, cards_by_id)
        if row is None:
            skip_counts["missing_name"] = skip_counts.get("missing_name", 0) + 1
            continue

        rows.append(row)
        if previous.get("printed_count"):
            preserved_printed += 1
        old_id = previous.get("id")
        if old_id and old_id != card_id:
            id_changes.append((str(old_id), card_id))

    new_oracles = {str(row[1]) for row in rows}
    summary = {
        "previous": len(existing_by_id),
        "imported": len(rows),
        "added": len(new_oracles - old_oracles),
        "removed": len(old_oracles - new_oracles),
        "preserved_printed": preserved_printed,
        "front_not_creature": skip_counts.get("front_not_creature", 0),
        "with_back": sum(1 for row in rows if row[-1]),
    }

    if dry_run:
        conn.close()
        return summary

    try:
        with conn:
            conn.execute("DELETE FROM cards")
            conn.executemany(
                """
                INSERT INTO cards(
                    id, oracle_id, name, mana_value, mana_cost, type_line,
                    oracle_text, power, toughness, loyalty, scryfall_uri,
                    storage_letter, printed_count, first_printed_at,
                    last_printed_at, layout, back_face_json
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )

            # Keep summon history connected if Scryfall picks a different
            # representative printing for the same Oracle card.
            for old_id, new_id in id_changes:
                conn.execute(
                    "UPDATE summon_history SET card_id=? WHERE card_id=?",
                    (new_id, old_id),
                )

            conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('cards_last_updated_at', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (datetime.now().astimezone().isoformat(timespec="seconds"),),
            )
            conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('cards_filter_version', 'front-creature-local-backs-no-art-v3')
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """
            )
    finally:
        conn.close()

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-json",
        type=Path,
        help="Use a local Scryfall JSON array instead of the live API.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate the update without changing momir.db.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        cards = (
            iter_json_cards(args.source_json)
            if args.source_json
            else iter_scryfall_cards()
        )
        summary = update_database(cards, dry_run=args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    mode = "Dry run complete" if args.dry_run else "Update complete"
    print()
    print(mode + ":")
    print(f"  Previous cards:          {summary['previous']}")
    print(f"  Current front creatures: {summary['imported']}")
    print(f"  Newly added:             {summary['added']}")
    print(f"  Removed from pool:       {summary['removed']}")
    print(f"  Printed status kept:     {summary['preserved_printed']}")
    print(f"  Creatures with backs:    {summary['with_back']}")
    print(
        "  Back-face-only creatures skipped: "
        f"{summary['front_not_creature']}"
    )
    if not args.dry_run:
        print("Printer previews and print files are generated locally as needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
