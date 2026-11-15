"""Generate a show day's draft mic plan: build the solver's inputs from what
the importer stored, run ``solver.solve`` and save the result as the day's
MicPlan (replacing the last draft, version + 1). Nothing here writes to Mic
Tracker.

Edits (PR 3): the A2's moves are an ordered log (MicPlanEdit) replayed as
pins on every re-solve, keyed by appearance key, never by pk. Every re-solve
but "Start over" also prefers the RFs of the version it replaces, so a move
changes only what it must and a re-generate only what the new data forces.
An edit or undo re-solves with the plan's own settings and skips the
lead-fix search (fix suggestions return on the next Generate).
"""

import logging
import secrets
import time
from dataclasses import replace

from django.db import transaction
from django.utils import timezone

from planner.models import (
    MicPlan, MicPlanA2Action, MicPlanAppearance, MicPlanAssignment, MicPlanEdit, MicPlanSettings, ShowflowEvent,
)

from . import solver
from .display import describe_change, describe_edit
from . import importer
from .importer import active_parts
from .parser import NO_CUE_MIN_COVERAGE, group_exit, segment_heading

logger = logging.getLogger(__name__)

SETTINGS_FIELDS = ('a2_count', 'mic_min', 'demic_min', 'premic_lead_min', 'margin_min',
                   'wireless_channels', 'handheld_channels', 'spare_handhelds', 'pack_policy',
                   'showflow_numbers')
POLICIES = ('recycle_at_breaks', 'fewest_packs')


def project_settings(project):
    return MicPlanSettings.objects.get_or_create(project=project)[0]


def settings_dict(obj):
    return {name: getattr(obj, name) for name in SETTINGS_FIELDS}


def mark_stale(day):
    """The day's imports, people or hints changed: its plan no longer matches."""
    MicPlan.objects.filter(day=day, stale=False).update(stale=True)


def segment_line(row):
    """The key a segment's break override is stored under: its heading's line."""
    return row.line_no or '#{}'.format(row.order + 1)


def named_orders(day, part):
    """Orders of ``part``'s rows that name someone to speak."""
    out = set()
    for p in day.showflow_people.all():
        if not p.flags.get('gone'):
            out.update(p.flags.get('rows', {}).get(str(part.pk), []))
    return out


def part_segments(part, rows, named):
    """Each segment heading of ``part`` (rows in order) that has a time:
    {row, name, t0, t1, end, detected, override, is_break, helpers,
    helpers_set}. ``override`` is the stored hand-set break value, or None;
    ``helpers`` the de-mic helpers set for it (0), ``helpers_set`` who set
    them ({'n', 'by', 'by_name', 'at'}, or None). Both are stored in
    ``part.break_overrides`` by the heading's line, so they follow it into
    a re-read or a replacing file."""
    parser_rows = [r.as_parser_row() for r in rows]
    by_order = {r.order: k for k, r in enumerate(rows)}
    named = {by_order[o] for o in named if o in by_order}
    starts = [k for k, r in enumerate(rows) if r.is_segment]
    out = []
    for k, a in enumerate(starts):
        b = starts[k + 1] if k + 1 < len(starts) else len(rows)
        head = rows[a]
        if head.segment_t0 is None:
            continue
        t1 = head.segment_t1 if head.segment_t1 is not None else head.segment_t0
        name, detected = segment_heading(parser_rows, a, b, named=named, minutes=t1 - head.segment_t0)
        entry = (part.break_overrides or {}).get(segment_line(head)) or {}
        override = entry if 'is_break' in entry else None
        helpers = entry.get('helpers')
        out.append({'row': head, 'name': name, 't0': head.segment_t0, 't1': max(t1, head.segment_t0 + 1),
                    'end': rows[b - 1].order + 1, 'detected': detected, 'override': override,
                    'is_break': override['is_break'] if override else detected,
                    'helpers': helpers['n'] if helpers else 0, 'helpers_set': helpers})
    return out


def _segment(part, row):
    seg = next((s for s in part_segments(part, list(part.rows.order_by('order')), named_orders(part.day, part))
                if s['row'].pk == row.pk), None)
    if seg is None:
        raise ValueError('Not a segment heading.')
    return seg


