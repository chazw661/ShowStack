"""How one wiring diagram ``Layout`` goes onto pages. Pure geometry: no
Django, no ReportLab, so the PDF (``utils/pdf_exports/wiring_pdf``) and its
tests share it.

``plan(lay, width, height)`` takes the space a page has for the diagram, in
points, and returns a ``Plan``: one scale for the whole tab and its tiles.

Scale: the diagram fits the page width and one page, enlarged at most
MAX_SCALE. The smallest text in a layout is 10 units (slot names, column
hints), so a scale under MIN_SCALE would print it under 6pt; then the
diagram is tiled instead: on as few pages as MIN_SCALE needs, at the largest
scale that still needs no more (``SCALE_STEPS`` tried, largest first).

Tiles never cut through a box:

  across  strips are cut in the gaps between columns, just left of a
          column's boxes; only lines cross there.
  down    each column of a strip is cut at its own gap between boxes (an amp
          location's header stays with its first box), so a page's lower
          edge can step from column to column. A column's region is its
          boxes and the gap to its right, which holds only lines and the
          labels of lines leaving its own boxes (inside those boxes' rows).

A box taller than a whole page is the one exception: it is cut between two
rows, where no slot name or label is, and its next part is marked
"(continued)".

Where a line leaves one tile and goes on in another, ``crossings`` gives
both ends, so each page can say "→ p.N" and "from p.N". Tiled pages keep a
band free along their edges for those markers.
"""
from dataclasses import dataclass, field

from planner.connections.layout import BOX_W

MIN_SCALE = 0.6         # 10-unit text at 6pt
MAX_SCALE = 1.5
X_CUT = 2               # a strip starts this far left of its first column's boxes
Y_CUT = 2               # a row cut runs this far above the next box (or header)
BAND_X = 36.0           # points kept free at a tiled page's left and right
BAND_Y = 11.0           # ... and top and bottom, for the page markers
EPS = 0.01
SCALE_STEPS = 36        # scales tried between MAX_SCALE and MIN_SCALE for a tiled tab


@dataclass
class Region:
    """Part of the layout a tile shows: one column's boxes and gap,
    x0..x1 and y0..y1 in layout units."""
    column: int
    x0: float
    x1: float
    y0: float
    y1: float

    def holds(self, x, y):
        return self.x0 - EPS <= x <= self.x1 + EPS and self.y0 - EPS <= y <= self.y1 + EPS


@dataclass
class Tile:
    index: int
    strip: int
    row: int
    x0: float               # the page window's left edge, in layout units
    top: float              # ... and its top
    regions: list
    continued: list = field(default_factory=list)   # [(box, y)] boxes carried on from a page before

    def holds(self, x, y):
        return any(r.holds(x, y) for r in self.regions)


@dataclass
class Plan:
    scale: float
    tiles: list
    width: float            # the window, in layout units
    height: float

    @property
    def tiled(self):
        return len(self.tiles) > 1

    @property
    def strips(self):
        return max((t.strip for t in self.tiles), default=0) + 1


@dataclass
class Crossing:
    route: str
    x: float
    y: float
    leaves: int             # tile index
    enters: int
    direction: str          # 'down' / 'up' / 'right'


def _column_spans(lay):
    """[(x0, x1)] of each shown column's region: its boxes and the gap to
    its right, ending just left of the next column's boxes."""
    xs = [x for _, x, _ in lay.columns]
    if not xs:
        return [(0.0, lay.width)]
    starts = [0.0] + [x - X_CUT for x in xs[1:]]
    ends = starts[1:] + [lay.width]
    return list(zip(starts, ends))


def _blocks(lay, x):
    """The boxes in the column at ``x``, as (top, bottom, box); a box under
    an amp location's header starts at the header."""
    heads = {(round(g.x, 2), round(g.y + g.head, 2)): g.y for g in lay.groups}
    out = []
    for box in lay.boxes:
        if abs(box.x - x) < EPS:
            top = heads.get((round(box.x, 2), round(box.y, 2)), box.y)
            out.append((top, box.y + box.h, box))
    return sorted(out, key=lambda b: b[0])


