"""The CH 1-4 routing block stays where it is; each cabinet cell (and the amp
PDF's cabinets row) gets an amber note when the channel's routing zone
disagrees with its cabinet section's. Plus the routing save validation.

Run with::

    python manage.py test planner.tests.test_amp_routing_note \\
        --settings=audiopatch.test_settings
"""

from django.urls import reverse

from planner.models import Amp, AmpChannel, AmpModel
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
        self.ch1.cabinet_section = section('KS28')
        self.assertEqual('CH 1 is routed LF, cabinet is KS28', self.ch1.routing_mismatch)

    def test_only_real_conflicts(self):
        from planner.models import routing_zones_conflict
        zones = ('PA', 'LF', 'HF', 'SB', '')
        for routed in zones:
            for implied in zones:
                expected = (routed not in ('PA', '') and implied not in ('PA', '')
                            and routed != implied)
                self.assertEqual(expected, routing_zones_conflict(routed, implied),
                                 (routed, implied))

    def test_pa_is_neutral_both_ways(self):
        self.ch1.cabinet_section = section('Kiva')                       # implies PA
        for setting in ('LF_B', 'HF_A', 'SB_C', 'PA_D'):
            self.ch1.channel_setting = setting
            self.assertEqual('', self.ch1.routing_mismatch, setting)
        self.ch1.channel_setting = 'PA_A'                                # routed PA
        for sec in (section('Kara II', 'LF'), section('Kara II', 'HF'), section('KS28')):
            self.ch1.cabinet_section = sec
            self.assertEqual('', self.ch1.routing_mismatch, str(sec))

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

    def test_pa_never_warns_on_the_card(self):
        AmpChannel.objects.filter(pk=self.ch1.pk).update(channel_setting='PA_A')
        AmpChannel.objects.filter(pk=self.ch2.pk).update(
            cabinet_section=section('Kiva'), channel_setting='LF_C')
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertNotIn('is routed', page.replace("' is routed '", ''))
        self.assertEqual(4, page.count('amp-routing-mismatch" data-channel-number="'))

    def test_cells_carry_what_the_note_is_worked_out_from(self):
        # Used for viewers, who have no cabinet picker to read.
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertIn(f'<div class="amp-cabinet-cell" data-channel-id="{self.ch1.pk}"\n'
                      '                             data-section-zone="HF"\n'
                      '                             data-section-label="Kara II · HF"\n'
                      '                             data-routed-zone="LF">', page)
        self.assertIn("routed === 'PA' || implied === 'PA'", page)

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

    def test_pdf_row_follows_the_same_rules(self):
        from planner.utils.pdf_exports import report_kit as kit
        AmpChannel.objects.filter(pk=self.ch1.pk).update(channel_setting='PA_A')   # PA: neutral
        AmpChannel.objects.filter(pk=self.ch2.pk).update(channel_setting='LF_A')   # LF vs SB
        AmpChannel.objects.filter(pk=self.ch3.pk).update(cabinet_section=section('Kiva'))  # HF vs PA
        _title, table = kit.amp_cabinets_table(self.channels())
        cells = [c.text for row in table._cellvalues for c in row if c]
        self.assertNotIn('is routed', cells[0])
        self.assertIn('CH 2 is routed LF, cabinet is KS28', cells[1])
        self.assertNotIn('is routed', cells[2])
        self.assertNotIn('is routed', cells[3])

    def test_both_pdfs_build(self):
        from planner.utils.pdf_exports.amplifier_pdf import export_all_amps_pdf
        from planner.utils.pdf_exports.report_kit import styles
        from planner.utils.pdf_exports.system_report import _section_amplifiers
        self.assertTrue(export_all_amps_pdf(self.project).content.startswith(b'%PDF'))
        self.assertTrue(_section_amplifiers(self.project, styles(), Amp))