def _by(user):
    return {'by': user.pk if user else None, 'by_name': user.get_username() if user else '',
            'at': timezone.now().isoformat()}


def _store(part, row, entry):
    """Save the stored entry for segment ``row`` (dropped when empty)."""
    overrides = dict(part.break_overrides or {})
    if entry:
        overrides[segment_line(row)] = entry
    else:
        overrides.pop(segment_line(row), None)
    part.break_overrides = overrides
    part.save(update_fields=['break_overrides'])
    mark_stale(part.day)


def set_break(part, row, is_break, user):
    """Mark segment ``row`` of ``part`` a break or not. Back to the detected
    value clears the override. The day's plan no longer matches."""
    seg = _segment(part, row)
    entry = {'helpers': seg['helpers_set']} if seg['helpers_set'] else {}
    if is_break != seg['detected']:
        entry.update(is_break=is_break, **_by(user))
    _store(part, row, entry)


def set_helpers(part, row, n, user):
    """Set the de-mic helpers for segment ``row`` of ``part`` (0 clears
    them). The day's plan no longer matches."""
    if not 0 <= n <= solver.MAX_HELPERS:
        raise ValueError('De-mic helpers: 0 to {}.'.format(solver.MAX_HELPERS))
    seg = _segment(part, row)
    entry = {k: v for k, v in (seg['override'] or {}).items() if k != 'helpers'}
    if n:
        entry['helpers'] = dict(n=n, **_by(user))
    _store(part, row, entry)


def _segments(part, rows, named):
    """solver.Segment for each segment heading of ``part`` (rows in order)."""
    return [solver.Segment(key=s['row'].pk, part=part.pk, start=s['row'].order, end=s['end'], name=s['name'],
                           t0=s['t0'], t1=s['t1'], is_break=s['is_break'], helpers=s['helpers'])
            for s in part_segments(part, rows, named)]


def _mic_changes(people, parts):
    """Keys of the people the showflow says lose their mic during the day,
    whatever the hosts rule says (follow only, see build_day): on two numbers, or their number goes to
    someone else after their last mention of it (Client F reuses Lav 1 each
    block). An all-day pack would run into that next wearer."""
    place = {part.pk: k for k, part in enumerate(parts)}
    number = {}          # number -> {person key: last place it is theirs}
    mine = {}            # person key -> their numbers
    for p in people:
        for pk, found in p.flags.get('mics', {}).items():
            for e in found if int(pk) in place else ():
                key = (e['kind'] == 'HH', e['n'])
                mine.setdefault(p.pk, set()).add(key)
                at = (place[int(pk)], e['row'])
                number.setdefault(key, {})
                number[key][p.pk] = max(at, number[key].get(p.pk, at))
    out = {pk for pk, keys in mine.items() if len(keys) > 1}
    for owners in number.values():
        out |= {pk for pk, at in owners.items() if any(other > at for other in owners.values())}
    return out


def showflow_rf(entry, R):
    """The RF a showflow mic number means on rig ``R``: HH n is the nth
    channel of the handheld zone, anything else channel n (and HH n too
    with no handheld zone). Past the zone it is a misfit like any pin."""
    if entry['kind'] == 'HH' and R.set and R.handhelds:
        return R.first_hh + entry['n'] - 1
    return entry['n']


def showflow_numbers(day, rows_by_part, apps):
    """{appearance key: the showflow's mic entry for it}: the person's latest
    entry at or before the appearance's off line. A list at the doors covers
    that block; the next list or a cell on their row takes over from there."""
    where = {r.pk: (k, r.order) for k, part in enumerate(active_parts(day)) for r in rows_by_part[part.pk]}
    place = {part.pk: k for k, part in enumerate(active_parts(day))}
    mine = {}
    for p in day.showflow_people.all():
        found = [((place[int(pk)], e['row']), e) for pk, entries in p.flags.get('mics', {}).items()
                 if int(pk) in place for e in entries]
        mine[p.pk] = sorted(found, key=lambda f: f[0])
    out = {}
    for a in apps:
        end = where.get(a.off_row) or where.get(a.on_row)
        before = [e for at, e in mine.get(a.person, ()) if end is not None and at <= end]
        if before:
            out[a.skey] = before[-1]
    return out