def _inner_cuts(box):
    """Where a box taller than a page may be cut: between rows on both
    sides, so no slot name and no line's label is split."""
    def edges(heights):
        y, out = box.y + box.head, set()
        for h in heights:
            y += h
            out.add(round(y, 2))
        return out
    ins, outs = edges(box.in_h), edges(box.out_h)
    first = box.y + box.head
    if not box.in_h:
        both = outs
    elif not box.out_h:
        both = ins
    else:
        both = ins & outs
        # past the last row on one side, any edge of the other side is clear
        last_in, last_out = max(ins), max(outs)
        both |= {y for y in outs if y >= last_in} | {y for y in ins if y >= last_out}
    return sorted(y for y in both if first < y < box.y + box.h - EPS)


def _cut(blocks, start, limit):
    """The lowest cut in (start, limit] that runs through no box, or None."""
    y = limit
    for top, bottom, _ in blocks:
        if top - Y_CUT < y < bottom:
            y = top - Y_CUT
    return y if y > start + EPS else None


def _cut_inside(blocks, start, limit):
    """A cut inside the box at ``start`` when it alone is taller than a page."""
    for top, bottom, box in blocks:
        if top - Y_CUT - EPS <= start < bottom:
            cuts = [y for y in _inner_cuts(box) if start + EPS < y <= limit]
            if cuts:
                return cuts[-1], box
            return min(limit, bottom), box      # no row edge in reach: never expected
    return None, None


def plan(lay, width, height, min_scale=MIN_SCALE, max_scale=MAX_SCALE):
    """``width`` x ``height``: the points a page has for the diagram."""
    one = min(width / lay.width, height / lay.height, max_scale)
    if one >= min_scale - 1e-9:
        region = Region(0, 0.0, lay.width, 0.0, lay.height)
        return Plan(one, [Tile(0, 0, 0, 0.0, 0.0, [region])], lay.width, lay.height)

    tiles = _tiles(lay, width, height, min_scale)
    scale = min_scale
    for i in range(SCALE_STEPS):
        bigger = max_scale - (max_scale - min_scale) * i / SCALE_STEPS
        fewer = _tiles(lay, width, height, bigger)
        if len(fewer) <= len(tiles):
            tiles, scale = fewer, bigger
            break
    return Plan(scale, tiles, width / scale, height / scale)


def _tiles(lay, width, height, scale):
    """The tiles of ``lay`` printed at ``scale``."""
    tw, th = width / scale, height / scale
    bx, by = BAND_X / scale, BAND_Y / scale
    spans = _column_spans(lay)
    xs = [x for _, x, _ in lay.columns] or [0.0]
    blocks = [_blocks(lay, x) for x in xs]

    # Strips: as many whole columns as fit, with a band at each cut edge.
    strips, k = [], 0
    while k < len(spans):
        first = k
        x0 = spans[k][0] - (bx if k else 0)
        while k + 1 < len(spans) and spans[k + 1][1] - x0 + (bx if k + 2 < len(spans) else 0) <= tw:
            k += 1
        strips.append((first, k, x0))
        k += 1

    tiles = []
    for s, (first, last, x0) in enumerate(strips):
        cols = range(first, last + 1)
        ya = {c: 0.0 for c in cols}
        carried = {}                # column -> the box its next part continues
        row = 0
        while any(ya[c] < lay.height - EPS for c in cols):
            live = [c for c in cols if ya[c] < lay.height - EPS]
            top = min(ya[c] for c in live) - (by if row else 0)
            limit = top + th - by
            yb = {}
            for c in live:
                if lay.height <= limit + EPS:
                    yb[c] = lay.height
                    continue
                y = _cut(blocks[c], ya[c], limit)
                yb[c] = ya[c] if y is None else y
            if all(abs(yb[c] - ya[c]) < EPS for c in live):
                # Nothing fits whole: the box at the top of the highest column
                # is taller than a page, so it is cut between rows.
                c = min(live, key=lambda c: ya[c])
                y, _ = _cut_inside(blocks[c], ya[c], limit)
                yb[c] = y if y is not None else limit
            tile = Tile(len(tiles), s, row, x0, top, [])
            for c in live:
                if yb[c] <= ya[c] + EPS:
                    continue
                tile.regions.append(Region(c, spans[c][0], spans[c][1], ya[c], yb[c]))
                if c in carried:
                    tile.continued.append((carried.pop(c), ya[c]))
                for _, bottom, box in blocks[c]:
                    if box.y < yb[c] < bottom - EPS:
                        carried[c] = box
                ya[c] = yb[c]
            tiles.append(tile)
            row += 1
    return tiles


