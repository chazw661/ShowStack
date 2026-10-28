"""Power plans generated from the amp module (Phase C).

Run with::

    python manage.py test planner.tests.test_power_plan_generate \\
        --settings=audiopatch.test_settings
"""

import json
import re
from decimal import Decimal

from django.apps import apps as live_apps
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from planner.models import (
    Amp, AmplifierAssignment, AmplifierProfile, AmpLocation, AmpModel, PowerDistributionPlan,
)
from planner.tests.test_amp_output_cabinets import Fixture, section, staff
from planner.utils import power_plan_generator as generator
from planner.utils.power_estimate import (
    HEAVY, IDLE, NORMAL, amp_channel_loads, plan_estimate, uniform_channel_loads,
)
from planner.utils.power_plan_generator import Item, balance

D = Decimal


class BalanceTests(TestCase):
    """The algorithm on its own: hand-set legs kept, the rest largest first
    onto the least-loaded leg, ties to the lower leg."""

    def test_worked_example(self):
        items = [Item('F', D(10), 'L1', 0), Item('A', D(12), '', 1), Item('B', D(10), '', 2),
                 Item('C', D(8), '', 3), Item('D', D(8), '', 4), Item('E', D(6), '', 5)]
        legs = ['L1', 'L2', 'L3']
        self.assertEqual({'F': 'L1', 'A': 'L2', 'B': 'L3', 'C': 'L1', 'D': 'L3', 'E': 'L2'},
                         balance(items, legs))
        self.assertEqual(balance(items, legs), balance(list(reversed(items)), legs))

    def test_hand_set_legs_never_move(self):
        items = [Item(n, D(10), 'L1', n) for n in range(4)]
        self.assertEqual({0: 'L1', 1: 'L1', 2: 'L1', 3: 'L1'}, balance(items, ['L1', 'L2', 'L3']))

    def test_preloaded_watts_count(self):
        self.assertEqual({'A': 'L2'}, balance([Item('A', D(5))], ['L1', 'L2'], {'L1': 100}))

    def test_a_leg_the_service_lacks_is_balanced(self):
        self.assertEqual({'A': 'L1'}, balance([Item('A', D(5), 'L3')], ['L1', 'L2']))


class GeneratorFixture(Fixture):

    def setUp(self):
        super().setUp()
        self.amp2 = self.amp(self.project, 'LA8', name='Amp 2')
        self.assign(self.channel(self.la12x, 1), section('Kara II', 'LF'), 3)
        self.assign(self.channel(self.la12x, 3), section('KS28'), 1)
        for n in range(1, 5):
            self.assign(self.channel(self.amp2, n), section('KS28'), 1)

    def generate(self):
        plan, created = generator.generate(self.project, user=self.owner)
        return PowerDistributionPlan.objects.get(pk=plan.pk)

    def rows(self, plan):
        return {r.position: r for r in plan.amplifier_assignments.filter(generated=True)}

    def watts(self, amp, programme=NORMAL):
        amp = Amp.objects.get(pk=amp.pk)  # the fixture's AmpModels predate their profile link
        profile = amp.amp_model.power_profile
        return plan_estimate(profile, programme, amp_channel_loads(amp),
                             '3phase_4wire_208', D('0.95')).watts


