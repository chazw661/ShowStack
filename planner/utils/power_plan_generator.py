"""Power plans generated from the amp module (Phase C).

A project has at most one generated plan. Its rows are the project's rack
amps, one row per amp, each worked out from the cabinets on its outputs
(power_estimate.amp_channel_loads) at the plan's programme level:

* An amp with no cabinets at all is charged the worst case -- the lowest
  load its table publishes on every channel -- and the row says so.
* Outputs with no cabinet on an amp that has some are counted at idle, and
  the row says how many.
* An amp whose model has no power profile has no figures; it is left out
  and listed (amp_models.amps_without_power_profile), as on any plan.

Legs. The leg lives on the amp (Amp.leg; blank = auto). balance() keeps
every leg set on an amp and puts each auto amp, largest first, on the leg
with the least load so far. Legs follow the plan's service: L1-L3 on 3-phase,
L1-L2 on split-phase, L1 on single-phase. A leg the service does not have
(L3 on split-phase) is balanced like an auto amp, and the row says so.

Regenerate rebuilds the generated rows from the racks as they are now and
keeps the plan's settings and any rows added by hand. fingerprint() is what
the plan was built from; the page compares it with the racks to say they
have changed since.

Nothing here assumes a brand: an "Add LA-RAK II" that creates three LA12X
set to L1/L2/L3 is three amps with legs set, which this already handles.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import List

from django.db import transaction
from django.utils import timezone

from planner.utils.cabinet_load import format_ohms
from planner.utils.power_estimate import (
    amp_channel_loads, assumed_load, is_three_phase, leg_current, uniform_channel_loads,
)

ALLOWANCE_LABEL = 'Other audio electronics (consoles, processors, playback)'
STALE_MESSAGE = 'Amps or cabinets changed since generated'

AUTO, SET, NOT_ON_SERVICE = 'auto', 'set', 'not_on_service'


def project_amps(project):
    """The project's amps in rack order, with what a row reads prefetched."""
    from planner.models import Amp
    return (Amp.objects.filter(project=project)
            .select_related('location', 'amp_model__power_profile')
            .prefetch_related('channels__cabinet_section',
                              'amp_model__power_profile__load_ratings',
                              'amp_model__power_profile__voltage_factors')
            .order_by('location__sort_order', 'location__name', 'sort_order', 'id'))


def fingerprint(project, amps=None):
    """A hash of everything the generated rows are built from: which amps,
    their names, locations, order, power profile, leg, and the cabinets on
    each output."""
    amps = project_amps(project) if amps is None else amps
    data = []
    for amp in amps:
        model = amp.amp_model
        data.append([
            amp.pk, amp.name, amp.location_id, amp.location.name, amp.location.sort_order,
            amp.sort_order, model.power_profile_id if model else None, amp.leg,
            [[ch.channel_number, ch.cabinet_section_id, ch.cabinet_quantity]
             for ch in sorted(amp.channels.all(), key=lambda c: c.channel_number)],
        ])
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def is_stale(plan):
    return plan.is_generated and plan.source_fingerprint != fingerprint(plan.project)


def row_loads(row):
    """(channel loads, notes) for a generated row: its amp's cabinets, or the
    worst case when the amp has none (or is gone)."""
    profile, amp = row.amplifier, row.source_amp
    if amp is not None:
        loads = amp_channel_loads(amp)
        empty = sum(1 for load in loads if load is None)
        if loads and empty < len(loads):
            notes = []
            if empty:
                notes.append(f'{empty} of {len(loads)} outputs have no cabinet (counted at idle)')
            return loads, notes
    load = assumed_load(profile, None)
    worst = f'worst case: {format_ohms(load)} Ω on every channel' if load is not None \
        else 'worst case'
    reason = ('amp deleted from the amp module, regenerate' if amp is None
              else 'no cabinets assigned')
    return uniform_channel_loads(profile, None), [f'{reason}, {worst}']


def leg_status(row, legs):
    """AUTO, SET (on the amp, kept) or NOT_ON_SERVICE (set on the amp to a
    leg this service does not have, so balanced)."""
    if not row.amp_leg:
        return AUTO
    return SET if row.amp_leg in legs else NOT_ON_SERVICE


@dataclass
class Item:
    key: object
    watts: Decimal
    leg: str = ''       # set by hand; '' = auto
    order: int = 0