def _showflow_hosts(values, edits):
    """Does the showflow's hosts rule apply (build_day ``follow``)? Following
    its numbers, or once "Use the showflow's numbers" is in the log: a host
    whose number goes to someone else could not take it otherwise."""
    return values.get('showflow_numbers') == 'follow' or any(e.value.get('batch') for e in edits)


def _follow(values, day, data, rows_by_part):
    """The numbers to pin: with 'follow', every one, else none."""
    if values.get('showflow_numbers') != 'follow':
        return {}
    return showflow_numbers(day, rows_by_part, solver.appearances(data)[0])


def build_day(day, follow=False):
    """(solver.Day, {part pk: rows}, cue_mode). ``follow``: the plan follows
    the showflow's mic numbers, so its mic changes rule out hosts; compare
    keeps the normal hosts rule, so its plan stays independent."""
    parts = active_parts(day)
    rows_by_part, rows, segments = {}, [], []
    for part in parts:
        part_rows = list(part.rows.order_by('order'))
        rows_by_part[part.pk] = part_rows
        rows += [solver.Row(r.pk, part.pk, r.order, r.line_no, r.est_time) for r in part_rows]
        segments += _segments(part, part_rows, named_orders(day, part))
    events = list(ShowflowEvent.objects.filter(row__showflow_import__in=parts).select_related('row'))
    cue_rows = {}
    for e in events:
        cue_rows.setdefault((e.person_id, e.row.showflow_import_id), set()).add(e.row.order)

    people, listings, exits, enters, added = [], {}, {}, {}, []
    changes = _mic_changes(day.showflow_people.all(), parts) if follow else set()
    for p in day.showflow_people.all():
        if p.flags.get('gone'):
            continue
        people.append(solver.Person(
            key=p.pk, name=p.display_name, mic_type=solver.HH if p.mic_hint == 'HH' else solver.BODY,
            backup=(solver.HH if p.backup_mic_type == 'HH' else solver.BODY)
            if p.mic_hint == 'backup' else None, name_key=p.name_key, no_host=p.pk in changes))
        keys = []
        for part in parts:
            by_order = {r.order: r.pk for r in rows_by_part[part.pk]}
            skip = cue_rows.get((p.pk, part.pk), set())
            keys += [by_order[o] for o in p.flags.get('rows', {}).get(str(part.pk), [])
                     if o in by_order and o not in skip]
            for kind, into in (('exits', exits), ('enters', enters)):
                orders = p.flags.get(kind, {}).get(str(part.pk), [])
                if orders:
                    into.setdefault(p.pk, []).extend(by_order[o] for o in orders if o in by_order)
        listings[p.pk] = keys
        for entry in p.flags.get('added', []):
            where = importer.resolve_added(entry, parts, rows_by_part)
            if where is not None:
                added.append(solver.Added(p.pk, where[1].pk, where[2].pk if where[2] is not None else None))
    groups = []
    for part in parts:
        for r in rows_by_part[part.pk]:
            g = group_exit(r.description)
            if g is not None:
                groups.append(solver.GroupExit(r.pk, g[0], tuple(g[1])))

    # A part's on/off comes from its cues when they cover at least half of
    # the people it lists (the parser's "No cue" rule); otherwise from lines.
    cued = set()
    for part in parts:
        part_keys = {r.pk for r in rows_by_part[part.pk]}
        listed = {p for p, keys in listings.items() if part_keys & set(keys)}
        sent = {e.person_id for e in events if e.row.showflow_import_id == part.pk}
        if sent and listed and len(listed & sent) >= NO_CUE_MIN_COVERAGE * len(listed):
            cued.add(part.pk)
    cues = tuple(solver.Cue(e.kind, e.person_id, e.row_id, e.event_min) for e in events)
    data = solver.Day(rows=tuple(rows), segments=tuple(segments), people=tuple(people), cues=cues,
                      listings=listings, cued_parts=frozenset(cued), exits=exits, enters=enters,
                      group_exits=tuple(groups), added=tuple(added))
    mode = 'cues' if parts and len(cued) == len(parts) else 'line estimates'
    return data, rows_by_part, mode