class GenerateTests(GeneratorFixture):

    def test_one_row_per_amp_on_its_real_loads(self):
        plan = self.generate()
        rows = self.rows(plan)
        self.assertEqual({'Amp 1', 'Amp 2'}, set(rows))
        row = rows['Amp 1']
        self.assertEqual((self.la12x.pk, 'HL', 1, NORMAL),
                         (row.source_amp_id, row.zone, row.quantity, plan.programme))
        self.assertEqual(self.watts(self.la12x), row.calculated_watts_per_unit)
        # Mixed loads differ from the uniform worst case a hand row would get.
        worst = plan_estimate(row.amplifier, NORMAL, uniform_channel_loads(row.amplifier, None),
                              plan.service_type, plan.power_factor).watts
        self.assertLess(row.calculated_watts_per_unit, worst)
        self.assertEqual(['2 of 4 outputs have no cabinet (counted at idle)'],
                         generator.row_loads(row)[1])

    def test_defaults(self):
        plan = self.generate()
        self.assertEqual(('3phase_4wire_208', 2000, 'Show A'),
                         (plan.service_type, plan.other_electronics_watts, plan.venue_name))
        self.assertTrue(plan.is_generated)

    def test_an_amp_with_no_cabinets_is_the_worst_case(self):
        bare = self.amp(self.project, 'LA12X', name='Bare')
        row = self.rows(self.generate())['Bare']
        worst = plan_estimate(row.amplifier, NORMAL, uniform_channel_loads(row.amplifier, None),
                              '3phase_4wire_208', D('0.95'))
        self.assertEqual(worst.watts, row.calculated_watts_per_unit)
        self.assertEqual(['no cabinets assigned, worst case: 2.7 Ω on every channel'],
                         generator.row_loads(row)[1])
        self.assertEqual(bare.pk, row.source_amp_id)

    def test_a_load_independent_table_says_worst_case_without_ohms(self):
        self.amp(self.project, 'LA4X', name='Fill')
        row = self.rows(self.generate())['Fill']
        self.assertEqual(['no cabinets assigned, worst case'], generator.row_loads(row)[1])

    def test_amps_without_figures_are_left_out(self):
        Amp.objects.create(project=self.project, location=self.la12x.location, name='Mystery')
        plan = self.generate()
        self.assertNotIn('Mystery', self.rows(plan))
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, 'excluded from totals')
        self.assertContains(page, 'No model ×1')

    def test_one_generated_plan_per_project(self):
        first = self.generate()
        self.assertEqual(first.pk, self.generate().pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PowerDistributionPlan.objects.create(project=self.project, venue_name='Two',
                                                 generated_at=first.generated_at)
        # Plans built by hand are not limited.
        PowerDistributionPlan.objects.create(project=self.project, venue_name='Hand 1')
        PowerDistributionPlan.objects.create(project=self.project, venue_name='Hand 2')

    def test_other_projects_amps_stay_out(self):
        self.amp(self.other, 'LA12X', name='Theirs')
        self.assertNotIn('Theirs', self.rows(self.generate()))


class LegTests(GeneratorFixture):

    def test_auto_legs_balance(self):
        self.amp(self.project, 'LA12X', name='Amp 3')
        rows = self.rows(self.generate())
        self.assertEqual(3, len({r.phase_assignment for r in rows.values()}))
        self.assertTrue(all(generator.leg_status(r, ['L1', 'L2', 'L3']) == generator.AUTO
                            for r in rows.values()))

    def test_hand_set_legs_are_kept(self):
        Amp.objects.filter(project=self.project).update(leg='L2')
        rows = self.rows(self.generate())
        self.assertEqual({'L2'}, {r.phase_assignment for r in rows.values()})
        self.assertEqual(generator.SET, generator.leg_status(rows['Amp 1'], ['L1', 'L2', 'L3']))

    def test_la_rak_ii_shape_needs_no_generator_change(self):
        """What a future "Add LA-RAK II" makes: three LA12X set L1/L2/L3."""
        Amp.objects.filter(project=self.project).delete()
        location = AmpLocation.objects.create(project=self.project, name='LA-RAK II 1')
        for n, leg in enumerate(('L1', 'L2', 'L3'), 1):
            Amp.objects.create(project=self.project, location=location, name=f'RAK {n}',
                               amp_model=self.models['LA12X'], leg=leg)
        rows = self.rows(self.generate())
        self.assertEqual({'RAK 1': 'L1', 'RAK 2': 'L2', 'RAK 3': 'L3'},
                         {k: r.phase_assignment for k, r in rows.items()})

    def test_split_phase_uses_l1_l2_and_flags_l3(self):
        plan = self.generate()
        self.amp(self.project, 'LA12X', name='Amp 3')
        Amp.objects.filter(name='Amp 1').update(leg='L3')
        plan.service_type = 'split_phase_120_240'
        plan.save()
        generator.regenerate(plan)
        rows = self.rows(plan)
        self.assertEqual({'L1', 'L2'}, {r.phase_assignment for r in rows.values()})
        self.assertEqual(generator.NOT_ON_SERVICE,
                         generator.leg_status(rows['Amp 1'], plan.legs))
        self.assertEqual(['L1', 'L2'], list(generator_phases(plan)))
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, 'set to L3 on amp; not on this service, balanced')
        self.assertNotContains(page, 'id="l3-current"')

    def test_single_phase_is_one_leg(self):
        plan = self.generate()
        plan.service_type = 'single_phase_120'
        plan.save()
        generator.recompute(plan)
        self.assertEqual({'L1'}, {r.phase_assignment for r in self.rows(plan).values()})
        self.assertEqual(['L1'], list(generator_phases(plan)))

    def test_hand_built_plans_keep_three_legs(self):
        plan = PowerDistributionPlan.objects.create(
            project=self.project, venue_name='Hand', service_type='single_phase_120')
        self.assertEqual(['L1', 'L2', 'L3'], list(generator_phases(plan)))

    def test_service_change_on_the_page_rebalances(self):
        plan = self.generate()
        self.use(self.owner)
        r = self.client.post(reverse('planner:update_plan_settings', args=[plan.pk]),
                             data=json.dumps({'service_type': 'single_phase_240'}),
                             content_type='application/json')
        self.assertEqual(200, r.status_code, r.content)
        self.assertEqual({'L1'}, {r.phase_assignment for r in self.rows(plan).values()})
        r = self.client.post(reverse('planner:update_plan_settings', args=[plan.pk]),
                             data=json.dumps({'service_type': 'nonsense'}),
                             content_type='application/json')
        self.assertEqual(400, r.status_code)


