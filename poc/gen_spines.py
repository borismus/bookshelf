"""Generate spine textures from front covers with Gemini Flash Image.

Usage: uv run --with pillow --with numpy gen_spines.py [--retrim] [slug ...]   (default: sample books without a picked real spine)
Needs GEMINI_API_KEY in ../.env. Writes data/ai/<slug>/raw_N.png and data/textures/<slug>.jpg (trimmed).
"""
import base64
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
MODEL = "gemini-3.1-flash-image"
SITE = Path.home() / "Projects/smus.com/content"
BG = (128, 128, 128)


def load_env():
    for line in (HERE.parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def cover_bytes(b):
    local = HERE / f"data/covers/{b['slug']}.jpg"   # cleaned-up front cover (jacket splits, square crops replaced)
    if local.exists():
        return local.read_bytes(), "data/covers"
    if b.get("cover"):
        p = SITE / b["cover"].lstrip("/")
        if p.exists():
            return p.read_bytes(), "smus.com"
    if b.get("ol_cover_id"):
        url = f"https://covers.openlibrary.org/b/id/{b['ol_cover_id']}-L.jpg"
        return urllib.request.urlopen(url, timeout=30).read(), "openlibrary"
    return None, None


def is_latin(x):
    return bool(x) and all(ord(c) < 0x250 for c in x if c.isalpha())


def names(b):
    """Title/author to print on the spine. Title: smus.com's English title. Author: Open Library's name if it's in
    Latin script (OL often stores original-language names), else smus.com's. Two authors only when smus.com lists
    co-authors ("Pratchett and Gaiman"): OL's author lists also contain translators, narrators and illustrators."""
    if b.get("display_title"):
        b = dict(b, title=b["display_title"])
    if b.get("display_author"):
        return b["title"], b["display_author"]
    smus = b.get("author") or ""
    if " and " in smus or "&" in smus:
        seen, out = set(), []
        for n in b.get("ol_authors") or []:
            if is_latin(n) and n.split()[-1] not in seen:
                seen.add(n.split()[-1]); out.append(n)
        if len(out) >= 2:
            return b["title"], " & ".join(out[:2])
    author = b.get("ol_author") if is_latin(b.get("ol_author")) else smus
    return b["title"], author


def prompt(b):
    d = b["dims_mm"]
    title, author = names(b)
    return f"""The attached image is the front cover of the book "{title}" by {author}{f" (publisher: {b['publisher']})" if b.get('publisher') else ""}.

Create a photograph of this exact edition's SPINE ONLY.
- Shot perfectly straight-on (orthographic, no perspective, no visible front or back cover), the book standing upright.
- The spine is a {"broad (it is a thick book)" if d['h']/d['t'] < 5 else "tall, narrow"} strip exactly {d['h']/d['t']:.1f} times taller than it is wide. Centre it and let it fill almost the full image height.
- Background: perfectly flat, uniform mid grey (RGB 128,128,128), no shadow, no other objects.
- Design: continue the cover's colours, typefaces, artwork and style as the real publisher would.
- Text runs top-to-bottom (rotated 90 degrees clockwise) and must read exactly: "{title}" and "{author}", with the publisher's name or logo set horizontally at the foot. Spell every word exactly; add no other text (no measurements, labels or notes)."""


THIN = 11   # spines thinner than 1:THIN are generated lying horizontally (see prompt_horizontal)


def prompt_horizontal(b):
    """Thin spines: image models draw tall narrow columns far too wide, but they draw a long thin horizontal band
    with one line of left-to-right text well. We generate the band and rotate it upright afterwards."""
    d = b["dims_mm"]
    title, author = names(b)
    return f"""The attached image is the front cover of the book "{title}" by {author}{f" (publisher: {b['publisher']})" if b.get('publisher') else ""}.

Create a flat, straight-on scan of this exact edition's SPINE, laid HORIZONTALLY: one long, very thin band running
across the full width of the image, about {d['h']/d['t']:.0f} times wider than it is tall (it is a thin book).
- Background: perfectly flat, uniform mid grey (RGB 128,128,128) above and below the band, no shadow, no other objects.
- Design: continue the cover's colours, typefaces and style as the real publisher would.
- Text reads left to right in ONE line along the band: "{title}" then "{author}", with a small publisher logo at the right end.
  Keep the lettering small enough to fit inside the band's height. Spell every word exactly; add no other text."""


def fat(b):
    d = b["dims_mm"]
    return d["h"] / d["t"] < 5


def horizontal(b):
    if b.get("_mode"):
        return b["_mode"] == "horizontal"
    d = b["dims_mm"]
    return d["h"] / d["t"] > THIN


def generate(b, img_bytes):
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img_bytes).decode()}},
            {"text": prompt_horizontal(b) if horizontal(b) else prompt(b)},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "21:9" if horizontal(b) else ("3:4" if fat(b) else "9:16")}},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]},
    )
    resp = json.load(urllib.request.urlopen(req, timeout=180))
    for part in resp["candidates"][0]["content"]["parts"]:
        data = part.get("inlineData") or part.get("inline_data")
        if data:
            im = Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")
            return im.rotate(-90, expand=True) if horizontal(b) else im   # band's left end becomes the spine's top
    raise RuntimeError(f"no image in response: {json.dumps(resp)[:300]}")


