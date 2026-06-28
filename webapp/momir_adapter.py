from pathlib import Path
from datetime import datetime
import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback

from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from momir_config import (
    get_printer_address,
    get_printer_type,
    get_thermal_printer_settings,
)

from db import (
    DB_PATH,
    connect,
    random_card,
    get_card,
    mark_printed,
    card_count,
    back_face_count,
    printed_card_count,
    total_print_count,
)
from render_printer import (
    render_printer,
    render_printer_preview,
    render_printer_back_face,
    render_printer_back_preview,
    print_printer,
)

from thermal_printer import (
    print_thermal,
    probe_thermal_connection,
    render_thermal_preview,
)

LAST_CARD = None
LAST_RENDERED = None
_STATE_LOCK = threading.Lock()
_CARD_OPERATION_LOCK = threading.Lock()

_UPDATE_STATE_LOCK = threading.RLock()
_UPDATE_STATE = {
    "running": False,
    "state": "idle",
    "message": "Ready to update when a new set is available.",
    "page": None,
    "total_pages": None,
    "downloaded": None,
    "total_cards": None,
    "progress_percent": None,
    "started_at": None,
    "finished_at": None,
    "summary": None,
    "error": None,
    "backup": None,
}

_STATUS_CACHE = {}
_STATUS_CACHE_LOCK = threading.Lock()
_PRINTER_PROBE_LOCK = threading.Lock()


def back_face_from_card(card):
    if not card:
        return None
    raw = card.get("back_face_json")
    if not raw:
        return None
    try:
        face = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return face if face.get("name") else None


def card_to_json(card):
    if not card:
        return None
    back = back_face_from_card(card)
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "mana_value": card.get("mana_value"),
        "mana_cost": card.get("mana_cost"),
        "type_line": card.get("type_line"),
        "oracle_text": card.get("oracle_text"),
        "power": card.get("power"),
        "toughness": card.get("toughness"),
        "loyalty": card.get("loyalty"),
        "printed_count": card.get("printed_count") or 0,
        "printed": bool(card.get("printed_count")),
        "storage_letter": card.get("storage_letter") or (card.get("name") or "?")[:1].upper(),
        "layout": card.get("layout"),
        "has_back": bool(back),
        "back": back,
    }


