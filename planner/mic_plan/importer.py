"""Save a parsed showflow, and keep a day's people and events in step.

An upload is parsed once, in the request, and saved as a *pending* import
with its rows; the PDF goes no further. The user then confirms whether it
replaces an existing part of the day or adds a new one (the default is
decided by time overlap). Every change after that -- confirm, delete, crew
names, a merge -- ends in ``rebuild_day``, which re-runs the parser over the
stored rows of every part and reconciles the day's people with what it found.
"""

import logging
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from planner.models import (
    Presenter, ShowflowEvent, ShowflowImport, ShowflowPerson, ShowflowRow,
)

from .extract import ShowflowError, extract
from .parser import analyse, name_key

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# pdfplumber is nearly all of an import. On Railway a 19-page showflow read in
# 0.77 s (the INFO timing log), about 0.04 s a page, so 60 pages is a few
# seconds; empty grid pages are skipped (extract._only_line_numbers), and
# extract.TIME_BUDGET_S stops any file at 15 s whatever its page count.
MAX_PAGES = 60
STALE_PENDING = timedelta(hours=6)


def _minute(value):
    return None if value is None else max(0, min(round(value), 24 * 60 - 1))


def project_crew(project):
    """Crew names of the project's most recent import, or None."""
    last = (ShowflowImport.objects.filter(day__project=project, status='active')
            .exclude(crew_names=[]).order_by('-imported_at').first())
    return list(last.crew_names) if last else None


def stage_upload(day, data, filename, user):
    """Parse ``data`` and save it as a pending import of ``day``.

    Raises ShowflowError with a message for the user if it cannot be read.
    """
    ShowflowImport.objects.filter(status='pending',
                                  imported_at__lt=timezone.now() - STALE_PENDING).delete()
    started = time.monotonic()
    rows, columns, warnings, pages = extract(data, max_pages=MAX_PAGES)
    extracted = time.monotonic()
    if not rows:
        raise ShowflowError('Found the column header but no rows under it.')
    crew = project_crew(day.project)
    known = [(p.display_name, p.aliases) for p in day.showflow_people.all()]
    result = analyse(rows, crew=crew, known=known)
    # No file name: showflows can be under NDA.
    logger.info('Mic Plan import: %d pages, %d rows, extract %.2fs, parse %.2fs '
                '(project %s, day %s)', pages, len(rows), extracted - started,
                time.monotonic() - extracted, day.project_id, day.pk)
    with transaction.atomic():
        imp = ShowflowImport.objects.create(
            day=day, status='pending', source_filename=filename[:255], imported_by=user,
            page_count=pages, detected_columns=columns, crew_names=result.crew,
            warnings=[{'kind': 'parse', 'text': w, 'row_order': None, 'person': None}
                      for w in warnings],
            span_start=_minute(result.span[0]), span_end=_minute(result.span[1]),
        )
        ShowflowRow.objects.bulk_create([
            ShowflowRow(
                showflow_import=imp, order=i, page_no=row['page_no'], line_no=row['line'][:20],
                start_text=row['start'][:50], end_text=row['end'][:50],
                duration_text=row['duration'][:50], description=row['description'],
                speaker_text=row['speaker'], bsm_text=row['bsm'], notes_text=row['notes'],
                is_segment=t.is_segment, segment_t0=_minute(t.t0), segment_t1=_minute(t.t1),
                est_time=_minute(t.minute), time_exact=t.exact,
            ) for i, (row, t) in enumerate(zip(rows, result.times))
        ])
    return imp


def overlap(a, b):
    """Minutes two imports' spans share (0 if either has no span)."""
    if None in (a.span_start, a.span_end, b.span_start, b.span_end):
        return 0
    return max(0, min(a.span_end, b.span_end) - max(a.span_start, b.span_start))


def default_target(pending):
    """The part of the day ``pending`` most overlaps in time, or None (= add)."""
    parts = active_parts(pending.day)
    best = max(parts, key=lambda p: overlap(pending, p), default=None)
    return best if best is not None and overlap(pending, best) > 0 else None


def active_parts(day):
    return list(day.showflow_imports.filter(status='active').order_by('part_order', 'id'))


def _renumber(day):
    parts = sorted(active_parts(day), key=lambda p: (p.span_start is None, p.span_start or 0, p.id))
    for n, part in enumerate(parts):
        if part.part_order != n:
            part.part_order = n
            part.save(update_fields=['part_order'])


@transaction.atomic
def confirm(pending, replace=None):
    """Make ``pending`` live, replacing part ``replace`` of the same day if given."""
    if replace is not None:
        if replace.day_id != pending.day_id or replace.status != 'active':
            raise ValueError('Not a part of this day.')
        if replace.crew_names:
            pending.crew_names = replace.crew_names
        replace.delete()
    pending.status = 'active'
    pending.save(update_fields=['status', 'crew_names'])
    _renumber(pending.day)
    rebuild_day(pending.day)
    return pending


