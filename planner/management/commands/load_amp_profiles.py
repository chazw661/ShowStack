"""Seed the Amplifier Profile catalogue and its cited mains-draw tables.

Two parts, with different redeploy rules:

* The profile rows themselves (the legacy single-figure fields the current
  calculator reads) load only into an empty table, or with --force, as before.
* The per-load mains-draw tables (AmplifierLoadRating), voltage factors
  (AmplifierVoltageFactor) and each profile's minimum load per output are
  created whenever missing, so they reach a database whose profiles already
  exist; --force resets them to the values below. A superuser's edit to an
  existing row survives a redeploy.

All draw tables are as printed in the L-Acoustics manuals: 230 V, all
channels driven, mains current and power. The power factor is not published.
Each row cites document, version and page; LA4X rows are unverified (the only
copy available was a garbled text extraction).

Finally each profile is linked to the rack view's AmpModel of the same name,
where an L-Acoustics AmpModel has no profile yet.
"""

import re
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import (
    AmpModel, AmplifierLoadRating, AmplifierProfile, AmplifierVoltageFactor,
)

SOURCES = {
    'LA8': ("L-Acoustics LA8 user manual (EN) v5.0, p.16",
            'https://hire.on-productions.co.uk/uploads/docs/LA8_UM_EN_5_705.0.pdf', True),
    'LA4X': ("L-Acoustics LA4X user manual (EN) v4.0, p.15 -- verify: transcribed "
             "from a garbled text extraction",
             'https://www.manualslib.com/manual/1135781/L-Acoustics-La4x.html?page=15', False),
    'LA12X': ("L-Acoustics LA12X user manual (EN) v1.0, p.18",
              'https://www.promusic.cz/sites/default/files/product/field_files/la12x_um_en.pdf', True),
    'LA7.16i': ("L-Acoustics LA7.16i owner's manual v5.0, pp.24-25",
                'https://www.bestecaudio.com/wp/wp-content/uploads/LA7.16i_OM_JP-5-0.pdf', True),
}

# model -> [(condition, load_ohms or None, amps, '<' bound, watts, channels_driven)]
# load_ohms None = not load-dependent (standby, idle, single-column tables).
LOAD_RATINGS = {
    'LA8': [
        ('standby', None, '0.1', True, 12, None),
        ('idle', None, '0.5', False, 115, None),
        ('eighth', 8, '10', False, 1300, None),
        ('eighth', 4, '11', False, 1500, None),
        ('third', 8, '15', False, 1950, None),
        ('third', 4, '22', False, 3100, None),
    ],
    'LA4X': [
        ('standby', None, '0.1', True, 11, None),
        ('idle', None, '0.26', False, 60, None),
        ('eighth', None, '3', False, 750, None),
        ('third', None, '7', False, 1600, None),
    ],
    'LA12X': [
        ('standby', None, '0.6', False, 10, None),
        ('idle', None, '1', False, 160, None),
        ('eighth', 8, '4.8', False, 1050, None),
        ('eighth', 4, '8.1', False, 1850, None),
        ('eighth', '2.7', '11.5', False, 2400, None),
        ('third', 8, '10.5', False, 2300, None),
        ('third', 4, '19', False, 4200, None),
        ('third', '2.7', '26', False, 5500, None),
    ],
    'LA7.16i': [
        ('standby', None, '0.8', False, 18, None),
        ('idle', None, '1.0', False, 138, None),
        ('eighth', 16, '6.7', False, 1500, None),
        ('eighth', 8, '11.2', False, 2500, None),
        ('eighth', 4, '13', False, 2900, None),
        ('third', 16, '16.9', False, 3800, None),
        # Footnoted in the manual: measured with 11 and 10 channels driven.
        ('third', 8, '18.6', False, 4200, 11),
        ('third', 4, '19.2', False, 4300, 10),
    ],
}

# Mains current at V relative to 230 V. 1.15 @ 200 V and 2.3 @ 100 V for
# every model; 1.9 @ 120 V except LA8 (2.0) and LA7.16 (1.92).
VOLTAGE_FACTORS = {
    model: {200: '1.15', 120: at_120, 100: '2.3'}
    for model, at_120 in (('LA8', '2.0'), ('LA4X', '1.9'), ('LA12X', '1.9'),
                          ('LA7.16i', '1.92'))
}
VOLTAGE_FACTOR_NOTE = "; current multiplier vs 230 V (page not recorded)"

