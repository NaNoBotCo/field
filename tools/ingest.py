#!/usr/bin/env python3
"""Turn one capture session's working folder into the files this site is built from.

    python3 tools/ingest.py <session-dir> <date> [--trim-start-m 1500] [--trim-end-m 400]

<session-dir> is the working folder the pipeline wrote (frames.csv, sign_matches.csv,
new_records.json, …). MOTDANG points at the mot-dang checkout, where the published
photographs and listings already live; this reads them, it does not write there.

Writes data/sessions/<date>.json, data/tracks/<date>.geojson and copies the session's
published photographs into photos/<date>/. The two ends of a track are trimmed because a
ride starts and ends somewhere personal.
"""
import argparse, csv, json, math, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTDANG = Path(os.environ.get("MOTDANG", Path.home() / "Developer/claude code projects/mot-dang"))

def metres(a, b):
    k = math.cos(math.radians(a[0]))
    return math.hypot(a[0] - b[0], (a[1] - b[1]) * k) * 111320

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session"); ap.add_argument("date")
    ap.add_argument("--trim-start-m", type=float, default=1500)
    ap.add_argument("--trim-end-m", type=float, default=400)
    ap.add_argument("--kind", default="ride")
    ap.add_argument("--camera", default="GoPro Max 2")
    a = ap.parse_args()
    S = Path(a.session)

    frames = list(csv.DictReader(open(S / "frames.csv")))
    fixes = [(float(r["lat"]), float(r["lon"])) for r in frames if r["position"] == "fix"]
    run, dist = [fixes[0]], 0.0
    for p in fixes[1:]:
        dist += metres(run[-1], p); run.append(p)
    # trim by distance from each end
    def trim(pts, m):
        d = 0.0
        for i in range(1, len(pts)):
            d += metres(pts[i - 1], pts[i])
            if d >= m: return pts[i:]
        return []
    line = trim(run, a.trim_start_m)
    line = list(reversed(trim(list(reversed(line)), a.trim_end_m)))
    shown = sum(metres(line[i - 1], line[i]) for i in range(1, len(line)))
    track = {"type": "FeatureCollection", "features": [{"type": "Feature",
             "properties": {"session": a.date, "metres_shown": round(shown), "metres_ridden": round(dist),
                            "note": "ends trimmed"},
             "geometry": {"type": "LineString", "coordinates": [[round(lo, 6), round(la, 6)] for la, lo in line]}}]}
    (ROOT / "data/tracks").mkdir(parents=True, exist_ok=True)
    (ROOT / f"data/tracks/{a.date}.geojson").write_text(json.dumps(track))

    def inside(la, lo):  # keep only what falls along the shown line
        return any(metres((la, lo), p) < 60 for p in line[::3])

    photos_dir = ROOT / "photos" / a.date; photos_dir.mkdir(parents=True, exist_ok=True)
    own = json.load(open(MOTDANG / "data/curated/own_pictures.json"))["picks"]
    pics = []
    for p in own:
        if p.get("date") != a.date: continue
        src = MOTDANG / "assets" / p["file"]
        if not src.exists(): continue
        dst = photos_dir / Path(p["file"]).name
        shutil.copy2(src, dst)
        pics.append({k: p.get(k) for k in ("slug", "title", "description", "description_th", "lat", "lng",
                     "placeId", "topic", "mood", "width", "height", "licence", "artist", "signText")}
                    | {"file": f"photos/{a.date}/{dst.name}"})

    confirmed = []
    for r in csv.DictReader(open(S / "sign_matches.csv")):
        if int(r["record_to_frame_m"]) > 50 or len(r["text_read"].replace(" ", "")) < 5: continue
        if not r["best_tile"].startswith(("GSAA1911", "GSAB2131")): continue
        confirmed.append({"id": r["id"], "name": r["name"], "cat": r["cat"], "read": r["text_read"],
                          "photo": (MOTDANG / f"assets/photos/{r['id']}.jpg").exists()})
    new = []
    for r in json.load(open(S / "new_records.json")):
        new.append({"id": r["id"], "name": r["name"], "nameTh": r.get("nameTh"), "nameEn": r.get("nameEn"),
                    "kind": r["attrs"]["kind"], "kindTh": r["attrs"].get("kindTh"), "cat": r["cat"],
                    "lat": r["lat"], "lng": r["lng"], "phone": r.get("phone") or "",
                    "photo": (MOTDANG / f"assets/photos/{r['id']}.jpg").exists()})
    reads = sum(1 for line_ in open(S / "ocr.jsonl"))
    text_lines = sum(len(json.loads(l).get("text", [])) for l in open(S / "ocr.jsonl"))
    sess = {"date": a.date, "kind": a.kind, "camera": a.camera,
            "counts": {"frames": len(frames), "frames_with_fix": len(fixes), "km": round(dist / 1000, 1),
                       "tiles_read": reads, "text_lines": text_lines, "confirmed": len(confirmed),
                       "new": len(new), "photos": len(pics),
                       "place_photos": sum(1 for p in pics if p.get("placeId"))},
            "confirmed": confirmed, "new": new, "photos": pics,
            "track": f"data/tracks/{a.date}.geojson"}
    old = ROOT / f"data/sessions/{a.date}.json"
    if old.exists():  # hand-written keys survive a re-ingest
        prev = json.loads(old.read_text())
        for k in ("title", "title_th", "line", "line_th", "hero", "example", "pin_fixes", "where", "where_th"):
            if k in prev: sess[k] = prev[k]
    import motdang_urls  # each place's page, by Mot Dang's own slug rule
    m = motdang_urls.urls(MOTDANG, [r["id"] for r in sess["new"] + sess["confirmed"]]
                          + [p["placeId"] for p in sess["photos"] if p.get("placeId")]
                          + [x["id"] for x in sess.get("pin_fixes", [])])
    for r in sess["new"] + sess["confirmed"] + sess.get("pin_fixes", []): r["url"] = m.get(r["id"])
    for p in sess["photos"]:
        if p.get("placeId"): p["url"] = m.get(p["placeId"])
    old.write_text(json.dumps(sess, ensure_ascii=False, indent=1) + "\n")
    print(a.date, sess["counts"])

if __name__ == "__main__":
    main()
