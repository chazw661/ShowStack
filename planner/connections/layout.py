"""Where every box and line of the wiring diagram goes. Pure geometry.

``layout(graph)`` takes ``graph.project_graph()``'s dict and returns a
``Layout``: boxes, group headers and routed edges in diagram units (px at
100%). No Django, no queries and no markup, so the screen view (``svg``) and a
later 11x17 PDF draw the same picture.

Six fixed columns, signal flowing left to right:

  0 I/O inputs    an I/O device's inputs box, "<name> · inputs"
  1 Console
  2 I/O outputs   the same device's outputs box, "<name> · outputs"
  3 Processor     also text a feed names that matched no single processor
  4 Amp           grouped by amp location, in the locations' order; amps with
                  none, and the "not linked" amp rack, last under "No location"
  5 Speaker       speaker arrays; where a run goes, as typed (a plain
                  "destination" box); text no single array matched (unlinked)

An I/O device is split so a console bus feeding a stage-box output runs left
to right like everything else; one with ports on one side only gets that box.
An edge that skips a column (I/O output -> amp) passes through a one-slot
dummy in each column between, so it gets its own lane there.

Ordering is barycenter: a few sweeps sorting each column by the mean position
of its neighbours in the column before (then after). In the amp column the
sort is only within a location group; groups never move.

Routing is orthogonal: out of the source's right side, along to a vertical
track of its own in the gap, then along into the target's left side. Every
horizontal run goes rightward. The edge's label sits on its first run, just
right of the source, in a label zone as wide as the gap's longest label.
"""
from dataclasses import dataclass, field
from statistics import mean

IO_IN, CONSOLE, IO_OUT, PROCESSOR, AMP, SPEAKER = range(6)
COLUMN_TITLES = ('I/O inputs', 'Console', 'I/O outputs', 'Processors', 'Amps', 'Speakers')

BOX_W = 200
HEAD = 34           # title + subtitle above the first port slot
SLOT = 18           # port slots, and the lines on them, are this far apart
PAD = 8             # below the last slot
GAP_Y = 18          # between boxes in a column
GROUP_HEAD = 24     # an amp location's header
MARGIN = 24
TITLE_H = 30        # column titles
TRACK = 8           # between vertical tracks in a gap
LABEL_PAD = 10
CHAR_W = 6.4        # 11px label text, a generous average
LABEL_MAX = 300
SWEEPS = 4

NO_LOCATION = 'No location'


@dataclass(eq=False)          # identity: boxes and segments point at each other
class Box:
    id: str
    label: str
    column: int
    kind: str
    sub: str = ''
    style: str = 'device'       # 'device' / 'unlinked' / 'location' / 'dummy'
    node: str = ''              # graph node id ('' for a dummy)
    group: str | None = None
    x: float = 0
    y: float = 0
    w: float = BOX_W
    h: float = 0
    ins: list = field(default_factory=list)     # segments ending here, top to bottom
    outs: list = field(default_factory=list)    # segments starting here

    @property
    def dummy(self):
        return self.style == 'dummy'

    def slot_y(self, segment):
        if self.dummy:
            return self.y + SLOT / 2
        side = self.ins if segment.to_box is self else self.outs
        return self.y + HEAD + SLOT / 2 + side.index(segment) * SLOT


@dataclass
class Group:
    key: str
    label: str
    rank: int
    x: float = 0
    y: float = 0


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
    label_full: str         # the untruncated label, for a tooltip
    classes: tuple
    question: bool          # unlinked or ambiguous: drawn with "?"


@dataclass
class Layout:
    width: float
    height: float
    columns: list           # [(title, x, width)]
    boxes: list             # real boxes only
    groups: list
    routes: list
    not_drawn: list = field(default_factory=list)   # edges that would run right to left


def text_width(text):
    return len(text) * CHAR_W


