#!/usr/bin/env python3
"""Build ภาคสนาม · Field into build/site/.

    SITE_URL=https://motdang.net/field python3 tools/site.py

Everything printed is read from data/sessions/*.json at build time, so a new session is
a new file there (tools/ingest.py writes it) and a rebuild. Numbers are counted here, not
typed.
"""
from __future__ import annotations

import csv
import html
import json
import math
import os
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import fleet  # noqa: E402

SITE_URL = os.environ.get("SITE_URL", "https://motdang.net/field").rstrip("/")
GH_URL = "https://nanobotco.github.io/field"
CANON = os.environ.get("CANONICAL_URL", "https://motdang.net/field").rstrip("/")
REPO = "https://github.com/NaNoBotCo/field"
MOTDANG = "https://motdang.net"
OUT = ROOT / "build" / "site"
SELF = "field"
FLEET = fleet.load(ROOT / "data" / "fleet.json")
CREDIT = "NaN Peacock · CC BY 4.0"

SESSIONS = sorted((json.loads(p.read_text()) for p in (ROOT / "data/sessions").glob("*.json")),
                  key=lambda s: s["date"], reverse=True)
LAND = json.loads((ROOT / "data/landmarks.json").read_text())


def e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def t(th: str, en: str, tag: str = "span") -> str:
    """Thai first, English beside it; the page shows one or both."""
    return f'<{tag} lang="th">{th}</{tag}><{tag} lang="en">{en}</{tag}>'


def pair(th: str, en: str, tag: str = "p", cls: str = "") -> str:
    c = f' class="pair {cls}"' if cls else ' class="pair"'
    return f'<div{c}><{tag} lang="th">{th}</{tag}><{tag} lang="en">{en}</{tag}></div>'


def n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else str(x)


def place_url(pid: str) -> str:
    return f"{MOTDANG}/cm/p/{pid}.html"


def fmt_date(d: str, lang: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    th = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    en = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{dd} {th[m]} {y + 543}" if lang == "th" else f"{dd} {en[m]} {y}"


# ---------------------------------------------------------------- page shell
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
    depth = path.count("/")
    up = "../" * depth
    canon = f"{CANON}/{path}".replace("index.html", "")
    alt = f"{(GH_URL if CANON != GH_URL else CANON)}/{path}".replace("index.html", "")
    img = f"{SITE_URL}/{image}" if image else ""
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": f"{title_en} — Field",
          "inLanguage": ["th", "en"], "url": canon, "isPartOf": {"@type": "WebSite", "name": "ภาคสนาม · Field", "url": SITE_URL + "/"},
          "creator": fleet.maker_ld(FLEET), "license": "https://creativecommons.org/licenses/by/4.0/"}
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
{f'<meta property="og:image" content="{e(img)}"><meta name="twitter:card" content="summary_large_image">' if img else ''}
<meta name="theme-color" content="#d9381e">
<link rel="icon" href="{up}assets/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{up}assets/css/field.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
{LANG_JS}
</head>
<body>
<header class="bar"><div class="wrap">
<a class="brand" href="{up or './'}"><i></i>ภาคสนาม <span class="small">Field</span></a>
<nav aria-label="site">
<a href="{up}#route">{t("เส้นทาง", "Route")}</a>
<a href="{up}#new">{t("ร้านใหม่", "New")}</a>
<a href="{up}photos/">{t("ภาพ", "Photos")}</a>
<a href="{up}#data">{t("ข้อมูล", "Data")}</a>
</nav>
<div class="langs" role="group" aria-label="language"><button data-l="th">ไทย</button><button data-l="en">EN</button><button data-l="both">ทั้งคู่</button></div>
</div></header>
<main>
{body}
</main>
{footer(up)}
{TAIL_JS}
</body>
</html>
"""


def footer(up: str) -> str:
    return f"""<footer><div class="wrap">