@transaction.atomic
def delete_part(part):
    day = part.day
    part.delete()
    _renumber(day)
    rebuild_day(day)


@transaction.atomic
def set_crew(part, names):
    cleaned = []
    for name in names:
        name = ' '.join(name.split())[:40]
        if name and name.lower() not in {c.lower() for c in cleaned}:
            cleaned.append(name)
    part.crew_names = cleaned
    part.save(update_fields=['crew_names'])
    rebuild_day(part.day)


@transaction.atomic
def merge(source, target):
    """Fold ``source`` into ``target``: its spellings become target's aliases."""
    if source.pk == target.pk or source.day_id != target.day_id:
        raise ValueError('Pick a different person on the same day.')
    keys = {target.name_key}
    aliases = []
    for alias in list(target.aliases) + [source.display_name] + list(source.aliases):
        if name_key(alias) not in keys:
            keys.add(name_key(alias))
            aliases.append(alias)
    target.aliases = aliases
    if target.presenter_id is None:
        target.presenter_id = source.presenter_id
    if not target.mic_hint_locked and source.mic_hint_locked:
        target.mic_hint, target.mic_hint_locked = source.mic_hint, True
    source.delete()
    target.save()
    rebuild_day(target.day)


@transaction.atomic
def remove_alias(person, alias):
    person.aliases = [a for a in person.aliases if name_key(a) != name_key(alias)]
    person.save(update_fields=['aliases'])
    rebuild_day(person.day)


def _hint_rank(hint):
    return {'HH': 2, 'backup': 1}.get(hint, 0)


def rebuild_day(day):
    """Re-run every active part of ``day`` and reconcile people and events.

    People are matched by name_key, then by alias, so merges, Presenter links
    and mic hints carry over. Someone no part mentions any more is removed.
    """
    people = list(day.showflow_people.all())
    known = [(p.display_name, p.aliases) for p in people]
    by_key = {}
    for p in people:
        by_key[p.name_key] = p
        for alias in p.aliases:
            by_key.setdefault(name_key(alias), p)

    parts = active_parts(day)
    results = []
    for part in parts:
        rows = list(part.rows.order_by('order'))
        results.append((part, rows, analyse([r.as_parser_row() for r in rows],
                                            crew=part.crew_names, known=known)))

    presenters = {name_key(p.name): p for p in Presenter.objects.filter(project=day.project)}
    found = {}           # name_key -> person
    states = {}          # person pk -> what this rebuild saw of them
    for part, rows, result in results:
        for name, info in result.people.items():
            person = by_key.get(name_key(name))
            if person is None:
                person = ShowflowPerson.objects.create(
                    day=day, display_name=name[:200], name_key=name_key(name)[:200],
                    presenter=presenters.get(name_key(name)))
                by_key[person.name_key] = person
            found[person.name_key] = person
            state = states.setdefault(person.pk, {'rows': {}, 'intro': {}, 'bsm_only': True,
                                                  'hint': ''})
            state['rows'][str(part.pk)] = [rows[i].order for i in info['rows']]
            if info.get('intro') is not None:
                state['intro'][str(part.pk)] = rows[info['intro']].order
            state['bsm_only'] = state['bsm_only'] and info['bsm_only']
            if _hint_rank(info['mic_hint']) > _hint_rank(state['hint']):
                state['hint'] = info['mic_hint']

    keep = {p.pk for p in found.values()}
    day.showflow_people.exclude(pk__in=keep).delete()
    for person in found.values():
        state = states[person.pk]
        person.flags = {'rows': state['rows'], 'intro': state['intro'],
                        'bsm_only': state['bsm_only']}
        fields = ['flags']
        if not person.mic_hint_locked and person.mic_hint != state['hint']:
            person.mic_hint = state['hint']
            fields.append('mic_hint')
        person.save(update_fields=fields)

    ShowflowEvent.objects.filter(row__showflow_import__in=parts).delete()
    events = []
    for part, rows, result in results:
        for e in result.events:
            events.append(ShowflowEvent(row=rows[e.row], person=by_key[name_key(e.name)],
                                        kind=e.kind, event_min=_minute(e.minute)))
        part.warnings = [w for w in part.warnings if w['kind'] == 'parse'] + [
            {'kind': kind, 'text': text,
             'row_order': rows[row].order if row is not None else None,
             'person': by_key[name_key(name)].pk if name else None}
            for kind, row, text, name in result.flags]
        part.save(update_fields=['warnings'])
    ShowflowEvent.objects.bulk_create(events)
