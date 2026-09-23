"""GoPro Max 2 ride, 2026-09-23 -> frame index, track and the Mot Dang records it passed.

Input is frames_raw.txt: line 1 maps each burst to its GoPro cloud id, then one line per
frame -- burst letter + item number, camera local time (UTC+7), and where the camera had a
fix, lat, lon, altitude and the GPS UTC time, all read from each frame's EXIF.
"""
import csv, json, math, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(Path.home() / "Developer/claude code projects/capture-pipeline/src"))
from cp.places import stream_records  # noqa: E402

DATE = "2026-09-23"
NEAR_M = 25.0
GAP_S = 20  # interpolate across a dropped fix no longer than this

lines = (HERE / "frames_raw.txt").read_text().splitlines()
ids = json.loads(lines[0])
letter = {k[3]: k for k in ids}  # GSAA1911 -> 'A'

frames = []
for ln in lines[1:]:
    p = ln.split(",")
    b, n = p[0][0], int(p[0][1:])
    t = p[1]
    sec = int(t[:2]) * 3600 + int(t[2:4]) * 60 + int(t[4:])
    f = {"burst": letter[b], "cloud_id": ids[letter[b]], "item": n,
         "local": f"{DATE}T{t[:2]}:{t[2:4]}:{t[4:]}+07:00", "sec": sec,
         "lat": None, "lon": None, "alt": None, "pos": "none"}
    if len(p) > 2:
        f.update(lat=float(p[2]), lon=float(p[3]), alt=int(p[4]), pos="fix")
    frames.append(f)
frames.sort(key=lambda f: f["sec"])

def hav(a, b, c, d):
    r = 6371008.8
    p1, p2 = math.radians(a), math.radians(c)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))

# fill short gaps between two fixes, same burst
for i, f in enumerate(frames):
    if f["pos"] != "none":
        continue
    prev = next((g for g in reversed(frames[:i]) if g["pos"] == "fix" and g["burst"] == f["burst"]), None)
    nxt = next((g for g in frames[i + 1:] if g["pos"] == "fix" and g["burst"] == f["burst"]), None)
    if prev and nxt and nxt["sec"] - prev["sec"] <= GAP_S:
        k = (f["sec"] - prev["sec"]) / (nxt["sec"] - prev["sec"])
        f.update(lat=round(prev["lat"] + k * (nxt["lat"] - prev["lat"]), 6),
                 lon=round(prev["lon"] + k * (nxt["lon"] - prev["lon"]), 6), pos="interpolated")

placed = [f for f in frames if f["lat"] is not None]
for a, b in zip(placed, placed[1:]):
    dt = b["sec"] - a["sec"]
    d = hav(a["lat"], a["lon"], b["lat"], b["lon"])
    b["kmh"] = round(d / dt * 3.6, 1) if dt else None
    y = math.sin(math.radians(b["lon"] - a["lon"])) * math.cos(math.radians(b["lat"]))
    x = (math.cos(math.radians(a["lat"])) * math.sin(math.radians(b["lat"]))
         - math.sin(math.radians(a["lat"])) * math.cos(math.radians(b["lat"])) * math.cos(math.radians(b["lon"] - a["lon"])))
    b["heading"] = round((math.degrees(math.atan2(y, x)) + 360) % 360) if d > 1 else None
    b["_d"] = d

# Mot Dang records near the track
lat0, lat1 = min(f["lat"] for f in placed) - .001, max(f["lat"] for f in placed) + .001
lon0, lon1 = min(f["lon"] for f in placed) - .001, max(f["lon"] for f in placed) + .001
canon = Path.home() / "Developer/claude code projects/mot-dang/data/canonical/cm.json"
near = {}
for r in stream_records(canon):
    la, lo = r.get("lat"), r.get("lng")
    if la is None or lo is None or not (lat0 <= la <= lat1 and lon0 <= lo <= lon1):
        continue
    best = min(((hav(la, lo, f["lat"], f["lon"]), f) for f in placed), key=lambda t: t[0])
    if best[0] <= NEAR_M:
        near[r["id"]] = (r, best)

for f in frames:
    f["places"] = []
for pid, (r, (d, f)) in near.items():
    f["places"].append((round(d), pid, r.get("nameTh") or r.get("name") or ""))

with open(HERE / "frames.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["burst", "item", "local_time", "lat", "lon", "alt_m", "position", "kmh", "heading",
                "cloud_id", "nearest_places"])
    for f in frames:
        w.writerow([f["burst"], f["item"], f["local"], f["lat"] or "", f["lon"] or "", f["alt"] or "",
                    f["pos"], f.get("kmh") or "", f.get("heading") if f.get("heading") is not None else "",
                    f["cloud_id"], " | ".join(f"{p[1]} ({p[0]} m)" for p in sorted(f["places"]))])

with open(HERE / "places_passed.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "name", "cat", "sub", "geoPrecision", "record_lat", "record_lng",
                "metres_from_track", "frame", "frame_time", "frame_lat", "frame_lon"])
    for pid, (r, (d, f)) in sorted(near.items(), key=lambda kv: kv[1][1][1]["sec"]):
        w.writerow([pid, r.get("nameTh") or r.get("name"), "/".join(r.get("cat") or []),
                    "/".join(r.get("sub") or []), r.get("geoPrecision") or "", r["lat"], r["lng"],
                    round(d, 1), f"{f['burst']}#{f['item']}", f["local"], f["lat"], f["lon"]])

# track: one line per run of placed frames with no gap over 60 s
feats, run = [], []
for f in placed:
    if run and f["sec"] - run[-1]["sec"] > 60:
        feats.append(run); run = []
    run.append(f)
feats.append(run)
gj = {"type": "FeatureCollection", "features": []}
for i, run in enumerate(feats):
    gj["features"].append({"type": "Feature", "properties": {
        "kind": "track", "segment": i + 1, "start": run[0]["local"], "end": run[-1]["local"],
        "metres": round(sum(f.get("_d", 0) for f in run[1:]))},
        "geometry": {"type": "LineString", "coordinates": [[f["lon"], f["lat"]] + ([f["alt"]] if f["alt"] else []) for f in run]}})
for f in placed:
    gj["features"].append({"type": "Feature", "properties": {
        "kind": "frame", "burst": f["burst"], "item": f["item"], "time": f["local"], "position": f["pos"],
        "kmh": f.get("kmh"), "heading": f.get("heading"), "cloud_id": f["cloud_id"],
        "places": [p[1] for p in f["places"]]},
        "geometry": {"type": "Point", "coordinates": [f["lon"], f["lat"]]}})
(HERE / "ride.geojson").write_text(json.dumps(gj, ensure_ascii=False))

# summary for the console
tot = sum(ft["properties"]["metres"] for ft in gj["features"] if ft["properties"]["kind"] == "track")
cnt = {k: sum(1 for f in frames if f["pos"] == k) for k in ("fix", "interpolated", "none")}
print(f"frames {len(frames)} · {cnt} · track {tot/1000:.2f} km in {len(feats)} segment(s) · records within {NEAR_M:.0f} m: {len(near)}")
for s in feats:
    print(" segment", s[0]["local"][11:19], "→", s[-1]["local"][11:19], len(s), "frames")
print(" no position:", sorted({f['burst'] for f in frames if f['pos'] == 'none'}))
