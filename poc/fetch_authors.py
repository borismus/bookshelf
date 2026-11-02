"""Store the full Open Library author list (ol_authors) for every enriched book that has a work key."""
import json, time, urllib.parse
from pathlib import Path
import enrich

HERE = Path(__file__).resolve().parent
path = HERE / "data/enriched.json"
recs = json.loads(path.read_text())
for r in recs:
    if not r.get("ol_work") or r.get("ol_authors"):
        continue
    q = urllib.parse.urlencode({"q": f"key:{r['ol_work']}", "fields": "author_name", "limit": 1})
    try:
        docs = enrich.get("https://openlibrary.org/search.json?" + q).get("docs", [])
        r["ol_authors"] = docs[0].get("author_name", []) if docs else []
    except Exception as e:
        print("failed", r["slug"], e)
    time.sleep(0.3)
path.write_text(json.dumps(recs, indent=1, ensure_ascii=False))
multi = [(r["slug"], r.get("author"), r["ol_authors"]) for r in recs if len(r.get("ol_authors") or []) > 1]
print(len(multi), "books with several OL authors"); [print(" ", *m) for m in multi[:40]]
