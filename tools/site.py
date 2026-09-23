#!/usr/bin/env python3
"""Build ภาคสนาม · Field into build/site/.

    SITE_URL=https://motdang.net/field python3 tools/site.py

The unit is COVERAGE, not the session. A session file (data/sessions/*.json, written
by tools/ingest.py) records what one outing saw: place ids, photographs, a track. Every
fact about a place — its name, page, district, pin — is read from mot-dang at build time,
so a place seen on forty rides is one row here and cannot drift from the directory.

Pages
  /                       totals across every session, the coverage map, the newest finds
  /areas/                 every district, how much of it the camera has seen
  /areas/<prov>-<amphoe>/ its tambon, the places seen there, its photographs
  /sessions/              the log, newest first
  /sessions/<id>/         one outing
  /photos/ /photos/<n>/   every photograph, newest first, 60 a page
  /how/  /data/           the method; the downloads

Links are root-relative from SITE_URL's path: motdang.net answers /field without its
trailing slash, and a relative link resolved from there lands one level too high.
"""
from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import fleet  # noqa: E402
import motdang_urls as mu  # noqa: E402

MD = Path(os.environ.get("MOTDANG", Path.home() / "Developer/claude code projects/mot-dang"))
SITE_URL = os.environ.get("SITE_URL", "https://motdang.net/field").rstrip("/")
CANON = os.environ.get("CANONICAL_URL", "https://motdang.net/field").rstrip("/")
GH_URL = "https://nanobotco.github.io/field"
BASE = urlparse(SITE_URL).path.rstrip("/") + "/"          # "/field/"
REPO = "https://github.com/NaNoBotCo/field"
MOTDANG = "https://motdang.net"
OUT = ROOT / "build" / "site"
SELF = "field"
FLEET = fleet.load(ROOT / "data" / "fleet.json")
CREDIT = "NaN Peacock · CC BY 4.0"
PER_PAGE = 60
PROV = {"cm": ("เชียงใหม่", "Chiang Mai"), "cr": ("เชียงราย", "Chiang Rai")}


def e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def t(th: str, en: str, tag: str = "span") -> str:
    return f'<{tag} lang="th">{th}</{tag}><{tag} lang="en">{en}</{tag}>'


def pair(th: str, en: str, tag: str = "p", cls: str = "") -> str:
    c = f' class="pair {cls}"' if cls else ' class="pair"'
    return f'<div{c}><{tag} lang="th">{th}</{tag}><{tag} lang="en">{en}</{tag}></div>'


def n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else str(x)


def fmt_date(d: str, lang: str) -> str:
    y, m, dd = (int(x) for x in d[:10].split("-"))
    th = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    en = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{dd} {th[m]} {y + 543}" if lang == "th" else f"{dd} {en[m]} {y}"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


# ------------------------------------------------------------------ the data
def load_sessions():
    out = []
    for p in sorted((ROOT / "data/sessions").glob("*.json")):
        s = json.loads(p.read_text())
        s.setdefault("id", p.stem)
        out.append(s)
    return sorted(out, key=lambda s: (s["date"], s["id"]), reverse=True)


SESSIONS = load_sessions()
RECS = mu.load(MD)
_ids = {r["id"] for s in SESSIONS for r in s["new"] + s["confirmed"]} | \
       {p["placeId"] for s in SESSIONS for p in s["photos"] if p.get("placeId")}
URL = mu.urls(MD, _ids)
BUILT = {i for i, u in URL.items() if (MD / "docs" / u).exists()}

_amph_en = {}
_polys = None


def _admin(r):
    """amphoe/tambon for a record: its own attrs, else mot-dang's polygons."""
    global _polys
    a = r.get("attrs") or {}
    if a.get("amphoe") and a.get("tambon"):
        return a["amphoe"], a["tambon"]
    if r.get("lat") is None:
        return a.get("amphoe"), a.get("tambon")
    sys.path.insert(0, str(MD))
    import derive
    if _polys is None:
        _polys = derive._load_polys()
    prov = r.get("province") or r["id"][:2]
    am = next((f["name"] for f in _polys.get(prov, {}).get("amphoe", []) if derive._contains(f, r["lat"], r["lng"])), None)
    tb = next((f["name"] for f in _polys.get(prov, {}).get("tambon", []) if derive._contains(f, r["lat"], r["lng"])), None)
    return a.get("amphoe") or am, a.get("tambon") or tb


for _f in json.loads((MD / "data/admin_boundaries.json").read_text())["levels"]["amphoe"]["features"]:
    _pr = _f.get("properties") or {}
    _amph_en[(_pr.get("province"), _pr.get("name"))] = _pr.get("nameEn") or ""

