"""The Wiring Diagram's tabs: one project graph, filtered per view. Pure.

``graph_view(graph, tab)`` takes ``graph.project_graph()``'s dict and returns
a dict of the same shape holding only what that tab draws, for ``layout`` to
lay out on its own. Each tab is laid out independently, so a later PDF can
draw each as its own section.

  overview   everything
  dante      every console, every device on Dante (``on_dante``: its
             Console connection is Dante, or it has a Dante network set, or
             it is a comm device) and the Dante console links. Boxes carry
             the IP Address Manager's primary / secondary IP (``lines``).
  avb        the AVB / Milan streams: every processor AVB output's feed to
             an amp, and the amps' AVB stream text that names no output (the
             "?" feeds). ``avb_boxes`` then boxes every processor that has an
             AVB output, patched or not, and gives processors and amps their
             IP line; it is called by ``views_wiring`` with what
             ``views_wiring.avb_devices`` read, never from the project graph.
             No headers per network (AVB has no network name; amps keep their
             rack headers) and no banner (there is no setting to make).

The Dante and AVB tabs are drawn as trunks (``TRUNK_TABS``;
``layout(trunks=)``): one line leaves each source port and branches to its
receivers, in a colour and with a name of its own. An AVB edge carries the
real output number as ``stream`` (added here, never in the project graph), so
its trunk is named with it; a Dante trunk is "T1"… down the tab.
  analog     analog and AES feeds (I/O or console -> processor -> amp, I/O
             -> amp, their unlinked feeds and "?" matches) and every console
             link that is not Dante. A console link whose device has no
             Console connection set is kept and flagged ``connection_unset``.
  speakers   PA cable runs only: amps and racks -> speakers.
  comms      the comms patch (``comms_tab.comms_view``): every comm device,
             the devices patched to it and its 2-wire destinations, laid out
             in the Comms tab's own three columns (``layout.COMMS_SCHEME``).

On the Dante tab, once any device there has a Dante network set, device
boxes sit under a header per network (``node['group']``), "No network set"
last; consoles are not grouped.

B input links (``edge['b']``) are console links like A's: they follow their
device's Console connection onto Dante or Analogue/AES, so a device patched
only on B is on its tab.

Comms patch links (``edge['comm']``) are drawn on the Comms tab only: each other tab
keeps the ones on its transport (Dante: dante; Analogue/AES: the 4-wire
cables) for its Connections table and Warnings, and they bring no box with
them. A device patched only to comms is still boxed on the Dante tab when it
is on Dante (``on_dante``), under its network, with its IPs and no line.

Only the nodes a drawn edge reaches are kept (Dante also keeps every device
on Dante, linked or not). An I/O device's ``ports`` are counted from the drawn edges, so
it gets only the inputs / outputs box the tab uses; one with no drawn link
is a single box, in the Device inputs column.

``comms_notes(graph, full)`` adds the Overview's and the Dante tab's
"N comms patches · see Comms tab" line to a device with comms links only.

``without_network(graph)`` is the Overview with "Show network feeds" off:
no AVB / Dante network edges. An amp or processor slot one fed stays on its
box, named with its source ("AVB 1 ← P1 AVB 3"), so the box still says what
plugs in where.
"""

import re

OVERVIEW, DANTE, AVB, ANALOG, SPEAKERS, COMMS = (
    'overview', 'dante', 'avb', 'analog', 'speakers', 'comms')
TABS = (
    (OVERVIEW, 'Overview'),
    (DANTE, 'Dante'),
    (AVB, 'AVB'),
    (ANALOG, 'Analogue/AES'),
    (SPEAKERS, 'Speaker cables'),
    (COMMS, 'Comms'),
)
NO_NETWORK = 'No network set'
COMMS_NOTE = '{n} {patches} · see Comms tab'
TAB_KEYS = tuple(key for key, _ in TABS)
CONSOLE_LINK_FIELDS = ('DeviceInput.console_input', 'DeviceInput.console_input_b',
                       'DeviceOutput.console_output')
CABLE_FEEDS = ('analog', 'aes')
TRUNK_TABS = (DANTE, AVB)      # one trunk per source port, a branch per receiver
TRUNK_PREFIX = 'T'              # a trunk with no stream number of its own: "T1"
AVB_PORT = re.compile(r'AVB (\d+)$')
SPEAKER_LABEL_MAX = 560     # two or three columns: room for the whole cable label


def tab_or_default(value):
    return value if value in TAB_KEYS else OVERVIEW


