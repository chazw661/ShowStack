"""One project's connection graph, as JSON-ready data. Read-only.

``project_graph(project)`` merges:

  confirmed  what is stored as a link today --
             * DeviceInput.console_input       (I/O input -> console channel, A)
             * DeviceInput.console_input_b     (the same, B: its own edges,
               ``b: true``, labelled "FOH Ch 3 (B) · <Source (B)>")
             * DeviceOutput's generic FK       (console bus -> I/O output)
             * PA cable runs entered with an end: from the amp (or, with no
               amp, the amp rack) to each linked array, else to the typed
               "To" text as a ``destination`` node
  inferred   what ``matchers`` reads out of the stored text, worked out on
             every call, so a renamed label shows up at once --
             * rule (a)  console / I/O output -> processor input
             * rule (b)  processor output -> amp channel
             * rule (c)  older PA cable runs with no amp, rack or array
             * amp input text that matched nothing

Port-level links between the same two nodes become one edge, keyed by
(from, to, status, network, unlinked, to slot). Network is in the key because
an AVB feed has no cable and an AES feed does even when none is recorded.

Both ends of a line are named, each inside its own box, and the line's label
names the far end -- so either end reads without tracing the line:

  source   the edge's ``from_ports``, the ports as the device's panel names
           them (``_physical``: "Analog Out 5", "AES Out 2", "AVB Out 3",
           "In 1–15", "Aux 23, Mtx 1–4"). Its row in the source box is the
           edge's ``from_slot``; the node lists them in port order in
           ``out_slots`` ([{id, lines}], a line per kind of port). Edges
           leaving the same ports share one row id: the diagram names it once.
  target   the edge's ``to_slot``, one of the node's ``slots``, each naming
           its port and what feeds it. A processor's is its input port ("AES
           1 ← Y001 AES Out 1 (Left)"). An amp's is the input a source plugs
           into: "XLR n ← Y001 Analog Out 3 (Left)", "AES n ← ...", n the
           lowest channel that source feeds on that transport, plus "· Ch
           1–2" when it feeds several; an AVB feed has no input number of its
           own: "AVB ← SL P1 stream 3 (L Main) · Ch 1"; text that names no
           output reads "AES 1 ← “Left” (not linked)". A console's or an I/O
           device's is one per line into it: "Ch 1–16, 33 ← Y001 In 1–17".
  label    ``label_lines``: the far device and port, a line per port group
           ("SL P1 AES 1", "Rack 1 Amp 2 XLR 1", "FOH Ch 1–15"), then each PA
           run's cable; ``label`` is the same on one line. ``to_ports`` are
           the far ports alone, for the diagram's Connections table.

A PA cable run is labelled with its cable: "HR · 2× NL 8 75' · NL4 Y ×2
+NL4 25' ×1" (the Cable Label, count, cable type, length, fan-outs, each
fan-out's extensions). One run feeding
several linked arrays is one edge per array, each saying so ("1 run → 3
arrays") and carrying ``cable.shared`` so a total counts the run once. A run
with no amp, rack or array is matched from its text (rule c): it starts at
the project's one ``amp_rack:unlinked`` node -- or at the amp rack its
Destination names (an Amp Location, or ``amp_rack:text:...`` for rack text
with no Amp Location), whose speaker end is then unnamed. A Destination that
is no single array is a node of its own text, shared by every run naming the
same thing.

Text that names nothing, or names more than one device, is drawn as an edge
to (or from) an ``unlinked`` node carrying the text. An ambiguous match is
never resolved: the edge has ``ambiguous: true`` and its ``candidates``, and
``warnings`` lists it too. An amp input's text is one ``feed`` node per field
and text ("AVB 1", "AES: Left"), shared by every amp channel that typed it,
with the ``reason`` it names nothing.

Stored Connection rows join in ``_stored_links``: amp inputs linked to their
source (PR 2b-2) and P1 / Galaxy AES or Analog inputs linked to an I/O or
console output (PR 2b-3), both confirmed; a linked input is never matched.

The comms patch (``_comm_links``; ``connections/comm_patch.py``) is stored
links too: a comm device's Dante ins / outs and 4-wire ports to and from the
devices they are patched to, confirmed. Their edges carry ``comm: true``.
The Comms tab draws them (``tabs.comms_view`` splits them one line per
port); every other tab lists them in its Connections table and never lays
them out. A comm device's 2-wire ports with a destination typed are on its
node (``two_wire``), for the same tab. A Dante one between devices whose Dante networks are both
set and differ is in ``warnings`` (kind ``dante_network``). A comm device's
node carries ``device_kind: 'comm'``; any device with a Dante network set,
``dante_network``.
"""
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import groupby

from planner.connections import endpoints as ep
from planner.connections import matchers as m

