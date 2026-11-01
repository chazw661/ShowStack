"""Help pages.

Tenant safety is structural, not a filter: nothing here reads the session's
project, and every template is rendered *without* the request, so no context
processor (``user_projects``, ``current_project`` ...) runs and no project data
can reach the page. Login is still required -- LoginRequiredMiddleware covers
these views like any other.
"""

from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from planner.tutorials import tutorial

from .context import topics_for
from .topics import SECTIONS, TOPICS, TOPICS_BY_SLUG


def _body(topic):
    # Fragments are static HTML written by us; render them with an empty
    # context so a stray variable could never pull in request data.
    return mark_safe(render_to_string(topic.template))


def _entry(topic):
    return {'topic': topic, 'body': _body(topic), 'video': tutorial(topic.video)}


def help_index(request):
    key = request.GET.get('for', '')
    here = topics_for(key)
    sections = []
    for section in SECTIONS:
        entries = [_entry(t) for t in TOPICS if t.section == section]
        if entries:
            sections.append({'name': section, 'entries': entries})
    html = render_to_string('help/index.html', {
        'here': [_entry(t) for t in here],
        'sections': sections,
        'topic_count': len(TOPICS),
    })
    return HttpResponse(html)


def help_topic(request, slug):
    topic = TOPICS_BY_SLUG.get(slug)
    if topic is None:
        raise Http404('No such help topic')
    related = [t for t in TOPICS if t.section == topic.section and t.slug != topic.slug]
    html = render_to_string('help/topic.html', {
        'topic': topic,
        'body': _body(topic),
        'video': tutorial(topic.video),
        'related': related,
    })
    return HttpResponse(html)
