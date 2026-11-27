"""Where every box and line of the wiring diagram goes. Pure geometry.

``layout(graph)`` takes ``graph.project_graph()``'s dict and returns a
``Layout``: boxes, group headers and routed edges in diagram units (px at
100%). No Django, no queries and no markup, so the screen view (``svg``) and
the PDF (``utils/pdf_exports/wiring_pdf``, paged by ``tiling``) draw the same
picture.

Seven fixed columns, signal flowing left to right:

  0 Device inputs   an I/O device's inputs box, titled with its name only
  1 Console
  2 Device outputs  the same device's outputs box
  3 Processor       also text a console / I/O output names that matched no
                    single processor input. Hidden when there is no processor.
  4 Unlinked feeds  amp input text that names no single output ("AVB 1",
                    "AES: Left"), one box per field and text, the reason below
                    it. Hidden when there is none.
  5 Amp             grouped by amp location, in the locations' order; amps
                    with none, and the "not linked" amp rack, last under
                    "No location"
  6 Speaker         speaker arrays; where a run goes, as typed (a plain
                    "destination" box); text no single array matched
                    (unlinked); arrays no cable reaches last, under
                    "Not cabled"

An I/O device is split so a console bus feeding a stage-box output runs left
to right like everything else; one with ports on one side only gets that box.
An edge that skips a column (I/O output -> amp) passes through a one-slot
dummy in each column between, so it gets its own lane there.

Ordering is barycenter: a few sweeps sorting each column by the mean position
of its neighbours in the column before (then after). In the amp column the
sort is only within a location group; groups never move.

A box's lines meet it on port slots SLOT apart, and every device box names
its own port where a line attaches: a line arriving, at the box's left edge;
a line leaving, right-aligned at its right edge -- by the line's direction,
never by the port's name. A line arrives on a named input slot (the graph's
``slots``: "XLR 1 ← Y001 Analog Out 3 (Left)", in input order; the edge's
``to_slot``). It leaves from a row of its source ports (the node's
``out_slots``, the edge's ``from_slot``), in port order; lines leaving the
same ports are consecutive rows and the ports are named once, on the first.
A box with names on both sides stacks them: its input slots, then its output
rows below, so neither runs into the other. A box with no named port (an amp
rack, a speaker) has one slot per line, ordered to cross least.

Routing is orthogonal: out of the source's right side, along to a vertical
track of its own in the gap, then along into the target's left side. Every
horizontal run goes rightward. The edge's label sits on its first run, just
right of the source, in a label zone as wide as the gap's longest label line.

Nothing is cut short. A label is drawn one line per port group or PA run
(the graph's ``label_lines``), stacked above its line; the out-slot it
starts from grows to hold them, so labels never overlap each other or a
track. A label with a line wider than ``label_max``, or more than
LABEL_LINES_MAX lines, is drawn as a key: a small boxed "[1]" badge on the
line itself, just right of the source box, in a row tall enough (KEY_ROW)
that the badge clears its neighbours; it is listed in the page's
Connections table (``Layout.keys``). Box titles, subtitles, extra lines,
slot names and group headers wrap at BOX_W; a wrapped slot is taller. Two
column titles carry a hint line under them (COLUMN_HINTS).

A device box may sit under a group header in its own column (the graph
node's ``group``: {key, label, order}; the Dante tab's Dante networks),
ordered like the amp locations: by ``order`` then label, ``order`` None last.

``layout(graph, scheme=COMMS_SCHEME)`` is the Comms tab (``tabs.comms_view``
builds its graph): three columns instead of the seven --

  0 To comms       a box per device feeding a comm device, one row per port
  1 Comm devices   a box per comm device, one row per patched port
  2 From comms     a box per device a comm device feeds; 2-wire destinations
                   as typed; another comm device a Dante Out goes to

Every box there is in port-row mode: its rows are named ports (the node's
``rows``), drawn inside it, and a line meets the box on its port's row -- in
on the left (``to_slot``), out on the right (``from_slot``), so a 4-wire
port's receive and send are on one row at one height. A row is named on the
side its line attaches (a 4-wire row with both, on both). A device patched
both ways is two boxes, left and right, and every route still runs rightward.

``Box.port_texts()`` is every port name of a box, placed and aligned; the
screen, the PDF and the DXF all draw that one list.

``layout(graph, trunks='T')`` is the Dante and AVB tabs: the lines leaving
one source port (the same box and ``from_slot``) are one trunk, not a line
each. They share one row in the source box, one lane through any column
they skip and one vertical track, and a branch leaves the track for each
receiver. ``Layout.trunks`` lists them, numbered down the page in tab order
(``Trunk.n``); ``Trunk.colour`` is its place in STREAM_COLOURS, which repeats
after the last. Its name (``Trunk.label``) is the edges' ``stream`` when the
tab gave them one (the AVB tab: the real output number), else the prefix and
its number ("T1"). The name is drawn in a badge at the top of the trunk and on
every tap, filled where the link is confirmed and hollow where it is inferred,
so a black-and-white print still reads; every line is solid. A trunk's routes
keep their whole path in ``points`` (for the page cuts) but a renderer draws
``Trunk.lines`` instead, each piece once, then each route's arrowhead and
label. The labels of a trunk stack on its first run, a receiver after the
other; one too wide is its "[n]" there, as text. A "?" edge is never a trunk:
it is drawn as on any tab, without the ``network`` class (dashed, not dotted).
A gap's tracks are put in the order that runs no line through another
trunk's badge when there is one (``clear_order``).
``Box.port_streams()`` is, for each of ``port_texts()``, the trunk it belongs
to (its ``n``) or None.

``layout(graph, wrap=True)`` (the Dante and AVB tabs too): a tab that would
not fit an 11x17 page at 100% (WRAP_PAGE) has its tallest column wrapped
into sub-columns, side by side, one more at a time for as long as the tab
then fits the page at a scale WRAP_GAIN larger. A sub-column is a column in every way
(``Layout.columns`` lists it, titled "Amps (cont.)"; the page cuts fall
between them), but no line runs between two sub-columns of one column. The
boxes keep their order, top to bottom then left to right, cut where the
sub-columns come out most even: between two groups when that is nearly as
even (within WRAP_GROUP_SLACK), else inside one, whose later part is headed
"PA LEFT (continued)". A line that passes a sub-column runs in a lane at its
top, above the first header, LANE_GAP from the next lane.
"""
from dataclasses import dataclass, field
from functools import cached_property
from statistics import mean

IO_IN, CONSOLE, IO_OUT, PROCESSOR, FEEDS, AMP, SPEAKER = range(7)
COLUMN_TITLES = ('Device inputs', 'Console', 'Device outputs', 'Processors', 'Unlinked feeds',
                 'Amps', 'Speakers')