# every place the camera has seen, once
PLACES = {}
for s in reversed(SESSIONS):                         # oldest first, so first-seen is right
    pics = {p["placeId"]: p for p in s["photos"] if p.get("placeId")}
    for kind, rows in (("added", s["new"]), ("confirmed", s["confirmed"])):
        for row in rows:
            i = row["id"]; r = RECS.get(i)
            if not r:
                continue
            pl = PLACES.setdefault(i, {"id": i, "rec": r, "status": kind, "first": s["date"], "sessions": [], "photo": None})
            if s["id"] not in pl["sessions"]:
                pl["sessions"].append(s["id"])
            if i in pics and not pl["photo"]:
                pl["photo"] = pics[i]["file"]
for pl in PLACES.values():
    r = pl["rec"]
    pl["prov"] = r.get("province") or pl["id"][:2]
    pl["amphoe"], pl["tambon"] = _admin(r)
    pl["name"] = r.get("name") or r.get("nameEn") or pl["id"]
    pl["nameEn"] = r.get("nameEn") or ""

PHOTOS = [dict(p, session=s["id"], date=s["date"]) for s in SESSIONS for p in s["photos"]]

# the directory's own totals per district: the denominator of coverage
TOTAL = Counter(); TOTAL_TB = Counter()
for r in RECS.values():
    if r.get("lat") is None:
        continue
    a = r.get("attrs") or {}
    prov = r.get("province") or r["id"][:2]
    if a.get("amphoe"):
        TOTAL[(prov, a["amphoe"])] += 1
        if a.get("tambon"):
            TOTAL_TB[(prov, a["amphoe"], a["tambon"])] += 1


def area_key(prov, amphoe):
    return f"{prov}-{slugify(_amph_en.get((prov, amphoe)) or '') or slugify(amphoe) or 'x'}"


AREAS = defaultdict(list)
for pl in PLACES.values():
    if pl["amphoe"]:
        AREAS[(pl["prov"], pl["amphoe"])].append(pl)


def place_href(i):
    """Its Mot Dang page once that page is built; until then its pin on the map."""
    u = URL.get(i)
    if u and i in BUILT:
        return f"{MOTDANG}/{u}"
    r = RECS.get(i) or {}
    if r.get("lat") is not None:
        return f"{MOTDANG}/map.html#17/{r['lat']:.5f}/{r['lng']:.5f}"
    return f"{MOTDANG}/"


def totals():
    return {"sessions": len(SESSIONS),
            "km": round(sum((s["counts"].get("km") or 0) for s in SESSIONS), 1),
            "frames": sum(s["counts"]["frames"] for s in SESSIONS),
            "added": sum(1 for p in PLACES.values() if p["status"] == "added"),
            "confirmed": sum(1 for p in PLACES.values() if p["status"] == "confirmed"),
            "photos": len(PHOTOS), "areas": len(AREAS)}


# ------------------------------------------------------------------ the shell
LANG_JS = """<script>(function(){var r=document.documentElement,k='field-lang',v=null;
try{v=localStorage.getItem(k)}catch(_){}
if(!v){v=(navigator.language||'').toLowerCase().indexOf('th')===0?'th':'en'}
if(v!=='both')r.setAttribute('data-lang',v);
window.fieldLang=function(x){if(x==='both')r.removeAttribute('data-lang');else r.setAttribute('data-lang',x);
try{localStorage.setItem(k,x)}catch(_){}document.querySelectorAll('.langs button').forEach(function(b){
b.setAttribute('aria-pressed',b.dataset.l===x?'true':'false')})};})();</script>"""

TAIL_JS = """<script>(function(){var cur=document.documentElement.getAttribute('data-lang')||'both';
document.querySelectorAll('.langs button').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.l===cur?'true':'false');
b.addEventListener('click',function(){fieldLang(b.dataset.l)})});
if(!matchMedia('(prefers-reduced-motion: no-preference)').matches||!('IntersectionObserver'in window))return;
var io=new IntersectionObserver(function(es){es.forEach(function(x){if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target)}})},{rootMargin:'0px 0px -8% 0px'});
document.querySelectorAll('[data-rise]').forEach(function(el){el.classList.add('rise');io.observe(el)});
setTimeout(function(){document.querySelectorAll('.rise').forEach(function(el){el.classList.add('in')})},4000);
document.querySelectorAll('svg .route').forEach(function(p){p.style.setProperty('--len',Math.ceil(p.getTotalLength()))});
})();</script>"""


def page(path: str, title_th: str, title_en: str, body: str, desc: str, image: str = "") -> str:
    canon = f"{CANON}/{path}".replace("index.html", "")
    alt = f"{GH_URL}/{path}".replace("index.html", "")
    img = f"{SITE_URL}/{image}" if image else ""
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": f"{title_en} — Field",
          "inLanguage": ["th", "en"], "url": canon,
          "isPartOf": {"@type": "WebSite", "name": "ภาคสนาม · Field", "url": CANON + "/"},
          "creator": fleet.maker_ld(FLEET), "license": "https://creativecommons.org/licenses/by/4.0/"}
    og = (f'<meta property="og:image" content="{e(img)}"><meta name="twitter:card" content="summary_large_image">'
          if img else "")
    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title_th)} · {e(title_en)} — ภาคสนาม · Field</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canon)}">
