"""Review cards checked off by an editor (MicPlanReviewCheck), per show day.

A check belongs to a card's fingerprint: its kind, the part's place in the
day (not its pk: Replace makes a new part), the line, the person (by name
key) and the numbers on the card ("material values": minutes late, RFs,
channels, packs in use). Plan versions, stamps and the solver's suggested fix
are not material: a Re-generate with no data change keeps every card's
fingerprint (test_mic_plan_review_checks.RegenerateKeepsChecksTests). A card
whose numbers change, or a new card, shows unchecked.

Stale checks are deleted when the plan is saved, or on a rebuild of a day
with no plan; never while the plan is stale, when its flags may point at
rows a Replace removed and come back on Re-generate.

Checking changes nothing else: a blocker (RF conflict, a shortage while
over the rig) still blocks Send to Mic Tracker."""

import hashlib
import re

from django.utils import timezone

from planner.models import MicPlan, MicPlanReviewCheck

from .importer import active_parts
from .page import review_cards
from .push import short_of_rig

# Not material: "v8", "sent v12", and dates and clock times with seconds
# (a stamp) — a card's clock times ("ready at 10:42") stay material.
_NOT_MATERIAL = re.compile(r'(?i)\bv\d+\b|\b\d{4}-\d\d-\d\d(?:[T ][\d:.+\-Z]*)?|\b\d\d?:\d\d:\d\d\b')
# Not material either: the fix the solver suggests ("Fix: 1 de-mic helper at
# ...", "Fix: pre-mic lead 12 min", "No pre-mic lead up to ..."), always the end
# of a card's text, added on Generate and not on every re-solve.
_ADVICE = re.compile(r'\s(?:Fix\b|No pre-mic lead up to\b).*$', re.S)
_NUMBER = re.compile(r'\d+')
NOTE_MAX = 200


def material(text):
    """The numbers on a card, in order."""
    return _NUMBER.findall(_NOT_MATERIAL.sub(' ', _ADVICE.sub('', text or '')))


def fingerprint(card, name_keys):
    """``card``: page.review_cards; ``name_keys``: {person pk: name_key}."""
    person = card.get('person')
    parts = [card['kind'], str(card.get('part_no') or ''), str(card.get('line') or ''),
             name_keys.get(person, '' if person is None else str(person)), ','.join(material(card['text']))]
    return hashlib.sha1('\x1f'.join(parts).encode()).hexdigest()


def annotate(day, cards, people, plan=None):
    """Add 'fp', 'check' (MicPlanReviewCheck or None) and 'blocks' (still
    blocks Send to Mic Tracker) to each card; returns ``cards``."""
    keys = {p.pk: p.name_key for p in people}
    checks = {c.fingerprint: c for c in MicPlanReviewCheck.objects.filter(day=day)}
    over = bool(plan is not None and short_of_rig(plan))
    for c in cards:
        c['fp'] = fingerprint(c, keys)
        c['check'] = checks.get(c['fp'])
        c['blocks'] = c['kind'] == 'conflict' or (over and c['kind'] == 'shortage')
    return cards


def unchecked(cards):
    return [c for c in cards if c['check'] is None]


def checked(cards):
    return [c for c in cards if c['check'] is not None]


def blocking(cards):
    return [c for c in cards if c['blocks']]


def day_cards(day, plan=None, labels=None):
    """Every Review card of ``day``, annotated."""
    plan = plan if plan is not None else MicPlan.objects.filter(day=day).first()
    apps = list(plan.appearances.all()) if plan is not None else []
    people = list(day.showflow_people.all())
    cards = review_cards(active_parts(day), plan, apps, people, labels or {})
    return annotate(day, cards, people, plan)


def set_check(day, card, note, user):
    """Check ``card`` off with ``note`` (or change the note of a check)."""
    note = ' '.join((note or '').split())[:NOTE_MAX]
    check = MicPlanReviewCheck.objects.filter(day=day, fingerprint=card['fp']).first()
    if check is None:
        check = MicPlanReviewCheck(day=day, fingerprint=card['fp'], kind=card['kind'][:30],
                                   checked_by=user, checked_by_name=user.get_username() if user else '',
                                   checked_at=timezone.now())
    check.note = note
    check.save()
    return check


def uncheck(day, card):
    MicPlanReviewCheck.objects.filter(day=day, fingerprint=card['fp']).delete()


def prune(day):
    """Delete the checks no card has any more (see the module docstring)."""
    if not MicPlanReviewCheck.objects.filter(day=day).exists():
        return 0
    plan = MicPlan.objects.filter(day=day).first()
    if plan is not None and plan.stale:
        return 0
    live = {c['fp'] for c in day_cards(day, plan)}
    return MicPlanReviewCheck.objects.filter(day=day).exclude(fingerprint__in=live).delete()[0]
