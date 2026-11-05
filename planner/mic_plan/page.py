"""What the Mic Plan page shows, built from the stored plan (never re-solved):
the Showflow + plan rows of one part, the day's pack chart, Review cards and
stat tiles. plan.json is built from the same pieces (``plan_data``).
"""

from planner.models import MicPlanA2Action, MicPlanAppearance

from .display import TX_WORDS, first_name, format_action, overlap_warning, rig_text
from .parser import description_candidates
from .planning import plan_rig, plan_values
from .solver import hm, is_helper

BUSY_WARN, BUSY_HOT = 0.7, 0.9       # A2-busy meter: amber from 70 %, red from 90 %
LONG_WAIT = 10                       # a de-mic this long after the catch is shown in amber


def _level(ratio):
    return 'hot' if ratio >= BUSY_HOT else 'mid' if ratio >= BUSY_WARN else ''


def load(plan):
    """The plan's appearances (assignments loaded) and actions."""
    if plan is None:
        return [], []
    apps = list(MicPlanAppearance.objects.filter(plan=plan).prefetch_related('assignments'))
    actions = list(MicPlanA2Action.objects.filter(plan=plan).select_related('appearance'))
    return apps, actions


def rf_of(app, backup=False):
    for s in app.assignments.all():
        if s.backup == backup:
            return s.rf_number
    return None


def segment_rows(plan):
    """{heading row pk: segment dict with busy meters}."""
    out = {}
    if plan is None:
        return out
    a2 = max(1, plan.settings.get('a2_count', 1))
    for s in plan.segments:
        span = max(1, s['t1'] - s['t0'])
        meters = []
        for k, busy in enumerate(s.get('busy') or []):
            ratio = busy / span
            meters.append({'a2': 'A2 {}'.format(k + 1) if a2 > 1 else 'A2', 'busy': round(busy),
                           'span': round(span), 'pct': min(100, round(ratio * 100)), 'level': _level(ratio)})
        spill = ''
        if s.get('spill'):
            spill = '+{} min into {}'.format(s['spill'], s.get('spill_into') or 'the next segment')
        # The de-mic helpers' minutes, never in an A2's meter.
        out[s['row']] = dict(s, meters=[m for m in meters if m['busy']], helper=round(s.get('helper_busy') or 0),
                             t0_label=hm(s['t0']),
                             t1_label=hm(s['t1']), spill_text=spill)
    return out


def changed_keys(plan):
    return {c['key'] for c in (plan.changes if plan else ())}


def _edit_attrs(app, changed):
    """What a bar or chip needs to be moved, and its marks."""
    if app is None:
        return {'key': '', 'pinned': False, 'changed': False, 'pool': ''}
    return {'key': app.skey, 'pinned': app.pinned_rf is not None or bool(app.pinned_type),
            'changed': app.skey in changed, 'pool': app.mic_type, 'on': app.on_min}


def showflow_rows(part, rows, events, plan, apps, actions):
    """Annotate ``rows`` (one part, in order) for the Showflow + plan table."""
    a2_count = max(1, plan.settings.get('a2_count', 1)) if plan else 1
    changed = changed_keys(plan)
    by_person = {}
    for a in apps:
        if a.person_id:
            by_person.setdefault(a.person_id, []).append(a)

    def app_at(person_id, minute, row_pk):
        mine = by_person.get(person_id, [])
        for a in mine:
            if row_pk in (a.on_row_id, a.off_row_id):
                return a
        if minute is not None:
            for a in mine:
                if a.on_min - 1 <= minute <= a.off_min + 1:
                    return a
            return min(mine, key=lambda a: abs(a.on_min - minute), default=None)
        return mine[0] if mine else None

    chips = {}
    for e in events:
        app = app_at(e.person_id, e.event_min, e.row_id)
        chips.setdefault(e.row_id, []).append({
            'kind': e.kind, 'person': e.person_id, 'name': first_name(e.person.display_name),
            'rf': rf_of(app) if app else None, **_edit_attrs(app, changed)})
    def cued_here(row_pk, person_id):
        return any(c['person'] == person_id and c['kind'] in ('send', 'catch') for c in chips.get(row_pk, ()))

    for a in apps:
        if a.source == 'cue' or a.part_id != part.pk:
            continue
        rf = rf_of(a)
        if not cued_here(a.on_row_id, a.person_id):
            chips.setdefault(a.on_row_id, []).append(
                {'kind': 'on', 'person': a.person_id, 'name': first_name(a.person_name), 'rf': rf,
                 **_edit_attrs(a, changed)})
        if a.off_row_id and not a.is_host and not cued_here(a.off_row_id, a.person_id):
            chips.setdefault(a.off_row_id, []).append(
                {'kind': 'off', 'person': a.person_id, 'name': first_name(a.person_name), 'rf': rf,
                 **_edit_attrs(a, changed)})

    acts = {}
    for act in actions:
        if act.row_id is None:
            continue
        f = format_action(act, a2_count)
        f.update(kind=act.kind, person=act.person_id, rf_number=act.rf_number, late=act.late,
                 tight=act.tight, long_wait=act.kind == 'demic' and act.wait_min > LONG_WAIT)
        acts.setdefault(act.row_id, []).append(f)

    segs = segment_rows(plan)
    for row in rows:
        row.chips = chips.get(row.pk, [])
        row.acts = acts.get(row.pk, [])
        row.segment = segs.get(row.pk)
        row.who = sorted({c['person'] for c in row.chips if c['person']} |
                         {a['person'] for a in row.acts if a['person']} | set(getattr(row, 'people_ids', ())))
        row.rfs = sorted({c['rf'] for c in row.chips if c['rf']} | {a['rf_number'] for a in row.acts})
        row.empty = row.is_blank and not row.chips and not row.acts
    return rows


