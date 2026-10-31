"""Where everything sits on one label. Pure: no canvas, no database.

Every dimension is a fraction of the label's side S, so a new stock size
needs no layout changes; font sizes have absolute floors on top of that,
because a 9 pt line is the smallest that reads at arm's length whatever the
label. For OL3016LP (S = 144 pt) the numbers come out as:

    safe inset      max(S/16, 3.2 mm)   9.07 pt  3.2 mm
    header band     0.26 S              37.44 pt 13.2 mm
    header->panel   0.015 S              2.16 pt
    panel margin    0.03 S               4.32 pt (tint shows round the panel)
    panel padding   0.04 S x, 0.015 S y  5.76 / 2.16 pt
    text box                            105.70 x 77.62 pt  (37.3 x 27.4 mm)

A running order fits six one-line names on a label, and five when every
name opens a new session and so brings a divider.

Text is stacked with the font's real ascent and descent, so a line's box --
what the tests check against the safe zone and the panel -- holds stacked
Vietnamese diacritics too.

Layouts are in label-local points (origin at the label's bottom-left) as
floats; the renderer translates them onto the sheet.
"""

import re
from dataclasses import dataclass, field

from planner.utils.labels import fonts
from planner.utils.labels.data import pack_label
from planner.utils.labels.stock import Rect, mm

ELLIPSIS = '…'

# Floors, in points, whatever the stock.
SINGLE_NAME_FLOOR = 14
RUNNING_NAME_FLOOR = 11
OTHER_FLOOR = 9
SIZE_STEP = 0.5

NAME_LEADING = 1.12
META_LEADING = 1.15
HEADER_LEADING = 1.1

# Noto Sans cap height (and lining-figure height), em.
CAP_HEIGHT = 0.714

# Second line of a wrapped running-order name, so it reads as the same row.
WRAP_INDENT = 6

# Extra space where a running order moves to the next session, x the name
# size (3.3 pt at the 11 pt floor). A 0.5 pt hairline sits in the middle of
# it. Checked against real glyph boxes: at the floor it clears the descender
# of "Phil Jacobs" above and the stacked accents of "Nguyễn Đặng" below.
DIVIDER_GAP = 0.3

# Running order is only offered where the worst case -- every name opening a
# new session, so every name brings a divider -- still shows this many.
RUNNING_MIN_NAMES = 3


@dataclass(frozen=True)
class Geometry:
    size: float
    corner_r: float
    label: Rect
    safe: Rect
    band: Rect
    panel: Rect
    panel_r: float
    text: Rect
    header_pad: float
    single_name_max: float
    meta_max: float
    small: float            # header lines and "RF": the 9 pt tier
    number: float           # the RF number in the header


def geometry(stock):
    s = float(stock.label_w)
    inset = max(s / 16, float(mm('3.2')))
    label = Rect(0.0, 0.0, s, float(stock.label_h))
    safe = label.inset(inset)
    band_h = 0.26 * s
    band = Rect(safe.x, safe.top - band_h, safe.w, band_h)
    margin = 0.03 * s
    gap = 0.015 * s
    panel = Rect(safe.x + margin, safe.y + margin,
                 safe.w - 2 * margin, band.y - gap - (safe.y + margin))
    pad_x, pad_y = 0.04 * s, 0.015 * s
    text = Rect(panel.x + pad_x, panel.y + pad_y, panel.w - 2 * pad_x, panel.h - 2 * pad_y)
    return Geometry(
        size=s, corner_r=float(stock.corner_r), label=label, safe=safe, band=band,
        panel=panel, panel_r=0.05 * s, text=text, header_pad=0.04 * s,
        single_name_max=max(SINGLE_NAME_FLOOR, 0.18 * s),
        meta_max=max(OTHER_FLOOR, 0.07 * s),
        small=max(OTHER_FLOOR, s / 16),
        number=0.75 * band_h,
    )


# ---------------------------------------------------------------- text runs

