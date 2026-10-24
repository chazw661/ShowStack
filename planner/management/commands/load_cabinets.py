"""Seed the cabinet catalogue (CabinetModel + CabinetSection).

Source for every row: L-Acoustics, *Preset Guide owner's manual (EN)*,
version 25.0, distributed October 29, 2024.

* Sections come from each enclosure's factory preset output table -- the
  "channels" column (LF / MF / HF / LC, or PA for a passive full-range
  enclosure, SB / SR for subwoofers). The page cited per cabinet is that
  table's page. A passive enclosure (PA on every output) is one 'Full range'
  section.
* Nominal impedances come from "Impedance load", p.118: most enclosures are
  8 ohm; the 16 ohm exceptions are K2 (HF section), Kiva II, V-DOSC (HF
  section), 5XT and X4i; the 4 ohm exceptions are SB28, KS28, Syva Low, K1-SB
  and SB6i.

``verified=False`` marks an impedance the guide does not state for that
section (it falls back to the general 8 ohm rule for a multi-module enclosure).

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

# (model, soundvision names, preset-table page, [(section, ohms, verified)])
CABINETS = [
    # Variable curvature WST
    ('K1', 'K1', 48, [('LF', 8, True), ('MF', 8, True), ('HF', 8, True)]),
    ('K1-SB', '', 50, [('SB', 4, True)]),
    ('K2', 'K2', 50, [('LF', 8, True), ('MF', 8, True), ('HF', 16, True)]),
    ('K3', 'K3', 53, [('LF', 8, True), ('HF', 8, True)]),
    ('Kara II', 'KARA II', 56, [('LF', 8, True), ('HF', 8, True)]),
    ('Kiva II', 'KIVA II', 58, [('Full range', 16, True)]),
    # Constant curvature WST
    ('ARCS Wide/Focus', 'ARCS', 67, [('Full range', 8, True)]),
    ('A10 Wide/Focus', 'A10', 68, [('Full range', 8, True)]),
    ('A15 Wide/Focus', 'A15', 70, [('Full range', 8, True)]),
    ('ARCS II', '', 72, [('LF', 8, True), ('HF', 8, True)]),
    # Progressive ultra-dense line source
    ('L2 / L2D', '', 47, [('LC', 8, False), ('LF', 8, False), ('HF', 8, False)]),
    # Colinear sources
    ('Syva', '', 74, [('Full range', 8, True)]),
    ('Syva Low', '', 75, [('LF', 4, True)]),
    ('Syva Sub', '', 75, [('LF', 8, True)]),
    ('Soka', '', 76, [('Full range', 8, True)]),
    # Coaxial
    ('X4i', '', 78, [('Full range', 16, True)]),
    ('5XT', '', 79, [('Full range', 16, True)]),
    ('X6i', '', 80, [('Full range', 8, True)]),
    ('X8', '', 81, [('Full range', 8, True)]),
    ('X8i', '', 82, [('Full range', 8, True)]),
    ('X12', '', 83, [('Full range', 8, True)]),
    ('X15 HiQ', '', 84, [('LF', 8, True), ('HF', 8, True)]),
    # Subwoofers ([xxxx_60] / [xxxx_60_C] layouts, p.90)
    ('KS28', 'KS28', 90, [('SB', 4, True)]),
    ('SB28', 'SB28', 90, [('SB', 4, True)]),
    ('KS21', 'KS21', 90, [('SB', 8, True)]),
    ('SB18', 'SB18', 90, [('SB', 8, True)]),
    ('SB15m', 'SB15M', 90, [('SB', 8, True)]),
    ('SB10i', '', 90, [('SB', 8, True)]),
    ('SB6i', '', 90, [('SB', 4, True)]),
]


def source_for(page):
    return f"{GUIDE}: sections p.{page}, impedance p.{IMPEDANCE_PAGE}"


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
        for order, (model, sv_names, page, sections) in enumerate(CABINETS, start=1):
            values = {
                'soundvision_names': sv_names,
                'source': source_for(page),
                'sort_order': order * 10,
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