SCHEMA = 1
CONFIRMED, INFERRED = 'confirmed', 'inferred'
KIND_ORDER = {k: i for i, k in enumerate(
    (ep.CONSOLE, ep.DEVICE, ep.PROCESSOR, ep.AMP_RACK, ep.AMP_LOCATION, ep.AMP, ep.ARRAY,
     ep.DESTINATION, ep.UNLINKED))}


@dataclass
class Link:
    from_node: str
    to_node: str
    from_port: m.Port | None = None
    to_port: m.Port | None = None
    transport: str | None = None
    status: str = CONFIRMED
    network: bool = False
    unlinked: bool = False
    rule: str = ''
    match: str = ''
    source: tuple = ()          # ('fk', 'DeviceInput.console_input') / ('rule', 'a') / ('pa_cable', pk)
    cable: dict | None = field(default_factory=lambda: {'recorded': False})
    ambiguous: bool = False
    drift: bool = False
    candidates: tuple = ()
    text: dict | None = None
    cable_label: str = ''       # PA runs: "HR · 2× NL 8 75'"
    to_slot: str = ''           # the input slot it lands on
    far: str = ''               # that slot's own name ("XLR 1", "AES 2"), for the line's label
    b: bool = False             # a B input link (DeviceInput.console_input_b)
    comm: bool = False          # a comms patch link: listed, not drawn
    networks: tuple = ()        # its two Dante networks, when they differ
    source_b: str = ''          # its channel's Source (B), for the label


def _cable_for(transport):
    """AVB is a network feed: no cable. Anything else is a cable, recorded or not."""
    return None if transport == 'avb' else {'recorded': False}


def _pa_cable(row):
    """The run's home-run cable. A linked run also lists its daisy-chain
    links, in order (``links`` is prefetched; the key is absent without any,
    so an unlinked run's graph, and its digest, are what they were)."""
    length = row.length or (float(row.length_per_run) if row.length_per_run else None)
    out = {'recorded': True, 'type': row.get_cable_display() if row.cable else '',
           'ids': [], 'length_ft': length, 'count': row.count}
    links = [{'type': link.get_cable_display(), 'length_ft': link.length,
              'count': link.quantity, 'note': link.note}
             for link in row.links.all()]
    if links:
        out['links'] = links
    return out


def _pa_links_text(row):
    """" → 2× NL 4 25' → 2× NL4 Jumper (under the stage)": each link after
    the home run, its note in brackets. Empty for a run with none."""
    return ''.join(f' → {link.summary}' + (f' ({link.note})' if link.note else '')
                   for link in row.links.all())


def _pa_cable_label(row, shared=0):
    """"HR · 2× NL 8 75' → 2× NL 4 25' · NL4 Y ×2": the Cable Label, the
    run and its daisy-chain links, its fan-outs (prefetched), and "1 run →
    3 arrays" when it feeds several."""
    cable = _pa_cable(row)
    length = cable['length_ft']
    run = ' '.join(x for x in (f"{row.count}×", cable['type'],
                               f"{length:g}'" if length else '') if x)
    run += _pa_links_text(row)
    zone = row.label.name.strip() if row.label_id else ''
    fans = ', '.join(' '.join([f'{fo.get_fan_out_type_display()} ×{fo.quantity}']
                              + [f"+{ext.extension_cable} {ext.extension_length}' ×{ext.quantity}"
                                 for ext in fo.extensions.all()])
                     for fo in row.fan_outs.all() if fo.fan_out_type)
    split = f'1 run → {shared} arrays' if shared > 1 else ''
    return ' · '.join(x for x in (zone, run, fans, split) if x)


FEED_PREFIX = {'avb_stream': 'AVB', 'aes_input': 'AES', 'analog_input': 'Analog'}


def _feed_label(field, text):
    """An amp input's field and text: "AVB 1", "AES: Left", never a bare number."""
    prefix = FEED_PREFIX[field]
    if field == 'avb_stream':
        return text if m.norm(text).startswith('avb') else f'{prefix} {text}'
    return f'{prefix}: {text}'


SLOT_PREFIX = {'avb': 'AVB', 'analog': 'XLR', 'aes': 'AES'}   # rack view's row order
PHYSICAL = {'aes': 'AES', 'analog': 'Analog'}
PROCESSOR_OUTPUTS = ('p1output', 'galaxyoutput')
IO_PORTS = ('deviceinput', 'deviceoutput')


