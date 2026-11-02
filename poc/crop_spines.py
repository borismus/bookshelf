"""Apply data/spine_picks.json: crop each chosen candidate into data/textures/<slug>.jpg."""
import json
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
picks = json.loads((HERE / "data/spine_picks.json").read_text())
out = HERE / "data/textures"
out.mkdir(exist_ok=True)
crops = HERE / "data/crops"
crops.mkdir(exist_ok=True)
for slug, p in picks.items():
    if slug.startswith("_"):
        continue
    im = Image.open(HERE / f"data/spines/{slug}/cand_{p['cand']:02}.jpg").convert("RGB")
    w, h = im.size
    x0, y0, x1, y1 = p["box"]
    im = im.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))
    if p.get("rotate"):
        im = im.rotate(p["rotate"], expand=True)
    im.save(crops / f"{slug}.jpg", quality=92)   # untouched crop, input for upscale_spines.py
    im.save(out / f"{slug}.jpg", quality=92)
    print(f"{slug}: {im.size[0]}x{im.size[1]}  aspect h/w={im.size[1]/im.size[0]:.1f}")
