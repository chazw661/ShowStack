"""The Wiring Diagram as a PDF (Download PDF on the Wiring Diagram page).

Drawn straight from ``connections.layout``: boxes, routed lines with their
dash styles, slot names, labels and [n] badges are vector paths and real
text, never pictures, so the file stays sharp at any size and its text can
be searched and copied. Text is Noto Sans (embedded, subset: the label font,
``utils/labels/fonts``) because Helvetica has no glyph for many names; the
arrows "←" / "→", which Noto lacks, are drawn in the built-in Symbol font
in the same line. A B input link is drawn as on screen: its line at 45%,
its label at 80%, labelled "(B)", with its own legend entry.

Each tab starts a page: a title block (project, tab, when it was printed,
the graph's digest), the legend, then the diagram at one scale
(``connections.tiling``: fitted to the page, at most 1.5x, never under 6pt
text; tiled when it would be). A tiled page shows where it sits in its
tab's tiles, and every line running on to another page says "→ p.N" where
it leaves and "from p.N" where it comes back. The Connections table follows
(header row repeated on each page, no row split), then Warnings.

The document is built twice: the first pass finds the page each tile lands
on and the page count, the second draws the page numbers in.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

from planner.connections import layout as L
from planner.connections import tiling
from planner.utils.labels.fonts import BOLD, REGULAR, SEMIBOLD, normalise, register_fonts
from planner.utils.pdf_exports.mic_plan_pdf import stamp

PAPER = {'11x17': (17 * inch, 11 * inch), '24x36': (36 * inch, 24 * inch)}
MARGIN = 0.4 * inch
FOOTER_H = 14
HEAD_H = 54             # the title block and legend above a diagram
HEAD_GAP = 6
MIN_PT = 6              # no text in the file is smaller
MARK_PT = 6.5           # "→ p.N" / "from p.N"
SYMBOL = 'Symbol'
ARROWS = '←→'

INK = colors.HexColor('#111111')
MUTED = colors.HexColor('#555555')
NAVY = colors.HexColor('#16304f')
LINE = colors.HexColor('#2b4c7e')

# The screen's styles (connections/svg.py STYLE), in the same cascade order.
EDGE_STYLES = (
    ('', {'stroke': '#2b4c7e', 'width': 1.4, 'dash': None, 'alpha': 1}),
    ('inferred', {'dash': (6, 4)}),
    ('unlinked', {'stroke': '#b7791f', 'dash': (4, 3)}),
    ('network', {'stroke': '#2f855a', 'dash': (2, 3), 'width': 1.8}),
    ('unset', {'stroke': '#7a7a7a', 'dash': (1, 3), 'width': 1.8}),
    ('b', {'alpha': 0.45}),             # a B input link: lighter, as on screen
)
LABEL_STYLES = (
    ('', {'fill': '#222222', 'font': REGULAR, 'alpha': 1}),
    ('unlinked', {'fill': '#8a5a12', 'font': SEMIBOLD}),
    ('network', {'fill': '#2f855a'}),
    ('unset', {'fill': '#6b6b6b'}),
    ('b', {'alpha': 0.8}),
)
BOX_STYLES = {
    'device': ('#f4f7fb', '#4a6f9a', None),
    'location': ('#f3f6ef', '#6b8a4a', None),
    'unlinked': ('#fff8e6', '#b7791f', (5, 3)),
}
LEGEND = (
    ('Confirmed (linked on a page)', ()),
    ('Inferred from labels', ('inferred',)),
    ('? Not linked or ambiguous', ('unlinked',)),
    ('AVB / Dante network (no cable)', ('network',)),
)
TRUNK_LEGEND = 'One colour and name per stream'
TAP_LEGEND = ('Confirmed', 'Inferred from labels')     # a filled badge, a hollow one
NOT_LINKED_LEGEND = LEGEND[2]
UNSET_LEGEND = ('Console connection not set', ('unset',))
B_LEGEND = ('B input (lighter; labelled “(B)”)', ('b',))


def _cascade(styles, classes):
    out = {}
    for cls, values in styles:
        if not cls or cls in classes:
            out.update(values)
    return out


# -- text ----------------------------------------------------------------------

def _runs(text, font):
    """``text`` as (font, part) runs: the arrows in Symbol, the rest in ``font``."""
    runs, part = [], ''
    for ch in normalise(text) if text else '':
        if ch in ARROWS:
            if part:
                runs.append((font, part))
                part = ''
            runs.append((SYMBOL, ch))
        else:
            part += ch
    if part:
        runs.append((font, part))
    return runs


def text_width(text, font, size):
    return sum(pdfmetrics.stringWidth(part, f, size) for f, part in _runs(text, font))


def draw_text(c, x, y, text, font=REGULAR, size=9, color=INK, anchor='start', fit=None):
    """One line of text at baseline ``y``. ``fit``: the widest it may be; a
    longer line is drawn smaller, never under MIN_PT (then it runs on)."""
    if not text:
        return
    width = text_width(text, font, size)
    if fit and width > fit:
        size = max(MIN_PT, size * fit / width)
        width = text_width(text, font, size)
    if anchor == 'end':
        x -= width
    elif anchor == 'middle':
        x -= width / 2
    t = c.beginText(x, y)
    t.setFillColor(color)
    for f, part in _runs(text, font):
        t.setFont(f, size)
        t.textOut(part)
    c.drawText(t)


def _para_text(text):
    """Escaped for a Paragraph, the arrows in Symbol."""
    out = escape(normalise(text or ''))
    for arrow in ARROWS:
        out = out.replace(arrow, f'<font face="{SYMBOL}">{arrow}</font>')
    return out


# -- the diagram ------------------------------------------------------------------

class _Window:
    """Maps layout units to page points for one tile."""

    def __init__(self, ox, oy, scale, x0, top):
        self.ox, self.oy, self.s, self.x0, self.top = ox, oy, scale, x0, top

    def x(self, x):
        return self.ox + (x - self.x0) * self.s

    def y(self, y):
        return self.oy - (y - self.top) * self.s

    def pt(self, units):
        return units * self.s


def _stroke(c, style):
    c.setStrokeColor(colors.HexColor(style['stroke']))
    c.setLineWidth(style['width'])
    c.setStrokeAlpha(style['alpha'])
    c.setDash(*([list(style['dash']), 0] if style['dash'] else [[], 0]))


def stream_colour(trunk):
    return colors.HexColor(L.STREAM_COLOURS[trunk.colour])


def _draw_badge(c, x, y, half_w, half_h, text, colour, filled, size):
    """A stream's name in its badge: filled, or hollow (an inferred tap)."""
    c.setDash([], 0)
    c.setStrokeColor(colour)
    c.setFillColor(colour if filled else colors.white)
    c.roundRect(x - half_w, y - half_h, 2 * half_w, 2 * half_h, half_h, stroke=1, fill=1)
    draw_text(c, x, y - size * 0.36, text, BOLD, size, colors.white if filled else colour,
              anchor='middle')


