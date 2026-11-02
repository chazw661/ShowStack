"""Mic Plan, PR 1: import a showflow per show day and review what was read.

Everything is the current project's: every id in a URL or form is looked up
through ``day__project`` of the session's project, so another tenant's id is
a 404. Any member may see the page; changing anything needs edit rights,
refused before the body is read. Nothing here touches Mic Tracker.

The PDF is read in memory only (``_MemoryOnlyUpload``) and dropped at the end
of the request: showflows can be under NDA and Railway's disk is ephemeral.
"""

import html
import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.core.files.uploadhandler import MemoryFileUploadHandler
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_POST

from planner.mic_plan import importer, stage
from planner.mic_plan.extract import ShowflowError
from planner.mic_plan.parser import hm
from planner.models import (
    MicPlanSettings, Presenter, ShowDay, ShowflowEvent, ShowflowImport, ShowflowPerson,
)
from planner.tenancy import can_edit_current_project, edit_rights_required_page
from planner.tenancy import current_project_or_none as _scoped_project

FLAG_LABELS = {
    'parse': 'File',
    'no_times': 'Times',
    'time_backwards': 'Times',
    'unknown_crew': 'Crew?',
    'unmatched_speaker': 'Speaker?',
    'never_caught': 'Not caught',
    'caught_but_listed': 'Still listed',
    'no_cue': 'No cue',
    'bsm_only': 'BSM only',
    'which_first': 'Which?',
    'description_names': 'Not listed',
}
_CUE_WORD = re.compile(r'(?i)\b(?:sends?|sending|catch(?:es)?|catching)\b')
SETTINGS_FIELDS = ('a2_count', 'mic_min', 'demic_min', 'premic_lead_min', 'margin_min')


def _project_or_404(request):
    project = _scoped_project(request)
    if project is None:
        raise Http404('No project.')
    return project


def _back(day=None, part=None, anchor=''):
    url = reverse('planner:mic_plan')
    query = []
    if day is not None:
        query.append('day={}'.format(day.pk))
    if part is not None:
        query.append('part={}'.format(part.pk))
    return redirect(url + ('?' + '&'.join(query) if query else '') + anchor)


def _part(request, pk, status='active'):
    return get_object_or_404(ShowflowImport, pk=pk, status=status,
                             day__project=_project_or_404(request))


def _person(request, pk):
    return get_object_or_404(ShowflowPerson, pk=pk, day__project=_project_or_404(request))


def _span(part):
    if part.span_start is None:
        return ''
    return '{}–{}'.format(hm(part.span_start), hm(part.span_end))


def _bsm_html(text, crew):
    """BSM text, escaped, with "<crew> sends/catches" marked up."""
    out = html.escape(text or '')
    if not crew or not out:
        return out
    names = '|'.join(re.escape(html.escape(c)) for c in sorted(crew, key=len, reverse=True))
    pattern = re.compile(r'(?i)\b(?:{})\s+(?:(?:to|will)\s+)?(send(?:s|ing)?|catch(?:es|ing)?)\b'
                         .format(names))

    def mark(m):
        kind = 'send' if m[1].lower().startswith('send') else 'catch'
        return '<mark class="mp-{}">{}</mark>'.format(kind, m[0])
    return pattern.sub(mark, out)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

