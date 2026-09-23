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
# every place link against mot-dang's built pages (a page not built yet is listed, not fatal)
python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "tools"); import motdang_urls as mu
md = Path.home() / "Developer/claude code projects/mot-dang"
urls = {u for f in Path("data/sessions").glob("*.json") for x in (lambda s: s["new"] + s["confirmed"] + s["photos"])(json.loads(f.read_text())) for u in [x.get("url")] if u}
miss = mu.check(md, urls) if (md / "docs").exists() else []
print(f"place links: {len(urls)} · not yet built on motdang: {len(miss)}")
PY