# Lowest load per output. The Preset Guide's drive-capacity tables give the
# most enclosures each model may drive in parallel on one output; with the
# total-impedance table (p.118) that is the lowest load it is rated for.
GUIDE = "L-Acoustics Preset Guide owner's manual (EN) v25.0"
MIN_LOADS = {
    # The v25.0 drive-capacity table (pp.119-120) has no LA8 column, so this
    # is not from it: 2.7 ohm (3 x 8 ohm, p.118) as for the LA12X.
    'LA8': ('2.7', f"Assumed: {GUIDE} pp.119-120 has no LA8 column; 2.7 ohm "
                   "(3 x 8 ohm, p.118) as for the LA12X -- check the LA8 manual"),
    'LA4X': ('4', f"{GUIDE} p.119: up to 2 x 8 ohm or 4 x 16 ohm enclosures "
                  "per output (4 ohm, p.118)"),
    'LA12X': ('2.7', f"{GUIDE} p.119: up to 3 x 8 ohm or 6 x 16 ohm enclosures "
                     "per output (2.7 ohm, p.118); LA12X UM v1.0 p.18 publishes "
                     "draw down to 2.7 ohm"),
    'LA7.16i': ('4', f"{GUIDE} p.119: up to 4 x X4i (16 ohm) per output "
                     "(4 ohm, p.118); LA7.16i OM v5.0 pp.24-25 publishes draw "
                     "down to 4 ohm"),
}


def _dec(value):
    return None if value is None else Decimal(str(value))


# Citations shipped before and since corrected; replaced where still stored.
SUPERSEDED_MIN_LOAD_SOURCES = {
    'LA8': f"{GUIDE} p.120: up to 3 x 8 ohm enclosures per output (2.7 ohm, p.118)",
}


