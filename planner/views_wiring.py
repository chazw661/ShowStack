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
printed stamp. B input links are drawn there as on screen: lighter, labelled
"(B)". Every page names the graph's digest, shown on screen too.

``wiring_diagram_dxf`` (Download DXF, for Vectorworks) writes one ``.dxf``
per chosen tab, each the whole tab in one drawing (``connections.dxf``); a
zip when more than one tab is asked for. Same ``?tabs=``, ``?network=`` and
``?tz=``; ``?arrows=ascii`` writes "<-" / "->" for the arrows. Its layers
(Vectorworks classes) are named from ``?prefix=`` ("Audio-Wiring") and
``?classes=split|single``, kept per project in the session; a ``.dxf`` is
named for its tab, never its project.

Both downloads leave the network feeds out unless ``?network=1`` (the
panel's box, unticked by default); the screen's own toggle is unchanged.
The panel shows how many diagram pages each tab is at each paper size
(``download_hints``, from ``connections.tiling``).
"""
import io
import re
import zipfile
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
from planner.connections.layout import STREAM_COLOURS, layout
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
        slot = ''
        if to.get('kind') in ('amp', 'processor'):      # elsewhere the slot is the ports again
            slot = next((s['label'] for s in to.get('slots', ())
                         if s['id'] == edge.get('to_slot')), '')
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
    T.AVB: 'No AVB stream yet. Add AVB outputs on a processor page, then pick them in the '
           'amps\' AVB Stream fields.',
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


def avb_devices(project):
    """What the AVB tab reads that the project graph does not hold:
    {'processors': the node ids of processors with an AVB output, 'ips':
    {node id: IP} of every processor and amp that has one}."""
    from planner.connections import endpoints as ep
    from planner.models import Amp, GalaxyOutput, P1Output, SystemProcessor

    processors = set()
    for model, owner in ((P1Output, 'p1_processor'), (GalaxyOutput, 'galaxy_processor')):
        pks = (model.objects.filter(**{f'{owner}__system_processor__project': project,
                                       'output_type': 'AVB'})
               .values_list(f'{owner}__system_processor_id', flat=True).distinct())
        processors.update(ep.node_id(ep.PROCESSOR, pk) for pk in pks)
    ips = {}
    for model, kind in ((SystemProcessor, ep.PROCESSOR), (Amp, ep.AMP)):
        for pk, ip in model.objects.filter(project=project).values_list('pk', 'ip_address'):
            if ip:
                ips[ep.node_id(kind, pk)] = ip
    return {'processors': processors, 'ips': ips}


def stream_legend(lay):
    """What the page's legend shows of a tab drawn as trunks: the first
    trunk's name and colour; None on any other tab."""
    if not lay.trunks:
        return None
    return {'label': lay.trunks[0].label, 'colour': STREAM_COLOURS[lay.trunks[0].colour]}


def tab_layout(full, tab, network=True, avb=None):
    """(graph, layout, network feeds hidden) of one tab: no queries.
    ``avb``: ``avb_devices(project)``, for the AVB tab."""
    graph = T.graph_view(full, tab)
    if tab in (T.OVERVIEW, T.DANTE):
        graph = T.comms_notes(graph, full)
    if tab == T.AVB:
        graph = T.avb_boxes(graph, full, avb or {})
    hidden_network = 0
    if tab == T.OVERVIEW and not network:
        hidden_network = sum(bool(e.get('network')) for e in graph['edges'])
        graph = T.without_network(graph)
    return graph, layout(graph, **T.layout_options(tab)), hidden_network


def tab_view(project, full, tab, network=True, avb=None):
    """One tab of the project's graph, laid out, with its tables: what the
    page, the PDF and the DXF all draw. ``avb``: ``avb_devices(project)``
    when the caller already has it (read here otherwise, for the AVB tab)."""
    if tab == T.AVB and avb is None:
        avb = avb_devices(project)
    graph, lay, hidden_network = tab_layout(full, tab, network, avb)
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
    from planner.connections.dxf import MAX_PREFIX, MODES

    context = {'title': 'Wiring Diagram', **_shared_header_context(request)}
    project = _scoped_project(request)
    if project is None:
        return render(request, 'planner/wiring_diagram.html', {**context, 'no_project': True})
    tab = T.tab_or_default(request.GET.get('view'))
    full = project_graph(project)
    network = request.GET.get('network') != '0'
    avb = avb_devices(project)
    view = tab_view(project, full, tab, network, avb)
    hints = download_hints(full, avb)
    dxf_prefix, dxf_mode = dxf_classes(request, project)
    context.update({
        'dxf_prefix': dxf_prefix,
        'dxf_mode': dxf_mode,
        'dxf_modes': MODES,
        'dxf_prefix_max': MAX_PREFIX,
        'project': project,
        'tab': tab,
        'tabs': [{'key': key, 'label': label, 'active': key == tab, 'pages': hints['tabs'][key]}
                 for key, label in T.TABS],
        'page_suggestion': hints['suggestion'],
        'many_pages': MANY_PAGES,
        'dxf_url': reverse('planner:wiring_diagram_dxf'),
        'unset': unset_banner(full, tab),
        'tab_empty': view['tab_empty'],
        'tab_empty_text': view['tab_empty_text'],
        'show_unset_legend': view['show_unset_legend'],
        'show_b_legend': view['show_b_legend'],
        'stream_legend': stream_legend(view['layout']),
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
MANY_PAGES = 4          # a tab over this many diagram pages at 11 x 17: suggest 24 x 36


def pages_text(n):
    return 'nothing to draw' if not n else f"{n} diagram page{'' if n == 1 else 's'}"


def suggestion_text(labels_and_pages):
    """The panel's hint for the tabs over MANY_PAGES at 11 x 17; '' for none.
    The panel's script builds the same sentence when a box changes."""
    return ' '.join(f'{label} is {n} diagram pages at 11 × 17. Try 24 × 36.'
                    for label, n in labels_and_pages if n > MANY_PAGES)


def download_hints(full, avb=None):
    """How many pages each tab's diagram takes in the PDF, per paper size
    (``tiling.plan``; the Connections table and Warnings come after, on
    pages of their own). {'tabs': {tab: {'text', 'counts'}}, 'suggestion'}:
    ``counts`` is [(key, n)] with key "<paper>-<network 0/1>", for the
    panel's script; ``text`` and ``suggestion`` are the panel as it opens:
    11 x 17, network feeds off."""
    from planner.utils.pdf_exports.wiring_pdf import diagram_pages

    tabs, first = {}, []
    for tab, label in T.TABS:
        by_network = {}
        for network in (0, 1):
            if network and tab != T.OVERVIEW:       # only the Overview has the feeds
                by_network[1] = by_network[0]
                continue
            graph, lay, _ = tab_layout(full, tab, bool(network), avb)
            drawn = bool(lay.boxes) and bool(graph['nodes'] or graph['edges'])
            by_network[network] = [diagram_pages(lay, paper) if drawn else 0 for paper, _ in PAPERS]
        counts = [(f'{paper}-{network}', by_network[network][i])
                  for network in (0, 1) for i, (paper, _) in enumerate(PAPERS)]
        tabs[tab] = {'text': pages_text(counts[0][1]), 'counts': counts}
        first.append((label, counts[0][1]))
    return {'tabs': tabs, 'suggestion': suggestion_text(first)}


def _download_network(request):
    """Network feeds in a download: only when asked for (``network=1``)."""
    return request.GET.get('network') == '1'


_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]+|\.{2,}')


def file_part(text, fallback='project'):
    """``text`` as part of a file name: no path separators, no control
    characters, no leading dots; never empty."""
    name = _UNSAFE_NAME.sub('-', str(text or '')).strip(' .-')[:80].strip(' .-')
    return name or fallback


def _zone(request):
    """The viewer's time zone from ``?tz=`` (the panel's script fills it
    in from the browser); UTC when absent or unknown."""
    try:
        return ZoneInfo(request.GET.get('tz', '') or 'UTC')
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _tabs(request):
    """The tabs asked for, in the page's order; every tab when none is."""
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
    network = _download_network(request)
    zone = _zone(request)
    full = project_graph(project)
    views = [tab_view(project, full, tab, network) for tab in _tabs(request)]
    pdf = build_wiring_pdf(project=project, views=views, digest=digest(full), paper=paper,
                           printed=timezone.now().astimezone(zone), empty=not full['nodes'])
    response = HttpResponse(pdf, content_type='application/pdf')
    name = f'Wiring Diagram - {project.name} - {date.today().isoformat()}.pdf'
    response['Content-Disposition'] = content_disposition_header(True, name)
    return response


DXF_TYPE = 'image/vnd.dxf'
DXF_CLASSES_KEY = 'wiring_dxf_classes'      # session: {project pk: [prefix, mode]}


def dxf_classes(request, project):
    """(prefix, mode) for the DXF's layer names: what the request asks for,
    else what this project's last download used (kept in the session), else
    the defaults. Always clean: the prefix is the only typed text that ever
    reaches a layer name."""
    from planner.connections.dxf import DEFAULT_PREFIX, SPLIT, clean_mode, clean_prefix

    kept = (request.session.get(DXF_CLASSES_KEY) or {}).get(str(project.pk)) or ()
    prefix, mode = kept if len(kept) == 2 else (DEFAULT_PREFIX, SPLIT)
    if 'prefix' in request.GET:
        prefix = request.GET['prefix']
    if 'classes' in request.GET:
        mode = request.GET['classes']
    return clean_prefix(prefix), clean_mode(mode)


def _remember_dxf_classes(request, project, prefix, mode):
    kept = dict(request.session.get(DXF_CLASSES_KEY) or {})
    if kept.get(str(project.pk)) != [prefix, mode]:
        kept[str(project.pk)] = [prefix, mode]
        request.session[DXF_CLASSES_KEY] = kept


@staff_member_required
@require_GET
def wiring_diagram_dxf(request):
    from planner.connections.dxf import ARROWS_ASCII, build_tab_dxf
    from planner.utils.pdf_exports.mic_plan_pdf import stamp

    project = _scoped_project(request)
    if project is None:
        return redirect('planner:wiring_diagram')
    zone = _zone(request)
    arrows = ARROWS_ASCII if request.GET.get('arrows') == ARROWS_ASCII else ''
    full = project_graph(project)
    graph_digest = digest(full)
    printed = stamp(timezone.now().astimezone(zone), zone)
    prefix, mode = dxf_classes(request, project)
    _remember_dxf_classes(request, project, prefix, mode)
    # A .dxf is named for its tab only. Vectorworks offers the file's name as
    # a prefix for the classes it imports, so a project named for its venue
    # would end up in class names; the project is in the title block and in
    # the zip's name.
    today = date.today().isoformat()
    files = []
    for tab in _tabs(request):
        view = tab_view(project, full, tab, _download_network(request))
        data = build_tab_dxf(project_name=project.name, view=view, digest=graph_digest,
                             printed=printed, arrows=arrows, empty=not full['nodes'],
                             prefix=prefix, mode=mode)
        files.append((f"Wiring Diagram - {file_part(view['tab_label'])} - {today}.dxf", data))
    if len(files) == 1:
        name, data = files[0]
        response = HttpResponse(data, content_type=DXF_TYPE)
    else:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file_name, data in files:
                archive.writestr(file_name, data)
        name = f'Wiring Diagram - {file_part(project.name)} - DXF - {today}.zip'
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = content_disposition_header(True, name)
    return response
