"""One project's connection graph, as JSON-ready data. Read-only.

``project_graph(project)`` merges:

  confirmed  what is stored as a link today --
             * DeviceInput.console_input       (I/O input -> console channel)
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
(from, to, status, network, unlinked, to slot): "In 1–15 → Ch 1–15". Network
is in the key because an AVB feed has no cable and an AES feed does even when
none is recorded.

Amps and processors have named input slots (PR 3.2), listed in the node's
``slots``; an edge into one lands on one slot (``to_slot``) and is labelled
with its source side only ("Out 1", "AVB 3"), the slot naming the input. A
processor's slot is its input port ("AES 1", "Analog 2"). An amp's is the
physical input a source plugs into, numbered by the rack view's input row:
"XLR n" (analog), "AES n", "AVB n", n the lowest channel that source feeds
on that transport, and "XLR 1 → Ch 1–2" when it feeds several channels.

Each edge also carries ``label_lines``: its label split one line per port
group ("Aux 1–4 → Out 1–4", "Mtx 1 → Out 5") and per PA run, which the
diagram draws one under another. ``from_ports`` / ``to_ports`` are the
same ports without the arrow, for the diagram's Connections table.

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
"""
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
    to_slot: str = ''           # the amp / processor input slot it lands on
    note: str = ''              # after the source ports on a slotted label: "Out 17 · AES"


def _cable_for(transport):
    """AVB is a network feed: no cable. Anything else is a cable, recorded or not."""
    return None if transport == 'avb' else {'recorded': False}


def _pa_cable(row):
    length = row.length or (float(row.length_per_run) if row.length_per_run else None)
    return {'recorded': True, 'type': row.get_cable_display() if row.cable else '',
            'ids': [], 'length_ft': length, 'count': row.count}


def _pa_cable_label(row, shared=0):
    """"HR · 2× NL 8 75' · NL4 Y ×2": the Cable Label, the run, its fan-outs
    (prefetched), and "1 run → 3 arrays" when it feeds several."""
    cable = _pa_cable(row)
    length = cable['length_ft']
    run = ' '.join(x for x in (f"{row.count}×", cable['type'],
                               f"{length:g}'" if length else '') if x)
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


def _slots(links, index):
    """Give every link into an amp or a processor port its ``to_slot``;
    returns {node id: [{'id', 'label'}]}, each node's slots in input order."""
    kinds = {nid: n.kind for nid, n in index.nodes.items()}
    by_source = defaultdict(list)       # amp: (amp, transport, source) -> links
    named = defaultdict(dict)           # processor: node -> {slot id: (key, label)}
    for link in links:
        kind = kinds.get(link.to_node)
        if not link.to_port:
            continue
        if kind == ep.AMP:
            source = link.from_port.ref if link.from_port else link.from_node
            by_source[(link.to_node, link.transport, source)].append(link)
        elif kind == ep.PROCESSOR:
            link.to_slot = link.to_port.ref
            named[link.to_node][link.to_slot] = (_sort_key(link.to_port.label),
                                                  str(link.to_port.label))
    channels = defaultdict(set)         # (amp, slot id) -> channel labels
    for (amp, transport, _), group in by_source.items():
        labels = {l.to_port.label for l in group}
        first = min(labels, key=_sort_key)
        slot = f'{transport}:{first.number}'
        for link in group:
            link.to_slot = slot
        channels[(amp, slot)] |= labels
    prefixes = list(SLOT_PREFIX)
    for (amp, slot), labels in channels.items():
        transport, number = slot.split(':', 1)
        first = min(labels, key=_sort_key)
        label = f'{SLOT_PREFIX.get(transport, transport)} {first.number}'
        if len(labels) > 1:
            label += f' → {_runs(sorted(labels, key=_sort_key))}'
        order = prefixes.index(transport) if transport in prefixes else len(prefixes)
        named[amp][slot] = ((order,) + _sort_key(first), label)
    return {node: [{'id': slot, 'label': label}
                   for slot, (_, label) in sorted(slots.items(), key=lambda kv: kv[1][0])]
            for node, slots in named.items()}


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


LINK_NOTE = {'aes': 'AES', 'analog': 'Analog'}


