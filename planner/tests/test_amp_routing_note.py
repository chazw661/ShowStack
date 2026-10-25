"""The CH 1-4 routing block stays where it is; each cabinet cell (and the amp
PDF's cabinets row) gets an amber note when the channel's routing zone
disagrees with its cabinet section's. Plus the routing save validation.

Run with::

    python manage.py test planner.tests.test_amp_routing_note \\
        --settings=audiopatch.test_settings
"""

from django.urls import reverse

from planner.models import Amp, AmpChannel
from planner.tests.test_amp_output_cabinets import Fixture, section, staff


def table_texts(flowables):
    """Every string in every Table among some ReportLab flowables."""
    from reportlab.platypus import Table
    texts = []
    stack = list(flowables if isinstance(flowables, (list, tuple)) else [flowables])
    while stack:
        f = stack.pop()
        if isinstance(f, Table):
            for row in f._cellvalues:
                for cell in row:
                    if isinstance(cell, (list, tuple, Table)):
                        stack.extend(cell if isinstance(cell, (list, tuple)) else [cell])
                    else:
                        texts.append(str(getattr(cell, 'text', cell)))
        elif isinstance(f, (list, tuple)):
            stack.extend(f)
    return texts


class Base(Fixture):

    def setUp(self):
        super().setUp()
        # CH 1 routed LF, carrying HF: the note. CH 2 agrees. CH 3 MF: no zone.
        self.ch1 = self.route(1, section('Kara II', 'HF'), 'LF_B')
        self.ch2 = self.route(2, section('KS28'), 'SB_A')
        self.ch3 = self.route(3, section('K1', 'MF'), 'HF_C')
        self.url = reverse('admin:planner_amp_changelist')

    def route(self, n, sec, setting):
        ch = self.assign(self.channel(self.la12x, n), sec, 1)
        AmpChannel.objects.filter(pk=ch.pk).update(channel_setting=setting)
        return AmpChannel.objects.get(pk=ch.pk)


class MismatchRuleTests(Base):

    def test_section_zones(self):
        self.assertEqual(['LF', 'HF', 'SB', 'PA', '', ''],
                         [s.routing_zone for s in (
                             section('Kara II', 'LF'), section('Kara II', 'HF'), section('KS28'),
                             section('Kiva'), section('K1', 'MF'), section('L2 / L2D', 'LC'))])

    def test_note_text(self):
        self.assertEqual('CH 1 is routed LF, cabinet is Kara II · HF', self.ch1.routing_mismatch)
        self.ch1.cabinet_section = section('Kiva')
        self.assertEqual('CH 1 is routed LF, cabinet is Kiva', self.ch1.routing_mismatch)

    def test_no_note_when_they_agree_or_either_side_is_empty(self):
        self.assertEqual('', self.ch2.routing_mismatch)                  # agree
        self.assertEqual('', self.ch3.routing_mismatch)                  # MF: no zone
        self.ch1.channel_setting = ''
        self.assertEqual('', self.ch1.routing_mismatch)                  # no routing
        bare = self.channel(self.la12x, 4)
        bare.channel_setting = 'LF_A'
        self.assertEqual('', bare.routing_mismatch)                      # no cabinet