def normalize_search_text(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def card_has_back(card):
    return bool(back_face_from_card(card))


def _select_as_current(card):
    global LAST_CARD, LAST_RENDERED
    selected = dict(card)
    with _STATE_LOCK:
        LAST_CARD = selected
        # Full print rendering is deliberately deferred until Print is tapped.
        LAST_RENDERED = None
    return selected


def _selection_response(card):
    selected = _select_as_current(card)
    result = {
        "card": card_to_json(selected),
        # Stable, card-specific URLs allow browser and server-side caching.
        "preview_url": f"/preview/card/{selected['id']}.jpg?v=17",
    }
    if card_has_back(selected):
        result["back_preview_url"] = (
            f"/preview/card/{selected['id']}/back.jpg?v=17"
        )
    return result


def select_card(card_id):
    conn = connect()
    try:
        card = get_card(conn, card_id)
    finally:
        conn.close()

    if not card:
        return None
    return _selection_response(card)


def summon(mana_value):
    conn = connect()
    try:
        card = random_card(conn, mana_value)
    finally:
        conn.close()

    if not card:
        return None
    return _selection_response(card)


def preview_card(card_id, face="front"):
    """Return a cached local preview without changing the selected card."""
    conn = connect()
    try:
        card = get_card(conn, card_id)
    finally:
        conn.close()

    if not card:
        return None
    card = dict(card)
    if face == "back":
        return render_printer_back_preview(card)
    return render_printer_preview(card)


# MOMIR_THERMAL_PRINTER_PREVIEW_START
def preview_current_thermal():
    """Render the selected card using the 58 mm receipt layout."""

    with _STATE_LOCK:
        card = dict(LAST_CARD) if LAST_CARD else None
    if not card:
        return None
    return render_thermal_preview(
        card,
        settings=get_thermal_printer_settings(),
        force=True,
    )


# MOMIR_THERMAL_PRINTER_PREVIEW_END
def card_details(card_id):
    conn = connect()
    try:
        card = get_card(conn, card_id)
    finally:
        conn.close()
    return card_to_json(dict(card)) if card else None


def print_last():
    global LAST_CARD, LAST_RENDERED

    if card_update_status().get("running"):
        return {
            "ok": False,
            "error": "Card database update is running. Print after it finishes.",
        }

    # Serialize printing with database maintenance so printed tracking cannot be
    # lost while a new card list is committed.
    with _CARD_OPERATION_LOCK:
        if card_update_status().get("running"):
            return {
                "ok": False,
                "error": "Card database update is running. Print after it finishes.",
            }

        with _STATE_LOCK:
            card = dict(LAST_CARD) if LAST_CARD else None
            rendered = LAST_RENDERED

        if not card:
            return {"ok": False, "error": "No card has been summoned yet."}

        printer_type = get_printer_type()

        if printer_type == "thermal_58mm":
            thermal_settings = get_thermal_printer_settings()
            thermal_result = print_thermal(card, thermal_settings)
            if not thermal_result.get("ok"):
                return {
                    "ok": False,
                    "error": thermal_result.get("error")
                    or "Thermal receipt could not be printed.",
                }

            if thermal_result.get("transport") == "mock":
                output = (
                    "Thermal mock job saved to "
                    f"{thermal_result.get('text_path')} and "
                    f"{thermal_result.get('preview_path')}."
                )
            else:
                output = (
                    "Printed thermal receipt through Bluetooth "
                    f"{thermal_result.get('address')} on RFCOMM channel "
                    f"{thermal_result.get('channel')}."
                )

            printed_card = card
        else:
            # Generate the full 450x730 photo image only when it is needed.
            if not rendered or not Path(rendered).exists():
                rendered = render_printer(card)
                with _STATE_LOCK:
                    if LAST_CARD and LAST_CARD.get("id") == card.get("id"):
                        LAST_RENDERED = rendered
            print_printer(rendered)
            output = f"Printed photo output from {rendered}."

            conn = connect()
            try:
                mark_printed(conn, card["id"])
                printed_card = get_card(conn, card["id"]) or card
            finally:
                conn.close()

        # Keep the in-memory selected card synchronized so the UI receives the
        # printed state immediately and future status calls remain accurate.
        with _STATE_LOCK:
            if LAST_CARD and LAST_CARD.get("id") == card.get("id"):
                LAST_CARD = dict(printed_card)

        return {
        "ok": True,
        "card": card_to_json(printed_card),
        "output": output,
        "printer_type": printer_type,
    }


def reprint_last():
    return print_last()


def mark_current_printed():
    global LAST_CARD

    if card_update_status().get("running"):
        return {
            "ok": False,
            "error": "Card database update is running. Try again after it finishes.",
        }

    with _CARD_OPERATION_LOCK:
        with _STATE_LOCK:
            card = dict(LAST_CARD) if LAST_CARD else None

        if not card:
            return {"ok": False, "error": "No current card selected."}

        conn = connect()
        try:
            mark_printed(conn, card["id"])
            printed_card = get_card(conn, card["id"]) or card
        finally:
            conn.close()

        with _STATE_LOCK:
            if LAST_CARD and LAST_CARD.get("id") == card.get("id"):
                LAST_CARD = dict(printed_card)

        return {"ok": True, "card": card_to_json(printed_card)}


def status():
    with _STATE_LOCK:
        last_card = dict(LAST_CARD) if LAST_CARD else None

    conn = connect()
    try:
        data = {
            "cards": card_count(conn),
            "back_faces": back_face_count(conn),
            "printed_unique": printed_card_count(conn),
            "prints_total": total_print_count(conn),
            "last_card": card_to_json(last_card),
        }
    finally:
        conn.close()
    return data


def search(query):
    q_norm = normalize_search_text(query)
    if not q_norm:
        return []

    conn = connect()
    try:
        # Fast path: SQL handles the common exact/substring searches first.
        like = f"%{query.strip()}%"
        direct_rows = conn.execute(
            "SELECT * FROM cards WHERE name LIKE ? ORDER BY name LIMIT 20",
            (like,),
        ).fetchall()
        if direct_rows:
            return [card_to_json(dict(row)) for row in direct_rows]

        # Fuzzy fallback is only used when the fast path found nothing.
        rows = conn.execute("SELECT * FROM cards ORDER BY name").fetchall()
    finally:
        conn.close()

    matches = []
    for row in rows:
        card = dict(row)
        name = card.get("name") or ""
        name_norm = normalize_search_text(name)
        type_norm = normalize_search_text(card.get("type_line") or "")

        words = q_norm.split()
        pos = 0
        ordered = True
        for word in words:
            found = name_norm.find(word, pos)
            if found == -1:
                ordered = False
                break
            pos = found + len(word)

        if ordered:
            score = 750 - pos
        else:
            name_score = fuzz.token_set_ratio(q_norm, name_norm)
            partial_score = fuzz.partial_ratio(q_norm, name_norm)
            type_score = fuzz.partial_ratio(q_norm, type_norm)
            score = max(name_score, partial_score, type_score * 0.75)
            if score < 55:
                continue

        matches.append((score, len(name), card))

    matches.sort(key=lambda item: (-item[0], item[1]))
    return [card_to_json(card) for _, _, card in matches[:20]]


def print_back_current():
    if get_printer_type() == "thermal_58mm":
        return {
            "ok": False,
            "error": "Back-face printing currently requires photo-printer mode.",
        }
    if card_update_status().get("running"):
        return {
            "ok": False,
            "error": "Card database update is running. Print after it finishes.",
        }

    with _CARD_OPERATION_LOCK:
        with _STATE_LOCK:
            card = dict(LAST_CARD) if LAST_CARD else None

        if not card:
            return {"ok": False, "error": "No current card selected."}
        if not card_has_back(card):
            return {"ok": False, "error": "This creature has no stored back face."}

        rendered = render_printer_back_face(card)
        if not rendered:
            return {"ok": False, "error": "Stored back-face data is unavailable."}

        if not print_printer(rendered):
            return {"ok": False, "error": "Back image was rendered, but printing failed."}
        return {
            "ok": True,
            "card": card_to_json(card),
            "output": f"Printed local back face from {rendered}",
        }


def _cached_value(key, ttl_seconds, loader):
    now = time.monotonic()
    with _STATUS_CACHE_LOCK:
        cached = _STATUS_CACHE.get(key)
        if cached and now - cached[0] < ttl_seconds:
            return cached[1]

    value = loader()
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE[key] = (time.monotonic(), value)
    return value


def _run_printer_probe(command, timeout_seconds):
    # Run a Bluetooth probe and kill its entire process group on timeout.
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        return {
            "returncode": 124,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "timed_out": True,
        }

    return {
        "returncode": process.returncode,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "timed_out": False,
    }


# MOMIR_THERMAL_PRINTER_STATUS_CACHE_START
def clear_printer_status_cache():
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE.clear()


# MOMIR_THERMAL_PRINTER_STATUS_CACHE_END
def _load_printer_status():
    if get_printer_type() == "thermal_58mm":
        settings = get_thermal_printer_settings()
        if settings["transport"] == "mock":
            return {
                "connected": True,
                "message": "Thermal Mock Ready",
                "details": (
                    "Jobs are saved under prints/thermal-mock/ and are not "
                    "sent to physical hardware."
                ),
                "printer_type": "thermal_58mm",
                "transport": "mock",
            }

        probe = probe_thermal_connection(settings)
        connected = bool(probe.get("ok"))
        if connected:
            details = (
                f"PT210-compatible RFCOMM printer at "
                f"{settings['bluetooth_address']}, channel "
                f"{settings['rfcomm_channel']}."
            )
        else:
            details = (
                "Could not reach the thermal printer: "
                f"{probe.get('error') or 'unknown Bluetooth error'}"
            )
        return {
            "connected": connected,
            "message": (
                "Thermal Printer Ready"
                if connected
                else "Thermal Printer Unavailable"
            ),
            "details": details,
            "printer_type": "thermal_58mm",
            "transport": "bluetooth_rfcomm",
        }

    mac = get_printer_address(required=False)

    if not mac:
        return {
            "connected": False,
            "message": "Printer Not Configured",
            "details": "Set printer.bluetooth_address in config.local.json.",
        }

    with _PRINTER_PROBE_LOCK:
        try:
            ping = _run_printer_probe(
                [
                    "sudo",
                    "-n",
                    "/usr/bin/l2ping",
                    "-c",
                    "1",
                    "-t",
                    "5",
                    mac,
                ],
                timeout_seconds=7,
            )

            if ping["returncode"] == 0:
                details = (
                    ping["stdout"].strip()
                    or "Bluetooth echo reply received."
                )
                return {
                    "connected": True,
                    "message": "Printer Ready",
                    "details": details,
                }

            info = subprocess.run(
                ["bluetoothctl", "info", mac],
                text=True,
                capture_output=True,
                timeout=4,
            )

            paired = (
                info.returncode == 0
                and "Paired: yes" in info.stdout
            )

            if paired:
                if ping["timed_out"]:
                    details = (
                        "The paired printer did not answer the Bluetooth "
                        "readiness probe within 7 seconds."
                    )
                else:
                    details = (
                        ping["stderr"].strip()
                        or ping["stdout"].strip()
                        or (
                            "The paired printer did not answer "
                            "the readiness probe."
                        )
                    )

                return {
                    "connected": False,
                    "message": "Printer Off",
                    "details": details,
                }

            details = (
                info.stderr.strip()
                or ping["stderr"].strip()
                or "The configured Bluetooth device is not paired."
            )

            return {
                "connected": False,
                "message": "Printer Not Paired",
                "details": details,
            }

        except FileNotFoundError as exc:
            return {
                "connected": False,
                "message": "Printer Check Unavailable",
                "details": str(exc),
            }

        except Exception as exc:
            return {
                "connected": False,
                "message": "Printer Unknown",
                "details": str(exc),
            }


def printer_status():
    # Bluetooth probing can block. Reuse the result instead of probing twice
    # every 10 seconds from the phone page.
    return _cached_value("printer", 30, _load_printer_status)


def _load_network_status():
    def run(cmd):
        try:
            return subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=3,
            ).stdout.strip()
        except Exception:
            return ""

    wifi = run([
        "bash",
        "-lc",
        "nmcli -t -f NAME,DEVICE connection show --active | awk -F: '$2==\"wlan0\" {print $1; exit}'",
    ])
    ip = run(["bash", "-lc", "hostname -I | awk '{print $1}'"])
    tail = run(["bash", "-lc", "tailscale ip -4 2>/dev/null | head -1"])

    return {
        "wifi": wifi or "unknown",
        "ip": ip or "unknown",
        "tailscale": tail or "unknown",
    }


