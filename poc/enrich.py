"""Look up ISBN, page count and physical dimensions on Open Library for books in a sample.

Writes poc/data/enriched.json: one record per slug with dims in mm and where each came from.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "smus-bookshelf-poc/0.1 (boris@smus.com)"}

# Height defaults by binding (mm) and paper caliper (mm per page = per leaf / 2).
HEIGHT = {"mass": 175, "paperback": 210, "hardcover": 240}
CALIPER = {"mass": 0.055, "paperback": 0.06, "hardcover": 0.07}
BOARD = {"mass": 1.0, "paperback": 1.0, "hardcover": 5.0}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def parse_dims(s):
    """'21 x 13.5 x 2.5 centimeters' / '8.2 x 5.4 x 1 inches' -> sorted mm triple (h, w, t)."""
    if not s:
        return None
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", s)]
    if len(nums) < 2:
        return None
    unit = 25.4 if re.search(r"inch|in\b|\"", s, re.I) else 10 if re.search(r"cm|centim", s, re.I) else 1
    mm = sorted((n * unit for n in nums[:3]), reverse=True)
    if mm[0] < 80 or mm[0] > 450:  # nonsense
        return None
    return mm


def _fold(x):
    import unicodedata
    x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", x).strip()


def search(title, author):
    """Best Open Library work + edition for title + author.

    Open Library files translations under the original title (Un verdor terrible, Всё течёт…), so we match
    on the EDITION a full-text query returns, not just the work title. Candidates must match the author's
    surname (accents ignored; works whose authors are only in non-Latin script are allowed at a penalty).
    Exact title > prefix > substring (rules out 'Summary of ...' and box sets as long as a real match exists)."""
    fields = ("key,title,author_name,number_of_pages_median,first_publish_year,cover_i,edition_count,"
              "editions,editions.key,editions.title,editions.language,editions.cover_i")
    first = author.split("&")[0].split(" and ")[0].strip() if author else ""
    parts = [w for w in _fold(first).split() if w not in ("jr", "sr", "ii", "iii", "phd")] if first else []
    surname = parts[-1] if parts else ""
    core = re.sub(r"^(the|a|an) ", "", _fold(title.split(":")[0]))
    queries = ([{"q": f"{title} {surname}"}, {"title": title, "author": surname}] if surname else []) + [{"q": title}]
    best, best_score = None, -1
    for q in queries:
        q.update(limit=10, fields=fields)
        for d in get("https://openlibrary.org/search.json?" + urllib.parse.urlencode(q)).get("docs", []):
            authors = " ".join(_fold(n) for n in d.get("author_name", [])).split()
            if surname and surname not in authors:
                if authors:                      # Latin-script authors that don't match: wrong book
                    continue
                penalty = 1                      # only non-Latin names: can't check, allow at a penalty
            else:
                penalty = 0
            ed = ((d.get("editions") or {}).get("docs") or [{}])[0]
            def tscore(t):
                t = re.sub(r"^(the|a|an) ", "", _fold((t or "").split(":")[0]))
                return 3 if t == core else 2 if (t.startswith(core) or (len(t) > 4 and core.startswith(t + " "))) else 1 if core in t else 0
            ts = max(tscore(d.get("title")), tscore(ed.get("title")))
            if ts == 0:
                continue
            english = "eng" in (ed.get("language") or [])
            score = (ts * 10 - penalty * 5 + english * 2) * 100000 + min(d.get("edition_count", 0), 99999)
            if score > best_score:
                best, best_score = dict(d, _edition=ed.get("key") if tscore(ed.get("title")) == ts else None), score
        if best_score >= 3200000:
            break
    return best


def pick_edition(work_key, isbn_hint):
    eds = get(f"https://openlibrary.org{work_key}/editions.json?limit=100").get("entries", [])

    def score(e):
        isbns = e.get("isbn_13", []) + e.get("isbn_10", [])
        langs = [l.get("key") for l in e.get("languages", [])]
        anglo_isbn = any(i.startswith(("9780", "9781", "0", "1")) for i in isbns)
        english = 2 if "/languages/eng" in langs else 1 if (not langs and anglo_isbn) else 0
        return (
            isbn_hint in isbns if isbn_hint else False,
            english,
            bool(parse_dims(e.get("physical_dimensions"))),
            bool(e.get("number_of_pages")),
            bool(e.get("isbn_13")),
        )

    eds.sort(key=score, reverse=True)
    return eds[0] if eds else None


def binding_class(fmt, pages, height):
    f = (fmt or "").lower()
    if "hard" in f:
        return "hardcover"
    if "mass" in f or (height and height < 185):
        return "mass"
    return "paperback"


def enrich(b):
    rec = {"slug": b["slug"], "title": b["title"], "author": b["author"], "beloved": b["beloved"], "cover": b.get("cover")}
    for k in ("link", "gr_id", "gr_rating"):
        if b.get(k):
            rec[k] = b[k]
    doc = None
    isbn = b.get("force_isbn") or b.get("isbn13") or b.get("isbn10")
    if isbn and not b.get("force_isbn"):
        try:
            ed0 = get(f"https://openlibrary.org/isbn/{isbn}.json")
            work = (ed0.get("works") or [{}])[0].get("key")
            if work:
                w = get(f"https://openlibrary.org{work}.json")
                names = []
                for a in (w.get("authors") or [])[:3]:
                    try:
                        names.append(get(f"https://openlibrary.org{a['author']['key']}.json").get("name"))
                    except Exception:
                        pass
                doc = {"key": work, "title": w.get("title"), "author_name": [n for n in names if n], "_edition": ed0["key"]}
                b = dict(b, force_isbn=isbn)
        except Exception:
            doc = None
    if doc is None:
        doc = search(b["title"], b["author"])
    if not doc:
        rec["error"] = "not found on Open Library"
        return rec
    rec["ol_work"] = doc["key"]
    rec["ol_author"] = (doc.get("author_name") or [""])[0]
    rec["ol_title"] = doc.get("title")
    if b.get("force_isbn"):
        ed = get(f"https://openlibrary.org/isbn/{b['force_isbn']}.json")
    elif doc.get("_edition") and not (b.get("isbn13") or b.get("isbn10")):
        ed = get(f"https://openlibrary.org{doc['_edition']}.json")
    else:
        ed = pick_edition(doc["key"], b.get("isbn13") or b.get("isbn10"))
    dims = parse_dims(ed.get("physical_dimensions")) if ed else None
    pages = b.get("pages") or (ed or {}).get("number_of_pages") or doc.get("number_of_pages_median")
    rec.update({
        "ol_edition": ed and ed["key"],
        "isbn13": b.get("isbn13") or ((ed or {}).get("isbn_13") or [None])[0],
        "isbn10": b.get("isbn10") or ((ed or {}).get("isbn_10") or [None])[0],
        "publisher": b.get("publisher") or ((ed or {}).get("publishers") or [None])[0],
        "format": (ed or {}).get("physical_format") or b.get("binding"),
        "pages": pages,
        "ol_cover_id": ((ed or {}).get("covers") or [doc.get("cover_i")])[0],
    })
    cls = binding_class(rec["format"], pages, dims and dims[0])
    if dims and len(dims) == 3:
        h, w, t = dims
        rec["dims_mm"] = {"h": round(h), "w": round(w), "t": round(t, 1)}
        rec["dims_source"] = "openlibrary:physical_dimensions"
    else:
        h = dims[0] if dims else HEIGHT[cls]
        w = dims[1] if dims else round(h * 0.66)
        t = (pages or 300) * CALIPER[cls] + BOARD[cls]
        rec["dims_mm"] = {"h": round(h), "w": round(w), "t": round(t, 1)}
        rec["dims_source"] = ("openlibrary:h,w + " if dims else f"estimate:{cls} height + ") + ("pages" if pages else "default 300 pages")
    rec["binding_class"] = cls
    return rec


def main():
    """Incremental: existing records in enriched.json (incl. hand fixes) are kept unless --force.
    Usage: enrich.py [--all] [--force] [slug ...]   (default: sample.txt)"""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    books = {b["slug"]: b for b in json.load(open(HERE / "data/books.json"))}
    gr = HERE / "data/goodreads_books.json"
    if gr.exists():
        books.update({b["slug"]: b for b in json.load(open(gr))})
        for slug, extra in json.load(open(HERE / "data/goodreads_skipped.json")).get("isbn_for_smus", {}).items():
            if slug in books and extra.get("isbn13"):
                books[slug] = dict(books[slug], isbn13=extra["isbn13"], author=books[slug]["author"] or extra["author"])
    path = HERE / "data/enriched.json"
    existing = {r["slug"]: r for r in json.loads(path.read_text())} if path.exists() else {}
    if "--all" in sys.argv:
        slugs = list(books)
    else:
        slugs = args or (HERE / "sample.txt").read_text().split()
    for s in slugs:
        if s in existing and "error" not in existing[s] and "--force" not in sys.argv:
            continue
        try:
            r = enrich(books[s])
        except Exception as e:  # keep going; record failure
            r = {"slug": s, "title": books[s]["title"], "author": books[s]["author"], "error": repr(e)}
        existing[s] = r
        d = r.get("dims_mm", {})
        print(f"{s[:40]:40} {r.get('isbn13') or '-':14} {d.get('h','?'):>4}x{d.get('w','?'):>4}x{d.get('t','?'):>5}mm  {r.get('dims_source', r.get('error'))}", flush=True)
        path.write_text(json.dumps(list(existing.values()), indent=1, ensure_ascii=False))  # save as we go
        time.sleep(0.35)
    print(f"{len(existing)} records in {path.name}")


if __name__ == "__main__":
    main()