def generator_phases(plan):
    from planner.views import calculate_phase_distribution
    return calculate_phase_distribution(plan)['phases']


class SpareTests(GeneratorFixture):
    """A spare amp is counted at its profile's idle draw; nothing else is."""

    def idle(self, row):
        return plan_estimate(row.amplifier, IDLE, [], '3phase_4wire_208', D('0.95'))

    def test_a_spare_is_counted_at_idle(self):
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        plan = self.generate()
        rows = self.rows(plan)
        spare, in_use = rows['Amp 2'], rows['Amp 1']
        idle = self.idle(spare)
        self.assertEqual((IDLE, idle.watts), (spare.effective_programme,
                                              spare.calculated_watts_per_unit))
        self.assertLess(idle.watts, self.watts(self.amp2))  # four KS28 at 1/8 power
        expected = (idle.current * plan.transient_headroom).quantize(D('0.01'))
        self.assertEqual(expected, spare.calculated_current_per_unit)
        self.assertEqual([generator.SPARE_NOTE], generator.row_loads(spare)[1])
        # The amp in use is untouched.
        self.assertEqual((NORMAL, self.watts(self.la12x)),
                         (in_use.effective_programme, in_use.calculated_watts_per_unit))

    def test_a_spare_ignores_the_plan_programme(self):
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        plan = self.generate()
        plan.programme = HEAVY
        plan.save()
        generator.recompute(plan)
        spare = self.rows(plan)['Amp 2']
        self.assertEqual(self.idle(spare).watts, spare.calculated_watts_per_unit)

    def test_a_spare_with_no_cabinets_is_idle(self):
        bare = self.amp(self.project, 'LA12X', name='Bare')
        Amp.objects.filter(pk=bare.pk).update(in_plan=Amp.SPARE)
        row = self.rows(self.generate())['Bare']
        self.assertEqual(self.idle(row).watts, row.calculated_watts_per_unit)
        self.assertEqual([generator.SPARE_NOTE], generator.row_loads(row)[1])

    def test_no_cabinets_in_use_stays_the_worst_case(self):
        # Missing data is never idle: only the toggle makes an amp idle.
        self.amp(self.project, 'LA12X', name='Bare')
        row = self.rows(self.generate())['Bare']
        worst = plan_estimate(row.amplifier, NORMAL, uniform_channel_loads(row.amplifier, None),
                              '3phase_4wire_208', D('0.95'))
        self.assertEqual((NORMAL, worst.watts),
                         (row.effective_programme, row.calculated_watts_per_unit))
        self.assertGreater(worst.watts, self.idle(row).watts)
        self.assertNotIn(generator.SPARE_NOTE, generator.row_loads(row)[1])

    def test_hand_built_rows_have_no_spare(self):
        plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='Hand')
        row = AmplifierAssignment.objects.create(
            distribution_plan=plan, amplifier=AmplifierProfile.objects.get(model='LA8'), quantity=1,
            zone='FOH', programme=HEAVY, phase_assignment='L1')
        Amp.objects.filter(project=self.project).update(in_plan=Amp.SPARE)
        self.assertEqual((False, HEAVY), (row.is_spare, row.effective_programme))

    def test_the_page_and_the_pdf_say_so(self):
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        plan = self.generate()
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, generator.SPARE_NOTE, count=1)
        self.assertContains(page, '<td>Idle (no signal)</td>', count=1)
        text = pdf_text(self.project)
        # The note is on the line under Amp 2's row, and only there.
        self.assertRegex(text, rf'Amp 2 LA8 1 Idle [\d.]+A [\d.]+A\s+{generator.SPARE_NOTE}')
        self.assertEqual(1, text.count(generator.SPARE_NOTE))

    def test_a_toggle_waits_for_regenerate(self):
        plan = self.generate()
        before = self.rows(plan)['Amp 2']
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        plan.programme = HEAVY  # a settings change re-saves every row
        plan.save()
        generator.recompute(plan)
        row = self.rows(plan)['Amp 2']
        heavy = plan_estimate(row.amplifier, HEAVY, amp_channel_loads(self.amp2),
                              '3phase_4wire_208', D('0.95')).watts
        # The row is still the amp in use, as generated...
        self.assertEqual((False, HEAVY, heavy),
                         (row.is_spare, row.effective_programme, row.calculated_watts_per_unit))
        self.assertNotIn(generator.SPARE_NOTE, generator.row_loads(row)[1])
        self.assertNotEqual(before.calculated_watts_per_unit, heavy)  # (recomputed at heavy)
        self.use(self.owner)
        url = reverse('planner:power_distribution_calculator_detail', args=[plan.pk])
        page = self.client.get(url)
        self.assertNotContains(page, generator.SPARE_NOTE)
        self.assertNotContains(page, 'Idle (no signal)</td>')
        # ...and the banner says the racks have changed.
        self.assertContains(page, generator.STALE_MESSAGE)
        self.assertTrue(generator.is_stale(plan))

        generator.regenerate(plan)
        row = self.rows(plan)['Amp 2']
        idle = self.idle(row)
        self.assertEqual((True, IDLE, idle.watts),
                         (row.is_spare, row.effective_programme, row.calculated_watts_per_unit))
        self.assertEqual((idle.current * plan.transient_headroom).quantize(D('0.01')),
                         row.calculated_current_per_unit)
        page = self.client.get(url)
        self.assertContains(page, generator.SPARE_NOTE, count=1)
        self.assertContains(page, '<td>Idle (no signal)</td>', count=1)
        self.assertNotContains(page, generator.STALE_MESSAGE)

        # And back: in use again only on Regenerate.
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.IN_USE)
        generator.recompute(plan)
        self.assertTrue(self.rows(plan)['Amp 2'].is_spare)
        generator.regenerate(plan)
        self.assertFalse(self.rows(plan)['Amp 2'].is_spare)

    def test_amps_in_use_hash_as_before(self):
        # Plans generated before spares existed must not all turn stale.
        import hashlib
        import json
        amps = generator.project_amps(self.project)
        before = hashlib.sha256(json.dumps([[
            a.pk, a.name, a.location_id, a.location.name, a.location.sort_order, a.sort_order,
            a.amp_model.power_profile_id, a.leg,
            [[c.channel_number, c.cabinet_section_id, c.cabinet_quantity]
             for c in sorted(a.channels.all(), key=lambda c: c.channel_number)],
        ] for a in amps]).encode()).hexdigest()
        self.assertEqual(before, generator.fingerprint(self.project))

    def test_inline_toggle(self):
        self.use(self.owner)
        url = reverse('planner:amp_inline_update', args=[self.amp2.pk])
        self.assertEqual(Amp.IN_USE, Amp.objects.get(pk=self.amp2.pk).in_plan)
        self.assertEqual(200, self.client.post(url, {'field': 'in_plan',
                                                     'value': 'spare'}).status_code)
        self.assertEqual(Amp.SPARE, Amp.objects.get(pk=self.amp2.pk).in_plan)
        self.assertEqual(400, self.client.post(url, {'field': 'in_plan',
                                                     'value': 'idle'}).status_code)
        self.assertEqual(Amp.SPARE, Amp.objects.get(pk=self.amp2.pk).in_plan)

    def test_duplicate_project_keeps_spares(self):
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        self.generate()
        copy = self.project.duplicate(new_name='Copy')
        self.assertEqual(Amp.SPARE, Amp.objects.get(project=copy, name='Amp 2').in_plan)
        plan = PowerDistributionPlan.objects.get(project=copy)
        self.assertFalse(generator.is_stale(plan))
        self.assertTrue(self.rows(plan)['Amp 2'].is_spare)