def _draw_trunk(c, w, trunk):
    """A trunk's pieces, each once, solid, in its colour."""
    c.setStrokeColor(stream_colour(trunk))
    c.setLineWidth(1.8 * w.s)
    c.setDash([], 0)
    for x0, y0, x1, y1, faded in trunk.lines:
        c.setStrokeAlpha(0.45 if faded else 1)
        c.line(w.x(x0), w.y(y0), w.x(x1), w.y(y1))
    c.setStrokeAlpha(1)


def _draw_badges(c, w, tile, trunk):
    c.setLineWidth(1.4 * w.s)
    for badge in trunk.badges:
        if tile.holds(badge.x, badge.y):
            x0, y0, x1, y1 = badge.box
            _draw_badge(c, w.x(badge.x), w.y(badge.y), w.pt(x1 - x0) / 2, w.pt(y1 - y0) / 2,
                        badge.text, stream_colour(trunk), badge.filled, w.pt(9))


def _draw_route(c, w, route, trunk=None):
    style = _cascade(EDGE_STYLES, route.classes)
    if trunk is None:       # a trunk's branch: the line is the trunk's
        _stroke(c, style)
        p = c.beginPath()
        for i, (x, y) in enumerate(route.points):
            (p.moveTo if i == 0 else p.lineTo)(w.x(x), w.y(y))
        c.drawPath(p, stroke=1, fill=0)
    ex, ey = route.points[-1]
    c.setStrokeAlpha(1)
    c.setDash([], 0)
    c.setFillColor(LINE if trunk is None else stream_colour(trunk))
    head = c.beginPath()
    head.moveTo(w.x(ex), w.y(ey))
    head.lineTo(w.x(ex - 6), w.y(ey - 3.5))
    head.lineTo(w.x(ex - 6), w.y(ey + 3.5))
    head.close()
    c.drawPath(head, stroke=0, fill=1)