def network_status():
    return _cached_value("network", 60, _load_network_status)



def _set_update_state(**changes):
    with _UPDATE_STATE_LOCK:
        _UPDATE_STATE.update(changes)


def card_update_status():
    with _UPDATE_STATE_LOCK:
        state = dict(_UPDATE_STATE)
        if isinstance(state.get("summary"), dict):
            state["summary"] = dict(state["summary"])
        return state


def _create_database_backup():
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "backups" / f"card_update_ui_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "momir.db"

    source = sqlite3.connect(DB_PATH)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_path


def _run_card_update():
    global LAST_CARD, LAST_RENDERED

    try:
        # Printing and the update are mutually exclusive. This keeps printed
        # tracking from changing between the updater's snapshot and commit.
        with _CARD_OPERATION_LOCK:
            from update_cards import iter_scryfall_cards, update_database

            backup_path = _create_database_backup()
            _set_update_state(
                state="downloading",
                message="Downloading the latest Scryfall creature list...",
                backup=str(backup_path),
            )

            def report_progress(progress):
                page = progress["page"]
                total_pages = progress["total_pages"]
                downloaded = progress["downloaded"]
                total_cards = progress["total_cards"]
                percent = progress["progress_percent"]
                _set_update_state(
                    state="downloading",
                    page=page,
                    total_pages=total_pages,
                    downloaded=downloaded,
                    total_cards=total_cards,
                    progress_percent=percent,
                    message=(
                        f"Downloaded page {page} of {total_pages} — "
                        f"{downloaded:,} of {total_cards:,} cards ({percent}%)."
                    ),
                )

            summary = update_database(
                iter_scryfall_cards(progress_callback=report_progress)
            )

            # A selected Battle or reverse-face-only creature may have just
            # been removed. Clear it rather than allowing a stale print.
            with _STATE_LOCK:
                current_id = LAST_CARD.get("id") if LAST_CARD else None
                if current_id:
                    conn = connect()
                    try:
                        still_exists = get_card(conn, current_id)
                    finally:
                        conn.close()
                    if still_exists:
                        LAST_CARD = dict(still_exists)
                        LAST_RENDERED = None
                    else:
                        LAST_CARD = None
                        LAST_RENDERED = None

        _set_update_state(
            running=False,
            state="complete",
            message=(
                f"Update complete: {summary['added']} added, "
                f"{summary['removed']} removed, {summary['imported']} total, "
                f"{summary.get('with_back', 0)} with stored backs."
            ),
            finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            summary=summary,
            error=None,
        )
    except Exception as exc:
        print("Momir card update failed:", file=sys.stderr)
        traceback.print_exc()
        _set_update_state(
            running=False,
            state="error",
            message="Card update failed.",
            finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            error=str(exc),
        )


def start_card_update():
    with _UPDATE_STATE_LOCK:
        if _UPDATE_STATE["running"]:
            return False, card_update_status()
        _UPDATE_STATE.update(
            {
                "running": True,
                "state": "starting",
                "message": "Preparing card database update...",
                "page": None,
                "total_pages": None,
                "downloaded": None,
                "total_cards": None,
                "progress_percent": None,
                "started_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "finished_at": None,
                "summary": None,
                "error": None,
                "backup": None,
            }
        )

    thread = threading.Thread(
        target=_run_card_update,
        name="momir-card-update",
        daemon=True,
    )
    thread.start()
    return True, card_update_status()

def dashboard_status():
    return {
        "printer": printer_status(),
        "network": network_status(),
        "status": status(),
    }
