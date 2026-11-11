"""Where everything sits on one label. Pure: no canvas, no database.

Every dimension is a fraction of the label's side S, so a new stock size
needs no layout changes; font sizes have absolute floors on top of that,
because a 9 pt line is the smallest that reads at arm's length whatever the
label. For OL3016LP (S = 144 pt) the numbers come out as:

    safe inset      max(S/16, 3.2 mm)   9.07 pt  3.2 mm
    logo            top of the safe zone, centred, up to 44.4 mm wide and
                    18 mm high, never under 8 mm (so at most ~5.5:1)
    logo->names     0.03 S               4.32 pt
    names           centred; text inset 0.07 S each side, 105.7 pt wide
    names->strip    0.03 S               4.32 pt
    RF strip        "1/2 RF 07 · Monday" bottom-left: RF 14 pt bold, the
                    rest 9 pt; 12.6 pt tall, or the 5 mm corner-bar footer

The label is one full-bleed colour with no panel. The logo is the biggest
thing on it: 18 mm high when the safe zone's width allows, shorter for a
wider logo; see header(). The RF strip shares the bottom of the label with
the corner bars and stops STRIP_GAP short of them, so the day it shows is
the first of day_options() that fits: the day's own label, then with
weekdays shortened ("Wed"), then the date (M/D). The names are centred in
everything between the logo (or the top of the safe zone) and the strip.

A single-name label carries the logo, the name, and RF and day: nothing
else. Running order, at the 11 pt floor, one session / every name a new
session: under an 18 mm logo 4 / 3, with or without corner bars; with no
logo 8 / 7, or 8 / 6 with corner bars.

Text is stacked with the font's real ascent and descent, so a line's box --
what the tests check against the safe zone and the text box -- holds stacked
Vietnamese diacritics too.

Layouts are in label-local points (origin at the label's bottom-left) as
floats; the renderer translates them onto the sheet.
"""

import re
from dataclasses import dataclass, field

from planner.utils.labels import fonts
from planner.utils.labels.data import pack_label
from planner.utils.labels.stock import BLEED_MM, Rect, mm

ELLIPSIS = '…'

# Floors, in points, whatever the stock.
SINGLE_NAME_FLOOR = 12
RUNNING_NAME_FLOOR = 11
OTHER_FLOOR = 9
SIZE_STEP = 0.5

NAME_LEADING = 1.12

# Noto Sans cap height (and lining-figure height), em.
CAP_HEIGHT = 0.714

# A wrapped running-order name's second line is broken this much narrower,
# so it sits inside the first when both are centred.
WRAP_INDENT = 6

# Extra space where a running order moves to the next session, x the name
# size (3.3 pt at the 11 pt floor). A 0.5 pt hairline sits in the middle of
# it. Checked against real glyph boxes: at the floor it clears the descender
# of "Phil Jacobs" above and the stacked accents of "Nguyễn Đặng" below.
DIVIDER_GAP = 0.3

# "RF 07 · Monday" on one baseline in a strip along the bottom-left of the
# safe zone, beside the corner bars: the number at RF_SIZE (for a 144 pt
# label; other stocks scale it), the day and a pack's "1/2" at OTHER_FLOOR.
RF_SIZE = 14
DAY_SEPARATOR = ' · '
# Kept clear between the strip's text and the nearest corner bar.
STRIP_GAP = 3

# Corner bars, as fractions of the label side S: three "/" parallelograms
# from the bottom-right corner into the bleed. The first sits on the bottom
# edge and runs into the bleed below it too. Here, not in render, because
# the RF strip has to stop short of them.
BAR_LEFTS = (0.50, 0.64, 0.78)
BAR_PITCH = 8.4 / 144
BAR_HEIGHT = 6.2 / 144
BAR_SLANT = 0.75

# A client logo is the biggest thing on the label: across the top of the
# safe zone, centred, LOGO_HEIGHT tall when the full width allows. A wider
# one shrinks to fit the width, but never below LOGO_MIN_HEIGHT -- a logo
# that would have to go smaller falls back to the mark, then to no logo at
# all. 18 mm still leaves RUNNING_MIN_NAMES in the worst case.
LOGO_HEIGHT = float(mm(18))
LOGO_MIN_HEIGHT = float(mm(8))

# Running order is only offered where the worst case -- a full-height logo,
# and every name opening a new session, so every name brings a divider --
# still shows this many.
RUNNING_MIN_NAMES = 3


