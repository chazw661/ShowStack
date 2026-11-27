"""The Wiring Diagram's Comms tab: the comms patch as its own graph. Pure.

``comms_view(graph)`` takes ``graph.project_graph()``'s dict and returns one
for ``layout(..., scheme=COMMS_SCHEME)``: every comm device, the devices
patched to it and its 2-wire destinations.

Each comms link is its own edge (one line per port, where the project graph
merges them: "Dante Out 2–3 → Out 3–4"). An edge names the box each end is
on -- ``from_box`` / ``to_box``: 'to' (left of the comm devices), 'main' (a
comm device) or 'from' (right) -- and its row there (``from_slot`` /
``to_slot``, the port's ref). A device patched both ways is on both sides,
and a comm device another's Dante Out goes to is drawn again on the right,
so every line runs left to right.

A node's ``rows`` lists its ports per box, top to bottom: Dante In, Dante
Out, 4W, 2W, each by number. The port convention is the comm page's
(``comm_patch``): a Dante Out goes to a device OUTPUT, a Dante In comes from
a device INPUT, a 4W send goes to a device INPUT and a 4W receive comes from
a device OUTPUT. An I/O port's row also says what else it is linked to and
its name -- "Out 5 ← FOH Aux 12 (Program)" -- so a box carrying program
shows where it gets it without a console column.

A 2-wire port with a destination typed is a row on its comm device and a
line to a ``destination`` node of that text, labelled with its cable type.
Any other line's label names its far end, device and port, then its cable
type: "Arcadia 4W 1 · 4W adapter", "Arcadia Dante In 3". ``layout`` names
each row on the side its line attaches.
"""
ROW_ORDER = {'In': 0, 'Out': 1, 'Dante In': 0, 'Dante Out': 1, '4W': 2, '2W': 3}
CONSOLE_LINK_FIELDS = ('DeviceInput.console_input', 'DeviceOutput.console_output')


def _row_key(port):
    prefix, _, number = port.rpartition(' ')
    return (ROW_ORDER.get(prefix, 9), int(number) if number.isdigit() else 0, port)


def _own_links(graph):
    """{I/O port ref: "← FOH Aux 12" / "→ FOH Ch 5"}: the console link each
    I/O port has of its own (A links only)."""
    labels = {n['id']: n['label'] for n in graph['nodes']}
    out = {}
    for edge in graph['edges']:
        if edge.get('comm') or edge.get('b') or not any(
                s.get('kind') == 'fk' and s.get('field') in CONSOLE_LINK_FIELDS
                for s in edge.get('sources', ())):
            continue
        for link in edge.get('links', ()):
            frm, to = link.get('from_ref') or '', link.get('to_ref') or ''
            if to.startswith('deviceoutput:'):
                out.setdefault(to, f"← {labels.get(edge['from'], '')} {link['from_port']}")
            if frm.startswith('deviceinput:'):
                out.setdefault(frm, f"→ {labels.get(edge['to'], '')} {link['to_port']}")
    return out


def comms_view(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    order = {nid: i for i, nid in enumerate(nodes)}
    own = _own_links(graph)
    rows = {}                       # node id -> {box: {slot: (port, row label)}}
    edges, first = [], {}           # first: a merged edge's id -> its first line's

    def is_comm(node_id):
        return nodes.get(node_id, {}).get('device_kind') == 'comm'

    def row(node_id, box, slot, port, name=''):
        label = port
        if not is_comm(node_id):
            label = ' '.join(x for x in (port, own.get(slot, '')) if x)
            if name:
                label = f'{label} ({name})'
        rows.setdefault(node_id, {}).setdefault(box, {}).setdefault(slot, (port, label))

    for edge in graph['edges']:
        if not edge.get('comm'):
            continue
        frm, to = edge['from'], edge['to']
        # A comm device a line leaves is 'main'; one it arrives at from
        # another comm device is drawn again on the right.
        from_box = 'main' if is_comm(frm) else 'to'
        to_box = 'from' if is_comm(frm) else 'main'
        for i, link in enumerate(edge['links']):
            row(frm, from_box, link['from_ref'], link['from_port'], link.get('from_name', ''))
            row(to, to_box, link['to_ref'], link['to_port'], link.get('to_name', ''))
            label = ' · '.join(x for x in (
                ' '.join(y for y in (nodes[to].get('label', ''), link['to_port']) if y),
                link.get('cable_type', '')) if x)
            new_id = f"{edge['id']}.{i}"
            first.setdefault(edge['id'], new_id)
            edges.append({
                'id': new_id, 'from': frm, 'to': to, 'label': label,
                'label_lines': [label] if label else [],
                'from_ports': link['from_port'], 'to_ports': link['to_port'],
                'transports': [link['transport']], 'network': edge['network'],
                'status': edge['status'], 'unlinked': False, 'cable': edge.get('cable'),
                'links': [link], 'sources': edge.get('sources', []), 'comms_tab': True,
                'from_box': from_box, 'to_box': to_box,
                'from_slot': link['from_ref'], 'to_slot': link['to_ref'],
            })

    destinations = []
    for node in graph['nodes']:
        if not is_comm(node['id']):
            continue
        for port in node.get('two_wire', ()):
            name = f"2W {port['number']}"
            slot = f"twowire:{port['number']}"
            dest = f"commdest:{node['id']}:{port['number']}"
            rows.setdefault(node['id'], {}).setdefault('main', {})[slot] = (name, name)
            destinations.append({'id': dest, 'kind': 'destination', 'label': port['destination']})
            order[dest] = len(order)
            label = port.get('cable_type', '')
            edges.append({
                'id': f"{node['id']}.2w{port['number']}", 'from': node['id'], 'to': dest,
                'label': label, 'label_lines': [label] if label else [],
                'from_ports': name, 'to_ports': '', 'transports': ['analog'],
                'network': False, 'status': 'confirmed', 'unlinked': False, 'cable': None,
                'links': [], 'sources': [], 'comms_tab': True, 'two_wire': True,
                'from_box': 'main', 'to_box': 'from', 'from_slot': slot, 'to_slot': '',
            })

    out_nodes = []
    for node in graph['nodes']:
        if is_comm(node['id']) or node['id'] in rows:
            node = {k: v for k, v in node.items() if k != 'ports'}
            node['rows'] = {
                box: [{'id': slot, 'label': label}
                      for slot, (port, label) in sorted(by_slot.items(),
                                                        key=lambda kv: _row_key(kv[1][0]))]
                for box, by_slot in rows.get(node['id'], {}).items()}
            out_nodes.append(node)
    # Lines in the order of the rows they leave, so the graph reads top down.
    edges.sort(key=lambda e: (order[e['from']], _row_key(e['from_ports']),
                              order[e['to']], _row_key(e['to_ports'])))
    warnings = [{**w, 'edge': first[w['edge']]} for w in graph['warnings'] if w['edge'] in first]
    return {**graph, 'nodes': out_nodes + destinations, 'edges': edges, 'warnings': warnings}
