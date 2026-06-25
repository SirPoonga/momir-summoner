#!/usr/bin/env python3
"""Print all local mana symbol PNGs with their tags on the configured printer.

Run from the ~/momir project folder:
    python3 print_symbols.py

Optional:
    python3 print_symbols.py --no-print
    python3 print_symbols.py --printer-address XX:XX:XX:XX:XX:XX
"""
import argparse
import math
import re
import subprocess
from pathlib import Path

from momir_config import get_printer_address, get_printer_channel

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SYMBOL_DIR = ROOT / "mana_symbols"
PRINT_DIR = ROOT / "prints"
PRINT_DIR.mkdir(exist_ok=True)

W, H = 450, 730
SAFE_LEFT = 28
SAFE_TOP = 42
SAFE_RIGHT = 28
SAFE_BOTTOM = 32

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(path: str, size: int):
    return ImageFont.truetype(path, size)


def symbol_sort_key(path: Path):
    name = path.stem
    order = {
        "W": 100, "U": 101, "B": 102, "R": 103, "G": 104, "C": 105,
        "T": 106, "Q": 107, "E": 108, "S": 109, "X": 110,
    }
    if name.isdigit():
        return (0, int(name), name)
    if name in order:
        return (1, order[name], name)
    return (2, name, name)


def pretty_tag(stem: str) -> str:
    # File names use safe names like WU.png for {W/U}, WP.png for {W/P}, 2W.png for {2/W}.
    replacements = {
        "WU": "W/U", "WB": "W/B", "UB": "U/B", "UR": "U/R", "BR": "B/R",
        "BG": "B/G", "RG": "R/G", "RW": "R/W", "GW": "G/W", "GU": "G/U",
        "2W": "2/W", "2U": "2/U", "2B": "2/B", "2R": "2/R", "2G": "2/G",
        "WP": "W/P", "UP": "U/P", "BP": "B/P", "RP": "R/P", "GP": "G/P",
        "CP": "C/P",
    }
    return "{" + replacements.get(stem, stem) + "}"


def make_pages(symbols):
    title_font = font(FONT_BOLD, 26)
    tag_font = font(FONT_BOLD, 19)
    page_font = font(FONT_REGULAR, 14)

    cols = 2
    rows = 11
    per_page = cols * rows
    symbol_size = 28
    row_h = 52
    col_w = (W - SAFE_LEFT - SAFE_RIGHT) // cols
    y_start = SAFE_TOP + 40

    out_paths = []
    pages = math.ceil(len(symbols) / per_page)

    for page_idx in range(pages):
        img = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(img)
        d.text((SAFE_LEFT, SAFE_TOP), "Mana Symbol Test", fill="black", font=title_font)
        d.text((W - SAFE_RIGHT - 80, SAFE_TOP + 7), f"{page_idx+1}/{pages}", fill="black", font=page_font)
        d.line((SAFE_LEFT, SAFE_TOP + 34, W - SAFE_RIGHT, SAFE_TOP + 34), fill="black", width=2)

        chunk = symbols[page_idx * per_page:(page_idx + 1) * per_page]
        for i, sym_path in enumerate(chunk):
            col = i // rows
            row = i % rows
            x = SAFE_LEFT + col * col_w
            y = y_start + row * row_h

            try:
                sym = Image.open(sym_path).convert("RGBA")
                sym.thumbnail((symbol_size, symbol_size), Image.Resampling.LANCZOS)
                sx = x
                sy = y + (symbol_size - sym.height) // 2
                img.paste(sym, (sx, sy), sym)
            except Exception:
                d.rectangle((x, y, x + symbol_size, y + symbol_size), outline="black", width=2)

            d.text((x + symbol_size + 10, y + 3), pretty_tag(sym_path.stem), fill="black", font=tag_font)

        out = PRINT_DIR / f"symbol_sheet_{page_idx+1:02d}.jpg"
        img.save(out, quality=100)
        out_paths.append(out)

    return out_paths


def print_printer(path: Path, address: str | None = None):
    address = address or get_printer_address()
    channel = get_printer_channel()
    cmd = ["obexftp", "--bluetooth", address, "--channel", channel, "--put", str(path)]
    result = subprocess.run(cmd)
    # Some printers report 255 even after accepting the job.
    if result.returncode not in (0, 255):
        raise subprocess.CalledProcessError(result.returncode, cmd)


def main():
    ap = argparse.ArgumentParser(description="Render/print all mana symbol tags.")
    ap.add_argument("--printer-address", default=None)
    ap.add_argument("--no-print", action="store_true")
    args = ap.parse_args()

    if not SYMBOL_DIR.exists():
        raise SystemExit(f"Missing {SYMBOL_DIR}")

    symbols = sorted(SYMBOL_DIR.glob("*.png"), key=symbol_sort_key)
    if not symbols:
        raise SystemExit("No PNG symbols found in mana_symbols/")

    pages = make_pages(symbols)
    print(f"Rendered {len(symbols)} symbols onto {len(pages)} page(s):")
    for p in pages:
        print(f"  {p}")

    if args.no_print:
        return

    for p in pages:
        print(f"Printing {p.name}...")
        print_printer(p, args.printer_address)
    print("Done.")


if __name__ == "__main__":
    main()
