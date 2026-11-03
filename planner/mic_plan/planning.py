"""Generate a show day's draft mic plan: build the solver's inputs from what
the importer stored, run ``solver.solve`` and save the result as the day's
MicPlan (replacing the last draft, version + 1). Nothing here writes to Mic
Tracker.
"""

import logging
import time
from dataclasses import replace

from django.db import transaction
from django.utils import timezone

from planner.models import (
    MicPlan, MicPlanA2Action, MicPlanAppearance, MicPlanAssignment, MicPlanSettings, ShowflowEvent,
)

from . import solver
from .importer import active_parts
from .parser import NO_CUE_MIN_COVERAGE, segment_heading

logger = logging.getLogger(__name__)

SETTINGS_FIELDS = ('a2_count', 'mic_min', 'demic_min', 'premic_lead_min', 'margin_min',
                   'body_pack_count', 'hh_count', 'emergency_spare_hh', 'pack_policy')
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
    {row, name, t0, t1, end, detected, override, is_break}. ``override`` is
    the stored hand-set value, or None."""
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
        override = (part.break_overrides or {}).get(segment_line(head))
        out.append({'row': head, 'name': name, 't0': head.segment_t0, 't1': max(t1, head.segment_t0 + 1),
                    'end': rows[b - 1].order + 1, 'detected': detected, 'override': override,
                    'is_break': override['is_break'] if override else detected})
    return out


def set_break(part, row, is_break, user):
    """Mark segment ``row`` of ``part`` a break or not. Back to the detected
    value clears the override. The day's plan no longer matches."""
    seg = next((s for s in part_segments(part, list(part.rows.order_by('order')), named_orders(part.day, part))
                if s['row'].pk == row.pk), None)
    if seg is None:
        raise ValueError('Not a segment heading.')
    overrides = dict(part.break_overrides or {})
    if is_break == seg['detected']:
        overrides.pop(segment_line(row), None)
    else:
        overrides[segment_line(row)] = {'is_break': is_break, 'by': user.pk if user else None,
                                        'by_name': user.get_username() if user else '',
                                        'at': timezone.now().isoformat()}
    part.break_overrides = overrides
    part.save(update_fields=['break_overrides'])
    mark_stale(part.day)


def _segments(part, rows, named):
    """solver.Segment for each segment heading of ``part`` (rows in order)."""
    return [solver.Segment(key=s['row'].pk, part=part.pk, start=s['row'].order, end=s['end'], name=s['name'],
                           t0=s['t0'], t1=s['t1'], is_break=s['is_break'])
            for s in part_segments(part, rows, named)]


def build_day(day):
    """(solver.Day, {part pk: rows}, cue_mode)."""
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

    people, listings = [], {}
    for p in day.showflow_people.all():
        if p.flags.get('gone'):
            continue
        people.append(solver.Person(
            key=p.pk, name=p.display_name, mic_type=solver.HH if p.mic_hint == 'HH' else solver.BODY,
            backup=(solver.HH if p.backup_mic_type == 'HH' else solver.BODY)
            if p.mic_hint == 'backup' else None))
        keys = []
        for part in parts:
            by_order = {r.order: r.pk for r in rows_by_part[part.pk]}
            skip = cue_rows.get((p.pk, part.pk), set())
            keys += [by_order[o] for o in p.flags.get('rows', {}).get(str(part.pk), [])
                     if o in by_order and o not in skip]
        listings[p.pk] = keys

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
                      listings=listings, cued_parts=frozenset(cued))
    mode = 'cues' if parts and len(cued) == len(parts) else 'line estimates'
    return data, rows_by_part, mode


def solver_settings(values):
    return solver.Settings(**{k: values[k] for k in SETTINGS_FIELDS})


def policy_counts(data, settings):
    """{policy: {body, hh, mid_session}}: the packs each policy needs for the
    day at ``settings`` with the pack counts blank."""
    out = {}
    for policy in POLICIES:
        s = solver.summary(solver.solve(
            data, replace(settings, pack_policy=policy, body_pack_count=None, hh_count=None), suggest=False))
        out[policy] = {'body': s['body'], 'hh': s['hh'], 'mid_session': s['mid_session']}
    return out


@transaction.atomic
def generate(day, user=None):
    """Solve ``day`` with its project's settings and save it as the day's plan."""
    values = settings_dict(project_settings(day.project))
    data, rows_by_part, mode = build_day(day)
    started = time.monotonic()
    result = solver.solve(data, solver_settings(values))
    counts = policy_counts(data, solver_settings(values))
    logger.info('Mic Plan generate: %d appearances, %d actions, %.3fs (project %s, day %s)',
                len(result.appearances), len(result.actions), time.monotonic() - started,
                day.project_id, day.pk)

    plan = MicPlan.objects.select_for_update().filter(day=day).first()
    if plan is None:
        plan = MicPlan(day=day)
    else:
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
                        'spill': spill['minutes'] if spill else 0,
                        'spill_into': seg_names.get(spill['into'], '') if spill else ''})
    plan.generated_at = timezone.now()
    plan.generated_by = user
    plan.version += 1
    plan.settings = values
    plan.cue_mode = mode
    plan.stale = False
    plan.segments = seg_out
    plan.flags = result.flags
    plan.packs = [{'rf': p.rf, 'pool': p.pool, 'label': p.label, 'host': p.host,
                   'backup_of': p.backup_of, 'spare': p.spare} for p in result.packs]
    plan.swaps = result.swaps
    plan.policy_counts = counts
    plan.save()

    apps = {}
    for a in result.appearances:
        apps[a.key] = MicPlanAppearance.objects.create(
            plan=plan, key=a.key, person_id=a.person, person_name=names.get(a.person, '')[:200],
            part_id=a.part, on_min=a.on, off_min=a.off, on_row_id=a.on_row, off_row_id=a.off_row,
            on_line=line(a.on_row), off_line=line(a.off_row), mic_type=a.mic_type, source=a.source,
            is_host=a.is_host, assumed=a.assumed[:200], note_row_id=a.note_row)
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
    return plan