def _draw_label(c, w, tile, route, trunk=None):
    if route.badge:
        x0, y0, x1, y1 = route.badge
        if not tile.holds(x0, route.points[0][1]):
            return
        c.setDash([], 0)
        c.setStrokeColor(colors.HexColor('#1f2d3d'))
        c.setFillColor(colors.white)
        c.setLineWidth(1.2 * w.s)
        c.roundRect(w.x(x0), w.y(y1), w.pt(x1 - x0), w.pt(y1 - y0), w.pt(3), stroke=1, fill=1)
        draw_text(c, w.x(x0 + L.KEY_PAD), w.y(route.label_y), f'[{route.key}]', BOLD, w.pt(11))
        return
    style = _cascade(LABEL_STYLES, route.classes)
    n = len(route.lines)
    c.setFillAlpha(style['alpha'])
    for i, line in enumerate(route.lines):
        y = route.label_y - (n - 1 - i) * L.LABEL_LH
        if tile.holds(route.label_x, y - 4):
            draw_text(c, w.x(route.label_x), w.y(y), line, style['font'], w.pt(11),
                      colors.HexColor(style['fill']) if trunk is None else stream_colour(trunk))
    c.setFillAlpha(1)


def _draw_box(c, w, tile, box, trunks=None):
    parts = tiling.box_regions(tile, box)
    if not parts:
        return
    fill, stroke, dash = BOX_STYLES.get(box.style, BOX_STYLES['device'])
    c.setFillColor(colors.HexColor(fill))
    c.setStrokeColor(colors.HexColor(stroke))
    c.setLineWidth(1.4 * w.s)
    c.setDash(*([list(dash), 0] if dash else [[], 0]))
    # The whole box, clipped to the tile: a box cut between rows shows open ends.
    c.roundRect(w.x(box.x), w.y(box.y + box.h), w.pt(box.w), w.pt(box.h), w.pt(4), stroke=1, fill=1)
    c.setDash([], 0)

    def shown(y):
        return any(y0 - 0.01 <= y - 4 and y <= y1 + 0.01 for y0, y1 in parts)
    fit = w.pt(L.TEXT_W)
    for cls, line, dy in box.text_rows:
        y = box.y + dy
        if shown(y):
            if cls == 't':
                draw_text(c, w.x(box.x + 8), w.y(y), line, SEMIBOLD, w.pt(12), INK, fit=fit)
            else:
                draw_text(c, w.x(box.x + 8), w.y(y), line, REGULAR, w.pt(11), MUTED, fit=fit)
    # Port names: from the left edge where a line arrives, ending at the
    # right edge where one leaves.
    for (anchor, x, y, lines, _), n in zip(box.port_texts(), box.port_streams()):
        trunk = (trunks or {}).get(n)
        for j, line in enumerate(lines):
            ly = y + j * L.SLOT_LH
            if shown(ly):
                draw_text(c, w.x(x), w.y(ly), line, REGULAR if trunk is None else SEMIBOLD, w.pt(10),
                          LINE if trunk is None else stream_colour(trunk), anchor=anchor, fit=fit)