class Command(BaseCommand):
    help = 'Load L-Acoustics amplifier profiles into the database'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reload even if profiles already exist',
        )

    def handle(self, *args, **options):
        self._load_profiles(options)
        with transaction.atomic():
            self._load_ratings(force=options['force'])
        self._link_amp_models()

    def _load_profiles(self, options):
        # Check if profiles already exist
        existing_count = AmplifierProfile.objects.count()
        
        if existing_count > 0 and not options['force']:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Amplifier profiles already loaded ({existing_count} profiles exist). '
                    'Use --force to reload.'
                )
            )
            return
        
        amplifiers = [
            {
                'manufacturer': "L-Acoustics",
                'model': 'LA8',
                'idle_power_watts': 190,
                'rated_power_watts': 1100,
                'peak_power_watts': 2200,
                'max_power_watts': 8800,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.92,
                'channels': 4,
                'rack_units': 2,
                'weight_kg': 11.5,
                'notes': '4 channels, 2200W @ 8Ω per channel pair'
            },
            {
                'manufacturer': "L-Acoustics",
                'model': 'LA4X',
                'idle_power_watts': 140,
                'rated_power_watts': 500,
                'peak_power_watts': 1000,
                'max_power_watts': 4000,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.93,
                'channels': 4,
                'rack_units': 1,
                'weight_kg': 6.6,
                'notes': '4 channels, 1000W @ 8Ω per channel, 1RU'
            },
            {
                'manufacturer': "L-Acoustics",
                'model': 'LA12X',
                'idle_power_watts': 240,
                'rated_power_watts': 1500,
                'peak_power_watts': 3000,
                'max_power_watts': 12000,
                'nominal_voltage': 208,
                'power_factor': 0.95,
                'efficiency': 0.93,
                'channels': 4,
                'rack_units': 2,
                'weight_kg': 15.9,
                'notes': '4 channels, 3300W @ 2.7Ω per channel, flagship model'
            },
            {
                'manufacturer': "L-Acoustics",
                'model': 'LA7.16i',
                'idle_power_watts': 100,
                'rated_power_watts': 700,
                'peak_power_watts': 1400,
                'max_power_watts': 5600,
                'nominal_voltage': 208,
                'power_factor': 0.94,
                'efficiency': 0.92,
                'channels': 16,   # was 7; 16 outputs on one SC32 (cf. AmpModel, 0170)
                'rack_units': 2,
                'weight_kg': 8.5,
                'notes': '16 channels, 800W @ 4Ω per channel, touring grade'
            },
        ]

        created_count = 0
        updated_count = 0

        for amp_data in amplifiers:
            amp, created = AmplifierProfile.objects.update_or_create(
                manufacturer=amp_data['manufacturer'],
                model=amp_data['model'],
                defaults=amp_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created: {amp.manufacturer} {amp.model}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated: {amp.manufacturer} {amp.model}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: {created_count} created, {updated_count} updated'
            )
        )

    def _upsert(self, model, lookup, values, force):
        row, created = model.objects.get_or_create(**lookup, defaults=values)
        if not created and force:
            for field, value in values.items():
                setattr(row, field, value)
            row.save()
        return created

    def _load_ratings(self, force):
        created = 0
        for model_name, rows in LOAD_RATINGS.items():
            profile = AmplifierProfile.objects.filter(
                manufacturer='L-Acoustics', model=model_name).first()
            if profile is None:
                self.stdout.write(self.style.WARNING(
                    f'No {model_name} profile; its load ratings were skipped'))
                continue
            source, url, verified = SOURCES[model_name]
            for condition, ohms, amps, bound, watts, driven in rows:
                created += self._upsert(
                    AmplifierLoadRating,
                    {'profile': profile, 'condition': condition,
                     'load_ohms': _dec(ohms), 'mains_voltage': 230},
                    {'current_amps': _dec(amps), 'current_is_upper_bound': bound,
                     'power_watts': watts, 'channels_driven': driven,
                     'source': source, 'source_url': url, 'verified': verified},
                    force,
                )
            for volts, factor in VOLTAGE_FACTORS[model_name].items():
                created += self._upsert(
                    AmplifierVoltageFactor,
                    {'profile': profile, 'mains_voltage': volts},
                    {'current_multiplier': _dec(factor),
                     'source': source + VOLTAGE_FACTOR_NOTE, 'verified': verified},
                    force,
                )
        self.stdout.write(self.style.SUCCESS(
            f'Load ratings / voltage factors: {created} created'))
        self._load_min_loads(force)

    def _load_min_loads(self, force):
        """Fill each profile's minimum load where it is empty (all of them
        with --force), so a superuser's value survives a redeploy."""
        filled = 0
        for model_name, (ohms, source) in MIN_LOADS.items():
            profiles = AmplifierProfile.objects.filter(
                manufacturer='L-Acoustics', model=model_name)
            if not force:
                profiles = profiles.filter(min_load_ohms__isnull=True)
            filled += profiles.update(min_load_ohms=_dec(ohms), min_load_source=source)
        # Correct a citation seeded wrongly, leaving the value alone.
        for model_name, old_source in SUPERSEDED_MIN_LOAD_SOURCES.items():
            AmplifierProfile.objects.filter(
                manufacturer='L-Acoustics', model=model_name,
                min_load_source=old_source,
            ).update(min_load_source=MIN_LOADS[model_name][1])
        self.stdout.write(self.style.SUCCESS(f'Minimum loads filled: {filled}'))

    def _link_amp_models(self):
        """Point each L-Acoustics AmpModel without a profile at the profile of
        the same model name. Manufacturer spellings vary in existing rows
        ("L-Acoustics", "Lacoustics", "L'Acoustics"), so compare letters only;
        anything else ("LA8-2") is left for a superuser to set by hand."""
        linked = 0
        profiles = {p.model.lower(): p for p in AmplifierProfile.objects.all()}
        for amp_model in AmpModel.objects.filter(power_profile__isnull=True):
            if re.sub(r'[^a-z]', '', amp_model.manufacturer.lower()) != 'lacoustics':
                continue
            profile = profiles.get(amp_model.model_name.strip().lower())
            if profile is not None:
                amp_model.power_profile = profile
                amp_model.save(update_fields=['power_profile'])
                linked += 1
        self.stdout.write(self.style.SUCCESS(f'Amp models linked to a profile: {linked}'))
