"""Power plans on the per-load manufacturer figures (phase 3B).

Run with::

    python manage.py test planner.tests.test_power_estimate \\
        --settings=audiopatch.test_settings
"""

import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from planner.models import (
    AmplifierAssignment, AmplifierProfile, PowerDistributionPlan,
)
from planner.tests.test_amp_output_cabinets import Fixture, seed, section
from planner.utils.power_estimate import (
    ESTIMATE_LABEL, FROM_WATTS, HEAVY, IDLE, NORMAL, PUBLISHED, amp_channel_loads,
    assumed_load, estimate,
)

D = Decimal


def profile(model):
    return AmplifierProfile.objects.prefetch_related(
        'load_ratings', 'voltage_factors').get(manufacturer='L-Acoustics', model=model)


class EstimateTests(TestCase):

    def setUp(self):
        seed()
        self.la12x = profile('LA12X')

    def test_equal_loads_give_the_published_figure(self):
        draw = estimate(self.la12x, HEAVY, [D(8)] * 4, 230, D('0.95'))
        self.assertEqual((D('10.50'), 2300, PUBLISHED), (draw.current, draw.watts, draw.basis))
        draw = estimate(self.la12x, NORMAL, [D(8) / 3] * 4, 230, D('0.95'))
        self.assertEqual((D('11.50'), 2400), (draw.current, draw.watts))  # 2.67 -> 2.7 row

    def test_mixed_loads(self):
        # idle 1 A / 160 W; 1/8 at 2.7 ohm 11.5 A / 2400 W, at 4 ohm 8.1 A / 1850 W.
        # 1 + ((11.5 - 1) + (8.1 - 1)) / 4 = 5.4 A
        # 160 + ((2400 - 160) + (1850 - 160)) / 4 = 1142.5 -> 1143 W
        draw = estimate(self.la12x, NORMAL, [D(8) / 3, D(4), None, None], 230, D('0.95'))
        self.assertEqual((D('5.40'), 1143), (draw.current, draw.watts))

    def test_empty_channels_and_idle_programme_draw_idle(self):
        self.assertEqual(D('1.00'), estimate(self.la12x, HEAVY, [None] * 4, 230, 1).current)
        self.assertEqual((D('1.00'), 160),
                         (lambda d: (d.current, d.watts))(estimate(self.la12x, IDLE, [D(8)] * 4, 230, 1)))

    def test_voltage(self):
        draw = estimate(self.la12x, HEAVY, [D(8)] * 4, 208, D('0.95'))
        self.assertEqual(D('11.61'), draw.current)  # 10.5 x 1.1058
        self.assertEqual(2300, draw.watts)          # power unchanged
        self.assertIn('×1.1058 for 208 V (derived', draw.notes[0])
        # Published multipliers win: LA12X x1.9, LA8 x2.0 at 120 V.
        self.assertEqual(D('19.95'), estimate(self.la12x, HEAVY, [D(8)] * 4, 120, 1).current)
        la8 = profile('LA8')
        self.assertEqual(D('30.00'), estimate(la8, HEAVY, [D(8)] * 4, 120, 1).current)

    def test_footnoted_channels_driven(self):
        la716i = profile('LA7.16i')
        draw = estimate(la716i, HEAVY, [D(8)] * 16, 230, 1)
        self.assertEqual(D('18.60'), draw.current)
        self.assertIn('LA7.16i 1/3 power at 8 Ω is published with 11 channels driven', draw.notes)

    def test_load_independent_table(self):
        la4x = profile('LA4X')
        for load in (D(16), D(4)):
            self.assertEqual(D('3.00'), estimate(la4x, NORMAL, [load] * 4, 230, 1).current)
        self.assertIsNone(assumed_load(la4x, None))

    def test_watts_fallback_uses_the_power_factor(self):
        bare = AmplifierProfile.objects.create(
            manufacturer='Acme', model='PA-1', idle_power_watts=100, rated_power_watts=1000,
            peak_power_watts=2000, max_power_watts=4000)
        draw = estimate(bare, NORMAL, [D(8)] * 4, 208, D('0.90'))
        self.assertEqual((D('5.34'), 1000, FROM_WATTS), (draw.current, draw.watts, draw.basis))
        self.assertIn('power factor 0.9 (assumed)', draw.notes[0])

    def test_assumed_load_is_the_lowest_published(self):
        self.assertEqual(D('2.7'), assumed_load(self.la12x, None))
        self.assertEqual(D('4'), assumed_load(profile('LA7.16i'), None))
        self.assertEqual(D('8'), assumed_load(self.la12x, D(8)))

    def test_no_profile(self):
        self.assertIsNone(estimate(None, NORMAL, [], 208, 1))