def _draw_columns(c, w, tile, lay):
    for text, x, _ in lay.columns:
        if tile.holds(x + 1, L.MARGIN + L.TITLE_Y - 4):
            draw_text(c, w.x(x), w.y(L.MARGIN + L.TITLE_Y), text.upper(), SEMIBOLD, w.pt(12), MUTED)
            hint = L.COLUMN_HINTS.get(text)
            if hint:
                draw_text(c, w.x(x), w.y(L.MARGIN + L.HINT_Y), hint, REGULAR, w.pt(10),
                          colors.HexColor('#666666'))
    for group in lay.groups:
        y = group.y + L.GROUP_HEAD - 8
        if not tile.holds(group.x + 1, y - 4):
            continue
        for i, line in enumerate(group.lines):
            draw_text(c, w.x(group.x), w.y(y + i * L.LINE_H), line, SEMIBOLD, w.pt(11),
                      colors.HexColor('#333333'))
        last = y + L.LINE_H * (len(group.lines) - 1) + 4
        c.setStrokeColor(colors.HexColor('#bbbbbb'))
        c.setLineWidth(1 * w.s)
        c.line(w.x(group.x), w.y(last), w.x(group.x + L.BOX_W), w.y(last))


def _clip(c, w, tile):
    p = c.beginPath()
    for r in tile.regions:
        p.rect(w.x(r.x0), w.y(r.y1), w.pt(r.x1 - r.x0), w.pt(r.y1 - r.y0))
    c.clipPath(p, stroke=0, fill=0)


def _markers(c, w, tile, marks):
    """Where lines leave this page or come onto it."""
    placed = []
    for m in marks:
        x, y = w.x(m['x']), w.y(m['y'])
        if any(abs(x - px) < 28 and abs(y - py) < 7 and m['text'] == t for px, py, t in placed):
            continue
        placed.append((x, y, m['text']))
        side = m['side']
        if side == 'below':
            draw_text(c, x + 2, y - MARK_PT - 1, m['text'], SEMIBOLD, MARK_PT, NAVY)
        elif side == 'above':
            draw_text(c, x + 2, y + 2.5, m['text'], SEMIBOLD, MARK_PT, NAVY)
        elif side == 'right':
            draw_text(c, x + 2, y + 2, m['text'], SEMIBOLD, MARK_PT, NAVY)
        else:
            draw_text(c, x - 2, y + 2, m['text'], SEMIBOLD, MARK_PT, NAVY, anchor='end')


def tile_marks(plan, crossings, pages):
    """{tile index: [marker]}: "→ p.N" where a line leaves a tile, "from p.N"
    where it comes onto one. ``pages``: tile index -> its page number."""
    out = {t.index: [] for t in plan.tiles}
    for x in crossings:
        to_page, from_page = pages.get(x.enters, '?'), pages.get(x.leaves, '?')
        leave_side, enter_side = {'down': ('below', 'above'), 'up': ('above', 'below'),
                                  'right': ('right', 'left')}[x.direction]
        out[x.leaves].append({'x': x.x, 'y': x.y, 'side': leave_side, 'text': f'→ p.{to_page}'})
        out[x.enters].append({'x': x.x, 'y': x.y, 'side': enter_side, 'text': f'from p.{from_page}'})
    return out


