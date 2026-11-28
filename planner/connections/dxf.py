"""The Wiring Diagram as DXF, one drawing per tab (Download DXF, for
Vectorworks). Drawn from ``connections.layout`` like the screen and the PDF,
but whole: no tiling, no page cuts, no "→ p.N" markers.

Top to bottom in model space: a title block (project, tab, when it was
made, the graph's digest, the scale), the legend, the diagram, then the
Connections table and Warnings as text (no warnings: "Warnings: none" in
the title block instead).

  boxes      closed LWPOLYLINEs (square corners; an unlinked box is DASHED)
  lines      LWPOLYLINEs along each route, a SOLID arrowhead at its end
  all text   TEXT entities, never outlines and never MTEXT (no inline
             formatting codes to escape): titles, subtitles, slot names,
             line labels, "[n]" keys, column titles and hints, group headers

Layers (Vectorworks imports them as classes). Their names are a prefix the
person downloading chose (``clean_prefix``; "Audio-Wiring" unless they say)
plus a fixed word, and nothing else: never a project, venue or location
name. Two modes:

  split (default)   <prefix>-Boxes, -Text, -Confirmed, -Inferred, -Unlinked,
                    -Network, -Speaker, -Comms, -Table, -Title
  single            everything on <prefix>

In split mode a line is on one layer, the kind of link when it has one,
else how sure it is --

  -Comms      every line on the Comms tab
  -Speaker    speaker cable runs
  -Network    AVB / Dante network feeds
  -Confirmed / -Inferred / -Unlinked   everything else, and every B input
              link (lighter, labelled "(B)")

-Boxes holds boxes and group rules; -Text every text of the diagram and the
key badges; -Title the title block and legend; -Table the Connections table
and Warnings.

On a tab drawn as trunks (Dante, AVB) each trunk is LINEs, every piece
once, CONTINUOUS and in the trunk's colour (``layout.STREAM_COLOURS``), on
the layer of its links; its name is in a badge at its top and on every tap:
a filled outline (a HATCH) with the name in white where the link is
confirmed, the outline alone where it is inferred. Its port names and labels
are in its colour too.

Every entity carries its own colour and linetype (CONTINUOUS / DASHED / DOT,
the screen's styles), never BYLAYER: a speaker run still shows whether it is
confirmed, and a single-class drawing looks the same as a split one.

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

# What a layer holds. Its name is the prefix plus this word (``layer_names``).
BOXES, TEXT, TITLE, TABLE = 'Boxes', 'Text', 'Title', 'Table'
CONFIRMED, INFERRED, UNLINKED = 'Confirmed', 'Inferred', 'Unlinked'
NETWORK, SPEAKER, COMMS = 'Network', 'Speaker', 'Comms'
INK = 7                         # ACI 7: black on a light page, white on a dark one
ROLES = (                       # word, true colour (None: INK)
    (BOXES, 0x4a6f9a), (TEXT, None), (CONFIRMED, 0x2b4c7e), (INFERRED, 0x2b4c7e),
    (UNLINKED, 0xb7791f), (NETWORK, 0x2f855a), (SPEAKER, 0x2b4c7e), (COMMS, 0x2b4c7e),
    (TABLE, None), (TITLE, None),
)
ROLE_COLOUR = dict(ROLES)
DEFAULT_PREFIX = 'Audio-Wiring'
MAX_PREFIX = 40
SPLIT, SINGLE = 'split', 'single'
MODES = ((SPLIT, 'Split classes'), (SINGLE, 'Single class'))
CONTINUOUS, DASHED, DOT = 'CONTINUOUS', 'DASHED', 'DOT'
# Patterns in inches, the screen's dashes at this drawing's scale. DOT is a
# short dash and a gap (the screen's "2 3"), not a true zero-length dot: a
# dot has no length to stroke, so it imports as nothing or as a solid line.
LINETYPES = (
    (DASHED, 'Dashed __ __ __ __', [10 * UNIT, 6 * UNIT, -4 * UNIT]),
    (DOT, 'Dot . . . . . . . .', [5 * UNIT, 2 * UNIT, -3 * UNIT]),
)
STYLE, STYLE_BOLD = 'Arial', 'Arial-Bold'
B_FADE = 0.45                   # a B link's colour, this much of it over white

LEGEND = (
    ('Confirmed (linked on a page)', ()),
    ('Inferred from labels', ('inferred',)),
    ('? Not linked or ambiguous', ('unlinked',)),
    ('AVB / Dante network (no cable)', ('network',)),
)
TRUNK_LEGEND = 'One colour and name per stream'
TAP_LEGEND = ('Confirmed', 'Inferred from labels')     # a filled badge, a hollow one
WHITE = 0xFFFFFF
NO_WARNINGS = 'Warnings: none'      # in the title block, instead of a Warnings section
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


_NOT_PREFIX = re.compile(r'[^A-Za-z0-9 _-]+')


def clean_prefix(text):
    """``text`` as a layer-name prefix: only letters, digits, space, "_" and
    "-", no "-" or space at either end, at most MAX_PREFIX long; the default
    when nothing is left."""
    s = _NOT_PREFIX.sub('', '' if text is None else str(text))
    s = re.sub(r' {2,}', ' ', s).strip(' -')[:MAX_PREFIX].strip(' -')
    return s or DEFAULT_PREFIX


def clean_mode(mode):
    return SINGLE if mode == SINGLE else SPLIT


def layer_names(prefix=DEFAULT_PREFIX, mode=SPLIT):
    """{what a layer holds: its name}. These are the only layers written."""
    prefix = clean_prefix(prefix)
    if clean_mode(mode) == SINGLE:
        return {role: prefix for role, _ in ROLES}
    return {role: f'{prefix}-{role}' for role, _ in ROLES}


def edge_layer(tab, classes, edge):
    """What the layer a route's line and arrowhead are on holds."""
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

    def __init__(self, ezdxf, arrows, prefix=DEFAULT_PREFIX, mode=SPLIT):
        from ezdxf.enums import TextEntityAlignment
        self.left = TextEntityAlignment.LEFT
        self.right = TextEntityAlignment.RIGHT
        self.center = TextEntityAlignment.CENTER
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
        self.layers = layer_names(prefix, mode)
        split = len(set(self.layers.values())) > 1
        for role, colour in ROLES:
            name = self.layers[role]
            if self.doc.layers.has_entry(name):
                continue
            layer = self.doc.layers.add(name, color=INK)
            if split and colour is not None:
                layer.true_color = colour
        self.msp = self.doc.modelspace()
        self.x0 = self.y0 = self.x1 = self.y1 = 0.0

    def _seen(self, x, y):
        self.x0, self.x1 = min(self.x0, x), max(self.x1, x)
        self.y0, self.y1 = min(self.y0, y), max(self.y1, y)

    @staticmethod
    def pt(x, y):
        return (round(x * UNIT, 5), round(-y * UNIT, 5))

    def attribs(self, role, linetype=CONTINUOUS, colour=None):
        """Layer, colour and linetype of one entity, all stated on it:
        ``colour`` when given, else the colour of what it is (``role``)."""
        if colour is None:
            colour = ROLE_COLOUR[role]
        attribs = {'layer': self.layers[role], 'color': INK, 'linetype': linetype}
        if colour is not None:
            attribs['true_color'] = colour
        return attribs

    def text(self, x, y, text, size, layer=TEXT, bold=False, fit=None, colour=None,
             anchor='start'):
        """One line at baseline ``y``; ``size`` is the screen's font size.
        ``fit``: the widest it may be, in layout units; a longer line is
        squeezed (TEXT width factor), never under MIN_WIDTH. ``anchor``
        'end': the line ends at ``x`` (right-aligned); 'middle': it is
        centred on ``x``."""
        value = clean(text, self.arrows)
        if not value:
            return None
        attribs = self.attribs(layer, colour=colour)
        attribs['style'] = STYLE_BOLD if bold else STYLE
        width = string_width(value, BOLD if bold else REGULAR, size)
        if fit and width > fit:
            attribs['width'] = round(max(MIN_WIDTH, fit / width), 3)
            width *= attribs['width']
        entity = self.msp.add_text(value, height=round(size * CAP * UNIT, 5), dxfattribs=attribs)
        if anchor == 'end':
            entity.set_placement(self.pt(x, y), align=self.right)
            x -= width
        elif anchor == 'middle':
            entity.set_placement(self.pt(x, y), align=self.center)
            x -= width / 2
        else:
            entity.set_placement(self.pt(x, y), align=self.left)
        self._seen(x, y - size)
        self._seen(x + width, y + size * 0.3)
        return entity

    def polyline(self, points, layer, linetype=CONTINUOUS, close=False, colour=None):
        attribs = self.attribs(layer, linetype, colour)
        for x, y in points:
            self._seen(x, y)
        return self.msp.add_lwpolyline([self.pt(x, y) for x, y in points], close=close,
                                       dxfattribs=attribs)

    def rect(self, x0, y0, x1, y1, layer, linetype=CONTINUOUS, colour=None):
        return self.polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, linetype, close=True,
                             colour=colour)

    def line(self, x0, y0, x1, y1, layer, linetype=CONTINUOUS, colour=None):
        attribs = self.attribs(layer, linetype, colour)
        self._seen(x0, y0)
        self._seen(x1, y1)
        return self.msp.add_line(self.pt(x0, y0), self.pt(x1, y1), dxfattribs=attribs)

    def arrowhead(self, x, y, layer, colour=None):
        return self.msp.add_solid([self.pt(x, y), self.pt(x - 6, y - 3.5), self.pt(x - 6, y + 3.5)],
                                  dxfattribs=self.attribs(layer, colour=colour))

    def badge(self, box, x, y, text, layer, colour, filled, size=L.BADGE_PX):
        """A stream's name in its badge (a circle, or a pill for a longer
        name), all in ``colour``: filled with the name in white, or hollow
        (an inferred tap)."""
        x0, y0, x1, y1 = box
        r = (y1 - y0) / 2
        self._seen(x0, y0)
        self._seen(x1, y1)
        # Anticlockwise as drawn (y up): along the bottom, round the right
        # end, back along the top, round the left end.
        outline = [(*self.pt(x0 + r, y1), 0), (*self.pt(x1 - r, y1), 1),
                   (*self.pt(x1 - r, y0), 0), (*self.pt(x0 + r, y0), 1)]
        attribs = self.attribs(layer, colour=colour)
        if filled:
            hatch = self.msp.add_hatch(dxfattribs=attribs)
            hatch.paths.add_polyline_path(outline, is_closed=True)
        self.msp.add_lwpolyline(outline, format='xyb', close=True, dxfattribs=attribs)
        self.text(x, y + size * 0.36, text, size, layer, bold=True,
                  colour=WHITE if filled else colour, anchor='middle')

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
    made = f'Made {printed} · Graph {digest}'
    if not view['warnings']:
        made += f' · {NO_WARNINGS}'
    d.text(0, y + 66, made, 11, TITLE)
    d.text(0, y + 82, scale_text(), 10, TITLE)
    entries = list(LEGEND)
    if view.get('show_b_legend'):
        entries.append(B_LEGEND)
    if view.get('show_unset_legend'):
        entries.append(UNSET_LEGEND)
    x, ly = 0, y + 106
    trunks = view['layout'].trunks
    if trunks:
        # A tab drawn as trunks: every line is solid, so the legend shows a
        # stream and the two badges.
        first = trunks[0]
        colour = stream_colour(first)
        d.line(x, ly - 4, x + 34, ly - 4, TITLE, colour=colour)
        d.text(x + 40, ly, TRUNK_LEGEND, 11, TITLE)
        x += 40 + string_width(TRUNK_LEGEND, REGULAR, 11) + 22
        for label, filled in zip(TAP_LEGEND, (True, False)):
            half = (L.Badge(0, 0, first.label, True).box[2])
            d.badge((x, ly - 4 - L.BADGE_R, x + 2 * half, ly - 4 + L.BADGE_R), x + half, ly - 4,
                    first.label, TITLE, colour, filled)
            d.text(x + 2 * half + 6, ly, label, 11, TITLE)
            x += 2 * half + 6 + string_width(label, REGULAR, 11) + 22
        entries = [LEGEND[2]] + ([B_LEGEND] if view.get('show_b_legend') else [])
    for label, classes in entries:
        layer = edge_layer(None, classes or ('confirmed',), None)
        colour = ROLE_COLOUR[layer]
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