class AmpChannelLoadTests(Fixture):

    def test_loads_from_the_rack_cabinets(self):
        self.assign(self.channel(self.la12x, 1), section('Kara II', 'LF'), 3)
        self.assign(self.channel(self.la12x, 3), section('KS28'), 1)
        loads = amp_channel_loads(self.la12x)
        self.assertEqual([D(8) / 3, None, D(4), None], loads)
        draw = estimate(profile('LA12X'), NORMAL, loads, 230, 1)
        # 1 + ((11.5 - 1) + (8.1 - 1)) / 4
        self.assertEqual(D('5.40'), draw.current)


class PlanFixture(Fixture):

    def setUp(self):
        super().setUp()
        self.plan = PowerDistributionPlan.objects.create(
            project=self.project, venue_name='Hall', transient_headroom=D('1.5'))
        self.row = AmplifierAssignment.objects.create(
            distribution_plan=self.plan, amplifier=profile('LA12X'), quantity=3, zone='FOH',
            programme=HEAVY)


class AssignmentTests(PlanFixture):

    def test_cached_figures(self):
        # 1/3 at 2.7 ohm: 26 A x 1.1058 = 28.75 at 208 V, x 1.5 headroom.
        self.assertEqual(D('43.13'), self.row.calculated_current_per_unit)
        self.assertEqual(D('129.39'), self.row.calculated_total_current)
        self.assertEqual(5500, self.row.calculated_watts_per_unit)

    def test_load_and_programme_change_the_figure(self):
        self.row.load_ohms = D(8)
        self.row.programme = NORMAL
        self.row.save()
        # 4.8 A x 1.1058 = 5.31; x 1.5 = 7.965, half up
        self.assertEqual(D('7.97'), self.row.calculated_current_per_unit)

    def test_no_duty_factor_on_top(self):
        details = self.row.get_power_details()
        self.assertEqual(28.75, details['per_unit']['current_amps'])
        self.assertEqual(round(28.75 * 1.5, 2), details['per_unit']['design_current_amps'])

    def test_duplicate_keeps_the_settings(self):
        self.row.load_ohms = D(4)
        self.row.save()
        PowerDistributionPlan.objects.filter(pk=self.plan.pk).update(power_factor=D('0.9'))
        copy = self.project.duplicate(new_name='Copy')
        row = AmplifierAssignment.objects.get(distribution_plan__project=copy)
        self.assertEqual((HEAVY, D(4), D('0.90')),
                         (row.programme, row.load_ohms, row.distribution_plan.power_factor))
        self.assertEqual(self.row.calculated_total_current, row.calculated_total_current)