def _legend(c, x, y, show_unset, show_b=False, trunks=()):
    entries = list(LEGEND) + ([B_LEGEND] if show_b else []) + ([UNSET_LEGEND] if show_unset else [])
    if trunks:
        # A tab drawn as trunks: every line is solid, so the legend shows a
        # stream and the two badges.
        first = trunks[0]
        colour = stream_colour(first)
        c.setStrokeColor(colour)
        c.setLineWidth(1.8)
        c.line(x, y + 3, x + 24, y + 3)
        draw_text(c, x + 30, y, TRUNK_LEGEND, REGULAR, 8, MUTED)
        x += 30 + text_width(TRUNK_LEGEND, REGULAR, 8) + 18
        for label, filled in zip(TAP_LEGEND, (True, False)):
            half = max(5.5, text_width(first.label, BOLD, 7) / 2 + 2.5)
            c.setLineWidth(1)
            _draw_badge(c, x + half, y + 3, half, 5.5, first.label, colour, filled, 7)
            draw_text(c, x + 2 * half + 6, y, label, REGULAR, 8, MUTED)
            x += 2 * half + 6 + text_width(label, REGULAR, 8) + 18
        entries = [NOT_LINKED_LEGEND] + ([B_LEGEND] if show_b else [])
    for label, classes in entries:
        style = _cascade(EDGE_STYLES, classes)
        _stroke(c, style)
        c.line(x, y + 3, x + 24, y + 3)
        c.setStrokeAlpha(1)
        c.setDash([], 0)
        draw_text(c, x + 30, y, label, REGULAR, 8, MUTED)
        x += 30 + text_width(label, REGULAR, 8) + 18


def _locator(c, right, top, plan, tile):
    """A small map of the tab's tiles, this one filled."""
    cell_w, cell_h, gap = 12, 8, 2
    x0 = right - plan.strips * (cell_w + gap)
    for t in plan.tiles:
        x = x0 + t.strip * (cell_w + gap)
        y = top - (t.row + 1) * (cell_h + gap)
        c.setLineWidth(0.6)
        c.setStrokeColor(colors.HexColor('#999999'))
        c.setFillColor(LINE if t.index == tile.index else colors.white)
        c.rect(x, y, cell_w, cell_h, stroke=1, fill=1)


class DiagramPage(Flowable):
    """One tile of one tab, with the title block above it: a whole page."""

    def __init__(self, doc_info, view, plan, tile, marks):
        super().__init__()
        self.info, self.view, self.plan, self.tile, self.marks = doc_info, view, plan, tile, marks

    def wrap(self, avail_w, avail_h):
        # Always a whole page, so the next tile (or the table) starts a new one.
        self.width, self.height = avail_w, self.info['frame_h'] - 0.5
        return self.width, self.height

    def draw(self):
        c = self.canv
        self.info['pages'][(self.view['tab'], self.tile.index)] = c.getPageNumber()
        top = self.height
        draw_text(c, 0, top - 14, self.info['project'], BOLD, 14, INK)
        parts = [f"Printed {self.info['printed']}", f"Graph {self.info['digest']}"]
        if self.plan.tiled:
            parts.insert(0, f'Part {self.tile.index + 1} of {len(self.plan.tiles)}')
        draw_text(c, 0, top - 31, self.view['tab_label'], SEMIBOLD, 11.5, NAVY)
        draw_text(c, text_width(self.view['tab_label'], SEMIBOLD, 11.5) + 12, top - 31,
                  '  ·  '.join(parts), REGULAR, 9, MUTED)
        _legend(c, 0, top - 48, self.view['show_unset_legend'], self.view.get('show_b_legend'),
                self.view['layout'].trunks)
        if self.plan.tiled:
            _locator(c, self.width, top, self.plan, self.tile)

        lay, tile = self.view['layout'], self.tile
        w = _Window(0, top - HEAD_H - HEAD_GAP, self.plan.scale, tile.x0, tile.top)
        c.saveState()
        _clip(c, w, tile)
        c.setFillColor(colors.white)
        trunks = {t.n: t for t in lay.trunks}
        for route in lay.routes:
            _draw_route(c, w, route, trunks.get(route.trunk))
        for trunk in lay.trunks:
            _draw_trunk(c, w, trunk)
        for trunk in lay.trunks:
            _draw_badges(c, w, tile, trunk)
        for route in lay.routes:
            _draw_label(c, w, tile, route, trunks.get(route.trunk))
        _draw_columns(c, w, tile, lay)
        for box in lay.boxes:
            _draw_box(c, w, tile, box, trunks)
        c.restoreState()
        for box, y in tile.continued:
            draw_text(c, w.x(box.x + 8), w.y(y) + 3, f'{box.label} (continued)', SEMIBOLD,
                      max(MIN_PT, w.pt(10)), MUTED)
        _markers(c, w, tile, self.marks)


