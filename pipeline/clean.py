"""Blur faces (and the head of every detected person) before a view is published.

python3 tools/clean.py <in.jpg> <out.jpg> [width]
Vision runs on the full view; a face box is grown 40% and blurred hard, and the top
fifth of each person box is blurred too, because a small face in a street scene is
often missed as a face but found as a person.
"""
import json, subprocess, sys
from pathlib import Path
from PIL import Image, ImageFilter
VISION = Path(__file__).with_name("vision")
def clean(src, dst, width=1400):
    d = json.loads(subprocess.run([str(VISION)], input=str(src) + "\n", capture_output=True, text=True).stdout)
    im = Image.open(src).convert("RGB"); W, H = im.size
    boxes = []
    for f in d.get("faces", []):
        x, y, w, h = f["box"]; boxes.append((x - .2 * w, y - .2 * h, w * 1.4, h * 1.4))
    for p in d.get("people", []):
        x, y, w, h = p["box"]; boxes.append((x, y, w, h * .38))
    for x, y, w, h in boxes:
        b = (max(0, int(x * W)), max(0, int(y * H)), min(W, int((x + w) * W)), min(H, int((y + h) * H)))
        if b[2] - b[0] < 2 or b[3] - b[1] < 2: continue
        reg = im.crop(b); r = max(6, (b[2] - b[0]) // 4)
        im.paste(reg.filter(ImageFilter.GaussianBlur(r)), b)
    if width and W > width:
        im = im.resize((width, round(H * width / W)), Image.LANCZOS)
    im.save(dst, quality=82, optimize=True, progressive=True)
    return len(d.get("faces", [])), len(d.get("people", []))
if __name__ == "__main__":
    print(clean(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1400))