def part_spans(segments):
    """{part pk: (first minute, last minute)} of a plan's segments."""
    spans = {}
    for s in segments:
        a, b = spans.get(s['part'], (s['t0'], s['t1']))
        spans[s['part']] = (min(a, s['t0']), max(b, s['t1']))
    return spans


def overlapping_parts(segments):
    """[(part pk, part pk)] of parts whose segments run at the same time
    (one ending as the next starts is not an overlap)."""
    spans = sorted(part_spans(segments).items(), key=lambda kv: (kv[1], kv[0]))
    return [(p, q) for k, (p, (a0, a1)) in enumerate(spans) for q, (b0, b1) in spans[k + 1:]
            if b0 < a1 and a0 < b1]


def part_numbers(parts):
    return {p.pk: k + 1 for k, p in enumerate(parts)}


def overlap_warnings(plan, parts):
    """The plan treats every part of a day as one stage (#169): a warning
    for each pair of parts that overlap in time."""
    if plan is None:
        return []
    numbers = part_numbers(parts)
    pairs = {tuple(sorted((numbers[p], numbers[q]))) for p, q in overlapping_parts(plan.segments)
             if p in numbers and q in numbers}
    return [overlap_warning(n, m) for n, m in sorted(pairs)]


def pack_chart(plan, apps, actions, parts=()):
    """Lanes for the pack chart: one per RF, bars as percentages of the day.
    With a rig, one per channel of it (unused ones too, spares as SPARE),
    then any the rig is short of (over). Segment bands sit in one header
    strip, or one strip per part when parts overlap in time (#168)."""
    if plan is None or not plan.packs:
        return None
    mic = {}
    demic = {}
    for act in actions:
        key = (act.appearance_id, act.backup)
        if act.kind == 'mic':
            mic[key] = act.start_min
        else:
            demic[key] = act.end_min
    slots = {}
    changed = changed_keys(plan)
    for a in apps:
        for s in a.assignments.all():
            key = (a.pk, s.backup)
            worn_from = mic.get(key, a.on_min)
            worn_to = demic.get(key, a.off_min)
            slots.setdefault(s.rf_number, []).append({
                'person': a.person_id, 'name': a.person_name, 'first': first_name(a.person_name),
                'on': a.on_min, 'off': a.off_min, 'from': worn_from, 'to': worn_to, 'backup': s.backup,
                **_edit_attrs(a, changed)})
    times = [t for ss in slots.values() for s in ss for t in (s['from'], s['to'])]
    times += [s['t0'] for s in plan.segments] + [s['t1'] for s in plan.segments]
    if not times:
        return None
    t0 = int(min(times) // 60 * 60)
    t1 = int(-(-max(times) // 60) * 60)
    span = max(1, t1 - t0)

    def pct(t):
        return round((t - t0) / span * 100, 3)

    def width(a, b):
        return round(max(0.2, (b - a) / span * 100), 3)

    R = plan_rig(plan)
    packs = list(plan.packs)
    if R.set:
        have = {p['rf'] for p in packs}
        packs += [{'rf': c, 'pool': pool, 'unused': True} for pool in ('body', 'HH')
                  for c in R.channels_of(pool) if c not in have]
        packs += [{'rf': c, 'pool': 'HH', 'spare': True} for c in R.spare_channels() if c not in have]
        packs.sort(key=lambda p: p['rf'])
    lanes = []
    for p in packs:
        if p.get('spare'):
            sub = 'SPARE'
        elif p.get('backup_of'):
            sub = p.get('label') or 'BACKUP'
        elif p.get('host'):
            sub = 'HOST'
        elif p.get('unused'):
            sub = 'unused'
        elif p.get('over'):
            sub = 'OVER the rig'
        else:
            n = len({s['person'] for s in slots.get(p['rf'], [])})
            sub = '{} {}'.format(n, 'person' if n == 1 else 'people')
        bars = []
        for s in slots.get(p['rf'], []):
            tip = "{} on RF {}: mic'd {}, on stage {}–{}, de-mic {}".format(
                s['name'], p['rf'], hm(s['from']), hm(s['on']), hm(s['off']), hm(s['to']))
            bars.append(dict(s, worn_left=pct(s['from']), worn_width=width(s['from'], s['to']),
                             stage_left=pct(s['on']), stage_width=width(s['on'], s['off']), tip=tip))
        conflict = any(a['from'] < b['to'] and b['from'] < a['to'] for k, a in enumerate(slots.get(p['rf'], []))
                       for b in slots.get(p['rf'], [])[k + 1:] if not a['backup'] and not b['backup'])
        # With a rig a lane is its channel's zone; the transmitter it needs
        # is shown when that is the other type, or changes during the day.
        zone = R.pool_at(p['rf']) if R.set else p['pool']
        pool = zone if zone in ('body', 'HH') else p['pool']
        tx = ''
        if not p.get('spare') and not p.get('unused'):
            kinds = [p['pool']] + [w['to'] for w in p.get('swaps') or ()]
            if len(kinds) > 1:
                tx = ' \u2192 '.join(TX_WORDS[k] for k in kinds)
            elif R.set and p['pool'] != pool:
                tx = 'needs ' + TX_WORDS[p['pool']]
        lanes.append({'rf': p['rf'], 'pool': pool, 'tx': tx, 'sub': sub, 'bars': bars,
                      'host': p.get('host'), 'spare': p.get('spare'), 'backup': bool(p.get('backup_of')),
                      'unused': p.get('unused', False), 'over': p.get('over', False), 'conflict': conflict})
    bands = [{'name': s['name'], 'left': pct(s['t0']), 'width': width(s['t0'], s['t1']),
              'is_break': s['is_break'], 'label': ' '.join((s['name'] or '').split()[:3])
              if s['t1'] - s['t0'] >= 14 else '', 'tip': '{} {}–{}'.format(s['name'], hm(s['t0']), hm(s['t1']))}
             for s in plan.segments]
    if overlapping_parts(plan.segments):
        numbers = part_numbers(parts)
        seen = list(dict.fromkeys(s['part'] for s in plan.segments))
        order = sorted(seen, key=lambda pk: (numbers.get(pk, len(seen) + 1), seen.index(pk)))
        strips = [{'label': 'Part {}'.format(numbers[pk]) if pk in numbers else 'Part',
                   'bands': [b for b, s in zip(bands, plan.segments) if s['part'] == pk]} for pk in order]
    else:
        strips = [{'label': '', 'bands': bands}]
    ticks = [{'left': pct(t), 'label': hm(t)} for t in range(t0, t1 + 1, 60)]
    regular = [p['rf'] for p in plan.packs if not p.get('spare') and not p.get('backup_of')]
    # A new pack lane only with no rig: with one, every channel has a lane.
    return {'lanes': lanes, 'bands': bands, 'strips': strips, 'ticks': ticks,
            'new_rf': None if R.set else max(regular, default=0) + 1}


def unused_channels(plan):
    """'15–20, 23': the rig's channels the plan leaves unused (spares
    aside), or '' (none, or no rig)."""
    R = plan_rig(plan)
    if not R.set:
        return ''
    have = {p['rf'] for p in plan.packs}
    free = [c for c in range(1, R.first_spare) if c not in have]
    runs = []
    for c in free:
        if runs and c == runs[-1][1] + 1:
            runs[-1][1] = c
        else:
            runs.append([c, c])
    return ', '.join(str(a) if a == b else '{}\u2013{}'.format(a, b) for a, b in runs)


def lane_windows(chart):
    """For the move menus and drag targets: each lane that can take a move,
    with when it is worn and by whom (minutes; JSON for mic_plan.js)."""
    if chart is None:
        return []
    return [{'rf': lane['rf'], 'pool': lane['pool'],
             'worn': [[b['from'], b['to'], b['key'], b['first']] for b in lane['bars']]}
            for lane in chart['lanes'] if not lane['spare'] and not lane['backup'] and not lane['over']]


def review_cards(parts, plan, apps, people, labels):
    """Parser flags of every part, the plan's own flags and "gone" people, as
    cards; each links to its part and line. An assumption the plan made
    about a flagged line is shown on that card."""
    rows = {}
    for part in parts:
        for r in part.rows.all():
            rows[r.pk] = (part, r)
    by_part_order = {(part.pk, r.order): r for part, r in rows.values()}
    assumed = {}
    for a in apps:
        if a.assumed and a.note_row_id:
            assumed.setdefault((a.person_id, a.note_row_id), a.assumed)
    numbers = {part.pk: k + 1 for k, part in enumerate(parts)}
    cards = []
    used = set()
    for part in parts:
        for w in part.warnings:
            row = by_part_order.get((part.pk, w.get('row_order'))) if w.get('row_order') is not None else None
            note = assumed.get((w.get('person'), row.pk)) if row else None
            if note:
                used.add((w.get('person'), row.pk))
            card = _card(w['kind'], labels.get(w['kind'], w['kind']), w['text'], part, row,
                         w.get('person'), numbers, note)
            if w['kind'] == 'description_names' and row is not None:
                # "Add people from this line": the names it brings on, to check.
                card['candidates'] = description_candidates(row.description)
            cards.append(card)
    # An assumption about a line the parser did not flag goes on the parser's
    # card for the same person inside that appearance (e.g. "No cue" two
    # lines further down), and only otherwise gets a card of its own.
    for a in apps:
        if not a.assumed or (a.person_id, a.note_row_id) in used:
            continue
        for c in cards:
            row = by_part_order.get((c['part'], c['row_order']))
            if (c['person'] == a.person_id and c['note'] is None and c['part'] == a.part_id
                    and row is not None and row.est_time is not None
                    and a.on_min - 1 <= row.est_time <= a.off_min + 1
                    and c['kind'] in ('no_cue', 'never_caught', 'caught_but_listed')):
                c['note'] = a.assumed
                used.add((a.person_id, a.note_row_id))
                break
    if plan is not None:
        plan_labels = {'late': 'Late', 'tight': 'Tight', 'shortage': 'Short', 'spill': 'Spill', 'who_both': 'Both?',
                       'reuse': 'Mid-session', 'break': 'Turnover', 'conflict': 'Conflict',
                       'pin_reuse': 'Mid-session', 'unmatched': 'Your change', 'moved': 'Moved',
                       'rig_use': 'Transmitter', 'swap': 'Swap', 'swap_mid': 'Swap mid-session', 'rig': 'Rig'}
        for f in plan.flags:
            part, row = rows.get(f.get('row'), (None, None))
            cards.append(_card(f['kind'], plan_labels.get(f['kind'], f['kind']), f['text'], part, row,
                               f.get('person'), numbers, None, plan=True))
        for a in apps:
            if a.assumed and (a.person_id, a.note_row_id) not in used:
                part, row = rows.get(a.note_row_id, (None, None))
                cards.append(_card('assumed', 'Assumed', '{}: {}'.format(a.person_name, a.assumed),
                                   part, row, a.person_id, numbers, None, plan=True))
    for p in people:
        for line in p.flags.get('added_missing', []):
            cards.append(_card('added_missing', labels.get('added_missing', 'Added'),
                               'Line {} no longer in this showflow: {} was added on at it by hand. Kept, but '
                               'not in the plan until you move or remove it in People.'.format(line, p.display_name),
                               None, None, p.pk, numbers, None))
        if p.flags.get('gone'):
            cards.append(_card('gone', labels.get('gone', 'Gone'),
                               '{} is no longer in this showflow but has a merge, Presenter link or '
                               'mic hint you set. Remove them in People if they are not needed.'
                               .format(p.display_name), None, None, p.pk, numbers, None))
    return cards


def _card(kind, label, text, part, row, person, numbers, note, plan=False):
    return {'kind': kind, 'label': label, 'text': text, 'part': part.pk if part else None,
            'row_pk': row.pk if row else None,
            'part_no': numbers.get(part.pk) if part else None, 'row_order': row.order if row else None,
            'line': (row.line_no or '#{}'.format(row.order + 1)) if row else '', 'person': person,
            'note': note, 'plan': plan}


def stats(plan):
    if plan is None:
        return None
    regular = [p for p in plan.packs if not p.get('spare')]
    # A segment shorter than one mic is always "busy": left out of the count.
    shortest = plan.settings.get('mic_min', 1)
    hot = sum(1 for s in plan.segments
              if s['t1'] - s['t0'] >= shortest
              and any(b / (s['t1'] - s['t0']) >= BUSY_HOT for b in (s.get('busy') or [])))
    return {
        'body': sum(1 for p in regular if p['pool'] == 'body'),
        'hh': sum(1 for p in regular if p['pool'] == 'HH'),
        'hosts': sum(1 for p in regular if p.get('host')),
        'backups': sum(1 for p in regular if p.get('backup_of')),
        'spare': sum(1 for p in plan.packs if p.get('spare')),
        'swaps': plan.swaps,
        'hot': hot,
        'conflicts': sum(1 for f in plan.flags if f['kind'] == 'conflict'),
    }


POLICY_NAMES = {'recycle_at_breaks': 'Recycle at breaks', 'fewest_packs': 'Fewest packs'}


def settings_summary(values):
    """``values``: planning.plan_values (or the project's settings)."""
    return '{} · {} A2 · mic {} · de-mic {} · lead {} · margin {} min · {}'.format(
        POLICY_NAMES[values['pack_policy']], values.get('a2_count'), values.get('mic_min'),
        values.get('demic_min'), values.get('premic_lead_min'), values.get('margin_min'), rig_text(values))


def policy_counts_text(counts):
    """"Recycle at breaks: 14 body · Fewest packs: 9 body", or '' (no counts)."""
    out = []
    for policy, name in POLICY_NAMES.items():
        c = counts.get(policy)
        if c:
            out.append('{}: {} body{}'.format(name, c['body'], ' + {} HH'.format(c['hh']) if c['hh'] else ''))
    return ' · '.join(out)


def plan_data(plan, apps, actions):
    """plan.json: the same stored data the page renders from."""
    a2_count = max(1, plan.settings.get('a2_count', 1))
    return {
        'version': plan.version,
        'generated_at': plan.generated_at.isoformat(),
        'stale': plan.stale,
        'cue_mode': plan.cue_mode,
        'settings': plan.settings,
        'segments': plan.segments,
        'packs': plan.packs,
        'swaps': plan.swaps,
        'flags': plan.flags,
        'changes': plan.changes,
        'appearances': [{
            'key': a.key, 'person': a.person_id, 'name': a.person_name, 'part': a.part_id,
            'on_min': a.on_min, 'off_min': a.off_min, 'on_row': a.on_row_id, 'off_row': a.off_row_id,
            'on_line': a.on_line, 'off_line': a.off_line, 'mic_type': a.mic_type, 'source': a.source,
            'is_host': a.is_host, 'assumed': a.assumed, 'skey': a.skey, 'pinned_rf': a.pinned_rf,
            'pinned_type': a.pinned_type,
        } for a in apps],
        'assignments': [{'appearance': a.key, 'rf_number': s.rf_number, 'how': s.how, 'backup': s.backup}
                        for a in apps for s in a.assignments.all()],
        'actions': [dict(format_action(act, a2_count), **{
            'a2_index': act.a2_index, 'helper': is_helper(act), 'seq': act.seq, 'kind': act.kind,
            'start_min': act.start_min,
            'end_min': act.end_min, 'appearance': act.appearance.key, 'person': act.person_id,
            'rf_number': act.rf_number, 'row': act.row_id, 'line_no': act.line, 'segment': act.segment_id,
            'late': act.late, 'tight': act.tight, 'wait_min': act.wait_min, 'backup': act.backup,
        }) for act in actions],
    }


ESTIMATE_WARNING = ('Based on line estimates: part of this day has no send/catch cues, so each person is '
                    'on from a line naming them to an exit line or the end of their segment.')
STALE_WARNING = 'The showflow changed after this plan was made. Re-generate it on the Mic Plan page.'


def plan_header(plan, parts):
    """What the A2 schedule and the PDF print about the plan: version,
    when it was made and last edited, the settings and every warning.
    "Edited" is the latest edit still in the log (an undo removes its edit)."""
    edits = list(plan.edits.order_by('seq'))
    values = plan_values(plan)
    warnings = []
    if plan.stale:
        warnings.append(STALE_WARNING)
    if plan.cue_mode == 'line estimates':
        warnings.append(ESTIMATE_WARNING)
    warnings += overlap_warnings(plan, parts)
    return {
        'version': plan.version,
        'generated_at': plan.generated_at,
        'edited_at': max((e.created_at for e in edits), default=None),
        'edit_count': len(edits),
        'policy': POLICY_NAMES[values['pack_policy']],
        'settings': settings_summary(values),
        'cue_mode': plan.cue_mode,
        'stale': plan.stale,
        'warnings': warnings,
    }
