"""Collect candidate spine images from Bing image search and build a contact sheet per book.

Usage: uv run --with pillow spine_search.py [slug ...]
Output: data/spines/<slug>/candidates.json, cand_NN.jpg, sheet.jpg
"""
import html
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
N = 12


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def bing_images(query):
    url = "https://www.bing.com/images/search?" + urllib.parse.urlencode({"q": query, "form": "HDRSC2", "first": 1})
    page = fetch(url).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'\sm="(\{[^"]+\})"', page):
        try:
            d = json.loads(html.unescape(m.group(1)))
        except json.JSONDecodeError:
            continue
        if "murl" in d:
            out.append({"url": d["murl"], "thumb": d.get("turl"), "title": d.get("t", ""), "page": d.get("purl", "")})
    return out


def main():
    books = {b["slug"]: b for b in json.load(open(HERE / "data/enriched.json"))}
    slugs = sys.argv[1:] or list(books)
    for slug in slugs:
        b = books[slug]
        author = b.get("ol_author") or b.get("author") or ""
        title = b.get("ol_title") or b["title"]
        q = f"{title} {author} book spine"
        d = HERE / "data/spines" / slug
        d.mkdir(parents=True, exist_ok=True)
        try:
            cands = bing_images(q)[:N]
        except Exception as e:
            print(f"{slug}: search failed {e!r}")
            continue
        thumbs = []
        for i, c in enumerate(cands):
            img = None
            for src in (c["url"], c["thumb"]):  # full image first; thumbnail if the host blocks us
                if not src:
                    continue
                try:
                    img = Image.open(io.BytesIO(fetch(src, 15))).convert("RGB")
                    c["fetched"] = "full" if src == c["url"] else "thumb"
                    break
                except Exception:
                    continue
            if img is None:
                c["fetched"] = None
                continue
            c["size"] = img.size
            c["file"] = f"cand_{i:02}.jpg"
            img.save(d / c["file"], quality=88)
            thumbs.append((i, img))
        (d / "candidates.json").write_text(json.dumps({"query": q, "candidates": cands}, indent=1))

        # contact sheet: 6 x 2 cells, 220 x 300 each, labelled with index + pixel size
        cw, ch = 220, 300
        sheet = Image.new("RGB", (cw * 6, ch * 2), "white")
        draw = ImageDraw.Draw(sheet)
        for k, (i, img) in enumerate(thumbs[:12]):
            t = img.copy()
            t.thumbnail((cw - 10, ch - 30))
            x, y = (k % 6) * cw, (k // 6) * ch
            sheet.paste(t, (x + 5, y + 5))
            draw.text((x + 6, y + ch - 22), f"#{i}  {img.size[0]}x{img.size[1]}", fill="black")
        sheet.save(d / "sheet.jpg", quality=80)
        print(f"{slug}: {len(thumbs)}/{len(cands)} candidates  [{q}]")
        time.sleep(1.0)


if __name__ == "__main__":
    main()