def _physical(link, port):
    """The port as its device's own panel names it, for this link. An I/O
    port feeding a processor or an amp is named by the link's transport --
    "Analog Out 5", "AES Out 2" (the model stores no port type, so one output
    patched both ways is two ports); a processor output says it is one:
    "AVB Out 3". A console link (Dante, MADI ...) and a comms link keep the
    plain port: "In 3", "Out 5", "Dante Out 2"."""
    label = port.label
    model = port.ref.split(':', 1)[0]
    if model in PROCESSOR_OUTPUTS:
        return ep.PortLabel(f'{label.prefix} Out', label.number)
    if (model in IO_PORTS and not link.comm and link.source[0] != 'fk'
            and link.transport in PHYSICAL):
        return ep.PortLabel(f'{PHYSICAL[link.transport]} {label.prefix}', label.number)
    return label


def _amp_source(link, index, extra_nodes):
    """Where an input's feed comes from, in full: "Y001 Analog Out 3 (Left)",
    "SL P1 stream 3 (L Main)", or the typed text when it names nothing."""
    port = link.from_port
    if port is None:
        text = (link.text or {}).get('source', '').strip()
        if not text:
            text = extra_nodes.get(link.from_node, {}).get('label', '')
        return f'“{text}” (not linked)'
    node = index.nodes.get(port.node)
    owner = node.label if node else ''
    if port.label.prefix == 'AVB':
        where = f'{owner} stream {port.label.number}'
    else:
        where = f'{owner} {_physical(link, port)}'
    name = (port.text or '').strip()
    return f'{where} ({name})' if name else where


def _amp_slot_label(transport, labels, link, index, extra_nodes):
    first = min(labels, key=_sort_key)
    source = _amp_source(link, index, extra_nodes)
    channels = _runs(sorted(labels, key=_sort_key))
    if transport == 'avb':
        return f'AVB ← {source} · {channels}'
    label = f'{SLOT_PREFIX.get(transport, transport)} {first.number} ← {source}'
    return f'{label} · {channels}' if len(labels) > 1 else label


def _slots(links, index, extra_nodes=None):
    """Give every drawn link that ends on a port its ``to_slot`` and
    ``far``; returns {node id: [{'id', 'label'}]}, each node's slots in input
    order. Every slot names its port and what feeds it ("← source")."""
    extra_nodes = extra_nodes or {}
    kinds = {nid: n.kind for nid, n in index.nodes.items()}
    by_source = defaultdict(list)       # amp: (amp, transport, source) -> links
    by_port = defaultdict(list)         # processor: (node, input port ref) -> links
    by_line = defaultdict(list)         # console / I/O device: one slot per line
    named = defaultdict(dict)           # node -> {slot id: (key, label)}
    for link in links:
        kind = kinds.get(link.to_node)
        if not link.to_port or link.comm:
            continue
        if kind == ep.AMP:
            source = link.from_port.ref if link.from_port else link.from_node
            by_source[(link.to_node, link.transport, source)].append(link)
        elif kind == ep.PROCESSOR:
            link.to_slot = link.to_port.ref
            link.far = str(link.to_port.label)
            by_port[(link.to_node, link.to_slot)].append(link)
        elif kind in (ep.CONSOLE, ep.DEVICE):
            by_line[(link.to_node, link.from_node, link.status, link.network,
                     link.unlinked, link.b)].append(link)
    for (node, slot), group in by_port.items():
        port = group[0].to_port.label
        sources = list(dict.fromkeys(_amp_source(l, index, extra_nodes) for l in group))
        named[node][slot] = (_sort_key(port), f"{port} ← {', '.join(sources)}")
    for (node, frm, status, network, unlinked, b), group in by_line.items():
        slot = 'in:' + '|'.join(str(x) for x in (frm, status, int(network), int(unlinked), int(b)))
        for link in group:
            link.to_slot = slot
        first = min((l.to_port.label for l in group), key=_sort_key)
        named[node][slot] = (_sort_key(first), _line_slot_label(group, index))
    channels = defaultdict(set)         # (amp, slot id) -> channel labels
    feeder = {}                         # (amp, slot id) -> a link of the source feeding it
    for (amp, transport, _), group in by_source.items():
        labels = {l.to_port.label for l in group}
        first = min(labels, key=_sort_key)
        slot = f'{transport}:{first.number}'
        if transport == 'avb':          # no input number of its own
            far = f"AVB {_runs(sorted(labels, key=_sort_key))}"
        else:
            far = f'{SLOT_PREFIX.get(transport, transport)} {first.number}'
        for link in group:
            link.to_slot = slot
            link.far = far
        channels[(amp, slot)] |= labels
        feeder.setdefault((amp, slot), group[0])
    prefixes = list(SLOT_PREFIX)
    for (amp, slot), labels in channels.items():
        transport, number = slot.split(':', 1)
        first = min(labels, key=_sort_key)
        label = _amp_slot_label(transport, labels, feeder[(amp, slot)], index, extra_nodes)
        order = prefixes.index(transport) if transport in prefixes else len(prefixes)
        named[amp][slot] = ((order,) + _sort_key(first), label)
    return {node: [{'id': slot, 'label': label}
                   for slot, (_, label) in sorted(slots.items(), key=lambda kv: kv[1][0])]
            for node, slots in named.items()}