class WideAmpBase(Fixture):
    """An LA7.16 (16 channels) beside the fixture's LA12X (4)."""

    def setUp(self):
        super().setUp()
        self.models['LA7.16'] = AmpModel.objects.create(
            manufacturer='L-Acoustics', model_name='LA7.16', channel_count=16)
        self.la716 = self.amp(self.project, 'LA7.16', name='Amp 16')
        self.url = reverse('admin:planner_amp_changelist')

    def set(self, amp, n, setting):
        ch = self.channel(amp, n)
        AmpChannel.objects.filter(pk=ch.pk).update(channel_setting=setting)
        return AmpChannel.objects.get(pk=ch.pk)

    def post(self, ch, value):
        return self.client.post(reverse('planner:amp_channel_inline_update', args=[ch.pk]),
                                {'field': 'channel_setting', 'value': value})


class RoleOnlyChoicesTests(WideAmpBase):

    def test_wide_amp_offers_the_role_only(self):
        ch = self.channel(self.la716, 9)
        self.assertTrue(ch.role_only_routing)
        self.assertEqual(['', 'PA', 'LF', 'HF', 'SB'], [v for v, _ in ch.channel_setting_choices])

    def test_four_channel_amp_keeps_role_and_input(self):
        ch = self.channel(self.la12x)
        self.assertFalse(ch.role_only_routing)
        self.assertEqual([''] + [f'{z}_{s}' for z in ('PA', 'LF', 'HF', 'SB') for s in 'ABCD'],
                         [v for v, _ in ch.channel_setting_choices])

    def test_a_stored_value_outside_the_list_stays_visible(self):
        # e.g. the amp's model was changed after the value was set
        ch = self.set(self.la716, 3, 'PA_B')
        self.assertEqual(('PA_B', 'PA_B'), ch.channel_setting_choices[-1])
        self.assertEqual(('LF', 'LF'), self.set(self.la12x, 1, 'LF').channel_setting_choices[-1])

    def test_pdfs_print_a_role_only_value(self):
        self.assertEqual('SB', self.set(self.la716, 1, 'SB').get_channel_setting_display())


class RoleOnlySaveTests(WideAmpBase):

    def test_role_saves_and_survives_a_reload(self):
        self.use(self.owner)
        ch = self.channel(self.la716, 12)
        self.assertEqual(200, self.post(ch, 'PA').status_code)
        ch.refresh_from_db()
        self.assertEqual('PA', ch.channel_setting)
        page = self.client.get(self.url).content.decode()
        select = page[page.index(f'data-channel-id="{ch.pk}"\n                data-field="channel_setting"'):]
        select = select[:select.index('</select>')]
        self.assertIn('title="PA"', select)
        self.assertIn('<option value="PA" selected>PA</option>', select)

    def test_wide_amp_refuses_a_suffix_and_four_channel_refuses_role_only(self):
        self.use(self.owner)
        wide, four = self.channel(self.la716, 2), self.channel(self.la12x, 2)
        self.assertEqual(400, self.post(wide, 'PA_B').status_code)
        self.assertEqual(400, self.post(four, 'PA').status_code)
        self.assertEqual(200, self.post(four, 'PA_B').status_code)
        wide.refresh_from_db()
        four.refresh_from_db()
        self.assertEqual(('', 'PA_B'), (wide.channel_setting, four.channel_setting))

    def test_clear_still_works(self):
        self.use(self.owner)
        ch = self.set(self.la716, 1, 'HF')
        self.assertEqual(200, self.post(ch, '').status_code)
        ch.refresh_from_db()
        self.assertEqual('', ch.channel_setting)