def stream_colour(trunk):
    return int(L.STREAM_COLOURS[trunk.colour][1:], 16)


def _trunk(d, tab, trunk, routes, edges):
    """A trunk's pieces, each once, on the layer of its links, in its colour."""
    mine = [routes[e] for e in trunk.edges]
    layers = {}         # faded (a B link's own stretch) or not -> its layer
    for route in mine:
        layers.setdefault('b' in route.classes, edge_layer(tab, route.classes, edges.get(route.id)))
    colour = stream_colour(trunk)
    for x0, y0, x1, y1, faded in trunk.lines:
        d.line(x0, y0, x1, y1, layers[faded if faded in layers else not faded],
               colour=_fade(colour) if faded else colour)
    for badge in trunk.badges:
        d.badge(badge.box, badge.x, badge.y, badge.text, TEXT, colour, badge.filled)


def _box(d, box, trunks=None):
    d.rect(box.x, box.y, box.x + box.w, box.y + box.h, BOXES,
           DASHED if box.style == 'unlinked' else CONTINUOUS)
    for cls, line, dy in box.text_rows:
        d.text(box.x + 8, box.y + dy, line, 12 if cls == 't' else 11, bold=cls == 't', fit=L.TEXT_W)
    for (anchor, x, y, lines, _), n in zip(box.port_texts(), box.port_streams()):
        trunk = (trunks or {}).get(n)
        for j, line in enumerate(lines):
            d.text(x, y + j * L.SLOT_LH, line, 10, fit=L.TEXT_W, anchor=anchor,
                   colour=stream_colour(trunk) if trunk else None)