def _line_slot_label(links, index):
    """A console's or an I/O device's input slot, for one line into it:
    "Ch 1–16, 33 ← Y001 In 1–17", "Out 5, 20 ← FOH Aux 23; Out 1–4 ← FOH Mtx
    1–4" (one phrase per kind of port), a B link's "Ch 3 (B) ← Y001 In 5"."""
    groups = defaultdict(lambda: ([], []))
    for link in sorted(links, key=lambda l: _sort_key(l.to_port.label)):
        source = _physical(link, link.from_port) if link.from_port else None
        froms, tos = groups[(source.prefix if source else None, link.to_port.label.prefix)]
        if source and source not in froms:
            froms.append(source)
        if link.to_port.label not in tos:
            tos.append(link.to_port.label)
    node = index.nodes.get(links[0].from_node)
    owner = node.label if node else ''
    b = ' (B)' if links[0].b else ''
    return '; '.join(
        ' ← '.join(x for x in (f'{_runs(tos)}{b}', ' '.join(y for y in (owner, _runs(froms)) if y)) if x)
        for froms, tos in groups.values())


class _Graph:
    def __init__(self, index):
        self.index = index
        self.links = []
        self.extra_nodes = {}   # synthetic: amp_rack (when used) and unlinked
        self.has_processors = any(n.kind == ep.PROCESSOR for n in index.nodes.values())

    def unlinked(self, key, text, ambiguous=False):
        """A node for text that names no single device. A shared key keeps
        the first text seen and is ambiguous if any of its uses is."""
        node_id = ep.node_id(ep.UNLINKED, key)
        node = self.extra_nodes.setdefault(node_id, {
            'id': node_id, 'kind': ep.UNLINKED, 'label': text,
            'unlinked': True, 'ambiguous': False})
        node['ambiguous'] = node['ambiguous'] or ambiguous
        return node_id

    def feed(self, match):
        """The node for an amp input's text that names no single output: one
        per field and text, so channels that typed the same thing share it."""
        text = match.text.strip()
        node_id = ep.node_id(ep.UNLINKED, f'b:{match.field}:{m.norm(text)}')
        if node_id not in self.extra_nodes:
            if match.verdict == m.AMBIGUOUS:
                n = len({c.ref for c in match.candidates})
                reason = f'{n} possible sources'
            elif match.verdict == m.DRIFT:
                reason = 'label differs from the stream'
            elif match.field != 'avb_stream':
                reason = 'not matched to an output'
            elif self.has_processors:
                reason = 'not matched to a processor output'
            else:
                reason = 'no processor in project'
            self.extra_nodes[node_id] = {
                'id': node_id, 'kind': ep.UNLINKED, 'label': _feed_label(match.field, text),
                'unlinked': True, 'ambiguous': match.verdict == m.AMBIGUOUS,
                'feed': match.field, 'reason': reason}
        return node_id

    def use(self, node_id):
        """A real node an edge reaches; amp locations are only listed then."""
        node = self.index.nodes[node_id]
        if node.kind == ep.AMP_LOCATION:
            self.extra_nodes[node_id] = _node_json(node)
        return node_id

    def rack_text(self, text):
        """A Destination that says "amp rack" but names no Amp Location."""
        node_id = f'{ep.AMP_RACK}:text:{m.norm(text)}'
        self.extra_nodes.setdefault(node_id, {'id': node_id, 'kind': ep.AMP_RACK,
                                              'label': text, 'unlinked': True})
        return node_id

    def amp_rack(self):
        """The one node every PA run with no Amp linked starts at."""
        self.extra_nodes[ep.AMP_RACK_UNLINKED] = {
            'id': ep.AMP_RACK_UNLINKED, 'kind': ep.AMP_RACK,
            'label': ep.AMP_RACK_UNLINKED_LABEL, 'unlinked': True}
        return ep.AMP_RACK_UNLINKED

    # -- confirmed -------------------------------------------------------------

    def console_transport(self, device_node):
        """An I/O device's Console connection is the transport of its console
        links: Dante is a network feed (no cable), the rest are cables. Blank
        (not set) leaves the transport unknown."""
        transport = self.index.nodes[device_node].extra.get('console_connection') or None
        return dict(transport=transport, network=transport == 'dante',
                    cable=None if transport == 'dante' else {'recorded': False})

    def foreign_keys(self):
        idx = self.index
        for port, channel in idx.device_inputs:
            if channel:
                self.links.append(Link(port.node, channel.node, port, channel,
                                       source=('fk', 'DeviceInput.console_input'),
                                       **self.console_transport(port.node)))
        for port, channel, source_b in idx.device_inputs_b:
            self.links.append(Link(port.node, channel.node, port, channel,
                                   source=('fk', 'DeviceInput.console_input_b'),
                                   b=True, source_b=source_b,
                                   **self.console_transport(port.node)))
        for port, bus in idx.device_outputs:
            if bus:
                bus_port = idx.ports[bus]
                self.links.append(Link(bus_port.node, port.node, bus_port, port,
                                       source=('fk', 'DeviceOutput.console_output'),
                                       **self.console_transport(port.node)))
        for row in idx.pa_rows:
            if m.entered_pa_run(row):
                self.pa_run(row)

    def destination(self, text):
        """Where a run goes, as typed: one node per distinct text."""
        node_id = ep.node_id(ep.DESTINATION, m.norm(text))
        self.extra_nodes.setdefault(node_id, {'id': node_id, 'kind': ep.DESTINATION,
                                              'label': text.strip()})
        return node_id

    def pa_run(self, row):
        """A run entered with its ends: from the amp, else its rack; to each
        linked array, else to the typed To. Confirmed: nothing is matched."""
        idx = self.index
        amp = ep.node_id(ep.AMP, row.amp_id)
        rack = ep.node_id(ep.AMP_LOCATION, row.amp_location_id)
        if row.amp_id and amp in idx.nodes:
            from_node = amp
        elif row.amp_location_id and rack in idx.nodes:
            from_node = self.use(rack)
        else:
            from_node = self.amp_rack()
        arrays = [ep.node_id(ep.ARRAY, a.pk) for a in row.speaker_arrays.all()]
        arrays = [a for a in arrays if a in idx.nodes]
        text = (row.destination or '').strip()
        if arrays:
            targets = arrays
        elif m.norm(text):
            targets = [self.destination(text)]
        else:
            targets = [self.unlinked(f'pa:{row.pk}:speaker', ep.SPEAKER_UNNAMED_LABEL)]
        shared = len(targets) if arrays else 0
        cable = _pa_cable(row)
        if shared > 1:
            cable['shared'] = shared
        for to_node in targets:
            self.links.append(Link(
                from_node, to_node, transport='speaker',
                unlinked=from_node == ep.AMP_RACK_UNLINKED or to_node.startswith(ep.UNLINKED + ':'),
                source=('pa_cable', row.pk), cable=dict(cable),
                cable_label=_pa_cable_label(row, shared)))

    # -- inferred ---------------------------------------------------------------

    def rule_a(self, matches):
        for match in matches:
            src = match.source
            if match.verdict in m.RESOLVED:
                for target in match.targets:
                    if isinstance(target, str):          # a processor, by name
                        self.links.append(Link(src.node, target, src, None,
                                               status=INFERRED, rule='a', match=match.verdict,
                                               source=('rule', 'a')))
                        continue
                    transport = ep.PROCESSOR_TYPES[target.type]
                    self.links.append(Link(src.node, target.node, src, target, transport,
                                           INFERRED, transport == 'avb', rule='a',
                                           match=match.verdict, source=('rule', 'a'),
                                           cable=_cable_for(transport)))
            elif match.verdict == m.AMBIGUOUS:
                node = self.unlinked(f'a:{src.ref}', match.text, ambiguous=True)
                self.links.append(Link(src.node, node, src, None, status=INFERRED,
                                       unlinked=True, rule='a', match=match.verdict,
                                       source=('rule', 'a'), ambiguous=True,
                                       candidates=match.candidates,
                                       text={'source': match.text}))
            # UNMATCHED: most outputs feed no processor (wedges, records,
            # press) -- the report counts them; the graph does not draw them.
            # VIA_IO: the I/O output's own match draws this feed.

    def rule_b(self, matches):
        for match in matches:
            ch, transport = match.source, match.transport
            common = dict(transport=transport, status=INFERRED, network=transport == 'avb',
                          rule='b', match=match.verdict, source=('rule', 'b'),
                          cable=_cable_for(transport))
            if match.verdict in m.RESOLVED:
                for target in match.targets:
                    self.links.append(Link(target.node, ch.node, target, ch, **common))
                continue
            ambiguous = match.verdict == m.AMBIGUOUS
            node = self.feed(match)
            self.links.append(Link(node, ch.node, None, ch, unlinked=True,
                                   ambiguous=ambiguous, drift=match.verdict == m.DRIFT,
                                   candidates=match.candidates,
                                   text={'source': match.text, 'field': match.field},
                                   **common))

    def rule_c(self, matches):
        for cm in matches:
            row = cm.row
            amp, speaker = cm.amp, cm.speaker
            if amp.verdict == m.MATCHED:
                from_node = self.use(amp.target)
            elif amp.via == 'rack_text':
                from_node = self.rack_text(amp.text)
            else:
                from_node = self.amp_rack()
            ambiguous = speaker.verdict == m.AMBIGUOUS
            if speaker.verdict == m.MATCHED:
                to_node = speaker.target
            elif m.norm(speaker.text):
                to_node = self.unlinked(f'text:{m.norm(speaker.text)}', speaker.text, ambiguous)
            else:                       # blank, or the Destination named the rack
                to_node = self.unlinked(f'pa:{row.pk}:speaker', ep.SPEAKER_UNNAMED_LABEL)
            unlinked = amp.verdict != m.MATCHED or speaker.verdict != m.MATCHED
            self.links.append(Link(
                from_node, to_node, transport='speaker', status=INFERRED,
                unlinked=unlinked, rule='c', match=speaker.verdict,
                source=('pa_cable', row.pk), cable=_pa_cable(row), ambiguous=ambiguous,
                candidates=speaker.candidates,
                text={'destination': speaker.text or amp.text,
                      'amp_linked': amp.via == 'fk', 'destination_is_rack': speaker.verdict == m.RACK},
                cable_label=_pa_cable_label(row)))