@dataclass(frozen=True)
class Run:
    text: str
    font: str
    size: float
    x: float                # left edge
    y: float                # baseline
    role: str               # 'header' | 'name' | 'meta'
    floor: float = 0

    @property
    def width(self):
        return fonts.string_width(self.text, self.font, self.size)

    @property
    def bbox(self):
        if self.text.isascii() and self.text.isdigit():
            # Lining figures: cap height, nothing below the baseline. The
            # font's ascent makes room for stacked accents a number never has.
            return Rect(self.x, self.y, self.width, CAP_HEIGHT * self.size)
        d = fonts.descent(self.font, self.size)
        return Rect(self.x, self.y - d, self.width, d + fonts.ascent(self.font, self.size))


@dataclass
class LabelLayout:
    geometry: Geometry
    runs: list = field(default_factory=list)
    rules: list = field(default_factory=list)     # (x1, y, x2) hairlines
    name_lines: int = 0                          # for tests: lines of presenter text
    truncated: bool = False


def _fits(text, font, size, width):
    return fonts.string_width(text, font, size) <= width + 1e-6


def ellipsize(text, font, size, width):
    if _fits(text, font, size, width):
        return text
    while text and not _fits(text.rstrip() + ELLIPSIS, font, size, width):
        text = text[:-1]
    return text.rstrip() + ELLIPSIS


# A break is allowed after a space or after a hyphen ("Müller-|Łukasz").
_TOKENS = re.compile(r'[^ -]+-?|-| +')


def wrap(text, font, size, width, max_lines=2, indent=0):
    """Break ``text`` into at most ``max_lines`` lines of ``width``, later
    lines indented by ``indent``. Returns (lines, truncated); only the last
    line ever gets an ellipsis. Words wider than a line break mid-word."""
    lines, rest = [], text.strip()
    for i in range(max_lines):
        available = width - (indent if i else 0)
        if not rest:
            break
        if _fits(rest, font, size, available):
            lines.append(rest)
            return lines, False
        if i == max_lines - 1:
            lines.append(ellipsize(rest, font, size, available))
            return lines, True
        taken, best = '', 0
        for token in _TOKENS.findall(rest):
            taken += token
            if _fits(taken.rstrip(), font, size, available):
                best = len(taken)
            else:
                break
        if not rest[:best].strip():
            best = 1
            while best < len(rest) and _fits(rest[:best + 1], font, size, available):
                best += 1
        lines.append(rest[:best].rstrip())
        rest = rest[best:].strip()
    return lines, False


def _whole_words(text, font, size, width):
    """True when every word fits a line, so wrapping never has to break one
    mid-word. Sizes above the floor must pass this."""
    return all(_fits(token.strip(), font, size, width)
               for token in _TOKENS.findall(text) if token.strip())


def _stack_height(lines):
    """lines: [(font, size, advance)]. Ascent of the first line, the
    baseline-to-baseline advances, descent of the last."""
    if not lines:
        return 0.0
    font, size, _ = lines[0]
    total = fonts.ascent(font, size)
    for _, _, advance in lines[1:]:
        total += advance
    font, size, _ = lines[-1]
    return total + fonts.descent(font, size)


def _sizes(maximum, floor):
    size = maximum
    while size > floor + 1e-9:
        yield size
        size -= SIZE_STEP
    yield floor


# ---------------------------------------------------------------- header

def _header(layout, g, lines, pack, part=None):
    band, pad = g.band, g.header_pad
    cap = CAP_HEIGHT
    baseline = band.y + (band.h - cap * g.number) / 2
    x = band.x + pad
    # A small column left of the number: "RF" level with the number's cap
    # height, and on a pack's continuation labels "1/2" level with its
    # baseline. Stacked rather than strung out after the number, so the
    # right block keeps the width for "Tue Nov 3".
    column = [Run('RF', fonts.BOLD, g.small, x,
                  baseline + cap * (g.number - g.small), 'header', OTHER_FLOOR)]
    if part:
        column.append(Run('{}/{}'.format(*part), fonts.BOLD, g.small, x, baseline,
                          'header', OTHER_FLOOR))
    layout.runs.extend(column)
    x += max(run.width for run in column) + 2
    number = pack_label(pack)
    layout.runs.append(Run(number, fonts.BOLD, g.number, x, baseline, 'header', OTHER_FLOOR))
    x += fonts.string_width(number, fonts.BOLD, g.number)

    right = band.right - pad
    width = right - (x + 6)
    if len(lines) == 1:
        texts, _ = wrap(lines[0], fonts.BOLD, g.small, width)
    else:
        texts = [ellipsize(line, fonts.BOLD, g.small, width) for line in lines[:3]]
    advance = g.small * HEADER_LEADING
    height = _stack_height([(fonts.BOLD, g.small, advance)] * len(texts))
    y = band.y + (band.h + height) / 2 - fonts.ascent(fonts.BOLD, g.small)
    for text in texts:
        w = fonts.string_width(text, fonts.BOLD, g.small)
        layout.runs.append(Run(text, fonts.BOLD, g.small, right - w, y, 'header', OTHER_FLOOR))
        y -= advance


