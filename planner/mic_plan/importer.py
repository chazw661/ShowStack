"""Save a parsed showflow, and keep a day's people and events in step.

An upload is parsed once, in the request, and saved as a *pending* import
with its rows; the PDF goes no further. The user then confirms whether it
replaces an existing part of the day or adds a new one (the default is
decided by time overlap). Every change after that -- confirm, delete, crew
names, a merge, a re-read -- ends in ``rebuild_day``, which re-runs the parser
over the stored rows of every part and reconciles the day's people with what
it found.

Only what the user set survives a rebuild: merges (``aliases``; only
``merge`` writes them), a mic hint picked by hand (``mic_hint_locked``), a
Presenter link chosen by hand (``flags['presenter_by'] == 'user'``) and
appearances added by hand (``flags['added']``, PR 5.2: kept by the label of
their line, so they survive Re-read and Replace).
Everything the parser derived -- the people themselves, their lines, an
automatic Presenter match, a hint read from a callout -- is worked out again
from scratch, so a parser fix is never undone by the state an older parse
left behind.
"""

import difflib
import hashlib
import logging
import secrets
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from planner.models import (
    MicPlan, MicPlannerDayOverride, Presenter, ShowflowEvent, ShowflowImport, ShowflowPerson, ShowflowRow,
)

from .extract import DOCUMENT_LAYOUT, ShowflowError, extract
from .parser import NAME_SUFFIXES, analyse, name_key

