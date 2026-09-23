"""Sign text per frame -> matches against Mot Dang names, and unmatched sign clusters.

Writes sign_matches.csv (record seen by name on a sign) and sign_unmatched.csv
(text read on signs with no Mot Dang record of that name within 120 m).
"""
import csv, json, math, re, difflib, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent

MARKS = re.compile(r"[ัิ-ฺ็-๎]")  # vowels above/below, tone marks
def skel(s):
    s = MARKS.sub("", (s or "").lower())
    return re.sub(r"[^0-9a-z฀-๿]", "", s)

frames = {f"{r['burst']}_{int(r['item']):03d}": r for r in csv.DictReader(open(HERE / "frames.csv"))}
recs = json.load(open(HERE / "nearby.json"))
for r in recs:
    r["_sk"] = {skel(n) for n in [r.get("name"), r.get("nameTh"), r.get("nameEn"), *r.get("altNames", [])] if n and len(skel(n)) >= 3}

def dist(a, b, c, d):
    k = math.cos(math.radians(a)); return (((a - c) ** 2 + ((b - d) * k) ** 2) ** .5) * 111320

def name_hit(sk, r):
    for n in r["_sk"]:
        if len(n) >= 4 and (n in sk or (len(sk) >= 4 and sk in n and len(sk) >= .6 * len(n))):
            return n
        if difflib.SequenceMatcher(None, sk, n).ratio() >= .8:
            return n
    return None

reads = []  # (frame, tile, text, conf, sk)
import sys
for line in open(sys.argv[1] if len(sys.argv) > 1 else HERE / "ocr.jsonl"):
    try: d = json.loads(line)
    except ValueError: continue
    tile = Path(d["path"]).stem                 # GSAB2131_100_y-45_p3
    frame = "_".join(tile.split("_")[:2])
    for t in d.get("text", []):
        sk = skel(t["s"])
        if t["conf"] >= .5 and len(sk) >= 3 and re.search(r"[a-zก-ฮ]", sk):
            reads.append((frame, tile, t["s"], t["conf"], sk, t["box"]))

matches, unmatched = {}, []
for frame, tile, s, conf, sk, box in reads:
    fr = frames.get(frame)
    if not fr or not fr["lat"]:
        unmatched.append((frame, tile, s, conf, sk, None, box)); continue
    la, lo = float(fr["lat"]), float(fr["lon"])
    hit = None
    for r in recs:
        dd = dist(la, lo, r["lat"], r["lng"])
        if dd <= 120 and (n := name_hit(sk, r)):
            if not hit or dd < hit[1]: hit = (r, dd, n)
    if hit:
        r, dd, n = hit
        m = matches.setdefault(r["id"], {"rec": r, "reads": []})
        m["reads"].append((frame, tile, s, round(conf, 2), round(dd)))
    else:
        unmatched.append((frame, tile, s, conf, sk, (la, lo), box))

with open(HERE / "sign_matches.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "name", "cat", "record_to_frame_m", "times_read", "best_tile", "text_read"])
    for pid, m in sorted(matches.items(), key=lambda kv: -len(kv[1]["reads"])):
        best = max(m["reads"], key=lambda x: x[3])
        w.writerow([pid, m["rec"].get("nameTh") or m["rec"]["name"], "/".join(m["rec"].get("cat") or []),
                    min(x[4] for x in m["reads"]), len(m["reads"]), best[1], best[2]])

# cluster unmatched by skeleton across nearby frames
clusters = []
for u in unmatched:
    for c in clusters:
        if difflib.SequenceMatcher(None, u[4], c["sk"]).ratio() >= .8 and (
                u[5] is None or c["pos"] is None or dist(*u[5], *c["pos"]) < 80):
            c["reads"].append(u); break
    else:
        clusters.append({"sk": u[4], "pos": u[5], "reads": [u]})
with open(HERE / "sign_unmatched.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["text", "times_read", "frames", "best_conf", "lat", "lon", "best_tile", "box", "all_texts"])
    for c in sorted(clusters, key=lambda c: -len(c["reads"])):
        best = max(c["reads"], key=lambda x: (x[3], len(x[2])))
        w.writerow([best[2], len(c["reads"]), len({x[0] for x in c["reads"]}), round(best[3], 2),
                    *(c["pos"] or ("", "")), best[1], json.dumps(best[6]), " | ".join(sorted({x[2] for x in c["reads"]})[:6])])
print("reads", len(reads), "· records named on a sign", len(matches), "· unmatched clusters", len(clusters),
      "· seen in 2+ frames", sum(1 for c in clusters if len({x[0] for x in c['reads']}) >= 2))