@staff_member_required
@require_GET
def mic_plan(request):
    project = _scoped_project(request)
    if project is None:
        return redirect('planner:mic_tracker')
    days = list(ShowDay.objects.filter(project=project).order_by('date'))
    day = None
    if request.GET.get('day', '').isdigit():
        day = next((d for d in days if d.pk == int(request.GET['day'])), None)
    if day is None:
        with_imports = set(ShowflowImport.objects.filter(day__project=project, status='active')
                           .values_list('day_id', flat=True))
        day = next((d for d in days if d.pk in with_imports), days[0] if days else None)

    parts, part, rows, people, events = [], None, [], [], []
    if day is not None:
        parts = importer.active_parts(day)
        if request.GET.get('part', '').isdigit():
            part = next((p for p in parts if p.pk == int(request.GET['part'])), None)
        part = part or (parts[0] if parts else None)
        people = list(day.showflow_people.select_related('presenter'))
    if part is not None:
        rows = list(part.rows.all())
        events = list(ShowflowEvent.objects.filter(row__showflow_import=part)
                      .select_related('row', 'person'))
        events_by_row = {}
        for e in events:
            events_by_row.setdefault(e.row_id, []).append(e)
        names_by_row = {}
        for person in people:
            for o in person.flags.get('rows', {}).get(str(part.pk), []):
                names_by_row.setdefault(o, []).append(person)
        for row in rows:
            row.bsm_html = _bsm_html(row.bsm_text, part.crew_names)
            row.time_label = ('' if row.est_time is None
                              else hm(row.est_time) if row.time_exact else '≈' + hm(row.est_time))
            row.event_list = events_by_row.get(row.pk, [])
            row.people = names_by_row.get(row.order, [])
            row.people_ids = ' '.join(str(p.pk) for p in row.people)
        line_of = {r.order: stage.line_label(r) for r in rows}
        for person in people:
            person.lines = [line_of[o] for o in person.flags.get('rows', {}).get(str(part.pk), [])
                            if o in line_of]
    segments, loose_flags = stage.build(part, rows, people, events) if part else ([], [])
    flag_count = len(loose_flags) + sum(isinstance(i, stage.Flag) for s in segments for i in s.items)

    from planner.views import _shared_header_context
    return render(request, 'planner/mic_plan.html', {
        **_shared_header_context(request),
        'project': project,
        'days': days,
        'day': day,
        'parts': [{'obj': p, 'span': _span(p)} for p in parts],
        'part': part,
        'rows': rows,
        'blank_count': sum(1 for r in rows if r.is_blank),
        'people': sorted(people, key=lambda p: p.display_name.lower()),
        'people_here': sum(1 for p in people if getattr(p, 'lines', None)),
        'segments': segments,
        'loose_flags': loose_flags,
        'flag_count': flag_count,
        'flag_labels': FLAG_LABELS,
        # Crew names only matter when this file has send/catch cues to read. Not
        # "has crew names": a new part starts with the project's last ones.
        'has_cues': bool(events) or any(_CUE_WORD.search(r.bsm_text) for r in rows),
        'presenters': Presenter.objects.filter(project=project).order_by('name'),
        'mic_hint_choices': ShowflowPerson.MIC_HINT_CHOICES,
        'can_edit': can_edit_current_project(request),
        'max_pages': importer.MAX_PAGES,
        'max_mb': importer.MAX_UPLOAD_BYTES // (1024 * 1024),
    })


# --------------------------------------------------------------------------
# Upload, confirm, delete
# --------------------------------------------------------------------------

class _MemoryOnlyUpload(MemoryFileUploadHandler):
    """Keep the upload in memory whatever its size, up to the cap; past it,
    take nothing, so no temporary file is ever written to disk."""

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        self.activated = 0 < content_length <= importer.MAX_UPLOAD_BYTES + 64 * 1024


@csrf_exempt
def showflow_upload(request):
    # The upload handler has to be swapped before anything reads request.POST,
    # and the CSRF middleware would; so CSRF is checked here instead, after.
    request.upload_handlers = [_MemoryOnlyUpload(request)]
    return _showflow_upload(request)


