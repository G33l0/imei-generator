#!/usr/bin/env python3
"""Render the G2 logo, launcher icons and presplash into assets/.

The mark is a SIM card silhouette (clipped corner) drawn as a gold outline,
with a "G2" monogram set in Space Grotesk Bold. Requires Pillow.
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
FONT = os.path.join(ASSETS, "fonts", "SpaceGrotesk-Bold.ttf")

BLACK = (11, 11, 12, 255)
GOLD_LIGHT = (245, 214, 128)
GOLD = (212, 175, 55)
GOLD_DARK = (150, 112, 30)
SS = 4  # supersampling factor


def gradient(size):
    """Diagonal gold gradient: light top-left -> deep bottom-right."""
    w, h = size
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    stops = [(0.0, GOLD_LIGHT), (0.55, GOLD), (1.0, GOLD_DARK)]
    for y in range(h):
        for x in range(0, w):
            t = (x / w * 0.35 + y / h * 0.65)
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t <= t1:
                    k = (t - t0) / (t1 - t0)
                    px[x, y] = tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))
                    break
    return grad


def sim_polygon(x0, y0, x1, y1, cut):
    return [(x0, y0), (x1 - cut, y0), (x1, y0 + cut), (x1, y1), (x0, y1)]


def mark(size, background=None, scale=1.0):
    """Return an RGBA image of the mark centred on a `size` square canvas."""
    S = size * SS
    img = Image.new("RGBA", (S, S), background or (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)

    w = S * 0.62 * scale
    h = w * 1.22
    x0, y0 = (S - w) / 2, (S - h) / 2
    x1, y1 = x0 + w, y0 + h
    stroke = max(2, int(w * 0.055))
    cut = w * 0.26
    d.polygon(sim_polygon(x0, y0, x1, y1, cut), fill=255)
    i = stroke
    d.polygon(sim_polygon(x0 + i, y0 + i, x1 - i, y1 - i, cut - i * 0.42), fill=0)

    # Monogram, optically centred slightly below the geometric centre.
    font = ImageFont.truetype(FONT, int(w * 0.50))
    text = "G2"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (S - tw) / 2 - bbox[0]
    ty = y0 + (h - th) / 2 - bbox[1] + h * 0.04
    d.text((tx, ty), text, font=font, fill=255)

    # Short contact bar under the monogram, a nod to the SIM chip.
    bw, bh = w * 0.30, stroke * 0.8
    by = ty + bbox[3] + h * 0.07
    d.rounded_rectangle(((S - bw) / 2, by, (S + bw) / 2, by + bh), radius=bh / 2, fill=255)

    img.paste(gradient((S, S)), (0, 0), mask)
    return img.resize((size, size), Image.LANCZOS)


def rounded_bg(size, radius_ratio=0.22):
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=S * radius_ratio, fill=BLACK)
    # Hairline gold border for definition on dark launchers.
    d.rounded_rectangle((SS * 3, SS * 3, S - 1 - SS * 3, S - 1 - SS * 3),
                        radius=S * radius_ratio - SS * 3, outline=GOLD + (90,), width=SS * 3)
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    # In-app header logo (transparent).
    mark(256).save(os.path.join(ASSETS, "logo.png"))
    # Legacy launcher icon: black rounded tile + mark.
    icon = rounded_bg(512)
    icon.alpha_composite(mark(512, scale=0.92))
    icon.save(os.path.join(ASSETS, "icon.png"))
    # Adaptive icon layers (mark kept inside the 66% safe zone).
    mark(432, scale=0.66).save(os.path.join(ASSETS, "icon_fg.png"))
    Image.new("RGBA", (432, 432), BLACK).save(os.path.join(ASSETS, "icon_bg.png"))
    # Presplash: mark on black.
    splash = Image.new("RGBA", (720, 720), BLACK)
    splash.alpha_composite(mark(720, scale=0.55))
    splash.save(os.path.join(ASSETS, "presplash.png"))
    print("Wrote logo.png, icon.png, icon_fg.png, icon_bg.png, presplash.png to assets/")


if __name__ == "__main__":
    main()