def balance(items: List[Item], legs, preloaded=None):
    """{key: leg}. Items with a leg in ``legs`` keep it. The rest, largest
    first (ties in ``order``), each go on the leg with the least load so far
    (ties to the lower leg). ``preloaded`` is {leg: watts} already there."""
    totals = {leg: Decimal((preloaded or {}).get(leg, 0)) for leg in legs}
    result, auto = {}, []
    for item in items:
        if item.leg in legs:
            result[item.key] = item.leg
            totals[item.leg] += item.watts
        else:
            auto.append(item)
    for item in sorted(auto, key=lambda i: (-i.watts, i.order)):
        leg = min(legs, key=lambda name: (totals[name], legs.index(name)))
        result[item.key] = leg
        totals[leg] += item.watts
    return result


def rebalance(plan):
    """Put the generated rows on legs: hand-set legs (as generated) kept,
    the rest balanced around them and around rows added by hand on a leg."""
    legs = plan.legs
    rows = list(plan.amplifier_assignments.all())
    preloaded = {}
    for row in rows:
        if not row.generated and row.phase_assignment in legs:
            preloaded[row.phase_assignment] = (preloaded.get(row.phase_assignment, 0)
                                               + (row.calculated_watts_per_unit or 0) * row.quantity)
    generated = [r for r in rows if r.generated]
    placed = balance([Item(r.pk, Decimal((r.calculated_watts_per_unit or 0) * r.quantity),
                           r.amp_leg, r.pk) for r in generated], legs, preloaded)
    for row in generated:
        if row.phase_assignment != placed[row.pk]:
            row.phase_assignment = placed[row.pk]
            type(row).objects.filter(pk=row.pk).update(phase_assignment=row.phase_assignment)


def build_rows(plan):
    """Replace the plan's generated rows with one per rack amp, then
    balance. Rows added by hand and the plan's settings are kept."""
    from planner.models import AmplifierAssignment
    amps = list(project_amps(plan.project))
    plan.amplifier_assignments.filter(generated=True).delete()
    for amp in amps:
        profile = amp.amp_model.power_profile if amp.amp_model_id else None
        if profile is None:
            continue
        row = AmplifierAssignment(
            distribution_plan=plan, amplifier=profile, quantity=1, generated=True,
            source_amp=amp, amp_leg=amp.leg, zone=amp.location.name, position=amp.name,
            programme=plan.programme, phase_assignment='AUTO')
        row.save()
    rebalance(plan)
    plan.source_fingerprint = fingerprint(plan.project, amps)
    plan.generated_at = timezone.now()
    plan.save(update_fields=['source_fingerprint', 'generated_at', 'updated_at'])


def generated_plan(project):
    from planner.models import PowerDistributionPlan
    return PowerDistributionPlan.objects.filter(
        project=project, generated_at__isnull=False).first()


@transaction.atomic
def generate(project, user=None):
    """(plan, created): the project's generated plan, built now if there is
    none. Service defaults to 3-phase (the model default)."""
    from planner.models import PowerDistributionPlan
    existing = generated_plan(project)
    if existing is not None:
        return existing, False
    plan = PowerDistributionPlan.objects.create(
        project=project, venue_name=project.venue or project.name,
        generated_at=timezone.now(), created_by=user)
    build_rows(plan)
    return plan, True


@transaction.atomic
def regenerate(plan):
    build_rows(plan)


def recompute(plan):
    """Re-save every row (cached figures at the plan's settings), then
    rebalance a generated plan: the programme or the service may have
    changed the loads or the legs."""
    for row in plan.amplifier_assignments.select_related('amplifier', 'source_amp'):
        row.distribution_plan = plan
        row.save()
    if plan.is_generated:
        rebalance(plan)


def allowance(plan):
    """The other-electronics allowance on each leg: (watts, current) with
    current = watts / (phase-to-neutral volts x PF). No transient headroom."""
    legs = plan.legs
    watts = Decimal(plan.other_electronics_watts or 0) / len(legs)
    return watts, leg_current(watts, plan.get_phase_to_neutral_voltage(), plan.power_factor)


def three_phase_warning(plan, assignments):
    """'LA12X, LA8 require 3-phase distro' when the plan is not on 3-phase
    and any of its amps needs it; '' otherwise. Any plan, generated or not."""
    if is_three_phase(plan.service_type):
        return ''
    models = sorted({a.amplifier.model for a in assignments if a.amplifier.needs_three_phase})
    if not models:
        return ''
    return f"{', '.join(models)} require{'s' if len(models) == 1 else ''} 3-phase distro"