<p>{t("ภาพถ่ายและข้อมูลโดย NaN Peacock เผยแพร่แบบ", "Photographs and data by NaN Peacock, under")}
<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> · {t("โค้ดแบบ", "code under")} MIT ·
<a href="{REPO}">GitHub</a> · <a href="{MOTDANG}/">motdang.net</a></p>
{fleet.maker_html(roster=FLEET, lang="en")}
{fleet.row_html(SELF, label="More from the same publisher", roster=FLEET)}
{fleet.support_html(roster=FLEET)}
</div></footer>"""


# ---------------------------------------------------------------- pieces
def band(img: str, inner: str, cls: str = "", credit: str = CREDIT) -> str:
    return (f'<section class="band {cls}" style="background-image:url({e(img)})">'
            f'<div class="in">{inner}</div><span class="cred">{e(credit)}</span></section>')


def shot(href: str, img: str, title: str, sub: str = "", credit: bool = True) -> str:
    bg = f'<span class="bg" style="background-image:url({e(img)})"></span>' if img else ""
    cls = "shot" if img else "shot plain"
    sub_html = f"<small>{sub}</small>" if sub else ""
    cred = f'<span class="cred">{e(CREDIT)}</span>' if (img and credit) else ""
    return (f'<figure class="card" data-rise><a class="{cls}" href="{e(href)}">{bg}<span class="scrim"></span>'
            f'<span class="sp"></span><span class="tx">{title}{sub_html}</span></a>{cred}</figure>')


def route_svg(sess: dict, up: str) -> str:
    """The shown track, the moat for bearings, and a dot per place read off a sign."""
    tr = json.loads((ROOT / sess["track"]).read_text())["features"][0]["geometry"]["coordinates"]
    pts = [(lo, la) for lo, la in tr]
    new = [(r["lng"], r["lat"], r) for r in sess["new"]]
    moat = [(lo, la) for la, lo in LAND["moat"]]
    xs = [p[0] for p in pts + moat]; ys = [p[1] for p in pts + moat]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = math.cos(math.radians((y0 + y1) / 2))
    W = 1000; pad = 40
    sx = (W - 2 * pad) / ((x1 - x0) * k)
    H = int((y1 - y0) * sx + 2 * pad)
    P = lambda lo, la: (pad + (lo - x0) * k * sx, H - pad - (la - y0) * sx)  # noqa: E731
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (P(*p) for p in pts))
    mo = " ".join(f"{x:.1f},{y:.1f}" for x, y in (P(*p) for p in moat))
    dots = []
    for i, (lo, la, r) in enumerate(new):
        x, y = P(lo, la)
        dots.append(f'<a href="{e(place_url(r["id"]))}"><circle class="dot new" cx="{x:.1f}" cy="{y:.1f}" r="6" style="--i:{i}">'
                    f'<title>{e(r["name"])} — {e(r["kind"])}</title></circle></a>')
    mx, my = P(*LAND["centre"][::-1])
    # a 1 km bar
    bar = 1000 / 111320 / k * k * sx
    return f"""<figure class="map" data-rise>