@dataclass(frozen=True)
class Geometry:
    size: float
    corner_r: float
    label: Rect
    safe: Rect
    text: Rect              # the names' box without a logo: from the top of
                            # the safe zone down to the RF strip or footer
    strip: Rect             # the RF strip, full safe width; the bars cut it short
    single_name_max: float
    small: float            # the day and "1/2": the 9 pt tier
    rf: float               # "RF 07"
    names_gap: float        # logo bottom to the top of the names
    baseline: float         # the RF strip's


@dataclass(frozen=True)
class Frame:
    """What a project's branding takes from the label, as far as layout is
    concerned: a footer above the safe zone's bottom edge kept clear for
    accent bars, how many corner bars there are (the RF strip stops short
    of them), and the logos that may go at the top as (kind, aspect) in
    order of preference -- the full logo, then the mark."""
    footer: float = 0.0
    logos: tuple = ()
    bars: int = 0


PLAIN = Frame()


def geometry(stock, footer=0.0):
    s = float(stock.label_w)
    inset = max(s / 16, float(mm('3.2')))
    label = Rect(0.0, 0.0, s, float(stock.label_h))
    safe = label.inset(inset)
    small, rf = max(OTHER_FLOOR, s / 16), RF_SIZE / 144 * s
    # The day's descent under the baseline, the number's cap height over it.
    baseline = safe.y + fonts.descent(fonts.BOLD, small)
    strip_h = max(baseline + CAP_HEIGHT * rf, baseline + fonts.ascent(fonts.BOLD, small)) - safe.y
    strip = Rect(safe.x, safe.y, safe.w, strip_h)
    side = 0.07 * s
    bottom = safe.y + max(footer, strip_h) + 0.03 * s
    text = Rect(safe.x + side, bottom, safe.w - 2 * side, safe.top - bottom)
    return Geometry(
        size=s, corner_r=float(stock.corner_r), label=label, safe=safe, text=text, strip=strip,
        single_name_max=max(SINGLE_NAME_FLOOR, 16 / 144 * s),
        small=small, rf=rf, names_gap=0.03 * s, baseline=baseline,
    )


# ---------------------------------------------------------------- text runs

# Capitals and figures that sit on the baseline (no J or Q).
_CAPS = re.compile(r'[0-9A-IK-PR-Z ]+')


@dataclass(frozen=True)
class Run:
    text: str
    font: str
    size: float
    x: float                # left edge
    y: float                # baseline
    role: str               # 'header' | 'name'
    floor: float = 0
    emphasis: bool = False  # "RF 07" and "1/2": may take accent 1

    @property
    def width(self):
        return fonts.string_width(self.text, self.font, self.size)

    @property
    def bbox(self):
        if (self.text.isascii() and self.text.isdigit()
                or self.role == 'header' and _CAPS.fullmatch(self.text)):
            # Lining figures, and "RF 07": cap height, nothing below the
            # baseline. The font's ascent makes room for stacked accents
            # these never have. (A name in capitals keeps the font's box,
            # so names centre the same whatever their case.)
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
    logo: tuple = None                           # (kind, Rect) when a logo is placed
    names: Rect = None                           # where the names may go


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


# ---------------------------------------------------------------- corner bars

def corner_bars(g, n, top):
    """Label-local polygons for ``n`` bars, bottom first, none above
    ``top``."""
    b, s = float(mm(BLEED_MM)), g.size
    bars = []
    for i in range(min(n, len(BAR_LEFTS))):
        y0 = -b if i == 0 else i * BAR_PITCH * s
        y1 = min(i * BAR_PITCH * s + BAR_HEIGHT * s, top)
        x0 = BAR_LEFTS[i] * s
        bars.append([(x0, y0), (g.label.right + b, y0), (g.label.right + b, y1),
                     (x0 + BAR_SLANT * (y1 - y0), y1)])
    return bars


def strip_right(g, frame):
    """Where the RF strip's text must stop: STRIP_GAP short of the nearest
    corner bar at the strip's height, or the safe zone's right edge."""
    right = g.safe.right
    for bar in corner_bars(g, frame.bars, g.safe.y + frame.footer):
        (x0, y0), _, _, (_, y1) = bar
        if y1 <= g.strip.y or y0 >= g.strip.top:
            continue
        # A "/" bar's left edge is furthest left at its lowest point.
        x = x0 + BAR_SLANT * (max(g.strip.y, y0) - y0)
        right = min(right, x - STRIP_GAP)
    return right


# ---------------------------------------------------------------- header

@dataclass(frozen=True)
class Header:
    runs: tuple
    logo: tuple = None      # (kind, Rect)


_WEEKDAYS = re.compile(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
                       re.IGNORECASE)


