"""Seed the cabinet catalogue (CabinetModel + CabinetSection).

Source for every row: L-Acoustics, *Preset Guide owner's manual (EN)*,
version 25.0, distributed October 29, 2024.

* Sections come from each enclosure's factory preset output table -- the
  "channels" column (LF / MF / HF / LC, or PA for a passive full-range
  enclosure, SB / SR for subwoofers). The page cited per cabinet is that
  table's page. A passive enclosure (PA on every output) is one 'Full range'
  section.
* Each cabinet's picker heading (line source, constant curvature, coaxial,
  colinear, subwoofer) follows the guide's chapter it sits in; the
  progressive line source L2 is listed as a line source.
* Nominal impedances come from "Impedance load", p.118: most enclosures are
  8 ohm; the 16 ohm exceptions are K2 (HF section), Kiva II, V-DOSC (HF
  section), 5XT and X4i; the 4 ohm exceptions are SB28, KS28, Syva Low, K1-SB
  and SB6i.

``verified=False`` marks an impedance the guide does not state for that
section: L2's sections fall back to the general 8 ohm rule for a multi-module
enclosure, and the original Kiva's 8 ohm is derived (DERIVED_NOTES).

Runs on every deploy (railway.json). Without --force it only creates rows
that are missing, so a superuser's edits in the admin survive a redeploy;
--force puts every seeded row back to the values below.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import CabinetModel, CabinetSection

GUIDE = "L-Acoustics Preset Guide owner's manual (EN) v25.0 (Oct 2024)"
IMPEDANCE_PAGE = 118

LINE = CabinetModel.LINE_SOURCE
CONSTANT = CabinetModel.CONSTANT_CURVATURE
COAX = CabinetModel.COAXIAL
COLINEAR = CabinetModel.COLINEAR
SUB = CabinetModel.SUBWOOFER

# (model, soundvision names, preset-table page, [(section, ohms, verified)],
#  picker heading)
CABINETS = [
    # Variable curvature WST
    ('K1', 'K1', 48, [('LF', 8, True), ('MF', 8, True), ('HF', 8, True)], LINE),
    ('K1-SB', '', 50, [('SB', 4, True)], SUB),
    ('K2', 'K2', 50, [('LF', 8, True), ('MF', 8, True), ('HF', 16, True)], LINE),
    ('K3', 'K3', 53, [('LF', 8, True), ('HF', 8, True)], LINE),
    ('Kara II', 'KARA II', 56, [('LF', 8, True), ('HF', 8, True)], LINE),
    # The original Kara and Kiva: legacy, still widely rented. Kiva's 8 ohm
    # is derived, not stated: see DERIVED_NOTES.
    ('Kara', 'KARA', 57, [('LF', 8, True), ('HF', 8, True)], LINE),
    ('Kiva II', 'KIVA II', 58, [('Full range', 16, True)], LINE),
    ('Kiva', 'KIVA', 59, [('Full range', 8, False)], LINE),
    # Constant curvature WST
    ('ARCS Wide/Focus', 'ARCS', 67, [('Full range', 8, True)], CONSTANT),
    ('A10 Wide/Focus', 'A10', 68, [('Full range', 8, True)], CONSTANT),
    ('A15 Wide/Focus', 'A15', 70, [('Full range', 8, True)], CONSTANT),
    ('ARCS II', '', 72, [('LF', 8, True), ('HF', 8, True)], CONSTANT),
    # Progressive ultra-dense line source
    ('L2 / L2D', '', 47, [('LC', 8, False), ('LF', 8, False), ('HF', 8, False)], LINE),
    # Colinear sources
    ('Syva', '', 74, [('Full range', 8, True)], COLINEAR),
    ('Syva Low', '', 75, [('LF', 4, True)], COLINEAR),
    ('Syva Sub', '', 75, [('LF', 8, True)], SUB),
    ('Soka', '', 76, [('Full range', 8, True)], COLINEAR),
    # Coaxial
    ('X4i', '', 78, [('Full range', 16, True)], COAX),
    ('5XT', '', 79, [('Full range', 16, True)], COAX),
    ('X6i', '', 80, [('Full range', 8, True)], COAX),
    ('X8', '', 81, [('Full range', 8, True)], COAX),
    ('X8i', '', 82, [('Full range', 8, True)], COAX),
    ('X12', '', 83, [('Full range', 8, True)], COAX),
    ('X15 HiQ', '', 84, [('LF', 8, True), ('HF', 8, True)], COAX),
    # Subwoofers ([xxxx_60] / [xxxx_60_C] layouts, p.90)
    ('KS28', 'KS28', 90, [('SB', 4, True)], SUB),
    ('SB28', 'SB28', 90, [('SB', 4, True)], SUB),
    ('KS21', 'KS21', 90, [('SB', 8, True)], SUB),
    ('SB18', 'SB18', 90, [('SB', 8, True)], SUB),
    ('SB15m', 'SB15M', 90, [('SB', 8, True)], SUB),
    ('SB10i', '', 90, [('SB', 8, True)], SUB),
    ('SB6i', '', 90, [('SB', 4, True)], SUB),
]


# Why an impedance marked unverified is what it is. Goes in the cabinet's
# notes, and its source says the impedance is derived.
DERIVED_NOTES = {
    'Kiva': ("Impedance derived: 8 \u03a9 per Preset Guide default rule; consistent "
             "with the p.120 drive limit of 3 per output and field practice "
             "(3 Kiva per channel)."),
}


def source_for(page, model=None):
    source = f"{GUIDE}: sections p.{page}, impedance p.{IMPEDANCE_PAGE}"
    if model in DERIVED_NOTES:
        source += " (derived, see notes)"
    return source


class Command(BaseCommand):
    help = 'Load the curated L-Acoustics cabinet catalogue (sections + nominal impedance)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Reset seeded cabinets and sections to the shipped values',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options['force']
        created = updated = 0
        for order, (model, sv_names, page, sections, category) in enumerate(CABINETS, start=1):
            values = {
                'soundvision_names': sv_names,
                'source': source_for(page, model),
                'notes': DERIVED_NOTES.get(model, ''),
                'sort_order': order * 10,
                'category': category,
            }
            cabinet, was_created = CabinetModel.objects.get_or_create(
                manufacturer='L-Acoustics', model=model, defaults=values,
            )
            if was_created:
                created += 1
            elif force:
                for field, value in values.items():
                    setattr(cabinet, field, value)
                cabinet.save()
                updated += 1
            elif not cabinet.category:
                # Rows seeded before headings existed. A heading a superuser
                # has set is left alone.
                cabinet.category = category
                cabinet.save(update_fields=['category'])

            for s_order, (name, ohms, verified) in enumerate(sections, start=1):
                s_values = {
                    'nominal_impedance_ohms': Decimal(ohms),
                    'verified': verified,
                    'sort_order': s_order,
                }
                section, s_created = CabinetSection.objects.get_or_create(
                    cabinet=cabinet, name=name, defaults=s_values,
                )
                if not s_created and force:
                    for field, value in s_values.items():
                        setattr(section, field, value)
                    section.save()

        self.stdout.write(self.style.SUCCESS(
            f'Cabinets: {created} created, {updated} reset, '
            f'{len(CABINETS) - created - updated} left as they were'
        ))
