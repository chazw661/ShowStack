"""The A2 schedule of a stored plan: one A2's actions grouped into sessions,
then segments in showflow order. Read by the schedule screen and the PDF, so
both group and mark the same way. Never re-solves.
"""

from bisect import bisect_right
from types import SimpleNamespace

from .display import MARKS, format_action, swap_line, swap_words, turnover_text
from .solver import HELPERS, hm, is_helper, session_starts


def a2_choice(value, a2_count, helpers=False):
    """The A2 asked for (``?a2=N``), or 1 when it is missing or out of range;
    HELPERS for ``?a2=helpers`` when the plan has helpers. Never 0: that is
    the helpers' a2_index, not an A2."""
    if value == HELPERS and helpers:
        return HELPERS
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return n if 1 <= n <= a2_count else 1


def sessions(segments):
    """Session number of each segment row, 0 first: a new session starts at
    every break and at a part that starts after every earlier part has ended
    (solver.session_starts, the rule the plan was made with)."""
    day = SimpleNamespace(segments=[
        SimpleNamespace(key=s['row'], part=s['part'], t0=s['t0'], t1=s['t1'], is_break=s['is_break'], start=k)
        for k, s in enumerate(segments)])
    marks = [minute for minute, _ in session_starts(day)]
    first = min((s['t0'] for s in segments), default=0)
    # A start at the very top of the day opens session 0, not 1.
    offset = 1 if marks and marks[0] <= first else 0
    return {s['row']: bisect_right(marks, s['t0']) - offset for s in segments}


def segment_key(seg, numbers):
    """What the screen remembers the current segment by: part number and
    line, which survive a re-generate (row pks do not survive a re-read)."""
    return '{}:{}'.format(numbers.get(seg['part'], 0), seg.get('line') or seg['row'])


def _marks(act, reuse, conflicts):
    app = act.appearance
    out = []
    if app.is_host:
        out.append('host')
    if act.backup:
        out.append('backup')
    elif app.pinned_rf is not None or app.pinned_type:
        out.append('pinned')
    if act.kind == 'mic' and not act.backup:
        if (app.person_id, app.on_row_id) in reuse:
            out.append('mid_session')
        if (app.person_id, app.on_row_id) in conflicts:
            out.append('conflict')
    return out


def has_helpers(actions):
    return any(is_helper(a) for a in actions)


def build(plan, actions, a2, parts):
    """{'a2', 'a2_count', 'helpers', 'sessions': [{'n', 't0', 't1',
    'segments': [...]}]} for A2 ``a2`` (1..n), or the de-mic helpers'
    list (HELPERS). Each segment: name, times, busy minutes, break and its
    turnover, and its action rows."""
    helpers = a2 == HELPERS
    a2_count = max(1, plan.settings.get('a2_count', 1))
    numbers = {p.pk: k + 1 for k, p in enumerate(parts)}
    session_of = sessions(plan.segments)
    reuse = {(f.get('person'), f.get('row')) for f in plan.flags if f['kind'] in ('reuse', 'pin_reuse')}
    conflicts = {(f.get('person'), f.get('row')) for f in plan.flags if f['kind'] == 'conflict'}
    turnover_flags = {}
    for f in plan.flags:
        if f['kind'] == 'break':
            turnover_flags.setdefault(f.get('row'), []).append(f['text'])

    segs = []
    by_row = {}
    for s in plan.segments:
        span = max(1, s['t1'] - s['t0'])
        busy = (s.get('busy') or [])
        seg = {'row': s['row'], 'key': segment_key(s, numbers), 'name': s['name'] or 'Segment',
               'line': s.get('line') or '', 'part_no': numbers.get(s['part']), 't0': s['t0'], 't1': s['t1'],
               'time': '{}–{}'.format(hm(s['t0']), hm(s['t1'])), 'is_break': s['is_break'],
               'busy': round(s.get('helper_busy') or 0) if helpers else round(busy[a2 - 1]) if len(busy) >= a2 else 0,
               'span': round(span),
               'session': session_of[s['row']], 'notes': list(turnover_flags.get(s['row'], ())), 'actions': []}
        segs.append(seg)
        by_row[s['row']] = seg

    def home(act):
        if act.segment_id in by_row:
            return by_row[act.segment_id]
        inside = [s for s in segs if s['t0'] <= act.start_min < s['t1']]
        if inside:
            return inside[0]
        before = [s for s in segs if s['t0'] <= act.start_min]
        return max(before, key=lambda s: s['t0']) if before else (segs[0] if segs else None)

    # A transmitter swap is a line of its own just before the mic that needs
    # it, at the break it is done in (or the mic's time, mid-session).
    swaps = {(w['appearance'], p['rf']): w for p in plan.packs for w in p.get('swaps') or ()}

    for act in sorted(actions, key=lambda a: (a.start_min, a.seq)):
        if helpers != is_helper(act) or (not helpers and act.a2_index != a2):
            continue
        seg = home(act)
        if seg is None:
            continue
        swap = swaps.get((act.appearance.key, act.rf_number)) if act.kind == 'mic' and not act.backup else None
        if swap is not None:
            seg['actions'].append({'time': hm(swap['brk'] if swap['brk'] is not None else swap['at']),
                                   'verb': 'SWAP', 'name': swap_line(act.rf_number, swap['to']),
                                   'rf': 'RF {}'.format(act.rf_number), 'reason': swap_words(swap), 'a2': '',
                                   'kind': 'swap', 'rf_number': act.rf_number, 'line': act.line,
                                   'late': False, 'tight': False, 'marks': [],
                                   'mid': swap['brk'] is None})
        f = format_action(act, a2_count)
        # A mark the row already says ("host" reason, "RF 21 (backup)") is not repeated.
        said = (f['reason'] + ' ' + f['rf']).lower()
        marks = [m for m in _marks(act, reuse, conflicts) if MARKS[m].lower() not in said]
        seg['actions'].append(dict(f, kind=act.kind, rf_number=act.rf_number, line=act.line, late=act.late,
                                   tight=act.tight, marks=[MARKS[m] for m in marks]))

    for seg in segs:
        if seg['is_break']:
            text = turnover_text(sum(1 for a in seg['actions'] if a['kind'] == 'mic'),
                                 sum(1 for a in seg['actions'] if a['kind'] == 'demic'))
            if text:
                seg['notes'].insert(0, text)

    # Parts that overlap in time come one after the other in showflow order,
    # so group by session number, keeping that order inside each session.
    grouped = {}
    for seg in segs:
        grouped.setdefault(seg['session'], []).append(seg)
    out = [{'n': n, 'segments': grouped[n]} for n in sorted(grouped)]
    shown = [seg for sess in out for seg in sess['segments']]
    for k, seg in enumerate(shown):
        seg['i'] = k                  # display order: what "past" and "next" go by
    for k, sess in enumerate(out):
        sess['number'] = k + 1
        sess['t0'] = min(s['t0'] for s in sess['segments'])
        sess['t1'] = max(s['t1'] for s in sess['segments'])
        sess['time'] = '{}–{}'.format(hm(sess['t0']), hm(sess['t1']))
    return {'a2': a2, 'a2_count': a2_count, 'helpers': helpers, 'sessions': out,
            'count': sum(len(s['actions']) for s in segs)}
