"""Bake each book's spine, front and back cover into compressed per-book atlas textures for the viewer.

Two tiers, same layout as preview/index.html (REG): cover | back | spine side by side, and a bottom band the page
fills in itself with the page-edge texture and a plain colour.
  lo   256x512   loaded for every book up front
  card 768x1536  loaded when a book's card opens
Outputs preview/atlas/<tier>/<slug>.webp. Incremental: an atlas is rebuilt only when a source image is newer.
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "preview/atlas"
REG = {"cover": (0, 0, 0.42, 0.9), "back": (0.42, 0, 0.66, 0.9), "spine": (0.66, 0, 1, 0.9)}
TIERS = {"lo": ((256, 512), 74), "card": ((768, 1536), 80)}
_cache = {}


def _img(path):
    if path not in _cache:
        _cache[path] = Image.open(path).convert("RGB")
    return _cache[path]


def edge_colour(spine_path):
    """Average colour of the spine's left column (where it meets the cover): used for board edges and backs."""
    im = _img(spine_path).resize((8, 64), Image.BILINEAR)
    px = [im.getpixel((0, y)) for y in range(64)]
    r, g, b = (round(sum(p[i] for p in px) / len(px)) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def hue_key(spine_path):
    """Sort key for the colour joke: hue of the clearly coloured pixels (circular mean) in [0, 1), reds first;
    spines that are mostly white/cream/grey/black get 1 + (1 - lightness), so neutrals go last, lightest first."""
    import colorsys, math
    im = _img(spine_path).resize((8, 64), Image.BILINEAR)
    sx = sy = n = light = 0.0
    for r, g, b in im.getdata():
        h, l, s_ = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        light += l
        if max(r, g, b) - min(r, g, b) < 64:
            continue
        sx += math.cos(2 * math.pi * h); sy += math.sin(2 * math.pi * h); n += 1
    total = 8 * 64
    if n < total * 0.25:
        return round(2 - light / total, 4)
    return round(((math.degrees(math.atan2(sy, sx)) + 360 + 15) % 360) / 360, 4)


def build(slug, spine, cover=None, back=None):
    """Make (or reuse) the three atlas tiers for one book. Returns {'lo','hi','card'} relative URLs and 'edge'."""
    sources = {"spine": spine, "cover": cover, "back": back}
    srcs = [Path(p) for p in sources.values() if p]
    newest = max(p.stat().st_mtime for p in srcs)
    edge = edge_colour(spine)
    urls = {}
    for tier, ((W, H), q) in TIERS.items():
        dst = OUT / tier / f"{slug}.webp"
        urls[tier] = f"atlas/{tier}/{slug}.webp"
        if dst.exists() and dst.stat().st_mtime >= newest:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (W, H), edge)
        for key, path in sources.items():
            if not path:
                continue                                  # region stays the plain edge colour
            x0, y0, x1, y1 = REG[key]
            box = (round(x0 * W), round(y0 * H), round(x1 * W), round(y1 * H))
            im.paste(_img(path).resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS), box[:2])
        im.save(dst, "WEBP", quality=q, method=6)
    urls["edge"] = edge
    urls["hue"] = hue_key(spine)
    return urls


if __name__ == "__main__":
    import json
    shelf = json.loads((HERE / "preview/shelf.json").read_text())
    n = 0
    for c in shelf["cases"]:
        for s in c["shelves"]:
            for b in s:
                build(b["slug"], *(str(HERE / b[k].replace("../", "")) if b.get(k) else None for k in ("texture", "cover", "back")))
                n += 1
    sizes = {t: sum(p.stat().st_size for p in (OUT / t).glob("*.webp")) / 1e6 for t in TIERS}
    print(n, "books;", {t: f"{v:.1f} MB" for t, v in sizes.items()})
