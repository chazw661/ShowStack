"""The touring LA7.16: its own provisional power profile, never merged with
the LA7.16i, and power plans that say which amps they cannot count.

Run with::

    python manage.py test planner.tests.test_la716_profile \\
        --settings=audiopatch.test_settings
"""

import importlib
from io import StringIO
from unittest import mock

from django.apps import apps
from django.core.management import call_command
from django.urls import reverse

from planner.models import (
    Amp, AmpLocation, AmpModel, AmplifierAssignment, AmplifierLoadRating, AmplifierProfile,
    AmplifierVoltageFactor, CabinetDriveCapacity, PowerDistributionPlan,
)
from planner.tests.test_amp_output_cabinets import Fixture
from planner.utils import amp_models, provisional_profiles
from planner.utils.provisional_profiles import PROVISIONAL

MIGRATION = importlib.import_module('planner.migrations.0212_la716_provisional_profile')


def run_migration():
    MIGRATION.forwards(apps, None)


def snapshot():
    """Everything the migration touches, comparable across runs."""
    la716 = AmplifierProfile.objects.filter(model='LA7.16')
    return {
        'profiles': list(AmplifierProfile.objects.order_by('pk').values_list(
            'pk', 'manufacturer', 'model', 'idle_power_watts', 'rated_power_watts',
            'figures_status', 'min_load_ohms')),
        'ratings': list(AmplifierLoadRating.objects.filter(profile__in=la716).order_by('pk')
                        .values_list('pk', 'condition', 'load_ohms', 'current_amps',
                                     'power_watts', 'verified', 'source')),
        'factors': list(AmplifierVoltageFactor.objects.filter(profile__in=la716).order_by('pk')
                        .values_list('pk', 'mains_voltage', 'current_multiplier', 'verified')),
        'amp_models': list(AmpModel.objects.order_by('pk').values_list(
            'pk', 'manufacturer', 'model_name', 'power_profile')),
    }


class Base(Fixture):
    """Prod's state: the touring row spelt "L'Acoustics", with no profile,
    next to the linked LA7.16i. The seed (which also creates the LA7.16
    profile) is undone first, so the migration starts from prod's state."""

    def setUp(self):
        super().setUp()
        AmplifierProfile.objects.filter(model='LA7.16').delete()
        self.touring = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA7.16', channel_count=16,
            sc32_connector_count=1)
        # A test database built from migrations already has an LA7.16i row;
        # use it, or the merge command would see two and keep the older.
        self.install, _ = AmpModel.objects.update_or_create(
            manufacturer='L-Acoustics', model_name='LA7.16i',
            defaults={'channel_count': 16, 'sc32_connector_count': 1,
                      'power_profile': AmplifierProfile.objects.get(model='LA7.16i')})
        self.models['LA7.16'] = self.touring


class MigrationTests(Base):

    def test_creates_links_and_normalises(self):
        run_migration()
        self.touring.refresh_from_db()
        la716 = AmplifierProfile.objects.get(manufacturer='L-Acoustics', model='LA7.16')
        la716i = AmplifierProfile.objects.get(model='LA7.16i')
        self.assertEqual(('L-Acoustics', la716), (self.touring.manufacturer, self.touring.power_profile))
        # The LA7.16i row and profile are untouched and separate.
        self.install.refresh_from_db()
        self.assertEqual(la716i, self.install.power_profile)
        self.assertNotEqual(la716.pk, la716i.pk)
        # Figures copied, marked provisional.
        self.assertEqual(PROVISIONAL, la716.figures_status)
        self.assertEqual('L-Acoustics LA7.16 (provisional)', str(la716))
        self.assertEqual((la716i.idle_power_watts, la716i.rated_power_watts, la716i.channels,
                          la716i.min_load_ohms),
                         (la716.idle_power_watts, la716.rated_power_watts, la716.channels,
                          la716.min_load_ohms))
        self.assertEqual(la716i.load_ratings.count(), la716.load_ratings.count())
        self.assertEqual(la716i.voltage_factors.count(), la716.voltage_factors.count())
        self.assertFalse(la716.load_ratings.filter(verified=True).exists())
        self.assertFalse(la716.voltage_factors.filter(verified=True).exists())
        self.assertTrue(all(r.source.startswith(PROVISIONAL) for r in la716.load_ratings.all()))
        third_8 = la716.load_ratings.get(condition='third', load_ohms=8)
        self.assertEqual(11, third_8.channels_driven)
        # The minimum load is published for both (the "LA7.16(i)" column),
        # so it is cited, not provisional.
        self.assertIn('LA7.16(i) column', la716.min_load_source)
        self.assertNotIn('provisional', la716.min_load_source)

    def test_applied_twice_gives_the_same_result(self):
        run_migration()
        first = snapshot()
        run_migration()
        self.assertEqual(first, snapshot())

    def test_normalises_any_row(self):
        other = AmpModel.objects.create(manufacturer="L'Acoustics", model_name='LA12X',
                                        channel_count=4)
        run_migration()
        other.refresh_from_db()
        self.assertEqual('L-Acoustics', other.manufacturer)

    def test_leaves_a_superuser_link_alone(self):
        la12x = AmplifierProfile.objects.get(model='LA12X')
        AmpModel.objects.filter(pk=self.touring.pk).update(power_profile=la12x)
        run_migration()
        self.touring.refresh_from_db()
        self.assertEqual(la12x, self.touring.power_profile)

    def test_without_an_la716i_profile_it_only_normalises(self):
        AmplifierProfile.objects.filter(model='LA7.16i').delete()
        run_migration()
        self.assertFalse(AmplifierProfile.objects.filter(model='LA7.16').exists())
        self.touring.refresh_from_db()
        self.assertEqual('L-Acoustics', self.touring.manufacturer)

    def test_seed_does_the_same_on_a_fresh_database(self):
        call_command('load_amp_profiles', stdout=StringIO())
        self.touring.refresh_from_db()
        self.assertEqual('LA7.16', self.touring.power_profile.model)
        self.assertTrue(self.touring.power_profile.is_provisional)


