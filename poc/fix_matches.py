"""Re-run Open Library lookups for slugs in data/overrides.json with corrected title/author hints."""
import json, sys
from pathlib import Path
import enrich

HERE = Path(__file__).resolve().parent
ov = {k: v for k, v in json.loads((HERE / "data/overrides.json").read_text()).items() if not k.startswith("_")}
books = {b["slug"]: b for b in json.loads((HERE / "data/books.json").read_text())}
books.update({b["slug"]: b for b in json.loads((HERE / "data/goodreads_books.json").read_text())})
path = HERE / "data/enriched.json"
enriched = {r["slug"]: r for r in json.loads(path.read_text())}
for slug in (sys.argv[1:] or ov):
    hint = ov[slug]
    b = dict(books[slug], title=hint["title"], author=hint["author"], isbn13=None, isbn10=None, pages=None, binding=None, publisher=None, force_isbn=hint.get("isbn"))
    r = enrich.enrich(b)
    r["title"], r["author"] = books[slug]["title"], books[slug]["author"]      # keep smus.com's own title/author
    if hint.get("display_author"):
        r["ol_author"] = hint["display_author"]
    r.update(hint.get("set", {}))          # hand-set facts (edition, binding, dims) win over the lookup
    enriched[slug] = r
    print(f"{slug[:45]:45} -> {r.get('ol_title')} | {r.get('ol_author')} | {r.get('isbn13')} | cover {r.get('ol_cover_id')} | {r.get('error', '')}")
path.write_text(json.dumps(list(enriched.values()), indent=1, ensure_ascii=False))