# ---------------------------------------------------------------- single name

def layout_single(item, stock):
    g = geometry(stock)
    layout = LabelLayout(g)
    _header(layout, g, [item.day_label], item.pack)
    box = g.text

    meta = [t for t in (item.time, item.session) if t]
    meta_size = OTHER_FLOOR
    for size in _sizes(g.meta_max, OTHER_FLOOR):
        if all(_fits(t, fonts.REGULAR, size, box.w) for t in meta):
            meta_size = size
            break
    meta = [ellipsize(t, fonts.REGULAR, meta_size, box.w) for t in meta]
    advance = meta_size * META_LEADING
    y = box.y + fonts.descent(fonts.REGULAR, meta_size) + advance * (len(meta) - 1)
    for t in meta:
        layout.runs.append(Run(t, fonts.REGULAR, meta_size, box.x, y, 'meta', OTHER_FLOOR))
        y -= advance
    meta_top = box.y + _stack_height([(fonts.REGULAR, meta_size, advance)] * len(meta))

    area_bottom = meta_top + 0.02 * g.size if meta else box.y
    area_h = box.top - area_bottom
    chosen = None
    for size in _sizes(g.single_name_max, SINGLE_NAME_FLOOR):
        lines, truncated = wrap(item.name, fonts.BOLD, size, box.w)
        height = _stack_height([(fonts.BOLD, size, size * NAME_LEADING)] * len(lines))
        if not truncated and height <= area_h and _whole_words(item.name, fonts.BOLD, size, box.w):
            chosen = (size, lines, truncated, height)
            break
    if chosen is None:
        size = SINGLE_NAME_FLOOR
        lines, truncated = wrap(item.name, fonts.BOLD, size, box.w)
        chosen = (size, lines, truncated,
                  _stack_height([(fonts.BOLD, size, size * NAME_LEADING)] * len(lines)))
    size, lines, truncated, height = chosen
    y = area_bottom + (area_h + height) / 2 - fonts.ascent(fonts.BOLD, size)
    for line in lines:
        w = fonts.string_width(line, fonts.BOLD, size)
        layout.runs.append(Run(line, fonts.BOLD, size, box.x + (box.w - w) / 2, y,
                               'name', SINGLE_NAME_FLOOR))
        y -= size * NAME_LEADING
    layout.name_lines = len(lines)
    layout.truncated = truncated
    return layout


# ---------------------------------------------------------------- running order

@dataclass(frozen=True)
class Row:
    """One presenter in a running order. ``divider``: this name opens a new
    session after another session's names, so a hairline goes above it --
    unless it is the first name on its label."""
    text: str
    divider: bool = False


@dataclass(frozen=True)
class RunningPage:
    pack: int
    header: tuple
    rows: tuple
    part: tuple = None      # (i, n) when the pack needs more than one label


def _row_lines(row, g, size, first=False):
    """([(text, indent, advance)], truncated) for one row at ``size``. A
    line's advance is the space above it; a label's first line has none."""
    texts, truncated = wrap(row.text, fonts.SEMIBOLD, size, g.text.w, indent=WRAP_INDENT)
    lines = []
    for i, text in enumerate(texts):
        advance = size * NAME_LEADING
        if i == 0 and row.divider and not first:
            advance += DIVIDER_GAP * size
        lines.append((text, WRAP_INDENT if i else 0, advance))
    return lines, truncated


