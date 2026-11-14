#!/usr/bin/env python3
"""make.fun bounty: Make the AI judge happy.

Writes one 1024x1024 PNG to /output/entry.png (or $OUTPUT_PATH).

STANDARD LIBRARY ONLY (math, os, shutil, struct, sys, zlib).
No Pillow, no third-party packages: the grading container installs
nothing, so the PNG is encoded by hand (zlib + struct) and the scene
is drawn procedurally on a bytearray canvas.

Deterministic, no network. Drawn at 2x and downscaled for smooth
edges. The program runs twice and both runs write identical bytes.

If generation fails for any reason, the program copies the bundled
entry.png asset instead -- the brief explicitly allows a program that
copies an image the repository holds.
"""
import math
import os
import shutil
import struct
import sys
import zlib

OUT = os.environ.get("OUTPUT_PATH", "/output/entry.png")
HERE = os.path.dirname(os.path.abspath(__file__))
ASSET = os.path.join(HERE, "entry.png")

S = 2  # supersampling factor
W = H = 1024


# ------------------------------------------------------------------ PNG

def encode_png(w, h, rgb):
    """Encode RGB bytes (w*h*3) as a PNG. Deterministic, no timestamps."""

    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)  # filter: None
        raw += rgb[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 6)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))

def downscale2(buf, w, h):
    """Average 2x2 blocks: (w,h) -> (w//2, h//2). Pure python."""
    ow, oh = w // 2, h // 2
    out = bytearray(ow * oh * 3)
    src = buf
    for oy in range(oh):
        r0 = (2 * oy) * w * 3
        r1 = r0 + w * 3
        o = oy * ow * 3
        for ox in range(ow):
            i0 = r0 + ox * 6
            i1 = r1 + ox * 6
            out[o] = (src[i0] + src[i0 + 3] + src[i1] + src[i1 + 3] + 2) // 4
            out[o + 1] = (src[i0 + 1] + src[i0 + 4] + src[i1 + 1]
                          + src[i1 + 4] + 2) // 4
            out[o + 2] = (src[i0 + 2] + src[i0 + 5] + src[i1 + 2]
                          + src[i1 + 5] + 2) // 4
            o += 3
    return bytes(out)


# ---------------------------------------------------------------- canvas

class Canvas:
    """RGB bytearray canvas with scanline fills (fast, no per-pixel loops
    over the whole image). All coordinates are floats; spans are clipped."""

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    def span(self, y, x0, x1, rgb):
        if y < 0 or y >= self.h:
            return
        x0 = max(0, int(x0))
        x1 = min(self.w - 1, int(x1))
        if x1 < x0:
            return
        o = y * self.w * 3
        self.buf[o + x0 * 3:o + (x1 + 1) * 3] = bytes(rgb) * (x1 - x0 + 1)

    def rect(self, x0, y0, x1, y1, rgb):
        for y in range(max(0, int(y0)), min(self.h, int(y1) + 1)):
            self.span(y, x0, x1, rgb)

    def circle(self, cx, cy, r, rgb):
        r = int(r)
        for y in range(max(0, cy - r), min(self.h, cy + r + 1)):
            dy = y - cy
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.span(y, cx - dx, cx + dx, rgb)

    def ellipse(self, cx, cy, rx, ry, rgb):
        for y in range(max(0, int(cy - ry)), min(self.h, int(cy + ry) + 1)):
            dy = (y - cy) / ry
            dx = int(rx * math.sqrt(max(0.0, 1.0 - dy * dy)))
            self.span(y, cx - dx, cx + dx, rgb)
    def poly(self, pts, rgb):
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(self.h - 1, int(max(ys)) + 1)
        n = len(pts)
        for y in range(y0, y1 + 1):
            ym = y + 0.5
            xs = []
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if (ay <= ym < by) or (by <= ym < ay):
                    t = (ym - ay) / (by - ay)
                    xs.append(ax + t * (bx - ax))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.span(y, xs[i], xs[i + 1], rgb)

    def sector(self, cx, cy, rx, ry, a0, a1, rgb, steps=48):
        """Filled elliptical sector from angle a0 to a1 (degrees)."""
        pts = [(cx, cy)]
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
        self.poly(pts, rgb)

    def rotated_ellipse(self, cx, cy, rx, ry, angle_deg, rgb, steps=48):
        th = math.radians(angle_deg)
        c, s = math.cos(th), math.sin(th)
        pts = []
        for i in range(steps):
            t = 2 * math.pi * i / steps
            ex, ey = rx * math.cos(t), ry * math.sin(t)
            pts.append((cx + ex * c - ey * s, cy + ex * s + ey * c))
        self.poly(pts, rgb)

    def thick_line(self, x0, y0, x1, y1, rgb, width):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L * width / 2, dx / L * width / 2
        self.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                   (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], rgb)
        self.circle(int(x0), int(y0), int(width / 2), rgb)
        self.circle(int(x1), int(y1), int(width / 2), rgb)

    def arc(self, cx, cy, rx, ry, a0, a1, rgb, width):
        steps = max(4, int(abs(a1 - a0) / 4))
        prev = None
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            p = (cx + rx * math.cos(a), cy + ry * math.sin(a))
            if prev is not None:
                self.thick_line(prev[0], prev[1], p[0], p[1], rgb, width)
            prev = p

    def vgrad(self, stops):
        for y in range(self.h):
            t = y / max(self.h - 1, 1)
            col = stops[-1][1]
            for i in range(len(stops) - 1):
                p0, c0 = stops[i]
                p1, c1 = stops[i + 1]
                if p0 <= t <= p1:
                    f = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
                    col = tuple(round(c0[j] + (c1[j] - c0[j]) * f)
                                for j in range(3))
                    break
            self.span(y, 0, self.w - 1, col)