def plan_values(plan):
    """The settings ``plan`` was made with, in today's fields. Plans from
    before PR 2.2 have no pack_policy: they used fewest_packs. Plans from
    before the rig (PR 5.1) had pack counts: converted as migration 0225
    converts the project's settings."""
    values = {'pack_policy': solver.FEWEST_PACKS, 'showflow_numbers': 'compare', **plan.settings}
    if 'wireless_channels' not in values:
        body, hh = values.pop('body_pack_count', None), values.pop('hh_count', None)
        spare = values.pop('emergency_spare_hh', False)
        if body is not None and hh is not None and body + hh:
            values.update(wireless_channels=body + hh, handheld_channels=hh,
                          spare_handhelds=min(1, hh) if spare else 0)
        else:
            values.update(wireless_channels=None, handheld_channels=0, spare_handhelds=1 if spare else 0)
    return values


def plan_rig(plan):
    """The solver.Rig ``plan`` was numbered on."""
    v = plan_values(plan)
    return solver.Rig(v.get('wireless_channels'), v.get('handheld_channels') or 0, v.get('spare_handhelds') or 0)


def before_rig(plan):
    """Was ``plan`` numbered before the rig, with a rig its numbers do not
    follow? Edits and Send to Mic Tracker wait for a Re-generate."""
    return 'wireless_channels' not in plan.settings and plan_values(plan)['wireless_channels'] is not None


BEFORE_RIG = 'This plan was made before rig channels. Re-generate it first.'


def solver_settings(values):
    return solver.Settings(**{k: values[k] for k in SETTINGS_FIELDS})


def policy_counts(data, settings):
    """{policy: {body, hh, mid_session}}: the packs each policy needs for the
    day at ``settings`` with the pack counts blank."""
    out = {}
    for policy in POLICIES:
        s = solver.summary(solver.solve(
            data, replace(settings, pack_policy=policy, wireless_channels=None), suggest=False))
        out[policy] = {'body': s['body'], 'hh': s['hh'], 'mid_session': s['mid_session']}
    return out


SHOWFLOW_CARD = 'showflow_mics'


class EditRefused(Exception):
    """An edit or undo that was not applied: ``str(e)`` says why, ``status``
    is the HTTP status for it."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def snapshot(plan):
    """{appearance key: [RF, pool]} of the plan's main (not backup) packs."""
    if plan is None:
        return {}
    return {skey: [rf, pool] for skey, rf, pool in MicPlanAssignment.objects.filter(
        appearance__plan=plan, backup=False).values_list('appearance__skey', 'rf_number', 'appearance__mic_type')
        if skey}


def replay(edits):
    """(pins {skey: RF}, types {skey: pool}) from the edit log in order; the
    last edit about a key wins. A move keeps the type it stored (since PR
    5.1b the wearer's own; before, a move to a lane of the other type
    switched it, and those stay switched)."""
    pins, types = {}, {}
    for e in edits:
        if e.kind == 'move_rf':
            pins[e.key] = e.value['rf']
            types[e.key] = e.value['pool']
        elif e.kind == 'set_mic_type':
            pins.pop(e.key, None)
            types[e.key] = e.value['mic_type']
        elif e.kind == 'unpin':
            pins.pop(e.key, None)
            types.pop(e.key, None)
    return pins, types


def _fixed(edits, prefer, R, rezone=False, numbers=None):
    """(solver.Fixed, misfits {skey: (rf, pool)}). A pin keeps its RF on any
    channel of the rig but a spare (either type takes either zone); on a
    spare or past the rig's end (misfit) the pin keeps its type and the
    solver gives it a channel. A preferred RF there is dropped, and with
    ``rezone`` (the rig changed) one outside its type's zone too, so a rig
    change puts each type back in its zone where it can. ``numbers``
    ({skey: showflow entry}, 'follow') are pins too, except where the log
    has said something about that appearance: a move, a Switch or an Unpin
    beats the showflow."""
    pins, types = replay(edits)
    touched = {e.key for e in edits}
    shown = set()
    for key, entry in (numbers or {}).items():
        if key not in touched:
            shown.add(key)
            pins[key] = showflow_rf(entry, R)
            if entry['pool']:
                types[key] = entry['pool']
    misfits = {}
    for key, rf in list(pins.items()):
        if not R.usable(rf):
            misfits[key] = (rf, types.get(key))
            del pins[key]
    prefer = {k: v[0] for k, v in prefer.items()
              if R.usable(v[0]) and not (rezone and R.set and R.pool_at(v[0]) != v[1])}
    return solver.Fixed(pins=pins, types=types, prefer=prefer, showflow=frozenset(shown)), misfits


