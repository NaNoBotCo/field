"""Place page addresses exactly as mot-dang's build.py writes them.

A copy of _slug_stem / _slug_clash / place_slug (mot-dang build.py): the Latin name plus
the id's digits (or the id's letters when it has none), a sha1 tail for non-ASCII ids, and
a hash suffix for a different place that lands on the same stem. Records come from
data/canonical/<prov>.json with data/curated/additions-*.json laid over them, which is
what import_all.py does before a build. `check()` compares against a built docs/.
"""
import hashlib, json, re
from pathlib import Path
UNSAFE = re.compile(r"[^a-z0-9]+"); ASCII_ID = re.compile(r"^[A-Za-z0-9_-]+$")
ADDS = {"cm": "additions-chiang-mai.json", "cr": "additions-chiang-rai.json"}

def stem(r):
    numeric = re.sub(r"\D", "", r["id"]) or re.sub(r"[^a-z0-9]", "", r["id"].lower())
    cand = r.get("nameEn") or r.get("name") or r.get("nameEn") or r["id"]
    s = UNSAFE.sub("-", cand.strip().lower()).strip("-")[:60].rstrip("-")
    st = f"{s}-{numeric}" if s else numeric
    if not ASCII_ID.match(r["id"]):
        st += "-" + hashlib.sha1(r["id"].encode("utf-8")).hexdigest()[:7]
    return st

def load(md: Path):
    recs = {}
    for prov in ("cm", "cr"):
        for r in json.loads((md / f"data/canonical/{prov}.json").read_text()):
            recs[r["id"]] = r
        a = md / "data/curated" / ADDS[prov]
        if a.exists():
            for r in json.loads(a.read_text()):
                recs[r["id"]] = {**recs.get(r["id"], {}), **r}
    return recs

def urls(md: Path, ids):
    recs = load(md)
    by_stem = {}
    for r in recs.values():
        by_stem.setdefault(stem(r), []).append((r["id"], (r.get("name") or r.get("nameTh") or r.get("nameEn") or "").strip()))
    clash = {}
    for st, rows in by_stem.items():
        rows = sorted(set(rows))
        if len(rows) < 2: continue
        keep = rows[0][1]
        for rid, nm in rows[1:]:
            if nm and nm != keep:
                clash[rid] = f"{st}-{hashlib.sha1(rid.encode()).hexdigest()[:6]}"
    out = {}
    for i in ids:
        r = recs.get(i)
        if not r: continue
        prov = r.get("province") or i.split("-", 1)[0]
        out[i] = f"{prov}/p/{clash.get(i) or stem(r)}.html"
    return out

def check(md: Path, paths):
    return [p for p in paths if not (md / "docs" / p).exists()]
