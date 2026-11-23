"""The Wiring Diagram as DXF, one drawing per tab (Download DXF, for
Vectorworks). Drawn from ``connections.layout`` like the screen and the PDF,
but whole: no tiling, no page cuts, no "→ p.N" markers.

Top to bottom in model space: a title block (project, tab, when it was
made, the graph's digest, the scale), the legend, the diagram, then the
Connections table and Warnings as text.

  boxes      closed LWPOLYLINEs (square corners; an unlinked box is DASHED)
  lines      LWPOLYLINEs along each route, a SOLID arrowhead at its end
  all text   TEXT entities, never outlines and never MTEXT (no inline
             formatting codes to escape): titles, subtitles, slot names,
             line labels, "[n]" keys, column titles and hints, group headers

Layers. A line is on one layer: the kind of link when it has one, else how
sure it is --

  WD-COMMS      every line on the Comms tab
  WD-SPEAKER    speaker cable runs
  WD-NETWORK    AVB / Dante network feeds
  WD-CONFIRMED / WD-INFERRED / WD-UNLINKED   everything else, and every B
                input link (lighter, labelled "(B)")

and its linetype is set on the line itself (CONTINUOUS / DASHED / DOT, the
screen's styles), so a speaker run still shows whether it is confirmed.
WD-BOXES holds boxes and group rules; WD-TEXT every text of the diagram and
the key badges; WD-TITLE the title block and legend; WD-TABLE the
Connections table and Warnings.

Units are inches. One layout unit is UNIT inches, chosen so the 10-unit
slot text is 1/8" high (a DXF text height is the capital height, 0.716 em
in Arial); text of s units is s / 80 inches high.

Every string is user data. ``clean`` makes it safe for a TEXT value: no
control codes (a newline would end the DXF tag), and "%%" / "^", which CAD
programs read as control codes, escaped so they read back as typed.

``ezdxf`` (and with it numpy) is imported inside ``build_tab_dxf``, so a
worker only loads it once someone downloads a DXF.
"""
import io
import re
import unicodedata

from planner.connections import layout as L
from planner.connections import tabs as T
from planner.utils.labels.fonts import BOLD, REGULAR, string_width

CAP = 0.716                     # Arial's capital height, in em
UNIT = 0.125 / (10 * CAP)       # inches per layout unit
DXF_VERSION = 'R2010'           # AC1024: UTF-8, read by every current CAD program
ARROWS_ASCII = 'ascii'
MAX_TEXT = 500                  # one TEXT value; far under the format's limit
MIN_WIDTH = 0.6                 # a too-long line is squeezed to no less than this

BOXES, TEXT, TITLE, TABLE = 'WD-BOXES', 'WD-TEXT', 'WD-TITLE', 'WD-TABLE'
CONFIRMED, INFERRED, UNLINKED = 'WD-CONFIRMED', 'WD-INFERRED', 'WD-UNLINKED'
NETWORK, SPEAKER, COMMS = 'WD-NETWORK', 'WD-SPEAKER', 'WD-COMMS'
INK = 7                         # ACI 7: black on a light page, white on a dark one
LAYERS = (                      # name, true colour (None: INK)
    (BOXES, 0x4a6f9a), (TEXT, None), (CONFIRMED, 0x2b4c7e), (INFERRED, 0x2b4c7e),
    (UNLINKED, 0xb7791f), (NETWORK, 0x2f855a), (SPEAKER, 0x2b4c7e), (COMMS, 0x2b4c7e),
    (TABLE, None), (TITLE, None),
)
LAYER_COLOUR = dict(LAYERS)
CONTINUOUS, DASHED, DOT = 'CONTINUOUS', 'DASHED', 'DOT'
# Patterns in inches, the screen's dashes at this drawing's scale.
LINETYPES = (
    (DASHED, 'Dashed __ __ __ __', [10 * UNIT, 6 * UNIT, -4 * UNIT]),
    (DOT, 'Dot . . . . . . . .', [3 * UNIT, 0.0, -3 * UNIT]),
)
STYLE, STYLE_BOLD = 'Arial', 'Arial-Bold'
B_FADE = 0.45                   # a B link's colour, this much of it over white

LEGEND = (
    ('Confirmed (linked on a page)', ()),
    ('Inferred from labels', ('inferred',)),
    ('? Not linked or ambiguous', ('unlinked',)),
    ('AVB / Dante network (no cable)', ('network',)),
)
UNSET_LEGEND = ('Console connection not set', ('unset',))
B_LEGEND = ('B input (lighter; labelled "(B)")', ('b',))
EMPTY_PROJECT = ('Nothing to draw yet. Add consoles, I/O devices, processors, amps or PA cable '
                 'runs and they appear here.')

