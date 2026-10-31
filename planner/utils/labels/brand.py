"""A project's label branding as plain values, and the colour rules.

``brand_for`` is the only function here that touches the database. The rules
-- what a colour may be, which text colour reads on it, what each colour
becomes in black & white, which logo goes on a label -- are pure, so they are
tested without fixtures.

With nothing set, labels print the default theme: charcoal at 85% black
toner only, white text, no accents, no logo.

The text colour rule
--------------------
WCAG 2 relative luminance L of the background. Text is white when
L < TEXT_THRESHOLD (0.1791), black otherwise. 0.1791 is where white and
black text give the same contrast, sqrt(1.05 x 0.05) - 0.05, and that
contrast is 4.58:1 -- so pure white or pure black text always clears WCAG
AA's 4.5:1, whatever the background. The same answer picks the logo: the
on-dark logo goes with white text.

Black & white
-------------
Each colour becomes the black-toner grey with the same luminance, so the
text decision is the same in both modes (navy #08274F is K85, the default
background). Accent greys are then moved, as little as possible, until every
grey is at least BW_SEPARATION K from the background's and from each
other's, or the bars would vanish into the background on a mono printer.
"""

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from planner.utils.labels.layout import Frame
from planner.utils.labels.stock import mm

ACCENT_STYLE_CHOICES = (
    ('none', 'None'),
    ('corner_bars', 'Angled corner bars'),
    ('edge_stripe', 'Edge stripe'),
)
ACCENT_STYLES = tuple(key for key, _ in ACCENT_STYLE_CHOICES)
MAX_ACCENTS = 3

LOGO_KIND_CHOICES = (
    ('on_dark', 'Logo for dark backgrounds'),
    ('on_light', 'Logo for light backgrounds'),
    ('mark', 'Logo mark (icon only)'),
)
LOGO_KINDS = tuple(key for key, _ in LOGO_KIND_CHOICES)

# Round 1 "Dark": charcoal from black toner alone.
DEFAULT_BG_K = 85

# Kept clear above the safe zone's bottom edge for each accent style. The
# edge stripe lies outside the safe zone (2 mm of a 3.2 mm inset), so it
# needs none.
ACCENT_FOOTER_MM = {'none': 0, 'corner_bars': 5, 'edge_stripe': 0}

TEXT_THRESHOLD = math.sqrt(1.05 * 0.05) - 0.05

BW_SEPARATION = 20

# Below this at its printed size a logo looks soft; the branding page warns.
MIN_PRINT_DPI = 250

# A logo mark is used as uploaded on any background; below this contrast
# with the background (its opaque pixels' mean luminance) the page warns.
MARK_MIN_CONTRAST = 3.0

_HEX = re.compile(r'^#?([0-9A-Fa-f]{6})$')


class BrandError(ValueError):
    """A branding value that is not allowed. ``str()`` is user-safe."""


def parse_hex(value):
    """'#RRGGBB' upper-case from '#rrggbb' or 'rrggbb'; anything else raises."""
    match = _HEX.match((value or '').strip())
    if not match:
        raise BrandError('"{}" is not a colour like #08274F.'.format(value))
    return '#' + match.group(1).upper()


def parse_accents(values):
    """0-3 colours, blanks dropped, each parsed by parse_hex."""
    accents = [parse_hex(v) for v in values if (v or '').strip()]
    if len(accents) > MAX_ACCENTS:
        raise BrandError('At most {} accent colours.'.format(MAX_ACCENTS))
    return accents


def parse_style(value):
    if value not in ACCENT_STYLES:
        raise BrandError('Unknown accent style.')
    return value


# ---------------------------------------------------------------- luminance

