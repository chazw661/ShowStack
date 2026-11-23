"""Wiring Diagram: the project's connection graph drawn as one read-only SVG.

Any project role can open it; nothing on it edits anything. The graph is
inferred live (``connections.graph``), filtered to the tab in ``?view=``
(``connections.tabs``), laid out by ``connections.layout`` and drawn by
``connections.svg``, which escapes every name. Each tab is laid out on its
own; an unknown ``view`` is the Overview. On the Overview ``?network=0``
hides the AVB / Dante network feeds ("Show network feeds" off).

A label too long to draw is a key on its line ("[1]"); the Connections
table under the diagram lists each key's ends and cable.

``wiring_diagram_pdf`` draws the same tabs into one PDF (Download PDF):
``?tabs=`` the tabs to include, ``?network=0`` network feeds off,
``?paper=11x17`` or ``24x36``, ``?tz=`` the viewer's time zone for the
printed stamp. B input links are on screen only, never in the PDF. Every page names the graph's digest, shown on screen too.
"""
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET

from planner.connections import svg
from planner.connections import tabs as T
from planner.connections.graph import digest, project_graph
from planner.connections.layout import layout
from planner.tenancy import current_project_or_none as _scoped_project
from planner.views import _shared_header_context

WARNING_TITLES = {
    'ambiguous': 'Matches more than one',
    'drift': 'Label differs from the stream',
    'duplicate': 'Same name, location and IP (rename one to link its outputs)',
    'dante_network': 'Dante link between different Dante networks (cannot be routed)',
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
            'text': (' / '.join(w['networks']) if w['kind'] == 'dante_network'
                     else _text(w.get('text'))),
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


def duplicate_warning_rows(project):
    """Devices the input pickers cannot tell apart (PR 2b-3): their outputs
    read "(duplicate device)" and link nothing until one is renamed."""
    from planner.connections import amp_sources, processor_sources, sources
    groups = (sources.duplicate_warnings(amp_sources.all_sources(project))
              + sources.duplicate_warnings(processor_sources.all_sources(project)))
    rows, seen = [], set()
    for names in groups:
        key = tuple(names)
        if key not in seen:
            seen.add(key)
            rows.append({'kind': 'duplicate', 'title': WARNING_TITLES['duplicate'],
                         'edge': ' and '.join(names), 'text': '', 'candidates': []})
    return rows


TRANSPORT_NAMES = {
    'analog': 'Analogue', 'aes': 'AES', 'avb': 'AVB (network)', 'dante': 'Dante (network)',
    'madi': 'MADI', 'twinlane': 'TWINLANe', 'other': 'Other',
}


def _end(node, ports, slot=''):
    return ' · '.join(x for x in (node.get('label', ''), ports, slot) if x)


def connection_rows(graph, lay, full=None):
    """The Connections table: one row per label drawn as a key. ``full``:
    the whole project graph, for the name of a device a comms link reaches
    that this tab does not draw."""
    nodes = {n['id']: n for n in graph['nodes']}
    every = {n['id']: n for n in (full or graph)['nodes']}
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
    # Comms patch links are listed here, not drawn: keyed C1, C2 ...
    for n, edge in enumerate((e for e in graph['edges'] if e.get('comm')), 1):
        transport = ', '.join(TRANSPORT_NAMES.get(t, t) for t in edge.get('transports', ()))
        cable = ' · '.join([transport] + edge.get('cable_types', []))
        rows.append({
            'key': f'C{n}',
            'from': _end(every.get(edge['from'], {}), edge.get('from_ports', '')),
            'to': _end(every.get(edge['to'], {}), edge.get('to_ports', '')),
            'cable': f'{cable} · see the Comms tab',
        })
    return rows


TAB_EMPTY = {
    T.DANTE: 'No console or Dante I/O device yet. Set Console connection to Dante on an '
             'I/O device page.',
    T.ANALOG: 'No analogue or AES feed and no non-Dante console link yet.',
    T.SPEAKERS: 'No PA cable runs yet. Add them on the PA Cable Schedule.',
    T.COMMS: 'No comm device yet. Add one on the Devices page ("Add comm device").',
}


def unset_banner(graph, tab):
    """The Dante and Analog tabs list the I/O devices that have a console
    link and no Console connection set, each linking to its device page."""
    if tab not in (T.DANTE, T.ANALOG):
        return []
    return [{'name': n['label'],
             'url': reverse('admin:planner_device_change', args=[n['id'].split(':', 1)[1]])}
            for n in T.unset_devices(graph)]


def tab_view(project, full, tab, network=True):
    """One tab of the project's graph, laid out, with its tables: what the
    page and the PDF both draw."""
    graph = T.graph_view(full, tab)
    if tab in (T.OVERVIEW, T.DANTE):
        graph = T.comms_notes(graph, full)
    hidden_network = 0
    if tab == T.OVERVIEW and not network:
        hidden_network = sum(bool(e.get('network')) for e in graph['edges'])
        graph = T.without_network(graph)
    lay = layout(graph, **T.layout_options(tab))
    edges = graph['edges']
    return {
        'tab': tab,
        'tab_label': dict(T.TABS)[tab],
        'graph': graph,
        'layout': lay,
        'hidden_network': hidden_network,
        'tab_empty': bool(full['nodes']) and not graph['nodes'] and not graph['edges'],
        'tab_empty_text': TAB_EMPTY.get(tab, ''),
        'show_unset_legend': any(e.get('connection_unset') for e in edges),
        'show_b_legend': any(e.get('b') for e in edges),
        'connections': connection_rows(graph, lay, full),
        'warnings': warnings_for(graph, lay) + duplicate_warning_rows(project),
        'counts': {
            'boxes': len(lay.boxes),
            'edges': len(edges),
            'confirmed': sum(e['status'] == 'confirmed' and not e['unlinked'] for e in edges),
            'inferred': sum(e['status'] == 'inferred' and not e['unlinked'] for e in edges),
            'unlinked': sum(bool(e['unlinked']) for e in edges),
        },
    }


@staff_member_required
@require_GET
def wiring_diagram(request):
    context = {'title': 'Wiring Diagram', **_shared_header_context(request)}
    project = _scoped_project(request)
    if project is None:
        return render(request, 'planner/wiring_diagram.html', {**context, 'no_project': True})
    tab = T.tab_or_default(request.GET.get('view'))
    full = project_graph(project)
    network = request.GET.get('network') != '0'
    view = tab_view(project, full, tab, network)
    context.update({
        'project': project,
        'tab': tab,
        'tabs': [{'key': key, 'label': label, 'active': key == tab} for key, label in T.TABS],
        'unset': unset_banner(full, tab),
        'tab_empty': view['tab_empty'],
        'tab_empty_text': view['tab_empty_text'],
        'show_unset_legend': view['show_unset_legend'],
        'show_b_legend': view['show_b_legend'],
        'network_toggle': tab == T.OVERVIEW,
        'network': network,
        'hidden_network': view['hidden_network'],
        'connections': view['connections'],
        # svg.render escapes every name it draws.
        'svg': mark_safe(svg.render(view['layout'],
                                    title=f"Wiring diagram: {project.name} — {view['tab_label']}")),
        'warnings': view['warnings'],
        'counts': view['counts'],
        'digest': digest(full),
        'empty': not full['nodes'],
        'pdf_url': reverse('planner:wiring_diagram_pdf'),
        'papers': PAPERS,
    })
    return render(request, 'planner/wiring_diagram.html', context)


PAPERS = (('11x17', '11 × 17 in'), ('24x36', '24 × 36 in'))


def _zone(request):
    """The viewer's time zone from ``?tz=`` (the panel's script fills it
    in from the browser); UTC when absent or unknown."""
    try:
        return ZoneInfo(request.GET.get('tz', '') or 'UTC')
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _tabs(request):
    """The tabs asked for, in the page's order; all four when none is."""
    asked = {t.strip() for value in request.GET.getlist('tabs') for t in value.split(',')
             if t.strip()}
    chosen = [key for key in T.TAB_KEYS if key in asked]
    return chosen or list(T.TAB_KEYS)


@staff_member_required
@require_GET
def wiring_diagram_pdf(request):
    from planner.utils.pdf_exports.wiring_pdf import build_wiring_pdf

    project = _scoped_project(request)
    if project is None:
        return redirect('planner:wiring_diagram')
    paper = request.GET.get('paper') if request.GET.get('paper') in dict(PAPERS) else PAPERS[0][0]
    network = request.GET.get('network') != '0'
    zone = _zone(request)
    full = project_graph(project)
    # B input links stay on screen only: the PDF leaves them out (the digest
    # is still the whole graph's, so it matches the screen).
    printed = T.without_b(full)
    views = [tab_view(project, printed, tab, network) for tab in _tabs(request)]
    pdf = build_wiring_pdf(project=project, views=views, digest=digest(full), paper=paper,
                           printed=timezone.now().astimezone(zone), empty=not full['nodes'])
    response = HttpResponse(pdf, content_type='application/pdf')
    name = f'Wiring Diagram - {project.name} - {date.today().isoformat()}.pdf'
    response['Content-Disposition'] = content_disposition_header(True, name)
    return response
