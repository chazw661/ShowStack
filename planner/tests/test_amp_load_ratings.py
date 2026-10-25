"""Per-load mains-draw tables: the seeded figures, redeploy rules, AmpModel links.

Run with::

    python manage.py test planner.tests.test_amp_load_ratings \\
        --settings=audiopatch.test_settings
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from planner.admin import AmplifierLoadRatingInline, AmpModelAdmin
from planner.admin_site import showstack_admin_site
from planner.models import (
    AmpModel, AmplifierLoadRating, AmplifierProfile, AmplifierVoltageFactor,
)


def load(*args):
    call_command('load_amp_profiles', *args, stdout=StringIO())


def rating(model, condition, ohms=None):
    return AmplifierLoadRating.objects.get(
        profile__model=model, condition=condition,
        load_ohms=None if ohms is None else Decimal(str(ohms)), mains_voltage=230,
    )


class SeededFiguresTests(TestCase):

    def setUp(self):
        load()

    def test_row_counts(self):
        counts = {m: AmplifierLoadRating.objects.filter(profile__model=m).count()
                  for m in ('LA8', 'LA4X', 'LA12X', 'LA7.16i')}
        self.assertEqual({'LA8': 6, 'LA4X': 4, 'LA12X': 8, 'LA7.16i': 8}, counts)

    def test_amps_and_watts_as_published(self):
        r = rating('LA12X', 'third', '2.7')
        self.assertEqual((Decimal('26'), 5500), (r.current_amps, r.power_watts))
        r = rating('LA8', 'eighth', 4)
        self.assertEqual((Decimal('11'), 1500), (r.current_amps, r.power_watts))
        r = rating('LA7.16i', 'idle')
        self.assertEqual((Decimal('1.0'), 138), (r.current_amps, r.power_watts))

    def test_la8_has_no_2_7_ohm_row(self):
        self.assertFalse(AmplifierLoadRating.objects.filter(
            profile__model='LA8', load_ohms=Decimal('2.7')).exists())

    def test_la716i_footnoted_channel_counts(self):
        self.assertEqual(11, rating('LA7.16i', 'third', 8).channels_driven)
        self.assertEqual(10, rating('LA7.16i', 'third', 4).channels_driven)
        self.assertIsNone(rating('LA7.16i', 'third', 16).channels_driven)

    def test_standby_upper_bounds(self):
        self.assertTrue(rating('LA8', 'standby').current_is_upper_bound)
        self.assertTrue(rating('LA4X', 'standby').current_is_upper_bound)
        self.assertFalse(rating('LA12X', 'standby').current_is_upper_bound)

    def test_la4x_is_load_independent_and_unverified(self):
        la4x = AmplifierLoadRating.objects.filter(profile__model='LA4X')
        self.assertFalse(la4x.filter(load_ohms__isnull=False).exists())
        self.assertFalse(la4x.filter(verified=True).exists())
        self.assertFalse(AmplifierVoltageFactor.objects.filter(
            profile__model='LA4X', verified=True).exists())
        # The LA7.16's are unverified too: a provisional copy of the LA7.16i's.
        self.assertEqual(
            {'LA4X', 'LA7.16'},
            set(AmplifierLoadRating.objects.filter(verified=False)
                .values_list('profile__model', flat=True)))

    def test_every_row_cites_a_page_and_url(self):
        for r in AmplifierLoadRating.objects.all():
            self.assertRegex(r.source, r'pp?\.\d+', str(r))
            self.assertTrue(r.source_url.startswith('https://'), str(r))

    def test_voltage_factors(self):
        def factor(model, volts):
            return AmplifierVoltageFactor.objects.get(
                profile__model=model, mains_voltage=volts).current_multiplier
        self.assertEqual(Decimal('2.0'), factor('LA8', 120))
        self.assertEqual(Decimal('1.92'), factor('LA7.16i', 120))
        self.assertEqual(Decimal('1.9'), factor('LA12X', 120))
        for model in ('LA8', 'LA4X', 'LA12X', 'LA7.16i'):
            self.assertEqual(Decimal('1.15'), factor(model, 200))
            self.assertEqual(Decimal('2.3'), factor(model, 100))

    def test_a_second_idle_row_is_refused(self):
        profile = AmplifierProfile.objects.get(model='LA12X')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AmplifierLoadRating.objects.create(
                profile=profile, condition='idle', current_amps=1, power_watts=1,
                source='x')


class RedeployTests(TestCase):

    def test_tables_reach_a_database_whose_profiles_already_exist(self):
        # The production case: profiles were loaded long ago, so the
        # profile part returns early -- the tables must still be created.
        load()
        AmplifierLoadRating.objects.all().delete()
        AmplifierVoltageFactor.objects.all().delete()
        load()
        # 26 published + the LA7.16's provisional copy of the LA7.16i's 8.
        self.assertEqual(34, AmplifierLoadRating.objects.count())
        self.assertEqual(15, AmplifierVoltageFactor.objects.count())

    def test_an_edit_survives_and_force_resets(self):
        load()
        r = rating('LA12X', 'idle')
        r.power_watts = 999
        r.save()
        load()
        r.refresh_from_db()
        self.assertEqual(999, r.power_watts)
        load('--force')
        r.refresh_from_db()
        self.assertEqual(160, r.power_watts)
        self.assertEqual(34, AmplifierLoadRating.objects.count())


class AmpModelLinkTests(TestCase):

    def test_links_by_name_across_spellings_and_leaves_the_rest(self):
        la12x = AmpModel.objects.create(manufacturer='Lacoustics', model_name='LA12X',
                                        channel_count=4)
        la8_2 = AmpModel.objects.create(manufacturer='L-Acoustics', model_name='LA8-2',
                                        channel_count=4)
        other = AmpModel.objects.create(manufacturer='Powersoft', model_name='LA8',
                                        channel_count=4)
        load()
        for m in (la12x, la8_2, other):
            m.refresh_from_db()
        self.assertEqual('LA12X', la12x.power_profile.model)
        self.assertIsNone(la8_2.power_profile)
        self.assertIsNone(other.power_profile)

    def test_a_hand_set_link_is_kept(self):
        load()
        la8 = AmplifierProfile.objects.get(model='LA8')
        amp_model = AmpModel.objects.create(manufacturer='L-Acoustics',
                                            model_name='LA12X', channel_count=4,
                                            power_profile=la8)
        load()
        amp_model.refresh_from_db()
        self.assertEqual(la8, amp_model.power_profile)


class PermissionTests(TestCase):

    def setUp(self):
        self.editor = User.objects.create_user('lr_editor', 'e@example.com', 'pw',
                                               is_staff=True)
        self.superuser = User.objects.create_superuser('lr_su', 's@example.com', 'pw')

    def _request(self, user):
        request = RequestFactory().get('/admin/')
        request.user = user
        return request

    def test_only_a_superuser_can_relink_an_amp_model(self):
        admin = AmpModelAdmin(AmpModel, showstack_admin_site)
        self.assertIn('power_profile', admin.get_readonly_fields(self._request(self.editor)))
        self.assertNotIn('power_profile',
                         admin.get_readonly_fields(self._request(self.superuser)))

    def test_only_a_superuser_can_change_a_rating(self):
        inline = AmplifierLoadRatingInline(AmplifierProfile, showstack_admin_site)
        self.assertFalse(inline.has_change_permission(self._request(self.editor)))
        self.assertFalse(inline.has_add_permission(self._request(self.editor)))
        self.assertTrue(inline.has_change_permission(self._request(self.superuser)))