# ---------------------------------------------------------------- shapes

def heart(c, cx, cy, s, fill):
    r = s * 0.5
    c.circle(int(cx - r), int(cy - r * 0.6), int(r), fill)
    c.circle(int(cx + r), int(cy - r * 0.6), int(r), fill)
    c.poly([(cx - s, cy - r * 0.1), (cx + s, cy - r * 0.1),
            (cx, cy + s * 0.95)], fill)


def cloud(c, cx, cy, s):
    w = (255, 255, 255)
    c.ellipse(int(cx - 60 * s), int(cy), int(130 * s), int(50 * s), w)
    c.ellipse(int(cx + 10 * s), int(cy - 25 * s), int(100 * s), int(70 * s), w)
    c.ellipse(int(cx + 110 * s), int(cy), int(80 * s), int(48 * s), w)
    c.ellipse(int(cx), int(cy + 15 * s), int(150 * s), int(40 * s), w)


def sunflower(c, cx, cy, stem_y, scale=1.0):
    c.thick_line(cx, stem_y, cx, cy + 80 * scale, (96, 146, 62), int(26 * scale))
    c.rotated_ellipse(cx - 95 * scale, cy + 300 * scale, 70 * scale,
                      38 * scale, -30, (110, 165, 70))
    c.rotated_ellipse(cx + 95 * scale, cy + 370 * scale, 70 * scale,
                      38 * scale, 30, (110, 165, 70))
    for k in range(12):
        a = math.radians(k * 30)
        px, py = cx + 95 * scale * math.sin(a), cy - 95 * scale * math.cos(a)
        c.rotated_ellipse(px, py, 34 * scale, 88 * scale, k * 30,
                          (255, 201, 60))
    c.circle(cx, cy, int(100 * scale), (122, 74, 33))
    for a in range(12):
        ang = a * 30 * math.pi / 180
        for rr in (35, 65):
            x = cx + rr * scale * math.cos(ang)
            y = cy + rr * scale * math.sin(ang)
            c.circle(int(x), int(y), int(9 * scale), (90, 52, 20))
    c.circle(cx, cy, int(14 * scale), (90, 52, 20))


def butterfly(c, cx, cy, s, upper, lower):
    c.rotated_ellipse(cx - 62 * s, cy - 55 * s, 55 * s, 85 * s, -35, upper)
    c.rotated_ellipse(cx + 62 * s, cy - 55 * s, 55 * s, 85 * s, 35, upper)
    c.rotated_ellipse(cx - 48 * s, cy + 55 * s, 40 * s, 60 * s, -30, lower)
    c.rotated_ellipse(cx + 48 * s, cy + 55 * s, 40 * s, 60 * s, 30, lower)
    c.thick_line(cx, cy - 105 * s, cx, cy + 105 * s, (60, 40, 30), int(14 * s))
    c.thick_line(cx, cy - 105 * s, cx - 34 * s, cy - 155 * s,
                 (60, 40, 30), int(7 * s))
    c.thick_line(cx, cy - 105 * s, cx + 34 * s, cy - 155 * s,
                 (60, 40, 30), int(7 * s))

# ---------------------------------------------------------------- build

