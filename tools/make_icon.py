"""Draw the app icon (teal tile, white drop) into build/padreset.ico."""

from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (14, 110, 102, 255)
OUT = Path(__file__).resolve().parent.parent / "build" / "padreset.ico"


def draw(size=256):
    s = size / 24  # the UI icon is drawn on a 24-unit grid
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=ACCENT)
    # Drop: circle bottom (centre 12,14.5 r 5.6) plus a triangle to the tip at (12, 4.2).
    cx, cy, r = 12 * s, 14.6 * s, 5.6 * s
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="white")
    d.polygon([(12 * s, 4.0 * s), (cx - r * 0.93, cy - r * 0.37), (cx + r * 0.93, cy - r * 0.37)], fill="white")
    # Highlight arc like the UI glyph.
    w = max(2, int(1.6 * s))
    d.arc((cx - r * 0.62, cy - r * 0.62, cx + r * 0.62, cy + r * 0.62), 95, 175, fill=ACCENT, width=w)
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    draw().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(OUT)
