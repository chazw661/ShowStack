"""The load on an amp output, from the cabinets the amp module says are on it.

Load = the section's nominal impedance / the number in parallel (Preset Guide
v25.0 p.118: 3 x 8 ohm = 2.7 ohm). It is then matched to the nearest load the
amp's draw table publishes, on a log scale -- 2.67 ohm is nearest 2.7, 5.33 is
nearest 4 rather than 8 -- with a tie going to the lower impedance, which
draws more. The power plan will use the draw at that published load.

An output is flagged when nothing is assigned, or when its load is below the
amp's minimum. Loads are compared at the 0.1 ohm the manuals print, so 8/3
(2.67) counts as the 2.7 ohm minimum and is not below it.
"""

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

UNASSIGNED = 'unassigned'
BELOW_MINIMUM = 'below_minimum'


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
        return ''


def output_load(channel):
    """OutputLoad for an AmpChannel. Reads channel.amp.amp_model.power_profile;
    prefetch ``amp__amp_model__power_profile__load_ratings`` and
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
        if (load.min_ohms is not None
                and ohms.quantize(Decimal('0.1'), ROUND_HALF_UP) < load.min_ohms):
            load.warning = BELOW_MINIMUM
    return load