def _route(d, tab, route, edge, trunk=None):
    layer = edge_layer(tab, route.classes, edge)
    colour = _fade(ROLE_COLOUR[layer]) if 'b' in route.classes else None
    text = None
    if trunk is None:
        d.polyline(route.points, layer, edge_linetype(route.classes), colour=colour)
    else:           # a trunk's branch: the line is the trunk's (``_trunk``)
        text = stream_colour(trunk)
        colour = _fade(text) if 'b' in route.classes else text
    d.arrowhead(*route.points[-1], layer, colour=colour)
    if route.badge:
        x0, y0, x1, y1 = route.badge
        d.rect(x0, y0, x1, y1, TEXT)
        d.text(x0 + L.KEY_PAD, route.label_y, f'[{route.key}]', 11, bold=True)
        return
    n = len(route.lines)
    for i, line in enumerate(route.lines):
        d.text(route.label_x, route.label_y - (n - 1 - i) * L.LABEL_LH, line, 11, colour=text)


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
    if not warnings:            # the title block says "Warnings: none"
        return
    d.text(0, top + 14, f"Warnings ({len(warnings)}) — {view['tab_label']}", 14, TABLE, bold=True)
    y = top + 34
    for w in warnings:
        for j, line in enumerate(L.wrap(' '.join(warning_text(w).split()), sum(TABLE_W) - 14)):
            d.text(0 if j == 0 else 12, y, ('• ' if j == 0 else '') + line, 11, TABLE)
            y += L.LABEL_LH
        y += 4


def build_tab_dxf(*, project_name, view, digest, printed, arrows='', empty=False,
                  prefix=DEFAULT_PREFIX, mode=SPLIT):
    """One tab's drawing as DXF bytes. ``view``: a ``views_wiring.tab_view``
    dict; ``printed``: the stamp, already text; ``arrows='ascii'`` writes
    "<-" / "->" for the arrows; ``empty``: the project has nothing at all;
    ``prefix`` / ``mode``: the layer names (``layer_names``)."""
    import ezdxf

    d = _Drawing(ezdxf, arrows, prefix, mode)
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
    trunks = {t.n: t for t in lay.trunks}
    for route in lay.routes:
        _route(d, view['tab'], route, edges.get(route.id), trunks.get(route.trunk))
    routes = {r.id: r for r in lay.routes}
    for trunk in lay.trunks:
        _trunk(d, view['tab'], trunk, routes, edges)
    for box in lay.boxes:
        _box(d, box, trunks)
    y = _table(d, view, lay.height + TABLE_GAP)
    _warnings(d, view, y)
    return d.data()