<link rel="alternate" href="{e(alt)}">
<meta property="og:title" content="{e(title_en)} — ภาคสนาม · Field">
<meta property="og:description" content="{e(desc)}">
{og}
<meta name="theme-color" content="#d9381e">
<link rel="icon" href="{BASE}assets/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{BASE}assets/css/field.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
{LANG_JS}
</head>
<body>
<header class="bar"><div class="wrap">
<a class="brand" href="{BASE}"><i></i>ภาคสนาม <span class="small">Field</span></a>
<nav aria-label="site">
<a href="{BASE}areas/">{t("พื้นที่", "Areas")}</a>
<a href="{BASE}sessions/">{t("รอบ", "Sessions")}</a>
<a href="{BASE}photos/">{t("ภาพ", "Photos")}</a>
<a href="{BASE}how/">{t("วิธีทำ", "How")}</a>
</nav>
<div class="langs" role="group" aria-label="language"><button data-l="th">ไทย</button><button data-l="en">EN</button><button data-l="both">ทั้งคู่</button></div>
</div></header>
<main>
{body}
</main>
<footer><div class="wrap">
<p>{t("ภาพถ่ายและข้อมูลโดย NaN Peacock เผยแพร่แบบ", "Photographs and data by NaN Peacock, under")}
<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> · {t("โค้ดแบบ", "code under")} MIT ·
<a href="{REPO}">GitHub</a> · <a href="{MOTDANG}/">motdang.net</a> · <a href="{BASE}data/">{t("ข้อมูล", "data")}</a></p>
{fleet.maker_html(roster=FLEET, lang="en")}
{fleet.row_html(SELF, label="More from the same publisher", roster=FLEET)}
{fleet.support_html(roster=FLEET)}
</div></footer>
{TAIL_JS}
</body>
</html>
"""


def band(img: str, inner: str, cls: str = "") -> str:
    return (f'<section class="band {cls}" style="background-image:url({e(img)})">'
            f'<div class="in">{inner}</div><span class="cred">{e(CREDIT)}</span></section>')


def shot(href: str, img: str, title: str, sub: str = "") -> str:
    bg = f'<span class="bg" style="background-image:url({e(img)})"></span>' if img else ""
    cls = "shot" if img else "shot plain"
    sub_html = f"<small>{sub}</small>" if sub else ""
    return (f'<figure class="card" data-rise><a class="{cls}" href="{e(href)}">{bg}<span class="scrim"></span>'
            f'<span class="sp"></span><span class="tx">{title}{sub_html}</span></a></figure>')


def stat_cells(cells) -> str:
    return '<div class="stats wrap">' + "".join(
        f'<div class="stat {cls}" data-rise><b>{n(v)}</b>{t(th, en)}</div>' for cls, v, th, en in cells) + "</div>"


def place_card(pl) -> str:
    img = f"{BASE}{pl['photo']}" if pl.get("photo") else ""
    kind = (pl["rec"].get("attrs") or {}).get("kind") or "/".join(pl["rec"].get("cat") or [])
    where = pl.get("tambon") or pl.get("amphoe") or ""
    sub = e(kind) + (f" · {e(where)}" if where else "")
    return shot(place_href(pl["id"]), img, e(pl["name"]), sub)


def chips(places) -> str:
    return '<div class="chips">' + "".join(
        f'<a class="{"has" if p.get("photo") else ""}" href="{e(place_href(p["id"]))}">{e(p["name"])}</a>'
        for p in sorted(places, key=lambda p: p["name"])) + "</div>"


def wall(photos, rise=True) -> str:
    out = []
    for p in photos:
        href = place_href(p["placeId"]) if p.get("placeId") else BASE + p["file"]
        out.append(f'<figure{" data-rise" if rise else ""}><a href="{e(href)}"><img src="{BASE}{e(p["file"])}" '
                   f'alt="{e(p.get("description") or p.get("title"))}" loading="lazy" '
                   f'width="{p.get("width") or 1200}" height="{p.get("height") or 800}"></a>'
                   f'<figcaption>{t(e(p.get("description_th") or p.get("title")), e(p.get("description") or p.get("title")))}'
                   f' · {fmt_date(p["date"], "en")}</figcaption></figure>')
    return '<div class="wall">' + "".join(out) + "</div>"


# ------------------------------------------------------------------ the coverage map
def coverage_svg(places, tracks, h_max=620) -> str:
    """Every route and every place seen, drawn to one scale."""
    pts = [(p["rec"]["lng"], p["rec"]["lat"]) for p in places if p["rec"].get("lat") is not None]
    for tr in tracks:
        pts += tr
    if not pts:
        return ""
    xs = [x for x, _ in pts]; ys = [y for _, y in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = math.cos(math.radians((y0 + y1) / 2))
    W, pad = 1000, 30
    span_x = max((x1 - x0) * k, 2e-3); span_y = max(y1 - y0, 2e-3)
    sc = min((W - 2 * pad) / span_x, (h_max - 2 * pad) / span_y)
    H = int(span_y * sc + 2 * pad)
    P = lambda lo, la: (pad + (lo - x0) * k * sc, H - pad - (la - y0) * sc)  # noqa: E731
    lines = []
    for tr in tracks:
        step = max(1, len(tr) // 250)
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (P(*q) for q in tr[::step]))
        lines.append(f'<path class="glow" d="{d}"/><path class="route" d="{d}"/>')
    dots = []
    for i, p in enumerate(places):
        r = p["rec"]
        if r.get("lat") is None:
            continue
        x, y = P(r["lng"], r["lat"])
        cls = "new" if p["status"] == "added" else "seen"
        dots.append(f'<a href="{e(place_href(p["id"]))}"><circle class="dot {cls}" cx="{x:.1f}" cy="{y:.1f}" r="5" '
                    f'style="--i:{i % 60}"><title>{e(p["name"])}</title></circle></a>')
    kmbar = sc / 111.32
    bar = (f'<g transform="translate({pad},{H - 14})"><rect width="{kmbar:.1f}" height="4" fill="currentColor" opacity=".5"/>'
           f'<text class="lbl" x="{kmbar + 8:.0f}" y="6">1 km</text></g>') if kmbar < W * .6 else ""
    return (f'<figure class="map" data-rise><svg viewBox="0 0 {W} {H}" role="img" aria-label="coverage">'
            + "".join(lines) + "".join(dots) + bar + "</svg>"
            f'<figcaption class="legend"><span><i style="background:var(--accent)"></i>{t("เพิ่มจากป้าย", "added from its sign")}</span>'
            f'<span><i style="background:var(--leaf)"></i>{t("ยืนยันจากป้าย", "confirmed by its sign")}</span></figcaption></figure>')


def tracks_for(sessions, prov):
    out = []
    for s in sessions:
        if s.get("track") and (ROOT / s["track"]).exists() and s.get("province", "cm") == prov:
            coords = json.loads((ROOT / s["track"]).read_text())["features"][0]["geometry"]["coordinates"]
            out.append([tuple(c[:2]) for c in coords])
    return out


# ------------------------------------------------------------------ pages
def sessions_table(sessions, more=False) -> str:
    rows = "".join(
        f'<tr><td><a href="{BASE}sessions/{e(s["id"])}/">{t(fmt_date(s["date"], "th"), fmt_date(s["date"], "en"))}</a></td>'
        f'<td>{t(e(s.get("title_th") or s.get("where_th") or ""), e(s.get("title") or s.get("where") or ""))}</td>'
        f'<td class="mono">{e(s["counts"].get("km") or "—")}</td><td class="mono">+{n(s["counts"]["new"])}</td>'
        f'<td class="mono">{n(s["counts"]["confirmed"])}</td><td class="mono">{n(s["counts"]["photos"])}</td></tr>'
        for s in sessions)
    link = f'<p><a href="{BASE}sessions/">{t("ทั้งหมด →", "The whole log →")}</a></p>' if more else ""
    return f"""<section class="block" id="sessions"><div class="wrap">