class RegenerateTests(GeneratorFixture):

    def test_stale_until_regenerated(self):
        plan = self.generate()
        self.assertFalse(generator.is_stale(plan))
        for change in (
            lambda: self.assign(self.channel(self.la12x, 2), section('KS28'), 1),
            lambda: Amp.objects.filter(pk=self.la12x.pk).update(leg='L1'),
            lambda: Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE),
            lambda: Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.IN_USE),
            lambda: Amp.objects.filter(pk=self.amp2.pk).update(name='Renamed'),
            lambda: self.amp(self.project, 'LA4X', name='New'),
            lambda: Amp.objects.filter(name='New').delete(),
        ):
            change()
            self.assertTrue(generator.is_stale(plan))
            generator.regenerate(plan)
            self.assertFalse(generator.is_stale(plan))

    def test_regenerate_keeps_settings_legs_and_hand_rows(self):
        plan = self.generate()
        self.use(self.owner)
        self.client.post(reverse('planner:update_plan_settings', args=[plan.pk]),
                         data=json.dumps({'transient_headroom': '1.50', 'programme': 'heavy',
                                          'service_type': 'split_phase_120_240',
                                          'other_electronics_watts': 1500}),
                         content_type='application/json')
        Amp.objects.filter(pk=self.la12x.pk).update(leg='L2')
        hand = AmplifierAssignment.objects.create(
            distribution_plan=plan, amplifier=AmplifierProfile.objects.get(model='LA4X'),
            zone='FOH', phase_assignment='L1')
        self.amp2.delete()

        r = self.client.post(reverse('planner:regenerate_power_plan', args=[plan.pk]))
        self.assertEqual(302, r.status_code)
        plan.refresh_from_db()
        self.assertEqual((D('1.50'), HEAVY, 'split_phase_120_240', 1500),
                         (plan.transient_headroom, plan.programme, plan.service_type,
                          plan.other_electronics_watts))
        rows = self.rows(plan)
        self.assertEqual({'Amp 1'}, set(rows))  # the deleted amp's row is gone
        self.assertEqual('L2', rows['Amp 1'].phase_assignment)
        self.assertEqual(self.watts(self.la12x, HEAVY), rows['Amp 1'].calculated_watts_per_unit)
        self.assertTrue(AmplifierAssignment.objects.filter(pk=hand.pk).exists())

    def test_hand_rows_on_a_leg_count_in_the_balance(self):
        plan = self.generate()
        AmplifierAssignment.objects.create(
            distribution_plan=plan, amplifier=AmplifierProfile.objects.get(model='LA12X'),
            zone='FOH', phase_assignment='L1', quantity=4)
        generator.regenerate(plan)
        self.assertNotIn('L1', {r.phase_assignment for r in self.rows(plan).values()})

    def test_deleted_amp_before_regenerate(self):
        plan = self.generate()
        self.amp2.delete()
        row = AmplifierAssignment.objects.get(distribution_plan=plan, position='Amp 2')
        self.assertIsNone(row.source_amp)
        self.assertIn('amp deleted from the amp module', generator.row_loads(row)[1][0])
        self.assertTrue(generator.is_stale(plan))