# A second, smaller line under a column title, for readers new to the split
# I/O device: which side a source plugs into, which side feeds the rest.
COLUMN_HINTS = {'Device inputs': '(mics & sources plug in here)',
                'Device outputs': '(feeds processors, amps, IEMs)'}
HIDDEN_WHEN_EMPTY = (PROCESSOR, FEEDS)
ALL_COLUMNS = tuple(range(len(COLUMN_TITLES)))
DEFAULT_SCHEME, COMMS_SCHEME = 'default', 'comms'
TO_COMMS, COMM_DEVICES, FROM_COMMS = range(3)
COMMS_TITLES = ('To comms', 'Comm devices', 'From comms')
COMMS_COLUMN = {'to': TO_COMMS, 'main': COMM_DEVICES, 'from': FROM_COMMS}

BOX_W = 200
HEAD = 28           # title + subtitle above the first port slot
TITLE_LH = 14       # each further line of a wrapped title
LINE_H = 13         # each further subtitle line, and each extra line (an IP line)
SLOT = 18           # port slots, and the lines on them, are this far apart
SLOT_LH = 12        # each further line of a wrapped slot name
LABEL_LH = 13       # between the lines of a label
PAD = 5             # below the last slot
GAP_Y = 10          # between boxes in a column
LANE_GAP = 0        # between two lanes at the top of a wrapped column: lines SLOT apart
GROUP_HEAD = 24     # an amp location's header
MARGIN = 24
TITLE_H = 42        # column titles, and the hint line under two of them
TITLE_Y = 12        # a column title's baseline below MARGIN
HINT_Y = 26         # its hint's baseline
TRACK = 8           # between vertical tracks in a gap
TRUNK_TRACK = 20    # ... on a tab drawn as trunks: room for the badges on them
BADGE_R = 7         # a stream badge's half height
BADGE_PX = 10       # a badge's text: never under the PDF's 6pt at its smallest scale
BADGE_CHAR_W = 6.2  # bold 10px badge text
# A trunk's colour: dark enough to read as 10px text on a box (4.5:1 or
# better), apart from each other for protan, deutan and tritan eyes, and none
# close to the diagram's own text or borders. ``test_wiring_trunks`` pins it.
STREAM_COLOURS = ('#0B7C8C', '#8B1A1A', '#4D7A00', '#C2185B', '#3D2DB3', '#5B1E7A')
LABEL_PAD = 10
CHAR_W = 6.4        # 11px label text, a generous average
TITLE_CHAR_W = 7.2  # 600 12px box titles
SLOT_CHAR_W = 5.9   # 10px slot names
TEXT_W = BOX_W - 16  # inside a box
PORT_PAD = 8        # a port name's gap from the box edge its line attaches to
PORT_DY = 3.5       # its baseline below the line
LABEL_MAX = 300
LABEL_LINES_MAX = 6
KEY_CHAR_W = 7.2    # bold 11px key text
KEY_PAD = 4         # either side of the key text, inside its badge
KEY_H = 14          # the badge's height, centred on the line
KEY_LINE = 11       # an out-row holding a badge: its line this far below the row's top
KEY_ROW = 26        # ... and the row this tall, so 4px clear the next row's label
SWEEPS = 4
WRAP_PAGE = (1166, 659)     # an 11x17 page's room for the diagram at 100%, in units
WRAP_GROUP_SLACK = 1.2      # whole groups, unless cutting inside one is this much more even
WRAP_GAIN = 1.05            # a further sub-column must let the tab print this much larger
WRAP_MAX = 8                # sub-columns added to one tab, at most
CONTINUED = '(continued)'   # after a group's label, on its later parts
CONT = '(cont.)'            # after a column's title, on its later sub-columns

NO_LOCATION = 'No location'
UNSET_NOTE = 'connection not set'       # a console link whose device has none (Analog tab)
NOT_CABLED = 'not_cabled'
NOT_CABLED_LABEL = 'Not cabled'


@dataclass(eq=False)          # identity: boxes and segments point at each other
class Box:
    id: str
    label: str
    column: int
    kind: str
    sub: str = ''
    logical: int = -1           # which of the scheme's columns ``column`` is (a sub-column of)
    lines: list = field(default_factory=list)   # extra text lines (the graph node's ``lines``)
    note: str = ''              # a last text line that links to the Comms tab (``comms_note``)
    style: str = 'device'       # 'device' / 'unlinked' / 'location' / 'dummy'
    node: str = ''              # graph node id ('' for a dummy)
    group: str | None = None
    x: float = 0
    y: float = 0
    w: float = BOX_W
    h: float = 0
    ins: list = field(default_factory=list)     # segments ending here, top to bottom
    outs: list = field(default_factory=list)    # segments starting here
    slots: list = field(default_factory=list)   # named input slots' labels, top to bottom
    in_slot: dict = field(default_factory=dict)  # segment -> its input slot's index
    slot_lines: list = field(default_factory=list)  # each slot's label, wrapped
    in_h: list = field(default_factory=list)    # each input row's height
    out_h: list = field(default_factory=list)   # each output row's height (its label's lines)
    out_line: list = field(default_factory=list)  # where in its row each output's line runs
    out_slot: dict = field(default_factory=dict)  # port-row mode: segment -> the row it leaves from
    slot_side: list = field(default_factory=list)  # port-row mode: each row's 'in' / 'out' / 'both'
    out_text: list = field(default_factory=list)  # each output row's port name, wrapped ([] = none)
    out_top: float = 0          # output rows start this far below the head (under named inputs)
    out_row: dict = field(default_factory=dict)  # trunks: segment -> the output row it shares
    in_stream: dict = field(default_factory=dict)   # input slot index -> its trunk's number
    out_stream: dict = field(default_factory=dict)  # output row index -> its trunk's number

    @property
    def dummy(self):
        return self.style == 'dummy'

    # Read once the box is built (its label, sub and lines are set by then).
    @cached_property
    def title_lines(self):
        return wrap(self.label, TEXT_W, TITLE_CHAR_W)

    @cached_property
    def text_rows(self):
        """[(class, text, y offset of its baseline)]: title, subtitle, extra lines."""
        rows, y = [], 15
        for line in self.title_lines:
            rows.append(('t', line, y))
            y += TITLE_LH
        y += LINE_H - TITLE_LH
        for line in wrap(self.sub, TEXT_W):
            rows.append(('s', line, y))
            y += LINE_H
        for extra in self.lines:
            for line in wrap(extra, TEXT_W):
                rows.append(('s ln', line, y))
                y += LINE_H
        for line in self.note_lines:
            rows.append(('s ln note', line, y))
            y += LINE_H
        return rows

    @cached_property
    def note_lines(self):
        """The note's lines: whole when it fits, else broken after its " · "
        ("2 comms patches ·" / "see Comms tab") before any other space."""
        if not self.note:
            return []
        if len(wrap(self.note, TEXT_W)) == 1:
            return [self.note]
        parts = self.note.split(' · ')
        return [line for i, part in enumerate(parts)
                for line in wrap(part + (' ·' if i < len(parts) - 1 else ''), TEXT_W)]

    @cached_property
    def head(self):
        return self.text_rows[-1][2] + HEAD - 28     # the rows start at the last baseline

    def row_y(self, i):
        """Input row ``i``'s line (a wrapped slot's first line)."""
        return self.y + self.head + sum(_rows(self.in_h, i)) + SLOT / 2

    def out_row_y(self, i):
        """Output row ``i``'s line: under its label's lines, or through the
        middle of a key badge's row."""
        line = self.out_line[i] if i < len(self.out_line) else SLOT / 2
        return self.y + self.head + self.out_top + sum(_rows(self.out_h, i)) + line

    def port_texts(self):
        """[(anchor, x, y, lines, full text)]: every port name in the box.
        ``anchor`` 'start': drawn from ``x`` (a line arrives there); 'end':
        ending at ``x`` (a line leaves there). ``y`` is the first line's
        baseline, the rest SLOT_LH apart below it."""
        return [port[:5] for port in self._ports()]

    def port_streams(self):
        """For each of ``port_texts()``, in order: the number of the trunk it
        is an end of, or None."""
        return [port[5] for port in self._ports()]

    def _ports(self):
        left, right = self.x + PORT_PAD, self.x + self.w - PORT_PAD
        out = []
        for i, (label, lines) in enumerate(zip(self.slots, self.slot_lines)):
            if not label:
                continue
            side = self.slot_side[i] if i < len(self.slot_side) else 'in'
            y = self.row_y(i) + PORT_DY
            if side != 'out':
                out.append(('start', left, y, lines, label, self.in_stream.get(i)))
            if side != 'in':
                out.append(('end', right, y, lines, label, self.in_stream.get(i)))
        for i, lines in enumerate(self.out_text):
            if lines:
                # Stacked upward: the last line is on the row's own line.
                y = self.out_row_y(i) + PORT_DY - SLOT_LH * (len(lines) - 1)
                out.append(('end', right, y, lines, ' '.join(lines), self.out_stream.get(i)))
        return out

    def slot_y(self, segment):
        if self.dummy:
            return self.y + SLOT / 2
        if segment.to_box is self:
            return self.row_y(self.in_slot.get(segment, self.ins.index(segment)))
        if segment in self.out_slot:
            return self.row_y(self.out_slot[segment])
        if segment in self.out_row:
            return self.out_row_y(self.out_row[segment])
        return self.out_row_y(self.outs.index(segment))