<span class="kick">{t("รอบ", "Sessions")}</span>
<h2>{t("บันทึกภาคสนาม", "The field log")}</h2>
<table class="t"><thead><tr><th>{t("วันที่", "Date")}</th><th>{t("ที่ไหน", "Where")}</th><th>km</th><th>{t("เพิ่ม", "Added")}</th><th>{t("ยืนยัน", "Confirmed")}</th><th>{t("ภาพ", "Photos")}</th></tr></thead>
<tbody>{rows}</tbody></table>
{link}
</div></section>"""


def build_home() -> str:
    T = totals()
    hero = next((p["file"] for p in PHOTOS if not p.get("placeId")), PHOTOS[0]["file"] if PHOTOS else "")
    lead = band(f"{BASE}{hero}", f"""<span class="kicker">{t("มดแดง · ภาคเหนือ", "Mot Dang · the north")}</span>
<h1>ภาคสนาม<br><span lang="en" style="font-size:.45em;display:block">Field</span></h1>
{pair("กล้อง 360° บนมอเตอร์ไซค์หรือในมือ ถ่ายทุกป้ายที่ผ่าน เครื่องอ่าน คนตรวจ แล้วเติมลงแผนที่มดแดง",
      "A 360° camera, on a motorbike or in hand, photographs every sign it passes. A machine reads them, a person checks them, and they go onto Mot Dang's map.")}""", "hero tall")
    cells = [("hot", T["added"], "ร้านที่เพิ่มลงมดแดงจากป้ายของร้านเอง", "places added to Mot Dang from their own signs"),
             ("leaf", T["confirmed"], "ร้านในมดแดงที่ป้ายยืนยันชื่อ", "Mot Dang places confirmed by their signs"),
             ("", T["photos"], "ภาพ ใช้ได้ทั้งเว็บ", "photographs, usable across the site"),
             ("", T["areas"], "อำเภอที่กล้องไปถึง", "districts the camera has reached"),
             ("", T["sessions"], "รอบออกภาคสนาม", "sessions in the field"),
             ("", T["frames"], "เฟรม 360°", "360° frames")]
    maps = ""
    for prov in ("cm", "cr"):
        pls = [p for p in PLACES.values() if p["prov"] == prov]
        if pls:
            maps += (f'<h3>{t(PROV[prov][0], PROV[prov][1])} <span class="small">{n(len(pls))}</span></h3>'
                     + coverage_svg(pls, tracks_for(SESSIONS, prov)))
    newest = sorted((p for p in PLACES.values() if p["status"] == "added"),
                    key=lambda p: (p["first"], bool(p.get("photo"))), reverse=True)[:12]
    area_cards = ""
    for (pv, am), pls in sorted(AREAS.items(), key=lambda kv: -len(kv[1]))[:8]:
        pic = next((p["photo"] for p in pls if p.get("photo")), "")
        area_cards += shot(f"{BASE}areas/{area_key(pv, am)}/", f"{BASE}{pic}" if pic else "",
                           t(e(am), e(_amph_en.get((pv, am)) or am)),
                           t(f"{n(len(pls))} แห่ง · {PROV[pv][0]}", f"{n(len(pls))} places · {PROV[pv][1]}"))
    body = f"""{lead}
{stat_cells(cells)}
<section class="block" id="coverage"><div class="wrap">
<span class="kick">{t("ความครอบคลุม", "Coverage")}</span>
<h2>{t("ทุกเส้นทาง ทุกป้ายที่อ่านได้", "Every route, every sign read")}</h2>
{maps}
</div></section>
<section class="block" id="new"><div class="wrap">
<span class="kick">{t("ล่าสุด", "Newest")}</span>
<h2>{t("เพิ่งขึ้นแผนที่", "Just onto the map")}</h2>
<div class="cards">{''.join(place_card(p) for p in newest)}</div>
</div></section>
<section class="block"><div class="wrap">
<span class="kick">{t("พื้นที่", "Areas")}</span>
<h2>{t("อำเภอที่เห็นมากที่สุด", "The districts seen most")}</h2>
<div class="cards">{area_cards}</div>
<p><a href="{BASE}areas/">{t("ทุกอำเภอ →", "Every district →")}</a></p>
</div></section>
<section class="block"><div class="wrap">
<span class="kick">{t("ภาพ", "Photographs")}</span>
<h2>{t("ภาพล่าสุด", "The latest photographs")}</h2>
{wall(PHOTOS[:16])}
<p><a href="{BASE}photos/">{t(f"ทั้ง {n(len(PHOTOS))} ภาพ →", f"All {n(len(PHOTOS))} →")}</a></p>
</div></section>
{sessions_table(SESSIONS[:10], more=len(SESSIONS) > 10)}"""
    return page("index.html", "ภาคสนาม", "Field", body,
                f"Street-level capture for Mot Dang: {T['added']} places added from their own signs, "
                f"{T['confirmed']} confirmed, {T['photos']} photographs under CC BY 4.0.", hero)


def build_areas() -> str:
    rows = []
    for (pv, am), pls in sorted(AREAS.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        tot = TOTAL.get((pv, am)) or 0
        photo = sum(1 for p in pls if p.get("photo"))
        pct = f"{100 * len(pls) / tot:.1f}%" if tot else "—"
        rows.append(f'<tr><td><a href="{BASE}areas/{area_key(pv, am)}/">{t(e(am), e(_amph_en.get((pv, am)) or am))}</a></td>'
                    f'<td>{t(PROV[pv][0], PROV[pv][1])}</td><td class="mono">{n(len(pls))}</td><td class="mono">{n(photo)}</td>'
                    f'<td class="mono">{n(tot)}</td><td class="mono">{pct}</td></tr>')
    body = f"""<section class="block"><div class="wrap">
