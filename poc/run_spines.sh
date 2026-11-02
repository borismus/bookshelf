#!/bin/bash
# Regenerate spines only for the slugs in $1, 6 in parallel. Logs to data/batch_gen.log.
cd "$(dirname "$0")"
xargs -P 6 -L 1 uv run -q --with pillow --with numpy gen_spines.py < "$1" >> data/batch_gen.log 2>&1
echo done >> data/batch_gen.log
