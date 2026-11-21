"""The Wiring Diagram's tabs: one project graph, filtered per view. Pure.

``graph_view(graph, tab)`` takes ``graph.project_graph()``'s dict and returns
a dict of the same shape holding only what that tab draws, for ``layout`` to
lay out on its own. Each tab is laid out independently, so a later PDF can
draw each as its own section.

  overview   everything
  dante      every console, every I/O device whose Console connection is
             Dante, and their console links. Boxes carry the IP Address
             Manager's primary / secondary IP (``lines``).
  analog     analog and AES feeds (I/O or console -> processor -> amp, I/O
             -> amp, their unlinked feeds and "?" matches) and every console
             link that is not Dante. A console link whose device has no
             Console connection set is kept and flagged ``connection_unset``.
  speakers   PA cable runs only: amps and racks -> speakers.

Only the nodes an edge reaches are kept (Dante also keeps its devices with
no link yet). An I/O device's ``ports`` are counted from the kept edges, so
it gets only the inputs / outputs box the tab uses.

``without_network(graph)`` is the Overview with "Show network feeds" off:
no AVB / Dante network edges. An amp or processor slot one fed stays on its
box, named with its source ("AVB 1 ← P1 AVB 3"), so the box still says what
plugs in where.
"""

OVERVIEW, DANTE, ANALOG, SPEAKERS = 'overview', 'dante', 'analog', 'speakers'
TABS = (
    (OVERVIEW, 'Overview'),
    (DANTE, 'Dante'),
    (ANALOG, 'Analogue/AES'),
    (SPEAKERS, 'Speaker cables'),
)
TAB_KEYS = tuple(key for key, _ in TABS)
CONSOLE_LINK_FIELDS = ('DeviceInput.console_input', 'DeviceOutput.console_output')
CABLE_FEEDS = ('analog', 'aes')
SPEAKER_LABEL_MAX = 560     # two or three columns: room for the whole cable label


def tab_or_default(value):
    return value if value in TAB_KEYS else OVERVIEW


def layout_options(tab):
    """``layout()`` keyword arguments for a tab: the Overview keeps its
    columns (Processors and Unlinked feeds hide when empty); a tab hides
    every column it does not use."""
    from planner.connections.layout import ALL_COLUMNS
    if tab == OVERVIEW:
        return {}
    options = {'hide_empty': ALL_COLUMNS}
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


def unset_devices(graph):
    """I/O devices with no Console connection set, in the graph's order."""
    return [n for n in graph['nodes']
            if n['kind'] == 'device' and not n.get('console_connection')]


def _keep_dante(edge, nodes):
    return is_console_link(edge) and _device_end(edge, nodes).get('console_connection') == 'dante'


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


KEEP = {DANTE: _keep_dante, ANALOG: _keep_analog, SPEAKERS: _keep_speakers}


def _ip_line(node):
    ips = [f'{label} {node[key]}' for label, key in (('Pri', 'primary_ip'), ('Sec', 'secondary_ip'))
           if node.get(key)]
    return ' · '.join(ips) or 'No IP'


def _ports(edges, device_id):
    refs = [l.get(f'{end}_ref') or '' for e in edges for l in e.get('links', ())
            for end in ('from', 'to') if device_id in (e['from'], e['to'])]
    return {'inputs': sum(r.startswith('deviceinput:') for r in refs),
            'outputs': sum(r.startswith('deviceoutput:') for r in refs)}


def without_network(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    edges, sources = [], {}         # (node, slot id) -> the hidden feeds' sources
    for edge in graph['edges']:
        if not edge.get('network'):
            edges.append(edge)
        elif edge.get('to_slot'):
            frm = nodes.get(edge['from'], {}).get('label', '')
            text = ' '.join(x for x in (frm, edge.get('label', '')) if x)
            sources.setdefault((edge['to'], edge['to_slot']), []).append(text)
    out_nodes = []
    for node in graph['nodes']:
        if node.get('slots') and any((node['id'], s['id']) in sources for s in node['slots']):
            slots = []
            for slot in node['slots']:
                feeds = sources.get((node['id'], slot['id']))
                if feeds:
                    slot = {**slot, 'label': f"{slot['label']} ← {', '.join(feeds)}", 'kept': True}
                slots.append(slot)
            node = {**node, 'slots': slots}
        out_nodes.append(node)
    kept = {e['id'] for e in edges}
    return {**graph, 'nodes': out_nodes, 'edges': edges,
            'warnings': [w for w in graph['warnings'] if w['edge'] in kept]}


def graph_view(graph, tab):
    tab = tab_or_default(tab)
    if tab == OVERVIEW:
        return graph
    nodes = {n['id']: n for n in graph['nodes']}
    keep = KEEP[tab]
    edges = []
    for edge in graph['edges']:
        if not keep(edge, nodes):
            continue
        if tab == ANALOG and is_console_link(edge) and not _device_end(edge, nodes).get(
                'console_connection'):
            edge = {**edge, 'connection_unset': True}
        edges.append(edge)

    used = {end for e in edges for end in (e['from'], e['to'])}
    if tab == DANTE:
        used |= {nid for nid, n in nodes.items()
                 if n['kind'] == 'console'
                 or (n['kind'] == 'device' and n.get('console_connection') == 'dante')}
    out_nodes = []
    for node in graph['nodes']:
        if node['id'] not in used:
            continue
        node = dict(node)
        if node['kind'] == 'device' and any(node['id'] in (e['from'], e['to']) for e in edges):
            node['ports'] = _ports(edges, node['id'])
        if tab == DANTE and node['kind'] in ('console', 'device'):
            node['lines'] = [_ip_line(node)]
        out_nodes.append(node)

    kept = {e['id'] for e in edges}
    return {**graph, 'nodes': out_nodes, 'edges': edges,
            'warnings': [w for w in graph['warnings'] if w['edge'] in kept]}
