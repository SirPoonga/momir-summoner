#!/usr/bin/env python3
"""58 mm thermal receipt formatting, preview rendering, and mock output."""

from __future__ import annotations

import re
import socket
import struct
import time
import textwrap
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont

from momir_config import get_local_base_url, get_thermal_printer_settings

try:
    import qrcode
except Exception:  # pragma: no cover - qrcode is already an application dependency.
    qrcode = None


ROOT = Path(__file__).resolve().parent
PRINTS_DIR = ROOT / "prints"
THERMAL_MOCK_DIR = PRINTS_DIR / "thermal-mock"
THERMAL_PREVIEW_DIR = PRINTS_DIR / "thermal-previews"

FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

_RENDER_LOCK = threading.Lock()
_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")

_TEXT_REPLACEMENTS = str.maketrans(
    {
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "*",
        "\u00a0": " ",
    }
)


def sanitize_filename(value: object) -> str:
    text = _FILENAME_RE.sub("_", str(value or "unknown")).strip("_")
    return (text or "unknown")[:80]


def normalize_thermal_text(value: object) -> str:
    """Normalize punctuation and remove mana-symbol braces for receipts."""

    text = str(value or "").translate(_TEXT_REPLACEMENTS)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("{", "").replace("}", "")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def scryfall_card_url(card: dict) -> str:
    """Exact Scryfall page encoded in the native thermal QR code."""
    uri = str(card.get("scryfall_uri") or "").strip()
    if uri:
        return uri

    card_name = str(card.get("name") or "").strip()
    if card_name:
        return f"https://scryfall.com/search?q={quote(card_name)}"

    return "https://scryfall.com/"

def _wrap_paragraph(text: str, columns: int) -> list[str]:
    if not text.strip():
        return [""]
    return textwrap.wrap(
        text,
        width=columns,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
    ) or [""]


def _header_lines(name: str, mana_cost: str, columns: int) -> list[str]:
    name_lines = _wrap_paragraph(name or "Unknown", columns)
    if not mana_cost:
        return name_lines

    if len(name_lines) == 1 and len(name_lines[0]) + 1 + len(mana_cost) <= columns:
        return [
            name_lines[0]
            + (" " * (columns - len(name_lines[0]) - len(mana_cost)))
            + mana_cost
        ]

    return [*name_lines, mana_cost.rjust(columns)]


def format_thermal_lines(card: dict, columns: int | None = None) -> list[str]:
    """Return the native-text portion of a thermal receipt job.

    The only card fields included are name, mana cost, creature type,
    oracle/rules text, and power/toughness. The QR code is carried separately
    as a graphic payload.
    """

    if columns is None:
        columns = get_thermal_printer_settings()["columns"]
    columns = int(columns)
    if not 24 <= columns <= 48:
        raise ValueError("Thermal columns must be between 24 and 48.")

    name = normalize_thermal_text(card.get("name")) or "Unknown"
    mana_cost = normalize_thermal_text(card.get("mana_cost"))
    type_line = normalize_thermal_text(card.get("type_line"))
    oracle_text = normalize_thermal_text(card.get("oracle_text"))
    power = normalize_thermal_text(card.get("power"))
    toughness = normalize_thermal_text(card.get("toughness"))

    lines: list[str] = []
    lines.extend(_header_lines(name, mana_cost, columns))

    if type_line:
        lines.extend(_wrap_paragraph(type_line, columns))

    lines.append("-" * columns)

    if oracle_text:
        # Each rules paragraph already begins on a new text line. Do not add
        # another empty line between abilities; this keeps receipts compact
        # and reduces print/feed time.
        for paragraph in oracle_text.split("\n"):
            if not paragraph.strip():
                continue
            lines.extend(_wrap_paragraph(paragraph, columns))

    lines.append("-" * columns)

    if power or toughness:
        lines.append(f"{power or '?'}/{toughness or '?'}".rjust(columns))

    return lines


def build_thermal_job(card: dict, settings: dict | None = None) -> dict:
    settings = dict(settings or get_thermal_printer_settings())
    return {
        "lines": format_thermal_lines(card, settings["columns"]),
        "qr_url": scryfall_card_url(card),
        "settings": settings,
    }