class AllowanceAndWarningTests(GeneratorFixture):

    def test_allowance_spread_across_the_legs(self):
        plan = self.generate()
        watts, current = generator.allowance(plan)
        # 2000 W / 3 legs = 666.7 W; / (120 V x 0.95) = 5.85 A, no headroom
        self.assertEqual(D('5.85'), current)
        before = generator_phases(plan)['L1']['total_current']
        plan.other_electronics_watts = 0
        plan.save()
        self.assertAlmostEqual(5.85, before - generator_phases(plan)['L1']['total_current'],
                               places=2)
        plan.other_electronics_watts = 2000
        plan.service_type = 'split_phase_120_240'
        plan.save()
        # 1000 W per leg / 114 = 8.77 A
        self.assertEqual(D('8.77'), generator.allowance(plan)[1])

    def test_allowance_on_the_page_and_the_pdf(self):
        plan = self.generate()
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, generator.ALLOWANCE_LABEL)
        self.assertContains(page, '2000 W, 667 W per leg')
        text = pdf_text(self.project)
        self.assertIn(f'{generator.ALLOWANCE_LABEL}: 2000 W', text)

    def test_warning_when_not_on_three_phase(self):
        plan = self.generate()
        self.assertEqual('', generator.three_phase_warning(plan, plan.amplifier_assignments.all()))
        plan.service_type = 'split_phase_120_240'
        plan.save()
        warning = generator.three_phase_warning(plan, plan.amplifier_assignments.all())
        self.assertEqual('LA12X, LA8 require 3-phase distro', warning)
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, warning)
        self.assertIn(f'Warning: {warning}.', pdf_text(self.project))

    def test_la4x_only_plans_never_warn(self):
        Amp.objects.filter(project=self.project).delete()
        self.amp(self.project, 'LA4X', name='Fill')
        plan = self.generate()
        for service in ('split_phase_120_240', 'single_phase_120', 'single_phase_240'):
            plan.service_type = service
            self.assertEqual('', generator.three_phase_warning(
                plan, plan.amplifier_assignments.all()))

    def test_hand_built_plans_warn_too(self):
        plan = PowerDistributionPlan.objects.create(
            project=self.project, venue_name='Hand', service_type='single_phase_120')
        AmplifierAssignment.objects.create(
            distribution_plan=plan, amplifier=AmplifierProfile.objects.get(model='LA8'), zone='FOH')
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, 'LA8 requires 3-phase distro')

    def test_the_flag_is_on_the_profile(self):
        flags = dict(AmplifierProfile.objects.filter(manufacturer='L-Acoustics')
                     .values_list('model', 'needs_three_phase'))
        self.assertEqual({'LA8': True, 'LA12X': True, 'LA7.16i': True, 'LA4X': False},
                         {k: flags[k] for k in ('LA8', 'LA12X', 'LA7.16i', 'LA4X')})
        # Any brand can be set: the warning reads the flag, not the name.
        la4x = AmplifierProfile.objects.get(model='LA4X')
        la4x.needs_three_phase = True
        la4x.save()
        Amp.objects.filter(project=self.project).delete()
        self.amp(self.project, 'LA4X', name='Fill')
        plan = self.generate()
        plan.service_type = 'single_phase_120'
        self.assertEqual('LA4X requires 3-phase distro', generator.three_phase_warning(
            plan, plan.amplifier_assignments.all()))

    def test_migration_flags_the_profiles(self):
        import importlib
        migration = importlib.import_module('planner.migrations.0216_generated_power_plans')
        AmplifierProfile.objects.update(needs_three_phase=False)
        migration.flag_three_phase(live_apps, None)
        self.assertEqual({'LA8', 'LA12X', 'LA7.16i'} | ({'LA7.16'} if AmplifierProfile.objects
                                                       .filter(model='LA7.16').exists() else set()),
                         set(AmplifierProfile.objects.filter(needs_three_phase=True)
                             .values_list('model', flat=True)))