TITLE_TOP = -150                # the title block, in layout units above the diagram
TABLE_W = (50, 330, 330, 260)   # Key, From, To, Cable / transport
TABLE_GAP = 40                  # between the diagram and the table
ROW_PAD = 6

_SPACE_LIKE = '\t\n\r\x0b\x0c\x85  '
_BIDI = set('‪‫‬‭‮⁦⁧⁨⁩‎‏')
_PERCENTS = re.compile(r'%{2,}')


def clean(text, arrows=''):
    """``text`` as a safe TEXT value that reads back as typed.

    NFC; tabs and line breaks become a space; other control characters,
    lone surrogates, non-characters and direction overrides are dropped.
    "%%" starts a control code in TEXT ("%%u" underlines, "%%d" is a degree
    sign), so each "%" of such a run is written "%%%", the code for a
    literal "%"; "^" starts a caret code ("^J"), so it is written "^ ", the
    code for a literal "^". ``arrows='ascii'``: "←" / "→" as "<-" / "->".
    """
    s = unicodedata.normalize('NFC', '' if text is None else str(text))
    out = []
    for ch in s:
        if ch in _SPACE_LIKE:
            out.append(' ')
        elif ch in _BIDI or unicodedata.category(ch) in ('Cc', 'Cs') or (ord(ch) & 0xFFFE) == 0xFFFE:
            continue
        else:
            out.append(ch)
    s = re.sub(r' {2,}', ' ', ''.join(out)).strip()[:MAX_TEXT]
    if arrows == ARROWS_ASCII:
        s = s.replace('←', '<-').replace('→', '->')
    s = _PERCENTS.sub(lambda m: '%%%' * len(m.group()), s)
    return s.replace('^', '^ ')


def edge_layer(tab, classes, edge):
    """The layer a route's line and arrowhead are on."""
    status = (UNLINKED if 'unlinked' in classes else
              INFERRED if 'inferred' in classes else CONFIRMED)
    if 'b' in classes:
        return status
    if tab == T.COMMS:
        return COMMS
    if 'speaker' in (edge or {}).get('transports', ()):
        return SPEAKER
    if 'network' in classes:
        return NETWORK
    return status


def edge_linetype(classes):
    """The screen's dash styles (``svg.STYLE``), in the same cascade order."""
    linetype = CONTINUOUS
    if 'inferred' in classes or 'unlinked' in classes:
        linetype = DASHED
    if 'network' in classes or 'unset' in classes:
        linetype = DOT
    return linetype


def _fade(colour):
    """``colour`` at B_FADE over white: a B link's lighter line."""
    parts = [(colour >> shift) & 0xFF for shift in (16, 8, 0)]
    r, g, b = (round(255 - (255 - p) * B_FADE) for p in parts)
    return (r << 16) | (g << 8) | b


