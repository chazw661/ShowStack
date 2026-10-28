"""The power plan in the system report PDF (section 7) and the plan page's
leg figures: wrapped cells, each amp's note under its row, the model only,
expected load vs size for, and the page title.

Run with::

    python manage.py test planner.tests.test_power_plan_pdf_layout \\
        --settings=audiopatch.test_settings
"""

from decimal import Decimal

from django.urls import reverse
from reportlab.platypus import Paragraph

from planner.models import Amp, AmplifierAssignment, AmplifierProfile, PowerDistributionPlan
from planner.tests.test_power_plan_generate import GeneratorFixture, pdf_text
from planner.utils import power_plan_generator as generator
from planner.utils.pdf_exports.report_kit import styles
from planner.utils.pdf_exports.system_report import USABLE_WIDTH, _power_table, _section_power
from planner.views import calculate_phase_distribution

D = Decimal
LONG = 'Stage Left Main Hang Kara II Upper Array Amp Rack Three'


class PdfFixture(GeneratorFixture):

    def setUp(self):
        super().setUp()
        Amp.objects.filter(pk=self.la12x.pk).update(name=LONG)
        self.plan = self.generate()

    def table(self, plan=None):
        plan = plan or self.plan
        assignments = list(plan.amplifier_assignments.select_related('amplifier', 'source_amp')
                           .order_by('phase_assignment', 'position'))
        brands = sorted({a.amplifier.manufacturer for a in assignments})
        return _power_table(plan, assignments, plan.legs, brands)[0]

    def story(self):
        return _section_power(self.project, styles(), PowerDistributionPlan)


class TableLayoutTests(PdfFixture):

    def test_cells_wrap_inside_their_column(self):
        table = self.table()
        table.wrap(USABLE_WIDTH, 1000)
        self.assertLessEqual(sum(table._colWidths), USABLE_WIDTH)
        # (wrap() holds a flowable cell in a tuple)
        cells = [[v[0] if isinstance(v, (list, tuple)) else v for v in row]
                 for row in table._cellvalues[1:]]
        for row in cells:
            for value in row:
                self.assertTrue(value == '' or isinstance(value, Paragraph), repr(value))
        position = next(row[1] for row in cells if getattr(row[1], 'text', '') == LONG)
        width = table._colWidths[1] - 12  # less the cell padding
        _, height = position.wrap(width, 1000)
        self.assertGreater(height, position.style.leading)  # more than one line
        self.assertLessEqual(max(position.getActualLineWidths0()), width)

    def test_amplifier_column_is_the_model_with_one_brand_in_the_header(self):
        table = self.table()
        self.assertEqual('Amplifier (L-Acoustics)', table._cellvalues[0][2])
        models = {row[2].text for row in table._cellvalues[1:] if isinstance(row[2], Paragraph)}
        self.assertEqual({'LA12X', 'LA8'}, models)
        self.assertNotIn('Amplifiers:', pdf_text(self.project))

    def test_mixed_brands_get_a_legend(self):
        other = AmplifierProfile.objects.create(
            manufacturer='Powersoft', model='X8', idle_power_watts=300, rated_power_watts=1200,
            peak_power_watts=2400, max_power_watts=4000)
        AmplifierAssignment.objects.create(distribution_plan=self.plan, amplifier=other,
                                           quantity=1, zone='FOH', position='Fills',
                                           phase_assignment='L3')
        table = self.table()
        self.assertEqual('Amplifier', table._cellvalues[0][2])
        self.assertIn('X8', {getattr(row[2], 'text', '') for row in table._cellvalues[1:]})
        self.assertIn('Amplifiers: LA12X, LA8 — L-Acoustics; X8 — Powersoft',
                      pdf_text(self.project))

    def test_each_note_is_under_its_row_in_table_order(self):
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        generator.regenerate(self.plan)
        rows = self.table()._cellvalues[1:]
        texts = [[getattr(c, 'text', c) for c in row] for row in rows]
        amp1 = next(i for i, r in enumerate(texts) if r[1] == LONG)
        amp2 = next(i for i, r in enumerate(texts) if r[1] == 'Amp 2')
        self.assertEqual('2 of 4 outputs have no cabinet (counted at idle)', texts[amp1 + 1][1])
        self.assertEqual(generator.SPARE_NOTE, texts[amp2 + 1][1])
        self.assertEqual('', texts[amp1 + 1][0])
        # No list of notes after the table any more.
        after = ' '.join(getattr(f, 'text', '') for f in self.story())
        self.assertNotIn(f'{LONG}:', after)
        self.assertNotIn('Amp 2:', after)

    def test_a_note_row_never_splits_from_its_amp(self):
        table = self.table()
        texts = [[getattr(c, 'text', c) for c in row] for row in table._cellvalues]
        notes = [i for i, r in enumerate(texts) if i and r[0] == '' and r[1]
                 and not r[2]]
        self.assertTrue(notes)
        nosplit = {(c[1][1], c[2][1]) for c in table._nosplitCmds}
        for row in notes:
            self.assertIn((row - 1, row), nosplit)

    def test_a_note_row_shares_its_amps_background(self):
        table = self.table()
        commands = table._bkgrndcmds
        spans = table._spanCmds
        # Amp 1's row and its note row are one span of background, or neither.
        note_rows = [s[1][1] for s in spans if s[1][0] == 1 and s[2][0] == -1]
        self.assertTrue(note_rows)
        for row in note_rows:
            shaded = [c for c in commands if c[1][1] <= row <= c[2][1]]
            above = [c for c in commands if c[1][1] <= row - 1 <= c[2][1]]
            self.assertEqual(shaded, above)