def misfit_text(rf, R):
    """Why a pin no longer fits the rig: 'kept spare', 'not in the rig (1–13)'."""
    if R.pool_at(rf) == 'spare':
        return 'kept spare'
    return 'not in the rig (1\u2013{})'.format(R.channels)


@transaction.atomic
def generate(day, user=None, mode='keep'):
    """Solve ``day`` with its project's settings and save it as the day's
    plan. ``mode`` 'keep': replay the edit log and prefer the current
    version's RFs; 'over': clear the log and number every pack afresh."""
    plan = MicPlan.objects.select_for_update().filter(day=day).first()
    if plan is not None and mode == 'over':
        plan.edits.all().delete()
    keep = plan is not None and mode == 'keep'
    prev = snapshot(plan) if keep else {}
    edits = list(plan.edits.all()) if plan is not None else []
    values = settings_dict(project_settings(day.project))
    R = solver.rig(solver_settings(values))
    data, rows_by_part, mode_label = build_day(day, follow=_showflow_hosts(values, edits))
    fixed, misfits = _fixed(edits, prev, R, rezone=keep and plan_rig(plan) != R,
                            numbers=_follow(values, day, data, rows_by_part))
    started = time.monotonic()
    result = solver.solve(data, solver_settings(values), fixed=fixed)
    counts = policy_counts(data, solver_settings(values))
    logger.info('Mic Plan generate: %d appearances, %d actions, %.3fs (project %s, day %s)',
                len(result.appearances), len(result.actions), time.monotonic() - started,
                day.project_id, day.pk)
    plan = plan or MicPlan(day=day)
    plan.generated_at = timezone.now()
    plan.generated_by = user
    plan.cue_mode = mode_label
    return _save(plan, data, rows_by_part, result, values, counts, fixed, edits, prev, prev, misfits)


def _resolve(plan, prefer):
    """Re-solve after an edit or undo: the plan's own settings, the log's
    pins, ``prefer``'s RFs, no lead-fix search."""
    values = plan_values(plan)
    edits = list(plan.edits.all())
    data, rows_by_part, _ = build_day(plan.day, follow=_showflow_hosts(values, edits))
    fixed, misfits = _fixed(edits, prefer, solver.rig(solver_settings(values)),
                            numbers=_follow(values, plan.day, data, rows_by_part))
    started = time.monotonic()
    result = solver.solve(data, solver_settings(values), suggest=False, fixed=fixed)
    logger.info('Mic Plan edit re-solve: %d appearances, %.3fs (project %s, day %s)',
                len(result.appearances), time.monotonic() - started, plan.day.project_id, plan.day_id)
    return _save(plan, data, rows_by_part, result, values, plan.policy_counts, fixed, edits, snapshot(plan), prefer,
                 misfits)


def _locked(day, version):
    plan = MicPlan.objects.select_for_update().filter(day=day).first()
    if plan is None:
        raise EditRefused('There is no plan for this day yet.', 404)
    if version != plan.version:
        raise EditRefused('The plan changed while you were looking at it (now v{}). Reload to see it, '
                          'then make your change again.'.format(plan.version), 409)
    if plan.stale:
        raise EditRefused('The showflow changed after this plan was made. Re-generate it first.', 409)
    if before_rig(plan):
        raise EditRefused(BEFORE_RIG, 409)
    return plan


