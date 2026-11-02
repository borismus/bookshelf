"""Copy/fetch a front cover per sample book into data/covers/<slug>.jpg (smus.com first, else Open Library)."""
import json, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent
SITE = Path.home() / "Projects/smus.com/content"
out = HERE / "data/covers"; out.mkdir(exist_ok=True)
from PIL import Image
jackets = {k for k in json.loads((HERE / "data/jackets.json").read_text()) if not k.startswith("_")}

def front_like(path):
    """A real front cover is portrait (w/h ~0.6-0.75). Square crops and jacket spreads are not."""
    w, h = Image.open(path).size
    return 0.55 <= w / h <= 0.8

for b in json.loads((HERE / "data/enriched.json").read_text()):
    dst = out / f"{b['slug']}.jpg"
    src = None
    if b["slug"] in jackets:
        print(f"{b['slug'][:42]:42} jacket (split_jackets.py)"); continue
    smus = SITE / b["cover"].lstrip("/") if b.get("cover") else None
    if smus and smus.exists() and front_like(smus):
        dst.write_bytes((SITE / b["cover"].lstrip("/")).read_bytes()); src = "smus.com"
    elif b.get("ol_cover_id"):
        url = f"https://covers.openlibrary.org/b/id/{b['ol_cover_id']}-L.jpg"
        try:
            dst.write_bytes(urllib.request.urlopen(url, timeout=30).read()); src = "openlibrary"
        except Exception as e:
            src = f"FAILED {e}"
    print(f"{b['slug'][:42]:42} {src or 'NONE'}")