<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="mt-{sess['date']}">
<title id="mt-{sess['date']}">Route of {sess['date']} with the places added from signs</title>
<polygon class="moat" points="{mo}"/><text class="lbl" x="{mx:.0f}" y="{my + 5:.0f}" text-anchor="middle">คูเมือง · moat</text>
<path class="glow" d="{d}"/><path class="route" d="{d}"/>
{''.join(dots)}
<g transform="translate({pad},{H - 16})"><rect width="{bar:.1f}" height="4" fill="currentColor" opacity=".5"/><text class="lbl" x="{bar + 8:.0f}" y="6">1 km</text></g>
</svg>
<figcaption class="legend"><span><i style="background:var(--accent)"></i>{t("ร้านที่เพิ่มจากป้าย", "added from its sign")}</span>
<span><i style="background:var(--accent);opacity:.3;border-radius:2px;width:22px;height:5px"></i>{t("เส้นทาง (ตัดหัวท้าย)", "route, ends trimmed")}</span></figcaption>
</figure>"""


def stats(c: dict) -> str:
    cells = [
        ("hot", c["new"], "ร้านที่ยังไม่มีในมดแดง เพิ่มจากป้ายหน้าร้าน", "places Mot Dang did not have, added from their own signs"),
        ("leaf", c["confirmed"], "ร้านในมดแดงที่ป้ายหน้าร้านยืนยันชื่อ", "Mot Dang places confirmed by name on their own sign"),
        ("", c["photos"], "ภาพที่ใช้ได้ทั้งเว็บ", "photographs, usable anywhere on the site"),
        ("", c["km"], "กิโลเมตรที่ขี่", "kilometres ridden"),
        ("", c["frames"], "เฟรม 360°", "360° frames"),
        ("", c["text_lines"], "บรรทัดข้อความที่เครื่องอ่านได้", "lines of text the machine read"),
    ]
    out = []
    for cls, v, th, en in cells:
        out.append(f'<div class="stat {cls}" data-rise><b>{n(v)}</b>{t(th, en)}</div>')
    return f'<div class="stats wrap">{"".join(out)}</div>'


def example(sess: dict, up: str) -> str:
    x = sess.get("example")
    if not x:
        return ""
    steps = [
        (x["view"], "", "เฟรม 360° ถูกตัดเป็นภาพแบน มองออกข้างทาง", "The 360° frame, cut flat, looking at the roadside"),
        (x["tile"], "fit", "ตัดเป็นช่องเล็ก 16 ช่องต่อเฟรม ให้เครื่องอ่านป้ายที่ความละเอียดเต็ม — กรอบแดงคือที่มันเจอข้อความ",
         "Cut again into 16 tiles a frame so the reader sees signs at full resolution — the red box is where it found text"),
        (x["crop"], "fit", f'เครื่องอ่านได้ <span class="read">{e(x["read"])}</span> ไม่ตรงกับร้านไหนในมดแดง คนอ่านซ้ำจากภาพ',
         f'The machine read <span class="read">{e(x["read"])}</span>, matched nothing in Mot Dang, and a person read the crop again'),
        (x["photo"], "", f'<a href="{e(place_url(x["id"]))}">{e(x["name"])}</a> อยู่ในมดแดงแล้ว พร้อมหมุดและรูปนี้ — '
                         f'ร้าน<a href="{e(place_url(x["also_id"]))}">{e(x["also"])}</a> ข้าง ๆ ก็มาจากเฟรมเดียวกัน',
         f'<a href="{e(place_url(x["id"]))}">{e(x["name"])}</a> is on Mot Dang now, with a pin and this photo — and '
         f'<a href="{e(place_url(x["also_id"]))}">{e(x["also"])}</a>, the coffin shop next door, came from the same frame'),
    ]
    cards = []
    for i, (img, cls, th, en) in enumerate(steps, 1):
        cards.append(f'<article class="step"><figure class="{cls}"><img src="{up}{e(img)}" alt="" loading="lazy"></figure>'
                     f'<div class="t"><span class="n">0{i}</span>{pair(th, en)}</div></article>')
    return f"""<section class="block" id="how"><div class="wrap">
