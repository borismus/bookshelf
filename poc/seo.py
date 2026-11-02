"""Fill dist/index.html's crawlable bits from dist/shelf.json: a screen-reader/search-engine book list (the shelf
itself is a WebGL canvas, invisible to both) and schema.org JSON-LD. Run by publish.sh."""
import html
import json
import sys
from pathlib import Path

URL = "https://borismus.github.io/bookshelf/"
dist = Path(sys.argv[1])
shelf = json.loads((dist / "shelf.json").read_text())
page = (dist / "index.html").read_text()

sections = {}                                   # case -> section -> [book], in shelf order
for c in shelf["cases"]:
    sec = c["name"]
    for s in c["shelves"]:
        for b in s:
            sec = b.get("section") or sec       # only a section's first book carries its label
            sections.setdefault(c["name"], {}).setdefault(sec, []).append(b)

e = html.escape
out = []
for case, secs in sections.items():
    out.append(f"<h2>{e(case)}</h2>")
    for sec, books in secs.items():
        out.append(f"<h3>{e(sec)}</h3>\n<ul>")
        for b in books:
            star = " ★" if b.get("beloved") else ""
            out.append(f'<li><a href="{e(b["link"])}">{e(b["title"])}</a> by {e(b["author"])}{star}</li>')
        out.append("</ul>")

books = [b for secs in sections.values() for bs in secs.values() for b in bs]
ld = {
    "@context": "https://schema.org", "@type": "CollectionPage", "name": "Boris Smus's Bookshelf", "url": URL,
    "description": "A 3D bookshelf of books Boris Smus has read and reviewed.",
    "author": {"@type": "Person", "name": "Boris Smus", "url": "https://smus.com/"},
    "mainEntity": {"@type": "ItemList", "numberOfItems": len(books), "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "item": {
            "@type": "Book", "name": b["title"], "author": {"@type": "Person", "name": b["author"]}, "url": b["link"],
            **({"datePublished": str(b["year"])} if b.get("year") else {}),
            **({"numberOfPages": b["pages"]} if b.get("pages") else {})}}
        for i, b in enumerate(books)]},
}
script = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>"
page = page.replace("<!--CATALOG-->", "\n".join(out), 1).replace("<!--JSONLD-->", script, 1)
(dist / "index.html").write_text(page)
print(f"seo: {len(books)} books in catalog + JSON-LD")
