"""Generate a show day's draft mic plan: build the solver's inputs from what
the importer stored, run ``solver.solve`` and save the result as the day's
MicPlan (replacing the last draft, version + 1). Nothing here writes to Mic
Tracker.
"""

import logging
import time

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
                   'body_pack_count', 'hh_count', 'emergency_spare_hh')


def project_settings(project):
    return MicPlanSettings.objects.get_or_create(project=project)[0]


def settings_dict(obj):
    return {name: getattr(obj, name) for name in SETTINGS_FIELDS}


def mark_stale(day):
    """The day's imports, people or hints changed: its plan no longer matches."""
    MicPlan.objects.filter(day=day, stale=False).update(stale=True)


def _segments(part, rows):
    """solver.Segment for each segment heading of ``part`` (rows in order)."""
    parser_rows = [r.as_parser_row() for r in rows]
    starts = [k for k, r in enumerate(rows) if r.is_segment]
    out = []
    for k, a in enumerate(starts):
        b = starts[k + 1] if k + 1 < len(starts) else len(rows)
        head = rows[a]
        if head.segment_t0 is None:
            continue
        name, is_break = segment_heading(parser_rows, a, b)
        t1 = head.segment_t1 if head.segment_t1 is not None else head.segment_t0
        out.append(solver.Segment(key=head.pk, part=part.pk, start=head.order, end=rows[b - 1].order + 1,
                                  name=name, t0=head.segment_t0, t1=max(t1, head.segment_t0 + 1),
                                  is_break=is_break))
    return out


def build_day(day):
    """(solver.Day, {part pk: rows}, cue_mode)."""
    parts = active_parts(day)
    rows_by_part, rows, segments = {}, [], []
    for part in parts:
        part_rows = list(part.rows.order_by('order'))
        rows_by_part[part.pk] = part_rows
        rows += [solver.Row(r.pk, part.pk, r.order, r.line_no, r.est_time) for r in part_rows]
        segments += _segments(part, part_rows)
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


@transaction.atomic
def generate(day, user=None):
    """Solve ``day`` with its project's settings and save it as the day's plan."""
    values = settings_dict(project_settings(day.project))
    data, rows_by_part, mode = build_day(day)
    started = time.monotonic()
    result = solver.solve(data, solver_settings(values))
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
    seg_out = [{'row': s.key, 'part': s.part, 'line': line(s.key), 'name': s.name, 't0': s.t0,
                't1': s.t1, 'is_break': s.is_break, 'busy': result.busy.get(s.key, [])}
               for s in data.segments]
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