@staff_member_required
@require_POST
@csrf_protect
@edit_rights_required_page
def _showflow_upload(request):
    project = _project_or_404(request)
    day = get_object_or_404(ShowDay, pk=request.POST.get('day') or 0, project=project)
    upload = request.FILES.get('showflow')
    too_big = int(request.META.get('CONTENT_LENGTH') or 0) > importer.MAX_UPLOAD_BYTES + 64 * 1024
    if upload is None or too_big:
        messages.error(request, 'That file is over {} MB.'.format(importer.MAX_UPLOAD_BYTES // 2**20)
                       if too_big else 'Choose a showflow PDF to import.')
        return _back(day)
    try:
        data = upload.read()
    finally:
        upload.close()
    try:
        pending = importer.stage_upload(day, data, upload.name, request.user)
    except ShowflowError as error:
        messages.error(request, str(error))
        return _back(day)
    finally:
        del data
    if not importer.active_parts(day):
        importer.confirm(pending)
        messages.success(request, 'Imported {}: {} rows.'.format(pending.source_filename,
                                                                 pending.rows.count()))
        return _back(day, pending)
    return redirect('planner:mic_plan_confirm', pk=pending.pk)


@staff_member_required
@edit_rights_required_page
def showflow_confirm(request, pk):
    pending = _part(request, pk, status='pending')
    day = pending.day
    parts = importer.active_parts(day)
    if request.method == 'POST':
        choice = request.POST.get('choice', '')
        if request.POST.get('cancel'):
            pending.delete()
            messages.info(request, 'Import cancelled; nothing changed.')
            return _back(day)
        replace = None
        if choice.startswith('replace:') and choice[8:].isdigit():
            replace = next((p for p in parts if p.pk == int(choice[8:])), None)
            if replace is None:
                raise Http404('No such part.')
        elif choice != 'add':
            messages.error(request, 'Choose replace or add.')
            return redirect('planner:mic_plan_confirm', pk=pending.pk)
        importer.confirm(pending, replace=replace)
        messages.success(request, '{} {}.'.format(
            'Replaced {} with'.format(replace.source_filename) if replace else 'Added',
            pending.source_filename))
        return _back(day, pending)
    target = importer.default_target(pending)
    from planner.views import _shared_header_context
    return render(request, 'planner/mic_plan_confirm.html', {
        **_shared_header_context(request),
        'pending': pending,
        'pending_span': _span(pending),
        'day': day,
        'parts': [{'obj': p, 'span': _span(p), 'overlap': importer.overlap(pending, p)}
                  for p in parts],
        'target': target,
    })


@staff_member_required
@require_POST
@edit_rights_required_page
def showflow_delete(request, pk):
    part = _part(request, pk)
    day, name = part.day, part.source_filename
    importer.delete_part(part)
    messages.success(request, 'Deleted {}.'.format(name))
    return _back(day)


# --------------------------------------------------------------------------
# Review edits
# --------------------------------------------------------------------------

@staff_member_required
@require_POST
@edit_rights_required_page
def showflow_crew(request, pk):
    part = _part(request, pk)
    names = request.POST.getlist('crew') + request.POST.get('add', '').split(',')
    importer.set_crew(part, names)
    messages.success(request, 'Crew names saved; send/catch cues re-read.')
    return _back(part.day, part, '#mp-crew')


@staff_member_required
@require_POST
@edit_rights_required_page
def person_save(request, pk):
    person = _person(request, pk)
    part = request.POST.get('part', '')
    presenter_id = request.POST.get('presenter', '')
    if presenter_id.isdigit():
        person.presenter = get_object_or_404(Presenter, pk=int(presenter_id),
                                             project=person.day.project)
    else:
        person.presenter = None
    hint = request.POST.get('mic_hint', '')
    if hint not in dict(ShowflowPerson.MIC_HINT_CHOICES):
        hint = ''
    if hint != person.mic_hint:
        person.mic_hint, person.mic_hint_locked = hint, True
    person.save(update_fields=['presenter', 'mic_hint', 'mic_hint_locked'])
    messages.success(request, 'Saved {}.'.format(person.display_name))
    return _back(person.day, _maybe_part(request, part), '#person-{}'.format(person.pk))


@staff_member_required
@require_POST
@edit_rights_required_page
def person_merge(request, pk):
    source = _person(request, pk)
    target_id = request.POST.get('into', '')
    target = get_object_or_404(ShowflowPerson, pk=int(target_id) if target_id.isdigit() else 0,
                               day=source.day)
    name, day = source.display_name, source.day
    importer.merge(source, target)
    messages.success(request, 'Merged {} into {}.'.format(name, target.display_name))
    return _back(day, _maybe_part(request, request.POST.get('part', '')),
                 '#person-{}'.format(target.pk))


@staff_member_required
@require_POST
@edit_rights_required_page
def person_unalias(request, pk):
    person = _person(request, pk)
    alias = request.POST.get('alias', '')
    importer.remove_alias(person, alias)
    messages.success(request, '"{}" is no longer read as {}.'.format(alias, person.display_name))
    return _back(person.day, _maybe_part(request, request.POST.get('part', '')),
                 '#person-{}'.format(person.pk))


@staff_member_required
@require_POST
@edit_rights_required_page
def mic_plan_settings(request):
    project = _project_or_404(request)
    settings_obj, _ = MicPlanSettings.objects.get_or_create(project=project)
    for name in SETTINGS_FIELDS:
        field = MicPlanSettings._meta.get_field(name)
        raw = request.POST.get(name, '')
        try:
            value = int(raw)
            for validator in field.validators:
                validator(value)
        except (ValueError, ValidationError):
            messages.error(request, '{}: enter a whole number in range.'.format(field.verbose_name))
            return _back(_maybe_day(request))
        setattr(settings_obj, name, value)
    settings_obj.save()
    messages.success(request, 'Mic Plan settings saved.')
    return _back(_maybe_day(request))


def _maybe_part(request, pk):
    if not str(pk).isdigit():
        return None
    return ShowflowImport.objects.filter(pk=int(pk), status='active',
                                         day__project=_project_or_404(request)).first()


def _maybe_day(request):
    pk = request.POST.get('day', '')
    if not pk.isdigit():
        return None
    return ShowDay.objects.filter(pk=int(pk), project=_project_or_404(request)).first()
