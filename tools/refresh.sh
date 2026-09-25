#!/bin/zsh
# Rebuild Field from every session file and publish both copies.
#   tools/refresh.sh            build, install into mot-dang, publish motdang.net/field, push the GitHub copy
#   tools/refresh.sh --no-push  the same without the GitHub pull request
# Run at the end of each ride's digest, and nightly, so a place whose Mot Dang page is built
# since the last run turns from a map pin into a page link.
set -euo pipefail
cd "${0:a:h}/.."
MD="$HOME/Developer/claude code projects/mot-dang"
./publish.sh                                                  # docs/ for GitHub Pages, every gate
SITE_URL=https://motdang.net/field python3 tools/site.py      # build/site for motdang.net
if grep -rlI "/Users/" build/site >/dev/null 2>&1; then echo "REFUSED: host paths in build/site"; exit 2; fi
rsync -a --delete build/site/ "$MD/assets/field/"
rsync -a --delete build/site/ "$MD/docs/field/"
(cd "$MD" && python3 publish/deploy.py --only field --yes)
python3 tools/commons.py stage >/dev/null && python3 tools/commons.py upload --if-ready   # Wikimedia Commons, once a login and approval exist
if [[ "${1:-}" != "--no-push" ]] && [[ -n "$(git status --porcelain -- docs data photos tools)" ]]; then
  git add docs data photos tools
  git commit -q -m "Field: sessions to $(ls data/sessions | sort | tail -1 | sed 's/\.json//')

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  "$HOME/.claude/bin/pr-push" "$PWD" "Field: refresh from the session files"
fi
echo "field refreshed: $(ls data/sessions | wc -l | tr -d ' ') sessions"