class LegFigureTests(PdfFixture):

    def test_expected_load_has_no_headroom_and_no_allowance(self):
        loads = calculate_phase_distribution(self.plan)
        allowance = float(generator.allowance(self.plan)[1])
        for name, leg in loads['phases'].items():
            rows = [r for r in self.plan.amplifier_assignments.all() if r.phase_assignment == name]
            watts = sum(r.calculated_watts_per_unit * r.quantity for r in rows)
            self.assertAlmostEqual(watts / (120 * 0.95), leg['expected_current'], delta=0.02)
            size_for = sum(float(r.calculated_total_current) for r in rows) + allowance
            self.assertAlmostEqual(size_for, leg['total_current'], places=6)
            # headroom on top of expected, then the allowance
            self.assertAlmostEqual(leg['expected_current'] * 1.25 + allowance,
                                   leg['total_current'], delta=0.05)

    def test_hand_built_auto_rows_split_both_figures_alike(self):
        plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='Hand',
                                                    other_electronics_watts=0)
        AmplifierAssignment.objects.create(
            distribution_plan=plan, amplifier=AmplifierProfile.objects.get(model='LA12X'),
            quantity=3, zone='FOH', phase_assignment='AUTO')
        legs = calculate_phase_distribution(plan)['phases']
        self.assertEqual(1, len({round(l['expected_current'], 6) for l in legs.values()}))
        for leg in legs.values():
            self.assertAlmostEqual(leg['expected_current'] * 1.25, leg['total_current'],
                                   delta=0.02)

    def test_the_pdf_shows_both_and_explains_them(self):
        text = ' '.join(getattr(f, 'text', '') for f in self.story())
        loads = calculate_phase_distribution(self.plan)['phases']
        self.assertIn('<b>Expected load:</b> ' + ' · '.join(
            f"{n} {l['expected_current']:.1f}A" for n, l in loads.items()), text)
        self.assertIn('<b>Size for:</b> ' + ' · '.join(
            f"{n} {l['total_current']:.1f}A" for n, l in loads.items()), text)
        self.assertIn("Expected load is the amps' estimated draw at programme level. Size for "
                      "adds 25% transient headroom to that, plus the other-electronics "
                      "allowance: size the distro and breakers for this figure.", text)
        self.assertNotIn('Per leg:', text)

    def test_footnote_wording(self):
        text = ' '.join(getattr(f, 'text', '') for f in self.story())
        self.assertIn('including 25% transient headroom. Headroom is not applied to the '
                      'other-electronics allowance.', text)
        self.assertNotIn('has none', text)
        self.plan.other_electronics_watts = 0
        self.plan.save()
        text = ' '.join(getattr(f, 'text', '') for f in self.story())
        self.assertNotIn('other-electronics allowance', text)

    def test_the_page_shows_both_on_every_leg_card(self):
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[self.plan.pk]))
        loads = calculate_phase_distribution(self.plan)['phases']
        for name, leg in loads.items():
            self.assertContains(page, f'id="{name.lower()}-expected">{leg["expected_rounded"]}A<')
            self.assertContains(page, f'id="{name.lower()}-current">{leg["current_rounded"]}A<')
        self.assertContains(page, 'Expected load</div>', count=len(loads))
        self.assertContains(page, 'Size for</div>', count=len(loads))
        self.assertContains(page, generator.leg_figures_note(self.plan).replace("'", '&#x27;'))


class PageTitleTests(GeneratorFixture):

    def title(self, plan):
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk]))
        self.assertNotContains(page, 'None')
        return page

    def test_title_is_the_venue(self):
        plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='Arena B')
        self.assertContains(self.title(plan),
                            '<title>Power Distribution Calculator - Arena B</title>')

    def test_title_falls_back_to_the_project(self):
        plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='')
        page = self.title(plan)
        self.assertContains(page, '<title>Power Distribution Calculator - Show A</title>')
        self.assertNotContains(page, '<strong>Show:</strong>')
