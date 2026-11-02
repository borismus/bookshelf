"""Split full dust-jacket scans (data/jackets.json) into front cover, back cover and spine crop.

The original scan is kept in data/jackets/<slug>.jpg. Writes data/covers/, data/backs/ and data/crops/ + data/textures/.
"""
import json, shutil
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
SITE = Path.home() / "Projects/smus.com/content"
books = {b["slug"]: b for b in json.loads((HERE / "data/enriched.json").read_text())}
for slug, j in json.loads((HERE / "data/jackets.json").read_text()).items():
    if slug.startswith("_"):
        continue
    src = HERE / f"data/jackets/{slug}.jpg"
    if not src.exists():
        shutil.copy(SITE / books[slug]["cover"].lstrip("/"), src)
    im = Image.open(src).convert("RGB")
    w, h = im.size
    part = lambda r: im.crop((round(r[0] * w), 0, round(r[1] * w), h))
    part(j["front"]).save(HERE / f"data/covers/{slug}.jpg", quality=92)
    part(j["back"]).save(HERE / f"data/backs/{slug}.jpg", quality=92)
    sp = part(j["spine"])
    sp.save(HERE / f"data/crops/{slug}.jpg", quality=92)
    if not list((HERE / "data/ai" / slug).glob("upscale_*.png")):   # don't clobber an upscaled spine
        sp.save(HERE / f"data/textures/{slug}.jpg", quality=92)
    f = part(j["front"]).size
    print(f"{slug}: front {f} (w/h {f[0]/f[1]:.2f}), spine {sp.size} -> thickness ≈ {sp.size[0]/h*books[slug]['dims_mm']['h']:.0f} mm")