<span class="kick">{t("ป้ายเดียว ตั้งแต่ต้นจนจบ", "One sign, start to finish")}</span>
<h2>{t("จากเฟรมสู่หมุดบนแผนที่", "From a frame to a pin")}</h2>
<div class="steps" tabindex="0" aria-label="steps">{''.join(cards)}</div>
</div></section>"""


def new_places(sess: dict, up: str) -> str:
    cards = []
    pic = {p["placeId"]: p["file"] for p in sess["photos"] if p.get("placeId")}
    for r in sorted(sess["new"], key=lambda r: (r["id"] not in pic, r["name"])):
        img = f"{up}{pic[r['id']]}" if r["id"] in pic else ""
        sub = t(e(r.get("kindTh") or r["kind"]), e(r["kind"]))
        cards.append(shot(place_url(r["id"]), img, e(r["name"]), sub, credit=False))
    return f'<div class="cards">{"".join(cards)}</div>'


def confirmed(sess: dict) -> str:
    chips = [f'<a class="{"has" if r["photo"] else ""}" href="{e(place_url(r["id"]))}" title="{e(r["read"])}">{e(r["name"])}</a>'
             for r in sorted(sess["confirmed"], key=lambda r: r["name"])]
    return f'<div class="chips">{"".join(chips)}</div>'


def downloads(sess: dict, up: str) -> str:
    d = sess["date"]
    items = [
        (f"data/sessions/{d}.json", "Session", "ทั้งหมดของรอบนี้", "JSON"),
        (f"data/tracks/{d}.geojson", "Track", "เส้นทาง", "GeoJSON"),
        (f"data/places-{d}.csv", "Places", "ร้านที่เพิ่มและยืนยัน", "CSV"),
        ("data/photos.json", "Photographs", "ภาพทั้งหมด พร้อมพิกัดและเครดิต", "JSON"),
    ]
    lis = "".join(f'<li><a href="{up}{p}" download><b>{t(th, en)}</b><span>{fmt} · {p}</span></a></li>'
                  for p, en, th, fmt in items)
    return f'<ul class="dl">{lis}<li><a href="{REPO}"><b>{t("โค้ดทั้งหมด", "All the code")}</b><span>GitHub · MIT</span></a></li></ul>'


def session_body(sess: dict, up: str, hero_h: str, with_hero: bool = True) -> str:
    c = sess["counts"]
    d = sess["date"]
    hero = band(f"{up}{sess['hero']}", f"""<span class="kicker">{t(fmt_date(d, 'th'), fmt_date(d, 'en'))} · {e(sess['camera'])}</span>
{hero_h}
{pair(sess.get('where_th', ''), sess.get('where', ''))}""", "hero tall")
    fixes = ""
    for f in sess.get("pin_fixes", []):
        m = n(f["moved_m"])
        fixes += (f'<p class="fix"><a href="{e(place_url(f["id"]))}">{e(f["name"])}</a> — '
                  + t(e(f["why_th"]) + " (" + m + " ม.)", e(f["why"]) + " (" + m + " m)") + "</p>")
    band2 = [p for p in sess["photos"] if "wat" in (p.get("topic") or []) and not p.get("placeId")]
    band3 = [p for p in sess["photos"] if "transport" in (p.get("topic") or []) and not p.get("placeId")]
    b2 = band(f"{up}{band2[-1]['file']}", f'<span class="kicker">{t("ใหม่บนแผนที่", "New on the map")}</span>'
              '<h2>' + t(str(c["new"]) + " ร้านที่แผนที่ยังไม่รู้จัก", str(c["new"]) + " places the map did not know") + '</h2>', "right") if band2 else ""
    b3 = band(f"{up}{band3[-1]['file']}", f'<span class="kicker">{t("ภาพ", "Photographs")}</span>'
              '<h2>' + t(str(c["photos"]) + " ภาพ ใช้ได้ทุกหน้า", str(c["photos"]) + " pictures for every page") + '</h2>'
              f'<a class="btn" href="{up}photos/">{t("ดูทั้งหมด", "See them all")}</a>') if band3 else ""
    if not with_hero:
        hero = ""
    return f"""{hero}
{stats(c)}
<section class="block" id="route"><div class="wrap">
<span class="kick">{t("เส้นทาง", "The route")}</span>
<h2>{t(f"{c['km']} กม. ในครั้งเดียว", f"{c['km']} km in one go")}</h2>
{route_svg(sess, up)}
</div></section>
{example(sess, up)}
{b2}
<section class="block" id="new"><div class="wrap">
{new_places(sess, up)}
</div></section>
<section class="block" id="seen"><div class="wrap">
<span class="kick">{t("ยืนยันแล้ว", "Confirmed")}</span>
<h2>{t(f"{c['confirmed']} ร้านที่ป้ายหน้าร้านตรงกับมดแดง", f"{c['confirmed']} places whose own sign matched Mot Dang")}</h2>
<p class="small">{t("จุดเขียว = ได้รูปใหม่จากรอบนี้", "green dot = got a new photo from this ride")}</p>
{confirmed(sess)}
{('<h3 style="margin-top:28px">' + t('หมุดที่ย้าย', 'Pins moved') + '</h3>' + fixes) if fixes else ''}
</div></section>
{b3}
<section class="block" id="data"><div class="wrap">
<span class="kick">{t("ข้อมูล", "Data")}</span>
<h2>{t("เอาไปใช้ได้", "Take it")}</h2>
{pair("ข้อมูลและภาพเผยแพร่แบบ CC BY 4.0 ใส่ชื่อ NaN Peacock เมื่อนำไปใช้", "Data and photographs are CC BY 4.0: credit NaN Peacock when you use them.", cls="lede")}
{downloads(sess, up)}
</div></section>"""


def sessions_list(up: str) -> str:
    cards = []
    for s in SESSIONS:
        c = s["counts"]
        sub = t(f"{fmt_date(s['date'], 'th')} · {c['km']} กม. · +{c['new']} ร้าน", f"{fmt_date(s['date'], 'en')} · {c['km']} km · +{c['new']} places")
        cards.append(shot(f"{up}sessions/{s['date']}/", f"{up}{s['hero']}", t(e(s.get('title_th', s['date'])), e(s.get('title', s['date']))), sub))
    return f"""<section class="block" id="sessions"><div class="wrap">