class _Badge(Flowable):
    """A Connections table key, boxed as on the diagram."""

    def __init__(self, key):
        super().__init__()
        self.text = f'[{key}]'

    def wrap(self, avail_w, avail_h):
        self.width = text_width(self.text, BOLD, 8) + 6
        self.height = 11
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, self.width, self.height, 2, stroke=1, fill=0)
        draw_text(c, 3, 3, self.text, BOLD, 8, INK)


class _TabMark(Flowable):
    """Zero-size: tells the footer which tab this page belongs to."""

    def __init__(self, label):
        super().__init__()
        self.label = label

    def wrap(self, *_):
        return 0, 0

    def draw(self):
        self.canv._wd_tab = self.label


def _styles():
    base = dict(fontName=REGULAR, textColor=INK)
    return {
        'h2': ParagraphStyle('wd-h2', fontName=SEMIBOLD, fontSize=12, leading=15, spaceAfter=6,
                             textColor=NAVY),
        'cell': ParagraphStyle('wd-cell', fontSize=8, leading=10, **base),
        'head': ParagraphStyle('wd-head', fontName=SEMIBOLD, fontSize=8, leading=10,
                               textColor=colors.white),
        'body': ParagraphStyle('wd-body', fontSize=9, leading=12, **base),
        'warn': ParagraphStyle('wd-warn', fontSize=8.5, leading=11, leftIndent=10, bulletIndent=0,
                               **base),
    }