<span class="kick">{t("พื้นที่", "Areas")}</span>
<h1>{t("กล้องไปถึงไหนแล้ว", "How much the camera has seen")}</h1>
{pair("เห็นแล้ว = ร้านที่ป้ายยืนยันหรือเพิ่มจากป้าย · ในมดแดง = ร้านที่มีหมุดในอำเภอนั้น",
      "Seen = places confirmed or added from their signs · In Mot Dang = places with a pin in that district", cls="lede")}
<table class="t"><thead><tr><th>{t("อำเภอ", "District")}</th><th>{t("จังหวัด", "Province")}</th><th>{t("เห็นแล้ว", "Seen")}</th><th>{t("มีภาพ", "With photo")}</th><th>{t("ในมดแดง", "In Mot Dang")}</th><th>%</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</div></section>"""
    return page("areas/index.html", "พื้นที่", "Areas", body, "Coverage by district.")


def build_area(pv, am, pls) -> str:
    en = _amph_en.get((pv, am)) or am
    by_tb = defaultdict(list)
    for p in pls:
        by_tb[p.get("tambon") or "—"].append(p)
    tb_rows = "".join(
        f'<tr><td>{e(tb)}</td><td class="mono">{n(len(x))}</td><td class="mono">{n(sum(1 for p in x if p.get("photo")))}</td>'
        f'<td class="mono">{n(TOTAL_TB.get((pv, am, tb)) or 0)}</td></tr>'
        for tb, x in sorted(by_tb.items(), key=lambda kv: -len(kv[1])))
    with_pic = sorted((p for p in pls if p.get("photo")), key=lambda p: p["name"])
    ids = {x["id"] for x in pls}
    pics = [p for p in PHOTOS if p.get("placeId") in ids]
    body = f"""<section class="block"><div class="wrap">