@dataclass
class Group:
    key: str
    label: str
    rank: int
    column: int = AMP
    x: float = 0
    y: float = 0

    @cached_property
    def lines(self):
        return wrap(self.label, BOX_W)

    @property
    def head(self):
        return GROUP_HEAD + LINE_H * (len(self.lines) - 1)


@dataclass(eq=False)          # identity: boxes and segments point at each other
class Segment:
    edge: dict
    from_box: Box
    to_box: Box
    first: bool             # carries the edge's label
    track_x: float = 0


@dataclass
class Route:
    id: str
    from_node: str
    to_node: str
    points: list            # [(x, y)], orthogonal, x never decreasing
    label: str
    label_x: float
    label_y: float
    label_full: str         # the label on one line, for a tooltip
    classes: tuple
    question: bool          # unlinked or ambiguous: drawn with "?"
    lines: list = field(default_factory=list)   # drawn, top to bottom; the last at label_y
    key: int | None = None  # drawn as "[key]", listed in the Connections table
    trunk: int | None = None    # the trunk (its ``n``) this is a branch of: its line is the trunk's

    @property
    def badge(self):
        """(x0, y0, x1, y1) of a key's badge, centred on the first run; else
        None (a trunk's key is a line of its label, "[n]")."""
        if not self.key or self.trunk:
            return None
        y = self.points[0][1]
        return (self.label_x, y - KEY_H / 2, self.label_x + key_width(self.key), y + KEY_H / 2)

    def line_boxes(self):
        """[(x0, y0, x1, y1)] around each drawn line (a key: its badge), for
        overlap checks."""
        if self.badge:
            return [self.badge]
        n = len(self.lines)
        return [(self.label_x, y - 9, self.label_x + text_width(line), y + 3)
                for i, line in enumerate(self.lines)
                for y in [self.label_y - (n - 1 - i) * LABEL_LH]]


@dataclass
class Badge:
    x: float
    y: float
    text: str
    filled: bool            # hollow: the tap of an inferred link
    edge: str = ''          # the edge whose tap it is ('' at the top of the trunk)

    @property
    def box(self):
        """(x0, y0, x1, y1): a circle for a short name, else a pill."""
        half = max(BADGE_R, len(self.text) * BADGE_CHAR_W / 2 + 3)
        return (self.x - half, self.y - BADGE_R, self.x + half, self.y + BADGE_R)


@dataclass
class Trunk:
    n: int                  # 1.. down the page, in tab order
    label: str              # its name: "T1", or the stream number the tab gave
    colour: int             # index into STREAM_COLOURS
    box: str                # the source box's id
    port: str               # the source port, as its box names it
    edges: list             # edge ids, in receiver order
    lines: list = field(default_factory=list)   # [(x0, y0, x1, y1, faded)], each piece once
    badges: list = field(default_factory=list)  # [Badge]


@dataclass
class Layout:
    width: float
    height: float
    columns: list           # [(title, x, width)], shown columns only
    boxes: list             # real boxes only
    groups: list
    routes: list
    not_drawn: list = field(default_factory=list)   # edges that would run right to left
    trunks: list = field(default_factory=list)      # [Trunk] (a tab drawn as trunks)

    @property
    def keys(self):
        """[(key, edge id)] of the labels drawn as keys, in key order."""
        return sorted((r.key, r.id) for r in self.routes if r.key)


def text_width(text, char_w=CHAR_W):
    return len(text) * char_w


def key_width(key):
    """A key badge's width."""
    return text_width(f'[{key}]', KEY_CHAR_W) + 2 * KEY_PAD


def wrap(text, width, char_w=CHAR_W):
    """``text`` in lines that fit ``width``, broken at spaces; a word longer
    than a line is split. Never shortened: the lines hold every character."""
    room = max(1, int(width / char_w))
    lines, line = [], ''
    for word in (text or '').split():
        while len(word) > room:
            if line:
                lines.append(line)
                line = ''
            lines.append(word[:room])
            word = word[room:]
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= room:
            line += ' ' + word
        else:
            lines.append(line)
            line = word
    if line or not lines:
        lines.append(line)
    return lines