def _connections(view, width, S):
    rows = view['connections']
    if not rows:
        return []
    header = [Paragraph(h, S['head']) for h in ('Key', 'From', 'To', 'Cable / transport')]
    data = [header] + [[_Badge(r['key']), Paragraph(_para_text(r['from']), S['cell']),
                        Paragraph(_para_text(r['to']), S['cell']),
                        Paragraph(_para_text(r['cable']), S['cell'])] for r in rows]
    key_w = 44
    rest = width - key_w
    table = Table(data, colWidths=[key_w, rest * 0.37, rest * 0.37, rest * 0.26], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6f9')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    title = f"Connections ({len(rows)}) — {view['tab_label']}"
    return [Paragraph(_para_text(title), S['h2']), table, Spacer(1, 12)]


def _warnings(view, S):
    out = [Paragraph(_para_text(f"Warnings ({len(view['warnings'])}) — {view['tab_label']}"
                                if view['warnings'] else f"Warnings — {view['tab_label']}"), S['h2'])]
    if not view['warnings']:
        return out + [Paragraph('None.', S['body'])]
    for w in view['warnings']:
        text = f"<b>{_para_text(w['title'])}</b>: {_para_text(w['edge'])}"
        if w.get('text'):
            text += f", “{_para_text(w['text'])}”"
        if w.get('candidates'):
            text += f". Could be: {_para_text(', '.join(w['candidates']))}"
        out.append(Paragraph(text, S['warn'], bulletText='•'))
    return out


class _Empty(Flowable):
    """A tab with nothing to draw: its title block and why."""

    def __init__(self, info, view, text):
        super().__init__()
        self.info, self.view, self.text = info, view, text

    def wrap(self, avail_w, avail_h):
        self.width, self.height = avail_w, 60
        return self.width, self.height

    def draw(self):
        c = self.canv
        draw_text(c, 0, self.height - 14, self.info['project'], BOLD, 14, INK)
        draw_text(c, 0, self.height - 31, self.view['tab_label'], SEMIBOLD, 11.5, NAVY)
        draw_text(c, text_width(self.view['tab_label'], SEMIBOLD, 11.5) + 12, self.height - 31,
                  f"Printed {self.info['printed']}  ·  Graph {self.info['digest']}", REGULAR, 9, MUTED)
        draw_text(c, 0, self.height - 52, self.text, REGULAR, 10, MUTED)


EMPTY_PROJECT = ('Nothing to draw yet. Add consoles, I/O devices, processors, amps or PA cable '
                 'runs and they appear here.')


def diagram_area(pagesize):
    """(width, height) in points a page of ``pagesize`` has for the diagram."""
    return (pagesize[0] - 2 * MARGIN,
            pagesize[1] - 2 * MARGIN - FOOTER_H - HEAD_H - HEAD_GAP - 1)


def diagram_pages(lay, paper):
    """How many pages ``lay``'s diagram takes on ``paper`` (the download
    panel's hint): the tiles ``build_wiring_pdf`` would draw."""
    return len(tiling.plan(lay, *diagram_area(PAPER.get(paper, PAPER['11x17']))).tiles)


def plans_for(views, pagesize):
    """{tab: (plan, crossings)} for the diagram area of ``pagesize``."""
    width, height = diagram_area(pagesize)
    out = {}
    for view in views:
        lay = view['layout']
        if view['tab_empty'] or not lay.boxes:
            continue
        p = tiling.plan(lay, width, height)
        out[view['tab']] = (p, tiling.crossings(p, lay.routes))
    return out


def _story(info, views, plans, pages, width, empty):
    S = _styles()
    story = []
    for n, view in enumerate(views):
        if n:
            story.append(PageBreak())
        story.append(_TabMark(view['tab_label']))
        if view['tab'] not in plans:
            text = EMPTY_PROJECT if empty else (view['tab_empty_text'] or 'Nothing on this tab.')
            story.append(_Empty(info, view, text))
            continue
        p, crossings = plans[view['tab']]
        tab_pages = {t: pages.get((view['tab'], t)) for t in range(len(p.tiles))}
        marks = tile_marks(p, crossings, tab_pages)
        for tile in p.tiles:
            story.append(DiagramPage(info, view, p, tile, marks[tile.index]))
        story += _connections(view, width, S)
        story += _warnings(view, S)
    return story


def build_wiring_pdf(*, project, views, digest, paper, printed, empty=False):
    """The PDF's bytes. ``views``: ``views_wiring.tab_view`` dicts, in order."""
    register_fonts()
    pagesize = PAPER.get(paper, PAPER['11x17'])
    plans = plans_for(views, pagesize)
    info = {'project': project.name, 'digest': digest,
            'printed': stamp(printed, printed.tzinfo), 'pages': {},
            'frame_h': pagesize[1] - 2 * MARGIN - FOOTER_H}
    total = [0]

    def footer(c, doc):
        text = '  ·  '.join(x for x in (
            f'Page {c.getPageNumber()} of {total[0] or "?"}', project.name,
            getattr(c, '_wd_tab', ''), f'Graph {digest}') if x)
        draw_text(c, MARGIN, MARGIN - 2, text, REGULAR, 7.5, MUTED)

    def build(pages):
        buf = BytesIO()
        doc = BaseDocTemplate(buf, pagesize=pagesize, leftMargin=MARGIN, rightMargin=MARGIN,
                              topMargin=MARGIN, bottomMargin=MARGIN + FOOTER_H,
                              title=f'Wiring Diagram — {project.name}', author='ShowStack')
        frame = Frame(MARGIN, MARGIN + FOOTER_H, pagesize[0] - 2 * MARGIN,
                      pagesize[1] - 2 * MARGIN - FOOTER_H, leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0, id='wd')
        doc.addPageTemplates([PageTemplate(id='wd', frames=[frame], onPageEnd=footer)])
        doc.build(_story(info, views, plans, pages, frame._width, empty))
        return buf.getvalue(), doc.page

    _, last = build({})
    total[0] = last
    pages = dict(info['pages'])
    pdf, last = build(pages)
    return pdf
