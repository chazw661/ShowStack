"""Label stock: the one place a sheet's geometry is written down.

A stock is a config entry, not code. Every layout dimension is derived from
the label size (planner.utils.labels.layout), so adding a size means adding
an entry to STOCKS and nothing else.

All dimensions are exact Fractions in PDF points (1/72"). The manufacturer
quotes OL3016LP's vertical pitch as 17/6" -- 2.8333...", which no decimal
spells exactly -- and a rounded pitch drifts by the bottom row. Fractions keep
"left + 2 x pitch + width + right == 8.5 in" an identity, not a tolerance.

PDF coordinates put the origin at the bottom-left of the page with y going
up. Label positions are numbered the way a person counts them on the sheet:
1 is top-left, then across, then down.
"""

import math
from dataclasses import dataclass
from fractions import Fraction

POINTS_PER_INCH = 72
# 25.4 mm to the inch, exactly.
POINTS_PER_MM = Fraction(POINTS_PER_INCH * 10, 254)

# Calibration offsets past this are not printer drift, they are the wrong
# stock or the wrong paper size, and a bigger offset would push the safe zone
# off the label.
OFFSET_LIMIT_MM = 5

# Background fills run this far past the die line, so a sheet die-cut a
# little off still shows no white edge. Text and logos stay inside the safe
# zone, well clear of it.
BLEED_MM = '2.5'


def inches(value):
    """Points from inches, exactly. Pass a str or Fraction, not a float."""
    return Fraction(value) * POINTS_PER_INCH


def mm(value):
    """Points from millimetres, exactly for str/Fraction/int input."""
    return Fraction(value) * POINTS_PER_MM


@dataclass(frozen=True)
class Rect:
    """x, y is the bottom-left corner, in points."""
    x: Fraction
    y: Fraction
    w: Fraction
    h: Fraction

    @property
    def top(self):
        return self.y + self.h

    @property
    def right(self):
        return self.x + self.w

    def inset(self, d):
        return Rect(self.x + d, self.y + d, self.w - 2 * d, self.h - 2 * d)

    def contains(self, other, tolerance=0):
        return (other.x >= self.x - tolerance and other.y >= self.y - tolerance
                and other.right <= self.right + tolerance
                and other.top <= self.top + tolerance)


@dataclass(frozen=True)
class LabelStock:
    part: str
    description: str
    page_w: Fraction
    page_h: Fraction
    label_w: Fraction
    label_h: Fraction
    corner_r: Fraction
    margin_left: Fraction
    margin_top: Fraction
    pitch_x: Fraction
    pitch_y: Fraction
    cols: int
    rows: int
    # Where to buy this stock; blank hides the order link and the PDF line.
    supplier: str = ''
    order_url: str = ''

    @property
    def count(self):
        return self.cols * self.rows

    @property
    def margin_right(self):
        return self.page_w - self.margin_left - (self.cols - 1) * self.pitch_x - self.label_w

    @property
    def margin_bottom(self):
        return self.page_h - self.margin_top - (self.rows - 1) * self.pitch_y - self.label_h

    def label_rect(self, position, dx_mm=0, dy_mm=0):
        """The label at sheet position 1..count, shifted by the calibration
        offset. A positive dx moves it right; a positive dy moves it DOWN the
        sheet, which is how a person measuring a misprint describes it."""
        if not 1 <= position <= self.count:
            raise ValueError('position {} outside 1..{}'.format(position, self.count))
        col = (position - 1) % self.cols
        row = (position - 1) // self.cols
        x = self.margin_left + col * self.pitch_x + mm(_exact(dx_mm))
        top = self.page_h - self.margin_top - row * self.pitch_y - mm(_exact(dy_mm))
        return Rect(x, top - self.label_h, self.label_w, self.label_h)


def _exact(value):
    # A float offset like 0.1 is not 1/10 in binary; go through its shortest
    # decimal spelling so 0.1 mm means exactly 0.1 mm.
    if isinstance(value, float):
        return Fraction(repr(value))
    return Fraction(value)


STOCKS = {
    'OL3016LP': LabelStock(
        part='OL3016LP',
        description='OnlineLabels OL3016LP: 2" x 2" square, weatherproof laser, 12 per sheet',
        page_w=inches('8.5'),
        page_h=inches(11),
        label_w=inches(2),
        label_h=inches(2),
        corner_r=inches('0.125'),
        margin_left=inches('0.25'),
        margin_top=inches('0.25'),
        pitch_x=inches(3),
        pitch_y=inches(Fraction(17, 6)),
        cols=3,
        rows=4,
        supplier='OnlineLabels',
        order_url='https://www.onlinelabels.com/products/ol3016lp',
    ),
}

DEFAULT_STOCK = 'OL3016LP'


def order_link_text(stock):
    """The order URL as a person would type it: no scheme, no www."""
    url = stock.order_url
    for prefix in ('https://', 'http://', 'www.'):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.rstrip('/')


def order_line(stock):
    """The alignment page's "where to buy" line, or '' with no order URL."""
    if not stock.order_url:
        return ''
    name = ' '.join(p for p in (stock.supplier, stock.part) if p)
    return 'Labels: {} \u2014 {}'.format(name, order_link_text(stock))


def get_stock(part):
    """The stock for ``part``, or None for an unknown part number."""
    return STOCKS.get(part or DEFAULT_STOCK)


def clamp_offset(value):
    """A calibration offset in mm from untrusted input: anything that is not
    a finite number is 0, and the rest is clamped to +/-OFFSET_LIMIT_MM and
    rounded to 0.1 mm (the step the page's input offers)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    number = max(-OFFSET_LIMIT_MM, min(OFFSET_LIMIT_MM, number))
    return round(number, 1) + 0.0  # + 0.0 turns -0.0 into 0.0


def clamp_start(value, stock):
    """Start position 1..stock.count from untrusted input; 1 if unusable."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(stock.count, number))


def sheet_positions(stock, n, start=1):
    """(page_index, position) for n labels, filling from ``start`` on the
    first sheet (so a part-used sheet can go back in) and from 1 on every
    sheet after it."""
    out = []
    page, position = 0, start
    for _ in range(n):
        if position > stock.count:
            page, position = page + 1, 1
        out.append((page, position))
        position += 1
    return out


def sheets_needed(stock, n, start=1):
    if n <= 0:
        return 0
    return math.ceil((start - 1 + n) / stock.count)
