#!/usr/bin/env python3
"""NaN's ride photographs to Wikimedia Commons.

    python3 tools/commons.py stage              write build/commons/: one file page per picture + plan.json
    python3 tools/commons.py upload --test 50   first N not yet on Commons (the bot request's test run)
    python3 tools/commons.py upload             everything staged, once data/commons.json names the approval
    python3 tools/commons.py upload --if-ready  the nightly form: nothing without a login; the 50-file test run
                                                once Commons:Bots/Requests/<bot> exists; everything once the
                                                bot account carries the bot flag

Reads mot-dang's data/curated/own_pictures.json, the pool every ride writes. Uploads the
blurred publish copy, largest available. Left out, and counted:
  - subjects in HOLD (data/commons.json "hold")
  - at upload, a picture whose bytes Commons already holds (SHA-1)

Login: a Special:BotPasswords pair in the macOS keychain, service "commons-bot",
account "<User>@<botname>". Uploads go one per 6 s. data/commons.json records each upload.
"""
import argparse, hashlib, json, math, os, re, subprocess, sys, time, uuid
import http.cookiejar, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOTDANG = Path(os.environ.get("MOTDANG", Path.home() / "Developer/claude code projects/mot-dang"))
POOL = MOTDANG / "data/curated/own_pictures.json"
LEDGER = ROOT / "data/commons.json"
OUT = ROOT / "build/commons"
API = "https://commons.wikimedia.org/w/api.php"
UA = "NaN-field-commons/1.0 (https://motdang.net/field; peacocksettlement@proton.me)"
AUTHOR = "NaN Peacock"
PACE_S = 6

CITY = {"cm": ((18.7883, 98.9853), "Chiang Mai", "Chiang Mai Province"),
        "cr": ((19.9105, 99.8406), "Chiang Rai", "Chiang Rai Province")}
CITY_KM = 8
SUBJECT_CATS = {  # {city} is filled from CITY; a category Commons lacks is dropped at stage
    "spirit-house": ["Spirit houses in {city}", "Spirit houses in Thailand"],
    "shrine": ["Shrines in {city}"],
    "street-art": ["Street art in Thailand"],
    "market": ["Markets in {city}"],
    "merch": ["Amulets of Thailand"],
    "muay-thai": ["Muay Thai"],
    "tattoo": ["Tattoos in Thailand"],
}

def km(a, b):
    k = math.cos(math.radians(a[0]))
    return math.hypot(a[0] - b[0], (a[1] - b[1]) * k) * 111.32

def ledger():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"hold": ["merch", "tattoo", "muay-thai"], "approved": "", "user": "", "uploaded": {}}

def save(led):
    LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n")

def source(pick):
    """The largest blurred copy of a pick."""
    slug, date = pick["slug"], pick["date"]
    cands = [MOTDANG / "assets" / (pick["file"] + ext) for ext in ("", ".jpg")]
    cands += list((MOTDANG / "_incoming").glob("gopro-%s*/pass2*/publish/%s.jpg" % (date, slug)))
    cands = [c for c in cands if c.is_file()]
    return max(cands, key=lambda c: c.stat().st_size) if cands else None

def sha1(p):
    return hashlib.sha1(p.read_bytes()).hexdigest()

def api(params, opener=None, data=None, headers=None):
    params = dict(params, format="json", formatversion="2")
    h = {"User-Agent": UA}
    h.update(headers or {})
    if data is None:
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers=h)
    else:
        req = urllib.request.Request(API, data=data, headers=h)
    for attempt in range(4):
        try:
            with (opener or urllib.request.build_opener()).open(req, timeout=120) as r:
                return json.load(r)
        except OSError:
            if attempt == 3: raise
            time.sleep(10 * (attempt + 1))

def existing_cats(names):
    have = set()
    names = sorted(set(names))
    for i in range(0, len(names), 50):
        r = api({"action": "query", "titles": "|".join("Category:" + n for n in names[i:i + 50])})
        have |= {p["title"][9:] for p in r["query"]["pages"] if not p.get("missing")}
    return have

def on_commons(hashes):
    found = {}
    for h in hashes:
        r = api({"action": "query", "list": "allimages", "aisha1": h, "ailimit": 1})
        if r["query"]["allimages"]:
            found[h] = r["query"]["allimages"][0]["name"]
    return found

def bot_groups(user):
    r = api({"action": "query", "list": "users", "ususers": user, "usprop": "groups"})
    return r["query"]["users"][0].get("groups", []) if r["query"]["users"] else []

def page_exists(title):
    r = api({"action": "query", "titles": title})
    return not r["query"]["pages"][0].get("missing")

def clean_title(s):
    s = re.sub(r"[#<>\[\]|{}/:\\]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")

def filename(pick, where):
    tail = re.sub(r"^(ride|field)-\d{8}-", "", pick["slug"])
    t = "%s, %s, %s (%s).jpg" % (clean_title(pick["title"])[:150], where, pick["date"], tail)
    return t[0].upper() + t[1:]

def page(pick, cats, user):
    who = "[[User:%s|%s]]" % (user, AUTHOR) if user else AUTHOR
    desc = "{{en|1=%s}}" % (pick.get("description") or pick["title"])
    if pick.get("description_th"):
        desc += "\n{{th|1=%s}}" % pick["description_th"]
    if pick.get("signText"):
        desc += "\n{{th|1=ป้าย: %s}}" % pick["signText"]
    lines = ["=={{int:filedesc}}==", "{{Information", "|description=" + desc,
             "|date={{Taken on|%s|location=Thailand}}" % pick["date"],
             "|source={{own}} — GoPro Max 2, cut from a 360° frame; faces blurred",
             "|author=%s ([https://motdang.net motdang.net])" % who, "}}"]
    if pick.get("lat") is not None:
        lines.append("{{Location|%.6f|%.6f}}" % (pick["lat"], pick["lng"]))
    lines += ["", "=={{int:license-header}}==",
              "{{self|cc-by-4.0|attribution=%s (motdang.net)}}" % AUTHOR, ""]
    lines += ["[[Category:%s]]" % c for c in cats]
    return "\n".join(lines) + "\n"

