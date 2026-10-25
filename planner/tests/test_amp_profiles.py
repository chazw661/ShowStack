"""#15: the shipped LA7.16i Amplifier Profile is 16 channels.

Run with::

    python manage.py test planner.tests.test_amp_profiles \\
        --settings=audiopatch.test_settings
"""

import importlib
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.test import TestCase

from planner.models import AmpModel, AmplifierProfile

migration_0203 = importlib.import_module(
    'planner.migrations.0203_la7_16i_profile_16_channels')
migration_0204 = importlib.import_module(
    'planner.migrations.0204_amplifier_profile_l_acoustics_spelling')

FIGURES = ('idle_power_watts', 'rated_power_watts', 'peak_power_watts',
           'max_power_watts', 'nominal_voltage', 'power_factor', 'efficiency',
           'channels', 'rack_units', 'weight_kg', 'notes')


def profile(**kw):
    values = dict(manufacturer='L-Acoustics', model='LA7.16i', idle_power_watts=100,
                  rated_power_watts=700, peak_power_watts=1400, max_power_watts=5600)
    values.update(kw)
    return AmplifierProfile.objects.create(**values)


class LA716iProfileTests(TestCase):

    def test_a_fresh_load_ships_16_channels(self):
        call_command('load_amp_profiles', stdout=StringIO())
        la716 = AmplifierProfile.objects.get(model='LA7.16i')
        self.assertEqual(la716.channels, 16)
        self.assertTrue(la716.notes.startswith('16 channels'))

    def test_profile_and_amp_model_agree(self):
        # The rack view's AmpModel was fixed to 16 in migration 0170.
        call_command('load_amp_profiles', stdout=StringIO())
        call_command('populate_amp_models', stdout=StringIO())
        self.assertEqual(AmplifierProfile.objects.get(model='LA7.16i').channels,
                         AmpModel.objects.get(model_name='LA7.16i').channel_count)

    def test_0203_fixes_the_shipped_row(self):
        row = profile(channels=7, notes=migration_0203.OLD_NOTES)
        migration_0203.sixteen(django_apps, None)
        row.refresh_from_db()
        self.assertEqual((row.channels, row.notes), (16, migration_0203.NEW_NOTES))

    def test_0203_leaves_a_hand_edited_row_alone(self):
        row = profile(channels=8, notes='ours')
        kept_notes = profile(model='LA7.16i', channels=7, notes='edited note')
        migration_0203.sixteen(django_apps, None)
        row.refresh_from_db()
        kept_notes.refresh_from_db()
        self.assertEqual(row.channels, 8)
        self.assertEqual((kept_notes.channels, kept_notes.notes), (16, 'edited note'))


class ManufacturerSpellingTests(TestCase):

    def test_a_fresh_load_spells_it_one_way(self):
        call_command('load_amp_profiles', stdout=StringIO())
        self.assertEqual(set(AmplifierProfile.objects.values_list('manufacturer', flat=True)),
                         {'L-Acoustics'})
        # LA4X, LA8, LA12X, LA7.16i, and the touring LA7.16 (provisional).
        self.assertEqual(AmplifierProfile.objects.count(), 5)

    def test_0204_renames_and_touches_nothing_else(self):
        old = [profile(manufacturer="L'Acoustics", model='LA8', channels=4),
               profile(manufacturer='L\u2019Acoustics', model='LA4X', channels=4)]
        other = profile(manufacturer='d&b audiotechnik', model='D80', channels=4)
        before = {p.pk: AmplifierProfile.objects.filter(pk=p.pk).values(*FIGURES).get()
                  for p in old + [other]}
        migration_0204.normalize(django_apps, None)
        for row in old:
            row.refresh_from_db()
            self.assertEqual(row.manufacturer, 'L-Acoustics')
        other.refresh_from_db()
        self.assertEqual(other.manufacturer, 'd&b audiotechnik')
        after = {pk: AmplifierProfile.objects.filter(pk=pk).values(*FIGURES).get()
                 for pk in before}
        self.assertEqual(after, before)

    def test_a_forced_reload_after_0204_updates_in_place(self):
        # update_or_create keys on (manufacturer, model): with the seed and the
        # migrated rows spelled alike, --force must not add a second LA8.
        profile(manufacturer="L'Acoustics", model='LA8', channels=4)
        migration_0204.normalize(django_apps, None)
        call_command('load_amp_profiles', '--force', stdout=StringIO())
        self.assertEqual(AmplifierProfile.objects.filter(model='LA8').count(), 1)
