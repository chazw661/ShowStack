"""Wiring Diagram: the project's connection graph drawn as one read-only SVG.

Any project role can open it; nothing on it edits anything. The graph is
inferred live (``connections.graph``), laid out by ``connections.layout`` and
drawn by ``connections.svg``, which escapes every name.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET

from planner.connections import svg
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


@staff_member_required
@require_GET
def wiring_diagram(request):
    context = {'title': 'Wiring Diagram', **_shared_header_context(request)}
    project = _scoped_project(request)
    if project is None:
        return render(request, 'planner/wiring_diagram.html', {**context, 'no_project': True})
    graph = project_graph(project)
    lay = layout(graph)
    edges = graph['edges']
    context.update({
        'project': project,
        # svg.render escapes every name it draws.
        'svg': mark_safe(svg.render(lay, title=f'Wiring diagram: {project.name}')),
        'warnings': warnings_for(graph, lay),
        'counts': {
            'boxes': len(lay.boxes),
            'edges': len(edges),
            'confirmed': sum(e['status'] == 'confirmed' and not e['unlinked'] for e in edges),
            'inferred': sum(e['status'] == 'inferred' and not e['unlinked'] for e in edges),
            'unlinked': sum(bool(e['unlinked']) for e in edges),
        },
        'empty': not graph['nodes'],
    })
    return render(request, 'planner/wiring_diagram.html', context)
