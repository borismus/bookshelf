"""All spine textures side by side at a common height, labelled real/AI."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
picks = json.loads((HERE / "data/spine_picks.json").read_text())
slugs = (HERE / "sample.txt").read_text().split()
H = 900
tiles = []
for s in slugs:
    im = Image.open(HERE / f"data/textures/{s}.jpg")
    im = im.resize((max(1, round(im.width * H / im.height)), H))
    tiles.append((s, im, "real" if s in picks else "AI"))
W = sum(t[1].width + 16 for t in tiles) + 16
sheet = Image.new("RGB", (W, H + 60), (235, 232, 226))
d = ImageDraw.Draw(sheet)
x = 16
for i, (s, im, kind) in enumerate(tiles):
    sheet.paste(im, (x, 16))
    d.text((x, H + 24), f"{i+1} {kind}", fill=(30, 30, 30))
    x += im.width + 16
sheet.save(HERE / "data/textures_sheet.jpg", quality=85)
print(sheet.size)