class DriveCapacityTests(Base):

    def test_la716_gets_the_la716i_column(self):
        run_migration()
        call_command('load_drive_capacity', stdout=StringIO())
        rows = {r.cabinet_id: (r.per_output, r.per_amp, r.source)
                for r in CabinetDriveCapacity.objects.filter(profile__model='LA7.16')}
        twin = {r.cabinet_id: (r.per_output, r.per_amp, r.source)
                for r in CabinetDriveCapacity.objects.filter(profile__model='LA7.16i')}
        self.assertEqual(31, len(rows))
        self.assertEqual(twin, rows)
        self.assertTrue(CabinetDriveCapacity.objects.get(
            profile__model='LA7.16', cabinet__model='X8').note.startswith('b:'))


class MergeGuardTests(Base):

    def setUp(self):
        super().setUp()
        run_migration()
        # A misspelt duplicate of the touring amp.
        self.dupe = AmpModel.objects.create(manufacturer='LA', model_name='LA 7.16',
                                            channel_count=16, sc32_connector_count=1)

    def group_members(self):
        return [{m.pk for m in [g.survivor, *g.extras]} for g in amp_models.duplicate_groups()]

    def test_la716_and_la716i_are_never_grouped(self):
        for members in self.group_members():
            self.assertFalse({self.touring.pk, self.install.pk} <= members, members)
        self.assertIn({self.touring.pk, self.dupe.pk}, self.group_members())

    def test_guard_holds_if_matching_gets_looser(self):
        # A future rule that drops a trailing "i" (install variants) would
        # make the keys equal; NEVER_MERGED still keeps them apart.
        real = amp_models.model_key

        def loose(manufacturer, model_name):
            maker, model = real(manufacturer, model_name)
            return maker, model[:-1] if model.endswith('i') else model

        with mock.patch.object(amp_models, 'model_key', loose):
            self.assertEqual(loose('L-Acoustics', 'LA7.16'), loose('L-Acoustics', 'LA7.16i'))
            for members in self.group_members():
                self.assertFalse({self.touring.pk, self.install.pk} <= members, members)
            offered = amp_models.find_existing('L-Acoustics', 'LA7.16')
            self.assertNotIn(self.install, offered)

    def test_add_form_never_offers_the_other(self):
        self.assertNotIn(self.install, amp_models.find_existing('L-Acoustics', 'LA7.16'))
        self.assertNotIn(self.touring, amp_models.find_existing('L-Acoustics', 'LA7.16i'))

    def test_merge_command_leaves_them_separate(self):
        call_command('merge_amp_models', '--apply', stdout=StringIO())
        self.assertTrue(AmpModel.objects.filter(pk=self.touring.pk).exists())
        self.assertTrue(AmpModel.objects.filter(pk=self.install.pk).exists())
        self.assertFalse(AmpModel.objects.filter(pk=self.dupe.pk).exists())
        self.install.refresh_from_db()
        self.assertEqual('LA7.16i', self.install.power_profile.model)


class PlanTests(Base):

    def setUp(self):
        super().setUp()
        run_migration()
        self.plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='Hall')
        self.use(self.owner)

    def page(self):
        return self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[self.plan.pk]))

    def test_la716_draws_and_says_provisional(self):
        row = AmplifierAssignment.objects.create(
            distribution_plan=self.plan, amplifier=AmplifierProfile.objects.get(model='LA7.16'),
            quantity=2, zone='FOH')
        self.assertGreater(row.calculated_current_per_unit, 0)
        page = self.page()
        self.assertContains(page, 'L-Acoustics LA7.16 (provisional)')
        self.assertContains(page, PROVISIONAL)

    def test_amp_without_a_profile_is_named(self):
        location = AmpLocation.objects.get_or_create(project=self.project, name='HL')[0]
        bare = AmpModel.objects.create(manufacturer='Acme', model_name='Test Amp', channel_count=4)
        Amp.objects.create(project=self.project, location=location, amp_model=bare, name='T1')
        Amp.objects.create(project=self.project, location=location, amp_model=bare, name='T2')
        Amp.objects.create(project=self.project, location=location, amp_model=self.touring, name='L1')
        self.assertContains(self.page(), '2 amps excluded from totals:</strong>\n            Acme Test Amp ×2.')

    def test_no_warning_when_every_amp_has_a_profile(self):
        self.assertNotContains(self.page(), 'excluded from totals')

    def test_system_report_section(self):
        from planner.utils.pdf_exports.report_kit import styles
        from planner.utils.pdf_exports.system_report import _section_power
        AmplifierAssignment.objects.create(
            distribution_plan=self.plan, amplifier=AmplifierProfile.objects.get(model='LA7.16'),
            quantity=1, zone='FOH')
        location = AmpLocation.objects.get_or_create(project=self.project, name='HL')[0]
        bare = AmpModel.objects.create(manufacturer='Acme', model_name='Test Amp', channel_count=4)
        Amp.objects.create(project=self.project, location=location, amp_model=bare, name='T1')
        story = _section_power(self.project, styles(), PowerDistributionPlan)
        text = ' '.join(getattr(f, 'text', '') for f in story)
        self.assertIn(PROVISIONAL, text)
        self.assertIn('1 amp excluded from totals:', text)
