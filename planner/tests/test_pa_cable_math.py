"""PA Cable summary math.

Two layers:

  * ``StockBreakdownTests`` pin the rule itself -- how one run of length L
    becomes physical stock cables.
  * ``NutanixFixtureTests`` / ``CaComFixtureTests`` run the real admin
    changelist against the rows from the "Nutanix SKO 26" audit, so the
    numbers on the screen are what is asserted, not just the helper.

Run with::

    python manage.py test planner.tests.test_pa_cable_math \
        --settings=audiopatch.test_settings
"""
from collections import Counter
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from planner.models import (
    PACableSchedule,
    PACoupler,
    PAFanOut,
    PAFanOutExtension,
    Project,
)
from planner.utils import pa_cable_math
from planner.utils.pa_cable_math import (
    DEFAULT_STOCK_LENGTHS,
    all_stock_lengths,
    explain_run,
    round_up_to_stock,
    run_breakdown,
    stock_breakdown,
    stock_lengths_for,
    with_safety,
)
from planner.utils.pdf_exports.pa_cable_pdf import _quick_order_rows

# The 16 NL 4 rows from the audited project, as (count, length).
# 31 runs, 2,490 ft.
NUTANIX_NL4 = [
    (4, 50), (1, 25), (4, 50), (1, 25), (1, 50), (4, 60), (1, 100),
    (2, 50), (4, 150), (1, 200), (1, 50), (1, 75), (1, 50), (1, 75),
    (1, 200), (3, 100),
]

# The CA-COM rows from the same project. 14 runs, 1,850 ft.
NUTANIX_CACOM = [
    (1, 100), (1, 100), (4, 50), (2, 175), (4, 150), (1, 200), (1, 300),
]


class StockBreakdownTests(TestCase):
    """The rule, stated as cases."""

    def test_stock_is_only_100_50_and_25(self):
        self.assertEqual(DEFAULT_STOCK_LENGTHS, (100, 50, 25))
        self.assertEqual(all_stock_lengths(), (100, 50, 25))
        self.assertEqual(stock_lengths_for('NL_4'), (100, 50, 25))

    def test_exact_stock_lengths_take_one_cable(self):
        for length in (25, 50, 100):
            with self.subTest(length=length):
                self.assertEqual(stock_breakdown(length), Counter({length: 1}))

    def test_leftover_rounds_up_never_down(self):
        # 60' cannot be run on a 50'.
        self.assertEqual(stock_breakdown(60), Counter({100: 1}))
        self.assertEqual(stock_breakdown(75), Counter({100: 1}))
        self.assertEqual(stock_breakdown(26), Counter({50: 1}))
        self.assertEqual(stock_breakdown(51), Counter({100: 1}))

    def test_short_runs_take_a_25(self):
        """Nothing under 25' is carried, so a short run coils the slack."""
        for length in (1, 3, 5, 6, 7, 10, 12, 24, 25):
            with self.subTest(length=length):
                self.assertEqual(stock_breakdown(length), Counter({25: 1}))

    def test_leftover_under_25_takes_a_25(self):
        self.assertEqual(stock_breakdown(110), Counter({100: 1, 25: 1}))
        self.assertEqual(stock_breakdown(101), Counter({100: 1, 25: 1}))
        self.assertEqual(stock_breakdown(210), Counter({100: 2, 25: 1}))

    def test_long_runs_take_whole_hundreds_then_one_leftover(self):
        self.assertEqual(stock_breakdown(150), Counter({100: 1, 50: 1}))
        self.assertEqual(stock_breakdown(175), Counter({100: 2}))
        self.assertEqual(stock_breakdown(200), Counter({100: 2}))
        self.assertEqual(stock_breakdown(300), Counter({100: 3}))
        self.assertEqual(stock_breakdown(325), Counter({100: 3, 25: 1}))
        self.assertEqual(stock_breakdown(275), Counter({100: 3}))

    def test_a_per_type_stock_list_changes_the_breakdown(self):
        """STOCK_LENGTHS_BY_TYPE is the seam for a type that differs."""
        with patch.dict(pa_cable_math.STOCK_LENGTHS_BY_TYPE,
                        {'SC32': (50, 25)}, clear=False):
            # Longest spool for SC32 is 50', so 110' is two 50's and a 25'.
            self.assertEqual(stock_breakdown(110, 'SC32'),
                             Counter({50: 2, 25: 1}))
            # Everything else is untouched.
            self.assertEqual(stock_breakdown(110, 'NL_4'),
                             Counter({100: 1, 25: 1}))
            self.assertEqual(all_stock_lengths(), (100, 50, 25))

    def test_count_multiplies_physical_cables(self):
        # The whole point: four 50' runs are four 50' cables. They go to four
        # different places and cannot be spliced into two 100' ones.
        self.assertEqual(run_breakdown(50, 4), Counter({50: 4}))
        self.assertEqual(run_breakdown(150, 4), Counter({100: 4, 50: 4}))
        self.assertEqual(run_breakdown(200, 1), Counter({100: 2}))

    def test_empty_and_degenerate_rows_need_no_cable(self):
        for length in (0, None, -25):
            with self.subTest(length=length):
                self.assertEqual(stock_breakdown(length), Counter())
        self.assertEqual(run_breakdown(100, 0), Counter())
        self.assertEqual(run_breakdown(100, None), Counter())
        self.assertIsNone(round_up_to_stock(0))
        self.assertIsNone(round_up_to_stock(None))

    def test_safety_margin_rounds_up_and_keeps_zero_at_zero(self):
        self.assertEqual(with_safety(0), 0)
        self.assertEqual(with_safety(18), 22)   # 21.6
        self.assertEqual(with_safety(17), 21)   # 20.4
        self.assertEqual(with_safety(15), 18)   # exact
        self.assertEqual(with_safety(2), 3)     # 2.4

    def test_safety_is_not_reversible(self):
        """Why the margin is applied once, at the end.

        The PDF used to un-apply it to merge extensions into a subtotal:
        ``raw = round(safe / 1.2)``. ceil() does not survive that round trip,
        so merging an extension could invent a cable.
        """
        raw = 17
        safe = with_safety(raw)              # ceil(20.4) == 21
        recovered = round(safe / 1.2)        # round(17.5) == 18
        self.assertEqual(safe, 21)
        self.assertNotEqual(recovered, raw)
        # Adding one extension to 17 should order 18 cables' worth, not 19.
        self.assertEqual(with_safety(raw + 1), 22)
        self.assertEqual(with_safety(recovered + 1), 23)

    def test_explain_run_shows_the_working(self):
        self.assertEqual(explain_run(150, 4), "4 × 150' → 4 × 100' + 4 × 50'")
        self.assertEqual(explain_run(60, 4), "4 × 60' → 4 × 100'")