def short_weekdays(text):
    """Every weekday word cut to its first three letters, case kept:
    "Wednesday Show" -> "Wed Show"."""
    return _WEEKDAYS.sub(lambda m: m.group(0)[:3], text)


def day_options(day, date=''):
    """What the strip may say for the day, in order: the day's own label,
    the same with weekdays shortened, the date as M/D."""
    options = []
    for text in (day, short_weekdays(day), date):
        if text and text not in options:
            options.append(text)
    return options


def _rf_strip(g, frame, pack, part=None, day='', date=''):
    """"1/2 RF 07 · Monday" left-aligned on the strip's baseline, stopping
    STRIP_GAP short of the corner bars. The day is the first of
    day_options() that fits. Only the date on a continuation label beside
    the bars can be too wide even so ("1/2 RF 07 · 11/12" is 84 pt of the
    81 on OL3016LP); it then loses the " · " for a space. The day is never
    dropped while that fits."""
    rf = 'RF ' + pack_label(pack)
    right = strip_right(g, frame)
    runs, x = [], g.safe.x
    if part:
        text = '{}/{} '.format(*part)
        runs.append(Run(text.rstrip(), fonts.BOLD, g.small, x, g.baseline, 'header',
                        OTHER_FLOOR, True))
        x += fonts.string_width(text, fonts.BOLD, g.small)
    runs.append(Run(rf, fonts.BOLD, g.rf, x, g.baseline, 'header', OTHER_FLOOR, True))
    x += fonts.string_width(rf, fonts.BOLD, g.rf) + fonts.string_width(' ', fonts.BOLD, g.small)
    options = [DAY_SEPARATOR.lstrip() + text for text in day_options(day, date)]
    if date:
        options.append(date)
    for text in options:
        if x + fonts.string_width(text, fonts.BOLD, g.small) <= right + 1e-6:
            runs.append(Run(text, fonts.BOLD, g.small, x, g.baseline, 'header', OTHER_FLOOR))
            break
    return runs


def logo_height(aspect, room):
    """How tall a logo of ``aspect`` prints in ``room`` points of width:
    LOGO_HEIGHT if it fits, else as tall as the width allows; None below
    LOGO_MIN_HEIGHT."""
    if aspect <= 0 or room <= 0:
        return None
    height = min(LOGO_HEIGHT, room / aspect)
    return height if height >= LOGO_MIN_HEIGHT - 1e-9 else None


def header(g, pack, part=None, day='', frame=PLAIN, date=''):
    """The RF strip, and the first of ``frame.logos`` that fits at
    LOGO_MIN_HEIGHT or taller: on the safe zone's top edge, centred across
    its full width."""
    runs = tuple(_rf_strip(g, frame, pack, part, day, date))
    for kind, aspect in frame.logos:
        h = logo_height(aspect, g.safe.w)
        if h:
            w = h * aspect
            return Header(runs, (kind, Rect(g.safe.x + (g.safe.w - w) / 2, g.safe.top - h, w, h)))
    return Header(runs)


def _names_box(g, head):
    if not head.logo:
        return g.text
    top = head.logo[1].y - g.names_gap
    return Rect(g.text.x, g.text.y, g.text.w, top - g.text.y)


def _place_header(layout, g, head):
    layout.runs.extend(head.runs)
    layout.logo = head.logo
    layout.names = _names_box(g, head)
    return layout.names


def header_logo_room(stock, part=False):
    """(geometry, room): the logo's width, the safe zone's, on every label;
    ``part`` is kept for callers."""
    g = geometry(stock)
    return g, g.safe.w


def max_logo_aspect(stock, part=False, height=LOGO_MIN_HEIGHT):
    """The widest logo (width / height) that prints at ``height``: by
    default the minimum, so anything wider cannot print."""
    _, room = header_logo_room(stock, part)
    return room / height


def printed_logo_height(stock, aspect, part=False):
    """How tall a logo of ``aspect`` prints; None if it cannot."""
    _, room = header_logo_room(stock, part)
    return logo_height(aspect, room)


# ---------------------------------------------------------------- single name