class _Drawing:
    """Model space in layout units (x right, y down), written in inches."""

    def __init__(self, ezdxf, arrows):
        from ezdxf.enums import TextEntityAlignment
        self.left = TextEntityAlignment.LEFT
        self.arrows = arrows
        self.doc = ezdxf.new(DXF_VERSION, setup=False)
        self.doc.units = 1          # $INSUNITS: inches
        self.doc.header['$MEASUREMENT'] = 0
        self.doc.header['$LTSCALE'] = 1.0
        for name, description, pattern in LINETYPES:
            self.doc.linetypes.add(name, pattern=pattern, description=description)
        regular = self.doc.styles.add(STYLE, font='arial.ttf')
        regular.set_extended_font_data(family='Arial')
        bold = self.doc.styles.add(STYLE_BOLD, font='arialbd.ttf')
        bold.set_extended_font_data(family='Arial', bold=True)
        for name, colour in LAYERS:
            layer = self.doc.layers.add(name, color=INK)
            if colour is not None:
                layer.true_color = colour
        self.msp = self.doc.modelspace()
        self.x0 = self.y0 = self.x1 = self.y1 = 0.0

    def _seen(self, x, y):
        self.x0, self.x1 = min(self.x0, x), max(self.x1, x)
        self.y0, self.y1 = min(self.y0, y), max(self.y1, y)

    @staticmethod
    def pt(x, y):
        return (round(x * UNIT, 5), round(-y * UNIT, 5))

    def text(self, x, y, text, size, layer=TEXT, bold=False, fit=None, colour=None):
        """One line at baseline ``y``; ``size`` is the screen's font size.
        ``fit``: the widest it may be, in layout units; a longer line is
        squeezed (TEXT width factor), never under MIN_WIDTH."""
        value = clean(text, self.arrows)
        if not value:
            return None
        attribs = {'layer': layer, 'style': STYLE_BOLD if bold else STYLE}
        width = string_width(value, BOLD if bold else REGULAR, size)
        if fit and width > fit:
            attribs['width'] = round(max(MIN_WIDTH, fit / width), 3)
            width *= attribs['width']
        if colour is not None:
            attribs['true_color'] = colour
        entity = self.msp.add_text(value, height=round(size * CAP * UNIT, 5), dxfattribs=attribs)
        entity.set_placement(self.pt(x, y), align=self.left)
        self._seen(x, y - size)
        self._seen(x + width, y + size * 0.3)
        return entity

    def polyline(self, points, layer, linetype=CONTINUOUS, close=False, colour=None):
        attribs = {'layer': layer, 'linetype': linetype}
        if colour is not None:
            attribs['true_color'] = colour
        for x, y in points:
            self._seen(x, y)
        return self.msp.add_lwpolyline([self.pt(x, y) for x, y in points], close=close,
                                       dxfattribs=attribs)

    def rect(self, x0, y0, x1, y1, layer, linetype=CONTINUOUS):
        return self.polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, linetype, close=True)

    def line(self, x0, y0, x1, y1, layer, linetype=CONTINUOUS, colour=None):
        attribs = {'layer': layer, 'linetype': linetype}
        if colour is not None:
            attribs['true_color'] = colour
        self._seen(x0, y0)
        self._seen(x1, y1)
        return self.msp.add_line(self.pt(x0, y0), self.pt(x1, y1), dxfattribs=attribs)

    def arrowhead(self, x, y, layer, colour=None):
        attribs = {'layer': layer}
        if colour is not None:
            attribs['true_color'] = colour
        return self.msp.add_solid([self.pt(x, y), self.pt(x - 6, y - 3.5), self.pt(x - 6, y + 3.5)],
                                  dxfattribs=attribs)

    def data(self):
        pad = 20
        x0, y0 = self.pt(self.x0 - pad, self.y1 + pad)
        x1, y1 = self.pt(self.x1 + pad, self.y0 - pad)
        # The view the file opens on: the whole drawing.
        self.doc.set_modelspace_vport(max(y1 - y0, 1.0), ((x0 + x1) / 2, (y0 + y1) / 2))
        stream = io.StringIO()
        self.doc.write(stream)
        return stream.getvalue().encode('utf-8')        # R2007 and later are UTF-8


# -- the parts of a drawing ---------------------------------------------------------

def scale_text():
    return (f'Scale: 1 diagram unit = {UNIT:.5f} in (a box is {L.BOX_W * UNIT:.2f} in wide); '
            f'10 pt text is 1/8 in high. Units: inches.')


def _title_block(d, project_name, view, digest, printed, width):
    y = TITLE_TOP
    d.rect(-10, y, max(width, 700) + 10, -24, TITLE)
    d.text(0, y + 26, project_name, 18, TITLE, bold=True, fit=max(width, 700))
    d.text(0, y + 48, f"Wiring Diagram: {view['tab_label']}", 14, TITLE, bold=True)
    d.text(0, y + 66, f'Made {printed} · Graph {digest}', 11, TITLE)
    d.text(0, y + 82, scale_text(), 10, TITLE)
    entries = list(LEGEND)
    if view.get('show_b_legend'):
        entries.append(B_LEGEND)
    if view.get('show_unset_legend'):
        entries.append(UNSET_LEGEND)
    x, ly = 0, y + 106
    for label, classes in entries:
        layer = edge_layer(None, classes or ('confirmed',), None)
        colour = LAYER_COLOUR[layer]
        if 'b' in classes:
            colour = _fade(colour)
        if x and x + 46 + string_width(label, REGULAR, 11) > max(width, 700):
            x, ly = 0, ly + 14          # never reached with today's five entries
        d.line(x, ly - 4, x + 34, ly - 4, TITLE, edge_linetype(classes), colour=colour)
        d.text(x + 40, ly, label, 11, TITLE)
        x += 40 + string_width(label, REGULAR, 11) + 22


def _columns(d, lay):
    for text, x, _ in lay.columns:
        d.text(x, L.MARGIN + L.TITLE_Y, text.upper(), 12, bold=True)
        hint = L.COLUMN_HINTS.get(text)
        if hint:
            d.text(x, L.MARGIN + L.HINT_Y, hint, 10)
    for group in lay.groups:
        y = group.y + L.GROUP_HEAD - 8
        for i, line in enumerate(group.lines):
            d.text(group.x, y + i * L.LINE_H, line, 11, bold=True)
        last = y + L.LINE_H * (len(group.lines) - 1) + 4
        d.line(group.x, last, group.x + L.BOX_W, last, BOXES)


