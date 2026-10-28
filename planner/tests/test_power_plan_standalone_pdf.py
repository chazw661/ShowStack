"""The standalone power plan PDF (the "PDF" button on the plan page), and a
spare row's Load / Channel shown as "—".

The PDF is the project, venue, date and service, then the plan exactly as
the system report's power section renders it -- the same function
(system_report._power_plan), not a copy.

Run with::

    python manage.py test planner.tests.test_power_plan_standalone_pdf \\
        --settings=audiopatch.test_settings
"""

from io import BytesIO
from unittest import mock

from django.urls import reverse
from PyPDF2 import PdfReader

from planner.models import Amp, PowerDistributionPlan, ShowDay
from planner.tests.test_amp_output_cabinets import staff
from planner.tests.test_power_plan_generate import GeneratorFixture
from planner.utils.pdf_exports import system_report
from planner.utils.pdf_exports.report_kit import styles


def text(response):
    return ' '.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)


class StandalonePdfTests(GeneratorFixture):

    def setUp(self):
        super().setUp()
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        self.plan = self.generate()
        self.url = reverse('planner:power_plan_pdf', args=[self.plan.pk])
        self.use(self.owner)

    def test_download_named_for_the_project(self):
        resp = self.client.get(self.url)
        self.assertEqual(200, resp.status_code)
        self.assertEqual('application/pdf', resp['Content-Type'])
        self.assertEqual('attachment; filename="Show A - Power Plan.pdf"',
                         resp['Content-Disposition'])
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_header_then_the_section_7_content(self):
        body = text(self.client.get(self.url))
        for expected in ('Show A', 'Power Plan', 'Venue:', 'Show A', 'Printed:',
                         'Service:', '3-Phase', 'Expected load:', 'Size for:',
                         'Amp 1', 'Amp 2', 'transient headroom', 'Spare: counted at idle'):
            self.assertIn(expected, body)
        # The header gives venue and service; the plan's own heading is left out.
        self.assertEqual(1, body.count('Venue:'))
        self.assertEqual(1, body.count('Service:'))

    def test_show_day_date_when_the_plan_has_one(self):
        day = ShowDay.objects.create(project=self.project, date='2026-11-14')
        PowerDistributionPlan.objects.filter(pk=self.plan.pk).update(show_day=day)
        body = text(self.client.get(self.url))
        self.assertIn('November 14, 2026', body)
        self.assertNotIn('Printed:', body)

    def test_one_renderer_for_both_pdfs(self):
        with mock.patch.object(system_report, '_power_plan',
                               wraps=system_report._power_plan) as renderer:
            self.client.get(self.url)
            self.assertEqual(1, renderer.call_count)
            self.assertFalse(renderer.call_args.kwargs['heading'])
            system_report._section_power(self.project, styles(), PowerDistributionPlan)
            self.assertEqual(2, renderer.call_count)
            self.assertEqual(self.plan, renderer.call_args.args[0])

    def test_viewer_may_download(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        self.assertEqual(200, self.client.get(self.url).status_code)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[self.plan.pk]))
        self.assertContains(page, f'href="{self.url}" class="pdf-link" id="pdf-link">PDF</a>')

    def test_another_projects_plan_is_404(self):
        self.use(self.other.owner, self.other)
        self.assertEqual(404, self.client.get(self.url).status_code)

    def test_page_has_the_button_next_to_amplifiers(self):
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[self.plan.pk])).content.decode()
        # The PDF link is the next element after "← Amplifiers".
        amps_end = page.index('</a>', page.index('id="amps-link"')) + len('</a>')
        between = page[amps_end:page.index('<a href="' + self.url)]
        self.assertEqual('', between.strip())


class SpareLoadTests(GeneratorFixture):

    def test_spare_row_has_no_load(self):
        Amp.objects.filter(pk=self.amp2.pk).update(in_plan=Amp.SPARE)
        plan = self.generate()
        rows = self.rows(plan)
        self.assertIsNone(rows['Amp 2'].assumed_load_ohms)
        self.assertIsNotNone(rows['Amp 1'].assumed_load_ohms)
        self.use(self.owner)
        page = self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[plan.pk])).content.decode()
        row = page[page.index(f'data-id="{rows["Amp 2"].pk}"'):]
        row = row[:row.index('</tr>')]
        self.assertIn('<td>—</td>', row)
        self.assertNotIn('lowest published', row)