def layout_single(item, stock, frame=PLAIN):
    """Logo, the name, and RF and day: nothing else. The name is centred
    between the logo and the RF strip, up to SINGLE_NAME_MAX on two lines."""
    g = geometry(stock, frame.footer)
    layout = LabelLayout(g)
    box = _place_header(layout, g, header(g, item.pack, day=item.day_label, frame=frame,
                                          date=item.day_date))

    chosen = None
    for size in _sizes(g.single_name_max, SINGLE_NAME_FLOOR):
        lines, truncated = wrap(item.name, fonts.BOLD, size, box.w)
        height = _stack_height([(fonts.BOLD, size, size * NAME_LEADING)] * len(lines))
        if not truncated and height <= box.h and _whole_words(item.name, fonts.BOLD, size, box.w):
            chosen = (size, lines, truncated, height)
            break
    if chosen is None:
        size = SINGLE_NAME_FLOOR
        lines, truncated = wrap(item.name, fonts.BOLD, size, box.w)
        chosen = (size, lines, truncated,
                  _stack_height([(fonts.BOLD, size, size * NAME_LEADING)] * len(lines)))
    size, lines, truncated, height = chosen
    y = box.y + (box.h + height) / 2 - fonts.ascent(fonts.BOLD, size)
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
    compact: tuple = None   # unused by the layout; kept with the unit's
    date: str = ''          # the day as M/D

    @property
    def day(self):
        return self.header[0] if self.header else ''


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


def _rows_fit(rows, g, size, height):
    return _rows_height(rows, g, size) <= height + 1e-6


def paginate_running(unit, stock, frame=PLAIN):
    """Split a unit's names onto as many labels as they need, measured at
    the floor size (wrapped names take their two lines). A divider that
    would start a continuation label is simply not drawn.

    The logo and the RF strip are the same on every page, so the room
    measured here is every page's."""
    g = geometry(stock, frame.footer)
    height = _names_box(g, header(g, unit.pack, frame=frame)).h
    rows = [Row(name, divider=bool(i) and j == 0)
            for i, names in enumerate(unit.groups) for j, name in enumerate(names)]
    pages, current = [], []
    for row in rows:
        if current and not _rows_fit(current + [row], g, RUNNING_NAME_FLOOR, height):
            pages.append(current)
            current = []
        current.append(row)
    if current:
        pages.append(current)
    n = len(pages)
    return [RunningPage(unit.pack, unit.header, tuple(p), (i + 1, n) if n > 1 else None,
                        unit.compact, unit.day_date)
            for i, p in enumerate(pages)]


def layout_running(page, stock, frame=PLAIN):
    g = geometry(stock, frame.footer)
    layout = LabelLayout(g)
    box = _place_header(layout, g, header(g, page.pack, page.part, page.day, frame, page.date))
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
        if (_rows_fit(rows, g, candidate, box.h) and not truncated and whole
                and (lone or counts == at_floor)):
            size = candidate
            break

    # Centre the block in the names box.
    top = box.y + (box.h + _rows_height(rows, g, size)) / 2
    ascent = fonts.ascent(fonts.SEMIBOLD, size)
    descent = fonts.descent(fonts.SEMIBOLD, size)
    y = None
    for i, row in enumerate(rows):
        lines, truncated = _row_lines(row, g, size, first=i == 0)
        layout.truncated = layout.truncated or truncated
        for j, (text, _, advance) in enumerate(lines):
            above = y
            y = top - ascent if y is None else y - advance
            # Centred like a single name; a wrapped line's indent only
            # narrows the width it was broken to.
            w = fonts.string_width(text, fonts.SEMIBOLD, size)
            layout.runs.append(Run(text, fonts.SEMIBOLD, size, box.x + (box.w - w) / 2, y,
                                   'name', RUNNING_NAME_FLOOR))
            layout.name_lines += 1
            if j == 0 and row.divider and above is not None:
                # Midway between the line above's descent and this line's
                # ascent: the font's whole boxes, accents included.
                layout.rules.append((box.x, ((above - descent) + (y + ascent)) / 2, box.right))
    return layout


def running_order_capacity(stock, frame=PLAIN):
    """Names per label in the worst case at the floor: a full-height logo
    when the frame has any, and every name opens a new session, so each
    brings a divider."""
    g = geometry(stock, frame.footer)
    height = g.text.h - (LOGO_HEIGHT + g.names_gap if frame.logos else 0)
    k = 0
    while _rows_fit([Row('Name', divider=True)] * (k + 1), g, RUNNING_NAME_FLOOR, height):
        k += 1
    return k


def running_order_available(stock, frame=PLAIN):
    """(available, reason). Reason is shown on the print page."""
    capacity = running_order_capacity(stock, frame)
    if capacity >= RUNNING_MIN_NAMES:
        return True, ''
    return False, ('Running order needs room for {} names at {} pt; a {} label '
                   'fits {}. Use single name labels on this stock.').format(
        RUNNING_MIN_NAMES, RUNNING_NAME_FLOOR, stock.part, capacity)
