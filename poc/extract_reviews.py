"""Collect what the book card shows: headline + first paragraph of the review, dates, rating, link.

smus.com books: from the preview build (h1 headline, first <p> of the review body, month posted).
Goodreads-only books: date read, star rating and the first paragraph of 'My Review' (often empty).
Writes data/reviews.json: slug -> {headline, excerpt, posted, read, rating, source}.
"""
import csv
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = Path.home() / "Projects/smus.com/preview-www/books"


def text(fragment):
    t = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def first_para(htmlish, limit=420):
    for p in re.findall(r"<p>(.*?)</p>", htmlish, re.S) or [htmlish]:
        t = text(p)
        if len(t) > 40:
            return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"
    return ""


def opening(body, budget=900):
    """Leading paragraphs of the review, up to ~budget characters, stopping at the first heading or non-prose block.
    The last paragraph is trimmed at a sentence end if it would run over."""
    out, used = [], 0
    for m in re.finditer(r"<(p|h\d|blockquote|ul|ol|table|figure|img|div)\b[^>]*>(.*?)</\1>|<img[^>]*>", body, re.S):
        tag = (m.group(1) or "img").lower()
        if tag != "p":
            if out:
                break
            continue
        t = text(m.group(2))
        if len(t) < 30:
            continue
        if used + len(t) > budget:
            if not out:                                     # always give at least one paragraph, cut at a sentence
                cut = t[:budget]
                end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
                out.append(cut[:end + 1] if end > 200 else cut.rsplit(" ", 1)[0] + "…")
            break
        out.append(t); used += len(t)
    return out


def main():
    out = {}
    for b in json.loads((HERE / "data/books.json").read_text()):
        page = SITE / b["slug"] / "index.html"
        rec = {"posted": b.get("posted"), "source": "smus"}
        if page.exists():
            h = page.read_text()
            m = re.search(r"<h1 class='title'>(.*?)</h1>", h, re.S)
            body = h.split("<div class='body'>", 1)[1] if "<div class='body'>" in h else ""
            paras = opening(body)
            rec.update(headline=text(m.group(1)) if m else None, excerpt=paras[0] if paras else '', paras=paras)
        out[b["slug"]] = rec
    rows = {r["Book Id"]: r for r in csv.DictReader(open(HERE.parent / "goodreads/goodreads_library_export_2026-08-18.csv"))}
    for b in json.loads((HERE / "data/goodreads_books.json").read_text()):
        r = rows.get(b["gr_id"], {})
        review = r.get("My Review", "").replace("<br/>", "</p><p>")
        out[b["slug"]] = {"source": "goodreads", "read": r.get("Date Read") or None,
                          "rating": int(float(r.get("My Rating") or 0)) or None,
                          "excerpt": first_para("<p>" + review + "</p>") if review else ""}
    (HERE / "data/reviews.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(out), "records;", sum(1 for v in out.values() if v.get("excerpt")), "with an excerpt")


if __name__ == "__main__":
    main()
