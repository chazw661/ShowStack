"""Seed CabinetDriveCapacity: how many of each cabinet one amp may drive.

Source for every cell: L-Acoustics, *Preset Guide owner's manual (EN)*,
version 25.0, "Enclosure drive capacity per amplified controller",
pp.119-120. Each cell is "per output / total"; "—" (None here) means the
amp does not drive that enclosure.

* Per output: enclosures in parallel for a passive cabinet, sections in
  parallel for an active one (footnote *).
* Total: enclosures per amplified controller.
* The LA7.16(i) column is stored on the LA7.16i profile. Its footnote b
  goes in each of its rows' note.
* Not stored:
  - LA2Xi: there is no LA2Xi amplifier profile. Its SE / BTL / PBTL
    columns would also need an output mode the amp module does not have.
  - LA8: the v25.0 table has no LA8 column.
  - Rows for enclosures that are not in the cabinet catalogue. They are
    kept below with no catalogue name, so the transcription is complete.

Runs on every deploy (railway.json), after load_amp_profiles and
load_cabinets. Without --force it only creates missing rows, so a
superuser's edits in the admin survive a redeploy.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import AmplifierProfile, CabinetDriveCapacity, CabinetModel

GUIDE = "L-Acoustics Preset Guide owner's manual (EN) v25.0"

# Guide column -> AmplifierProfile.model
AMPS = ['LA4X', 'LA7.16i', 'LA12X']

NOTE_B = ("b: given for nominal use, all channels at full power. Same signal "
          "on all outputs: never exceed these numbers, whatever the Power "
          "Budget shows. On a 100 V supply, drive fewer so the power gauge "
          "stays under 75%.")
NOTE_C = "c: up to two Syva Low per output, but no more than six per controller at high level."

# (guide row, catalogue model or None, page, LA4X, LA7.16(i), LA12X)
# Each cell is (per output, total) or None for "—".
TABLE = [
    # coaxial enclosures
    ('X4i', 'X4i', 119, (4, 16), (4, 64), (6, 24)),
    ('5XT', '5XT', 119, (4, 16), (3, 48), (6, 24)),
    ('X6i', 'X6i', 119, (2, 8), (1, 16), (3, 12)),
    ('X8', 'X8', 119, (2, 8), (1, 16), (3, 12)),
    ('X8i', 'X8i', 119, (2, 8), (1, 16), (3, 12)),
    ('X12', 'X12', 119, (1, 4), (1, 14), (3, 12)),
    ('X15 HiQ', 'X15 HiQ', 119, (1, 2), (1, 8), (3, 6)),
    ('8XT', None, 119, (2, 8), None, (3, 12)),
    ('Active 12XT', None, 119, (2, 4), None, (3, 6)),
    ('Passive 12XT', None, 119, (1, 4), None, (3, 12)),
    ('112XT', None, 119, (2, 4), None, (3, 6)),
    ('115XT HiQ', None, 119, (1, 2), None, (3, 6)),
    ('115XT', None, 119, (1, 2), None, (3, 6)),
    ('MTD108a', None, 119, (2, 8), None, (3, 12)),
    ('MTD112b', None, 119, (1, 4), None, (2, 8)),
    ('Active MTD115b', None, 119, (1, 2), None, (2, 4)),
    ('Passive MTD115b', None, 119, (1, 4), None, (2, 8)),
    # colinear sources
    ('Soka', 'Soka', 119, (2, 8), (1, 16), (3, 12)),
    ('Syva', 'Syva', 119, (1, 4), (1, 10), (3, 12)),
    # constant curvature WST enclosures
    ('A10(i) Wide/Focus', 'A10 Wide/Focus', 119, (2, 8), (1, 16), (3, 12)),
    ('A15(i) Wide/Focus', 'A15 Wide/Focus', 119, (1, 4), (1, 10), (3, 12)),
    ('ARCS Wide/Focus', 'ARCS Wide/Focus', 119, (1, 4), None, (3, 12)),
    ('ARCS II', 'ARCS II', 119, (1, 2), None, (3, 6)),
    ('ARCS', None, 119, (1, 2), None, (3, 6)),
    # variable curvature WST enclosures
    ('K1', 'K1', 119, None, None, (2, 2)),
    ('K1-SB', 'K1-SB', 119, None, None, (1, 4)),
    ('K2', 'K2', 119, (1, 1), (1, 4), (3, 3)),
    ('K3(i)', 'K3', 120, (1, 2), (1, 8), (3, 6)),
    ('Kara(i)', 'Kara', 120, (2, 4), None, (3, 6)),
    ('Kara II(i)', 'Kara II', 120, (2, 4), (1, 8), (3, 6)),
    ('Kiva II', 'Kiva II', 120, (2, 8), (2, 32), (6, 24)),
    ('Kiva / Kilo', 'Kiva', 120, (2, 8), None, (3, 12)),
    ('Kudo', None, 120, (1, 1), None, (3, 3)),
    ('V-DOSC', None, 120, None, None, (2, 2)),
    ('dV-DOSC', None, 120, None, None, (3, 6)),
    # progressive curvature WST enclosures
    ('L2 / L2D', 'L2 / L2D', 120, None, (1, 1), None),
    # subwoofer enclosures
    ('KS28', 'KS28', 120, None, None, (1, 4)),
    ('SB28', 'SB28', 120, None, None, (1, 4)),
    ('KS21(i)', 'KS21', 120, (1, 4), (1, 8), (2, 8)),
    ('SB18(i/m) / SB18 IIi', 'SB18', 120, (1, 4), (1, 6), (3, 12)),
    ('SB218', None, 120, None, None, (1, 4)),
    ('SB118', None, 120, (1, 4), None, (2, 8)),
    ('SB15m', 'SB15m', 120, (1, 4), (1, 9), (3, 12)),
    ('Syva Low', 'Syva Low', 120, (1, 4), (1, 8), (2, 6)),
    ('Syva Sub', 'Syva Sub', 120, (1, 4), (1, 16), (3, 12)),
    ('SB10i', 'SB10i', 120, (2, 8), (2, 32), (3, 12)),
    ('SB6i', 'SB6i', 120, (1, 4), (1, 16), (2, 8)),
    ('dV-SUB', None, 120, None, None, (1, 4)),
]


def note_for(amp, guide_row):
    if amp == 'LA7.16i':
        return NOTE_B
    if amp == 'LA12X' and guide_row == 'Syva Low':
        return NOTE_C
    return ''


class Command(BaseCommand):
    help = 'Load the Preset Guide drive-capacity table (enclosures per amp output and per amp)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Reset seeded cells to the shipped values',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options['force']
        profiles = {p.model: p for p in AmplifierProfile.objects.filter(
            manufacturer='L-Acoustics', model__in=AMPS)}
        cabinets = {c.model: c for c in CabinetModel.objects.filter(manufacturer='L-Acoustics')}
        created = updated = 0
        skipped = []
        for guide_row, model, page, *cells in TABLE:
            cabinet = cabinets.get(model) if model else None
            if cabinet is None:
                skipped.append(guide_row)
                continue
            for amp, cell in zip(AMPS, cells):
                profile = profiles.get(amp)
                if profile is None:
                    continue
                per_output, per_amp = cell if cell else (None, None)
                values = {
                    'per_output': per_output,
                    'per_amp': per_amp,
                    'guide_row': guide_row,
                    'note': note_for(amp, guide_row),
                    'source': f"{GUIDE}, p.{page}",
                }
                row, was_created = CabinetDriveCapacity.objects.get_or_create(
                    profile=profile, cabinet=cabinet, defaults=values,
                )
                if was_created:
                    created += 1
                elif force:
                    for field, value in values.items():
                        setattr(row, field, value)
                    row.save()
                    updated += 1

        missing = [a for a in AMPS if a not in profiles]
        self.stdout.write(self.style.SUCCESS(
            f'Drive capacity: {created} created, {updated} reset'
        ))
        if missing:
            self.stdout.write(f'  No profile for: {", ".join(missing)}')
        if skipped:
            self.stdout.write(f'  Not in the cabinet catalogue: {", ".join(skipped)}')