def build():
    W2, H2 = W * S, H * S
    c = Canvas(W2, H2)
    c.vgrad([
        (0.00, (255, 226, 176)),
        (0.45, (255, 196, 132)),
        (0.75, (255, 164, 124)),
        (1.00, (255, 190, 148)),
    ])

    # ---- sun with flat halo and rays
    c.circle(1580, 430, 330, (255, 214, 140))
    c.circle(1580, 430, 280, (255, 210, 110))
    for k in range(12):
        ang = k * 30 * math.pi / 180
        c.thick_line(1580 + 250 * math.cos(ang), 430 + 250 * math.sin(ang),
                     1580 + 350 * math.cos(ang), 430 + 350 * math.sin(ang),
                     (255, 205, 80), 26)
    c.circle(1580, 430, 200, (255, 214, 70))

    # ---- clouds, birds, floating hearts
    cloud(c, 430, 380, 1.0)
    cloud(c, 1250, 300, 0.8)
    cloud(c, 1750, 800, 0.65)
    for (bx, by) in [(600, 500), (760, 440), (900, 540)]:
        c.arc(bx, by, 30, 30, 200, 340, (90, 60, 40), 10)
    for (hx, hy, hs, hc) in [
            (420, 700, 46, (255, 110, 140)),
            (1180, 660, 38, (255, 130, 160)),
            (1380, 600, 34, (255, 150, 180)),
            (700, 900, 30, (255, 120, 150))]:
        heart(c, hx, hy, hs, hc)

    # ---- rolling hills
    pts = [(x, 1330 + 90 * math.sin(x / W2 * 2 * math.pi * 1.2 + 0.5))
           for x in range(0, W2 + 1, 32)]
    pts += [(W2, H2), (0, H2)]
    c.poly(pts, (140, 196, 112))
    pts = [(x, 1560 + 70 * math.sin(x / W2 * 2 * math.pi * 1.6 + 2.0))
           for x in range(0, W2 + 1, 32)]
    pts += [(W2, H2), (0, H2)]
    c.poly(pts, (106, 176, 96))

    # ---- little grass flowers
    for (fx, fy, fc) in [
            (180, 1760, (255, 255, 255)), (520, 1850, (255, 210, 90)),
            (880, 1790, (255, 150, 180)), (1180, 1880, (255, 255, 255)),
            (1440, 1800, (255, 210, 90)), (1700, 1900, (255, 150, 180)),
            (1930, 1780, (255, 255, 255)), (60, 1920, (255, 210, 90)),
            (1990, 1950, (255, 150, 180)), (350, 1950, (255, 255, 255))]:
        for a in range(5):
            ang = a * 72 * math.pi / 180
            c.circle(int(fx + 13 * math.cos(ang)), int(fy + 13 * math.sin(ang)),
                     9, fc)
        c.circle(fx, fy, 8, (255, 180, 40))
    # ---- sunflowers
    sunflower(c, 330, 1330, 1980, 1.0)
    sunflower(c, 1730, 1400, 1990, 1.0)
    sunflower(c, 1480, 1620, 2010, 0.7)

    # ---- puppy: shoulders, ears, head
    c.ellipse(1024, 1875, 385, 230, (232, 164, 80))
    c.rotated_ellipse(700, 1330, 150, 280, 24, (198, 122, 44))
    c.rotated_ellipse(1350, 1330, 150, 280, -24, (198, 122, 44))
    c.circle(1024, 1360, 390, (242, 178, 92))
    c.poly([(985, 985), (1010, 920), (1030, 990)], (232, 164, 80))
    c.poly([(1020, 975), (1050, 915), (1070, 985)], (232, 164, 80))
    # collar + tag
    c.arc(1024, 1725, 325, 225, 20, 160, (214, 69, 65), 46)
    c.circle(1024, 1890, 55, (255, 214, 70))
    heart(c, 1024, 1882, 26, (214, 69, 65))
    # muzzle, nose, open smile, tongue
    c.ellipse(1025, 1585, 195, 115, (250, 216, 164))
    c.poly([(950, 1415), (1100, 1415), (1024, 1515)], (56, 36, 28))
    c.ellipse(1002, 1442, 18, 13, (255, 255, 255))
    c.sector(1025, 1650, 125, 90, 0, 180, (124, 56, 42))
    c.ellipse(1025, 1678, 50, 48, (255, 138, 158))
    c.thick_line(1024, 1640, 1024, 1720, (230, 100, 120), 8)
    # happy closed eyes + lashes
    c.arc(830, 1300, 70, 70, 200, 340, (70, 45, 30), 28)
    c.arc(1220, 1300, 70, 70, 200, 340, (70, 45, 30), 28)
    for (lx0, ly0, lx1, ly1) in [
            (772, 1255, 738, 1222), (782, 1285, 744, 1278),
            (1278, 1255, 1312, 1222), (1268, 1285, 1306, 1278)]:
        c.thick_line(lx0, ly0, lx1, ly1, (70, 45, 30), 10)
    # blush
    c.ellipse(745, 1530, 55, 30, (255, 150, 160))
    c.ellipse(1305, 1530, 55, 30, (255, 150, 160))
    # paws
    c.ellipse(825, 1965, 125, 65, (250, 214, 160))
    c.ellipse(1225, 1965, 125, 65, (250, 214, 160))
    for tx in (790, 860, 1190, 1260):
        c.thick_line(tx, 1960, tx, 2010, (200, 150, 90), 8)

    # ---- butterflies
    butterfly(c, 520, 880, 1.0, (255, 150, 60), (255, 190, 90))
    butterfly(c, 1620, 980, 0.85, (170, 120, 255), (200, 160, 255))

    small = downscale2(c.buf, W2, H2)
    return encode_png(W, H, small)

def fallback():
    if os.path.exists(ASSET):
        os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
        shutil.copyfile(ASSET, OUT)
        return 0
    raise SystemExit("generation failed and no bundled entry.png found")


def main():
    try:
        png = build()
    except Exception:
        if os.environ.get("MAKEFUN_DEBUG"):
            raise
        return fallback()
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
