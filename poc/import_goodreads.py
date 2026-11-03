"""Add Goodreads 'read' books that aren't on smus.com (shown as not starred; they link to Goodreads).

Also gives ISBNs to smus.com books that Open Library couldn't find, when Goodreads has the same book.
Writes data/goodreads_books.json (same shape as books.json) and data/goodreads_skipped.json.
"""
import csv
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GR = max((HERE.parent / "goodreads").glob("goodreads_library_export_*.csv"))   # newest export

# Not printed books, or not something on the shelf: lecture courses, sheet music, a mis-scanned product.
SKIP_TITLES = ["Encyclopedia of Picture Chords", "Best of Metallica", "Piano/Vocal/Guitar", "Diesel Women",
               "Hal Leonard Guitar Method", "The Other 1492", "The Bible and Western Culture",
               "Peoples and Cultures of the World", "Great Battles of the Ancient World", "The History of Ancient Rome"]
# Goodreads titles that are the same book as a smus.com entry: Goodreads title -> smus.com slug
SAME_AS_SMUS = {"The Goal: A Business Graphic Novel": "the-goal-a-business-graphic-novel",
                "Selected Stories Of Philip K. Dick": "selected-short-stories-of-philip-k-dick",
                "Hands": "john-napier-hands", "Rainbows End": "vernor-vinge-rainbows-end"}


def norm(s):
    s = html.unescape(s or "").lower()
    s = re.sub(r"\(.*?\)", "", s).split(":")[0]
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"^(the|a|an) ", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def slugify(s):
    s = re.sub(r"\(.*?\)", "", html.unescape(s)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]


def clean_title(t):
    t = re.sub(r"\s*\((?:[^()]*#[^()]*)\)\s*$", "", t)   # drop series info "(Dune #3)"
    return t.strip()


def main():
    smus = json.loads((HERE / "data/books.json").read_text())
    keys = {norm(b["title"]): b["slug"] for b in smus}
    rows = [r for r in csv.DictReader(open(GR)) if r["Exclusive Shelf"] == "read"]
    out, skipped, seen, smus_isbn = [], [], set(), {}
    for r in rows:
        title, isbn13 = r["Title"], r["ISBN13"].strip('="')
        k = norm(title)
        if title in SAME_AS_SMUS:
            smus_isbn[SAME_AS_SMUS[title]] = {"isbn13": isbn13, "gr_id": r["Book Id"], "author": r["Author"]}
            continue
        if k in keys or any(len(k) > 4 and len(x) > 4 and (k.startswith(x) or x.startswith(k)) for x in keys):
            continue                                            # already on smus.com
        if any(s.lower() in title.lower() for s in SKIP_TITLES):
            skipped.append(title); continue
        full = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()   # whole title: "JavaScript: The Good Parts" != "...: Definitive Guide"
        if full in seen:
            skipped.append(title + " (duplicate)"); continue
        seen.add(full)
        out.append({
            "slug": "gr-" + slugify(title), "title": clean_title(title), "author": r["Author"].replace("  ", " "),
            "beloved": False, "posted": r["Date Read"], "audio": False, "cover": None,
            "isbn13": isbn13 or None, "isbn10": r["ISBN"].strip('="') or None, "binding": r["Binding"],
            "pages": int(r["Number of Pages"] or 0) or None, "publisher": r["Publisher"],
            "gr_id": r["Book Id"], "gr_rating": r["My Rating"],
            "link": f"https://www.goodreads.com/book/show/{r['Book Id']}",
        })
    (HERE / "data/goodreads_books.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    (HERE / "data/goodreads_skipped.json").write_text(json.dumps({"skipped": skipped, "isbn_for_smus": smus_isbn}, indent=1))
    print(f"{len(out)} Goodreads-only books; skipped {len(skipped)}; ISBNs for {len(smus_isbn)} smus.com books")


if __name__ == "__main__":
    main()