def _stored_links(index):
    """Stored Connection rows, as confirmed links: an amp input linked to its
    source output (PR 2b-2), drawn from the processor or the I/O device's
    outputs box, and a processor AES / Analog input linked to an I/O or
    console output (PR 2b-3), labelled with its transport ("Out 17 · AES").
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
                          source=('connection', pk), cable=_cable_for(transport),
                          note=LINK_NOTE.get(transport, '')))
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


def _label_parts(links):
    """(phrases, cables): one "From → To" phrase per (from prefix, to
    prefix), and each PA run's cable label."""
    groups = defaultdict(lambda: ([], []))
    for link in links:
        key = (link.from_port.label.prefix if link.from_port else None,
               link.to_port.label.prefix if link.to_port else None)
        froms, tos = groups[key]
        if link.from_port and link.from_port.label not in froms:
            froms.append(link.from_port.label)
        if link.to_port and link.to_port.label not in tos:
            tos.append(link.to_port.label)
    # Into a slot: the slot names the input, so only the source side.
    slotted = all(l.to_slot for l in links)
    notes = {l.note for l in links}
    note = notes.pop() if len(notes) == 1 else ''
    phrases = []
    for froms, tos in groups.values():
        if slotted:
            phrase = ' · '.join(x for x in (_runs(froms), note) if x)
        elif not froms and not tos:
            continue
        else:
            phrase = f'{_runs(froms)} → {_runs(tos)}'.strip()
        if phrase:
            phrases.append(phrase)
    return phrases, list(dict.fromkeys(l.cable_label for l in links if l.cable_label))


def _edge_label(links):
    """The label on one line: phrases joined by " · "; PA runs carry no
    ports, their label is the cable's, several runs "; "-separated (each
    already uses " · ")."""
    phrases, cables = _label_parts(links)
    return ' · '.join(x for x in (' · '.join(phrases), '; '.join(cables)) if x)


def _edge_label_lines(links):
    phrases, cables = _label_parts(links)
    return phrases + cables


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
    shared = max((c.get('shared', 0) for c in recorded), default=0)
    if shared:
        out['shared'] = shared      # this run also feeds other arrays: count it once
    if len(recorded) < len(cables):
        out['partly_recorded'] = True
    return out


def _sources(links):
    counts = defaultdict(int)
    pa = []
    for link in links:
        if link.source[0] == 'pa_cable':
            pa.append(link.source[1])
        else:
            counts[link.source] += 1
    out = [({'kind': 'fk', 'field': s[1]} if s[0] == 'fk' else {'kind': 'rule', 'rule': s[1]})
           | {'count': n} for s, n in counts.items()]
    out += [{'kind': 'pa_cable', 'pk': pk} for pk in pa]
    return out


def _link_json(link):
    out = {'transport': link.transport}
    for side, port in (('from', link.from_port), ('to', link.to_port)):
        out[f'{side}_port'] = str(port.label) if port else None
        out[f'{side}_ref'] = port.ref if port else None
    if link.match:
        out['match'] = link.match
    return out


def _candidate_json(candidate):
    if isinstance(candidate, str):
        return {'node': candidate}
    return {'node': candidate.node, 'port': str(candidate.label), 'ref': candidate.ref}


def _node_order(nodes, node_id):
    node = nodes.get(node_id, {})
    return (KIND_ORDER.get(node.get('kind'), 99), str(node.get('label', '')).casefold(), node_id)


def project_graph(project, index=None, matches=None):
    index = index or m.ProjectIndex.load(project)
    matches = matches or m.match_all(index)

    g = _Graph(index)
    g.foreign_keys()
    g.links += _stored_links(index)
    g.rule_a(matches.a)
    g.rule_b(matches.b)
    g.rule_c(matches.c)
    slots = _slots(g.links, index)

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

    grouped = defaultdict(list)
    for link in g.links:
        grouped[(link.from_node, link.to_node, link.status, link.network,
                 link.unlinked, link.to_slot)].append(link)

    def order(item):
        (frm, to, status, network, unlinked, slot), _ = item
        return (_node_order(nodes, frm), _node_order(nodes, to),
                slot_order.get((to, slot), -1), status, network, unlinked)

    edges, warnings = [], []
    for n, ((frm, to, status, network, unlinked, slot), links) in enumerate(
            sorted(grouped.items(), key=order), 1):
        links.sort(key=lambda l: (_sort_key(l.from_port.label) if l.from_port else (),
                                  _sort_key(l.to_port.label) if l.to_port else ()))
        edge_id = f'e{n}'
        edge = {
            'id': edge_id, 'from': frm, 'to': to,
            'label': _edge_label(links),
            'label_lines': _edge_label_lines(links),
            'from_ports': _ports([l.from_port.label for l in links if l.from_port]),
            'to_ports': _ports([l.to_port.label for l in links if l.to_port]),
            'transports': sorted({l.transport for l in links if l.transport}),
            'network': network, 'status': status, 'unlinked': unlinked,
            'cable': _merge_cables([l.cable for l in links]),
            'links': [_link_json(l) for l in links],
            'sources': _sources(links),
        }
        if slot:
            edge['to_slot'] = slot
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

    return {
        'schema': SCHEMA,
        'project': {'id': project.pk, 'name': project.name},
        'nodes': sorted(nodes.values(), key=lambda nd: _node_order(nodes, nd['id'])),
        'edges': edges,
        'warnings': warnings,
    }