def _stored_links(index):
    """Stored Connection rows, as confirmed links: an amp input linked to its
    source output (PR 2b-2), drawn from the processor or the I/O device's
    outputs box, and a processor AES / Analog input linked to an I/O or
    console output (PR 2b-3); an I/O output is named by its transport there
    ("AES Out 17").
    Rules (a) and (b) leave those inputs alone. A row whose end is gone
    (deleted outside the ORM) is skipped; the report counts it."""
    links = []
    for pk, source, channel, transport in index.amp_links:
        if source is None or channel is None:
            continue
        links.append(Link(source.node, channel.node, source, channel, transport,
                          network=transport == 'avb', source=('connection', pk),
                          cable=_cable_for(transport)))
    for pk, source, target, transport in index.processor_links:
        if source is None or target is None:
            continue
        links.append(Link(source.node, target.node, source, target, transport,
                          source=('connection', pk), cable=_cable_for(transport)))
    return links


def _comm_links(index):
    """The comms patch's stored Connection rows, as confirmed links. A row
    whose end is gone is skipped."""
    links = []
    for pk, source, target, transport, cable_type in index.comm_links:
        if source is None or target is None:
            continue
        networks = ()
        if transport == 'dante':
            a, b = (index.nodes[p.node].extra.get('dante_network', '') for p in (source, target))
            if a and b and a.casefold() != b.casefold():
                networks = (a, b)
        cable = None if transport == 'dante' else {'recorded': bool(cable_type),
                                                   **({'type': cable_type} if cable_type else {})}
        links.append(Link(source.node, target.node, source, target, transport,
                          network=transport == 'dante', source=('connection', pk),
                          cable=cable, comm=True, networks=networks))
    return links


