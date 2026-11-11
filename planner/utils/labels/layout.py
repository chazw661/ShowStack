"""Where everything sits on one label. Pure: no canvas, no database.

Every dimension is a fraction of the label's side S, so a new stock size
needs no layout changes; font sizes have absolute floors on top of that,
because a 9 pt line is the smallest that reads at arm's length whatever the
label. For OL3016LP (S = 144 pt) the numbers come out as:

    safe inset      max(S/16, 3.2 mm)   9.07 pt  3.2 mm
    "RF 07"         14 pt bold, top-right on the safe zone's corner
    day             9 pt bold, right-aligned under it
    RF block        53.6 pt wide on every label ("2/2 RF 00", "Wednesday")
    logo box        68.3 pt (24.1 mm) wide left of the block, up to 16 mm high
    header->names   0.03 S               4.32 pt
    text inset      0.07 S each side    10.08 pt

The label is one full-bleed colour with no panel. The logo is the biggest
thing on it: 16 mm high when its width allows, shorter for a wider logo,
never under 8 mm (about 3:1); see header(). The names are centred in
everything under the logo and the RF block, down to the bottom of the safe
zone -- unless a Frame reserves a footer there for accent bars, which takes
the footer and a 0.02 S gap off the bottom. Without a logo the names start
under the RF block.

A single-name label carries the RF number, the day, the logo and the name;
nothing else. A running order fits, at the 11 pt floor, under a full-height
logo: four one-line names, three when every name opens a new session and so
brings a divider; with a 5 mm corner-bar footer, four and three. Without a
logo: seven and six; with the footer, six and five.

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
from planner.utils.labels.stock import Rect, mm

ELLIPSIS = '…'

# Floors, in points, whatever the stock.
SINGLE_NAME_FLOOR = 14
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

# "RF 07", top-right on the safe zone's corner, on a 144 pt label; other
# stocks scale it. The day prints under it at OTHER_FLOOR.
RF_SIZE = 14
# Space above the day line, under the RF line's lowest point.
DAY_GAP = 2
# The RF block is this wide on every label, so every logo on a sheet prints
# the same size: room for "Wednesday", or for "2/2 RF 00". A day label wider
# than the block is dropped rather than squeeze the logo.
BLOCK_SAMPLES = ('Wednesday', '2/2', 'RF 00')

# A client logo is the biggest thing on the label: top of the label, centred
# in the width left of the RF block, LOGO_HEIGHT tall when that width allows.
# A wider one shrinks to fit the width, but never below LOGO_MIN_HEIGHT -- a
# logo that would have to go smaller falls back to the mark, then to no logo
# at all.
LOGO_HEIGHT = float(mm(16))
LOGO_MIN_HEIGHT = float(mm(8))

# Between the logo box and the RF block. With the block's width this lets
# a 3:1 logo print at LOGO_MIN_HEIGHT.
LOGO_GAP = 4

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
    text: Rect              # the names' sides and bottom; its top is the
                            # safe zone's, the header decides the real one
    single_name_max: float
    small: float            # the day and "1/2": the 9 pt tier
    rf: float               # "RF 07"
    names_gap: float        # header bottom to the top of the names


@dataclass(frozen=True)
class Frame:
    """What a project's branding takes from the label, as far as layout is
    concerned: a footer above the safe zone's bottom edge kept clear for
    accent bars, and the logos that may go in the header as (kind, aspect)
    in order of preference -- the full logo, then the mark."""
    footer: float = 0.0
    logos: tuple = ()


PLAIN = Frame()


def geometry(stock, footer=0.0):
    s = float(stock.label_w)
    inset = max(s / 16, float(mm('3.2')))
    label = Rect(0.0, 0.0, s, float(stock.label_h))
    safe = label.inset(inset)
    side = 0.07 * s
    bottom = safe.y + (footer + 0.02 * s if footer else 0)
    text = Rect(safe.x + side, bottom, safe.w - 2 * side, safe.top - bottom)
    return Geometry(
        size=s, corner_r=float(stock.corner_r), label=label, safe=safe, text=text,
        single_name_max=max(SINGLE_NAME_FLOOR, 20 / 144 * s),
        small=max(OTHER_FLOOR, s / 16),
        rf=RF_SIZE / 144 * s,
        names_gap=0.03 * s,
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


# ---------------------------------------------------------------- header

@dataclass(frozen=True)
class Header:
    runs: tuple
    left: float             # the RF block's left edge
    bottom: float           # its lowest point
    logo: tuple = None      # (kind, Rect)

    @property
    def names_top(self):
        """The lowest of the RF block and the logo: the names go under it."""
        return min(self.bottom, self.logo[1].y if self.logo else self.bottom)


def block_width(g):
    """The RF block's reserved width: see BLOCK_SAMPLES."""
    day, part, rf = BLOCK_SAMPLES
    return max(fonts.string_width(day, fonts.BOLD, g.small),
               fonts.string_width(part, fonts.BOLD, g.small) + 3
               + fonts.string_width(rf, fonts.BOLD, g.rf))


