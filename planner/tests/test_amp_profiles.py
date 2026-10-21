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
