# ภาคสนาม · Field

Street-level capture for [Mot Dang](https://motdang.net/), the Thai-first directory of Chiang Mai
and Chiang Rai. A 360° camera rides on a motorbike; every sign it passes is read, by machine
and then by a person, and goes onto the map.

**Live:** https://motdang.net/field/ · https://nanobotco.github.io/field/

Made by [hongdam.net](https://hongdam.net/), a bilingual web studio in Chiang Rai.

## So far

| session | km | frames | places added | places confirmed | photographs |
|---|---|---|---|---|---|
| 2026-09-23 | 13.5 | 818 | 29 | 60 | 84 |

*Places added* had no Mot Dang record; their own signboard named them. *Confirmed* already
had one, and the sign agreed with its name within 50 m.

## How a frame becomes a pin

1. **Cloud.** The camera uploads to GoPro's cloud. Each `.36P` burst frame is a stitched
   7680×3840 equirectangular JPEG; its EXIF carries a GPS fix on most frames.
2. **Track.** `pipeline/frames.py` reads the fixes into a per-frame index and a GeoJSON line.
3. **Tiles.** `pipeline/tiles.py` cuts each frame into 16 flat tiles, 50°×30°, at the source's
   own resolution — sign text is unreadable in a wide view and readable here.
4. **Reading.** `pipeline/vision.swift` runs Apple Vision's text recogniser (Thai and
   English) and its face and person detectors, all on the Mac.
5. **Matching.** `pipeline/signs.py` compares every line read against Mot Dang names within
   120 m, ignoring Thai tone marks and vowels above and below, so a missed ไม้โท still matches.
6. **People.** What matched nothing is cropped and read again by a person. A name painted on
   its own premises, with the trade on the same sign, becomes a record.
7. **Photographs.** `pipeline/level.py` straightens a view by its verticals and
   `pipeline/clean.py` blurs faces and the heads of detected people before a photograph is
   published.

`tools/ingest.py` turns a session's working folder into `data/sessions/<date>.json`; the
site is built from those files, so a new session is a new file and a rebuild.

## Data

- `data/sessions/*.json` — counts, the places added and confirmed, the photographs
- `data/tracks/*.geojson` — each route, with the two ends trimmed
- the built site also serves `data/photos.json` and `data/places-<date>.csv`

## Licences

Photographs and data: **CC BY 4.0**, credit **NaN Peacock**. Code: **MIT**. Fonts: SIL OFL,
licences beside the files in `assets/fonts/`.

## Build

```
./publish.sh                                               # GitHub Pages copy into docs/
SITE_URL=https://motdang.net/field python3 tools/site.py   # the motdang.net copy
python3 tools/serve.py                                     # http://localhost:8820
```