@transaction.atomic
def edit(day, version, kind, key, value, user=None):
    """Add one edit to the log and re-solve. ``value``: move_rf {rf} (the
    wearer keeps their type on any lane: only set_mic_type changes it),
    set_mic_type {mic_type}, unpin {}. Returns (plan, edit)."""
    plan = _locked(day, version)
    app = plan.appearances.filter(skey=key).prefetch_related('assignments').first() if key else None
    if app is None:
        raise EditRefused('That appearance is not in this plan.')
    main = next((s for s in app.assignments.all() if not s.backup), None)
    pools = {p['rf']: p for p in plan.packs}
    if kind == 'move_rf':
        try:
            rf = int(value.get('rf'))
        except (TypeError, ValueError):
            raise EditRefused('Choose an RF.')
        if not 1 <= rf <= 999:
            raise EditRefused('Choose an RF from 1 to 999.')
        lane = pools.get(rf)
        R = plan_rig(plan)
        if lane is not None and lane.get('backup_of'):
            raise EditRefused('RF {} is a backup pack.'.format(rf))
        if R.set and R.pool_at(rf) is None:
            raise EditRefused("RF {} isn't in the rig (1\u2013{}).".format(rf, R.channels))
        if R.set and R.pool_at(rf) == 'spare':
            raise EditRefused('RF {} is kept spare \u2014 lower the spare count in settings to use it.'.format(rf))
        clean = {'rf': rf, 'pool': app.mic_type}
    elif kind == 'set_mic_type':
        pool = value.get('mic_type')
        if pool not in (solver.BODY, solver.HH):
            raise EditRefused('Choose body pack or handheld.')
        if pool == app.mic_type:
            raise EditRefused('{} already has a {}.'.format(app.person_name, display_pool(pool)))
        clean = {'mic_type': pool}
    elif kind == 'unpin':
        if app.pinned_rf is None and not app.pinned_type:
            raise EditRefused('{} is not pinned.'.format(app.person_name))
        clean = {}
    else:
        raise EditRefused('Unknown change.')
    clean.update(name=app.person_name, line=app.on_line, from_rf=main.rf_number if main else None,
                 from_pool=app.mic_type)
    before = snapshot(plan)
    seq = (plan.edits.order_by('-seq').values_list('seq', flat=True).first() or 0) + 1
    made = MicPlanEdit.objects.create(plan=plan, seq=seq, kind=kind, key=key, value=clean, before=before,
                                      created_by=user)
    return _resolve(plan, before), made


@transaction.atomic
def undo(day, version, user=None):
    """Remove the last edit and re-solve, preferring the RFs from just before
    it, so the plan returns to what it was. Returns (plan, removed edit)."""
    plan = _locked(day, version)
    last = plan.edits.order_by('-seq').first()
    if last is None:
        raise EditRefused('Nothing to undo.')
    before = last.before
    batch = last.value.get('batch')
    if batch:        # "Use the showflow's numbers": its edits go together
        plan.edits.filter(pk__in=[e.pk for e in plan.edits.all() if e.value.get('batch') == batch]).delete()
    else:
        last.delete()
    return _resolve(plan, before), last


@transaction.atomic
def use_showflow(day, version, user=None):
    """Pin every wearing the showflow numbers to its number, as normal move
    edits sharing a batch: one re-solve, one Undo. The wearings are the ones
    the showflow's hosts rule gives (the batch keeps that rule on, see
    _showflow_hosts), so a host whose number goes to someone else is split.
    Numbers the rig has no channel for stay on the card. Returns (plan, count)."""
    plan = _locked(day, version)
    card = next((f for f in plan.flags if f['kind'] == SHOWFLOW_CARD), None)
    if not any(i['fits'] for i in (card['items'] if card else ())):
        raise EditRefused('Nothing here differs from the showflow.')
    R = solver.rig(solver_settings(plan_values(plan)))
    data, rows_by_part, _ = build_day(day, follow=True)
    apps = solver.appearances(data)[0]
    numbers = showflow_numbers(day, rows_by_part, apps)
    names = {p.key: p.name for p in data.people}
    lines = {r.pk: r.line_no for part_rows in rows_by_part.values() for r in part_rows}
    before = snapshot(plan)
    wanted = []
    for a in apps:
        entry = numbers.get(a.skey)
        want = showflow_rf(entry, R) if entry else None
        pool = (entry or {}).get('pool') or a.mic_type
        if want is not None and R.usable(want) and before.get(a.skey) != [want, pool]:
            wanted.append((a, want, pool))
    if not wanted:
        raise EditRefused('Nothing here differs from the showflow.')
    batch = secrets.token_hex(4)
    seq = plan.edits.order_by('-seq').values_list('seq', flat=True).first() or 0
    made = []
    for a, want, pool in wanted:
        seq += 1
        was = before.get(a.skey, [None, a.mic_type])
        made.append(MicPlanEdit(plan=plan, seq=seq, kind='move_rf', key=a.skey, before=before, created_by=user,
                                value={'rf': want, 'pool': pool, 'name': names.get(a.person, ''),
                                       'line': lines.get(a.on_row, ''), 'from_rf': was[0], 'from_pool': was[1],
                                       'batch': batch, 'count': len(wanted)}))
    MicPlanEdit.objects.bulk_create(made)
    return _resolve(plan, before), len(made)


