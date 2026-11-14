"""One show day's Mic Planner status, for the dashboard card: imported?,
the plan's version, channels used of the rig, review items not checked off, and
whether the plan has been sent to Mic Tracker since it last changed.
Read-only; the counts are the Mic Planner page's own (``page``)."""

from planner.models import MicPlan, MicPlanAppearance, MicPlanPush

from . import checks, importer
from .page import review_cards
from .planning import plan_rig
from .push import last_push


def channel_count(plan):
    """Regular packs (spares aside) against the rig's usable channels:
    {'used', 'of', 'spare', 'over', 'text'}. ``of`` is None with no rig.
    "9 of 13 ch · 1 spare", "13 of 13 ch", "15 of 13 ch — over the rig",
    "9 ch" with no rig."""
    used = sum(1 for p in plan.packs if not p.get('spare'))
    R = plan_rig(plan)
    if not R.set:
        return {'used': used, 'of': None, 'spare': 0, 'over': False, 'text': '{} ch'.format(used)}
    of, spare = R.limit, R.channels - R.limit
    over = used > of or any(p.get('over') for p in plan.packs)
    text = '{} of {} ch'.format(used, of)
    if over:
        text += ' — over the rig'
    elif spare:
        text += ' · {} spare'.format(spare)
    return {'used': used, 'of': of, 'spare': spare, 'over': over, 'text': text}


def day_status(day):
    """The card's row for ``day``; ``state`` is 'none' (no showflow), 'imported'
    (no plan yet) or 'plan'."""
    parts = importer.active_parts(day)
    out = {'day': day.pk, 'state': 'none' if not parts else 'imported'}
    plan = MicPlan.objects.filter(day=day).first() if parts else None
    if plan is None:
        return out
    apps = list(MicPlanAppearance.objects.filter(plan=plan))
    people = list(day.showflow_people.all())
    sent = last_push(day)
    out.update({
        'state': 'plan',
        'version': plan.version,
        'stale': plan.stale,
        'channels': channel_count(plan),
        # The page's "To review" tile counts the same cards: those not checked off.
        'review': len(checks.unchecked(checks.annotate(day, review_cards(parts, plan, apps, people, {}),
                                                       people, plan))),
        'sent': None if sent is None else {'version': sent.plan_version, 'at': sent.pushed_at.isoformat()},
        'changed_since_sent': bool(sent and sent.plan_version != plan.version),
    })
    return out


def pushed_days(project):
    """Pks of the project's days with a push that has not been reverted:
    the Mic Tracker card's "Planned in Mic Planner"."""
    return set(MicPlanPush.objects.filter(day__project=project).exclude(summary__has_key='reverted')
               .values_list('day_id', flat=True))
