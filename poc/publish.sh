#!/bin/bash
# Build the static site (only what the viewer loads) into dist/ and force-push it to the gh-pages branch.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf dist && mkdir -p dist
cp poc/preview/index.html dist/
cp -R poc/preview/atlas dist/atlas
cp -R poc/preview/props dist/props
# shelf data without the source-image paths (the site only serves the atlases)
python3 - <<'PY'
import json
d = json.load(open("poc/preview/shelf.json"))
for c in d["cases"]:
    for s in c["shelves"]:
        for b in s:
            for k in ("texture", "cover", "back"):
                b.pop(k, None)
json.dump(d, open("dist/shelf.json", "w"), ensure_ascii=False, separators=(",", ":"))
PY
python3 poc/seo.py dist
cp poc/preview/og.jpg dist/og.jpg
touch dist/.nojekyll
if [ "${1:-}" = "--dry-run" ]; then du -sh dist; exit 0; fi
REMOTE=$(git remote get-url origin)
cd dist
git init -q -b gh-pages
git add -A
git commit -q -m "Publish bookshelf ($(cd .. && git rev-parse --short HEAD))"
git push -q -f "$REMOTE" gh-pages
cd .. && rm -rf dist/.git
echo "published"