@lru_cache(maxsize=16)
def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _qr_image(payload: str, size: int) -> Image.Image:
    if qrcode is None:
        image = Image.new("1", (size, size), 1)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, size - 1, size - 1), outline=0, width=3)
        draw.text(
            (size // 3, size // 2),
            "QR",
            fill=0,
            font=_font(FONT_BOLD, 18),
        )
        return image

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("1")
    return image.resize((size, size), Image.Resampling.NEAREST)


def render_thermal_preview(
    card: dict,
    output_path: Path | str | None = None,
    *,
    settings: dict | None = None,
    force: bool = False,
) -> Path:
    # Render a compact monochrome preview of text plus the QR graphic.
    # Rules abilities receive a small visual gap rather than a full blank
    # line. The QR code and power/toughness share the final horizontal row.

    job = build_thermal_job(card, settings)
    settings = job["settings"]
    width = int(settings["paper_width_pixels"])
    qr_size = int(settings["qr_size_pixels"])
    columns = max(1, int(settings["columns"]))

    card_id = sanitize_filename(card.get("id") or card.get("name"))
    if output_path is None:
        THERMAL_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        output_path = THERMAL_PREVIEW_DIR / (
            f"thermal_{card_id}_{columns}c_"
            f"{width}w_{qr_size}q_sideqr_v2.png"
        )
    output_path = Path(output_path)

    with _RENDER_LOCK:
        if output_path.exists() and not force:
            return output_path

        side_padding = 12
        font_size = max(
            12,
            min(
                22,
                int(
                    (width - (side_padding * 2))
                    / (columns * 0.62)
                ),
            ),
        )
        regular = _font(FONT_REG, font_size)
        bold = _font(FONT_BOLD, font_size)
        line_height = font_size + 7
        top_padding = 16
        ability_gap = max(4, line_height // 4)
        qr_row_gap = 10
        bottom_padding = 18

        divider = "-" * columns
        lines = list(job["lines"])
        divider_indexes = [
            index for index, line in enumerate(lines) if line == divider
        ]
        if len(divider_indexes) < 2:
            raise RuntimeError("Thermal preview layout is missing divider lines.")

        first_divider = divider_indexes[0]
        heading_lines = lines[:first_divider]

        oracle_text = normalize_thermal_text(card.get("oracle_text"))
        rule_paragraphs = [
            _wrap_paragraph(paragraph, columns)
            for paragraph in oracle_text.split("\n")
            if paragraph.strip()
        ]

        power = normalize_thermal_text(card.get("power")) or "?"
        toughness = normalize_thermal_text(card.get("toughness")) or "?"
        power_toughness = f"{power}/{toughness}"

        heading_height = len(heading_lines) * line_height
        first_divider_height = line_height
        rules_height = sum(
            len(paragraph) * line_height for paragraph in rule_paragraphs
        )
        rules_height += max(0, len(rule_paragraphs) - 1) * ability_gap
        second_divider_height = line_height

        height = (
            top_padding
            + heading_height
            + first_divider_height
            + rules_height
            + second_divider_height
            + qr_row_gap
            + qr_size
            + bottom_padding
        )

        image = Image.new("1", (width, height), 1)
        draw = ImageDraw.Draw(image)

        y = top_padding
        for index, line in enumerate(heading_lines):
            selected_font = bold if index == 0 else regular
            draw.text(
                (side_padding, y),
                line,
                fill=0,
                font=selected_font,
            )
            y += line_height

        draw.line(
            (
                side_padding,
                y + line_height // 2,
                width - side_padding,
                y + line_height // 2,
            ),
            fill=0,
            width=2,
        )
        y += line_height

        for paragraph_index, paragraph_lines in enumerate(rule_paragraphs):
            for line in paragraph_lines:
                draw.text(
                    (side_padding, y),
                    line,
                    fill=0,
                    font=regular,
                )
                y += line_height
            if paragraph_index != len(rule_paragraphs) - 1:
                y += ability_gap

        draw.line(
            (
                side_padding,
                y + line_height // 2,
                width - side_padding,
                y + line_height // 2,
            ),
            fill=0,
            width=2,
        )
        y += line_height + qr_row_gap

        qr_y = y
        qr = _qr_image(job["qr_url"], qr_size)

        pt_bbox = draw.textbbox(
            (0, 0),
            power_toughness,
            font=bold,
        )
        pt_width = pt_bbox[2] - pt_bbox[0]
        pt_x = width - side_padding - pt_width
        pt_y = qr_y

        available_left_width = max(
            qr_size,
            pt_x - (side_padding * 2),
        )
        qr_x = side_padding + max(
            0,
            (available_left_width - qr_size) // 2,
        )

        if qr_x + qr_size + side_padding > pt_x:
            qr_x = side_padding
            maximum_qr_width = max(
                96,
                pt_x - (side_padding * 2),
            )
            if maximum_qr_width < qr_size:
                qr = qr.resize(
                    (maximum_qr_width, maximum_qr_width),
                    Image.Resampling.NEAREST,
                )

        image.paste(qr, (qr_x, qr_y))
        draw.text(
            (pt_x, pt_y),
            power_toughness,
            fill=0,
            font=bold,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".tmp.png")
        image.save(temporary, format="PNG", optimize=True)
        temporary.replace(output_path)

    return output_path


def write_mock_thermal_job(card: dict, settings: dict | None = None) -> dict:
    """Save a text job and a monochrome preview instead of using hardware."""

    job = build_thermal_job(card, settings)
    THERMAL_MOCK_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    card_name = sanitize_filename(card.get("name"))
    stem = f"{stamp}_{card_name}"
    text_path = THERMAL_MOCK_DIR / f"{stem}.txt"
    preview_path = THERMAL_MOCK_DIR / f"{stem}.png"

    debug_text = "\n".join(job["lines"])
    debug_text += f"\n\n[QR GRAPHIC]\n{job['qr_url']}\n"
    text_path.write_text(debug_text, encoding="utf-8")
    render_thermal_preview(
        card,
        preview_path,
        settings=job["settings"],
        force=True,
    )

    return {
        "ok": True,
        "transport": "mock",
        "text_path": str(text_path),
        "preview_path": str(preview_path),
        "qr_url": job["qr_url"],
    }


def _escpos_text(value: object) -> bytes:
    return normalize_thermal_text(value).encode("ascii", errors="replace")


def _native_qr_commands(payload: str, module_size: int) -> bytes:
    data = payload.encode("utf-8")
    store_length = len(data) + 3
    if store_length > 65535:
        raise ValueError("Thermal QR payload is too long.")

    commands = bytearray()
    commands += b"\x1d\x28\x6b\x04\x00\x31\x41\x32\x00"
    commands += b"\x1d\x28\x6b\x03\x00\x31\x43"
    commands += bytes((module_size,))
    commands += b"\x1d\x28\x6b\x03\x00\x31\x45\x31"
    commands += b"\x1d\x28\x6b"
    commands += struct.pack("<H", store_length)
    commands += b"\x31\x50\x30"
    commands += data
    commands += b"\x1d\x28\x6b\x03\x00\x31\x51\x30"
    return bytes(commands)


def build_bluetooth_escpos_payload(
    card: dict,
    settings: dict | None = None,
) -> bytes:
    settings = dict(settings or get_thermal_printer_settings())
    columns = int(settings["columns"])
    module_size = int(settings.get("qr_module_size", 5))
    feed_lines = int(settings.get("feed_lines", 1))

    name = normalize_thermal_text(card.get("name")) or "Unknown"
    mana_cost = normalize_thermal_text(card.get("mana_cost"))
    type_line = normalize_thermal_text(card.get("type_line"))
    oracle_text = normalize_thermal_text(card.get("oracle_text"))
    power = normalize_thermal_text(card.get("power")) or "?"
    toughness = normalize_thermal_text(card.get("toughness")) or "?"
    qr_url = scryfall_card_url(card)

    output = bytearray()
    output += b"\x1b\x40"
    output += b"\x1b\x33\x18"
    output += b"\x1b\x61\x00"

    output += b"\x1b\x45\x01"
    for line in _header_lines(name, mana_cost, columns):
        output += _escpos_text(line) + b"\r\n"
    output += b"\x1b\x45\x00"

    if type_line:
        for line in _wrap_paragraph(type_line, columns):
            output += _escpos_text(line) + b"\r\n"

    divider = "-" * columns
    output += _escpos_text(divider) + b"\r\n"

    paragraphs = [
        paragraph
        for paragraph in oracle_text.split("\n")
        if paragraph.strip()
    ]
    for paragraph_index, paragraph in enumerate(paragraphs):
        wrapped = _wrap_paragraph(paragraph, columns)
        for line_index, line in enumerate(wrapped):
            is_last_line = line_index == len(wrapped) - 1
            has_next_ability = paragraph_index != len(paragraphs) - 1
            if is_last_line and has_next_ability:
                output += b"\x1b\x33\x20"
            output += _escpos_text(line) + b"\r\n"
            if is_last_line and has_next_ability:
                output += b"\x1b\x33\x18"

    output += _escpos_text(divider) + b"\r\n"

    output += b"\x1b\x61\x02"
    output += b"\x1b\x45\x01"
    output += _escpos_text(f"{power}/{toughness}") + b"\r\n"
    output += b"\x1b\x45\x00"

    output += b"\x1b\x61\x01"
    output += _native_qr_commands(qr_url, module_size)
    output += b"\r\n"
    output += b"\n" * feed_lines
    output += b"\x1b\x61\x00"
    return bytes(output)


def probe_thermal_connection(settings: dict | None = None) -> dict:
    settings = dict(settings or get_thermal_printer_settings())
    if settings.get("transport") == "mock":
        return {
            "ok": True,
            "transport": "mock",
            "message": "Thermal mock mode is ready.",
        }

    address = settings["bluetooth_address"]
    channel = int(settings["rfcomm_channel"])
    timeout = int(settings["connect_timeout_seconds"])

    sock = socket.socket(
        socket.AF_BLUETOOTH,
        socket.SOCK_STREAM,
        socket.BTPROTO_RFCOMM,
    )
    sock.settimeout(timeout)
    try:
        sock.connect((address, channel))
    except OSError as exc:
        return {
            "ok": False,
            "transport": "bluetooth_rfcomm",
            "address": address,
            "channel": channel,
            "error": str(exc),
        }
    finally:
        sock.close()

    return {
        "ok": True,
        "transport": "bluetooth_rfcomm",
        "address": address,
        "channel": channel,
        "message": f"Bluetooth printer reachable at {address}, channel {channel}.",
    }


def print_bluetooth_rfcomm(
    card: dict,
    settings: dict | None = None,
) -> dict:
    settings = dict(settings or get_thermal_printer_settings())
    address = settings["bluetooth_address"]
    channel = int(settings["rfcomm_channel"])
    timeout = int(settings["connect_timeout_seconds"])
    delay = float(settings["post_write_delay_seconds"])
    payload = build_bluetooth_escpos_payload(card, settings)

    sock = socket.socket(
        socket.AF_BLUETOOTH,
        socket.SOCK_STREAM,
        socket.BTPROTO_RFCOMM,
    )
    sock.settimeout(timeout)
    try:
        sock.connect((address, channel))
        sock.sendall(payload)
        if delay:
            time.sleep(delay)
    except OSError as exc:
        return {
            "ok": False,
            "transport": "bluetooth_rfcomm",
            "address": address,
            "channel": channel,
            "error": f"Bluetooth thermal print failed: {exc}",
        }
    finally:
        sock.close()

    return {
        "ok": True,
        "transport": "bluetooth_rfcomm",
        "address": address,
        "channel": channel,
        "bytes_sent": len(payload),
        "qr_url": scryfall_card_url(card),
        "physical_print": True,
    }


def print_thermal(card: dict, settings: dict | None = None) -> dict:
    settings = dict(settings or get_thermal_printer_settings())
    transport = settings.get("transport", "mock")
    if transport == "mock":
        return write_mock_thermal_job(card, settings)
    if transport == "bluetooth_rfcomm":
        return print_bluetooth_rfcomm(card, settings)
    return {
        "ok": False,
        "transport": transport,
        "error": f"Unsupported thermal transport: {transport}",
    }