def stage():
    led = ledger()
    hold = set(led["hold"])
    picks = json.loads(POOL.read_text())["picks"]
    OUT.mkdir(parents=True, exist_ok=True)
    skipped = {"hold": 0, "no file": 0, "uploaded": 0}
    plan, wanted = [], set()
    for p in picks:
        if p["slug"] in led["uploaded"]:
            skipped["uploaded"] += 1; continue
        if p.get("subject") in hold:
            skipped["hold"] += 1; continue
        pt = (p["lat"], p["lng"]) if p.get("lat") is not None else None
        src = source(p)
        if not src:
            skipped["no file"] += 1; continue
        prov = (p.get("place") or ["cm"])[0]
        centre, city, province = CITY.get(prov, CITY["cm"])
        in_city = pt is not None and km(pt, centre) < CITY_KM
        where = city if in_city else province
        cats = [where] + [c.format(city=city) for c in SUBJECT_CATS.get(p.get("subject"), [])]
        wanted |= set(cats)
        plan.append({"slug": p["slug"], "src": str(src), "sha1": sha1(src), "title": filename(p, where),
                     "cats": cats, "pick": p})
    have = existing_cats(wanted)
    keep = []
    for x in plan:
        cats = [c for c in x["cats"] if c in have]
        (OUT / (x["slug"] + ".wiki")).write_text(page(x.pop("pick"), cats, led["user"]))
        x["cats"] = cats
        keep.append(x)
    (OUT / "plan.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1))
    save(led)
    print("staged %d · left out: %s" % (len(keep), ", ".join("%s %d" % kv for kv in skipped.items() if kv[1])))

def credentials():
    r = subprocess.run(["security", "find-generic-password", "-s", "commons-bot", "-g"],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    acct = re.search(r'"acct"<blob>="([^"]+)"', r.stdout)
    pw = re.search(r'^password: "(.*)"$', r.stderr, re.M)
    return (acct.group(1), pw.group(1)) if acct and pw else None

def multipart(fields, fname, blob):
    b = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode())
    out.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                "Content-Type: image/jpeg\r\n\r\n" % (b, fname)).encode() + blob + b"\r\n")
    out.append(("--%s--\r\n" % b).encode())
    return b"".join(out), "multipart/form-data; boundary=" + b

def upload(test, if_ready):
    led = ledger()
    cred = credentials()
    if not cred:
        if if_ready: return
        sys.exit("no login: add a BotPasswords pair to the keychain as service commons-bot")
    bot = cred[0].split("@")[0]
    if if_ready and not test and not led["approved"]:
        if "bot" in bot_groups(bot):
            led["approved"] = "bot flag on User:" + bot; save(led)
        elif page_exists("Commons:Bots/Requests/" + bot):
            test = 50                             # the request is posted: its test run
        else:
            return
    if not test and not led["approved"]:
        sys.exit("no approval recorded: the bot account has no bot flag yet; use --test N")
    plan = json.loads((OUT / "plan.json").read_text())
    plan = [x for x in plan if x["slug"] not in led["uploaded"]]
    if test:
        plan = plan[:max(0, test - sum(1 for v in led["uploaded"].values() if v.get("test")))]
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    lt = api({"action": "query", "meta": "tokens", "type": "login"}, op)["query"]["tokens"]["logintoken"]
    r = api({}, op, urllib.parse.urlencode({"action": "login", "lgname": cred[0], "lgpassword": cred[1],
                                            "lgtoken": lt, "format": "json"}).encode())
    if r.get("login", {}).get("result") != "Success":
        sys.exit("login refused: %s" % r.get("login", {}).get("reason", r))
    token = api({"action": "query", "meta": "tokens"}, op)["query"]["tokens"]["csrftoken"]
    done = 0
    for x in plan:
        dup = on_commons([x["sha1"]])
        if dup:
            led["uploaded"][x["slug"]] = {"title": dup[x["sha1"]], "sha1": x["sha1"], "note": "already on Commons"}
            save(led); continue
        text = (OUT / (x["slug"] + ".wiki")).read_text()
        fields = {"action": "upload", "format": "json", "filename": x["title"], "text": text,
                  "comment": "Own work: ride photograph from Chiang Mai field mapping (motdang.net/field)",
                  "ignorewarnings": "0", "token": token}
        body, ctype = multipart(fields, x["title"], Path(x["src"]).read_bytes())
        r = api({}, op, body, {"Content-Type": ctype})
        res = r.get("upload", {})
        if res.get("result") == "Success":
            led["uploaded"][x["slug"]] = {"title": res["filename"], "sha1": x["sha1"],
                                          "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "test": bool(test)}
            save(led); done += 1
        else:
            print("NOT uploaded %s: %s" % (x["slug"], json.dumps(r.get("error") or res.get("warnings") or r)[:300]))
        time.sleep(PACE_S)
    print("uploaded %d of %d" % (done, len(plan)))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stage", "upload"])
    ap.add_argument("--test", type=int, default=0)
    ap.add_argument("--if-ready", action="store_true")
    a = ap.parse_args()
    stage() if a.cmd == "stage" else upload(a.test, a.if_ready)