def clip(text, width):
    """``text`` cut with "…" to fit ``width`` (at the label size)."""
    room = max(1, int(width / CHAR_W))
    return text if len(text) <= room else text[:room - 1].rstrip() + '…'


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
    def __init__(self, graph):
        self.graph = graph
        self.nodes = {n['id']: n for n in graph['nodes']}
        self.boxes = {}                 # box id -> Box
        self.columns = [[] for _ in COLUMN_TITLES]
        self.groups = {}                # key -> Group
        self.segments = []
        self.edges = []                 # (edge, from box, to box)
        self.not_drawn = []

    def box(self, box_id, **kw):
        if box_id not in self.boxes:
            box = Box(box_id, **kw)
            self.boxes[box_id] = box
            self.columns[box.column].append(box)
        return self.boxes[box_id]

    def device_box(self, node, side):
        name = node['label']
        if side == 'in':
            return self.box(f"{node['id']}#in", label=f'{name} · inputs', column=IO_IN,
                            kind='device', sub=_where(node), node=node['id'])
        return self.box(f"{node['id']}#out", label=f'{name} · outputs', column=IO_OUT,
                        kind='device', sub=_where(node), node=node['id'])

    def node_box(self, node_id, edge=None, end=None):
        node = self.nodes[node_id]
        kind = node['kind']
        if kind == 'device':
            return self.device_box(node, _io_side(edge, end) if edge else 'in')
        if kind == 'unlinked':
            column = SPEAKER if edge and 'speaker' in edge.get('transports', ()) else PROCESSOR
            return self.box(node_id, label=node['label'], column=column, kind=kind,
                            sub='ambiguous' if node.get('ambiguous') else 'not linked',
                            style='unlinked', node=node_id)
        if kind in ('amp', 'amp_location', 'amp_rack'):
            group = _location_group(node)
            if group is None:
                key, label, order = '', NO_LOCATION, None
            else:
                key, label, order = group
            self.groups.setdefault(key, (label, order))
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
        for edge in self.graph['edges']:
            src = self.node_box(edge['from'], edge, 'from')
            dst = self.node_box(edge['to'], edge, 'to')
            if src.column >= dst.column:
                self.not_drawn.append(edge)
                continue
            self.edges.append((edge, src, dst))
            chain = [src] + [self.box(f"{edge['id']}~{c}", label='', column=c, kind='dummy',
                                      style='dummy', h=SLOT)
                             for c in range(src.column + 1, dst.column)] + [dst]
            for i, (a, b) in enumerate(zip(chain, chain[1:])):
                seg = Segment(edge, a, b, first=i == 0)
                a.outs.append(seg)
                b.ins.append(seg)
                self.segments.append(seg)

        ranked = sorted(self.groups.items(),
                        key=lambda kv: (kv[1][1] is None, kv[1][1] or 0, kv[1][0].casefold(), kv[0]))
        self.groups = {key: Group(key, label, rank) for rank, (key, (label, _)) in enumerate(ranked)}

    # -- order ---------------------------------------------------------------

    def group_rank(self, box):
        if box.group is None:
            return len(self.groups) if box.column == AMP else 0
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
            if not box.dummy:
                box.h = HEAD + max(len(box.ins), len(box.outs), 1) * SLOT + PAD

    # -- position --------------------------------------------------------------

    def place_y(self):
        top = MARGIN + TITLE_H
        for column in self.columns:
            bottom = top - GAP_Y
            group = object()
            for box in column:
                header = 0
                if box.column == AMP and not box.dummy and box.group != group:
                    group = box.group
                    header = GROUP_HEAD
                wanted = [s.from_box.slot_y(s) - (box.slot_y(s) - box.y) for s in box.ins
                          if s.from_box.column == box.column - 1]
                y = bottom + GAP_Y + header
                if wanted:
                    y = max(y, mean(wanted))
                box.y = y
                if header:
                    self.groups[group].y = y - GROUP_HEAD
                bottom = y + box.h

    def place_x(self):
        x = MARGIN
        self.column_x = []
        for c, column in enumerate(self.columns):
            for box in column:
                box.x = x
                if box.dummy:
                    box.w = BOX_W
            self.column_x.append(x)
            if c == len(self.columns) - 1:
                break
            gap = [s for s in self.segments if s.from_box.column == c]
            labels = [min(text_width(self.label(s.edge)), LABEL_MAX) for s in gap if s.first]
            label_zone = (max(labels) + 2 * LABEL_PAD) if labels else LABEL_PAD
            bends = sorted((s for s in gap if abs(s.from_box.slot_y(s) - s.to_box.slot_y(s)) > 0.5),
                           key=lambda s: (s.from_box.slot_y(s), s.to_box.slot_y(s)))
            track0 = x + BOX_W + label_zone
            for i, seg in enumerate(bends):
                seg.track_x = track0 + i * TRACK
            for seg in gap:
                if seg not in bends:
                    seg.track_x = track0
            x = track0 + max(len(bends) - 1, 0) * TRACK + 2 * LABEL_PAD
        for group in self.groups.values():
            group.x = self.column_x[AMP]

    # -- routes ----------------------------------------------------------------

    @staticmethod
    def label(edge):
        text = edge.get('label') or ''
        if edge.get('unlinked') or edge.get('ambiguous'):
            text = text.rstrip(' →')        # "Out 4 →": the far end is the "?" box
            source = _edge_text(edge)
            text = ' · '.join(x for x in (f'? {source}' if source else '?', text) if x)
        return text

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
            out.append(Route(
                id=edge['id'], from_node=edge['from'], to_node=edge['to'],
                points=_simplify(points), label=clip(full, LABEL_MAX), label_full=full,
                label_x=src.x + src.w + LABEL_PAD, label_y=y0 - 4,
                classes=_classes(edge), question=bool(edge.get('unlinked') or edge.get('ambiguous'))))
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
    return tuple(out)


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


def layout(graph):
    b = _Builder(graph)
    b.build()
    b.order()
    b.sort_slots()
    b.place_y()
    b.place_x()
    routes = b.routes()
    boxes = [box for column in b.columns for box in column if not box.dummy]
    width = b.column_x[-1] + BOX_W + MARGIN
    height = max([box.y + box.h for box in boxes] + [MARGIN + TITLE_H]) + MARGIN
    columns = [(title, b.column_x[c], BOX_W) for c, title in enumerate(COLUMN_TITLES)]
    groups = sorted((g for g in b.groups.values()
                     if any(box.group == g.key for box in b.columns[AMP])),
                    key=lambda g: g.rank)
    return Layout(width, height, columns, boxes, groups, routes,
                  [e['id'] for e in b.not_drawn])
