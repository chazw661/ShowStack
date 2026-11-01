"""Colour read out of a logo: "Suggest from logo", the mark's contrast
check, and the greyscale copy black & white labels print. Pillow only.

Suggestions are only suggestions: the page shows them and nothing is saved
until the user saves.

How the accents are picked:

1. The logo at 128 px, its transparent pixels (alpha < 128) dropped.
2. Median-cut to 8 colours, each with its pixel count.
3. Colours under 5% of the logo dropped -- mostly the blends anti-aliasing
   leaves where two colours meet -- and colours with little colour in them:
   CIELAB chroma under 20 (white, black, greys and near-greys), or
   lightness under 10.
4. Colours within delta E 12 of a bigger one merged into it.
5. Colours within delta E 20 of the background dropped -- an accent the same
   colour as the label vanishes.
6. The rest, biggest share first, up to three.
"""

from io import BytesIO

from PIL import Image

from planner.utils.labels.brand import MAX_ACCENTS, luminance_rgb, parse_hex

SAMPLE_EDGE = 128
OPAQUE = 128
MIN_SHARE = 0.05
MIN_CHROMA = 20
MIN_LIGHTNESS = 10
MERGE_DELTA_E = 12
BG_DELTA_E = 20


def _opaque_pixels(data):
    with Image.open(BytesIO(data)) as img:
        img = img.convert('RGBA')
        img.thumbnail((SAMPLE_EDGE, SAMPLE_EDGE))
        return [(r, g, b) for r, g, b, a in img.getdata() if a >= OPAQUE]


def mean_luminance(data):
    """Mean relative luminance of a logo's opaque pixels; None if it has none."""
    pixels = _opaque_pixels(data)
    if not pixels:
        return None
    return sum(luminance_rgb(*p) for p in pixels) / len(pixels)


def _lab(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _delta_e(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


def _hex(rgb):
    return '#{:02X}{:02X}{:02X}'.format(*rgb)


def suggest_accents(data, bg=None):
    """Up to three '#RRGGBB' accent colours from a logo, biggest share first."""
    pixels = _opaque_pixels(data)
    if not pixels:
        return []
    strip = Image.new('RGB', (len(pixels), 1))
    strip.putdata(pixels)
    quantised = strip.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantised.getpalette()
    counted = sorted(quantised.getcolors(), reverse=True)
    bg_lab = _lab(tuple(int(parse_hex(bg)[i:i + 2], 16) for i in (1, 3, 5))) if bg else None

    kept = []           # [(lab, rgb)]
    for count, index in counted:
        if count < MIN_SHARE * len(pixels):
            continue
        rgb = tuple(palette[3 * index:3 * index + 3])
        lab = _lab(rgb)
        chroma = (lab[1] ** 2 + lab[2] ** 2) ** 0.5
        if chroma < MIN_CHROMA or lab[0] < MIN_LIGHTNESS:
            continue
        if bg_lab is not None and _delta_e(lab, bg_lab) < BG_DELTA_E:
            continue
        if any(_delta_e(lab, other) < MERGE_DELTA_E for other, _ in kept):
            continue
        kept.append((lab, rgb))
    return [_hex(rgb) for _, rgb in kept[:MAX_ACCENTS]]


def greyscale_png(data):
    """The logo as a greyscale PNG, alpha kept, for black & white labels."""
    with Image.open(BytesIO(data)) as img:
        has_alpha = img.mode in ('RGBA', 'LA') or 'transparency' in img.info
        out = img.convert('LA' if has_alpha else 'L')
    buffer = BytesIO()
    out.save(buffer, format='PNG')
    return buffer.getvalue()