def layout_options(tab):
    """``layout()`` keyword arguments for a tab: the Overview keeps its
    columns (Processors and Unlinked feeds hide when empty); a tab hides
    every column it does not use."""
    from planner.connections.layout import ALL_COLUMNS, COMMS_SCHEME
    if tab == OVERVIEW:
        return {}
    if tab == COMMS:
        return {'scheme': COMMS_SCHEME, 'hide_empty': ()}
    options = {'hide_empty': ALL_COLUMNS}
    if tab in TRUNK_TABS:
        options['trunks'] = TRUNK_PREFIX
        options['wrap'] = True      # a tall column wraps into sub-columns
    if tab == SPEAKERS:
        options['label_max'] = SPEAKER_LABEL_MAX
    return options


def is_console_link(edge):
    return any(s.get('kind') == 'fk' and s.get('field') in CONSOLE_LINK_FIELDS
               for s in edge.get('sources', ()))


def _device_end(edge, nodes):
    """The I/O device node of a console link."""
    for end in (edge['from'], edge['to']):
        if nodes.get(end, {}).get('kind') == 'device':
            return nodes[end]
    return {}


def on_dante(node):
    """A device the Dante tab boxes: its Console connection is Dante, or it
    has a Dante network set, or it is a comm device."""
    return node['kind'] == 'device' and (node.get('console_connection') == 'dante'
                                         or bool(node.get('dante_network'))
                                         or node.get('device_kind') == 'comm')


def unset_devices(graph):
    """I/O devices with a console link (A or B) and no Console connection
    set, in the graph's order. A device with no console link -- one used
    only for comms, or not patched yet -- has nothing the setting would
    place, so it is not listed."""
    linked = {end for e in graph['edges'] if not e.get('comm') and is_console_link(e)
              for end in (e['from'], e['to'])}
    return [n for n in graph['nodes']
            if n['kind'] == 'device' and not n.get('console_connection')
            and n.get('device_kind') != 'comm' and n['id'] in linked]


def _keep_dante(edge, nodes):
    if edge.get('comm'):
        return 'dante' in edge.get('transports', ())
    return is_console_link(edge) and _device_end(edge, nodes).get('console_connection') == 'dante'


def _keep_avb(edge, nodes):
    return 'avb' in edge.get('transports', ()) and not edge.get('comm')


def _avb_stream(edge):
    """The AVB output number an edge's links all leave from ("3"), or ''."""
    numbers = {m.group(1) if m else '' for l in edge.get('links', ())
               for m in [AVB_PORT.match(l.get('from_port') or '')]}
    return numbers.pop() if len(numbers) == 1 else ''


def _keep_analog(edge, nodes):
    transports = set(edge.get('transports', ()))
    if is_console_link(edge):
        return _device_end(edge, nodes).get('console_connection') != 'dante'
    if 'speaker' in transports:
        return False
    if transports & set(CABLE_FEEDS):
        return True
    # A processor matched by name, or a "?" match: no port, so no transport.
    return not transports and 'a' in edge.get('rules', ())


def _keep_speakers(edge, nodes):
    return 'speaker' in edge.get('transports', ())


KEEP = {DANTE: _keep_dante, AVB: _keep_avb, ANALOG: _keep_analog, SPEAKERS: _keep_speakers}


def _ip_line(node):
    ips = [f'{label} {node[key]}' for label, key in (('Pri', 'primary_ip'), ('Sec', 'secondary_ip'))
           if node.get(key)]
    return ' · '.join(ips) or 'No IP'


def _ports(edges, device_id):
    # A set: a port that is A of one channel and B of another (or of the
    # same one) is one input on the box, not two.
    refs = {l.get(f'{end}_ref') or '' for e in edges if not e.get('comm')
            for l in e.get('links', ())
            for end in ('from', 'to') if device_id in (e['from'], e['to'])}
    return {'inputs': sum(r.startswith('deviceinput:') for r in refs),
            'outputs': sum(r.startswith('deviceoutput:') for r in refs)}


KEPT_SLOTS = ('amp', 'processor')   # a console's or an I/O device's slot goes with its line