def _rows_height(rows, g, size):
    advances = []
    for i, row in enumerate(rows):
        lines, _ = _row_lines(row, g, size, first=i == 0)
        advances.extend(advance for _, _, advance in lines)
    return _stack_height([(fonts.SEMIBOLD, size, a) for a in advances])


def _rows_fit(rows, g, size):
    return _rows_height(rows, g, size) <= g.text.h + 1e-6


def paginate_running(unit, stock):
    """Split a unit's names onto as many labels as they need, measured at
    the floor size (wrapped names take their two lines). A divider that
    would start a continuation label is simply not drawn."""
    g = geometry(stock)
    rows = [Row(name, divider=bool(i) and j == 0)
            for i, names in enumerate(unit.groups) for j, name in enumerate(names)]
    pages, current = [], []
    for row in rows:
        if current and not _rows_fit(current + [row], g, RUNNING_NAME_FLOOR):
            pages.append(current)
            current = []
        current.append(row)
    if current:
        pages.append(current)
    n = len(pages)
    return [RunningPage(unit.pack, unit.header, tuple(p), (i + 1, n) if n > 1 else None)
            for i, p in enumerate(pages)]


def layout_running(page, stock):
    g = geometry(stock)
    layout = LabelLayout(g)
    _header(layout, g, list(page.header), page.pack, page.part)
    box = g.text
    rows = page.rows

    # The largest size, up to the single-name maximum, where everything
    # fits and nothing is cut short or broken mid-word: a name that needs an
    # ellipsis gets it at the floor, where it keeps the most letters. With
    # more than one name, no name may wrap that would sit on one line at the
    # floor (a bigger name broken in two reads worse than a smaller one
    # whole, next to names that are not); a lone name wraps to two lines as
    # on a single-name label.
    def shape(size):
        measured = [_row_lines(row, g, size) for row in rows]
        return [len(lines) for lines, _ in measured], any(t for _, t in measured)

    at_floor, _ = shape(RUNNING_NAME_FLOOR)
    lone = len(rows) == 1
    size = RUNNING_NAME_FLOOR
    for candidate in _sizes(g.single_name_max, RUNNING_NAME_FLOOR):
        counts, truncated = shape(candidate)
        whole = all(_whole_words(row.text, fonts.SEMIBOLD, candidate, box.w - WRAP_INDENT)
                    for row in rows)
        if (_rows_fit(rows, g, candidate) and not truncated and whole
                and (lone or counts == at_floor)):
            size = candidate
            break

    # Centre the block in the text box.
    top = box.y + (box.h + _rows_height(rows, g, size)) / 2
    ascent = fonts.ascent(fonts.SEMIBOLD, size)
    descent = fonts.descent(fonts.SEMIBOLD, size)
    y = None
    for i, row in enumerate(rows):
        lines, truncated = _row_lines(row, g, size, first=i == 0)
        layout.truncated = layout.truncated or truncated
        for j, (text, indent, advance) in enumerate(lines):
            above = y
            y = top - ascent if y is None else y - advance
            layout.runs.append(Run(text, fonts.SEMIBOLD, size, box.x + indent, y,
                                   'name', RUNNING_NAME_FLOOR))
            layout.name_lines += 1
            if j == 0 and row.divider and above is not None:
                # Midway between the line above's descent and this line's
                # ascent: the font's whole boxes, accents included.
                layout.rules.append((box.x, ((above - descent) + (y + ascent)) / 2, box.right))
    return layout


def running_order_capacity(stock):
    """Names per label in the worst case at the floor: every name opens a
    new session, so each brings a divider."""
    g = geometry(stock)
    k = 0
    while _rows_fit([Row('Name', divider=True)] * (k + 1), g, RUNNING_NAME_FLOOR):
        k += 1
    return k


def running_order_available(stock):
    """(available, reason). Reason is shown on the print page."""
    capacity = running_order_capacity(stock)
    if capacity >= RUNNING_MIN_NAMES:
        return True, ''
    return False, ('Running order needs room for {} names at {} pt; a {} label '
                   'fits {}. Use single name labels on this stock.').format(
        RUNNING_MIN_NAMES, RUNNING_NAME_FLOOR, stock.part, capacity)
