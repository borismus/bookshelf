"""Generate the side panels of the Lego set boxes on the low Billy with Gemini, from each box's front art.

For each set in preview/props/lego/manifest.json writes preview/props/lego/<set>_top.jpg (the long top panel,
width x depth) and <set>_end.jpg (the short end panel, height x depth), both flat and straight-on.
Usage: uv run --with pillow --with numpy gen_box_sides.py [set ...] [--force]
"""
import base64
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
DIR = HERE / "preview/props/lego"
MODEL = "gemini-3.1-flash-image"


def load_env():
    for line in (HERE.parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def gemini(img_bytes, text):
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img_bytes).decode()}},
                                    {"text": text}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "21:9"}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    resp = json.load(urllib.request.urlopen(req, timeout=180))
    for part in resp["candidates"][0]["content"]["parts"]:
        data = part.get("inlineData") or part.get("inline_data")
        if data:
            return Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")
    raise RuntimeError("no image in response")


def trim(im, ratio):
    """Crop to the panel. The backdrop is whatever colour the corners are (white, or a light grey with a shadow), so
    'ink' is distance from that. Rejects strips that touch the image edge (cut off) or have the wrong proportions."""
    a = np.asarray(im).astype(int)
    H, W = a.shape[:2]
    corners = np.concatenate([a[:6, :6].reshape(-1, 3), a[:6, -6:].reshape(-1, 3), a[-6:, :6].reshape(-1, 3), a[-6:, -6:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    ink = np.abs(a - bg).max(axis=2) > 45
    rows = np.where(ink.mean(axis=1) > 0.6)[0]
    if len(rows) < 10:
        return None, "no panel"
    # the longest run of panel rows (a soft shadow under the strip is a separate, fainter band)
    runs, start = [], rows[0]
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i] != rows[i - 1] + 1:
            runs.append((start, rows[i - 1])); start = rows[i] if i < len(rows) else None
    y0, y1 = max(runs, key=lambda r: r[1] - r[0])
    cols = np.where(ink[y0:y1 + 1].mean(axis=0) > 0.6)[0]
    if cols[0] <= 3 or cols[-1] >= W - 4:
        return None, "touches the image edge"
    crop = im.crop((cols[0] + 2, y0 + 2, cols[-1] - 1, y1 - 1))
    got = crop.width / crop.height
    if not (ratio * 0.6 < got < ratio * 1.6):
        return None, f"proportions {got:.1f} vs {ratio:.1f}"
    return crop, None


PROMPT = """This is the front of the box of LEGO set {set} "{name}" ({year_hint}LEGO SYSTEM Space). The real box is
{w} cm wide, {h} cm tall and {d} cm deep.

Draw the box's {which} panel ({pw} x {pd} cm, a long thin strip about {ratio:.1f} times longer than it is tall) as a
flat, perfectly straight-on scan: no perspective, no shadows, no box edges or other faces, evenly lit printed cardboard.
Lay it horizontally, centred, on a plain pure-white background with a clear white margin on all four sides (the
whole strip must be visible, nothing cut off at the image edges).

Design it the way LEGO printed these panels in the early 1990s, in the same graphic style and colours as the front:
the same background (starfield / neon grid / landscape), the red LEGO logo with "SYSTEM", the set number {set},
and a small picture of the model or a minifigure. Text must be crisp and correctly spelled. Do not invent other text."""


def main():
    load_env()
    sets = json.loads((DIR / "manifest.json").read_text())
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    for s in sets:
        if only and s["set"] not in only:
            continue
        w, h, d = (round(v / 10, 1) for v in s["dims"])
        front = (DIR / f"{s['set']}.jpg").read_bytes()
        for which, pw, pd in (("top", w, d), ("end", h, d)):
            out = DIR / f"{s['set']}_{which}.jpg"
            if out.exists() and "--force" not in sys.argv:
                continue
            im = None
            for attempt in range(4):
                text = PROMPT.format(set=s["set"], name=s["name"], year_hint=f"{s['year']} " if s.get("year") else "",
                                     w=w, h=h, d=d, which="top" if which == "top" else "short end (side)",
                                     pw=pw, pd=pd, ratio=pw / pd)
                im, why = trim(gemini(front, text), pw / pd)
                if im is not None:
                    break
                print(f"  {s['set']} {which}: rejected ({why}), retrying")
            if im is None:
                print(f"{s['set']} {which}: FAILED"); continue
            im = im.resize((1024, max(64, round(1024 * pd / pw))), Image.LANCZOS)   # exact panel proportions
            im.save(out, quality=86)
            print(f"{s['set']} {which}: {im.size}")


if __name__ == "__main__":
    main()
