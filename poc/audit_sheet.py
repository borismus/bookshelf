"""Contact sheets for auditing spines: one row per shelved book with the expected title/author, the spine (rotated to
read left-to-right) and the front cover it was generated from. Writes data/audit/sheet_NN.jpg (12 books per sheet).
Usage: python3 audit_sheet.py [slug ...]   (default: every shelved book, in shelf order)"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "data/audit"
ROW, PER, W = 118, 12, 1500
try:
    FONT = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 17)
    SMALL = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
except OSError:
    FONT = SMALL = ImageFont.load_default()


def main():
    shelf = json.loads((HERE / "preview/shelf.json").read_text())
    books = [b for c in shelf["cases"] for s in c["shelves"] for b in s]
    if sys.argv[1:]:
        books = [b for b in books if b["slug"] in sys.argv[1:]]
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("sheet_*.jpg"):
        old.unlink()
    for k in range(0, len(books), PER):
        sheet = Image.new("RGB", (W, ROW * PER), "white")
        d = ImageDraw.Draw(sheet)
        for i, b in enumerate(books[k:k + PER]):
            y = i * ROW
            d.rectangle((0, y, W, y + ROW - 1), fill="#f4f2ee" if i % 2 else "white")
            n = k + i + 1
            d.text((8, y + 8), f"#{n}", fill="#b00", font=FONT)
            title = b["title"] + (": " + b["subtitle"] if b.get("subtitle") else "")
            words, lines, cur = title.split(), [], ""
            for w in words:
                if len(cur) + len(w) > 30:
                    lines.append(cur); cur = w
                else:
                    cur = (cur + " " + w).strip()
            lines.append(cur)
            d.multiline_text((58, y + 8), "\n".join(lines[:3]), fill="#111", font=FONT, spacing=2)
            d.text((58, y + ROW - 40), b["author"], fill="#555", font=SMALL)
            d.text((58, y + ROW - 22), f'{b["spine_source"]} · {b["binding"]} · {b["dims"]["h"]}×{b["dims"]["t"]}mm', fill="#999", font=SMALL)
            sp = Image.open(HERE / b["texture"].replace("../", "")).convert("RGB").rotate(90, expand=True)
            sw = 1020
            sh = min(ROW - 10, max(24, round(sw * sp.height / sp.width)))
            sheet.paste(sp.resize((sw, sh), Image.LANCZOS), (330, y + (ROW - sh) // 2))
            if b.get("cover"):
                cv = Image.open(HERE / b["cover"].replace("../", "")).convert("RGB")
                ch = ROW - 10
                cw = min(130, round(ch * cv.width / cv.height))
                sheet.paste(cv.resize((cw, ch), Image.LANCZOS), (W - 140, y + 5))
        sheet.save(OUT / f"sheet_{k // PER + 1:02d}.jpg", quality=88)
    print(len(books), "books ->", (len(books) + PER - 1) // PER, "sheets in", OUT)


if __name__ == "__main__":
    main()
