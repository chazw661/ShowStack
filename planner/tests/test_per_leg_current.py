"""Per-leg current at the phase-to-neutral voltage (migration 0215).

A leg's current is the watts on it / (phase-to-neutral volts x the plan's
assumed power factor), times the transient headroom.

Run with::

    python manage.py test planner.tests.test_per_leg_current \\
        --settings=audiopatch.test_settings
"""

import importlib
from decimal import Decimal

from django.apps import apps as live_apps
from django.db.migrations.state import ProjectState
from django.test import TestCase
from django.urls import reverse

from planner.models import AmplifierAssignment, AmplifierProfile, PowerDistributionPlan
from planner.tests.test_amp_output_cabinets import Fixture, seed
from planner.utils.power_estimate import (
    NORMAL, estimate, leg_current, phase_to_neutral_voltage, plan_voltage,
)
from planner.views import calculate_phase_distribution

D = Decimal


def la12x():
    return AmplifierProfile.objects.prefetch_related(
        'load_ratings', 'voltage_factors').get(manufacturer='L-Acoustics', model='LA12X')


class VoltageTableTests(TestCase):

    def test_phase_to_neutral(self):
        self.assertEqual({
            '3phase_4wire_208': 120, '3phase_5wire_208': 120, '3phase_4wire_240': 240,
            '3phase_5wire_400': 230, 'single_phase_120': 120, 'single_phase_240': 240,
        }, {key: phase_to_neutral_voltage(key) for key, _ in PowerDistributionPlan.SERVICE_TYPES})

    def test_service_voltage(self):
        # 400 used to fall through to 208.
        self.assertEqual((208, 400, 240), (plan_voltage('3phase_5wire_208'),
                                           plan_voltage('3phase_5wire_400'),
                                           plan_voltage('single_phase_240')))

    def test_leg_current(self):
        self.assertEqual(D('67.54'), leg_current(7700, 120, D('0.95')))


class PlanFixture(Fixture):

    def plan(self, service='3phase_4wire_208', **kwargs):
        return PowerDistributionPlan.objects.create(
            project=self.project, venue_name='Hall', service_type=service, **kwargs)

    def row(self, plan, phase='AUTO', quantity=1, load=D(8)):
        return AmplifierAssignment.objects.create(
            distribution_plan=plan, amplifier=la12x(), quantity=quantity, zone='FOH',
            programme=NORMAL, load_ohms=load, phase_assignment=phase)


class PerLegTests(PlanFixture):

    def test_three_la12x_one_per_leg_on_208y120(self):
        plan = self.plan()
        for leg in ('L1', 'L2', 'L3'):
            self.row(plan, leg)
        phases = calculate_phase_distribution(plan)['phases']
        new = {name: phases[name]['total_current'] for name in ('L1', 'L2', 'L3')}
        self.assertEqual(1, len(set(new.values())))  # equal loads, equal legs
        # 1/8 power at 8 ohm: 1050 W / (120 x 0.95) = 9.21 A, x 1.25 = 11.51
        self.assertAlmostEqual(11.51, new['L1'], places=2)

        # The old per-leg figure: the published current at the 208 V service
        # voltage (4.8 A at 230 V x 1.1058 = 5.31 A), x 1.25.
        old = float(estimate(la12x(), NORMAL, [D(8)] * 4, 208, plan.power_factor).current
                    * plan.transient_headroom)
        self.assertAlmostEqual(6.64, old, places=2)
        # 208 / 120 = 1.733; the rest is the published current's own power
        # factor against the assumed 0.95.
        self.assertAlmostEqual(1.73, new['L1'] / old, delta=0.02)

    def test_leg_sums_the_watts_on_it(self):
        plan = self.plan()
        self.row(plan, 'L1', quantity=2)
        self.row(plan, 'L2')
        phases = calculate_phase_distribution(plan)['phases']
        # 2 x 1050 W on L1: 2 x 9.21 A x 1.25 = 23.02 (per unit rounded first)
        self.assertAlmostEqual(23.02, phases['L1']['total_current'], places=2)
        self.assertAlmostEqual(11.51, phases['L2']['total_current'], places=2)
        self.assertEqual(0, phases['L3']['total_current'])

    def test_single_phase_uses_the_service_voltage(self):
        row = self.row(self.plan('single_phase_240'), 'L1')
        # 1050 / (240 x 0.95) = 4.61 A, x 1.25 = 5.7625, half up
        self.assertEqual(D('5.76'), row.calculated_current_per_unit)

    def test_230_400(self):
        row = self.row(self.plan('3phase_5wire_400'), 'L1')
        # 1050 / (230 x 0.95) = 4.81 A, x 1.25 = 6.0125, half up
        self.assertEqual(D('6.01'), row.calculated_current_per_unit)

    def test_power_factor_is_in_every_row(self):
        row = self.row(self.plan(power_factor=D('1.00')), 'L1')
        # 1050 / 120 = 8.75 A, x 1.25 = 10.9375, half up
        self.assertEqual(D('10.94'), row.calculated_current_per_unit)

    def test_watts_are_unchanged(self):
        self.assertEqual(1050, self.row(self.plan(), 'L1').calculated_watts_per_unit)


class PagesTests(PlanFixture):

    def test_plan_page_shows_the_phase_to_neutral_voltage(self):
        plan = self.plan('3phase_5wire_400')
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, 'Phase-to-Neutral Voltage')
        self.assertContains(page, 'value="230V"')
        self.assertContains(page, '3-Phase 5-Wire 230/400V')

    def test_admin_shows_the_phase_to_neutral_voltage(self):
        plan = self.plan()
        self.use(self.owner)
        page = self.client.get(reverse('admin:planner_powerdistributionplan_change',
                                       args=[plan.pk]))
        self.assertEqual(200, page.status_code)
        self.assertContains(page, 'Phase-to-neutral voltage')
        self.assertContains(page, '120 V')

    def test_pdf_states_the_voltage_and_the_legs(self):
        from planner.utils.pdf_exports.report_kit import styles
        from planner.utils.pdf_exports.system_report import _section_power
        plan = self.plan()
        self.row(plan, 'L2')
        story = _section_power(self.project, styles(), PowerDistributionPlan)
        text = ' '.join(getattr(f, 'text', '') for f in story)
        self.assertIn('120 V phase-to-neutral', text)
        self.assertIn('L1 0.0A · L2 11.5A · L3 0.0A', text)


class MigrationTests(PlanFixture):
    """0215's recompute, run on state-built models as a migration gets them
    (no custom save()), so it is the migration's own arithmetic that writes
    the figures. 0215 is the head, so the current state is its state."""

    def test_recompute(self):
        row = self.row(self.plan(), 'L1')
        AmplifierAssignment.objects.filter(pk=row.pk).update(
            calculated_current_per_unit=D('6.64'), calculated_total_current=D('6.64'))
        apps = ProjectState.from_apps(live_apps).apps
        migration = importlib.import_module('planner.migrations.0215_per_leg_phase_to_neutral')
        for _ in range(2):  # twice: same result
            migration.recompute(apps, None)
            row.refresh_from_db()
            self.assertEqual((D('11.51'), D('11.51'), 1050),
                             (row.calculated_current_per_unit, row.calculated_total_current,
                              row.calculated_watts_per_unit))