<span class="kick">{t("ทุกรอบ", "Every session")}</span>
<h2>{t(f"{len(SESSIONS)} รอบ", f"{len(SESSIONS)} session" + ("s" if len(SESSIONS) != 1 else ""))}</h2>
<div class="sessions">{''.join(cards)}</div>
</div></section>"""


# ---------------------------------------------------------------- pages
def build_index() -> str:
    s = SESSIONS[0]
    h1 = f'<h1>ภาคสนาม<br><span lang="en" style="font-size:.45em;display:block">Field</span></h1>'
    lead = band(f"{s['hero']}", f"""<span class="kicker">{t("มดแดง · เชียงใหม่", "Mot Dang · Chiang Mai")}</span>
{h1}
{pair("กล้อง 360° ติดมอเตอร์ไซค์ ถ่ายทุกป้ายที่ผ่าน เครื่องอ่าน คนตรวจ แล้วเติมลงแผนที่มดแดง",
      "A 360° camera on a motorbike photographs every sign it passes. A machine reads them, a person checks them, and they go onto Mot Dang's map.")}""",
                "hero tall")
    body = session_body(s, "", "", with_hero=False)  # the index leads with its own band
    return page("index.html", "ภาคสนาม", "Field", lead + body + sessions_list(""),
                "Street-level capture for Mot Dang: 360° frames from a motorbike, signs read, places added and confirmed, photographs under CC BY 4.0.",
                s["hero"])


def build_session(s: dict) -> str:
    up = "../../"
    h = f"<h1>{t(e(s.get('title_th', s['date'])), e(s.get('title', s['date'])))}</h1>"
    return page(f"sessions/{s['date']}/index.html", s.get("title_th", s["date"]), s.get("title", s["date"]),
                session_body(s, up, h), f"{s.get('title', '')}: {s['counts']['new']} places added, {s['counts']['confirmed']} confirmed, {s['counts']['photos']} photographs.",
                s["hero"])


def build_photos() -> str:
    up = "../"
    figs = []
    for s in SESSIONS:
        for p in s["photos"]:
            href = place_url(p["placeId"]) if p.get("placeId") else f"{up}{p['file']}"
            cap = t(e(p.get("description_th") or p["title"]), e(p.get("description") or p["title"]))
            figs.append(f'<figure data-rise><a href="{e(href)}"><img src="{up}{e(p["file"])}" alt="{e(p.get("description") or p["title"])}" '
                        f'width="{p.get("width") or 1200}" height="{p.get("height") or 800}" loading="lazy"></a>'
                        f'<figcaption>{cap} · {fmt_date(s["date"], "en")} · {e(CREDIT)}</figcaption></figure>')
    total = sum(len(s["photos"]) for s in SESSIONS)
    body = f"""<section class="block"><div class="wrap">
