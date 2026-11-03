"""How an A2 action reads, wherever it is shown: the Showflow + plan page,
plan.json and (PR 4) the A2 schedule and its PDF. Keep every wording of an
action here so they never drift apart.
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