def display_pool(pool):
    return 'handheld' if pool == solver.HH else 'body pack'


def _compare_card(day, rows_by_part, result, main, names, line, R):
    """The Review flag listing every appearance whose plan differs from the
    showflow's number, or None. ``items`` carry what "Use the showflow's
    numbers" needs; a person on one number in several wearings reads once."""
    numbers = showflow_numbers(day, rows_by_part, result.appearances)
    items, seen = [], set()
    for a in result.appearances:
        entry = numbers.get(a.skey)
        have = main.get(a.skey)
        if entry is None or have is None:
            continue
        want = showflow_rf(entry, R)
        if want == have and entry['pool'] in (None, a.mic_type):
            continue
        label = entry['label'] if want == entry['n'] else '{} (RF {})'.format(entry['label'], want)
        fits = R.usable(want)
        text = 'Showflow: {} on {} \u00b7 Plan: RF {}{}'.format(names.get(a.person, ''), label, have,
                                                               '' if fits else ' (not on this rig)')
        items.append({'key': a.skey, 'name': names.get(a.person, ''), 'label': label, 'want': want,
                      'pool': entry['pool'], 'plan': have, 'line': line(a.on_row), 'fits': fits, 'text': text,
                      'repeat': text in seen})
        seen.add(text)
    if not items:
        return None
    return {'kind': SHOWFLOW_CARD, 'row': None, 'person': None, 'items': items,
            'text': '; '.join(i['text'] for i in items if not i['repeat']) + '.'}