def _linear(channel):
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance_rgb(r, g, b):
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def luminance(hex_colour):
    h = parse_hex(hex_colour)
    return luminance_rgb(int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def contrast(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def grey_luminance(k):
    """Luminance of a K-only grey, ``k`` in percent."""
    return _linear(255 * (1 - k / 100))


def k_for_luminance(lum):
    """The K-only grey, in whole percent, with luminance ``lum``."""
    s = 12.92 * lum if lum <= 0.0031308 else 1.055 * lum ** (1 / 2.4) - 0.055
    return max(0, min(100, round(100 * (1 - s))))


def k_for_hex(hex_colour):
    return k_for_luminance(luminance(hex_colour))


@lru_cache(maxsize=256)
def bw_accent_greys(bg_k, accent_ks):
    """(greys, separated) for accents of natural greys ``accent_ks`` on a
    ``bg_k`` background: each as close to its own grey as possible while at
    least BW_SEPARATION from the background and from one another.
    ``separated`` is False, and the natural greys come back, if no set of
    greys can do that."""
    if not accent_ks:
        return (), True
    options = [sorted(set(range(0, 101, 5)) | {k}) for k in accent_ks]
    best, best_cost = None, None
    for combo in product(*options):
        values = (bg_k,) + combo
        if any(abs(a - b) < BW_SEPARATION
               for i, a in enumerate(values) for b in values[i + 1:]):
            continue
        cost = sum(abs(k - n) for k, n in zip(combo, accent_ks))
        if best_cost is None or cost < best_cost:
            best, best_cost = combo, cost
    if best is None:
        return tuple(accent_ks), False
    return best, True


# ---------------------------------------------------------------- brand

@dataclass(frozen=True)
class Logo:
    kind: str
    content: bytes
    width: int
    height: int

    @property
    def aspect(self):
        return self.width / self.height if self.height else 0.0

    def dpi_at(self, height_pt):
        """Pixels per inch when printed ``height_pt`` tall."""
        return self.height / (height_pt / 72) if height_pt else 0.0


@dataclass(frozen=True)
class Brand:
    bg: str = ''                # '#RRGGBB'; '' is the default charcoal
    accents: tuple = ()
    accent_style: str = 'none'
    logos: tuple = ()           # (Logo, ...)

    @property
    def style(self):
        """The accent style actually drawn: none without accent colours."""
        return self.accent_style if self.accents else 'none'

    @property
    def is_default(self):
        return not self.bg and self.style == 'none' and not self.logos

    @property
    def bg_luminance(self):
        return luminance(self.bg) if self.bg else grey_luminance(DEFAULT_BG_K)

    @property
    def bg_k(self):
        """The background in black & white, in percent K."""
        return k_for_hex(self.bg) if self.bg else DEFAULT_BG_K

    @property
    def text_white(self):
        return self.bg_luminance < TEXT_THRESHOLD

    @property
    def text_contrast(self):
        return contrast(1.0 if self.text_white else 0.0, self.bg_luminance)

    @property
    def full_logo_kind(self):
        return 'on_dark' if self.text_white else 'on_light'

    def logo(self, kind):
        return next((logo for logo in self.logos if logo.kind == kind), None)

    def logo_candidates(self):
        """The logos a label may print, best first: the full logo for this
        background, then the mark."""
        return tuple(logo for logo in (self.logo(self.full_logo_kind), self.logo('mark'))
                     if logo is not None)

    def frame(self):
        return Frame(footer=float(mm(ACCENT_FOOTER_MM[self.style])),
                     logos=tuple((logo.kind, logo.aspect) for logo in self.logo_candidates()))

    def bw_accents(self):
        """(K greys, separated) for the accents in black & white."""
        return bw_accent_greys(self.bg_k, tuple(k_for_hex(a) for a in self.accents))

    def describe(self):
        """One line for the print page."""
        if self.is_default:
            return 'none (default dark)'
        parts = [self.bg or 'default dark']
        if self.style != 'none':
            n = len(self.accents)
            parts.append('{} accent{}, {}'.format(
                n, '' if n == 1 else 's', dict(ACCENT_STYLE_CHOICES)[self.style].lower()))
        if self.logo_candidates():
            parts.append('logo')
        return ' · '.join(parts)


DEFAULT = Brand()


def brand_for(project, with_logo_content=True):
    """The project's Brand. Without logo content (for status lines and
    capacity) only the logos' sizes are loaded."""
    from planner.models import ProjectLogo

    if project is None:
        return DEFAULT
    rows = ProjectLogo.objects.filter(project=project)
    if not with_logo_content:
        rows = rows.only('kind', 'width', 'height')
    logos = tuple(Logo(kind=row.kind, content=bytes(row.content) if with_logo_content else b'',
                       width=row.width, height=row.height)
                  for row in rows.order_by('kind'))
    accents = []
    for value in (project.brand_accent_colors or [])[:MAX_ACCENTS]:
        try:
            accents.append(parse_hex(value))
        except BrandError:
            continue
    try:
        bg = parse_hex(project.brand_bg_color) if project.brand_bg_color else ''
    except BrandError:
        bg = ''
    style = project.brand_accent_style if project.brand_accent_style in ACCENT_STYLES else 'none'
    return Brand(bg=bg, accents=tuple(accents), accent_style=style, logos=logos)
