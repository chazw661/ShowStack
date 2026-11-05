"""How an A2 action reads, wherever it is shown: the Showflow + plan page,
plan.json and (PR 4) the A2 schedule and its PDF. Keep every wording of an
action here so they never drift apart. Likewise the wording of an edit
(Undo button, message after a move) and of what a re-solve changed.
"""

from .solver import Rig, hm

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


def _span(r):
    return '' if not r else str(r[0]) if len(r) == 1 else '{}\u2013{}'.format(r[0], r[-1])


def rig_text(values):
    """"Body 1–20 · Handheld 21–23 · Spare 24" for settings values (mic_plan.js
    writes the same line live in the settings form)."""
    R = Rig(values.get('wireless_channels'), values.get('handheld_channels') or 0,
            values.get('spare_handhelds') or 0)
    if not R.set:
        spare = R.spares
        return 'No rig set: body from 1, handhelds after the last body pack{}'.format(
            ', {} spare{} after them'.format(spare, '' if spare == 1 else 's') if spare else '')
    out = [(word, _span(r)) for word, r in (('Body', R.channels_of('body')), ('Handheld', R.channels_of('HH')),
                                             ('Spare', R.spare_channels()))]
    return ' \u00b7 '.join('{} {}'.format(word, span) for word, span in out if span)


TX_WORDS = {'body': 'beltpack', 'HH': 'handheld'}
ZONE_WORDS = {'body': 'body', 'HH': 'HH'}


def swap_line(rf, to):
    """The A2's line for a transmitter swap: 'Swap RF 9 to handheld transmitter'."""
    return 'Swap RF {} to {} transmitter'.format(rf, TX_WORDS[to])


def swap_words(swap):
    """When a swap (an entry of a plan pack's 'swaps') is done: 'at the 1:45p
    break', 'mid-session'."""
    return swap.get('when') or 'mid-session'


def tx_note(pool, zone):
    """'beltpack on HH channel' for a ``pool`` wearing on a channel of
    ``zone`` (Rig.pool_at), or '' when it is that zone's type (or no rig)."""
    if zone not in TX_WORDS or zone == pool:
        return ''
    return '{} on {} channel'.format(TX_WORDS[pool], ZONE_WORDS[zone])


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