def owner(plan_, x, y):
    """The tile showing layout point (x, y), or None."""
    for t in plan_.tiles:
        if t.holds(x, y):
            return t.index
    return None


def crossings(plan_, routes):
    """[Crossing] for every line that runs from one tile into another."""
    if not plan_.tiled:
        return []
    xs = sorted({r.x0 for t in plan_.tiles for r in t.regions} |
                {r.x1 for t in plan_.tiles for r in t.regions})
    out = []
    for route in routes:
        pieces = []                 # (tile, (x, y) where it starts)
        for (x0, y0), (x1, y1) in zip(route.points, route.points[1:]):
            if abs(y0 - y1) < EPS:          # horizontal: rightward only
                cuts = [x for x in xs if min(x0, x1) + EPS < x < max(x0, x1) - EPS]
                stops = [x0] + sorted(cuts) + [x1]
                for a, b in zip(stops, stops[1:]):
                    pieces.append((_owner_open(plan_, (a + b) / 2, y0), (a, y0), 'right'))
            else:
                ys = sorted({r.y0 for t in plan_.tiles for r in t.regions if r.x0 - EPS <= x0 <= r.x1 + EPS} |
                            {r.y1 for t in plan_.tiles for r in t.regions if r.x0 - EPS <= x0 <= r.x1 + EPS})
                lo, hi = min(y0, y1), max(y0, y1)
                cuts = [y for y in ys if lo + EPS < y < hi - EPS]
                stops = [y0] + (sorted(cuts) if y1 > y0 else sorted(cuts, reverse=True)) + [y1]
                for a, b in zip(stops, stops[1:]):
                    pieces.append((_owner_open(plan_, x0, (a + b) / 2), (x0, a),
                                   'down' if y1 > y0 else 'up'))
        prev = None
        for tile, (x, y), direction in pieces:
            if tile is None:
                continue
            if prev is not None and tile != prev:
                out.append(Crossing(route.id, x, y, prev, tile, direction))
            prev = tile
    # A trunk's branches share its stretches: one marker where they cross.
    seen, once = set(), []
    for c in out:
        at = (round(c.x, 2), round(c.y, 2), c.leaves, c.enters, c.direction)
        if at not in seen:
            seen.add(at)
            once.append(c)
    return once


def _owner_open(plan_, x, y):
    """The tile whose region holds (x, y) strictly inside, else on an edge."""
    for t in plan_.tiles:
        for r in t.regions:
            if r.x0 + EPS < x < r.x1 - EPS and r.y0 + EPS < y < r.y1 - EPS:
                return t.index
    return owner(plan_, x, y)


def box_regions(tile, box):
    """The parts of ``box`` this tile shows: [(y0, y1)] within the box."""
    out = []
    for r in tile.regions:
        if r.x0 - EPS <= box.x and box.x + BOX_W <= r.x1 + EPS:
            y0, y1 = max(r.y0, box.y), min(r.y1, box.y + box.h)
            if y1 > y0 + EPS:
                out.append((y0, y1))
    return out