# -- JSON ----------------------------------------------------------------------

def _node_json(node):
    out = {'id': node.id, 'kind': node.kind, 'label': node.label}
    if node.location:
        out['location'] = node.location
    out.update(node.extra)
    return out


def _sort_key(label):
    n = label.number
    return (label.prefix, 0, n, '') if isinstance(n, int) else (label.prefix, 1, 0, str(n))


def _runs(labels):
    """[In 1, In 2, In 3, In 7] -> 'In 1–3, 7'. Unnumbered ports are listed."""
    if not labels:
        return ''
    prefix = labels[0].prefix
    numbers = [l.number for l in labels]
    ints = sorted({n for n in numbers if isinstance(n, int)})
    parts = []
    for _, run in groupby(enumerate(ints), lambda p: p[1] - p[0]):
        run = [n for _, n in run]
        parts.append(str(run[0]) if len(run) == 1 else f'{run[0]}–{run[-1]}')
    parts += list(dict.fromkeys(str(n) for n in numbers if not isinstance(n, int)))
    return f'{prefix} {", ".join(parts)}'


def _ports(labels):
    """Port labels as runs, one per prefix: 'Aux 1–4, Mtx 1'."""
    groups = defaultdict(list)
    for label in labels:
        if label not in groups[label.prefix]:
            groups[label.prefix].append(label)
    return ', '.join(_runs(sorted(g, key=_sort_key)) for g in groups.values())