USER_FLAGS = ('presenter_by', 'added', 'role', 'confirmed')   # keys of ShowflowPerson.flags a rebuild keeps
VOG_KEY = 'vog'      # the name key of a day's VOG, made only when it is given a pack

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# pdfplumber is nearly all of an import. On Railway a 19-page showflow read in
# 0.77 s (the INFO timing log), about 0.04 s a page, so 60 pages is a few
# seconds; empty grid pages are skipped (extract._only_line_numbers), and
# extract.TIME_BUDGET_S stops any file at 15 s whatever its page count.
MAX_PAGES = 60
STALE_PENDING = timedelta(hours=6)
# After extract.DOCUMENT_LAYOUT. Add person needs a line of a part, so it is
# only offered on a day that has one.
DOCUMENT_NEXT_PARTS = 'You can still plan this day by adding people by hand (People \u2192 Add person).'
DOCUMENT_NEXT_NO_PARTS = "For now, build this day's sessions directly in Mic Tracker."


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
    try:
        rows, columns, warnings, pages = extract(data, max_pages=MAX_PAGES)
    except ShowflowError as error:
        if error.layout:
            # No file name: showflows can be under NDA.
            logger.info('Mic Plan import: layout %s, not read (project %s, day %s)', error.layout,
                        day.project_id, day.pk)
        if error.layout == 'document':
            raise ShowflowError('{} {}'.format(DOCUMENT_LAYOUT, DOCUMENT_NEXT_PARTS if active_parts(day)
                                               else DOCUMENT_NEXT_NO_PARTS), layout='document')
        raise
    extracted = time.monotonic()
    if not rows:
        raise ShowflowError('Found the column header but no rows under it.')
    crew = project_crew(day.project)
    known = _merges(day.showflow_people.all())
    result = analyse(rows, crew=crew, known=known)
    # No file name: showflows can be under NDA.
    logger.info('Mic Plan import: layout table, %d pages, %d rows, extract %.2fs, parse %.2fs '
                '(project %s, day %s)', pages, len(rows), extracted - started,
                time.monotonic() - extracted, day.project_id, day.pk)
    with transaction.atomic():
        imp = ShowflowImport.objects.create(
            day=day, status='pending', source_filename=filename[:255], imported_by=user,
            page_count=pages, detected_columns=columns, crew_names=result.crew,
            warnings=[{'kind': 'parse', 'text': w, 'row_order': None, 'person': None}
                      for w in warnings],
            span_start=_minute(result.span[0]), span_end=_minute(result.span[1]),
            file_sha256=hashlib.sha256(data).hexdigest(),
        )
        ShowflowRow.objects.bulk_create([
            ShowflowRow(
                showflow_import=imp, order=i, page_no=row['page_no'], line_no=row['line'][:20],
                start_text=row['start'][:50], end_text=row['end'][:50],
                duration_text=row['duration'][:50], description=row['description'],
                speaker_text=row['speaker'], bsm_text=row['bsm'], audio_text=row['audio'],
                notes_text=row['notes'],
                is_segment=t.is_segment, segment_t0=_minute(t.t0), segment_t1=_minute(t.t1),
                est_time=_minute(t.minute), time_exact=t.exact, bbox=row['box'],
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
        # Breaks set by hand follow the segment's line into the new file, and
        # row overrides their row (overrides.resolve, by line or start + text).
        pending.break_overrides = replace.break_overrides
        pending.row_overrides = replace.row_overrides
        # Walkthrough checks too: each finds its row again (walkthrough, by rowkey).
        replace.row_checks.update(part=pending)
        replace.delete()
    pending.status = 'active'
    pending.save(update_fields=['status', 'crew_names', 'break_overrides', 'row_overrides'])
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
    if target.presenter_id is None and source.presenter_id is not None:
        target.presenter_id = source.presenter_id
        target.flags = {**target.flags, **_user_flags(source)}
    if not target.mic_hint_locked and source.mic_hint_locked:
        target.mic_hint, target.mic_hint_locked = source.mic_hint, True
    if source.flags.get('added'):
        target.flags = {**target.flags,
                        'added': list(target.flags.get('added', [])) + list(source.flags['added'])}
    source.delete()
    target.save()
    rebuild_day(target.day)


def _set_by(user):
    return {'set_by': user, 'set_by_name': user.get_username() if user else '', 'set_at': timezone.now()}


def rejected_keys(day):
    """Name keys of the phrases ``day``'s parse must not make into people."""
    return set(MicPlannerDayOverride.objects.filter(day=day, kind='not_a_person').values_list('key', flat=True))


@transaction.atomic
def reject_phrase(day, phrase, user=None):
    """"Not a person": ``phrase`` is dropped wherever it appears on ``day``,
    in every part, and stays dropped across Re-read and Replace."""
    key = name_key(phrase)[:200]
    if not key:
        raise ValueError('Nothing to reject.')
    MicPlannerDayOverride.objects.update_or_create(
        day=day, kind='not_a_person', key=key, defaults={'value': {'phrase': phrase[:200]}, **_set_by(user)})
    rebuild_day(day)


@transaction.atomic
def unreject_phrase(day, key):
    MicPlannerDayOverride.objects.filter(day=day, kind='not_a_person', key=key).delete()
    rebuild_day(day)


def confirm_person(person, user=None, confirmed=True):
    """The user says ``person`` is a real person on this day (or takes it
    back). Read with planning.people_to_confirm."""
    flags = dict(person.flags)
    if confirmed:
        flags['confirmed'] = {'by': user.pk if user else None,
                              'by_name': user.get_username() if user else '', 'at': timezone.now().isoformat()}
    else:
        flags.pop('confirmed', None)
    person.flags = flags
    person.save(update_fields=['flags'])


@transaction.atomic
def set_vog_pack(day, pack, user=None):
    """Give the VOG a pack for the day (``pack`` 'body' or 'HH'), or none
    (None). With one, the VOG is a person with role 'vog' that the plan
    gives one pack from its first line to its last; without, it is no one."""
    if pack is None:
        MicPlannerDayOverride.objects.filter(day=day, kind='vog').delete()
        ShowflowPerson.objects.filter(day=day, name_key=VOG_KEY, flags__role='vog').delete()
    else:
        if pack not in ('body', 'HH'):
            raise ValueError('A VOG pack is body or HH.')
        MicPlannerDayOverride.objects.update_or_create(
            day=day, kind='vog', key='', defaults={'value': {'pack': pack}, **_set_by(user)})
        person, _ = ShowflowPerson.objects.get_or_create(
            day=day, name_key=VOG_KEY, defaults={'display_name': 'VOG', 'flags': {'role': 'vog'}})
        person.flags = {**person.flags, 'role': 'vog'}
        person.mic_hint = 'HH' if pack == 'HH' else ''
        person.mic_hint_locked = True
        person.save(update_fields=['flags', 'mic_hint', 'mic_hint_locked'])
    rebuild_day(day)


CLOSE_RATIO = 0.8


def close_names(day, name, exclude=None):
    """People on ``day`` whose name is close to ``name`` but not it ("Pat
    Gest" for "Pat Guest", or the same surname and first initial): a typed
    Same as name is checked against them before a new person is made."""
    key = name_key(name)
    words = key.split()
    out = []
    for p in day.showflow_people.exclude(pk=getattr(exclude, 'pk', None)):
        if p.flags.get('gone') or p.name_key == key:
            continue
        theirs = p.name_key.split()
        same_surname = (len(words) > 1 and len(theirs) > 1 and words[-1] == theirs[-1]
                        and words[0][:1] == theirs[0][:1])
        if same_surname or difflib.SequenceMatcher(None, key, p.name_key).ratio() >= CLOSE_RATIO:
            out.append(p)
    return out


@transaction.atomic
def same_as(source, target=None, new_name=None):
    """"Same as": ``source``'s spelling is ``target`` (merge), or a person
    called ``new_name`` that is made for it ("Acme Lee Park" is
    "Lee Park"). An existing person with that name is used, not doubled."""
    if (target is None) == (not new_name):
        raise ValueError('Pick a person or type a name.')
    if target is None:
        name = ' '.join(new_name.split())[:200]
        target = ShowflowPerson.objects.filter(day=source.day, name_key=name_key(name)).first()
        if target is None:
            target = ShowflowPerson.objects.create(day=source.day, display_name=name, name_key=name_key(name)[:200])
    merge(source, target)
    return target


@transaction.atomic
def remove_alias(person, alias):
    person.aliases = [a for a in person.aliases if name_key(a) != name_key(alias)]
    person.save(update_fields=['aliases'])
    rebuild_day(person.day)


@transaction.atomic
def reread(part):
    """Run the current parser over ``part``'s stored rows: their times and
    segments, then the whole day (people, cues, flags). No PDF needed."""
    rows = list(part.rows.order_by('order'))
    result = analyse([r.as_parser_row() for r in rows], crew=part.crew_names)
    changed = []
    for row, t in zip(rows, result.times):
        new = (t.is_segment, _minute(t.t0), _minute(t.t1), _minute(t.minute), t.exact)
        if new != (row.is_segment, row.segment_t0, row.segment_t1, row.est_time, row.time_exact):
            (row.is_segment, row.segment_t0, row.segment_t1, row.est_time, row.time_exact) = new
            changed.append(row)
    ShowflowRow.objects.bulk_update(changed, ['is_segment', 'segment_t0', 'segment_t1',
                                              'est_time', 'time_exact'])
    part.span_start, part.span_end = _minute(result.span[0]), _minute(result.span[1])
    part.save(update_fields=['span_start', 'span_end'])
    rebuild_day(part.day)


@transaction.atomic
def remove_person(person):
    """Drop someone no showflow mentions any more, with what the user set on them."""
    if not person.flags.get('gone'):
        raise ValueError('Still in a showflow of this day.')
    day = person.day
    person.delete()
    rebuild_day(day)


def _entry(part, row, off_row, user, from_flag):
    line = lambda r: r.line_no or '#{}'.format(r.order + 1)
    return {'id': secrets.token_hex(4), 'part': part.pk, 'line': line(row),
            'off': line(off_row) if off_row is not None else None, 'from_flag': from_flag,
            'by': user.pk if user else None, 'by_name': user.get_username() if user else '',
            'at': timezone.now().isoformat()}


def _person_for(day, name):
    """The day's person ``name`` means (by name, an alias, or the name
    without a title or suffix), or a new one."""
    name = ' '.join(name.split())[:200]
    key, loose = name_key(name), match_key(name)
    for p in day.showflow_people.all():
        if (p.name_key == key or key in {name_key(a) for a in p.aliases}
                or match_key(p.display_name) == loose):
            return p
    return ShowflowPerson.objects.create(day=day, display_name=name, name_key=key[:200])


@transaction.atomic
def add_people(day, names, part, row, user, off_row=None, from_flag=False):
    """Add an appearance by hand for each of ``names`` (PR 5.2), on at
    ``row``: from a "not listed" line (``from_flag``) or People's Add person.
    Returns the people."""
    if part.day_id != day.pk or row.showflow_import_id != part.pk:
        raise ValueError('Not a line of this day.')
    if off_row is not None and (off_row.showflow_import_id != part.pk or off_row.order <= row.order):
        raise ValueError('The off line must come after the on line, in the same showflow.')
    out = []
    for name in names:
        if not name.strip():
            continue
        person = _person_for(day, name)
        person.flags = {**person.flags, 'added': list(person.flags.get('added', []))
                        + [_entry(part, row, off_row, user, from_flag)]}
        person.save(update_fields=['flags'])
        out.append(person)
    if not out:
        raise ValueError('Give at least one name.')
    rebuild_day(day)
    return out


def _find_entry(person, entry_id):
    entry = next((e for e in person.flags.get('added', []) if e['id'] == entry_id), None)
    if entry is None:
        raise ValueError('That appearance is no longer there.')
    return entry


@transaction.atomic
def update_added(person, entry_id, part, row, off_row, user):
    """Move a hand-added appearance to other lines."""
    entry = _find_entry(person, entry_id)
    if part.day_id != person.day_id or row.showflow_import_id != part.pk:
        raise ValueError('Not a line of this day.')
    if off_row is not None and (off_row.showflow_import_id != part.pk or off_row.order <= row.order):
        raise ValueError('The off line must come after the on line, in the same showflow.')
    new = _entry(part, row, off_row, user, entry.get('from_flag', False))
    new['id'] = entry['id']
    person.flags = {**person.flags, 'added': [new if e['id'] == entry_id else e
                                              for e in person.flags['added']]}
    person.save(update_fields=['flags'])
    rebuild_day(person.day)


@transaction.atomic
def remove_added(person, entry_id):
    """Drop a hand-added appearance; the person too if nothing else keeps them."""
    _find_entry(person, entry_id)
    day = person.day
    person.flags = {**person.flags, 'added': [e for e in person.flags['added'] if e['id'] != entry_id]}
    if not person.flags['added']:
        del person.flags['added']
    person.save(update_fields=['flags'])
    rebuild_day(day)          # someone only hand-added, with nothing else set, is deleted here


def _merges(people):
    """What the parser is told about the day's people: merges only. A hint
    or Presenter link set by hand stays with the person by name after the
    parse; it does not make their name a spelling the parser must match."""
    return [(p.display_name, p.aliases) for p in people if p.aliases]


def _user_flags(person):
    return {k: person.flags[k] for k in USER_FLAGS if k in person.flags}


def has_user_state(person):
    return bool(person.aliases or person.mic_hint_locked
                or person.flags.get('presenter_by') == 'user' or person.flags.get('added')
                or person.flags.get('role'))


def match_key(name):
    """A name compared without a title or a suffix: "Dr. Ann Lee, MD" and
    "Ann Lee" are the same person when adding people by hand."""
    words = name_key(name).replace(',', ' ').split()
    while words and words[-1].strip('.') in NAME_SUFFIXES:
        words.pop()
    if len(words) > 2 and words[0].rstrip('.') in ('dr', 'mr', 'mrs', 'ms', 'mx', 'prof'):
        words = words[1:]
    return ' '.join(words)


def resolve_added(entry, parts, rows_by_part):
    """(part, on row, off row or None) for a hand-added appearance, by the
    label of its line: in its own part, else (a Replace made a new part) the
    first part of the day with that line. None: the line is gone."""
    ordered = sorted(parts, key=lambda p: (p.pk != entry.get('part'), p.part_order, p.pk))
    for part in ordered:
        rows = rows_by_part[part.pk]
        on = next((r for r in rows if (r.line_no or '#{}'.format(r.order + 1)) == entry['line']), None)
        if on is None:
            continue
        off = None
        if entry.get('off'):
            off = next((r for r in rows if (r.line_no or '#{}'.format(r.order + 1)) == entry['off']
                        and r.order > on.order), None)
        return part, on, off
    return None


def _hint_rank(hint):
    return {'HH': 2, 'backup': 1}.get(hint, 0)


def rebuild_day(day):
    """Re-run every active part of ``day`` and reconcile people and events.

    The parser is told only about merges (``_merges``); people it made last
    time are not fed back to it. Existing people are matched by name_key,
    then by alias, so a user link or hint stays with them. Someone no part
    mentions any more is removed, unless they carry user state: then they
    stay, marked ``gone``.
    """
    people = list(day.showflow_people.all())
    known = _merges(people)
    by_key = {}
    for p in people:
        by_key[p.name_key] = p
    for p in people:
        for alias in p.aliases:
            by_key.setdefault(name_key(alias), p)

    parts = active_parts(day)
    rejected = rejected_keys(day)
    results = []
    for part in parts:
        rows = list(part.rows.order_by('order'))
        results.append((part, rows, analyse([r.as_parser_row() for r in rows],
                                            crew=part.crew_names, known=known, rejected=rejected)))

    presenters = {name_key(p.name): p for p in Presenter.objects.filter(project=day.project)}
    found = {}           # name_key -> person
    states = {}          # person pk -> what this rebuild saw of them
    for part, rows, result in results:
        for name, info in result.people.items():
            person = by_key.get(name_key(name))
            if person is None:
                person = ShowflowPerson.objects.create(
                    day=day, display_name=name[:200], name_key=name_key(name)[:200])
                by_key[person.name_key] = person
            found[person.name_key] = person
            state = states.setdefault(person.pk, {'rows': {}, 'intro': {}, 'bsm_only': True,
                                                  'hint': '', 'exits': {}, 'enters': {}, 'mics': {},
                                                  'spans': {}})
            state['rows'][str(part.pk)] = [rows[i].order for i in info['rows']]
            if info.get('spans'):
                # [row order, column, start, end]: the characters their name came from.
                state['spans'][str(part.pk)] = [[rows[r].order, col, start, end]
                                                for r, col, start, end in info['spans']]
            for kind in ('exits', 'enters'):
                if info.get(kind):
                    state[kind][str(part.pk)] = [rows[i].order for i in info[kind]]
            if info.get('mics'):
                state['mics'].setdefault(str(part.pk), []).extend(
                    dict(e, row=rows[e['row']].order) for e in info['mics'])
            if info.get('intro') is not None:
                state['intro'][str(part.pk)] = rows[info['intro']].order
            state['bsm_only'] = state['bsm_only'] and info['bsm_only']
            if _hint_rank(info['mic_hint']) > _hint_rank(state['hint']):
                state['hint'] = info['mic_hint']

    # People added by hand are on the day whether or not a showflow names them.
    for p in people:
        if (p.flags.get('added') or p.flags.get('role')) and p.name_key not in found:
            found[p.name_key] = p
    keep = {p.pk for p in found.values()}
    gone = [p for p in people if p.pk not in keep and has_user_state(p)]
    day.showflow_people.exclude(pk__in=keep | {p.pk for p in gone}).delete()
    rows_by_part = {part.pk: rows for part, rows, result in results}
    loose = {}
    for p in presenters.values():
        loose.setdefault(match_key(p.name), p)
    cleared = set()          # (part pk, row order) of "not listed" lines people were added from
    for person in found.values():
        state = states.get(person.pk, {'rows': {}, 'intro': {}, 'bsm_only': False, 'hint': person.mic_hint,
                                       'exits': {}, 'enters': {}, 'mics': {}, 'spans': {}})
        missing = []
        for entry in person.flags.get('added', []):
            where = resolve_added(entry, parts, rows_by_part)
            if where is None:
                missing.append(entry['line'])
            elif entry.get('from_flag'):
                cleared.add((where[0].pk, where[1].order))
        person.flags = {'rows': state['rows'], 'intro': state['intro'], 'bsm_only': state['bsm_only'],
                        'exits': state['exits'], 'enters': state['enters'], 'mics': state['mics'],
                        'spans': state['spans'],
                        **_user_flags(person)}
        if missing:
            person.flags['added_missing'] = missing
        if not person.mic_hint_locked:
            person.mic_hint = state['hint']
        if person.flags.get('presenter_by') != 'user':
            # Automatic: matched afresh, by name (a title or suffix aside).
            person.presenter = presenters.get(person.name_key) or loose.get(match_key(person.display_name))
        person.save(update_fields=['flags', 'mic_hint', 'presenter'])
    for person in gone:
        person.flags = {'rows': {}, 'intro': {}, 'bsm_only': False, 'gone': True,
                        **_user_flags(person)}
        person.save(update_fields=['flags'])

    ShowflowEvent.objects.filter(row__showflow_import__in=parts).delete()
    events = []
    for part, rows, result in results:
        for e in result.events:
            events.append(ShowflowEvent(row=rows[e.row], person=by_key[name_key(e.name)],
                                        kind=e.kind, event_min=_minute(e.minute),
                                        source_rows=[rows[i].order for i in e.rows]))
        part.warnings = [w for w in part.warnings if w['kind'] == 'parse'] + [
            dict({'kind': kind, 'text': text,
                  'row_order': rows[row].order if row is not None else None,
                  'person': by_key[name_key(name)].pk if name else None},
                 # The Speaker-cell characters no name accounts for: [[start, end]].
                 **({'spans': [list(s) for s in result.leftovers[row]]}
                    if kind == 'unmatched_speaker' and row in result.leftovers else {}))
            for kind, row, text, name in result.flags
            # People were added from this "not listed" line: it is dealt with.
            if not (kind == 'description_names' and row is not None and (part.pk, rows[row].order) in cleared)]
        part.save(update_fields=['warnings'])
    ShowflowEvent.objects.bulk_create(events)
    # People, lines or cues may have changed: the day's plan no longer matches.
    MicPlan.objects.filter(day=day, stale=False).update(stale=True)
