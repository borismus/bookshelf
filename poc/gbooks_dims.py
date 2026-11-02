"""Fill in real book dimensions from Google Books where our current numbers are estimates.

Only touches books whose dims_source is an estimate (cover ratio, other editions, page-count guess); measured
(Open Library, this edition) and hand-set values are kept. Looks up by ISBN first, then title + author, and only
accepts a volume whose title matches. Height/width come from Google; thickness too if Google has it, otherwise
our page-count thickness stays. Needs GOOGLE_BOOKS_API_KEY in ../.env.
"""
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATH = HERE / "data/enriched.json"
ESTIMATED = ("cover ratio", "openlibrary: median", "estimate")


def load_env():
    for line in (HERE.parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def get(url, tries=5):
    sep = "&" if "?" in url else "?"
    for i in range(tries):
        try:
            with urllib.request.urlopen(url + sep + "key=" + os.environ["GOOGLE_BOOKS_API_KEY"], timeout=30) as r:
                time.sleep(0.6)                      # stay under the per-minute quota
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(15 * (i + 1))                 # rate limited: back off


def fold(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s.split(":")[0]).strip()


def cm(v):
    m = re.match(r"([\d.]+)\s*cm", v or "")
    return float(m.group(1)) * 10 if m else None


def lookup(r):
    title = r.get("display_title") or r["title"]
    want = re.sub(r"^(the|a|an) ", "", fold(title))
    surname = fold(r.get("display_author") or r.get("ol_author") or r.get("author") or "").split()
    queries = []
    if r.get("isbn13"):
        queries.append(f"isbn:{r['isbn13']}")
    if r.get("isbn10"):
        queries.append(f"isbn:{r['isbn10']}")
    queries.append(f"intitle:{title.split(':')[0]}" + (f"+inauthor:{surname[-1]}" if surname else ""))
    for q in queries:
        items = get("https://www.googleapis.com/books/v1/volumes?maxResults=5&printType=books&q=" + urllib.parse.quote(q, safe=":+")).get("items", [])
        for it in items[:3]:
            v = it.get("volumeInfo", {})
            got = re.sub(r"^(the|a|an) ", "", fold(v.get("title")))
            if not (got == want or got.startswith(want) or want.startswith(got)):
                continue
            dims = v.get("dimensions") or get(it["selfLink"]).get("volumeInfo", {}).get("dimensions")
            if dims and cm(dims.get("height")):
                return dims, q, v.get("title")
        time.sleep(0.15)
    return None, None, None


def main():
    load_env()
    shelf = json.loads((HERE / "preview/shelf.json").read_text())
    on_shelf = {b["slug"] for c in shelf["cases"] for s in c["shelves"] for b in s}
    recs = json.loads(PATH.read_text())
    todo = [r for r in recs if r["slug"] in on_shelf and r.get("dims_source", "").startswith(ESTIMATED)]
    hits = 0
    for r in todo:
        try:
            dims, q, got = lookup(r)
        except Exception as e:
            print(f"{r['slug'][:40]:40} error {e}")
            continue
        if not dims:
            continue
        h, w, t = cm(dims.get("height")), cm(dims.get("width")), cm(dims.get("thickness"))
        if not (120 <= h <= 330):
            continue
        old = r["dims_mm"]
        new = {"h": round(h), "w": round(w) if w and 70 < w < h else old["w"],
               "t": round(t, 1) if t and 2 <= t <= 120 else old["t"]}
        r["dims_mm"] = new
        r["dims_source"] = f"google books ({q})" + ("" if t else " + pages -> thickness")
        hits += 1
        print(f"{r['slug'][:40]:40} {old['h']}x{old['w']}x{old['t']} -> {new['h']}x{new['w']}x{new['t']}  [{got}]")
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(recs, indent=1, ensure_ascii=False))
    os.replace(tmp, PATH)
    print(f"{hits} of {len(todo)} estimated books now have Google Books dimensions")


if __name__ == "__main__":
    main()