def _label_parts(links, names, kinds):
    """(from lines, far lines, cables) of one line.

    from lines   the source's own ports, as its panel names them, one line
                 per kind of port: "Analog Out 1", "Aux 23" / "Mtx 1–4, 14".
                 Drawn inside the source box, where the line leaves it.
    far lines    where the line goes, device and port: "SL P1 AES 1", "Rack 1
                 Amp 2 XLR 1", "FOH Ch 1–16, 33"; a B link's ends " (B) ·
                 <Source (B)>". The line's label. None for a PA run (no
                 ports) or a line to text that names nothing (the "?" box).
    cables       each PA run's cable label."""
    groups = defaultdict(lambda: ([], []))
    for link in links:
        source = _physical(link, link.from_port) if link.from_port else None
        key = (source.prefix if source else None,
               link.to_port.label.prefix if link.to_port else None,
               link.b, link.source_b, link.far, link.to_node)
        froms, tos = groups[key]
        if source and source not in froms:
            froms.append(source)
        if link.to_port and link.to_port.label not in tos:
            tos.append(link.to_port.label)
    by_prefix, far_lines = {}, []
    for (prefix, _, b, source_b, far, to), (froms, tos) in groups.items():
        if froms:
            seen = by_prefix.setdefault(prefix, [])
            seen += [f for f in froms if f not in seen]
        if kinds.get(to) == ep.UNLINKED or not (froms or tos):
            continue
        line = ' '.join(x for x in (names.get(to, ''), far or _runs(tos)) if x)
        if b:
            line = f'{line} (B)'
        far_lines.append(f'{line} · {source_b}' if source_b else line)
    from_lines = [_runs(sorted(labels, key=_sort_key)) for labels in by_prefix.values()]
    return (from_lines, list(dict.fromkeys(x for x in far_lines if x)),
            list(dict.fromkeys(l.cable_label for l in links if l.cable_label)))


def _merge_cables(cables):
    cables = [c for c in cables if c is not None]
    if not cables:
        return None
    recorded = [c for c in cables if c.get('recorded')]
    if not recorded:
        return {'recorded': False}
    out = {'recorded': True, 'ids': sorted({i for c in recorded for i in c.get('ids', [])}),
           'count': sum(c.get('count') or 0 for c in recorded)}
    for key in ('type', 'length_ft'):
        values = list(dict.fromkeys(c.get(key) for c in recorded))
        out[key] = values[0] if len(values) == 1 else values
        if len(values) > 1:
            out['mixed'] = True
    links = [link for c in recorded for link in c.get('links', ())]
    if links:
        out['links'] = links
    shared = max((c.get('shared', 0) for c in recorded), default=0)
    if shared:
        out['shared'] = shared      # this run also feeds other arrays: count it once
    if len(recorded) < len(cables):
        out['partly_recorded'] = True
    return out


def _sources(links):
    """Where an edge's links come from: a stored FK or a rule, counted; a
    PA cable run or a stored Connection row, each by pk."""
    counts = defaultdict(int)
    rows = []
    for link in links:
        if link.source[0] in ('pa_cable', 'connection'):
            rows.append(link.source)
        else:
            counts[link.source] += 1
    out = [({'kind': 'fk', 'field': s[1]} if s[0] == 'fk' else {'kind': 'rule', 'rule': s[1]})
           | {'count': n} for s, n in counts.items()]
    out += [{'kind': kind, 'pk': pk} for kind, pk in rows]
    return out


def _link_json(link):
    out = {'transport': link.transport}
    for side, port in (('from', link.from_port), ('to', link.to_port)):
        out[f'{side}_port'] = str(port.label) if port else None
        out[f'{side}_ref'] = port.ref if port else None
    if link.match:
        out['match'] = link.match
    if link.comm:
        # The ports' own names, for the Comms tab's rows.
        for side, port in (('from', link.from_port), ('to', link.to_port)):
            if port is not None and port.text:
                out[f'{side}_name'] = port.text
        if link.cable and link.cable.get('type'):
            out['cable_type'] = link.cable['type']
    return out


def _candidate_json(candidate):
    if isinstance(candidate, str):
        return {'node': candidate}
    return {'node': candidate.node, 'port': str(candidate.label), 'ref': candidate.ref}


def _node_order(nodes, node_id):
    node = nodes.get(node_id, {})
    return (KIND_ORDER.get(node.get('kind'), 99), str(node.get('label', '')).casefold(), node_id)


def digest(graph):
    """Eight hex digits naming this exact graph: the same wiring gives the
    same digest, so two printouts (or a printout and the screen) can be
    compared at a glance. Every node and edge counts, in canonical JSON."""
    text = json.dumps(graph, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]