class CalculatorPageTests(PlanFixture):

    def setUp(self):
        super().setUp()
        self.use(self.owner)

    def page(self):
        return self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[self.plan.pk]))

    def post(self, name, obj_id, payload):
        return self.client.post(reverse(f'planner:{name}', args=[obj_id]),
                                data=json.dumps(payload), content_type='application/json')

    def test_figures_are_labelled_as_estimates(self):
        page = self.page()
        self.assertContains(page, ESTIMATE_LABEL)
        self.assertContains(page, 'Total Current (estimate)')
        self.assertContains(page, 'Current/Unit (estimate)')
        self.assertContains(page, 'Power Factor (assumed)')
        self.assertContains(page, 'Heavy programme (1/3 power)')
        self.assertContains(page, '(lowest published)')
        self.assertContains(page, '×1.1058 for 208 V')
        self.assertContains(page, '16.5kW')  # 5500 W x 3
        self.assertNotContains(page, 'Duty')

    def test_power_factor_setting(self):
        r = self.post('update_plan_settings', self.plan.pk, {'power_factor': '0.9'})
        self.assertEqual(200, r.status_code, r.content)
        self.plan.refresh_from_db()
        self.assertEqual(D('0.90'), self.plan.power_factor)
        r = self.post('update_plan_settings', self.plan.pk, {'power_factor': '1.4'})
        self.assertEqual(400, r.status_code)

    def test_update_assignment(self):
        r = self.post('update_amplifier_assignment', self.row.pk,
                      {'programme': 'normal', 'load_ohms': '8'})
        self.assertEqual(200, r.status_code, r.content)
        self.row.refresh_from_db()
        self.assertEqual((NORMAL, D(8)), (self.row.programme, self.row.load_ohms))
        r = self.post('update_amplifier_assignment', self.row.pk, {'programme': 'heavy_music'})
        self.assertEqual(400, r.status_code)
        r = self.post('update_amplifier_assignment', self.row.pk, {'load_ohms': ''})
        self.row.refresh_from_db()
        self.assertIsNone(self.row.load_ohms)

    def test_get_assignment(self):
        r = self.client.get(reverse('planner:get_amplifier_assignment', args=[self.row.pk]))
        self.assertEqual(('heavy', ''), (r.json()['assignment']['programme'],
                                         r.json()['assignment']['load_ohms']))

    def test_system_report_section(self):
        from planner.utils.pdf_exports.report_kit import styles
        from planner.utils.pdf_exports.system_report import _section_power
        story = _section_power(self.project, styles(), PowerDistributionPlan)
        text = ' '.join(getattr(f, 'text', '') for f in story)
        self.assertIn(ESTIMATE_LABEL, text)
        self.assertIn('208 V', text)


class MigrationTests(PlanFixture):
    """0213's data steps. The test settings build tables from the models, not
    the migration chain (a legacy migration has Postgres-only SQL), so the
    end-to-end run of 0213 -- back to 0212, old duty cycles in, forward -- is
    done on a copy of a database (see the PR); this pins the mapping and the
    recompute it calls."""

    def migration(self):
        import importlib
        return importlib.import_module('planner.migrations.0213_power_plan_per_load')

    def test_mapping(self):
        self.assertEqual({'speech': 'normal', 'light_music': 'normal', 'heavy_music': 'normal',
                          'edm_concert': 'heavy', 'test_tone': 'heavy'},
                         self.migration().FORWARD)

    def test_default_headroom_is_25_percent(self):
        plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='New')
        self.assertEqual(D('1.25'), plan.transient_headroom)
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, '<option value="1.25" selected>25% (default)</option>')
        # A stored value off the list still shows, selected.
        PowerDistributionPlan.objects.filter(pk=plan.pk).update(transient_headroom=D('1.40'))
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, '<option value="1.40" selected>1.40×</option>')

    def test_old_default_headroom_moves_to_25_percent(self):
        from django.apps import apps
        kept = PowerDistributionPlan.objects.create(
            project=self.project, venue_name='Chosen', transient_headroom=D('1.30'))
        self.migration().headroom_to_new_default(apps, None)
        self.migration().recompute(apps, None)
        self.plan.refresh_from_db()
        kept.refresh_from_db()
        self.assertEqual((D('1.25'), D('1.30')), (self.plan.transient_headroom,
                                                  kept.transient_headroom))
        # 28.75 A x 1.25 = 35.9375, half up
        self.row.refresh_from_db()
        self.assertEqual(D('35.94'), self.row.calculated_current_per_unit)
        self.migration().headroom_to_new_default(apps, None)  # twice: same result
        self.plan.refresh_from_db()
        self.assertEqual(D('1.25'), self.plan.transient_headroom)

    def test_recompute_overwrites_stale_figures(self):
        from django.apps import apps
        AmplifierAssignment.objects.filter(pk=self.row.pk).update(
            calculated_current_per_unit=99, calculated_total_current=297,
            calculated_watts_per_unit=None)
        self.migration().recompute(apps, None)
        self.row.refresh_from_db()
        self.assertEqual((D('43.13'), D('129.39'), 5500),
                         (self.row.calculated_current_per_unit, self.row.calculated_total_current,
                          self.row.calculated_watts_per_unit))
        self.migration().recompute(apps, None)  # twice: same result
        self.row.refresh_from_db()
        self.assertEqual(D('129.39'), self.row.calculated_total_current)
