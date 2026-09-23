#!/bin/bash
# Build the GitHub Pages copy into docs/. The motdang.net copy is built with
# SITE_URL=https://motdang.net/field and installed into mot-dang/assets/field/.
set -euo pipefail
cd "$(dirname "$0")"
SITE_URL="${SITE_URL:-https://nanobotco.github.io/field}"
STYLE="$HOME/.claude/bin/stylecheck.py"
if [ -f "$STYLE" ]; then
  python3 "$STYLE" README.md NOTICE.txt tools/site.py tools/ingest.py pipeline data/sessions || {
    echo "REFUSED: style. See ~/.claude/STYLE.md"; exit 4; }
fi
SITE_URL="$SITE_URL" python3 tools/site.py
rm -rf docs && mkdir -p docs && cp -R build/site/ docs/ && touch docs/.nojekyll
if grep -rl "/Users/" docs >/dev/null 2>&1; then echo "REFUSED: host paths found in docs/"; exit 2; fi
echo "docs/ built for $SITE_URL — $(find docs -name '*.html' | wc -l | tr -d ' ') pages, $(du -sh docs | cut -f1)"