def _longest_run(mask):
    """(start, end) of the longest run of True values, bridging gaps of up to 3 entries."""
    best, start, gap = (0, 0), None, 0
    for i, v in enumerate(list(mask) + [False] * 4):
        if v:
            if start is None:
                start = i
            gap, end = 0, i + 1
            if end - start > best[1] - best[0]:
                best = (start, end)
        elif start is not None:
            gap += 1
            if gap > 3:
                start, gap = None, 0
    return best


def trim(im):
    """Crop a generated spine out of its flat grey background.

    A column is spine if most of its pixels differ clearly from the image's left/right margins (same row); a row is
    spine if most of its pixels (within those columns) differ from the image's top/bottom margins (same column).
    Fractions of pixels are robust to lettering, soft or light edges, vignettes and the shadow under the book.
    Then crop slightly inside: models draw rounded spine ends whose corners would show background."""
    import numpy as np
    a = np.asarray(im).astype(np.float32)
    h, w, _ = a.shape
    side_bg = (a[:, :12].mean(axis=1) + a[:, -12:].mean(axis=1)) / 2                 # per row
    col_frac = (np.abs(a - side_bg[:, None, :]).sum(axis=2) > 40).mean(axis=0)
    x0, x1 = _longest_run(col_frac > 0.5)
    if x1 - x0 < 8:
        return im
    # Second pass against the background just outside the run: vignettes make the background near the spine
    # brighter (or shadowed darker) than the image margins, which the first pass counts as spine.
    for _ in range(2):
        l0, l1 = max(0, x0 - 24), max(1, x0 - 8)
        r0, r1 = min(w - 1, x1 + 8), min(w, x1 + 24)
        local = (a[:, l0:l1].mean(axis=1) + a[:, r0:r1].mean(axis=1)) / 2
        lo, hi = max(0, x0 - 4), min(w, x1 + 4)
        frac = (np.abs(a[:, lo:hi] - local[:, None, :]).sum(axis=2) > 60).mean(axis=0)
        n0, n1 = _longest_run(frac > 0.5)
        if n1 - n0 < 8:
            break
        x0, x1 = lo + n0, lo + n1
    cols = a[:, x0:x1]
    top_bg, bot_bg = a[:10, x0:x1].mean(axis=0), a[-10:, x0:x1].mean(axis=0)       # per column
    d = np.minimum(np.abs(cols - top_bg).sum(axis=2), np.abs(cols - bot_bg).sum(axis=2))
    # A row is spine if most of it differs from the background, or if it has texture at all: the generated background
    # is perfectly flat (row std < 1), so spine areas whose colour happens to match the grey are still caught.
    texture = cols.std(axis=1).mean(axis=1)
    core = (d > 40).mean(axis=1) > 0.5
    y0, y1 = _longest_run(core | (texture > 6))
    while y1 - y0 > 8 and not core[y0]:          # ends must clearly differ from the background (not a soft shadow)
        y0 += 1
    while y1 - y0 > 8 and not core[y1 - 1]:
        y1 -= 1
    if y1 - y0 < 8:
        return im
    px = max(2, round((x1 - x0) * 0.03)); py = max(2, round((y1 - y0) * 0.01))
    return im.crop((x0 + px, y0 + py, x1 - px, y1 - py))


