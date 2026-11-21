"""Wiring Diagram: the project's connection graph drawn as one read-only SVG.

Any project role can open it; nothing on it edits anything. The graph is
inferred live (``connections.graph``), filtered to the tab in ``?view=``
(``connections.tabs``), laid out by ``connections.layout`` and drawn by
``connections.svg``, which escapes every name. Each tab is laid out on its
own; an unknown ``view`` is the Overview. On the Overview ``?network=0``
hides the AVB / Dante network feeds ("Show network feeds" off).

A label too long to draw is a key on its line ("[1]"); the Connections
table under the diagram lists each key's ends and cable.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET

from planner.connections import svg
from planner.connections import tabs as T
from planner.connections.graph import project_graph
from planner.connections.layout import layout
from planner.tenancy import current_project_or_none as _scoped_project
from planner.views import _shared_header_context

WARNING_TITLES = {
    'ambiguous': 'Matches more than one',
    'drift': 'Label differs from the stream',
}


def _candidate(candidate, labels):
    name = labels.get(candidate['node'], candidate['node'])
    return f"{name} {candidate['port']}" if candidate.get('port') else name


def _text(text):
    texts = text if isinstance(text, list) else [text] if text else []
    for t in texts:
        value = (t.get('source') or t.get('destination') or '').strip()
        if value:
            return value
    return ''


def warnings_for(graph, lay):
    """The panel's rows: ambiguous and drift matches, then edges not drawn."""
    labels = {n['id']: n['label'] for n in graph['nodes']}
    edges = {e['id']: e for e in graph['edges']}
    rows = []
    for w in graph['warnings']:
        edge = edges[w['edge']]
        rows.append({
            'kind': w['kind'],
            'title': WARNING_TITLES.get(w['kind'], w['kind']),
            'edge': f"{labels.get(edge['from'], edge['from'])} → {labels.get(edge['to'], edge['to'])}",
            'text': _text(w.get('text')),
            'candidates': [_candidate(c, labels) for c in w.get('candidates', ())],
        })
    for edge_id in lay.not_drawn:
        edge = edges[edge_id]
        rows.append({
            'kind': 'not_drawn', 'title': 'Not drawn (runs right to left)',
            'edge': f"{labels.get(edge['from'], edge['from'])} → {labels.get(edge['to'], edge['to'])}",
            'text': edge.get('label', ''), 'candidates': [],
        })
    return rows


TRANSPORT_NAMES = {
    'analog': 'Analogue', 'aes': 'AES', 'avb': 'AVB (network)', 'dante': 'Dante (network)',
    'madi': 'MADI', 'twinlane': 'TWINLANe', 'other': 'Other',
}


def _end(node, ports, slot=''):
    return ' · '.join(x for x in (node.get('label', ''), ports, slot) if x)


def connection_rows(graph, lay):
    """The Connections table: one row per label drawn as a key."""
    nodes = {n['id']: n for n in graph['nodes']}
    edges = {e['id']: e for e in graph['edges']}
    rows = []
    for key, edge_id in lay.keys:
        edge = edges[edge_id]
        to = nodes.get(edge['to'], {})
        slot = next((s['label'] for s in to.get('slots', ()) if s['id'] == edge.get('to_slot')), '')
        transports = edge.get('transports', ())
        if 'speaker' in transports:
            cable = '; '.join(edge.get('label_lines') or [edge.get('label', '')])
        else:
            cable = ', '.join(TRANSPORT_NAMES.get(t, t) for t in transports) or 'Not known'
        rows.append({
            'key': key,
            'from': _end(nodes.get(edge['from'], {}), edge.get('from_ports', '')),
            'to': _end(to, edge.get('to_ports', ''), slot),
            'cable': cable,
        })
    return rows


TAB_EMPTY = {
    T.DANTE: 'No console or Dante I/O device yet. Set Console connection to Dante on an '
             'I/O device page.',
    T.ANALOG: 'No analogue or AES feed and no non-Dante console link yet.',
    T.SPEAKERS: 'No PA cable runs yet. Add them on the PA Cable Schedule.',
}


def unset_banner(graph, tab):
    """The Dante and Analog tabs list the I/O devices with no Console
    connection set, each linking to its device page."""
    if tab not in (T.DANTE, T.ANALOG):
        return []
    return [{'name': n['label'],
             'url': reverse('admin:planner_device_change', args=[n['id'].split(':', 1)[1]])}
            for n in T.unset_devices(graph)]


@staff_member_required
@require_GET
def wiring_diagram(request):
    context = {'title': 'Wiring Diagram', **_shared_header_context(request)}
    project = _scoped_project(request)
    if project is None:
        return render(request, 'planner/wiring_diagram.html', {**context, 'no_project': True})
    tab = T.tab_or_default(request.GET.get('view'))
    full = project_graph(project)
    graph = T.graph_view(full, tab)
    network = request.GET.get('network') != '0'
    hidden_network = 0
    if tab == T.OVERVIEW and not network:
        hidden_network = sum(bool(e.get('network')) for e in graph['edges'])
        graph = T.without_network(graph)
    lay = layout(graph, **T.layout_options(tab))
    edges = graph['edges']
    tab_label = dict(T.TABS)[tab]
    context.update({
        'project': project,
        'tab': tab,
        'tabs': [{'key': key, 'label': label, 'active': key == tab} for key, label in T.TABS],
        'unset': unset_banner(full, tab),
        'tab_empty': bool(full['nodes']) and not graph['nodes'],
        'tab_empty_text': TAB_EMPTY.get(tab, ''),
        'show_unset_legend': any(e.get('connection_unset') for e in edges),
        'network_toggle': tab == T.OVERVIEW,
        'network': network,
        'hidden_network': hidden_network,
        'connections': connection_rows(graph, lay),
        # svg.render escapes every name it draws.
        'svg': mark_safe(svg.render(lay, title=f'Wiring diagram: {project.name} — {tab_label}')),
        'warnings': warnings_for(graph, lay),
        'counts': {
            'boxes': len(lay.boxes),
            'edges': len(edges),
            'confirmed': sum(e['status'] == 'confirmed' and not e['unlinked'] for e in edges),
            'inferred': sum(e['status'] == 'inferred' and not e['unlinked'] for e in edges),
            'unlinked': sum(bool(e['unlinked']) for e in edges),
        },
        'empty': not full['nodes'],
    })
    return render(request, 'planner/wiring_diagram.html', context)