class _SummaryFixtureMixin:
    """Builds a project of PA cable rows and reads the real admin summary."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username='pa_audit', email='pa@example.com', password='x')
        cls.project = Project.objects.create(
            name='PA Math Fixture', owner=cls.user)

    def add_rows(self, cable, rows):
        for count, length in rows:
            PACableSchedule.objects.create(
                project=self.project, cable=cable,
                count=count, length=length, destination='SL Amp Rack')

    def summary(self):
        client = Client()
        client.force_login(self.user)
        session = client.session
        session['current_project_id'] = self.project.pk
        session.save()
        response = client.get('/admin/planner/pacableschedule/')
        self.assertEqual(response.status_code, 200)
        return response.context_data['cable_summary']


class NutanixFixtureTests(_SummaryFixtureMixin, TestCase):
    """The NL 4 rows that prompted the audit."""

    def setUp(self):
        self.add_rows('NL_4', NUTANIX_NL4)

    def test_fixture_matches_the_audited_project(self):
        self.assertEqual(sum(c for c, _ in NUTANIX_NL4), 31)
        self.assertEqual(sum(c * l for c, l in NUTANIX_NL4), 2490)

    def test_cables_needed(self):
        data = self.summary()['NL 4']
        self.assertEqual(data['total_runs'], 31)
        self.assertEqual(data['total_length'], 2490)
        self.assertEqual(
            (data['hundreds'], data['fifties'], data['twenty_fives']),
            (18, 17, 2))
        # The 10' and 5' buckets are gone with the spools.
        self.assertNotIn('tens', data)
        self.assertNotIn('fives', data)

    def test_order_qty_carries_the_20_percent_margin(self):
        data = self.summary()['NL 4']
        self.assertEqual(
            (data['hundreds_with_safety'], data['fifties_with_safety'],
             data['twenty_fives_with_safety']),
            (22, 21, 3))

    def test_every_row_is_accounted_for(self):
        """The total of the per-row breakdowns is the summary, exactly."""
        expected = Counter()
        for count, length in NUTANIX_NL4:
            expected += run_breakdown(length, count)
        data = self.summary()['NL 4']
        self.assertEqual(data['hundreds'], expected[100])
        self.assertEqual(data['fifties'], expected[50])
        self.assertEqual(data['twenty_fives'], expected[25])

    def test_quick_order_list_agrees_with_the_screen(self):
        """The PDF and the screen are one calculation, not two."""
        data = self.summary()['NL 4']
        rows = {
            (name, label): int(qty)
            for name, label, qty in _quick_order_rows(
                PACableSchedule.objects.filter(project=self.project))
        }
        self.assertEqual(rows[('NL 4', "100'")], data['hundreds_with_safety'])
        self.assertEqual(rows[('NL 4', "50'")], data['fifties_with_safety'])
        self.assertEqual(rows[('NL 4', "25'")], data['twenty_fives_with_safety'])


class CaComFixtureTests(_SummaryFixtureMixin, TestCase):
    """CA-COM on the same project -- the type whose numbers were trusted."""

    def setUp(self):
        self.add_rows('CA-COM', NUTANIX_CACOM)

    def test_fixture_shape(self):
        self.assertEqual(sum(c for c, _ in NUTANIX_CACOM), 14)
        self.assertEqual(sum(c * l for c, l in NUTANIX_CACOM), 1850)

    def test_cables_needed(self):
        data = self.summary()['CA-COM']
        self.assertEqual(
            (data['hundreds'], data['fifties'], data['twenty_fives']),
            (15, 8, 0))

    def test_175_foot_runs_take_two_hundreds(self):
        self.assertEqual(stock_breakdown(175), Counter({100: 2}))


class ExtensionRoundingTests(_SummaryFixtureMixin, TestCase):
    """Fan-out extensions go through the same rule as runs.

    They used to have a rule of their own that rounded DOWN: a 150'
    extension counted as a single 100' cable, and a 6' one as a single 5'.

    Sub-25' lengths are no longer offered, but rows stored before the choices
    were trimmed still carry them, so the math still has to answer for them.
    """

    def _add_extension(self, length, quantity=1, cable='NL4'):
        run = PACableSchedule.objects.create(
            project=self.project, cable='NL_4', count=1, length=0,
            destination='SL Amp Rack')
        fan_out = PAFanOut.objects.create(
            cable_schedule=run, fan_out_type='NL4_Y', quantity=1)
        PAFanOutExtension.objects.create(
            cable_schedule=run, fan_out=fan_out,
            extension_cable=cable, extension_length=length,
            quantity=quantity)
        return run

    def test_150_foot_extension_is_a_100_and_a_50(self):
        self._add_extension(150)
        data = self.summary()['NL 4']
        self.assertEqual(data['hundreds'], 1)
        self.assertEqual(data['fifties'], 1)

    def test_six_foot_extension_rounds_up_to_a_25(self):
        """A legacy 6' row: nothing under 25' is carried, so it takes a 25'."""
        self._add_extension(6)
        data = self.summary()['NL 4']
        self.assertEqual(data['twenty_fives'], 1)
        self.assertEqual(data['hundreds'], 0)
        self.assertEqual(data['fifties'], 0)

    def test_legacy_sub_25_extension_lengths_all_take_a_25(self):
        """5', 6' and 10' were dropped from the dropdown, not from the data."""
        for length in (5, 6, 10):
            with self.subTest(length=length):
                self.assertEqual(stock_breakdown(length), Counter({25: 1}))

    def test_extension_quantity_multiplies(self):
        self._add_extension(150, quantity=3)
        data = self.summary()['NL 4']
        self.assertEqual(data['hundreds'], 3)
        self.assertEqual(data['fifties'], 3)

    def test_exact_stock_extensions_are_unchanged(self):
        self._add_extension(100, quantity=2)
        data = self.summary()['NL 4']
        self.assertEqual(data['hundreds'], 2)
        self.assertEqual(data['fifties'], 0)