def pad_fat(sp, target):
    """Fat books: models draw the spine too narrow. Widen it by extending its own artwork: behind the sharp spine
    goes a horizontally stretched, blurred copy (same colours and texture, no readable detail), feathered in."""
    from PIL import ImageFilter
    want_w = round(sp.height / (target * 1.1))
    if want_w <= sp.width:
        return sp
    bg = sp.resize((want_w, sp.height), Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=max(6, want_w // 18)))
    mask = Image.new("L", sp.size, 255)
    feather = max(3, sp.width // 14)
    px = mask.load()
    for x in range(feather):
        v = int(255 * (x + 1) / (feather + 1))
        for y in range(sp.height):
            px[x, y] = min(px[x, y], v); px[sp.width - 1 - x, y] = min(px[sp.width - 1 - x, y], v)
    bg.paste(sp, ((want_w - sp.width) // 2, 0), mask)
    return bg


def check(sp, raw, target):
    """Reject crops that can't be a spine: the model sometimes ignores the grey background or draws the band at
    the image edge, and the crop then keeps the whole image or a sliver."""
    r = sp.height / sp.width
    if sp.width * sp.height > 0.6 * raw.width * raw.height:
        return "crop kept most of the image"
    if sp.height < 0.6 * raw.height:
        return f"too short ({sp.height}px of {raw.height})"
    if r < 3:
        return f"too wide (h/w {r:.1f})"
    if r > target * 1.6:
        return f"too thin (h/w {r:.1f}, target {target:.1f})"
    return None


def main():
    load_env()
    books = {b["slug"]: b for b in json.loads((HERE / "data/enriched.json").read_text())}
    picked = {k for k in json.loads((HERE / "data/spine_picks.json").read_text()) if not k.startswith("_")}
    slugs = [a for a in sys.argv[1:] if not a.startswith("--")] or [s for s in books if s not in picked]
    (HERE / "data/textures").mkdir(exist_ok=True)
    for s in slugs:
        b = books[s]
        img, src = cover_bytes(b)
        if not img:
            print(f"{s}: no cover, skipped")
            continue
        out = HERE / "data/ai" / s
        out.mkdir(parents=True, exist_ok=True)
        existing = sorted(out.glob("raw_*.png"))
        if "--retrim" in sys.argv and existing:
            sp = trim(Image.open(existing[-1]).convert("RGB"))
            sp.save(HERE / "data/textures" / f"{s}.jpg", quality=92)
            print(f"{s}: retrimmed -> {sp.size} (h/w {sp.size[1]/sp.size[0]:.1f})")
            continue
        # Try horizontal mode for thin books (twice), then the vertical mode; keep the first result that passes.
        if not b.get("dims_mm"):
            print(f"{s}: no dimensions (Open Library lookup failed?); skipped")
            continue
        target = b["dims_mm"]["h"] / b["dims_mm"]["t"]
        modes = (["horizontal"] * 2 if target > THIN else []) + ["vertical"] * 2
        sp = raw = None
        for mode in modes:
            try:
                raw = generate(dict(b, _mode=mode), img)
            except Exception as e:
                print(f"{s}: {mode} attempt failed {e!r}")
                continue
            n = len(list(out.glob("raw_*.png")))
            raw.save(out / f"raw_{n}.png")
            cand = trim(raw)
            problem = check(cand, raw, target)
            # (thick books are generated on a squarer canvas instead of being widened afterwards)
            if not problem:
                sp = cand
                break
            print(f"{s}: rejected {mode} result ({problem})")
        if sp is None:
            print(f"{s}: FAILED all attempts; keeping previous texture")
            continue
        sp.save(HERE / "data/textures" / f"{s}.jpg", quality=92)
        print(f"{s}: cover from {src}; raw {raw.size} -> spine {sp.size} (h/w {sp.size[1]/sp.size[0]:.1f}, target {b['dims_mm']['h']/b['dims_mm']['t']:.1f})")


if __name__ == "__main__":
    main()
