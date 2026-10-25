"""Mains draw of one amplifier, estimated from the manufacturer's tables.

Every figure here is an estimate from manufacturer data, and the page says so
(ESTIMATE_LABEL).

Published path (AmplifierLoadRating rows at 230 V, all channels driven):

* Programme level: idle, normal = the 1/8-power (pink noise) row, heavy =
  the 1/3-power row. No further duty factor: 1/8 and 1/3 power already are
  programme levels, and multiplying them by a duty cycle counted it twice.
* Each channel's load is snapped to the nearest load the table publishes
  (planner.utils.cabinet_load.nearest_published_load).
* Mixed loads: the tables assume every channel carries the same load, so an
  amp is charged  idle + sum over channels of (draw at that channel's load
  - idle) / channels.  An empty channel adds idle only; equal loads give the
  published figure exactly. Applied to the published current and the
  published power separately -- neither is derived from the other.
* Current at the plan's voltage = current at 230 V x the multiplier: the one
  the manual prints for that voltage, else 230 / V. Power is unchanged.

Fallback for a profile with no draw table: its legacy watts (idle, rated =
1/8, peak = 1/3) at the plan's power factor, current = W / (V x PF). That is
the only place the power factor is used; the page lists it as an assumption.

No model methods are called, so data migrations can pass historical models.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from planner.utils.cabinet_load import format_ohms, nearest_published_load

ESTIMATE_LABEL = 'Estimate from manufacturer data'
REFERENCE_VOLTAGE = 230
DERIVED_VOLTAGE_SOURCE = "derived: L-Acoustics multipliers are the 230 V ratio"

IDLE, NORMAL, HEAVY = 'idle', 'normal', 'heavy'
PROGRAMME_CHOICES = [
    (IDLE, 'Idle (no signal)'),
    (NORMAL, 'Normal programme (1/8 power)'),
    (HEAVY, 'Heavy programme (1/3 power)'),
]
CONDITION = {IDLE: 'idle', NORMAL: 'eighth', HEAVY: 'third'}
LEVEL_NAME = {IDLE: 'idle', NORMAL: '1/8 power', HEAVY: '1/3 power'}
LEGACY_WATTS = {IDLE: 'idle_power_watts', NORMAL: 'rated_power_watts', HEAVY: 'peak_power_watts'}

PUBLISHED, FROM_WATTS = 'published', 'watts'


def plan_voltage(service_type):
    """208 / 240 / 120 from a PowerDistributionPlan service type."""
    for volts in ('208', '240', '120'):
        if volts in (service_type or ''):
            return int(volts)
    return 208


def voltage_multiplier(profile, voltage):
    """(multiplier, source): current at V = current at 230 V x multiplier.
    A multiplier published for this model and voltage wins; else 230 / V."""
    voltage = int(voltage)
    if voltage <= 0:
        raise ValueError(f"mains voltage must be positive, not {voltage}")
    if voltage == REFERENCE_VOLTAGE:
        return Decimal(1), f"published at {REFERENCE_VOLTAGE} V"
    for factor in profile.voltage_factors.all():
        if factor.mains_voltage == voltage:
            return factor.current_multiplier, factor.source
    ratio = (Decimal(REFERENCE_VOLTAGE) / Decimal(voltage)).quantize(Decimal('0.0001'))
    return ratio, DERIVED_VOLTAGE_SOURCE


def _ratings(profile):
    return [r for r in profile.load_ratings.all() if r.mains_voltage == REFERENCE_VOLTAGE]


def published_loads(profile):
    """Loads the draw table has a column for, lowest first."""
    return sorted({r.load_ohms for r in _ratings(profile) if r.load_ohms is not None})


@dataclass
class Draw:
    """One amp's draw at one programme level."""
    current: Decimal            # A at the plan's voltage, before headroom
    watts: int
    basis: str                  # PUBLISHED or FROM_WATTS
    notes: List[str] = field(default_factory=list)


def _q(value):
    return Decimal(value).quantize(Decimal('0.01'), ROUND_HALF_UP)