class UnknownCableTypeTests(_SummaryFixtureMixin, TestCase):
    """A row whose cable value is not a known choice must not vanish.

    ``PACableSchedule.cable`` defaults to ``'100_NL4'``, which is not in
    ``CABLE_TYPE_CHOICES``. The summary used to iterate the choices and
    filter, so any such row contributed to nothing at all and the screen
    quietly disagreed with a hand count of the drawing.
    """

    def test_row_with_an_unrecognised_cable_value_still_appears(self):
        PACableSchedule.objects.create(
            project=self.project, cable='100_NL4', count=2, length=150,
            destination='SL Amp Rack')
        summary = self.summary()
        self.assertIn('100_NL4', summary)
        data = summary['100_NL4']
        self.assertEqual(data['total_runs'], 2)
        self.assertEqual(data['total_length'], 300)
        self.assertEqual(data['hundreds'], 2)
        self.assertEqual(data['fifties'], 2)

    def test_known_types_keep_their_display_label(self):
        self.add_rows('NL_4', [(1, 100)])
        self.assertIn('NL 4', self.summary())


class GrandTotalTests(_SummaryFixtureMixin, TestCase):
    """Totals across types, and the couplers column."""

    def test_grand_total_is_every_type(self):
        self.add_rows('NL_4', NUTANIX_NL4)
        self.add_rows('CA-COM', NUTANIX_CACOM)
        client = Client()
        client.force_login(self.user)
        session = client.session
        session['current_project_id'] = self.project.pk
        session.save()
        response = client.get('/admin/planner/pacableschedule/')
        self.assertEqual(response.context_data['grand_total'], 2490 + 1850)

    def test_couplers_are_counted_but_do_not_touch_cable_counts(self):
        self.add_rows('NL_4', [(1, 100)])
        run = PACableSchedule.objects.filter(project=self.project).first()
        PACoupler.objects.create(
            cable_schedule=run, coupler_type='NL4_COUPLER', quantity=3)
        data = self.summary()['NL 4']
        self.assertEqual(data['couplers'], 3)
        self.assertEqual(data['hundreds'], 1)