class RackCardTests(Base):

    def test_ch_block_is_unchanged(self):
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertIn('<div class="amp-channel-settings">', page)
        self.assertEqual(4, page.count('class="amp-cell-input amp-channel-setting-select"'))
        self.assertEqual(4, page.count('data-field="channel_setting"'))
        self.assertIn('<span class="amp-channel-setting-label">Ch 1</span>', page)

    def test_note_in_the_cell_only_where_they_disagree(self):
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertIn('<span class="amp-cabinet-chip amp-routing-mismatch" data-channel-number="1">'
                      'CH 1 is routed LF, cabinet is Kara II · HF</span>', page)
        self.assertEqual(4, page.count('amp-routing-mismatch" data-channel-number="'))
        for n in (2, 3, 4):
            self.assertIn(f'amp-routing-mismatch" data-channel-number="{n}" hidden>', page)

    def test_viewer_sees_the_note(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        self.assertContains(self.client.get(self.url), 'CH 1 is routed LF, cabinet is Kara II · HF')

    def test_display_only(self):
        self.use(self.owner)
        self.client.get(self.url)
        url = reverse('planner:amp_channel_inline_update', args=[self.ch1.pk])
        self.client.post(url, {'field': 'cabinet', 'cabinet_section': section('KS28').pk,
                               'cabinet_quantity': '1'})
        self.ch1.refresh_from_db()
        self.assertEqual('LF_B', self.ch1.channel_setting)
        self.client.post(url, {'field': 'channel_setting', 'value': 'HF_D'})
        self.ch1.refresh_from_db()
        self.assertEqual((section('KS28'), 'HF_D'), (self.ch1.cabinet_section, self.ch1.channel_setting))

    def test_ipad_css(self):
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertIn('select.amp-cabinet-select { height: 44px;', page)
        add_row = page[page.index('.add-amp-row {'):]
        self.assertIn('flex-wrap: wrap;', add_row[:add_row.index('}')])


class ChannelSettingSaveTests(Fixture):

    def setUp(self):
        super().setUp()
        self.ch = self.channel(self.la12x)
        self.url = reverse('planner:amp_channel_inline_update', args=[self.ch.pk])

    def post(self, value):
        return self.client.post(self.url, {'field': 'channel_setting', 'value': value})

    def test_whole_setting_or_clear(self):
        self.use(self.owner)
        self.assertEqual(200, self.post('LF_B').status_code)
        self.ch.refresh_from_db()
        self.assertEqual('LF_B', self.ch.channel_setting)
        self.assertEqual(200, self.post('').status_code)
        self.ch.refresh_from_db()
        self.assertEqual('', self.ch.channel_setting)

    def test_anything_else_is_refused(self):
        self.use(self.owner)
        for value in ('LF_', '_B', 'LF', 'XX_A', 'LF_E', 'lf_b', 'x' * 30):
            self.assertEqual(400, self.post(value).status_code, value)
        self.ch.refresh_from_db()
        self.assertEqual('', self.ch.channel_setting)

    def test_viewer_is_refused(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        self.assertEqual(403, self.post('LF_B').status_code)


class PdfTests(Base):

    def channels(self):
        amp = Amp.objects.prefetch_related('channels').get(pk=self.la12x.pk)
        return sorted(amp.channels.all(), key=lambda c: c.channel_number)

    def test_routing_still_prints_in_the_middle_panel(self):
        from planner.utils.pdf_exports import report_kit, system_report
        for module in (report_kit, system_report):
            texts = table_texts(module._amp_middle(self.la12x, self.channels()))
            for setting in ('LF_B', 'SB_A', 'HF_C'):
                self.assertIn(setting, texts, module.__name__)

    def test_cabinets_row_carries_the_note_in_amber(self):
        from planner.utils.pdf_exports import report_kit as kit
        _title, table = kit.amp_cabinets_table(self.channels())
        cells = [c for row in table._cellvalues for c in row if c]
        self.assertIn('CH 1 is routed LF, cabinet is Kara II · HF', cells[0].text)
        frag = [f for f in cells[0].frags if 'CH 1 is routed' in f.text][0]
        self.assertEqual(kit.AMP_WARN.hexval(), frag.textColor.hexval())
        for cell in cells[1:]:
            self.assertNotIn('is routed', cell.text)

    def test_both_pdfs_build(self):
        from planner.utils.pdf_exports.amplifier_pdf import export_all_amps_pdf
        from planner.utils.pdf_exports.report_kit import styles
        from planner.utils.pdf_exports.system_report import _section_amplifiers
        self.assertTrue(export_all_amps_pdf(self.project).content.startswith(b'%PDF'))
        self.assertTrue(_section_amplifiers(self.project, styles(), Amp))
