"""The load on an amp output, from the cabinets the amp module says are on it.

Load = the section's nominal impedance / the number in parallel (Preset Guide
v25.0 p.118: 3 x 8 ohm = 2.7 ohm). It is then matched to the nearest load the
amp's draw table publishes, on a log scale -- 2.67 ohm is nearest 2.7, 5.33 is
nearest 4 rather than 8 -- with a tie going to the lower impedance, which
draws more. The power plan will use the draw at that published load.

An output is flagged when nothing is assigned, or against the amp's drive
capacity (Preset Guide v25.0 pp.119-120, CabinetDriveCapacity): a cabinet the
amp does not drive, or more in parallel than one output takes. Where the
drive table has no cell for the amp and cabinet (the LA8, a cabinet the table
does not list), the load is checked against the amp's minimum instead. Loads
are compared at the 0.1 ohm the manuals print, so 8/3 (2.67) counts as the
2.7 ohm minimum and is not below it. The table takes precedence because it
allows 4 ohm Syva Low and SB6i in parallel (p.118), below the minimum.

``amp_drive_warnings`` checks the table's per-amp total across the outputs.
"""

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

UNASSIGNED = 'unassigned'
BELOW_MINIMUM = 'below_minimum'
NOT_DRIVEN = 'not_driven'
OVER_PER_OUTPUT = 'over_per_output'
# Shown in red: the amp can't drive what is assigned. UNASSIGNED is amber.
ERRORS = {BELOW_MINIMUM, NOT_DRIVEN, OVER_PER_OUTPUT}


def format_ohms(value):
    """2.6667 -> '2.67', 4.00 -> '4', 2.70 -> '2.7'."""
    text = f"{Decimal(value).quantize(Decimal('0.01'), ROUND_HALF_UP):f}"
    return text.rstrip('0').rstrip('.') if '.' in text else text


def nearest_published_load(ohms, published):
    """The published load nearest ``ohms`` on a log scale; ties go to the
    lower impedance. None if nothing is published."""
    best = None
    for candidate in sorted(published):
        distance = abs(math.log(float(ohms)) - math.log(float(candidate)))
        if best is None or distance < best[0] - 1e-9:
            best = (distance, candidate)
    return None if best is None else best[1]


@dataclass
class OutputLoad:
    section: Optional[object]       # CabinetSection
    quantity: int
    ohms: Optional[Decimal] = None
    published_ohms: Optional[Decimal] = None
    min_ohms: Optional[Decimal] = None
    amp_name: str = ''
    max_per_output: Optional[int] = None
    warning: str = ''

    @property
    def label(self):
        """'Kara II · LF ×3 → 2.67 Ω (2.7 Ω)'; the bracket is left out when
        it would repeat the load, or the amp's table does not depend on load."""
        if self.section is None:
            return ''
        text = f"{self.section} ×{self.quantity} → {format_ohms(self.ohms)} Ω"
        if (self.published_ohms is not None
                and format_ohms(self.published_ohms) != format_ohms(self.ohms)):
            text += f" ({format_ohms(self.published_ohms)} Ω)"
        return text

    @property
    def warning_text(self):
        if self.warning == UNASSIGNED:
            return 'No cabinet'
        if self.warning == BELOW_MINIMUM:
            return f'Below {format_ohms(self.min_ohms)} Ω minimum'
        if self.warning == NOT_DRIVEN:
            return f'{self.amp_name} does not drive this'
        if self.warning == OVER_PER_OUTPUT:
            return f'Over {self.max_per_output} per output'
        return ''


def output_load(channel):
    """OutputLoad for an AmpChannel. Reads channel.amp.amp_model.power_profile;
    prefetch ``amp__amp_model__power_profile__load_ratings``,
    ``amp__amp_model__power_profile__drive_capacities`` and
    ``cabinet_section__cabinet`` when doing this for many channels."""
    section = channel.cabinet_section
    if section is None:
        return OutputLoad(section=None, quantity=channel.cabinet_quantity,
                          warning=UNASSIGNED)
    quantity = max(int(channel.cabinet_quantity or 1), 1)
    ohms = Decimal(section.nominal_impedance_ohms) / quantity
    model = channel.amp.amp_model if channel.amp_id else None
    profile = getattr(model, 'power_profile', None) if model else None
    load = OutputLoad(section=section, quantity=quantity, ohms=ohms)
    if profile is not None:
        load.published_ohms = nearest_published_load(ohms, profile.published_loads())
        load.min_ohms = profile.min_load_ohms
        load.amp_name = profile.model
        capacity = profile.drive_capacity(section.cabinet_id)
        if capacity is not None:
            load.max_per_output = capacity.per_output
            if not capacity.is_supported:
                load.warning = NOT_DRIVEN
            elif quantity > capacity.per_output:
                load.warning = OVER_PER_OUTPUT
        elif (load.min_ohms is not None
                and ohms.quantize(Decimal('0.1'), ROUND_HALF_UP) < load.min_ohms):
            load.warning = BELOW_MINIMUM
    return load


def enclosures_per_cabinet(channels):
    """{cabinet: enclosures} on one amp. A passive cabinet counts its
    quantities across outputs. An active one counts the most of any one
    section: K2 LF x3, MF x3, HF x3 is three K2."""
    by_section = {}
    for ch in channels:
        if ch.cabinet_section_id is None:
            continue
        key = ch.cabinet_section
        by_section[key] = by_section.get(key, 0) + max(int(ch.cabinet_quantity or 1), 1)
    totals = {}
    for section, count in by_section.items():
        cabinet = section.cabinet
        totals[cabinet] = max(totals.get(cabinet, 0), count)
    return totals


def amp_drive_warnings(profile, channels):
    """['Kara II: 8 on this amp, max 6'] for each cabinet over the drive
    table's per-amp total. Empty when the amp has no profile or the table
    gives no total."""
    if profile is None:
        return []
    warnings = []
    for cabinet, count in enclosures_per_cabinet(channels).items():
        capacity = profile.drive_capacity(cabinet.pk)
        if capacity is None or capacity.per_amp is None:
            continue
        if count > capacity.per_amp:
            warnings.append(f'{cabinet.model}: {count} on this amp, max {capacity.per_amp}')
    return warnings