<span class="kick">{t(PROV[pv][0], PROV[pv][1])}</span>
<h1>{t(e(am), e(en))}</h1>
{pair(f"เห็นแล้ว {n(len(pls))} แห่ง จาก {n(TOTAL.get((pv, am)) or 0)} ในมดแดง",
      f"{n(len(pls))} places seen, of {n(TOTAL.get((pv, am)) or 0)} Mot Dang holds here", cls="lede")}
{coverage_svg(pls, [])}
<h2>{t("ตำบล", "Tambon")}</h2>
<table class="t"><thead><tr><th>{t("ตำบล", "Tambon")}</th><th>{t("เห็นแล้ว", "Seen")}</th><th>{t("มีภาพ", "With photo")}</th><th>{t("ในมดแดง", "In Mot Dang")}</th></tr></thead><tbody>{tb_rows}</tbody></table>
<h2>{t("มีภาพ", "With a photograph")}</h2>
<div class="cards">{''.join(place_card(p) for p in with_pic)}</div>
<h2>{t("ทั้งหมดที่เห็น", "Everything seen")}</h2>
{chips(pls)}
</div></section>"""
    return page(f"areas/{area_key(pv, am)}/index.html", am, en, body, f"{en}: {len(pls)} places seen.",
                pics[0]["file"] if pics else "")


def build_session(s) -> str:
    c = s["counts"]
    new_ids = {r["id"] for r in s["new"]}
    pls = [PLACES[r["id"]] for r in s["new"] + s["confirmed"] if r["id"] in PLACES]
    hero = s.get("hero") or next((p["file"] for p in s["photos"] if not p.get("placeId")),
                                 s["photos"][0]["file"] if s["photos"] else "")
    title_th = s.get("title_th") or s.get("where_th") or fmt_date(s["date"], "th")
    title_en = s.get("title") or s.get("where") or fmt_date(s["date"], "en")
    head = band(f"{BASE}{hero}", f'<span class="kicker">{t(fmt_date(s["date"], "th"), fmt_date(s["date"], "en"))} · '
                f'{e(s.get("camera", ""))}</span><h1>{t(e(title_th), e(title_en))}</h1>', "hero") if hero else ""
    last = ("", c.get("km"), "กม.", "km") if c.get("km") else ("", c["frames"], "เฟรม", "frames")
    cells = [("hot", c["new"], "เพิ่มจากป้าย", "added from signs"), ("leaf", c["confirmed"], "ยืนยันจากป้าย", "confirmed by signs"),
             ("", c["photos"], "ภาพ", "photographs"), last]
    added = [p for p in pls if p["id"] in new_ids]
    body = f"""{head}
{stat_cells(cells)}
<section class="block"><div class="wrap">
{coverage_svg(pls, tracks_for([s], s.get("province", "cm")))}
<h2>{t("เพิ่มลงมดแดง", "Added to Mot Dang")}</h2>
<div class="cards">{''.join(place_card(p) for p in sorted(added, key=lambda p: (not p.get("photo"), p["name"])))}</div>
<h2>{t("ยืนยันแล้ว", "Confirmed")}</h2>
{chips([p for p in pls if p["id"] not in new_ids])}
<h2>{t("ภาพ", "Photographs")}</h2>
{wall([dict(p, date=s["date"]) for p in s["photos"]], rise=False)}
<p class="small"><a href="{BASE}data/sessions/{e(s["id"])}.json">{t("ข้อมูลรอบนี้ (JSON)", "This session's data (JSON)")}</a></p>
</div></section>"""
    return page(f"sessions/{s['id']}/index.html", title_th, title_en, body,
                f"{title_en}: {c['new']} places added, {c['confirmed']} confirmed, {c['photos']} photographs.", hero)


def build_photos():
    pages = max(1, math.ceil(len(PHOTOS) / PER_PAGE))
    for k in range(pages):
        chunk = PHOTOS[k * PER_PAGE:(k + 1) * PER_PAGE]
        nav = " ".join(f'<a href="{BASE}photos/{"" if i == 0 else str(i + 1) + "/"}"'
                       f'{" aria-current=page" if i == k else ""}>{i + 1}</a>' for i in range(pages)) if pages > 1 else ""
        body = f"""<section class="block"><div class="wrap">
