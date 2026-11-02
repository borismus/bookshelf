#!/bin/bash
# Generate AI spines and back covers for the slugs in $1, 6 requests in parallel. Logs to data/batch_gen.log.
cd "$(dirname "$0")"
LIST="$1"
{ sed 's/^/spine /' "$LIST"; sed 's/^/back /' "$LIST"; } | xargs -P 6 -L 1 bash -c '
  if [ "$0" = spine ]; then uv run -q --with pillow --with numpy gen_spines.py "$1"; else uv run -q --with pillow --with numpy gen_backs.py "$1" | sed "s/^/back: /"; fi' >> data/batch_gen.log 2>&1
echo "done" >> data/batch_gen.log
