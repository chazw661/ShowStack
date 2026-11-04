"""How an A2 action reads, wherever it is shown: the Showflow + plan page,
plan.json and (PR 4) the A2 schedule and its PDF. Keep every wording of an
action here so they never drift apart. Likewise the wording of an edit
(Undo button, message after a move) and of what a re-solve changed.
"""

from .solver import hm

VERBS = {'mic': 'MIC', 'demic': 'DE-MIC'}


def format_action(action, a2_count=1):
    """``action``: a MicPlanA2Action or a solver.Action (same field names).

    {'time', 'verb', 'name', 'rf', 'reason', 'a2', 'text'}; ``a2`` is '' with
    one A2.
    """
    rf = 'RF {}'.format(action.rf_number) + (' (backup)' if action.backup else '')
    out = {
        'time': hm(action.start_min),
        'verb': VERBS[action.kind],
        'name': action.person_name,
        'rf': rf,
        'reason': action.reason,
        'a2': 'A2 {}'.format(action.a2_index) if a2_count > 1 else '',
    }
    if action.late:
        out['reason'] += ', late'
    elif action.tight:
        out['reason'] += ', tight'
    out['text'] = '{}{} {} {} {} ({})'.format(
        out['a2'] + ' ' if out['a2'] else '', out['time'], out['verb'], out['name'], out['rf'],
        out['reason'])
    return out


POOL_WORDS = {'body': 'body pack', 'HH': 'handheld'}


def first_name(name):
    words = (name or '').replace('Dr. ', '').split()
    return words[0] if words else name


def describe_edit(edit):
    """"Alex → RF 13, now handheld", for a MicPlanEdit (or anything with
    ``kind`` and ``value``)."""
    v = edit.value
    who = first_name(v.get('name', ''))
    if edit.kind == 'move_rf':
        now = ', now {}'.format(POOL_WORDS[v['pool']]) if v.get('from_pool') and v['pool'] != v['from_pool'] else ''
        return '{} \u2192 RF {}{}'.format(who, v['rf'], now)
    if edit.kind == 'set_mic_type':
        return '{} \u2192 {}'.format(who, POOL_WORDS[v['mic_type']])
    return '{} unpinned'.format(who)


def describe_change(c):
    """"Alex (line 171) RF 3 → RF 13, now handheld", for one entry of
    MicPlan.changes."""
    now = ', now {}'.format(POOL_WORDS[c['to_pool']]) if c['to_pool'] != c['from_pool'] else ''
    return '{} (line {}) RF {} \u2192 RF {}{}'.format(first_name(c['name']), c['line'] or '?', c['from'], c['to'], now)


# Marks on an A2 action, in words (the schedule and its PDF must read in
# black and white). Late and tight are already in the reason.
MARKS = {'host': 'HOST', 'backup': 'BACKUP', 'pinned': 'PINNED', 'mid_session': 'MID-SESSION',
         'conflict': 'CONFLICT'}


def overlap_warning(n, m):
    """Parts ``n`` and ``m`` (numbers) run at the same time."""
    return ('Parts {} and {} overlap in time — this plan treats them as one stage with shared A2s and packs. '
            "If they're separate rooms, plan each room on its own day for now.").format(n, m)


def turnover_text(mics, demics):
    """"Turn over: 3 de-mics, 2 mics" for a break, or ''."""
    out = []
    if demics:
        out.append('{} de-mic{}'.format(demics, '' if demics == 1 else 's'))
    if mics:
        out.append('{} mic{}'.format(mics, '' if mics == 1 else 's'))
    return 'Turn over: ' + ', '.join(out) if out else ''