<span class="kick">{t("ภาพ", "Photographs")}</span>
<h1>{t(f"{n(len(PHOTOS))} ภาพจากภาคสนาม", f"{n(len(PHOTOS))} photographs from the field")}</h1>
{pair("ใช้ได้ทุกที่ ใส่ชื่อ NaN Peacock และ CC BY 4.0 · ภาพของร้านพาไปหน้าร้านนั้นในมดแดง",
      "Use them anywhere with the credit NaN Peacock, CC BY 4.0. A photo of a place links to its Mot Dang page.", cls="lede")}
{wall(chunk)}
<p class="pager">{nav}</p>
</div></section>"""
        path = f"photos/{'' if k == 0 else str(k + 1) + '/'}index.html"
        write(path, page(path, "ภาพ", "Photographs", body, f"{len(PHOTOS)} street photographs under CC BY 4.0."))
    return pages


def build_how() -> str:
    ex = next((s["example"] for s in SESSIONS if s.get("example")), None)
    steps = ""
    if ex:
        items = [(ex["view"], "", "เฟรม 360° ถูกตัดเป็นภาพแบน มองออกข้างทาง", "The 360° frame, cut flat, looking at the roadside"),
                 (ex["tile"], "fit", "ตัดเป็นช่องเล็ก 16 ช่องต่อเฟรม ให้เครื่องอ่านป้ายที่ความละเอียดเต็ม — กรอบแดงคือที่มันเจอข้อความ",
                  "Cut again into 16 tiles a frame so the reader sees signs at full resolution — the red box is where it found text"),
                 (ex["crop"], "fit", f'เครื่องอ่านได้ <span class="read">{e(ex["read"])}</span> ไม่ตรงกับร้านไหนในมดแดง คนอ่านซ้ำจากภาพ',
                  f'The machine read <span class="read">{e(ex["read"])}</span>, matched nothing in Mot Dang, and a person read the crop again'),
                 (ex["photo"], "", f'<a href="{e(place_href(ex["id"]))}">{e(ex["name"])}</a> อยู่ในมดแดงแล้ว พร้อมหมุดและรูป',
                  f'<a href="{e(place_href(ex["id"]))}">{e(ex["name"])}</a> is on Mot Dang now, with a pin and this photograph')]
        steps = '<div class="steps" tabindex="0">' + "".join(
            f'<article class="step"><figure class="{c}"><img src="{BASE}{e(img)}" alt="" loading="lazy"></figure>'
            f'<div class="t"><span class="n">0{i}</span>{pair(th, en)}</div></article>'
            for i, (img, c, th, en) in enumerate(items, 1)) + "</div>"
    body = f"""<section class="block"><div class="wrap">
<span class="kick">{t("วิธีทำ", "How")}</span>
<h1>{t("จากเฟรมสู่หมุดบนแผนที่", "From a frame to a pin")}</h1>
{steps}
<ol class="lede">
<li>{t("กล้องอัปโหลดขึ้นคลาวด์ของ GoPro เฟรมเป็นภาพ 360° ขนาด 7680×3840 ส่วนใหญ่มีพิกัด GPS", "The camera uploads to GoPro's cloud; each frame is a 7680×3840 360° image, most with a GPS fix.")}</li>
<li>{t("แต่ละเฟรมถูกตัดเป็น 16 ช่องแบน ให้ Apple Vision อ่านข้อความไทยและอังกฤษ", "Each frame is cut into 16 flat tiles and Apple Vision reads the Thai and English on them.")}</li>
<li>{t("ข้อความที่ตรงกับชื่อในมดแดงระยะ 120 ม. ยืนยันร้านนั้น", "A line that matches a Mot Dang name within 120 m confirms that place.")}</li>
<li>{t("ที่ไม่ตรงกับอะไร คนอ่านจากภาพ ป้ายที่มีชื่อและประเภทบนหน้าร้านเองกลายเป็นรายการใหม่", "What matches nothing is read again by a person; a name and a trade on the premises' own sign become a new listing.")}</li>
<li>{t("ภาพถูกปรับให้ตรง เบลอหน้าคน แล้วขึ้นหน้าร้านและคลังภาพของมดแดง", "Photographs are straightened, faces blurred, and they go onto the place's page and Mot Dang's picture pool.")}</li>
</ol>
<p><a href="{REPO}">{t("โค้ดทั้งหมดบน GitHub →", "All the code on GitHub →")}</a></p>
</div></section>"""
    return page("how/index.html", "วิธีทำ", "How", body, "How a 360° frame becomes a pin on Mot Dang.")


def build_data() -> str:
    items = [("data/places.csv", "ทุกร้านที่เห็น", "Every place seen", "CSV"),
             ("data/photos.json", "ทุกภาพ", "Every photograph", "JSON"),
             ("data/tracks.geojson", "ทุกเส้นทาง", "Every route", "GeoJSON")]
    lis = "".join(f'<li><a href="{BASE}{p}" download><b>{t(th, en)}</b><span>{f} · {p}</span></a></li>' for p, th, en, f in items)
    body = f"""<section class="block"><div class="wrap">