class WideCardTests(WideAmpBase):

    def test_wide_amp_wraps_and_four_channel_amp_does_not(self):
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertEqual(1, page.count('<div class="amp-channel-settings amp-channel-settings-wrap">'))
        self.assertEqual(1, page.count('<div class="amp-channel-settings">'))
        self.assertEqual(20, page.count('data-field="channel_setting"'))
        wide = page[page.index('amp-channel-settings-wrap">'):]
        wide = wide[:wide.index('amp-card-cabinets')]
        self.assertEqual(16, wide.count('title="No routing"'))
        self.assertNotIn('PA_A', wide)
        self.assertIn('<span class="amp-channel-setting-label">Ch 16</span>', wide)

    def test_wide_block_gets_the_full_card_width(self):
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        routing = page.index('<div class="amp-card-routing">')
        self.assertLess(page.index('amp-card-outputs'), routing)
        self.assertLess(routing, page.index('amp-channel-settings-wrap"'))
        self.assertIn('Channel routing — role only; inputs are routed in LA Network Manager', page)
        self.assertEqual(1, page.count('<div class="amp-card-routing">'))
        self.assertIn('.amp-card-routing,\n    .amp-card-cabinets {\n        grid-column: 1 / -1;', page)
        self.assertNotIn('Issue #30: the CH-block routing selects', page)  # template comment

    def test_wrap_css(self):
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        rule = page[page.index('.amp-channel-settings-wrap {'):]
        self.assertIn('minmax(max(72px, calc((100% - 7 * 6px) / 8)), 1fr)', rule[:rule.index('}')])
        self.assertIn('.amp-channel-settings-wrap select.amp-channel-setting-select {\n'
                      '            height: 44px;', page)


class RoleOnlyMismatchTests(WideAmpBase):

    def route(self, n, sec, setting):
        ch = self.assign(self.channel(self.la716, n), sec, 1)
        AmpChannel.objects.filter(pk=ch.pk).update(channel_setting=setting)
        return AmpChannel.objects.get(pk=ch.pk)

    def test_role_only_tag_against_the_cabinet(self):
        self.assertEqual('LF', self.route(3, section('Kara II', 'HF'), 'LF').routing_zone)
        self.assertEqual('CH 3 is routed LF, cabinet is Kara II · HF',
                         self.route(3, section('Kara II', 'HF'), 'LF').routing_mismatch)
        self.assertEqual('CH 14 is routed SB, cabinet is Kara II · LF',
                         self.route(14, section('Kara II', 'LF'), 'SB').routing_mismatch)
        self.assertEqual('', self.route(5, section('KS28'), 'SB').routing_mismatch)
        self.assertEqual('', self.route(6, section('K1', 'MF'), 'HF').routing_mismatch)
        self.assertEqual('', self.route(7, section('KS28'), '').routing_mismatch)

    def test_note_on_the_rack_card(self):
        self.route(11, section('Kara II', 'HF'), 'LF')
        self.route(12, section('Kara II', 'HF'), 'HF')
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertIn('<span class="amp-cabinet-chip amp-routing-mismatch" data-channel-number="11">'
                      'CH 11 is routed LF, cabinet is Kara II · HF</span>', page)
        self.assertIn('amp-routing-mismatch" data-channel-number="12" hidden>', page)

    def test_pdf_cabinets_row_carries_the_note(self):
        from planner.utils.pdf_exports import report_kit as kit
        self.route(11, section('Kara II', 'HF'), 'LF')
        amp = Amp.objects.prefetch_related('channels').get(pk=self.la716.pk)
        _title, table = kit.amp_cabinets_table(sorted(amp.channels.all(), key=lambda c: c.channel_number))
        texts = ' '.join(c.text for row in table._cellvalues for c in row if c)
        self.assertIn('CH 11 is routed LF, cabinet is Kara II · HF', texts)


class StripInputSuffixTests(WideAmpBase):

    def test_converts_wide_amps_only_reports_the_count_and_is_idempotent(self):
        from planner.utils.channel_routing import strip_input_suffix
        self.set(self.la716, 1, 'PA_B')
        self.set(self.la716, 2, 'SB_D')
        self.set(self.la716, 3, 'HF')
        self.set(self.la12x, 1, 'PA_B')
        no_model = Amp.objects.create(project=self.project, location=self.la12x.location, name='Bare')
        self.assertEqual(2, strip_input_suffix(AmpChannel))
        self.assertEqual(['PA', 'SB', 'HF', ''],
                         [self.channel(self.la716, n).channel_setting for n in (1, 2, 3, 4)])
        self.assertEqual('PA_B', self.channel(self.la12x, 1).channel_setting)
        self.assertFalse(no_model.channels.exists())
        self.assertEqual(0, strip_input_suffix(AmpChannel))