def _box(d, box):
    d.rect(box.x, box.y, box.x + box.w, box.y + box.h, BOXES,
           DASHED if box.style == 'unlinked' else CONTINUOUS)
    for cls, line, dy in box.text_rows:
        d.text(box.x + 8, box.y + dy, line, 12 if cls == 't' else 11, bold=cls == 't', fit=L.TEXT_W)
    for i, (label, lines) in enumerate(zip(box.slots, box.slot_lines)):
        if not label:
            continue
        y = box.row_y(i) + 3.5
        for j, line in enumerate(lines):
            d.text(box.x + 8, y + j * L.SLOT_LH, line, 10, fit=L.TEXT_W)


def _route(d, tab, route, edge):
    layer = edge_layer(tab, route.classes, edge)
    colour = _fade(LAYER_COLOUR[layer]) if 'b' in route.classes else None
    d.polyline(route.points, layer, edge_linetype(route.classes), colour=colour)
    d.arrowhead(*route.points[-1], layer, colour=colour)
    if route.key:
        x0, y0, x1, y1 = route.badge
        d.rect(x0, y0, x1, y1, TEXT)
        d.text(x0 + L.KEY_PAD, route.label_y, f'[{route.key}]', 11, bold=True)
        return
    n = len(route.lines)
    for i, line in enumerate(route.lines):
        d.text(route.label_x, route.label_y - (n - 1 - i) * L.LABEL_LH, line, 11)


def _cell_lines(text, width):
    return L.wrap(' '.join(str(text or '').split()), width - 12)


def _table(d, view, top):
    """The Connections table; returns the y under it."""
    rows = view['connections']
    if not rows:
        return top
    d.text(0, top + 14, f"Connections ({len(rows)}) — {view['tab_label']}", 14, TABLE, bold=True)
    xs = [sum(TABLE_W[:i]) for i in range(len(TABLE_W) + 1)]
    y = top + 26
    start = y
    for i, head in enumerate(('Key', 'From', 'To', 'Cable / transport')):
        d.text(xs[i] + 6, y + 14, head, 11, TABLE, bold=True)
    y += 20
    d.line(0, y, xs[-1], y, TABLE)
    for row in rows:
        cells = [[f"[{row['key']}]"]] + [_cell_lines(row[k], TABLE_W[i + 1])
                                         for i, k in enumerate(('from', 'to', 'cable'))]
        for i, lines in enumerate(cells):
            for j, line in enumerate(lines):
                d.text(xs[i] + 6, y + 14 + j * L.LABEL_LH, line, 11, TABLE, bold=i == 0)
        y += max(len(lines) for lines in cells) * L.LABEL_LH + ROW_PAD
        d.line(0, y, xs[-1], y, TABLE)
    d.rect(0, start, xs[-1], y, TABLE)
    for x in xs[1:-1]:
        d.line(x, start, x, y, TABLE)
    return y + 24


def warning_text(w):
    text = f"{w['title']}: {w['edge']}"
    if w.get('text'):
        text += f", “{w['text']}”"
    if w.get('candidates'):
        text += f". Could be: {', '.join(w['candidates'])}"
    return text


def _warnings(d, view, top):
    warnings = view['warnings']
    title = (f"Warnings ({len(warnings)}) — {view['tab_label']}" if warnings
             else f"Warnings — {view['tab_label']}")
    d.text(0, top + 14, title, 14, TABLE, bold=True)
    y = top + 34
    if not warnings:
        d.text(0, y, 'None.', 11, TABLE)
        return
    for w in warnings:
        for j, line in enumerate(L.wrap(' '.join(warning_text(w).split()), sum(TABLE_W) - 14)):
            d.text(0 if j == 0 else 12, y, ('• ' if j == 0 else '') + line, 11, TABLE)
            y += L.LABEL_LH
        y += 4


def build_tab_dxf(*, project_name, view, digest, printed, arrows='', empty=False):
    """One tab's drawing as DXF bytes. ``view``: a ``views_wiring.tab_view``
    dict; ``printed``: the stamp, already text; ``arrows='ascii'`` writes
    "<-" / "->" for the arrows; ``empty``: the project has nothing at all."""
    import ezdxf

    d = _Drawing(ezdxf, arrows)
    lay = view['layout']
    drawn = bool(lay.boxes) and not view['tab_empty']
    width = lay.width if drawn else 0
    _title_block(d, project_name, view, digest, printed, width)
    if not drawn:
        text = EMPTY_PROJECT if empty else (view['tab_empty_text'] or 'Nothing on this tab.')
        d.text(0, 14, text, 11, TITLE)
        return d.data()
    edges = {e['id']: e for e in view['graph']['edges']}
    _columns(d, lay)
    for route in lay.routes:
        _route(d, view['tab'], route, edges.get(route.id))
    for box in lay.boxes:
        _box(d, box)
    y = _table(d, view, lay.height + TABLE_GAP)
    _warnings(d, view, y)
    return d.data()
