#!/usr/bin/env python3
"""Generic 2x3 printer renderer for Momir creature cards."""
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
import threading
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont
from momir_config import (
    get_local_base_url,
    get_printer_address,
    get_printer_channel,
)

try:
    import qrcode
except Exception:
    qrcode = None

ROOT = Path(__file__).resolve().parent
PRINTS_DIR = ROOT / "prints"
PRINTS_DIR.mkdir(exist_ok=True)
PREVIEWS_DIR = PRINTS_DIR / "previews"
PREVIEWS_DIR.mkdir(exist_ok=True)
SYMBOL_DIR = ROOT / "mana_symbols"
_RENDER_LOCK = threading.Lock()

# Printer canvas. These values came from print calibration.
W, H = 450, 730
SAFE_LEFT = 25       # slightly less side margin
SAFE_TOP = 45        # keep extra top margin to avoid clipping
SAFE_RIGHT = 25      # slightly less side margin
SAFE_BOTTOM = 40     # increased bottom margin to avoid clipping

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

SYMBOL_RE = re.compile(r"\{([^}]+)\}")


@lru_cache(maxsize=64)
def font(path, size):
    return ImageFont.truetype(path, size)


def sanitize_filename(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")[:60]


def symbol_code(raw: str) -> str:
    code = raw.upper().replace("/", "")
    # In project chat shorthand, O means Phyrexian. Real Scryfall text uses /P.
    if code.endswith("O") and len(code) > 1:
        code = code[:-1] + "P"
    return code


@lru_cache(maxsize=256)
def load_symbol(code: str, size: int):
    code = symbol_code(code)
    path = SYMBOL_DIR / f"{code}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def draw_fallback_symbol(draw, x, y, code, size):
    code = symbol_code(code)
    draw.ellipse((x, y, x + size, y + size), outline="black", width=2, fill="white")
    f = font(FONT_BOLD, max(10, int(size * 0.52)))
    box = draw.textbbox((0, 0), code, font=f)
    tx = x + (size - (box[2] - box[0])) // 2 - box[0]
    ty = y + (size - (box[3] - box[1])) // 2 - box[1]
    draw.text((tx, ty), code, fill="black", font=f)


def draw_symbol(canvas, draw, x, y, code, size):
    img = load_symbol(code, size)
    if img:
        canvas.paste(img, (int(x), int(y)), img)
    else:
        draw_fallback_symbol(draw, int(x), int(y), code, size)


def split_symbols(text: str):
    parts = []
    pos = 0
    for m in SYMBOL_RE.finditer(text or ""):
        if m.start() > pos:
            parts.append(("text", text[pos:m.start()]))
        parts.append(("symbol", m.group(1)))
        pos = m.end()
    if pos < len(text or ""):
        parts.append(("text", text[pos:]))
    return parts


def measure_tokens(draw, tokens, text_font, symbol_size):
    width = 0
    for typ, val in tokens:
        if typ == "symbol":
            width += symbol_size + 2
        else:
            box = draw.textbbox((0, 0), val, font=text_font)
            width += box[2] - box[0]
    return width


def wrap_symbol_text(draw, text, max_width, text_font, symbol_size):
    lines = []
    for paragraph in (text or "").split("\n"):
        if paragraph.strip() == "":
            lines.append([])
            continue
        raw_words = paragraph.split(" ")
        current = []
        for i, word in enumerate(raw_words):
            tokens = split_symbols(word)
            if i != len(raw_words) - 1:
                tokens = tokens + [("text", " ")]
            trial = current + tokens
            if current and measure_tokens(draw, trial, text_font, symbol_size) > max_width:
                lines.append(current)
                current = tokens
            else:
                current = trial
        if current:
            lines.append(current)
    return lines


def draw_tokens(canvas, draw, x, y, tokens, text_font, symbol_size, fill="black"):
    cx = x
    for typ, val in tokens:
        if typ == "symbol":
            draw_symbol(canvas, draw, cx, y + 1, val, symbol_size)
            cx += symbol_size + 3
        else:
            draw.text((cx, y), val, fill=fill, font=text_font)
            box = draw.textbbox((0, 0), val, font=text_font)
            cx += box[2] - box[0]


def draw_fit_text(draw, xy, text, max_width, preferred_size, min_size, bold=True):
    path = FONT_BOLD if bold else FONT_REG
    for size in range(preferred_size, min_size - 1, -1):
        f = font(path, size)
        candidate = text
        while candidate:
            box = draw.textbbox((0, 0), candidate, font=f)
            if box[2] - box[0] <= max_width:
                draw.text(xy, candidate, fill="black", font=f)
                return size
            candidate = candidate[:-1]
    f = font(path, min_size)
    draw.text(xy, text[:10], fill="black", font=f)
    return min_size


@lru_cache(maxsize=256)
def make_qr(uri: str, size: int):
    if not uri or qrcode is None:
        img = Image.new("RGB", (size, size), "white")
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, size - 1, size - 1), outline="black", width=3)
        d.text((size // 4, size // 3), "QR", fill="black", font=font(FONT_BOLD, max(14, size // 4)))
        return img
    qr = qrcode.QRCode(border=1, box_size=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((size, size), Image.Resampling.NEAREST)


def local_card_url(card):
    """Stable local rules page used during offline play."""
    base = get_local_base_url()
    card_id = quote(str(card.get("id") or ""), safe="")
    return f"{base}/card/{card_id}" if card_id else base


def back_face_card(card):
    raw = card.get("back_face_json")
    if not raw:
        return None
    try:
        face = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not face.get("name"):
        return None
    face["id"] = card.get("id")
    face["oracle_id"] = card.get("oracle_id")
    face["storage_letter"] = card.get("storage_letter")
    return face


def draw_mana_cost(canvas, draw, x, y, mana_cost, max_width):
    symbols = SYMBOL_RE.findall(mana_cost or "")
    if not symbols:
        return 0
    size = 25
    gap = 3
    total = len(symbols) * size + max(0, len(symbols) - 1) * gap
    if total > max_width:
        size = max(18, int((max_width - (len(symbols) - 1) * gap) / max(1, len(symbols))))
    cx = x
    for sym in symbols:
        draw_symbol(canvas, draw, cx, y, sym, size)
        cx += size + gap
    return size



def fit_name_lines(draw, name: str, max_width: int):
    """Return 1-2 uppercase name lines, preferring comma splits for legendary names."""
    name = (name or "Unknown").upper()
    f31 = font(FONT_BOLD, 31)
    if draw.textbbox((0, 0), name, font=f31)[2] <= max_width:
        return [name]

    if "," in name:
        left, right_part = name.split(",", 1)
        candidate = [left.strip() + ",", right_part.strip()]
        if all(draw.textbbox((0, 0), line, font=f31)[2] <= max_width for line in candidate if line):
            return [line for line in candidate if line]

    words = name.split()
    if len(words) <= 1:
        return [name]
    best = None
    best_score = 10**9
    for i in range(1, len(words)):
        a = " ".join(words[:i])
        b = " ".join(words[i:])
        wa = draw.textbbox((0, 0), a, font=f31)[2]
        wb = draw.textbbox((0, 0), b, font=f31)[2]
        overflow = max(0, wa - max_width) + max(0, wb - max_width)
        balance = abs(wa - wb)
        score = overflow * 1000 + balance
        if score < best_score:
            best_score = score
            best = [a, b]
    return best or textwrap.wrap(name, width=22)[:2]

def _render_printer_image(card, face_label=None):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    x = SAFE_LEFT
    y = SAFE_TOP
    right = W - SAFE_RIGHT
    usable_w = right - x
    bottom = H - SAFE_BOTTOM

    name_f = font(FONT_BOLD, 31)
    type_f = font(FONT_BOLD, 18)
    rules_size = 20
    rules_min = 16
    pt_f = font(FONT_BOLD, 48)

    name = card.get("name", "Unknown")
    name_lines = fit_name_lines(d, name, usable_w)[:2]
    for line in name_lines:
        draw_fit_text(d, (x, y), line, usable_w, 31, 22, bold=True)
        y += 35
    y += 4
    d.line((x, y, right, y), fill="black", width=3)
    y += 10

    type_line = card.get("type_line") or ""
    type_lines = textwrap.wrap(type_line, width=34)[:2]
    for line in type_lines:
        draw_fit_text(d, (x, y), line, usable_w, 18, 15, bold=True)
        y += 22
    y += 5

    # The mana symbols already communicate the cost. Keep this row clean by
    # omitting the redundant "MV X" label and starting the symbols at the left.
    mana_cost = card.get("mana_cost") or ""
    if mana_cost:
        draw_mana_cost(img, d, x, y - 1, mana_cost, usable_w)
        y += 32
    else:
        y += 6
    d.line((x, y, right, y), fill="black", width=2)
    y += 12

    has_pt = bool(card.get("power") or card.get("toughness"))
    qr_size = 76
    bottom_line_y = bottom - 102
    rules_bottom = bottom_line_y - 8

    oracle = card.get("oracle_text") or ""
    oracle = oracle.replace("\u2212", "-")

    for size in range(rules_size, rules_min - 1, -1):
        f = font(FONT_REG, size)
        sym_size = max(15, size + 2)
        lines = wrap_symbol_text(d, oracle, usable_w, f, sym_size)
        line_h = size + 6
        total_h = sum((line_h if line else 10) for line in lines)
        if y + total_h <= rules_bottom:
            break
    else:
        f = font(FONT_REG, rules_min)
        sym_size = rules_min + 2
        lines = wrap_symbol_text(d, oracle, usable_w, f, sym_size)
        line_h = rules_min + 6

    cy = y
    max_lines = max(1, (rules_bottom - y) // line_h)
    if len(lines) > max_lines:
        lines = lines[:max(1, max_lines - 1)]
        lines.append([("text", "[...] Full text in Momir UI")])

    for line in lines:
        if not line:
            cy += 10
        else:
            draw_tokens(img, d, x, cy, line, f, sym_size)
            cy += line_h

    # Bottom section: QR on left, P/T on right.
    d.line((x, bottom_line_y, right, bottom_line_y), fill="black", width=3)
    stat_y = bottom_line_y + 18

    qr = make_qr(local_card_url(card), qr_size)
    img.paste(qr, (x, bottom - qr_size))

    if face_label:
        label_f = font(FONT_BOLD, 20)
        d.text((x + qr_size + 14, bottom - 28), face_label, fill="black", font=label_f)

    stat = None
    stat_font = pt_f
    if has_pt:
        stat = f"{card.get('power') or '?'}/{card.get('toughness') or '?'}"
    elif card.get("loyalty") not in (None, ""):
        stat = f"L {card.get('loyalty')}"
        stat_font = font(FONT_BOLD, 32)
    elif card.get("defense") not in (None, ""):
        stat = f"D {card.get('defense')}"
        stat_font = font(FONT_BOLD, 32)

    if stat:
        stat_box = d.textbbox((0, 0), stat, font=stat_font)
        stat_w = stat_box[2] - stat_box[0]
        stat_y = bottom - stat_box[3]
        d.text((right - stat_w, stat_y), stat, fill="black", font=stat_font)

    return img


def _cache_is_current(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return path.stat().st_mtime >= Path(__file__).stat().st_mtime
    except OSError:
        return False


def render_printer(card, force: bool = False, face=None, is_back: bool = False):
    """Render and cache a full printer-resolution image.

    ``face`` and ``is_back`` are supported for the legacy face-print helper.
    Normal gameplay passes only the locally stored card record.
    """
    source_card = dict(card)
    rendered_card = dict(face) if face else dict(source_card)
    for key in ("id", "oracle_id", "storage_letter"):
        if not rendered_card.get(key) and source_card.get(key):
            rendered_card[key] = source_card.get(key)

    name = rendered_card.get("name", "Unknown")
    identity = source_card.get("id") or rendered_card.get("id") or name
    identity = sanitize_filename(str(identity))
    prefix = "printer_back" if is_back else "printer"
    out = PRINTS_DIR / f"{prefix}_{sanitize_filename(name)}_{identity}.jpg"

    with _RENDER_LOCK:
        if force or not _cache_is_current(out):
            img = _render_printer_image(
                rendered_card,
                face_label="BACK" if is_back else None,
            )
            temp = out.with_suffix(".tmp.jpg")
            img.save(temp, quality=100)
            temp.replace(out)

        last_name = "printer_back_last.jpg" if is_back else "printer_last.jpg"
        shutil.copyfile(out, PRINTS_DIR / last_name)

    return out


def render_printer_preview(card, width: int = 300, force: bool = False):
    """Render a compact mobile preview and cache it by card ID."""
    width = max(180, min(int(width), W))
    height = round(H * width / W)
    card_id = sanitize_filename(str(card.get("id") or card.get("name") or "unknown"))
    out = PREVIEWS_DIR / f"preview_{card_id}_{width}.jpg"

    with _RENDER_LOCK:
        if force or not _cache_is_current(out):
            img = _render_printer_image(card)
            img = img.resize((width, height), Image.Resampling.LANCZOS)
            temp = out.with_suffix(".tmp.jpg")
            # Quality 84 is visually clean on a phone and substantially smaller.
            img.save(temp, quality=84, subsampling=1)
            temp.replace(out)

    return out


def render_printer_back_face(card, force: bool = False):
    """Render the locally stored reverse face at printer resolution."""
    face = back_face_card(card)
    if not face:
        return None
    name = face.get("name", "Back")
    out = PRINTS_DIR / f"printer_back_{sanitize_filename(name)}_{card.get('id')}.jpg"

    with _RENDER_LOCK:
        if force or not _cache_is_current(out):
            img = _render_printer_image(face, face_label="BACK")
            temp = out.with_suffix(".tmp.jpg")
            img.save(temp, quality=100)
            temp.replace(out)
    return out


def render_printer_back_preview(card, width: int = 300, force: bool = False):
    """Render and cache a compact preview of the locally stored reverse face."""
    face = back_face_card(card)
    if not face:
        return None
    width = max(180, min(int(width), W))
    height = round(H * width / W)
    card_id = sanitize_filename(str(card.get("id") or card.get("name") or "unknown"))
    out = PREVIEWS_DIR / f"preview_back_{card_id}_{width}.jpg"

    with _RENDER_LOCK:
        if force or not _cache_is_current(out):
            img = _render_printer_image(face, face_label="BACK")
            img = img.resize((width, height), Image.Resampling.LANCZOS)
            temp = out.with_suffix(".tmp.jpg")
            img.save(temp, quality=84, subsampling=1)
            temp.replace(out)
    return out


def print_printer(path, mac: str | None = None):
    import subprocess
    import time

    mac = mac or get_printer_address()
    channel = get_printer_channel()

    cmd = [
        "obexftp",
        "--bluetooth", mac,
        "--channel", channel,
        "--put", str(path),
    ]

    result = subprocess.run(cmd)

    if result.returncode in (0, 255):
        # Some printers return 255 even after accepting the job.
        time.sleep(2)
        return True

    if result.returncode == 69:
        print("WARNING: Printer rejected the transfer with return code 69.")
        print("Most likely cause: out of paper, lid open, or printer not ready.")
        print(f"Sticker image was saved here: {path}")
        return False

    print(f"WARNING: Printer transfer failed with return code {result.returncode}.")
    print("Check printer power, paper, Bluetooth connection, and try again.")
    print(f"Sticker image was saved here: {path}")
    return False

def render_printer_back():
    """Render a simple generic printer card back."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 450, 730
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    try:
        title = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54
        )
        subtitle = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30
        )
        body = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24
        )
        small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
        )
    except Exception:
        title = ImageFont.load_default()
        subtitle = ImageFont.load_default()
        body = ImageFont.load_default()
        small = ImageFont.load_default()

    def center(text, y, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y), text, fill="black", font=font)

    left, top, right, bottom = 34, 44, W - 34, H - 24
    draw.rectangle((left, top, right, bottom), outline="black", width=4)

    center("MOMIR", 130, title)
    center("BASIC", 195, subtitle)

    draw.line((70, 270, W - 70, 270), fill="black", width=3)

    center("Creature Library", 315, body)
    center("Alphabetize by Name", 365, body)
    center("One Copy Per Card", 415, body)

    draw.line((70, 500, W - 70, 500), fill="black", width=3)

    center("Kevin's Momir", 555, body)
    center("Momir Summoner", 610, small)

    out = ROOT / "prints" / "printer_card_back.jpg"
    out.parent.mkdir(exist_ok=True)
    img.save(out, quality=95)
    return out