def estimate(profile, programme, channel_loads, voltage, power_factor):
    """Draw for ``profile`` at ``programme`` with ``channel_loads`` -- one
    entry per channel, the load in ohms or None for an empty channel. None
    when there is no profile."""
    if profile is None:
        return None
    ratings = _ratings(profile)
    idle = next((r for r in ratings if r.condition == 'idle' and r.load_ohms is None), None)
    if idle is None:
        return _from_watts(profile, programme, voltage, power_factor)

    notes = []
    if programme == IDLE:
        current, watts = Decimal(idle.current_amps), Decimal(idle.power_watts)
    else:
        condition = CONDITION[programme]
        rows = [r for r in ratings if r.condition == condition]
        if not rows:
            return _from_watts(profile, programme, voltage, power_factor)
        by_load = {r.load_ohms: r for r in rows}
        loads = sorted(k for k in by_load if k is not None)
        n = max(len(channel_loads), 1)
        current, watts = Decimal(idle.current_amps), Decimal(idle.power_watts)
        footnoted = set()
        for load in channel_loads:
            if load is None:
                continue  # an empty channel adds idle only
            row = by_load[nearest_published_load(load, loads)] if loads else by_load.get(None)
            if row is None:
                continue
            current += (Decimal(row.current_amps) - Decimal(idle.current_amps)) / n
            watts += (Decimal(row.power_watts) - Decimal(idle.power_watts)) / n
            if row.channels_driven:
                footnoted.add((row.load_ohms, row.channels_driven))
        for load_ohms, driven in sorted(footnoted, key=lambda x: (x[0] or 0)):
            at = f' at {format_ohms(load_ohms)} Ω' if load_ohms is not None else ''
            notes.append(f'{profile.model} {LEVEL_NAME[programme]}{at} is published '
                         f'with {driven} channels driven')
    multiplier, source = voltage_multiplier(profile, voltage)
    if multiplier != 1:
        notes.append(f'current ×{multiplier.normalize():f} for {voltage} V ({source})')
    return Draw(current=_q(current * multiplier), watts=int(watts.quantize(Decimal(1), ROUND_HALF_UP)),
                basis=PUBLISHED, notes=notes)


def _from_watts(profile, programme, voltage, power_factor):
    watts = int(getattr(profile, LEGACY_WATTS[programme]) or 0)
    pf = Decimal(power_factor)
    current = _q(Decimal(watts) / (Decimal(voltage) * pf)) if watts else Decimal('0.00')
    return Draw(current=current, watts=watts, basis=FROM_WATTS, notes=[
        f'no published current: {watts} W at {voltage} V, power factor {pf.normalize():f} (assumed)'])


def assumed_load(profile, load_ohms):
    """The per-channel load a hand-added plan row is worked out at: the one
    set on the row, else the lowest load the table publishes (the highest
    draw). None when the table does not depend on load."""
    if load_ohms is not None:
        return Decimal(load_ohms)
    loads = published_loads(profile) if profile is not None else []
    return loads[0] if loads else None


def uniform_channel_loads(profile, load_ohms):
    """Every channel of the profile at one load: a hand-added plan row."""
    channels = max(int(getattr(profile, 'channels', 0) or 0), 1)
    load = assumed_load(profile, load_ohms)
    if load is None:
        # A table that does not depend on load (LA4X): any load reads its
        # single column, and None would mean an empty channel.
        load = Decimal(8)
    return [load] * channels


def amp_channel_loads(amp):
    """One entry per channel of a rack Amp: the load of its cabinets in ohms
    (section impedance / quantity), or None where nothing is assigned. Reads
    channels and their cabinet sections; prefetch for many amps."""
    loads = []
    for ch in sorted(amp.channels.all(), key=lambda c: c.channel_number):
        section = ch.cabinet_section
        if section is None:
            loads.append(None)
        else:
            loads.append(Decimal(section.nominal_impedance_ohms)
                         / max(int(ch.cabinet_quantity or 1), 1))
    return loads