def _save(plan, data, rows_by_part, result, values, counts, fixed, edits, prev, prefer, misfits=None):
    """Store ``result`` as ``plan`` (version + 1), with what changed against
    ``prev`` ({skey: [rf, pool]}), who could not keep the RF ``prefer``
    gave them, and the edit log's Review flags (``misfits``: pins the rig
    no longer fits, see _fixed)."""
    if plan.pk:
        plan.appearances.all().delete()       # cascades assignments and actions
    rows = {r.pk: r for part_rows in rows_by_part.values() for r in part_rows}
    line = (lambda key: (rows[key].line_no or '#{}'.format(rows[key].order + 1))
            if key in rows else '')
    names = {p.key: p.name for p in data.people}
    seg_names = {s.key: s.name for s in data.segments}
    seg_out = []
    for s in data.segments:
        spill = result.spill.get(s.key)
        seg_out.append({'row': s.key, 'part': s.part, 'line': line(s.key), 'name': s.name, 't0': s.t0,
                        't1': s.t1, 'is_break': s.is_break, 'busy': result.busy.get(s.key, []),
                        'helpers': s.helpers, 'helper_busy': result.helper_busy.get(s.key, 0),
                        'spill': spill['minutes'] if spill else 0,
                        'spill_into': seg_names.get(spill['into'], '') if spill else ''})

    # What changed, and the Review flags only edits make.
    main = {result.appearances[a.appearance].skey: a.rf for a in result.assignments if not a.backup}
    def change(a, was):
        c = {'key': a.skey, 'name': names.get(a.person, ''), 'line': line(a.on_row), 'from': was[0],
             'to': main.get(a.skey), 'from_pool': was[1], 'to_pool': a.mic_type, 'pinned': a.skey in fixed.pins}
        c['text'] = describe_change(c)
        return c

    changes, moved = [], []
    for a in result.appearances:
        for was, out in ((prev.get(a.skey), changes), (prefer.get(a.skey), moved)):
            if was is not None and (was[0], was[1]) != (main.get(a.skey), a.mic_type):
                if out is changes or (a.skey not in fixed.pins and a.skey not in fixed.types):
                    out.append(change(a, was))
    flags = list(result.flags)
    if moved:
        flags.append({'kind': 'moved', 'row': None, 'person': None,
                      'text': 'Moved from the RF they had: {}.'.format('; '.join(c['text'] for c in moved))})
    R = solver.rig(solver_settings(values))
    for a in result.appearances:
        if a.skey in (misfits or {}):
            rf, pool = misfits[a.skey]
            flags.append({'kind': 'rig', 'row': a.on_row, 'person': a.person,
                          'text': 'Line {}: {} RF {} {} {} on this rig \u2014 now RF {} ({}).'.format(
                              line(a.on_row) or '?', "the showflow's" if a.skey in fixed.showflow else 'your',
                              rf, 'number' if a.skey in fixed.showflow else 'pin', 'is ' + misfit_text(rf, R),
                              main.get(a.skey), display_pool(pool or a.mic_type))})
    if values.get('showflow_numbers') != 'follow':
        card = _compare_card(plan.day, rows_by_part, result, main, names, line, R)
        if card:
            flags.append(card)
    keys = {a.skey for a in result.appearances}
    last = {}
    for e in edits:
        last[e.key] = e
    for key, e in last.items():
        if key not in keys and (key in fixed.pins or key in fixed.types):
            flags.append({'kind': 'unmatched', 'row': None, 'person': None,
                          'text': 'Your change to {} at line {} no longer matches the showflow ({}); '
                                  'it is kept but not applied.'.format(e.value.get('name', '?'),
                                                                       e.value.get('line', '?'),
                                                                       describe_edit(e))})

    plan.version += 1
    plan.settings = values
    plan.stale = False
    plan.segments = seg_out
    plan.flags = flags
    plan.packs = [{'rf': p.rf, 'pool': p.pool, 'label': p.label, 'host': p.host,
                   'backup_of': p.backup_of, 'spare': p.spare, 'over': p.over, 'swaps': p.swaps}
                  for p in result.packs]
    plan.swaps = result.swaps
    plan.policy_counts = counts
    plan.changes = changes
    plan.save()

    apps = {}
    for a in result.appearances:
        apps[a.key] = MicPlanAppearance.objects.create(
            plan=plan, key=a.key, skey=a.skey[:300], person_id=a.person, person_name=names.get(a.person, '')[:200],
            part_id=a.part, on_min=a.on, off_min=a.off, on_row_id=a.on_row, off_row_id=a.off_row,
            on_line=line(a.on_row), off_line=line(a.off_row), mic_type=a.mic_type, source=a.source,
            is_host=a.is_host, assumed=a.assumed[:200], note_row_id=a.note_row,
            pinned_rf=fixed.pins.get(a.skey), pinned_type=fixed.types.get(a.skey, ''),
            stage=[list(span) for span in a.stage])
    MicPlanAssignment.objects.bulk_create([
        MicPlanAssignment(appearance=apps[s.appearance], rf_number=s.rf, how=s.how, backup=s.backup)
        for s in result.assignments])
    MicPlanA2Action.objects.bulk_create([
        MicPlanA2Action(
            plan=plan, a2_index=a.a2_index, seq=a.seq, kind=a.kind, start_min=a.start_min,
            end_min=a.end_min, appearance=apps[a.appearance], person_id=a.person,
            person_name=a.person_name[:200], rf_number=a.rf_number, row_id=a.row,
            line=line(a.row), segment_id=a.segment, reason=a.reason, late=a.late, tight=a.tight,
            wait_min=a.wait_min, backup=a.backup)
        for a in result.actions])
    from .checks import prune
    prune(plan.day)
    return plan