def project_graph(project, index=None, matches=None):
    index = index or m.ProjectIndex.load(project)
    matches = matches or m.match_all(index)

    g = _Graph(index)
    g.foreign_keys()
    g.links += _stored_links(index)
    g.links += _comm_links(index)
    g.rule_a(matches.a)
    g.rule_b(matches.b)
    g.rule_c(matches.c)
    slots = _slots(g.links, index, g.extra_nodes)

    nodes = {nid: _node_json(n) for nid, n in index.nodes.items()
             if n.kind in ep.DEVICE_KINDS}
    # An I/O device is drawn as an inputs box and an outputs box; one with
    # no ports on a side gets no box for it.
    for side, ports in (('inputs', index.device_inputs), ('outputs', index.device_outputs)):
        for port, _ in ports:
            counts = nodes[port.node].setdefault('ports', {'inputs': 0, 'outputs': 0})
            counts[side] += 1
    for node_id, node_slots in slots.items():
        nodes[node_id]['slots'] = node_slots
    nodes.update(g.extra_nodes)
    slot_order = {(nid, s['id']): i for nid, ss in slots.items() for i, s in enumerate(ss)}
    names = {nid: n.get('label', '') for nid, n in nodes.items()}
    kinds = {nid: n.get('kind') for nid, n in nodes.items()}
    out_slots = defaultdict(dict)       # node -> {from_slot: (key, lines)}

    grouped = defaultdict(list)
    for link in g.links:
        grouped[(link.from_node, link.to_node, link.status, link.network,
                 link.unlinked, link.to_slot, link.b)].append(link)

    def order(item):
        (frm, to, status, network, unlinked, slot, b), _ = item
        return (_node_order(nodes, frm), _node_order(nodes, to),
                slot_order.get((to, slot), -1), status, network, unlinked, b)

    edges, warnings = [], []
    for n, ((frm, to, status, network, unlinked, slot, b), links) in enumerate(
            sorted(grouped.items(), key=order), 1):
        links.sort(key=lambda l: (_sort_key(l.from_port.label) if l.from_port else (),
                                  _sort_key(l.to_port.label) if l.to_port else ()))
        edge_id = f'e{n}'
        from_lines, far_lines, cables = _label_parts(links, names, kinds)
        sources = [_physical(l, l.from_port) for l in links if l.from_port]
        edge = {
            'id': edge_id, 'from': frm, 'to': to,
            'label': ' · '.join(x for x in (' · '.join(far_lines), '; '.join(cables)) if x),
            'label_lines': far_lines + cables,
            'from_ports': _ports(sources),
            'to_ports': _ports([l.to_port.label for l in links if l.to_port]),
            'transports': sorted({l.transport for l in links if l.transport}),
            'network': network, 'status': status, 'unlinked': unlinked,
            'cable': _merge_cables([l.cable for l in links]),
            'links': [_link_json(l) for l in links],
            'sources': _sources(links),
        }
        if slot:
            edge['to_slot'] = slot
        if from_lines and not any(l.comm for l in links):
            # Its row inside the source box: lines leaving the same ports
            # share one, named once.
            edge['from_slot'] = edge['from_ports']
            out_slots[frm].setdefault(edge['from_slot'],
                                      (_sort_key(min(sources, key=_sort_key)), from_lines))
        if any(l.comm for l in links):
            edge['comm'] = True
            cables = sorted({l.cable['type'] for l in links if l.cable and l.cable.get('type')})
            if cables:
                edge['cable_types'] = cables
        if b:
            # Its own line, lighter than A's (layout._classes: 'b').
            edge['b'] = True
            edge['to_ports'] = f"{edge['to_ports']} (B)"
        rules = sorted({l.rule for l in links if l.rule})
        if rules:
            edge['rules'] = rules
            edge['match'] = sorted({l.match for l in links if l.match})
        if any(l.ambiguous for l in links):
            edge['ambiguous'] = True
        if any(l.drift for l in links):
            edge['drift'] = True
        candidates = [_candidate_json(c) for l in links for c in l.candidates]
        if candidates:
            edge['candidates'] = candidates
        texts = [l.text for l in links if l.text]
        if texts:
            edge['text'] = texts[0] if len(texts) == 1 else texts
        edges.append(edge)

        mismatched = sorted({l.networks for l in links if l.networks})
        for networks in mismatched:
            warnings.append({'kind': 'dante_network', 'edge': edge_id, 'networks': list(networks)})
        for link in links:
            if link.ambiguous or link.drift:
                warnings.append({
                    'kind': 'ambiguous' if link.ambiguous else 'drift',
                    'rule': link.rule, 'edge': edge_id,
                    'source': (link.from_port or link.to_port).ref
                    if (link.from_port or link.to_port) else f'pa_cable:{link.source[1]}',
                    'text': link.text,
                    'candidates': [_candidate_json(c) for c in link.candidates],
                })

    for node_id, rows in out_slots.items():
        nodes[node_id]['out_slots'] = [
            {'id': slot, 'lines': lines}
            for slot, (_, lines) in sorted(rows.items(), key=lambda kv: kv[1][0])]

    return {
        'schema': SCHEMA,
        'project': {'id': project.pk, 'name': project.name},
        'nodes': sorted(nodes.values(), key=lambda nd: _node_order(nodes, nd['id'])),
        'edges': edges,
        'warnings': warnings,
    }
