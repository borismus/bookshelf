"""Replace estimated book dimensions with better ones, without touching measured or hand-set values.

For each book whose dims_source starts with "estimate":
  1. Other editions on Open Library: median height/width of English editions (same binding class if possible)
     that list physical_dimensions.
  2. Cover proportions: our front cover's width/height ratio is exact for the edition we show, so it picks the
     standard trim size (5x8, 5.5x8.5, 6x9 in, hardcover ~6.1x9.25 in) and gives the width once height is known.
  3. Otherwise a small deterministic variation (+-4 mm) so unknown books stop looking identical.
Thickness stays page-count based. Writes data/enriched.json atomically (generators may be reading it).
"""
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

from PIL import Image

import enrich

HERE = Path(__file__).resolve().parent
PATH = HERE / "data/enriched.json"

# Common trim sizes (height mm, width/height) by binding class.
TRIMS = {
    "paperback": [(203, 0.625), (198, 0.652), (216, 0.647), (229, 0.664)],
    "hardcover": [(235, 0.664), (241, 0.655), (222, 0.66)],
    "mass": [(175, 0.606), (178, 0.62)],
}


def wiggle(slug, amp):
    """Deterministic value in [-amp, amp] per book."""
    return (int(hashlib.md5(slug.encode()).hexdigest()[:6], 16) / 0xFFFFFF * 2 - 1) * amp


def cover_ratio(slug):
    p = HERE / f"data/covers/{slug}.jpg"
    if not p.exists():
        return None
    w, h = Image.open(p).size
    r = w / h
    return r if 0.55 <= r <= 0.8 else None


def from_editions(work, cls):
    try:
        eds = enrich.get(f"https://openlibrary.org{work}/editions.json?limit=100").get("entries", [])
    except Exception:
        return None
    dims = []
    for e in eds:
        langs = [l.get("key") for l in e.get("languages", [])]
        if langs and "/languages/eng" not in langs:
            continue
        d = enrich.parse_dims(e.get("physical_dimensions"))
        if not d or len(d) < 2:
            continue
        fmt = enrich.binding_class(e.get("physical_format"), None, d[0])
        dims.append((fmt == cls, d[0], d[1]))
    if not dims:
        return None
    same = [x for x in dims if x[0]] or dims
    return statistics.median(x[1] for x in same), statistics.median(x[2] for x in same), len(same)


def main():
    recs = json.loads(PATH.read_text())
    counts = {"editions": 0, "cover": 0, "wiggle": 0}
    for r in recs:
        src = r.get("dims_source", "")
        if "dims_mm" not in r or not src.startswith("estimate"):
            continue
        cls = r.get("binding_class") or "paperback"
        t = r["dims_mm"]["t"]
        ratio = cover_ratio(r["slug"])
        got = from_editions(r["ol_work"], cls) if r.get("ol_work") else None
        time.sleep(0.25)
        if got:
            h, w, n = got
            if ratio:
                w = h * ratio
            r["dims_mm"] = {"h": round(h), "w": round(w), "t": t}
            r["dims_source"] = f"openlibrary: median of {n} other edition(s)" + (" + cover ratio" if ratio else "") + "; pages -> thickness"
            counts["editions"] += 1
        elif ratio:
            h, _ = min(TRIMS.get(cls, TRIMS["paperback"]), key=lambda tr: abs(tr[1] - ratio))
            h += wiggle(r["slug"], 3)
            r["dims_mm"] = {"h": round(h), "w": round(h * ratio), "t": t}
            r["dims_source"] = f"cover ratio {ratio:.3f} -> {cls} trim size; pages -> thickness"
            counts["cover"] += 1
        else:
            h = r["dims_mm"]["h"] + wiggle(r["slug"], 4)
            r["dims_mm"] = {"h": round(h), "w": round(h * 0.66), "t": t}
            r["dims_source"] = src + " + small variation"
            counts["wiggle"] += 1
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(recs, indent=1, ensure_ascii=False))
    os.replace(tmp, PATH)
    print(counts)
    hs = [r["dims_mm"]["h"] for r in recs if "dims_mm" in r]
    print("heights now:", sorted(set(hs))[:40], f"... {len(set(hs))} distinct")


if __name__ == "__main__":
    main()
