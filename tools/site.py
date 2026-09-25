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
# spirit houses, shrines and cloth-wrapped trees: points with a picture, not directory listings
POINTS = [dict(p, session=s["id"], date=s["date"]) for s in SESSIONS for p in s.get("points", [])]
POINT_KINDS = {  # key: (Thai, English, plural Thai, plural English, colour)
    "spirit-house": ("ศาลพระภูมิ ศาลเจ้าที่", "Spirit house", "ศาลพระภูมิ ศาลเจ้าที่", "Spirit houses", "var(--accent2)"),
    "ribbon-tree": ("ต้นไม้ผูกผ้า", "Cloth-wrapped tree", "ต้นไม้ผูกผ้า", "Cloth-wrapped trees", "var(--leaf)"),
    "shrine": ("ศาล", "Shrine", "ศาลอื่น ๆ", "Other shrines", "var(--sky)")}
# markets and pictures kept for how they look
SCENE_KINDS = (("street-art", "ศิลปะริมถนน", "Street art"), ("market", "ตลาด", "Markets"),
               ("merch", "ของในตลาดพระ", "At the amulet market"), ("aesthetic", "ภาพเมือง", "Scenes"),
               ("tattoo", "สัก", "Tattoo"), ("muay-thai", "มวยไทย", "Muay thai"))
