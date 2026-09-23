"""Every Mot Dang record (cm canonical) within 200 m of any placed frame -> nearby.json."""
import csv, json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path.home() / "Developer/claude code projects/capture-pipeline/src"))
from cp.places import stream_records
fr = [(float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(HERE / "frames.csv")) if r["lat"]]
la0, la1 = min(a for a, _ in fr) - .002, max(a for a, _ in fr) + .002
lo0, lo1 = min(b for _, b in fr) - .002, max(b for _, b in fr) + .002
def near(la, lo):
    k = math.cos(math.radians(la))
    return min(((la - a) ** 2 + ((lo - b) * k) ** 2) ** .5 * 111320 for a, b in fr)
keep = []
for r in stream_records(Path.home() / "Developer/claude code projects/mot-dang/data/canonical/cm.json"):
    la, lo = r.get("lat"), r.get("lng")
    if la is None or lo is None or not (la0 <= la <= la1 and lo0 <= lo <= lo1):
        continue
    d = near(la, lo)
    if d <= 200:
        keep.append({k: r.get(k) for k in ("id", "name", "nameTh", "nameEn", "lat", "lng", "cat", "sub", "geoPrecision", "phone")}
                    | {"altNames": (r.get("attrs") or {}).get("altNames") or [], "track_m": round(d)})
(HERE / "nearby.json").write_text(json.dumps(keep, ensure_ascii=False))
print(len(keep))