def _rf_block(g, pack, part=None, day=''):
    """"RF 07" right-aligned on the safe zone's top-right corner, with a
    pack's "1/2" just left of it, and the day right-aligned under them
    unless it is wider than the block."""
    rf = 'RF ' + pack_label(pack)
    baseline = g.safe.top - CAP_HEIGHT * g.rf
    x = g.safe.right - fonts.string_width(rf, fonts.BOLD, g.rf)
    runs = [Run(rf, fonts.BOLD, g.rf, x, baseline, 'header', OTHER_FLOOR, True)]
    if part:
        text = '{}/{}'.format(*part)
        x -= 3 + fonts.string_width(text, fonts.BOLD, g.small)
        runs.append(Run(text, fonts.BOLD, g.small, x, baseline, 'header', OTHER_FLOOR, True))
    if day and _fits(day, fonts.BOLD, g.small, block_width(g)):
        # Under "1/2"'s descent whether or not there is one, so every label
        # of a pack has the same room for names.
        y = (baseline - fonts.descent(fonts.BOLD, g.small) - DAY_GAP
             - fonts.ascent(fonts.BOLD, g.small))
        runs.append(Run(day, fonts.BOLD, g.small,
                        g.safe.right - fonts.string_width(day, fonts.BOLD, g.small), y,
                        'header', OTHER_FLOOR))
    return runs


def logo_height(aspect, room):
    """How tall a logo of ``aspect`` prints in ``room`` points of width:
    LOGO_HEIGHT if it fits, else as tall as the width allows; None below
    LOGO_MIN_HEIGHT."""
    if aspect <= 0 or room <= 0:
        return None
    height = min(LOGO_HEIGHT, room / aspect)
    return height if height >= LOGO_MIN_HEIGHT - 1e-9 else None


def logo_room(g, left):
    """The logo box's width: from the safe zone's left edge to LOGO_GAP
    short of ``left``, the RF block's left edge."""
    return max(0.0, left - LOGO_GAP - g.safe.x)


def header(g, pack, part=None, day='', logos=()):
    """The RF block, and the first of ``logos`` that fits at
    LOGO_MIN_HEIGHT or taller: top of the label, centred in the width left
    of the RF block's reserved width (or of the block itself, should a
    "12/12" ever run past it)."""
    runs = _rf_block(g, pack, part, day)
    left = g.safe.right - block_width(g)
    if min(run.x for run in runs) < left - 1e-6:
        left = min(run.x for run in runs)
    bottom = min(run.bbox.y for run in runs)
    room = logo_room(g, left)
    for kind, aspect in logos:
        h = logo_height(aspect, room)
        if h:
            w = h * aspect
            rect = Rect(g.safe.x + (room - w) / 2, g.safe.top - h, w, h)
            return Header(tuple(runs), left, bottom, (kind, rect))
    return Header(tuple(runs), left, bottom)


def _names_box(g, head):
    top = head.names_top - g.names_gap
    return Rect(g.text.x, g.text.y, g.text.w, top - g.text.y)


def _place_header(layout, g, head):
    layout.runs.extend(head.runs)
    layout.logo = head.logo
    layout.names = _names_box(g, head)
    return layout.names


def header_logo_room(stock, part=False):
    """(geometry, room): the logo width the header has. The same on every
    label, continuation or not; ``part`` is kept for callers."""
    g = geometry(stock)
    return g, logo_room(g, header(g, 0, (1, 2) if part else None, BLOCK_SAMPLES[0]).left)


def max_logo_aspect(stock, part=False, height=LOGO_MIN_HEIGHT):
    """The widest logo (width / height) the header takes at ``height``:
    by default the minimum, so anything wider cannot print."""
    _, room = header_logo_room(stock, part)
    return room / height


def printed_logo_height(stock, aspect, part=False):
    """How tall a logo of ``aspect`` prints in the header; None if it cannot."""
    _, room = header_logo_room(stock, part)
    return logo_height(aspect, room)


# ---------------------------------------------------------------- single name

def layout_single(item, stock, frame=PLAIN):
    """RF, day, logo and the name: nothing else. The name is centred in
    everything under the header, as big as SINGLE_NAME_MAX on two lines."""
    g = geometry(stock, frame.footer)
    layout = LabelLayout(g)
    box = _place_header(layout, g, header(g, item.pack, day=item.day_label, logos=frame.logos))

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

    The header is the same height with or without "1/2", so the room
    measured here is every page's."""
    g = geometry(stock, frame.footer)
    day = unit.header[0] if unit.header else ''
    height = _names_box(g, header(g, unit.pack, day=day, logos=frame.logos)).h
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
                        unit.compact)
            for i, p in enumerate(pages)]


def layout_running(page, stock, frame=PLAIN):
    g = geometry(stock, frame.footer)
    layout = LabelLayout(g)
    box = _place_header(layout, g, header(g, page.pack, page.part, page.day, frame.logos))
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
    head = header(g, 0, day=BLOCK_SAMPLES[0])
    top = min(head.bottom, g.safe.top - LOGO_HEIGHT) if frame.logos else head.bottom
    height = top - g.names_gap - g.text.y
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