<span class="kick">{t("ข้อมูล", "Data")}</span>
<h1>{t("เอาไปใช้ได้", "Take it")}</h1>
{pair("ข้อมูลและภาพเผยแพร่แบบ CC BY 4.0 ใส่ชื่อ NaN Peacock เมื่อนำไปใช้", "Data and photographs are CC BY 4.0: credit NaN Peacock when you use them.", cls="lede")}
<ul class="dl">{lis}<li><a href="{REPO}"><b>{t("โค้ดทั้งหมด", "All the code")}</b><span>GitHub · MIT</span></a></li></ul>
</div></section>"""
    return page("data/index.html", "ข้อมูล", "Data", body, "Field's data under CC BY 4.0.")


def write(path: str, text: str):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(ROOT / "assets", OUT / "assets")
    shutil.copy2(ROOT / "tools/bands.css", OUT / "assets/css/bands.css")
    shutil.copytree(ROOT / "photos", OUT / "photos")
    (OUT / "data").mkdir()
    shutil.copytree(ROOT / "data/sessions", OUT / "data/sessions")
    with open(OUT / "data/places.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "status", "name", "name_en", "province", "amphoe", "tambon", "lat", "lng", "first_seen",
                    "sessions", "photo", "motdang_url"])
        for p in sorted(PLACES.values(), key=lambda p: p["id"]):
            r = p["rec"]
            w.writerow([p["id"], p["status"], p["name"], p["nameEn"], p["prov"], p.get("amphoe") or "", p.get("tambon") or "",
                        r.get("lat"), r.get("lng"), p["first"], len(p["sessions"]),
                        f"{SITE_URL}/{p['photo']}" if p.get("photo") else "",
                        f"{MOTDANG}/{URL[p['id']]}" if p["id"] in URL else ""])
    (OUT / "data/photos.json").write_text(json.dumps(
        {"licence": "CC BY 4.0", "credit": "NaN Peacock",
         "photos": [dict(p, url=f"{SITE_URL}/{p['file']}") for p in PHOTOS]}, ensure_ascii=False, indent=1))
    feats = []
    for s in SESSIONS:
        if s.get("track") and (ROOT / s["track"]).exists():
            f = json.loads((ROOT / s["track"]).read_text())["features"][0]
            f["properties"]["session"] = s["id"]
            feats.append(f)
    (OUT / "data/tracks.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    write("index.html", build_home())
    write("areas/index.html", build_areas())
    for (pv, am), pls in AREAS.items():
        write(f"areas/{area_key(pv, am)}/index.html", build_area(pv, am, pls))
    write("sessions/index.html", page("sessions/index.html", "รอบ", "Sessions", sessions_table(SESSIONS),
                                      f"{len(SESSIONS)} sessions in the field."))
    for s in SESSIONS:
        write(f"sessions/{s['id']}/index.html", build_session(s))
    npages = build_photos()
    write("how/index.html", build_how())
    write("data/index.html", build_data())

    urls = (["", "areas/", "sessions/", "photos/", "how/", "data/"]
            + [f"areas/{area_key(pv, am)}/" for pv, am in AREAS]
            + [f"sessions/{s['id']}/" for s in SESSIONS] + [f"photos/{k}/" for k in range(2, npages + 1)])
    today = date.today().isoformat()
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{CANON}/{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {CANON}/sitemap.xml\n")
    T = totals()
    write("llms.txt", f"# ภาคสนาม · Field\n\n> Street-level capture feeding Mot Dang, the Thai-first directory of Chiang Mai "
          f"and Chiang Rai. A 360° camera on a motorbike or in hand; each frame is cut into tiles, the signs are read by Apple "
          f"Vision (Thai + English) and checked by a person; names that match a Mot Dang record confirm it, names that match "
          f"nothing become new records with a pin.\n\n- Sessions: {T['sessions']}\n- Places added: {T['added']} · confirmed: "
          f"{T['confirmed']} · districts reached: {T['areas']}\n- Photographs: {T['photos']}\n- Data: {CANON}/data/places.csv, "
          f"{CANON}/data/photos.json, {CANON}/data/tracks.geojson\n- Licence: data and photographs CC BY 4.0 (credit NaN "
          f"Peacock); code MIT\n- Code: {REPO}\n")
    write("humans.txt", "Photographs, riding and direction: NaN Peacock\nStudio: hongdam.net — Chiang Rai\n")
    fleet.decorate(OUT, SELF, roster=FLEET)
    print(f"built {SITE_URL}: {len(list(OUT.rglob('*.html')))} pages · {T['sessions']} sessions · {len(PLACES)} places · "
          f"{len(AREAS)} districts · {len(PHOTOS)} photographs · {len(BUILT)}/{len(URL)} place pages built on motdang")


if __name__ == "__main__":
    main()
