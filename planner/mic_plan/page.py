"""What the Mic Plan page shows, built from the stored plan (never re-solved):
the Showflow + plan rows of one part, the day's pack chart, Review cards and
stat tiles. plan.json is built from the same pieces (``plan_data``).
"""

from planner.models import MicPlanA2Action, MicPlanAppearance

from .display import format_action
from .solver import hm

BUSY_WARN, BUSY_HOT = 0.7, 0.9       # A2-busy meter: amber from 70 %, red from 90 %
LONG_WAIT = 10                       # a de-mic this long after the catch is shown in amber


def first_name(name):
    words = (name or '').replace('Dr. ', '').split()
    return words[0] if words else name


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
        out[s['row']] = dict(s, meters=[m for m in meters if m['busy']], t0_label=hm(s['t0']),
                             t1_label=hm(s['t1']), spill_text=spill)
    return out


def showflow_rows(part, rows, events, plan, apps, actions):
    """Annotate ``rows`` (one part, in order) for the Showflow + plan table."""
    a2_count = max(1, plan.settings.get('a2_count', 1)) if plan else 1
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
            'rf': rf_of(app) if app else None})
    def cued_here(row_pk, person_id):
        return any(c['person'] == person_id and c['kind'] in ('send', 'catch') for c in chips.get(row_pk, ()))

    for a in apps:
        if a.source == 'cue' or a.part_id != part.pk:
            continue
        rf = rf_of(a)
        if not cued_here(a.on_row_id, a.person_id):
            chips.setdefault(a.on_row_id, []).append(
                {'kind': 'on', 'person': a.person_id, 'name': first_name(a.person_name), 'rf': rf})
        if a.off_row_id and not a.is_host and not cued_here(a.off_row_id, a.person_id):
            chips.setdefault(a.off_row_id, []).append(
                {'kind': 'off', 'person': a.person_id, 'name': first_name(a.person_name), 'rf': rf})

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


def pack_chart(plan, apps, actions):
    """Lanes for the pack chart: one per RF, bars as percentages of the day."""
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
    for a in apps:
        for s in a.assignments.all():
            key = (a.pk, s.backup)
            worn_from = mic.get(key, a.on_min)
            worn_to = demic.get(key, a.off_min)
            slots.setdefault(s.rf_number, []).append({
                'person': a.person_id, 'name': a.person_name, 'first': first_name(a.person_name),
                'on': a.on_min, 'off': a.off_min, 'from': worn_from, 'to': worn_to, 'backup': s.backup})
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

    lanes = []
    for p in plan.packs:
        if p.get('spare'):
            sub = 'SPARE'
        elif p.get('backup_of'):
            sub = p.get('label') or 'BACKUP'
        elif p.get('host'):
            sub = 'HOST'
        else:
            n = len({s['person'] for s in slots.get(p['rf'], [])})
            sub = '{} {}'.format(n, 'person' if n == 1 else 'people')
        bars = []
        for s in slots.get(p['rf'], []):
            tip = "{} on RF {}: mic'd {}, on stage {}–{}, de-mic {}".format(
                s['name'], p['rf'], hm(s['from']), hm(s['on']), hm(s['off']), hm(s['to']))
            bars.append(dict(s, worn_left=pct(s['from']), worn_width=width(s['from'], s['to']),
                             stage_left=pct(s['on']), stage_width=width(s['on'], s['off']), tip=tip))
        lanes.append({'rf': p['rf'], 'pool': p['pool'], 'sub': sub, 'bars': bars,
                      'host': p.get('host'), 'spare': p.get('spare')})
    bands = [{'name': s['name'], 'left': pct(s['t0']), 'width': width(s['t0'], s['t1']),
              'is_break': s['is_break'], 'label': ' '.join((s['name'] or '').split()[:3])
              if s['t1'] - s['t0'] >= 14 else '', 'tip': '{} {}–{}'.format(s['name'], hm(s['t0']), hm(s['t1']))}
             for s in plan.segments]
    ticks = [{'left': pct(t), 'label': hm(t)} for t in range(t0, t1 + 1, 60)]
    return {'lanes': lanes, 'bands': bands, 'ticks': ticks}


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
            cards.append(_card(w['kind'], labels.get(w['kind'], w['kind']), w['text'], part, row,
                               w.get('person'), numbers, note))
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
        plan_labels = {'late': 'Late', 'tight': 'Tight', 'shortage': 'Short', 'spill': 'Spill',
                       'reuse': 'Mid-session', 'break': 'Turnover'}
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
        if p.flags.get('gone'):
            cards.append(_card('gone', labels.get('gone', 'Gone'),
                               '{} is no longer in this showflow but has a merge, Presenter link or '
                               'mic hint you set. Remove them in People if they are not needed.'
                               .format(p.display_name), None, None, p.pk, numbers, None))
    return cards


def _card(kind, label, text, part, row, person, numbers, note, plan=False):
    return {'kind': kind, 'label': label, 'text': text, 'part': part.pk if part else None,
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
    }


POLICY_NAMES = {'recycle_at_breaks': 'Recycle at breaks', 'fewest_packs': 'Fewest packs'}


def settings_summary(values):
    # Plans from before PR 2.2 have no pack_policy: they used fewest_packs.
    return '{} · {} A2 · mic {} · de-mic {} · lead {} · margin {} min'.format(
        POLICY_NAMES[values.get('pack_policy', 'fewest_packs')], values.get('a2_count'),
        values.get('mic_min'), values.get('demic_min'), values.get('premic_lead_min'), values.get('margin_min'))


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
        'appearances': [{
            'key': a.key, 'person': a.person_id, 'name': a.person_name, 'part': a.part_id,
            'on_min': a.on_min, 'off_min': a.off_min, 'on_row': a.on_row_id, 'off_row': a.off_row_id,
            'on_line': a.on_line, 'off_line': a.off_line, 'mic_type': a.mic_type, 'source': a.source,
            'is_host': a.is_host, 'assumed': a.assumed, 'pinned_rf': a.pinned_rf,
        } for a in apps],
        'assignments': [{'appearance': a.key, 'rf_number': s.rf_number, 'how': s.how, 'backup': s.backup}
                        for a in apps for s in a.assignments.all()],
        'actions': [dict(format_action(act, a2_count), **{
            'a2_index': act.a2_index, 'seq': act.seq, 'kind': act.kind, 'start_min': act.start_min,
            'end_min': act.end_min, 'appearance': act.appearance.key, 'person': act.person_id,
            'rf_number': act.rf_number, 'row': act.row_id, 'line_no': act.line, 'segment': act.segment_id,
            'late': act.late, 'tight': act.tight, 'wait_min': act.wait_min, 'backup': act.backup,
        }) for act in actions],
    }