def pdf_text(project):
    from planner.utils.pdf_exports.report_kit import styles
    from planner.utils.pdf_exports.system_report import _section_power

    def walk(flowables):
        for f in flowables:
            yield getattr(f, 'text', '')
            for attr in ('_content', '_cellvalues'):
                inner = getattr(f, attr, None)
                if inner:
                    for item in inner:
                        if isinstance(item, (list, tuple)):
                            yield ' '.join(str(getattr(c, 'text', c)) for c in item)
                        else:
                            yield from walk([item])
    return ' '.join(walk(_section_power(project, styles(), PowerDistributionPlan)))


class AccessTests(GeneratorFixture):

    def test_button_generates_once_then_opens(self):
        self.use(self.owner)
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertContains(page, 'id="generate-power-plan"')
        r = self.client.post(reverse('planner:generate_power_plan'))
        plan = PowerDistributionPlan.objects.get(project=self.project)
        self.assertRedirects(r, reverse('planner:power_distribution_calculator_detail',
                                        args=[plan.pk]), fetch_redirect_response=False)
        self.client.post(reverse('planner:generate_power_plan'))
        self.assertEqual(1, PowerDistributionPlan.objects.filter(project=self.project).count())
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertContains(page, 'id="open-power-plan"')
        self.assertNotContains(page, 'changed since generated')
        self.assign(self.channel(self.la12x, 2), section('KS28'), 1)
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertContains(page, 'changed since generated')
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertContains(page, generator.STALE_MESSAGE)
        self.assertContains(page, 'Regenerate')

    def test_viewer_cannot_generate_or_regenerate(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        self.client.post(reverse('planner:generate_power_plan'))
        self.assertFalse(PowerDistributionPlan.objects.exists())
        plan = self.generate()
        self.amp2.delete()
        self.client.post(reverse('planner:regenerate_power_plan', args=[plan.pk]))
        self.assertTrue(AmplifierAssignment.objects.filter(position='Amp 2').exists())

    def test_regenerate_is_scoped_to_the_project(self):
        plan = self.generate()
        outsider = staff('outsider')
        self.use(outsider, self.other)
        r = self.client.post(reverse('planner:regenerate_power_plan', args=[plan.pk]))
        self.assertEqual(404, r.status_code)

    def test_generated_rows_are_not_edited_by_hand(self):
        plan = self.generate()
        row = self.rows(plan)['Amp 1']
        self.use(self.owner)
        r = self.client.post(reverse('planner:update_amplifier_assignment', args=[row.pk]),
                             data=json.dumps({'quantity': 5}), content_type='application/json')
        self.assertEqual(400, r.status_code)
        r = self.client.delete(reverse('planner:delete_amplifier_assignment', args=[row.pk]))
        self.assertEqual(400, r.status_code)
        from planner.admin import AmplifierAssignmentInlineForm
        form = AmplifierAssignmentInlineForm(instance=row)
        self.assertTrue(all(f.disabled for f in form.fields.values()))


class AmpModuleTests(GeneratorFixture):

    def post_leg(self, value):
        return self.client.post(reverse('planner:amp_inline_update', args=[self.la12x.pk]),
                                {'field': 'leg', 'value': value})

    def test_leg_inline(self):
        self.use(self.owner)
        self.assertEqual(200, self.post_leg('L2').status_code)
        self.la12x.refresh_from_db()
        self.assertEqual('L2', self.la12x.leg)
        self.assertEqual(400, self.post_leg('L4').status_code)
        self.assertEqual(200, self.post_leg('').status_code)

    def test_leg_choices_follow_the_service(self):
        self.use(self.owner)
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertContains(page, '<option value="L3"')
        plan = self.generate()
        plan.service_type = 'split_phase_120_240'
        plan.save()
        Amp.objects.filter(pk=self.amp2.pk).update(leg='L3')
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertContains(page, 'L3 (not on this service)', count=1)

    def heads(self, page):
        """Each amp card's cabinets heading line, and its middle column."""
        html = page.content.decode()
        return (re.findall(r'<div class="amp-cabinets-head">(.*?)<div class="amp-cabinet-grid">',
                           html, re.S),
                re.findall(r'amp-card-middle">(.*?)Right: Outputs', html, re.S))

    def test_in_plan_and_leg_sit_at_the_end_of_the_cabinets_heading(self):
        model = AmpModel.objects.create(manufacturer='L-Acoustics', model_name='LA7.16i',
                                        channel_count=16)
        location = self.la12x.location
        wide = Amp.objects.create(project=self.project, location=location, amp_model=model,
                                  name='Amp 16')
        self.use(self.owner)
        heads, middles = self.heads(self.client.get(reverse('admin:planner_amp_changelist')))
        self.assertEqual(3, len(heads))
        for amp in (self.la12x, self.amp2, wide):  # 4 and 16 outputs alike
            head = next(h for h in heads if f'id="amp-leg-{amp.pk}"' in h)
            # last things on the line, after the title and notes: In plan, then Leg
            self.assertRegex(head, r'(?s)Cabinets per output.*class="amp-plan-controls"'
                                   r'.*data-field="in_plan".*Leg.*data-field="leg"'
                                   r'.*</select>\s*</div>\s*</div>\s*</div>\s*$')
        self.assertFalse(any('data-field="leg"' in m or 'data-field="in_plan"' in m
                             for m in middles))

    def test_viewer_sees_in_plan_and_leg_read_only(self):
        Amp.objects.filter(pk=self.la12x.pk).update(leg='L2', in_plan=Amp.SPARE)
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertNotContains(page, 'data-field="leg"')
        self.assertNotContains(page, 'data-field="in_plan"')
        heads, _ = self.heads(page)
        self.assertEqual([('Spare', 'L2'), ('In use', 'Auto')], [
            re.search(r'(?s)amp-in-plan-value">([\w ]+)<.*'
                      r'Leg</span>\s*<span class="amp-leg-value">(\w+)<', h).groups()
            for h in heads])

    def test_duplicate_project(self):
        Amp.objects.filter(pk=self.la12x.pk).update(leg='L3')
        self.generate()
        copy = self.project.duplicate(new_name='Copy')
        plan = PowerDistributionPlan.objects.get(project=copy)
        self.assertTrue(plan.is_generated)
        self.assertFalse(generator.is_stale(plan))
        row = plan.amplifier_assignments.get(position='Amp 1')
        self.assertEqual((copy.pk, 'L3', 'L3'),
                         (row.source_amp.project_id, row.source_amp.leg, row.amp_leg))