def _rows(heights, n):
    """The first ``n`` row heights; a row not sized yet is one SLOT."""
    return heights[:n] + [SLOT] * (n - len(heights[:n]))


# -- boxes -----------------------------------------------------------------

def _io_side(edge, end):
    """Which half of an I/O device an edge's ``end`` ('from'/'to') is on."""
    refs = [l.get(f'{end}_ref') or '' for l in edge.get('links', ())]
    return 'in' if any(r.startswith('deviceinput:') for r in refs) else 'out'


def _edge_text(edge):
    text = edge.get('text')
    texts = text if isinstance(text, list) else [text] if text else []
    for t in texts:
        value = (t.get('source') or t.get('destination') or '').strip()
        if value:
            return value
    return ''


def _location_group(node):
    loc = node.get('location')
    if loc and loc.get('kind') == 'amp_location':
        return f"amp_location:{loc['id']}", loc['name'], loc.get('sort_order', 0)
    if node.get('kind') == 'amp_location':
        return node['id'], node['label'], node.get('sort_order', 0)
    return None


class _Builder:
    titles = COLUMN_TITLES

    def __init__(self, graph, hide_empty=HIDDEN_WHEN_EMPTY, label_max=LABEL_MAX, trunks=None,
                 split=None):
        self.split = split or {}        # column -> {box id: its sub-column, 0..}
        self.trunk_prefix = trunks      # None: a line per edge
        self.trunk_of = {}              # edge id -> (source box id, from_slot), its trunk
        self.hide_empty = hide_empty
        self.label_max = label_max
        self.graph = graph
        self.nodes = {n['id']: n for n in graph['nodes']}
        self.boxes = {}                 # box id -> Box
        # ``Box.column`` and ``self.columns`` are the columns as drawn: a
        # wrapped column is several. ``Box.logical`` is the scheme's column.
        self.first, self.logical_of = [], []
        for c in range(len(self.titles)):
            self.first.append(len(self.logical_of))
            self.logical_of += [c] * (max(self.split.get(c, {}).values(), default=0) + 1)
        self.columns = [[] for _ in self.logical_of]
        self.wrapped = {p for p, c in enumerate(self.logical_of) if c in self.split}
        self.groups = {}                # key -> Group
        self.segments = []
        self.edges = []                 # (edge, from box, to box)
        self.not_drawn = []
        self.drawn_lines = {}           # edge id -> the label's lines as drawn
        self.keys = {}                  # edge id -> its key, when drawn as one

    def box(self, box_id, **kw):
        if box_id not in self.boxes:
            box = Box(box_id, **kw)
            box.logical = box.column
            box.column = self.first[box.logical] + self.split.get(box.logical, {}).get(box_id, 0)
            box.lines = list(self.nodes.get(box.node, {}).get('lines', ()))
            box.note = self.nodes.get(box.node, {}).get('comms_note', '')
            self.boxes[box_id] = box
            self.columns[box.column].append(box)
        return self.boxes[box_id]

    def subs(self, c):
        """The columns, as drawn, of the scheme's column ``c``."""
        return [p for p, logical in enumerate(self.logical_of) if logical == c]

    def title(self, p):
        title = self.titles[self.logical_of[p]]
        return title if p == self.first[self.logical_of[p]] else f'{title} {CONT}'

    def lane(self, lane, p):
        """The one-slot dummy a line passes column ``p`` (as drawn) through."""
        box_id = f'{lane}~{p}'
        if box_id not in self.boxes:
            box = Box(box_id, label='', column=p, kind='dummy', style='dummy', h=SLOT,
                      logical=self.logical_of[p])
            self.boxes[box_id] = box
            self.columns[p].append(box)
        return self.boxes[box_id]

    def device_box(self, node, side):
        # The column title says inputs or outputs.
        name = node['label']
        sub = _where(node)
        if node.get('device_kind') == 'comm':
            sub = ' · '.join(x for x in ('Comm device', sub) if x)
        column = IO_IN if side == 'in' else IO_OUT
        return self.box(f"{node['id']}#{side}", label=name, column=column,
                        kind='device', sub=sub, node=node['id'],
                        group=self.node_group(node, column))

    def node_group(self, node, column):
        """The header a node's box sits under in ``column`` (its ``group``),
        or None. One header per column: a device's two boxes each get one."""
        group = node.get('group')
        if not group:
            return None
        key = f"{group['key']}@{column}"
        self.groups.setdefault(key, (group['label'], group.get('order'), column))
        return key

    def node_box(self, node_id, edge=None, end=None):
        node = self.nodes[node_id]
        kind = node['kind']
        if kind == 'device':
            return self.device_box(node, _io_side(edge, end) if edge else 'in')
        if kind == 'unlinked':
            if node.get('feed'):
                column = FEEDS
            elif edge and 'speaker' in edge.get('transports', ()):
                column = SPEAKER
            else:
                column = PROCESSOR
            sub = node.get('reason') or ('ambiguous' if node.get('ambiguous') else 'not linked')
            return self.box(node_id, label=node['label'], column=column, kind=kind,
                            sub=sub, style='unlinked', node=node_id)
        if kind in ('amp', 'amp_location', 'amp_rack'):
            group = _location_group(node)
            if group is None:
                key, label, order = '', NO_LOCATION, None
            else:
                key, label, order = group
            self.groups.setdefault(key, (label, order, AMP))
            style = ('unlinked' if node.get('unlinked')
                     else 'location' if kind == 'amp_location' else 'device')
            sub = (node.get('model') or 'Amp') if kind == 'amp' else (
                'amp location' if kind == 'amp_location' else 'not linked')
            return self.box(node_id, label=node['label'], column=AMP, kind=kind, sub=sub,
                            style=style, node=node_id, group=key)
        column = {'console': CONSOLE, 'processor': PROCESSOR, 'speaker_array': SPEAKER,
                  'destination': SPEAKER}[kind]
        sub = {'console': 'Console', 'speaker_array': 'Speaker array',
               'destination': 'destination'}.get(kind) or (
            node.get('device_type') or 'Processor')
        if kind not in ('speaker_array', 'destination') and _where(node):
            sub = f'{sub} · {_where(node)}'
        return self.box(node_id, label=node['label'], column=column, kind=kind, sub=sub,
                        node=node_id)

    def build(self):
        self.seed_boxes()
        self.connect()

    def seed_boxes(self):
        # Every node gets its boxes, connected or not, in the graph's order.
        for node in self.graph['nodes']:
            if node['kind'] == 'device':
                ports = node.get('ports') or {}
                if ports.get('inputs') or not ports.get('outputs'):
                    self.device_box(node, 'in')
                if ports.get('outputs'):
                    self.device_box(node, 'out')
            elif node['kind'] != 'unlinked':
                self.node_box(node['id'])

    def connect(self):
        for edge in self.graph['edges']:
            if edge.get('comm'):        # a comms patch link: listed, never drawn here
                continue
            src = self.node_box(edge['from'], edge, 'from')
            dst = self.node_box(edge['to'], edge, 'to')
            if src.logical >= dst.logical:
                self.not_drawn.append(edge)
                continue
            self.edges.append((edge, src, dst))
        # A column with no box of its own is left out: no title, no width, and
        # no dummies, so lines cross the gap where it would be.
        self.hidden = {self.first[c] for c in self.hide_empty
                       if c < len(self.titles) and not any(self.columns[p] for p in self.subs(c))}
        for edge, src, dst in self.edges:
            lane = edge['id']
            if (self.trunk_prefix is not None and edge.get('from_slot')
                    and not edge.get('unlinked') and not edge.get('ambiguous')):
                # One trunk for all that leaves this port: one lane too.
                self.trunk_of[edge['id']] = (src.id, edge['from_slot'])
                lane = f"trunk:{src.id}:{edge['from_slot']}"
            chain = [src] + [self.lane(lane, p) for p in range(src.column + 1, dst.column)
                             if p not in self.hidden] + [dst]
            for i, (a, b) in enumerate(zip(chain, chain[1:])):
                seg = Segment(edge, a, b, first=i == 0)
                a.outs.append(seg)
                b.ins.append(seg)
                self.segments.append(seg)

        ranked = sorted(self.groups.items(),
                        key=lambda kv: (kv[1][1] is None, kv[1][1] or 0, kv[1][0].casefold(), kv[0]))
        self.groups = {key: Group(key, label, rank, column)
                       for rank, (key, (label, _, column)) in enumerate(ranked)}
        # Speaker arrays no cable reaches go last, under their own header.
        for box in (self.boxes.values() if self.titles is COLUMN_TITLES else ()):
            if (box.logical == SPEAKER and box.kind == 'speaker_array'
                    and not box.ins and not box.outs):
                box.group = NOT_CABLED
                self.groups.setdefault(NOT_CABLED, Group(NOT_CABLED, NOT_CABLED_LABEL, 1, SPEAKER))
        # A header per column as drawn: a group cut by the wrap is headed
        # again, "(continued)", in each later sub-column.
        for key, group in list(self.groups.items()):
            mine = [box for box in self.boxes.values() if not box.dummy and box.group == key]
            at = sorted({box.column for box in mine})
            group.column = at[0] if at else self.first[group.column]
            for p in at[1:]:
                part = f'{key}~{p}'
                self.groups[part] = Group(part, f'{group.label} {CONTINUED}', group.rank, p)
                for box in mine:
                    if box.column == p:
                        box.group = part

    # -- order ---------------------------------------------------------------

    def top_lane(self, box):
        """A line passing a wrapped column: in a lane at its top."""
        return box.dummy and box.column in self.wrapped

    def group_rank(self, box):
        if self.top_lane(box):
            return -1
        if box.group is None:
            return len(self.groups) if box.logical == AMP else 0
        return self.groups[box.group].rank

    def order(self):
        for column in self.columns:
            column.sort(key=self.group_rank)          # stable: graph order within a group
        for _ in range(SWEEPS):
            for c in range(1, len(self.columns)):
                self.sweep(c, lambda b: [s.from_box for s in b.ins])
            for c in range(len(self.columns) - 2, -1, -1):
                self.sweep(c, lambda b: [s.to_box for s in b.outs])

    def sweep(self, c, neighbours):
        pos = {}
        for column in self.columns:
            for i, box in enumerate(column):
                pos[box.id] = i
        column = self.columns[c]

        def key(item):
            i, box = item
            near = [pos[n.id] for n in neighbours(box)]
            return (self.group_rank(box), mean(near) if near else i, i)
        self.columns[c] = [box for _, box in sorted(enumerate(column), key=key)]

    def sort_slots(self):
        pos = {box.id: (c, i) for c, column in enumerate(self.columns)
               for i, box in enumerate(column)}
        for box in self.boxes.values():
            box.ins.sort(key=lambda s: pos[s.from_box.id])
            box.outs.sort(key=lambda s: pos[s.to_box.id])
            if box.dummy:
                continue
            node = self.nodes.get(box.node, {})
            named = node.get('slots')
            rows = self.port_rows(box)
            if rows is not None:
                self.name_rows(box, rows)
                out_rows = [[seg] for seg in box.outs]
            else:
                if named:
                    self.name_slots(box, named)
                out_rows = self.name_outs(box, node.get('out_slots') or ())
            box.slot_lines = [wrap(label, TEXT_W, SLOT_CHAR_W) for label in box.slots]
            box.in_h = ([SLOT + SLOT_LH * (len(lines) - 1) for lines in box.slot_lines]
                        or [SLOT] * len(box.ins))
            box.out_h, box.out_line = [], []
            for i, row in enumerate(out_rows):
                seg = row[0]
                if seg.first and seg.edge['id'] in self.keys and seg.edge['id'] not in self.trunk_of:
                    h, line = KEY_ROW, KEY_LINE
                else:
                    # A trunk's row holds every receiver's label, stacked.
                    lines = sum(len(self.drawn_lines[s.edge['id']]) for s in row) if seg.first else 1
                    h = SLOT + LABEL_LH * (max(lines, 1) - 1)
                    line = h - SLOT / 2
                # Room above the line for a wrapped port name.
                names = len(box.out_text[i]) if i < len(box.out_text) else 0
                need = SLOT / 2 + SLOT_LH * (max(names, 1) - 1)
                if line < need:
                    h, line = h + need - line, need
                box.out_h.append(h)
                box.out_line.append(line)
            if any(box.slots) and any(box.out_text):
                box.out_top = sum(box.in_h)     # names on both sides: outputs under inputs
            box.h = box.head + max(sum(box.in_h), box.out_top + sum(box.out_h), SLOT) + PAD

    def port_rows(self, box):
        """The box's named port rows ([{id, label}]) when it is in port-row
        mode, else None."""
        return None

    def name_rows(self, box, rows):
        """Port-row mode: every row is a named port; a line comes in on its
        ``to_slot``'s row and leaves from its ``from_slot``'s."""
        index = {row['id']: i for i, row in enumerate(rows)}
        box.slots = [row['label'] for row in rows]
        for seg in box.ins:
            box.in_slot[seg] = index[seg.edge['to_slot']]
        for seg in box.outs:
            box.out_slot[seg] = index[seg.edge['from_slot']]
        box.ins.sort(key=lambda s: box.in_slot[s])
        box.outs.sort(key=lambda s: box.out_slot[s])
        ins, outs = set(box.in_slot.values()), set(box.out_slot.values())
        box.slot_side = ['both' if i in ins and i in outs else 'out' if i in outs else 'in'
                         for i in range(len(rows))]

    def name_outs(self, box, named):
        """The rows this box's lines leave from, in the graph's port order
        (``out_slots``); lines leaving the same ports are consecutive and the
        ports are named on the first only. A line with no source port (a PA
        run) keeps its place after them, unnamed. Returns the rows, each the
        segments leaving on it: one, or all of a trunk's."""
        order = {slot['id']: i for i, slot in enumerate(named)}
        lines = {slot['id']: slot['lines'] for slot in named}
        trunk = lambda s: self.trunk_of.get(s.edge['id'])
        box.outs.sort(key=lambda s: (order.get(s.edge.get('from_slot'), len(order)),
                                     trunk(s) is None))
        rows = []
        for seg in box.outs:
            if rows and trunk(seg) is not None and trunk(rows[-1][0]) == trunk(seg):
                rows[-1].append(seg)
            else:
                rows.append([seg])
            box.out_row[seg] = len(rows) - 1
        seen = set()
        for row in rows:
            slot = row[0].edge.get('from_slot')
            first = slot in lines and slot not in seen
            seen.add(slot)
            box.out_text.append([part for line in lines[slot]
                                 for part in wrap(line, TEXT_W, SLOT_CHAR_W)] if first else [])
        return rows

    def name_slots(self, box, named):
        """The slots this box's lines use, in the graph's input order; a line
        with no slot (a processor matched by name only) gets an unnamed one.
        A slot whose line is hidden (``kept``: network feeds off) stays."""
        used = {s.edge.get('to_slot') for s in box.ins}
        rows = [slot for slot in named if slot['id'] in used or slot.get('kept')]
        index = {slot['id']: i for i, slot in enumerate(rows)}
        box.slots = [slot['label'] for slot in rows]
        for seg in box.ins:
            if seg.edge.get('to_slot') not in index:
                box.in_slot[seg] = len(box.slots)
                box.slots.append('')
            else:
                box.in_slot[seg] = index[seg.edge['to_slot']]
        box.ins.sort(key=lambda s: box.in_slot[s])

    # -- position --------------------------------------------------------------

    def place_y(self):
        top = MARGIN + TITLE_H
        for column in self.columns:
            bottom = top - GAP_Y
            group = object()
            above = None
            for box in column:
                header = 0
                if (not box.dummy and box.group != group
                        and (box.logical == AMP or box.group is not None)):
                    group = box.group
                    header = self.groups[group].head
                lane = self.top_lane(box)       # packed at the top, wherever it comes from
                wanted = [] if lane else [
                    s.from_box.slot_y(s) - (box.slot_y(s) - box.y) for s in box.ins
                    if s.from_box.column == box.column - 1]
                gap = LANE_GAP if lane and above is not None and self.top_lane(above) else GAP_Y
                above = box
                y = bottom + gap + header
                if wanted:
                    y = max(y, mean(wanted))
                box.y = y
                if header:
                    self.groups[group].y = y - header
                bottom = y + box.h

    def place_x(self):
        x = MARGIN
        self.column_x = []
        for c, column in enumerate(self.columns):
            self.column_x.append(x)
            if c in self.hidden:
                continue
            for box in column:
                box.x = x
                if box.dummy:
                    box.w = BOX_W
            if c == len(self.columns) - 1:
                break
            gap = [s for s in self.segments if s.from_box.column == c]
            labels = [key_width(self.keys[s.edge['id']])
                      if s.edge['id'] in self.keys and s.edge['id'] not in self.trunk_of
                      else text_width(line)
                      for s in gap if s.first for line in self.drawn_lines[s.edge['id']]]
            label_zone = (max(labels) + 2 * LABEL_PAD) if labels else LABEL_PAD
            # A track for each line that bends, and for each trunk (all its
            # segments: the badges sit on it), in the order they leave.
            units = {}
            for seg in gap:
                units.setdefault(self.trunk_of.get(seg.edge['id'], seg), []).append(seg)

            def bends(seg):
                return abs(seg.from_box.slot_y(seg) - seg.to_box.slot_y(seg)) > 0.5
            tracked = sorted(
                (unit for key, unit in units.items()
                 if isinstance(key, tuple) or bends(unit[0])),
                key=lambda unit: (unit[0].from_box.slot_y(unit[0]),
                                  min(s.to_box.slot_y(s) for s in unit)))
            if self.trunk_prefix is not None:
                tracked = self.clear_order(tracked)
            step = TRACK if self.trunk_prefix is None else TRUNK_TRACK
            track0 = x + BOX_W + label_zone + (0 if self.trunk_prefix is None else BADGE_R)
            for seg in gap:
                seg.track_x = track0
            for i, unit in enumerate(tracked):
                for seg in unit:
                    seg.track_x = track0 + i * step
            x = track0 + max(len(tracked) - 1, 0) * step + 2 * LABEL_PAD
        for group in self.groups.values():
            group.x = self.column_x[group.column]

    def clear_order(self, units):
        """``units`` (a gap's tracks, left to right) in the order that runs
        the fewest lines through another trunk's badge: as given, by where
        each first lands, or either reversed. A line and a badge only meet
        when a receiver's slot is level with another trunk's port or tap."""
        def ends(unit):
            return (unit[0].from_box.slot_y(unit[0]), [s.to_box.slot_y(s) for s in unit])

        def badges(unit):
            if unit[0].edge['id'] not in self.trunk_of:
                return []
            y0, ys = ends(unit)
            return ys + ([min([y0] + ys)] if any(abs(y - y0) > 0.5 for y in ys) else [])

        def hits(order):
            marks = [badges(unit) for unit in order]
            n = 0
            for i, unit in enumerate(order):
                y0, ys = ends(unit)
                # Its first run crosses the tracks before its own; each
                # branch, the tracks after.
                for others, lines in ((marks[:i], [y0]), (marks[i + 1:], ys)):
                    n += sum(abs(y - mark) < BADGE_R + 2
                             for other in others for mark in other for y in lines)
            return n
        by_landing = sorted(units, key=lambda unit: (min(ends(unit)[1]), ends(unit)[0]))
        return min((units, units[::-1], by_landing, by_landing[::-1]), key=hits)

    # -- routes ----------------------------------------------------------------

    def label(self, edge):
        text = edge.get('label') or ''
        if edge.get('unlinked') or edge.get('ambiguous'):
            text = text.rstrip(' →')        # "Out 4 →": the far end is the "?" box
            frm = self.nodes.get(edge['from'], {})
            source = frm['label'] if frm.get('feed') else _edge_text(edge)
            head = f'? {source}' if source else '?'
            # "→ In 1": no from-port, so the arrow follows the text directly.
            joiner = ' ' if text.startswith('→') else ' · '
            text = joiner.join(x for x in (head, text) if x)
        if edge.get('connection_unset'):
            text = ' · '.join(x for x in (text, UNSET_NOTE) if x)
        return text

    def label_lines(self, edge):
        """The label one line per port group / PA run, as ``label`` words it."""
        lines = [x for x in (edge.get('label_lines') or [edge.get('label') or '']) if x]
        if edge.get('unlinked') or edge.get('ambiguous'):
            lines = [x.rstrip(' →') for x in lines]
            lines = [x for x in lines if x]
            frm = self.nodes.get(edge['from'], {})
            source = frm['label'] if frm.get('feed') else _edge_text(edge)
            head = f'? {source}' if source else '?'
            if lines and lines[0].startswith('→'):
                head = f'{head} {lines.pop(0)}'
            lines = [head] + lines
        if edge.get('connection_unset'):
            lines.append(UNSET_NOTE)
        return lines

    def fit_labels(self):
        """Each drawn edge's label lines, or its key when a line is wider
        than ``label_max`` or there are too many."""
        n = 0
        for edge, _, _ in self.edges:
            lines = self.label_lines(edge)
            if len(lines) > LABEL_LINES_MAX or any(text_width(x) > self.label_max for x in lines):
                n += 1
                self.keys[edge['id']] = n
                lines = [f'[{n}]']
            self.drawn_lines[edge['id']] = lines

    def trunks(self, routes):
        """The trunks, numbered down the page, with ``routes`` (this
        builder's) made their branches: each route's label placed in its
        trunk's stack, each end's port given the trunk's number."""
        by_id = {r.id: r for r in routes}
        last = {}           # edge id -> its last segment (into the receiver)
        for seg in self.segments:
            if not seg.to_box.dummy:
                last[seg.edge['id']] = seg
        out = []
        for column in self.columns:
            for box in column:
                rows = {}
                for seg in ([] if box.dummy else box.outs):
                    if seg.edge['id'] in self.trunk_of:
                        rows.setdefault(box.out_row[seg], []).append(seg)
                for row, segs in sorted(rows.items()):
                    n = len(out) + 1
                    named = {str(s.edge['stream']) for s in segs if s.edge.get('stream')}
                    label = named.pop() if len(named) == 1 and all(
                        s.edge.get('stream') for s in segs) else f'{self.trunk_prefix}{n}'
                    trunk = Trunk(n, label, (n - 1) % len(STREAM_COLOURS), box.id,
                                  ' '.join(box.out_text[row]), [s.edge['id'] for s in segs])
                    box.out_stream[row] = n
                    y0 = box.out_row_y(row)
                    below = sum(len(by_id[e].lines) for e in trunk.edges)
                    paths = []
                    for seg in segs:
                        route = by_id[seg.edge['id']]
                        below -= len(route.lines)
                        route.trunk = n
                        route.label_y = y0 - 4 - below * LABEL_LH
                        end = last[route.id]
                        if end in end.to_box.in_slot:
                            end.to_box.in_stream[end.to_box.in_slot[end]] = n
                        paths.append((route.points, 'b' in route.classes))
                        trunk.badges.append(Badge(end.track_x, route.points[-1][1], label,
                                                  filled='inferred' not in route.classes,
                                                  edge=route.id))
                    trunk.lines = _pieces(paths)
                    upright = [l for l in trunk.lines if abs(l[0] - l[2]) < 0.01]
                    if upright:
                        x, top = min(((l[0], min(l[1], l[3])) for l in upright),
                                     key=lambda p: (p[1], p[0]))
                        if not any(abs(b.x - x) < 0.01 and abs(b.y - top) < 0.01
                                   for b in trunk.badges):
                            trunk.badges.insert(0, Badge(x, top, label, filled=True))
                    out.append(trunk)
        # What is left is a "?" feed: dashed like any other, not a network
        # line of its own style (every network line here is a trunk).
        for route in routes:
            if route.trunk is None:
                route.classes = tuple(c for c in route.classes if c != 'network')
        return out

    def routes(self):
        out = []
        for edge, src, dst in self.edges:
            segs = []
            box = src
            while box is not dst:
                seg = next(s for s in box.outs if s.edge is edge)
                segs.append(seg)
                box = seg.to_box
            points = []
            for seg in segs:
                y0, y1 = seg.from_box.slot_y(seg), seg.to_box.slot_y(seg)
                points += [(seg.from_box.x + seg.from_box.w, y0), (seg.track_x, y0),
                           (seg.track_x, y1), (seg.to_box.x, y1)]
            full = self.label(edge)
            y0 = points[0][1]
            key = self.keys.get(edge['id'])
            out.append(Route(
                id=edge['id'], from_node=edge['from'], to_node=edge['to'],
                points=_simplify(points), label=full, label_full=full,
                # a key's text is centred in its badge on the line; a label sits above it
                label_x=src.x + src.w + LABEL_PAD, label_y=y0 + 4 if key else y0 - 4,
                classes=_classes(edge), question=bool(edge.get('unlinked') or edge.get('ambiguous')),
                lines=self.drawn_lines[edge['id']], key=key))
        return out


