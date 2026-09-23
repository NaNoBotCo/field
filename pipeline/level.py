"""Straighten a view by its verticals, then crop back to the frame's own shape.

The tilt is the median lean of near-vertical edges. A correction over MAX_FIX degrees is
not applied: a lean that large is perspective or a turn, and rotating it away eats most
of the frame. The crop is the largest rectangle with the original aspect ratio that fits
inside the rotated frame, found by bisection.
"""
import cv2, math, numpy as np
MAX_FIX = 12.0

def _fits(k, W, H, a):
    c, s = math.cos(a), math.sin(a)
    for x, y in ((k * W / 2, k * H / 2), (k * W / 2, -k * H / 2)):
        # rotate the corner back into the original frame and test it
        xr, yr = x * c + y * s, -x * s + y * c
        if abs(xr) > W / 2 or abs(yr) > H / 2:
            return False
    return True

def level(src, dst, max_deg=30):
    im = cv2.imread(src); H, W = im.shape[:2]
    g = cv2.Canny(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), 60, 160)
    lines = cv2.HoughLinesP(g, 1, np.pi / 360, 80, minLineLength=H // 8, maxLineGap=8)
    angs = []
    for x1, y1, x2, y2 in (lines.reshape(-1, 4) if lines is not None else []):
        a = math.degrees(math.atan2(x2 - x1, y2 - y1))
        a = (a + 90) % 180 - 90
        if abs(a) < max_deg: angs.append(a)
    tilt = float(np.median(angs)) if len(angs) >= 4 else 0.0
    if .5 < abs(tilt) <= MAX_FIX:
        M = cv2.getRotationMatrix2D((W / 2, H / 2), -tilt, 1)
        im = cv2.warpAffine(im, M, (W, H), flags=cv2.INTER_CUBIC)
        a = math.radians(abs(tilt)); lo, hi = 0.0, 1.0
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _fits(mid, W, H, a) else (lo, mid)
        w2, h2 = int(W * lo), int(H * lo)
        x0, y0 = (W - w2) // 2, (H - h2) // 2
        im = im[y0:y0 + h2, x0:x0 + w2]
    else:
        tilt = 0.0 if abs(tilt) > MAX_FIX else tilt
    cv2.imwrite(dst, im, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return round(tilt, 1)