SCENES = [p for p in PHOTOS if p.get("subject") in {k for k, _, _ in SCENE_KINDS}]

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
            "photos": len(PHOTOS), "areas": len(AREAS), "points": len(POINTS), "scenes": len(SCENES),
            "spirit": sum(1 for p in POINTS if p["kind"] == "spirit-house"),
            "trees": sum(1 for p in POINTS if p["kind"] == "ribbon-tree")}


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
})();</script>
<script>(function(){
/* nearest first: motdang.net's edge writes the reader's city into meta md-where; the 📍 button asks for an exact fix */
var lists=document.querySelectorAll('[data-near]');if(!lists.length)return;
function km(a,b,c,d){var r=Math.PI/180,x=Math.sin((c-a)*r/2),y=Math.sin((d-b)*r/2);
return 12742*Math.asin(Math.sqrt(x*x+Math.cos(a*r)*Math.cos(c*r)*y*y))}
function lab(k){return k<1?Math.round(k*1000/10)*10+' m':(k<10?k.toFixed(1):Math.round(k))+' km'}
function near(la,lo,th,en){lists.forEach(function(l){var it=[].slice.call(l.children).filter(function(c){return c.dataset.lat});
it.forEach(function(c){c._k=km(la,lo,+c.dataset.lat,+c.dataset.lng);var s=c.querySelector('.dist');if(s)s.textContent=lab(c._k)});
it.sort(function(a,b){return a._k-b._k}).forEach(function(c){l.appendChild(c)})});
document.querySelectorAll('.near-note').forEach(function(n){n.innerHTML='<span lang="th">ใกล้'+th+'ก่อน</span><span lang="en">Nearest to '+en+' first</span>'})}
var m=document.querySelector('meta[name=md-where]');
if(m){var p=(m.content||'').split('|');if(p.length>2&&!isNaN(+p[1])&&!isNaN(+p[2])&&km(+p[1],+p[2],18.79,98.99)<300){var c=p[0]||'';near(+p[1],+p[2],c?' '+c+' ':'คุณ',c||'you')}}
document.querySelectorAll('.locate').forEach(function(b){if(!navigator.geolocation){b.hidden=true;return}
b.addEventListener('click',function(){b.disabled=true;navigator.geolocation.getCurrentPosition(function(q){b.disabled=false;
near(q.coords.latitude,q.coords.longitude,'คุณ','you')},function(){b.disabled=false},{enableHighAccuracy:true,timeout:10000})})});
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
<html lang="th" translate="no" class="notranslate">
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
<meta name="google" content="notranslate">
<meta name="robots" content="notranslate">
<script>if(/[.]translate[.]goog$/.test(location.hostname))location.replace("https://"+location.hostname.slice(0,-15).replace(/--/g,"~").replace(/-/g,".").replace(/~/g,"-")+location.pathname+location.search.replace(/([?&])_x_tr_[^&]*/g,"$1").replace(/[?&]+$/,"").replace(/[?]&+/,"?")+location.hash)</script>
</head>
<body>
<header class="bar"><div class="wrap">
<a class="brand" href="{BASE}"><i></i>ภาคสนาม <span class="small">Field</span></a>
<nav aria-label="site">
<a href="{BASE}areas/">{t("พื้นที่", "Areas")}</a>
<a href="{BASE}sessions/">{t("รอบ", "Sessions")}</a>
<a href="{BASE}photos/">{t("ภาพ", "Photos")}</a>
<a href="{BASE}san/">{t("ศาล · ต้นไม้", "Shrines · trees")}</a>
<a href="{BASE}scenes/">{t("ตลาด · ภาพเมือง", "Markets · scenes")}</a>
<a href="{BASE}how/">{t("วิธีทำ", "How")}</a>
<a href="{BASE}about/">{t("แผน · ต้นทุน", "Plan · costs")}</a>
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
    cells = [c for c in cells if c[1]]          # a kind the camera has not met yet is left off, not shown as 0
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


def near_bar() -> str:
    """The line above a nearest-first list, and the button that asks for an exact fix."""
    return (f'<div class="nearbar"><span class="near-note small"></span>'
            f'<button class="locate" type="button">📍 {t("เรียงจากที่ฉันอยู่", "Sort from where I am")}</button></div>')


def point_card(p) -> str:
    """A spirit house, shrine or tree: the picture is the link, its kind and distance lie on it."""
    th, en = POINT_KINDS.get(p["kind"], ("", "", "", "", ""))[:2]
    href = f"{MOTDANG}/map.html#18/{p['lat']:.5f}/{p['lng']:.5f}" if p.get("lat") is not None else f"{BASE}{p['file']}"
    ll = f' data-lat="{p["lat"]:.6f}" data-lng="{p["lng"]:.6f}"' if p.get("lat") is not None else ""
    return (f'<figure class="card pt" id="{e(p["slug"])}"{ll} data-rise><a class="shot" href="{e(href)}">'
            f'<span class="bg" style="background-image:url({BASE}{e(p["file"])})"></span><span class="scrim"></span>'
            f'<span class="sp"></span><span class="tx">{t(e(p.get("title_th") or th), e(p.get("title") or en))}'
            f'<small>{t(th, en)}<span class="dist"></span></small></span></a></figure>')


def scene_card(p) -> str:
    ll = f' data-lat="{p["lat"]:.6f}" data-lng="{p["lng"]:.6f}"' if p.get("lat") is not None else ""
    k = {k: (th, en) for k, th, en in SCENE_KINDS}.get(p.get("subject"), ("", ""))
    return (f'<figure class="card"{ll} data-rise><a class="shot" href="{BASE}{e(p["file"])}">'
            f'<span class="bg" style="background-image:url({BASE}{e(p["file"])})"></span><span class="scrim"></span>'
            f'<span class="sp"></span><span class="tx">{t(e(p.get("description_th") or p.get("title")), e(p.get("description") or p.get("title")))}'
            f'<small>{t(*k)}<span class="dist"></span></small></span></a></figure>')


def points_svg(points, tracks, h_max=620) -> str:
    """Every point on one drawn map, coloured by kind, over the routes that found them."""
    pts = [(p["lng"], p["lat"]) for p in points if p.get("lat") is not None]
    if not pts:
        return ""
    allp = pts + [q for tr in tracks for q in tr]
    xs = [x for x, _ in allp]; ys = [y for _, y in allp]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = math.cos(math.radians((y0 + y1) / 2))
    W, pad = 1000, 30
    sc = min((W - 2 * pad) / max((x1 - x0) * k, 2e-3), (h_max - 2 * pad) / max(y1 - y0, 2e-3))
    H = int(max(y1 - y0, 2e-3) * sc + 2 * pad)
    P = lambda lo, la: (pad + (lo - x0) * k * sc, H - pad - (la - y0) * sc)  # noqa: E731
    lines = []
    for tr in tracks:
        step = max(1, len(tr) // 250)
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (P(*q) for q in tr[::step]))
        lines.append(f'<path class="glow" d="{d}"/><path class="route faint" d="{d}"/>')
    dots = []
    for i, p in enumerate(points):
        if p.get("lat") is None:
            continue
        x, y = P(p["lng"], p["lat"])
        col = POINT_KINDS.get(p["kind"], ("", "", "", "", "var(--accent)"))[4]
        dots.append(f'<a href="#{e(p["slug"])}"><circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="6" style="fill:{col};--i:{i % 60}">'
                    f'<title>{e(p.get("title") or p["kind"])}</title></circle></a>')
    kinds = sorted({p["kind"] for p in points}, key=list(POINT_KINDS).index)
    legend = "".join(f'<span><i style="background:{POINT_KINDS[k][4]}"></i>{t(POINT_KINDS[k][2], POINT_KINDS[k][3])}</span>'
                     for k in kinds if k in POINT_KINDS)
    return (f'<figure class="map" data-rise><svg viewBox="0 0 {W} {H}" role="img" aria-label="points">'
            + "".join(lines) + "".join(dots) + f'</svg><figcaption class="legend">{legend}</figcaption></figure>')


def build_san() -> str:
    pts = sorted(POINTS, key=lambda p: (-(p.get("quality") or 0), p["slug"]))
    T = totals()
    hero = next((p["file"] for p in pts if p["kind"] == "spirit-house"), pts[0]["file"] if pts else "")
    head = band(f"{BASE}{hero}", f"""<span class="kicker">{t("ภาคสนาม", "Field")}</span>
<h1>{t("ศาล ต้นไม้ผูกผ้า", "Spirit houses, shrines, cloth-wrapped trees")}</h1>
{pair("ศาลและต้นไม้ผูกผ้าที่เห็นจากถนน ปักหมุดตรงที่ถ่าย", "Spirit houses, shrines and cloth-wrapped trees seen from the road, each pinned where it was photographed")}""",
                "hero") if hero else ""
    cells = [("hot", T["spirit"], "ศาลพระภูมิ ศาลเจ้าที่", "spirit houses"), ("leaf", T["trees"], "ต้นไม้ผูกผ้า", "cloth-wrapped trees"),
             ("", T["points"] - T["spirit"] - T["trees"], "ศาลอื่น ๆ", "other shrines")]
    groups = ""
    for k, (th, en, pth, pen, _) in POINT_KINDS.items():
        rows = [p for p in pts if p["kind"] == k]
        if rows:
            groups += (f'<h2 id="{k}">{t(pth, pen)} <span class="small">{n(len(rows))}</span></h2>'
                       f'{near_bar()}<div class="cards" data-near>{"".join(point_card(p) for p in rows)}</div>')
    body = f"""{head}
{stat_cells(cells)}
<section class="block"><div class="wrap">
{points_svg(pts, tracks_for(SESSIONS, "cm"))}
{pair("แตะหมุดเพื่อเลื่อนไปที่ภาพ แตะภาพเพื่อเปิดจุดนั้นบนแผนที่มดแดง", "Tap a dot to jump to its picture; tap a picture to open that spot on Mot Dang's map", cls="small")}
{groups}
<p class="small"><a href="{BASE}data/points.geojson" download>{t("จุดทั้งหมดในไฟล์เดียว (GeoJSON)", "The points in one file (GeoJSON)")}</a> ·
<a href="{MOTDANG}/san.html">{t("ศาลหลักของเมืองในมดแดง →", "The city's main shrines on Mot Dang →")}</a></p>
</div></section>"""
    return page("san/index.html", "ศาล ต้นไม้ผูกผ้า", "Spirit houses, shrines, trees", body,
                f"{T['spirit']} spirit houses and {T['trees']} cloth-wrapped trees seen from the road in Chiang Mai, "
                f"pinned where each was photographed.", hero)


def build_scenes() -> str:
    sc = sorted(SCENES, key=lambda p: (-(p.get("quality") or 0), p["slug"]))
    hero = sc[0]["file"] if sc else ""
    head = band(f"{BASE}{hero}", f"""<span class="kicker">{t("ภาคสนาม", "Field")}</span>
<h1>{t("ตลาด ภาพเมือง ศิลปะริมถนน", "Markets, scenes, street art")}</h1>
{pair("ภาพที่เก็บไว้เพราะความงาม ตลาด ภาพวาดบนกำแพง ตู้ไฟ และชีวิตริมถนน ปักหมุดตรงที่ถ่าย", "Pictures kept for how they look: markets, murals, painted boxes, light, streets, each pinned where it was taken")}""",
                "hero") if hero else ""
    groups = ""
    for k, th, en in SCENE_KINDS:
        rows = [p for p in sc if p.get("subject") == k]
        if rows:
            groups += (f'<h2 id="{k}">{t(th, en)} <span class="small">{n(len(rows))}</span></h2>'
                       f'{near_bar()}<div class="cards" data-near>{"".join(scene_card(p) for p in rows)}</div>')
    body = f"""{head}
<section class="block"><div class="wrap">
{groups}
</div></section>"""
    return page("scenes/index.html", "ตลาด ภาพเมือง ศิลปะริมถนน", "Markets, scenes, street art", body,
                f"{len(sc)} photographs of markets, street art and streets in Chiang Mai, CC BY 4.0, pinned where each was taken.", hero)


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
             ("", T["spirit"], "ศาลพระภูมิ ศาลเจ้าที่ ปักหมุดแล้ว", "spirit houses pinned"),
             ("", T["trees"], "ต้นไม้ผูกผ้า ปักหมุดแล้ว", "cloth-wrapped trees pinned"),
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
{home_teasers()}
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


def home_teasers() -> str:
    out = ""
    pts = sorted(POINTS, key=lambda p: -(p.get("quality") or 0))[:8]
    if pts:
        out += f"""<section class="block" id="san"><div class="wrap">
<span class="kick">{t("ศาล · ต้นไม้", "Shrines · trees")}</span>
<h2>{t("ศาลริมทาง", "Roadside spirit houses")}</h2>
{near_bar()}<div class="cards" data-near>{"".join(point_card(p) for p in pts)}</div>
<p><a href="{BASE}san/">{t(f"ทั้ง {n(len(POINTS))} จุด →", f"All {n(len(POINTS))} →")}</a></p>
</div></section>"""
    sc = sorted(SCENES, key=lambda p: -(p.get("quality") or 0))[:8]
    if sc:
        out += f"""<section class="block" id="scenes"><div class="wrap">
<span class="kick">{t("ตลาด · ภาพเมือง", "Markets · scenes")}</span>
<h2>{t("ภาพที่เก็บไว้เพราะความงาม", "Kept for how they look")}</h2>
{near_bar()}<div class="cards" data-near>{"".join(scene_card(p) for p in sc)}</div>
<p><a href="{BASE}scenes/">{t(f"ทั้ง {n(len(SCENES))} ภาพ →", f"All {n(len(SCENES))} →")}</a></p>
</div></section>"""
    return out


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
{session_extras(s)}
<h2>{t("ภาพ", "Photographs")}</h2>
{wall([dict(p, date=s["date"]) for p in s["photos"]], rise=False)}
<p class="small"><a href="{BASE}data/sessions/{e(s["id"])}.json">{t("ข้อมูลรอบนี้ (JSON)", "This session's data (JSON)")}</a></p>
</div></section>"""
    return page(f"sessions/{s['id']}/index.html", title_th, title_en, body,
                f"{title_en}: {c['new']} places added, {c['confirmed']} confirmed, {c['photos']} photographs.", hero)


def session_extras(s) -> str:
    pts = [p for p in POINTS if p["session"] == s["id"]]
    sc = [p for p in SCENES if p["session"] == s["id"]]
    out = ""
    if pts:
        out += (f'<h2>{t("ศาล ต้นไม้ผูกผ้า", "Spirit houses, shrines, trees")} <span class="small">{n(len(pts))}</span></h2>'
                f'<div class="cards">{"".join(point_card(p) for p in pts)}</div>')
    if sc:
        out += (f'<h2>{t("ตลาด ภาพเมือง ศิลปะริมถนน", "Markets, scenes, street art")} <span class="small">{n(len(sc))}</span></h2>'
                f'<div class="cards">{"".join(scene_card(p) for p in sc)}</div>')
    return out


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
<li>{t("ภาพที่เผยแพร่ถูกตัดใหม่จากทรงกลม 360° หันไปที่สิ่งที่ถ่าย เบลอหน้าคน แล้วขึ้นหน้าร้าน คลังภาพของมดแดง และหน้าศาลกับภาพเมืองของภาคสนาม", "A published photograph is re-cut from the 360° sphere, aimed at its subject, with faces blurred; it goes onto the place's page, Mot Dang's picture pool, and Field's shrine and scene pages.")}</li>
</ol>
<p><a href="{REPO}">{t("โค้ดทั้งหมดบน GitHub →", "All the code on GitHub →")}</a></p>
</div></section>"""
    return page("how/index.html", "วิธีทำ", "How", body, "How a 360° frame becomes a pin on Mot Dang.")


def build_data() -> str:
    items = [("data/places.csv", "ทุกร้านที่เห็น", "Every place seen", "CSV"),
             ("data/photos.json", "ทุกภาพ", "Every photograph", "JSON"),
             ("data/tracks.geojson", "ทุกเส้นทาง", "Every route", "GeoJSON"),
             ("data/points.geojson", "ศาล ต้นไม้ผูกผ้า ตลาด ทุกจุด", "Every spirit house, shrine, tree and market", "GeoJSON")]
    lis = "".join(f'<li><a href="{BASE}{p}" download><b>{t(th, en)}</b><span>{f} · {p}</span></a></li>' for p, th, en, f in items)
    body = f"""<section class="block"><div class="wrap">
<span class="kick">{t("ข้อมูล", "Data")}</span>
<h1>{t("เอาไปใช้ได้", "Take it")}</h1>
{pair("ข้อมูลและภาพเผยแพร่แบบ CC BY 4.0 ใส่ชื่อ NaN Peacock เมื่อนำไปใช้", "Data and photographs are CC BY 4.0: credit NaN Peacock when you use them.", cls="lede")}
<ul class="dl">{lis}<li><a href="{REPO}"><b>{t("โค้ดทั้งหมด", "All the code")}</b><span>GitHub · MIT</span></a></li></ul>
</div></section>"""
    return page("data/index.html", "ข้อมูล", "Data", body, "Field's data under CC BY 4.0.")


def build_about() -> str:
    """Planning, method and money, all of it counted from the files where it can be."""
    C = json.loads((ROOT / "data/costs.json").read_text())
    T = totals()
    seen = T["added"] + T["confirmed"]
    total_md = sum(TOTAL.values())
    cap = next((x["usd"] for x in C["parts"] if x["key"] == "capture"), 0)
    per = lambda usd, k: f"${usd / k:,.2f}" if k else "—"  # noqa: E731
    rows = "".join(f'<tr><td>{t(e(x["th"]), e(x["en"]))}</td><td class="mono">{"≈ " if x.get("approx") else ""}${x["usd"]:,}</td></tr>'
                   for x in C["parts"])
    unit = "".join(f'<tr><td>{t(th, en)}</td><td class="mono">{n(k)}</td><td class="mono">{per(cap, k)}</td></tr>' for th, en, k in (
        ("ร้านที่ป้ายยืนยันหรือเพิ่มจากป้าย", "places confirmed or added from a sign", seen),
        ("ร้านที่เพิ่มใหม่", "places added", T["added"]),
        ("ภาพที่ใช้ได้ (รวมศาลและต้นไม้)", "photographs in use (spirit houses and trees included)", T["photos"] + T["points"]),
        ("เฟรม 360°", "360° frames", T["frames"])))
    body = f"""<section class="block"><div class="wrap">
<span class="kick">{t("แผน · วิธี · ต้นทุน", "Plan · method · cost")}</span>
<h1>{t("ทำอย่างไร ใช้เงินเท่าไร", "How it is done, and what it has cost")}</h1>
{pair(f"มดแดงเปิดใช้งานและสร้างไปพร้อมกันมาราว {C['months_live']} เดือน มีคนทำเต็มเวลา {C['people_full_time']} คน คือ NaN Peacock ภาคสนามคือส่วนที่ออกไปดูของจริง",
      f"Mot Dang has been live and under construction at the same time for about {C['months_live']} months, with {C['people_full_time']} person on it full-time: NaN Peacock. Field is the part that goes and looks.", cls="lede")}

<h2 id="plan">{t("แผน", "The plan")}</h2>
{pair(f"มดแดงถือหมุด {n(total_md)} แห่งในเชียงใหม่และเชียงราย ส่วนใหญ่มาจากแผนที่เปิด ทะเบียนราชการ และแหล่งอื่นที่ไม่มีใครไปยืนหน้าร้าน แผนคือออกภาคสนามไม่กี่ร้อยรอบในสองสามเดือนข้างหน้า จนของส่วนใหญ่ถูกเห็นกับตา ตอนนี้เห็นแล้ว {n(seen)} แห่ง",
      f"Mot Dang holds {n(total_md)} pinned places in Chiang Mai and Chiang Rai, most from open maps, government registers and other sources nobody stood in front of. The plan, as of {C['as_of']}, is a few hundred sessions over the next couple of months, until most of it has been seen. So far: {n(seen)}.")}
<ul>
<li>{t("วัดความคืบหน้าเป็นรายอำเภอและตำบล: เห็นแล้วกี่แห่ง จากที่มดแดงถือ — หน้า", "Progress is measured by district and tambon: places seen against places held — the")} <a href="{BASE}areas/">{t("พื้นที่", "Areas")}</a> {t("", "page")}</li>
<li>{t("ขี่เป็นวงตามถนนสายหลักก่อน แล้วเดินในตลาด ห้าง และวัด ที่กล้องบนรถเข้าไม่ถึง", "Ride the main roads first, then walk the markets, malls and wats a bike camera cannot enter.")}</li>
<li>{t("ภาพที่ได้ใช้สามทาง: เป็นภาพของร้านนั้น ใช้ประกอบหน้าอื่นในเว็บ และใช้ในส่วนที่ตอบว่า 'แถวนี้มีอะไร' ตามตำแหน่งของผู้อ่าน", "Each photograph works three ways: as the place's own picture, as a picture for other pages, and in the parts of the site that answer 'what is around me' from where the reader stands.")}</li>
<li>{t("ที่เดียวอาจได้หลายภาพจากหลายรอบ ภาพที่ดีกว่าแทนภาพเก่าได้", "A place can collect several photographs over many sessions, and a better one can replace the first.")}</li>
</ul>

<h2 id="method">{t("วิธี", "The method")}</h2>
<table class="t"><tbody>
<tr><th>{t("กล้อง", "Camera")}</th><td>{t("GoPro Max 2 ภาพ 360° ถ่ายต่อเนื่องทุก 2–3 วินาที ติดหน้ารถมอเตอร์ไซค์หรือถือเดิน", "GoPro Max 2, 360° bursts every 2–3 seconds, on the front of a motorbike or carried on foot")}</td></tr>
<tr><th>{t("ต้นฉบับ", "Source")}</th><td>{t("ภาพ equirectangular 7680×3840 ต่อเฟรม ส่วนใหญ่มี GPS ใน EXIF วิดีโอมีแทร็ก GPX แยก", "7680×3840 equirectangular frames, most with a GPS fix in EXIF; videos carry a separate GPX track")}</td></tr>
<tr><th>{t("ดึงไฟล์", "Fetch")}</th><td>{t("จากคลาวด์ของ GoPro ทีละเฟรม ต้นฉบับเก็บไว้ในฮาร์ดดิสก์ภายนอก และคลาวด์ก็ยังเก็บไว้", "From GoPro's cloud one frame at a time; the originals are kept on an external drive, and the cloud keeps them too")}</td></tr>
<tr><th>{t("ตัดภาพ", "Cut")}</th><td>{t("16 ช่องต่อเฟรม (8 ทิศ × 2 ระดับ) ช่องละ 50°×30° ที่ราว 21 พิกเซลต่อองศา และภาพกว้าง 4 ทิศ รวมทิศที่หันหาผู้ขี่ ทุกภาพกว้างถูกอ่าน และซูมเข้าป้ายเล็กทีละช่อง", "16 tiles a frame (8 bearings × 2 heights), 50°×30° each at about 21 px per degree, plus four wide views including the one facing the rider; every wide view is read, zooming into small signs tile by tile")}</td></tr>
<tr><th>{t("อ่าน", "Read")}</th><td>{t("Apple Vision อ่านไทยและอังกฤษบนเครื่องเอง พร้อมหาใบหน้าและคน", "Apple Vision reads Thai and English on the Mac itself, and finds faces and people")}</td></tr>
<tr><th>{t("จับคู่", "Match")}</th><td>{t("เทียบกับชื่อในมดแดงระยะ 120 ม. โดยไม่นับวรรณยุกต์และสระบนล่าง ยืนยันเมื่อตรงกันในระยะ 50 ม.", "Against Mot Dang names within 120 m, ignoring tone marks and vowels above and below; a match within 50 m confirms the place")}</td></tr>
<tr><th>{t("คนตรวจ", "People")}</th><td>{t("ข้อความที่ไม่ตรงกับอะไรถูกตัดเป็นภาพ แล้วคนอ่านซ้ำ ป้ายบนหน้าร้านที่บอกทั้งชื่อและประเภทกลายเป็นรายการใหม่ ตั้งชื่อหน้าตามชื่อบนป้าย", "Text that matches nothing is cropped and read again by a person; a sign on the premises naming both the place and its trade becomes a new listing, named as painted")}</td></tr>
<tr><th>{t("ปรับระดับ", "Level")}</th><td>{t("ทั้งทรงกลม 360° ถูกหมุนให้ตั้งตรงก่อนตัดภาพ ใช้เส้นตั้งของตึกและเสา กับตำแหน่งของท้องฟ้า เอียงเท่าไรก็ปรับได้โดยไม่ต้องครอป เฟรมที่ห่างกันไม่กี่วินาทีช่วยตรวจกันเอง", "The whole 360° sphere is turned upright before any view is cut, from the verticals of buildings and poles and where the sky lies; any tilt is corrected without cropping, and frames a few seconds apart check each other")}</td></tr>
<tr><th>{t("ภาพ", "Photographs")}</th><td>{t("อ่านเฟรมทุกราว 25 ม. เมื่อขี่ และเว้นเฟรมเมื่อเดิน ส่วนเฟรมที่อยู่ระหว่างกันเปิดดูได้เมื่อป้ายถูกบัง รวมเฟรมที่มีคนหรือนิ้วบังเลนส์ ภาพที่เผยแพร่ตัดให้พ้นผู้ถ่ายและนิ้ว เบลอใบหน้าและศีรษะของคนที่ตรวจพบ ต้นฉบับเก็บไว้ตามเดิม ตัดหัวท้ายเส้นทาง 1.5 กม. และ 0.4 กม.", "A frame about every 25 m is read on a ride and every other frame on foot, with the frames between opened when a sign is blocked, those with people or a finger over the lens included; a published picture is cut away from the rider and the finger, with faces and the heads of detected people blurred, and the original is kept as shot; each route's first 1.5 km and last 0.4 km are trimmed")}</td></tr>
<tr><th>{t("ตำแหน่ง", "Position")}</th><td>{t("เฟรมที่มี GPS ให้หมุดภายในราว 30 ม. เฟรมที่ไม่มี GPS วางตามอาคารหรือตลาดที่ป้ายบอก และบอกไว้ในรายการว่าวางอย่างไร", "A frame with GPS pins a place to within about 30 m; one without is placed by the building or market its sign names, and the listing says how it was placed")}</td></tr>
<tr><th>{t("เครื่อง", "Machine")}</th><td>{t("ประมวลผลบน MacBook เครื่องเดียว เฟรมราว 800 เฟรมใช้เวลาเครื่องไม่ถึงชั่วโมง", "All of it runs on one MacBook; about 800 frames take under an hour of machine time")}</td></tr>
</tbody></table>
<p><a href="{BASE}how/">{t("ดูป้ายเดียวตั้งแต่ต้นจนจบ →", "One sign, start to finish →")}</a> · <a href="{REPO}">{t("โค้ด →", "The code →")}</a></p>

<h2 id="cost">{t("ต้นทุน", "The cost")}</h2>
{pair(f"ใช้ไปทั้งหมดกับมดแดงราว ${C['total']:,} (ณ {C['as_of']}) ไม่รวมเวลาทำงานของคน", f"Spent on Mot Dang so far: about ${C['total']:,} (as of {C['as_of']}), not counting anyone's time.", cls="lede")}
<table class="t"><thead><tr><th>{t("รายการ", "Item")}</th><th>USD</th></tr></thead><tbody>{rows}
<tr><th>{t("รวม", "Total")}</th><th class="mono">${C['total']:,}</th></tr>
<tr><td>{t("ต่อเดือน", "Per month")}</td><td class="mono">${C['total'] / C['months_live']:,.0f}</td></tr>
<tr><td>{t(f"ต่อหมุดที่มดแดงถือ ({n(total_md)} แห่ง)", f"Per pinned place Mot Dang holds ({n(total_md)})")}</td><td class="mono">${C['total'] / total_md:,.3f}</td></tr></tbody></table>
<h3>{t("อุปกรณ์เก็บภาพ หารด้วยสิ่งที่ได้จนถึงวันนี้", "The capture kit, divided by what it has produced so far")}</h3>
<table class="t"><thead><tr><th></th><th>{t("จำนวน", "Count")}</th><th>{t("ต่อหน่วย", "Per unit")}</th></tr></thead><tbody>{unit}</tbody></table>
{pair("อุปกรณ์ซื้อครั้งเดียว ยิ่งออกภาคสนามมาก ตัวเลขต่อหน่วยยิ่งลด ตารางนี้คำนวณใหม่ทุกครั้งที่สร้างเว็บ", "The kit is bought once, so every session lowers these figures; the table is recalculated on every build.", cls="small")}
</div></section>"""
    return page("about/index.html", "แผน · วิธี · ต้นทุน", "Plan, method, cost", body,
                f"How Field works and what Mot Dang has cost: about ${C['total']:,} over {C['months_live']} months, one person full-time.")


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
    pf = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
           "properties": {"kind": p.get("kind") or p.get("subject"), "title": p.get("title") or p.get("description"),
                          "title_th": p.get("title_th") or p.get("description_th"), "date": p["date"],
                          "photo": f"{SITE_URL}/{p['file']}", "credit": "NaN Peacock", "licence": "CC BY 4.0"}}
          for p in POINTS + [x for x in SCENES if x.get("subject") in ("market", "street-art")] if p.get("lat") is not None]
    (OUT / "data/points.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": pf}, ensure_ascii=False))

    write("index.html", build_home())
    write("areas/index.html", build_areas())
    for (pv, am), pls in AREAS.items():
        write(f"areas/{area_key(pv, am)}/index.html", build_area(pv, am, pls))
    write("sessions/index.html", page("sessions/index.html", "รอบ", "Sessions", sessions_table(SESSIONS),
                                      f"{len(SESSIONS)} sessions in the field."))
    for s in SESSIONS:
        write(f"sessions/{s['id']}/index.html", build_session(s))
    npages = build_photos()
    write("san/index.html", build_san())
    write("scenes/index.html", build_scenes())
    write("how/index.html", build_how())
    write("data/index.html", build_data())
    write("about/index.html", build_about())

    urls = (["", "areas/", "sessions/", "photos/", "san/", "scenes/", "how/", "data/", "about/"]
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
