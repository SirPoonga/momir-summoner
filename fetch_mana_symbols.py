#!/usr/bin/env python3
"""Create/cache mana symbol PNG images for the Momir printer renderer.

This uses locally generated, Magic-style symbol images. They are simple
readable printer symbols, not official Wizards of the Coast assets.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "mana_symbols"
OUT.mkdir(exist_ok=True)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SIZE = 72

COLORS = {
    "W": ((246, 238, 208), "black"),
    "U": ((170, 210, 235), "black"),
    "B": ((35, 35, 35), "white"),
    "R": ((230, 120, 85), "black"),
    "G": ((120, 175, 120), "black"),
    "C": ((220, 220, 220), "black"),
    "S": ((230, 245, 255), "black"),
    "X": ((230, 230, 230), "black"),
    "T": ((230, 230, 230), "black"),
    "Q": ((230, 230, 230), "black"),
}

HYBRID = ["WU", "WB", "UB", "UR", "BR", "BG", "RG", "RW", "GW", "GU"]
PHYREXIAN = ["WP", "UP", "BP", "RP", "GP"]
NUMBERS = [str(i) for i in range(0, 21)]
EXTRA = ["HW", "HR", "2W", "2U", "2B", "2R", "2G", "P"]


def fit_font(draw, text, max_w, max_h):
    for size in range(42, 12, -2):
        font = ImageFont.truetype(FONT_BOLD, size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_w and box[3] - box[1] <= max_h:
            return font
    return ImageFont.truetype(FONT_BOLD, 16)


def make_symbol(code: str):
    code = code.upper().replace("/", "")
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    bg, fg = COLORS.get(code, ((230, 230, 230), "black"))

    if code in HYBRID and len(code) == 2:
        c1, _ = COLORS.get(code[0], ((230, 230, 230), "black"))
        c2, _ = COLORS.get(code[1], ((230, 230, 230), "black"))
        d.pieslice((3, 3, SIZE-4, SIZE-4), 90, 270, fill=c1)
        d.pieslice((3, 3, SIZE-4, SIZE-4), -90, 90, fill=c2)
        fg = "black"
    elif code in PHYREXIAN:
        c1, _ = COLORS.get(code[0], ((230, 230, 230), "black"))
        d.ellipse((3, 3, SIZE-4, SIZE-4), fill=c1)
        code = code[0] + "Φ"
        fg = "black"
    elif code.startswith("2") and len(code) == 2:
        c1 = (230, 230, 230)
        c2, _ = COLORS.get(code[1], ((230, 230, 230), "black"))
        d.pieslice((3, 3, SIZE-4, SIZE-4), 90, 270, fill=c1)
        d.pieslice((3, 3, SIZE-4, SIZE-4), -90, 90, fill=c2)
        fg = "black"
    else:
        d.ellipse((3, 3, SIZE-4, SIZE-4), fill=bg)

    d.ellipse((3, 3, SIZE-4, SIZE-4), outline="black", width=4)

    label = code
    if code == "T":
        label = "↷"
    elif code == "Q":
        label = "↶"
    elif code == "S":
        label = "✶"
    elif code == "C":
        label = "◇"
    elif code == "P":
        label = "Φ"

    font = fit_font(d, label, SIZE - 16, SIZE - 16)
    box = d.textbbox((0, 0), label, font=font)
    x = (SIZE - (box[2] - box[0])) // 2 - box[0]
    y = (SIZE - (box[3] - box[1])) // 2 - box[1] - 1
    d.text((x, y), label, fill=fg, font=font)

    out = OUT / f"{code}.png"
    img.save(out)


def main():
    codes = sorted(set(NUMBERS + list(COLORS.keys()) + HYBRID + PHYREXIAN + EXTRA))
    for code in codes:
        make_symbol(code)
    print(f"Created {len(codes)} mana symbol PNGs in {OUT}")

if __name__ == "__main__":
    main()
