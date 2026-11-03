"""Gather candidate front covers for books that have none, for a human to pick from.

For every visible book without data/covers/<slug>.jpg, collect up to ~6 distinct candidates from: the smus.com post
image (even if it isn't portrait), Open Library by ISBN, Open Library search (work + edition covers) and Google Books.
Writes data/cover_candidates/<slug>/<n>.jpg + data/cover_candidates/manifest.json, and preview/covers_review.html
where you click a candidate per book and copy the resulting JSON into data/cover_picks.json.
Then: python3 bookshelf.py covers '<json>'   (copies picks into data/covers and builds those books).
"""
import hashlib
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "data/cover_candidates"
SITE = Path.home() / "Projects/smus.com/content"
UA = {"User-Agent": "bookshelf-cover-review/1.0 (+https://github.com/borismus/bookshelf)"}
MAX = 6


def load_env():
    for line in (HERE.parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def fetch(url, timeout=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def jget(url):
    b = fetch(url)
    try:
        return json.loads(b) if b else {}
    except ValueError:
        return {}


def missing():
    ex = json.loads((HERE / "data/exclude.json").read_text())
    skip = set(ex.get("slugs", [])) | set(ex.get("hidden", []))
    recs = json.loads((HERE / "data/enriched.json").read_text())
    return [r for r in recs if r["slug"] not in skip and not (HERE / f"data/covers/{r['slug']}.jpg").exists()]


def candidates(r):
    """Yield (source, url-or-path) in rough order of trust."""
    title = r.get("display_title") or r["title"]
    author = r.get("display_author") or r.get("ol_author") or r.get("author") or ""
    if r.get("cover"):
        p = SITE / r["cover"].lstrip("/")
        if p.exists():
            yield "smus.com post image", p
    for isbn in filter(None, (r.get("isbn13"), r.get("isbn10"))):
        yield f"Open Library ISBN {isbn}", f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
    q = {"title": title.split(":")[0], "limit": 5, "fields": "key,title,author_name,cover_i,edition_key"}
    if author:
        q["author"] = re.split(r" and |,|&", author)[0].strip()
    for doc in jget("https://openlibrary.org/search.json?" + urllib.parse.urlencode(q)).get("docs", [])[:4]:
        label = f"Open Library: {doc.get('title')} — {', '.join(doc.get('author_name', [])[:2])}"
        if doc.get("cover_i"):
            yield label, f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"
        for e in jget(f"https://openlibrary.org{doc['key']}/editions.json?limit=20").get("entries", []):
            for cid in (e.get("covers") or [])[:1]:
                if cid and cid > 0:
                    yield f"{label} (edition {e.get('publish_date', '?')})", f"https://covers.openlibrary.org/b/id/{cid}-L.jpg"
    gq = f"intitle:{title.split(':')[0]}" + (f"+inauthor:{author.split()[-1]}" if author else "")
    key = os.environ.get("GOOGLE_BOOKS_API_KEY")
    gurl = "https://www.googleapis.com/books/v1/volumes?maxResults=5&printType=books&q=" + urllib.parse.quote(gq, safe=":+")
    for it in jget(gurl + (f"&key={key}" if key else "")).get("items", [])[:5]:
        v = it.get("volumeInfo", {})
        if v.get("imageLinks"):
            yield (f"Google Books: {v.get('title')} — {', '.join(v.get('authors', [])[:2])}",
                   f"https://books.google.com/books/content?id={it['id']}&printsec=frontcover&img=1&zoom=0")


def main():
    load_env()
    todo = missing()
    if sys.argv[1:]:
        todo = [r for r in todo if r["slug"] in sys.argv[1:]]
    OUT.mkdir(parents=True, exist_ok=True)
    mpath = OUT / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    for r in todo:
        slug, d = r["slug"], OUT / r["slug"]
        d.mkdir(exist_ok=True)
        seen, got = set(), []
        for src, where in candidates(r):
            if len(got) >= MAX:
                break
            data = where.read_bytes() if isinstance(where, Path) else fetch(where)
            if not data:
                continue
            h = hashlib.md5(data).hexdigest()
            try:
                im = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:
                continue
            from PIL import ImageStat
            blank = max(ImageStat.Stat(im.convert("L")).stddev) < 25 and ImageStat.Stat(im.convert("L")).mean[0] > 235
            if h in seen or blank or im.width < 150 or im.height < 150:     # "image not available" / tiny / duplicate
                continue
            seen.add(h)
            n = len(got) + 1
            im.save(d / f"{n}.jpg", quality=90)
            got.append({"n": n, "file": f"{slug}/{n}.jpg", "source": src, "url": str(where) if not isinstance(where, Path) else "smus.com",
                        "size": [im.width, im.height]})
        manifest[slug] = {"title": r.get("display_title") or r["title"],
                          "author": r.get("display_author") or r.get("ol_author") or r.get("author") or "",
                          "candidates": got}
        print(f"{slug[:50]:50} {len(got)} candidates", flush=True)
    mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    write_page(manifest)


def write_page(manifest):
    e = html.escape
    rows = []
    for slug, m in manifest.items():
        cells = "".join(
            f'<label class="c"><input type="radio" name="{e(slug)}" value="{c["n"]}"><img src="../data/cover_candidates/{e(c["file"])}" loading="lazy">'
            f'<span>{c["n"]}. {e(c["source"])}<br>{c["size"][0]}×{c["size"][1]}</span></label>' for c in m["candidates"])
        cells += f'<label class="c none"><input type="radio" name="{e(slug)}" value="0"><span>None of these<br>(leave off the shelf)</span></label>'
        q = urllib.parse.quote(f'{m["title"]} {m["author"]} book cover')
        rows.append(f'<section><h2>{e(m["title"])} <small>{e(m["author"])} · <code>{e(slug)}</code> · '
                    f'<a href="https://www.google.com/search?tbm=isch&q={q}" target="_blank" rel="noopener">image search ↗</a></small></h2>'
                    f'<div class="row">{cells}</div><input class="url" data-slug="{e(slug)}" type="url" '
                    f'placeholder="…or paste an image URL for the right cover"></section>')
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cover Review</title><style>
:root {{ --bg:#f6f4ef; --fg:#24201b; --muted:#7a7268; --card:#fff; --pick:#d89a00; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1c1a17; --fg:#eee8df; --muted:#a39a8e; --card:#2a2723; }} }}
body {{ margin:0; padding:24px 16px 140px; background:var(--bg); color:var(--fg); font:14px/1.4 -apple-system, system-ui, sans-serif; }}
h1 {{ font-size:22px; margin:0 0 4px; }} p.lead {{ color:var(--muted); margin:0 0 24px; }}
section {{ margin:0 0 28px; }} h2 {{ font-size:16px; margin:0 0 8px; }} h2 small {{ color:var(--muted); font-weight:400; }}
.row {{ display:flex; gap:12px; overflow-x:auto; padding-bottom:6px; }}
.c {{ flex:0 0 auto; width:150px; background:var(--card); border-radius:8px; padding:8px; cursor:pointer; border:3px solid transparent; }}
.c:has(input:checked) {{ border-color:var(--pick); }} .c input {{ display:none; }}
.c img {{ width:100%; height:200px; object-fit:contain; display:block; background:#0001; }}
.c span {{ display:block; font-size:11px; color:var(--muted); margin-top:6px; }}
.url {{ margin-top:8px; width:min(560px,100%); box-sizing:border-box; padding:7px 9px; border-radius:6px; border:1px solid #0002; background:var(--card); color:var(--fg); font:13px system-ui; }}
.none {{ display:flex; align-items:center; text-align:center; min-height:200px; }}
#out {{ position:fixed; left:0; right:0; bottom:0; background:var(--card); padding:10px 16px; box-shadow:0 -2px 12px #0002; display:flex; gap:10px; align-items:center; }}
#out textarea {{ flex:1; height:70px; font:12px ui-monospace, monospace; background:var(--bg); color:var(--fg); border:0; border-radius:6px; padding:6px; }}
#out button {{ padding:10px 14px; border-radius:20px; border:0; background:var(--fg); color:var(--bg); font-weight:600; cursor:pointer; }}
</style></head><body>
<h1>Missing covers</h1><p class="lead">Pick the right front cover for each book (or “None”). Then copy the JSON into
<code>poc/data/cover_picks.json</code> — or just paste it to Claude.</p>
{''.join(rows)}
<div id="out"><textarea readonly></textarea><button>Copy</button></div>
<script>
const ta = document.querySelector('#out textarea');
const update = () => {{ const picks = {{}}; document.querySelectorAll('input:checked').forEach(i => picks[i.name] = +i.value);
  document.querySelectorAll('input.url').forEach(i => {{ if (i.value.trim()) picks[i.dataset.slug] = i.value.trim(); }});
  ta.value = JSON.stringify(picks); try {{ localStorage.coverPicks = ta.value; }} catch (e) {{}} }};
try {{ const saved = JSON.parse(localStorage.coverPicks || '{{}}');
  for (const [k, v] of Object.entries(saved)) {{
    if (typeof v === 'string') {{ const u = document.querySelector(`input.url[data-slug="${{CSS.escape(k)}}"]`); if (u) u.value = v; continue; }}
    const i = document.querySelector(`input[name="${{CSS.escape(k)}}"][value="${{v}}"]`); if (i) i.checked = true; }} }} catch (e) {{}}
document.addEventListener('change', update); document.addEventListener('input', update); update();
document.querySelector('#out button').onclick = () => navigator.clipboard.writeText(ta.value);
</script></body></html>"""
    (HERE / "preview/covers_review.html").write_text(page)


if __name__ == "__main__":
    main()