<span class="kick">{t("ภาพ", "Photographs")}</span>
<h1>{t(f"{total} ภาพจากถนน", f"{total} photographs from the road")}</h1>
{pair("ใช้ได้ทุกที่ ใส่ชื่อ NaN Peacock และ CC BY 4.0 · ภาพของร้านพาไปหน้าร้านนั้นในมดแดง",
      "Use them anywhere with the credit NaN Peacock, CC BY 4.0. A photo of a place links to its Mot Dang page.", cls="lede")}
<div class="wall">{''.join(figs)}</div>
</div></section>"""
    return page("photos/index.html", "ภาพ", "Photographs", body, f"{total} street photographs of Chiang Mai under CC BY 4.0.")


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
    shutil.copytree(ROOT / "data/tracks", OUT / "data/tracks")
    allphotos = []
    for s in SESSIONS:
        with open(OUT / f"data/places-{s['date']}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["status", "id", "name", "kind", "lat", "lng", "motdang_url"])
            for r in s["new"]:
                w.writerow(["added", r["id"], r["name"], r["kind"], r["lat"], r["lng"], place_url(r["id"])])
            for r in s["confirmed"]:
                w.writerow(["confirmed", r["id"], r["name"], r["cat"], "", "", place_url(r["id"])])
        allphotos += [p | {"session": s["date"], "url": f"{SITE_URL}/{p['file']}"} for p in s["photos"]]
    (OUT / "data/photos.json").write_text(json.dumps({"licence": "CC BY 4.0", "credit": "NaN Peacock", "photos": allphotos}, ensure_ascii=False, indent=1))

    write("index.html", build_index())
    for s in SESSIONS:
        write(f"sessions/{s['date']}/index.html", build_session(s))
    write("photos/index.html", build_photos())

    urls = ["", "photos/"] + [f"sessions/{s['date']}/" for s in SESSIONS]
    today = date.today().isoformat()
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{SITE_URL}/{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    latest = SESSIONS[0]["counts"]
    write("llms.txt", f"# ภาคสนาม · Field\n\n> Street-level capture feeding Mot Dang, the Thai-first directory of Chiang Mai "
          f"and Chiang Rai. A 360° camera on a motorbike; each frame is cut into tiles, the signs are read by Apple Vision "
          f"(Thai + English) and checked by a person; names that match a Mot Dang record confirm it, names that match nothing "
          f"become new records with a pin.\n\n- Sessions: {len(SESSIONS)}\n- Latest: {SESSIONS[0]['date']}, {latest['km']} km, "
          f"{latest['new']} places added, {latest['confirmed']} confirmed, {latest['photos']} photographs\n"
          f"- Data: {SITE_URL}/data/photos.json and {SITE_URL}/data/sessions/\n- Licence: data and photographs CC BY 4.0 "
          f"(credit NaN Peacock); code MIT\n- Code: {REPO}\n")
    write("humans.txt", "Photographs, riding and direction: NaN Peacock\nStudio: hongdam.net — Chiang Rai\n")
    fleet.decorate(OUT, SELF, roster=FLEET)
    print(f"built {SITE_URL}: {len(list(OUT.rglob('*.html')))} pages, {len(allphotos)} photographs")


if __name__ == "__main__":
    main()