def without_network(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    edges, sources = [], {}         # (node, slot id) -> the hidden feeds' sources
    for edge in graph['edges']:
        if not edge.get('network'):
            edges.append(edge)
        elif edge.get('to_slot') and nodes.get(edge['to'], {}).get('kind') in KEPT_SLOTS:
            frm = nodes.get(edge['from'], {}).get('label', '')
            text = ' '.join(x for x in (frm, edge.get('label', '')) if x)
            sources.setdefault((edge['to'], edge['to_slot']), []).append(text)
    out_nodes = []
    for node in graph['nodes']:
        if node.get('slots') and any((node['id'], s['id']) in sources for s in node['slots']):
            slots = []
            for slot in node['slots']:
                feeds = sources.get((node['id'], slot['id']))
                if feeds and ' ← ' in slot['label']:      # an amp slot already names its source
                    slot = {**slot, 'kept': True}
                elif feeds:
                    slot = {**slot, 'label': f"{slot['label']} ← {', '.join(feeds)}", 'kept': True}
                slots.append(slot)
            node = {**node, 'slots': slots}
        out_nodes.append(node)
    kept = {e['id'] for e in edges}
    return {**graph, 'nodes': out_nodes, 'edges': edges,
            'warnings': [w for w in graph['warnings'] if w['edge'] in kept]}


def comms_notes(graph, full):
    """``graph`` with ``comms_note`` on each device whose only links are
    comms links: "2 comms patches · see Comms tab". For the Overview and the
    Dante tab, which box those devices and draw none of their lines.

    Counted per device from ``full``: one for each comms link it is an end
    of, and one for each 2-wire port with a destination. A device with any
    other link (a console, an amp, a processor) gets no note."""
    counts, others = {}, set()
    for edge in full['edges']:
        ends = (edge['from'], edge['to'])
        if edge.get('comm'):
            for end in ends:
                counts[end] = counts.get(end, 0) + len(edge.get('links', ()))
        else:
            others.update(ends)
    for node in full['nodes']:
        if node.get('two_wire'):
            counts[node['id']] = counts.get(node['id'], 0) + len(node['two_wire'])
    nodes = []
    for node in graph['nodes']:
        n = counts.get(node['id'], 0)
        if node['kind'] == 'device' and n and node['id'] not in others:
            node = {**node, 'comms_note': COMMS_NOTE.format(
                n=n, patches='comms patch' if n == 1 else 'comms patches')}
        nodes.append(node)
    return {**graph, 'nodes': nodes}


def avb_boxes(graph, full, devices):
    """The AVB tab's ``graph`` with every processor that has an AVB output
    boxed, an amp on it or not, and an IP line on each processor and amp.
    ``devices``: {'processors': node ids with an AVB output, 'ips': {node id:
    IP}} (``views_wiring.avb_devices``). Nodes stay in ``full``'s order."""
    shown = {n['id']: n for n in graph['nodes']}
    ips = devices.get('ips', {})
    nodes = []
    for node in full['nodes']:
        boxed = node['kind'] == 'processor' and node['id'] in devices.get('processors', ())
        if node['id'] not in shown and not boxed:
            continue
        node = dict(shown.get(node['id'], node))
        if node['id'] not in shown:
            # Its slots name feeds this tab does not draw.
            node.pop('slots', None)
            node.pop('out_slots', None)
        if node['kind'] in ('processor', 'amp'):
            node['lines'] = [f"IP {ips[node['id']]}" if ips.get(node['id']) else 'No IP']
        nodes.append(node)
    return {**graph, 'nodes': nodes}


def _network_groups(nodes):
    """Each device node with the Dante network header it sits under, once
    any of them has a network set."""
    spelling = {}
    for n in nodes:
        name = n.get('dante_network') or ''
        if n['kind'] == 'device' and name:
            spelling.setdefault(name.casefold(), name)
    if not spelling:
        return nodes
    out = []
    for n in nodes:
        if n['kind'] == 'device':
            key = (n.get('dante_network') or '').casefold()
            n = {**n, 'group': {'key': f'net:{key}', 'label': spelling.get(key, NO_NETWORK),
                                'order': 0 if key else None}}
        out.append(n)
    return out


def graph_view(graph, tab):
    tab = tab_or_default(tab)
    if tab == OVERVIEW:
        return graph
    if tab == COMMS:
        from planner.connections.comms_tab import comms_view
        return comms_view(graph)
    nodes = {n['id']: n for n in graph['nodes']}
    keep = KEEP[tab]
    edges = []
    for edge in graph['edges']:
        if not keep(edge, nodes):
            continue
        if tab == ANALOG and is_console_link(edge) and not _device_end(edge, nodes).get(
                'console_connection'):
            edge = {**edge, 'connection_unset': True}
        if tab == AVB and _avb_stream(edge):
            edge = {**edge, 'stream': _avb_stream(edge)}    # its trunk's name
        edges.append(edge)

    drawn = [e for e in edges if not e.get('comm')]
    used = {end for e in drawn for end in (e['from'], e['to'])}
    if tab == DANTE:
        used |= {nid for nid, n in nodes.items() if n['kind'] == 'console' or on_dante(n)}
    out_nodes = []
    for node in graph['nodes']:
        if node['id'] not in used:
            continue
        node = dict(node)
        if node['kind'] == 'device':
            # Counted from the drawn links: a device with none is one box.
            node['ports'] = _ports(edges, node['id'])
        if tab == DANTE and node['kind'] in ('console', 'device'):
            node['lines'] = [_ip_line(node)]
        out_nodes.append(node)

    if tab == DANTE:
        out_nodes = _network_groups(out_nodes)
    kept = {e['id'] for e in edges}
    return {**graph, 'nodes': out_nodes, 'edges': edges,
            'warnings': [w for w in graph['warnings'] if w['edge'] in kept]}
