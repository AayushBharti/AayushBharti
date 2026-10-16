"""Render the photo -> AB logo reveal as 800px PNG frames (build.sh encodes them).

usage: python render.py [start] [end]   (env: FPS, ZOOM, OUTDIR)
Reads build/photo1000.png, build/A800.png, build/B800.png (made by build.sh)
and writes build/<OUTDIR>/fNNNN.png.
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(BUILD, os.environ.get("OUTDIR", "frames"))
os.makedirs(OUT, exist_ok=True)

S = 800  # render size
FPS = int(os.environ.get("FPS", "20"))
DUR = 8.0
N = int(FPS * DUR)
BLUE = (59, 130, 246)

photo = Image.open(os.path.join(BUILD, "photo1000.png")).convert("RGB")
A = Image.open(os.path.join(BUILD, "A800.png")).convert("RGBA")
B = Image.open(os.path.join(BUILD, "B800.png")).convert("RGBA")
LOGO = Image.alpha_composite(A.copy(), B)
LOGO_ALPHA = LOGO.split()[3]
bbox = LOGO_ALPHA.getbbox()  # logo bounds for guides


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, start, dur):
    return clamp((t - start) / dur)


def smooth(p):
    return p * p * (3 - 2 * p)


def out_expo(p):
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def in_cubic(p):
    return p * p * p


def out_back(p, c=1.4):
    return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2


# Radial distance field, 0 centre .. ~1.41 corners
yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
R = np.hypot(xx - S / 2, yy - S / 2) / (S / 2)


def photo_at(zoom, dx=0.0):
    """Photo cropped to S with a centred zoom and small horizontal drift."""
    w = photo.width / zoom
    cx = photo.width / 2 + dx
    cy = photo.height / 2 - (photo.height - w) / 2 * 0.3  # zoom toward the face
    box = (cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2)
    return photo.resize((S, S), Image.LANCZOS, box=box)


def iris_mask(open_amt):
    """Darkness mask (0..255): open_amt 1 = no dark, 0 = fully dark.
    A soft circle closing toward the centre."""
    radius = -0.25 + 1.9 * open_amt
    soft = 0.3
    d = np.clip((R - radius) / soft + 0.5, 0, 1)
    d = d * d * (3 - 2 * d)
    return Image.fromarray((d * 255).astype(np.uint8), "L")


def letters_layer(t):
    """A and B with position, motion blur and the impact bump."""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    off = S * 0.62

    def pos(tt):
        # Intro is the outro reversed: both letters fly in together while the
        # iris closes (out-cubic), and split back out while it opens (in-cubic).
        p = prog(tt, 2.9, 0.5)
        en = 1 - (1 - p) ** 3
        ex = in_cubic(prog(tt, 6.3, 0.5))
        d = off * 1.1 * ((1 - en) + ex)
        vis = 1.0 if tt >= 2.9 else 0.0
        return -d, d, vis, vis

    # Impact bump when they meet (~3.45s), and a tiny settle.
    bump_p = prog(t, 3.4, 0.6)
    bump = 1 + 0.07 * math.sin(math.pi * clamp(bump_p * 1.0)) * (1 - bump_p) if 0 < bump_p < 1 else 1

    samples = 16
    acc = None
    for i in range(samples):
        tt = t - (i / samples) * (1 / FPS) * 1.6  # shutter
        xa, xb, aa, ab = pos(tt)
        frame = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        for img, x, a in ((A, xa, aa), (B, xb, ab)):
            if a <= 0:
                continue
            im = img
            if a < 1:
                al = im.split()[3].point(lambda v, a=a: int(v * a))
                im = im.copy()
                im.putalpha(al)
            frame.alpha_composite(im, (int(round(x)), 0))
        arr = np.asarray(frame, dtype=np.float32)
        acc = arr if acc is None else acc + arr
    layer = Image.fromarray((acc / samples).astype(np.uint8), "RGBA")

    if bump != 1:
        w = int(S * bump)
        big = layer.resize((w, w), Image.LANCZOS)
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        layer.alpha_composite(big, ((S - w) // 2, (S - w) // 2))
    return layer


def sheen(t, layer):
    """Diagonal light sweep across the settled logo."""
    p = prog(t, 4.35, 0.9)
    if p <= 0 or p >= 1:
        return layer
    centre = -0.4 + 1.8 * smooth(p)
    band = np.exp(-(((xx + yy * 0.6) / (S * 1.6) - centre) ** 2) / 0.0022)
    band[band < 0.02] = 0  # drop invisible tails (alpha < 4) so only the band repaints
    glow = Image.fromarray((band * 200).astype(np.uint8), "L")
    glow = ImageChops.multiply(glow, layer.split()[3])
    tint = Image.new("RGBA", (S, S), (200, 222, 255, 0))
    tint.putalpha(glow)
    base = layer.copy()
    # darken letter a hair under the sweep to make it read as light, not paint
    return Image.alpha_composite(base, tint)


def glow_amt(t):
    """Halo strength: flares as the letters lock, settles to a soft backlight,
    fades as they split."""
    if t < 3.32:
        return 0.0
    rise = smooth(prog(t, 3.32, 0.14))
    settle = smooth(prog(t, 3.5, 0.6))
    level = 1.0 - 0.62 * settle
    out = smooth(prog(t, 6.12, 0.3))
    return rise * level * (1 - out)


def halo(t, img, logo):
    """Blue backlight shaped by the letters themselves (additive), plus a thin
    anamorphic streak through the seam at the moment of impact."""
    g = glow_amt(t)
    flash = (1 - smooth(prog(t, 3.42, 0.45))) * smooth(prog(t, 3.34, 0.08))
    if g <= 0 and flash <= 0:
        return img
    alpha = logo.split()[3]
    wide = np.asarray(alpha.filter(ImageFilter.GaussianBlur(46)), dtype=np.float32) / 255
    tight = np.asarray(alpha.filter(ImageFilter.GaussianBlur(14)), dtype=np.float32) / 255
    base = np.asarray(img.convert("RGB"), dtype=np.float32)
    add = (
        np.clip(wide * 1.9, 0, 1)[..., None] * np.array([37, 99, 235]) * 0.95 * g
        + np.clip(tight * 1.6, 0, 1)[..., None] * np.array([96, 165, 250]) * 0.55 * g
    )
    if flash > 0:
        x0, y0, x1, y1 = bbox
        cy = (y0 + y1) / 2
        cx = (x0 + x1) / 2 + 18
        streak = np.exp(-((yy - cy) ** 2) / (2 * 2.2**2)) * np.exp(-((xx - cx) ** 2) / (2 * 230**2))
        core = np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * 26**2))
        add = add + core[..., None] * np.array([90, 140, 255]) * flash
    out = np.clip(base + add, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB").convert("RGBA")


def guides(t, img):
    """Hairline frame guides that draw in around the logo (the site's bands)."""
    pin = smooth(prog(t, 3.7, 0.5))
    pout = smooth(prog(t, 6.05, 0.3))
    k = pin * (1 - pout)
    if k <= 0:
        return img
    x0, y0, x1, y1 = bbox
    pad = 34
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = (255, 255, 255, int(46 * k))
    reach = S * pin  # lines grow out from the centre
    c = S / 2
    for y in (y0, y1):
        d.line((c - reach / 2 - 2, y, c + reach / 2 + 2, y), fill=col, width=2)
    for x in (x0, x1):
        d.line((x, c - reach / 2 - 2, x, c + reach / 2 + 2), fill=col, width=2)
    # square nodes where the lines cross
    nk = smooth(prog(t, 4.2, 0.3)) * (1 - pout)
    for x in (x0, x1):
        for y in (y0, y1):
            d.rectangle((x - 5, y - 5, x + 5, y + 5), fill=(10, 10, 10, int(255 * nk)), outline=(255, 255, 255, int(110 * nk)), width=2)
    # fade the line ends toward the canvas edge
    fade = Image.fromarray((np.clip(1.25 - R, 0, 1) ** 1.2 * 255).astype(np.uint8), "L")
    layer.putalpha(ImageChops.multiply(layer.split()[3], fade))
    return Image.alpha_composite(img, layer)


def frame(i):
    t = i / FPS
    # Slow, settled phases step at 12fps (GIF size); motion stays at full rate.
    if 3.7 < t < 6.25:
        t = math.floor(t * 12) / 12
    # Zoom: slow drift, pushes in as the iris closes, eases back on exit.
    z_in = smooth(prog(t, 1.6, 2.2))
    z_out = smooth(prog(t, 6.3, 1.6))
    zoom = 1.0 + float(os.environ.get("ZOOM", "0")) * z_in * (1 - z_out)
    base = photo_at(zoom).convert("RGBA")

    # Darkness: iris closes 1.8 -> 3.4, opens with the split 6.35 -> 7.5.
    close = smooth(prog(t, 2.8, 0.6))
    reopen = smooth(prog(t, 6.3, 0.6))
    open_amt = 1 - close * (1 - reopen)
    mask = iris_mask(open_amt)
    # plus an overall dim so the centre goes fully black too
    dim = 0.0
    m = np.maximum(np.asarray(mask, dtype=np.float32) / 255, dim)
    black = Image.new("RGBA", (S, S), (6, 6, 8, 255))
    base = Image.composite(black, base, Image.fromarray((m * 255).astype(np.uint8), "L"))

    # guides removed
    letters = letters_layer(t)
    base = halo(t, base, letters)
    logo = sheen(t, letters)
    base = Image.alpha_composite(base, logo)
    return base.convert("RGB")


start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
end = int(sys.argv[2]) if len(sys.argv) > 2 else N
for i in range(start, end):
    frame(i).save(os.path.join(OUT, f"f{i:04d}.png"))
print("frames", start, end, "of", N)
