"""Build poc/data/books.json from the smus.com preview build + Goodreads exports.

smus.com is the source of truth (slug, title, author, beloved, cover).
Goodreads fills in ISBN, binding, page count, publisher.
"""
import csv
import os
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(os.environ.get("SMUS_WWW") or Path.home() / "Projects/smus.com/preview-www")   # bookshelf.py builds a fresh copy
GR = ROOT / "goodreads"
OUT = ROOT / "poc/data/books.json"

LI = re.compile(
    r'<a href="/books/([^"]+)">\s*(<div class=\'rating\'>\s*☆\s*</div>)?\s*'
    r"<div class='title'>(.*?)</div>\s*<time>\s*(.*?)\s*</time>",
    re.S,
)
COVER = re.compile(r'<img class="book-cover"[^>]*src="([^"]+)"')


def norm(s: str) -> str:
    s = html.unescape(s).lower()
    s = re.sub(r"\(.*?\)", "", s)  # (audio), (Kindle Edition) ...
    s = s.split(":")[0]
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"^(the|a|an) ", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def split_title(full: str):
    full = html.unescape(full).strip()
    full = re.sub(r"\s*\((audio|audiobook)\)\s*$", "", full, flags=re.I)
    m = re.match(r"(.*) by (.*)$", full)
    return (m.group(1), m.group(2)) if m else (full, "")


def isbn_clean(v: str) -> str:
    return re.sub(r"[^0-9X]", "", v or "")


def load_goodreads():
    """title-key -> metadata. Prefer rows with ISBN-13 and a physical binding."""
    rows = {}

    def add(key, meta):
        old = rows.get(key)
        score = lambda m: (bool(m.get("isbn13")), m.get("binding") not in ("Kindle Edition", "ebook", "", None))
        if old is None or score(meta) > score(old):
            rows[key] = meta

    for r in csv.DictReader(open(max(GR.glob("goodreads_library_export_*.csv")))):   # newest export (dates sort lexically)
        add(norm(r["Title"]), {
            "isbn13": isbn_clean(r["ISBN13"]), "isbn10": isbn_clean(r["ISBN"]),
            "binding": r["Binding"], "pages": int(r["Number of Pages"] or 0) or None,
            "publisher": r["Publisher"], "year": r["Year Published"],
            "gr_title": r["Title"], "gr_author": r["Author"], "gr_rating": r["My Rating"],
        })
    for f in ["goodreads_import_review_links.csv", "goodreads_import_retry_with_isbn.csv"]:
        for r in csv.DictReader(open(GR / f)):
            isbn = isbn_clean(r["ISBN"])
            if not isbn:
                continue
            key = norm(r["Title"])
            meta = rows.get(key, {}).copy()
            if not meta.get("isbn13") and len(isbn) == 13:
                meta["isbn13"] = isbn
            if not meta.get("isbn10") and len(isbn) == 10:
                meta["isbn10"] = isbn
            meta.setdefault("gr_title", r["Title"])
            meta.setdefault("gr_author", r["Author"])
            rows[key] = meta
    return rows


def main():
    index = (SITE / "books/index.html").read_text()
    gr = load_goodreads()
    books, unmatched = [], []
    for slug, star, full, date in LI.findall(index):
        title, author = split_title(full)
        page = SITE / "books" / slug / "index.html"
        cover = None
        if page.exists():
            m = COVER.search(page.read_text())
            cover = m.group(1) if m else None
        meta = gr.get(norm(title))
        if meta is None:  # try prefix match, e.g. "Book of Why" vs "The Book of Why: The New Science..."
            k = norm(title)
            meta = next((v for kk, v in gr.items() if k and (kk.startswith(k) or k.startswith(kk)) and len(kk) > 3), None)
        if meta is None:
            unmatched.append(full)
        books.append({
            "slug": slug, "title": title, "author": author,
            "beloved": bool(star), "posted": date, "audio": "audio" in slug,
            "cover": cover, **(meta or {}),
        })
    OUT.write_text(json.dumps(books, indent=1, ensure_ascii=False))
    n = len(books)
    have = lambda k: sum(1 for b in books if b.get(k))
    print(f"{n} books -> {OUT.relative_to(ROOT)}")
    print(f"  beloved {have('beloved')}, cover {have('cover')}, isbn13 {have('isbn13')}, "
          f"isbn10-only {sum(1 for b in books if b.get('isbn10') and not b.get('isbn13'))}, pages {have('pages')}, audio {have('audio')}")
    print(f"  unmatched to Goodreads: {len(unmatched)}", file=sys.stderr)
    for u in unmatched[:15]:
        print("   -", u, file=sys.stderr)


if __name__ == "__main__":
    main()