def _where(node):
    loc = node.get('location')
    return loc['name'] if loc and loc.get('kind') == 'location' else ''


def _classes(edge):
    out = ['unlinked'] if edge.get('unlinked') or edge.get('ambiguous') else [edge.get('status', 'inferred')]
    if edge.get('network'):
        out.append('network')
    if edge.get('ambiguous'):
        out.append('ambiguous')
    if edge.get('connection_unset'):
        out.append('unset')
    if edge.get('b'):
        out.append('b')         # a B input link: drawn lighter (svg.STYLE)
    return tuple(out)


def _union(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + 0.01:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _minus(spans, cover):
    """``spans`` without what ``cover`` holds (both as ``_union`` gives them)."""
    out = []
    for a, b in spans:
        for c, d in cover:
            if d <= a or c >= b:
                continue
            if c - a > 0.01:
                out.append((a, c))
            a = max(a, d)
        if b - a > 0.01:
            out.append((a, b))
    return out


def _pieces(paths):
    """[(x0, y0, x1, y1, faded)]: every stretch of ``paths`` ([(points,
    faded)], orthogonal) once, however many of them run along it. A stretch
    only faded paths (B input links) run along is faded."""
    spans = {}
    for points, faded in paths:
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if abs(y0 - y1) < 0.01:
                key, span = ('h', round(y0, 2)), tuple(sorted((x0, x1)))
            else:
                key, span = ('v', round(x0, 2)), tuple(sorted((y0, y1)))
            spans.setdefault(key, ([], []))[bool(faded)].append(span)
    out = []
    for (way, at), (solid, faded) in sorted(spans.items()):
        solid = _union(solid)
        for is_faded, group in ((False, solid), (True, _minus(_union(faded), solid))):
            for a, b in group:
                out.append((a, at, b, at, is_faded) if way == 'h' else (at, a, at, b, is_faded))
    return out


def _simplify(points):
    """Drop repeated points and the middle of straight runs."""
    out = []
    for p in points:
        if out and abs(out[-1][0] - p[0]) < 0.01 and abs(out[-1][1] - p[1]) < 0.01:
            continue
        if len(out) >= 2:
            (x0, y0), (x1, y1) = out[-2], out[-1]
            if (abs(x0 - x1) < 0.01 and abs(x1 - p[0]) < 0.01) or (
                    abs(y0 - y1) < 0.01 and abs(y1 - p[1]) < 0.01):
                out[-1] = p
                continue
        out.append(p)
    return out


class _CommsBuilder(_Builder):
    """The Comms tab's three columns, every box in port-row mode. The graph
    is ``tabs.comms_view``'s: an edge names the box each end is on
    (``from_box`` / ``to_box``: 'to', 'main' or 'from') and its row there."""
    titles = COMMS_TITLES

    def seed_boxes(self):
        # Every comm device is drawn, patched or not; the rest come with
        # the lines that reach them.
        for node in self.graph['nodes']:
            if node.get('device_kind') == 'comm':
                self.node_box(node['id'])

    def node_box(self, node_id, edge=None, end=None):
        node = self.nodes[node_id]
        if node['kind'] == 'destination':
            return self.box(node_id, label=node['label'], column=FROM_COMMS,
                            kind='destination', sub='2-wire destination', node=node_id)
        which = edge[f'{end}_box'] if edge else 'main'
        sub = _where(node)
        if node.get('device_kind') == 'comm':
            sub = ' · '.join(x for x in ('Comm device', sub) if x)
        return self.box(f'{node_id}#{which}', label=node['label'], column=COMMS_COLUMN[which],
                        kind='device', sub=sub, node=node_id)

    def port_rows(self, box):
        if box.kind != 'device':
            return None
        which = box.id.rsplit('#', 1)[1]
        used = ({s.edge['to_slot'] for s in box.ins} | {s.edge['from_slot'] for s in box.outs})
        return [row for row in self.nodes[box.node].get('rows', {}).get(which, ())
                if row['id'] in used]


BUILDERS = {DEFAULT_SCHEME: _Builder, COMMS_SCHEME: _CommsBuilder}


def layout(graph, hide_empty=HIDDEN_WHEN_EMPTY, label_max=LABEL_MAX, scheme=DEFAULT_SCHEME,
           trunks=None, wrap=False):
    """``hide_empty``: the columns left out when no box is in them (a tab
    passes ``ALL_COLUMNS``). ``label_max``: the widest a label line may be;
    a wider one makes the label a key. ``scheme``: which columns (the
    seven, or the Comms tab's three). ``trunks``: a prefix ("T") to draw the
    lines leaving one port as one trunk, named with it and a number.
    ``wrap``: wrap a tall column into sub-columns while the tab then fits an
    11x17 page at a larger scale."""
    def build(split):
        return _build(BUILDERS[scheme](graph, hide_empty, label_max, trunks, split), trunks)
    plain, lay = build({})
    b, split = plain, {}
    for _ in range(WRAP_MAX if wrap else 0):
        if _fit(lay) >= 1:
            break
        wider = _wider(plain, b, split)
        if wider is None:
            break
        b2, lay2 = build(wider)
        if _fit(lay2) < _fit(lay) * WRAP_GAIN:
            break
        b, lay, split = b2, lay2, wider
    return lay


def _fit(lay):
    """The scale ``lay`` fits one 11x17 page at."""
    return min(WRAP_PAGE[0] / lay.width, WRAP_PAGE[1] / lay.height)


def _partition(heights, n):
    """``heights`` in ``n`` consecutive runs, the tallest as short as can
    be: (that height, where each run starts)."""
    count = len(heights)
    total = [0]
    for h in heights:
        total.append(total[-1] + h)
    # best[k][i]: the first i in k runs -> (tallest, starts)
    best = [{0: (0, ())}]
    for k in range(1, n + 1):
        row = {}
        for i in range(k, count - (n - k) + 1):
            row[i] = min((max(best[k - 1][j][0], total[i] - total[j]), best[k - 1][j][1] + (j,))
                         for j in best[k - 1] if j < i)
        best.append(row)
    return best[n][count]


def _wider(plain, b, split):
    """``split`` with one more sub-column in the tallest column of ``b``,
    or None when its boxes are already one each. ``plain``: the same tab's
    builder with nothing wrapped, for the boxes' order and heights."""
    bottoms = {}
    for box in b.boxes.values():
        if not box.dummy:
            bottoms[box.logical] = max(bottoms.get(box.logical, 0), box.y + box.h)
    if not bottoms:
        return None
    c = max(bottoms, key=lambda k: (bottoms[k], -k))
    n = len(b.subs(c)) + 1
    boxes = [box for box in plain.columns[plain.first[c]] if not box.dummy]
    if n > len(boxes):
        return None
    groups = []                     # runs of boxes under one header
    for box in boxes:
        if groups and groups[-1][0].group == box.group:
            groups[-1].append(box)
        else:
            groups.append([box])

    def cut(units):
        heights = [sum(box.h + GAP_Y for box in unit) + GROUP_HEAD for unit in units]
        tallest, starts = _partition(heights, n)
        return tallest, [[box for unit in units[a:z] for box in unit]
                         for a, z in zip(starts, starts[1:] + (len(units),))]
    tallest, runs = cut([[box] for box in boxes])
    if len(groups) >= n:
        whole, whole_runs = cut(groups)
        if whole <= tallest * WRAP_GROUP_SLACK:
            runs = whole_runs
    return {**split, c: {box.id: k for k, run in enumerate(runs) for box in run}}


def _build(b, trunks):
    """(the builder, its Layout), everything placed and routed."""
    b.build()
    b.fit_labels()
    b.order()
    b.sort_slots()
    b.place_y()
    b.place_x()
    routes = b.routes()
    trunks = b.trunks(routes) if trunks is not None else []
    boxes = [box for column in b.columns for box in column if not box.dummy]
    drawn = [p for p in range(len(b.columns)) if p not in b.hidden]
    shown = [b.column_x[p] for p in drawn]
    width = (max(shown) if shown else MARGIN) + BOX_W + MARGIN
    height = max([box.y + box.h for box in boxes] + [MARGIN + TITLE_H]) + MARGIN
    columns = [(b.title(p), b.column_x[p], BOX_W) for p in drawn]
    groups = sorted((g for g in b.groups.values()
                     if any(box.group == g.key for box in b.columns[g.column])),
                    key=lambda g: (g.column, g.rank))
    return b, Layout(width, height, columns, boxes, groups, routes,
                     [e['id'] for e in b.not_drawn], trunks)
