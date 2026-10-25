"""The per-output routing tag (PA/LF/HF/SB + slot A-D) moved from the
"Ch 1-4" block in the middle of the amp card into each output's cell, next
to its cabinet, with the zone pre-filled from the cabinet section.

Run with::

    python manage.py test planner.tests.test_amp_routing_tag \\
        --settings=audiopatch.test_settings
"""

from django.urls import reverse

from planner.models import AmpChannel, CabinetSection
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
                    if isinstance(cell, (list, tuple)):
                        stack.extend(cell)
                    elif isinstance(cell, Table):
                        stack.append(cell)
                    else:
                        texts.append(getattr(cell, 'text', cell))
        elif isinstance(f, (list, tuple)):
            stack.extend(f)
    return [str(t) for t in texts]


class ZoneFromSectionTests(Fixture):

    def test_section_zones(self):
        self.assertEqual('LF', section('Kara II', 'LF').routing_zone)
        self.assertEqual('HF', section('Kara II', 'HF').routing_zone)
        self.assertEqual('SB', section('KS28').routing_zone)
        self.assertEqual('PA', section('Kiva').routing_zone)      # passive full range
        self.assertEqual('', section('K1', 'MF').routing_zone)    # no zone of its own
        self.assertEqual('', section('L2 / L2D', 'LC').routing_zone)

    def test_tag_parts_and_suggestion(self):
        ch = self.assign(self.channel(self.la12x), section('Kara II', 'LF'), 2)
        self.assertEqual(('', '', 'LF'), (ch.routing_zone, ch.routing_slot, ch.suggested_routing_zone))
        ch.channel_setting = 'HF_C'
        self.assertEqual(('HF', 'C', ''), (ch.routing_zone, ch.routing_slot, ch.suggested_routing_zone))
        bare = self.channel(self.la12x, 2)
        self.assertEqual('', bare.suggested_routing_zone)


class RackCardTests(Fixture):

    def setUp(self):
        super().setUp()
        self.url = reverse('admin:planner_amp_changelist')
        # Out 1: tagged before this PR, cabinet assigned since: tag kept.
        ch1 = self.assign(self.channel(self.la12x, 1), section('Kara II', 'LF'), 3)
        AmpChannel.objects.filter(pk=ch1.pk).update(channel_setting='HF_B')
        # Out 2: cabinet, no tag: zone suggested.
        self.assign(self.channel(self.la12x, 2), section('KS28'), 1)
        # Out 3: MF section: nothing to suggest. Out 4: nothing at all.
        self.assign(self.channel(self.la12x, 3), section('K1', 'MF'), 1)
        self.use(self.owner)

    def page(self):
        return self.client.get(self.url).content.decode()

    def tag_html(self, page, n):
        cells = page.split('<div class="amp-cabinet-cell"')[1:]
        cell = cells[n - 1]
        return cell[cell.index('<div class="amp-tag"'):cell.index('</div>', cell.index('amp-tag-hint'))]

    def test_old_ch_block_is_gone(self):
        page = self.page()
        self.assertNotIn('amp-channel-setting', page)
        self.assertNotIn('data-field="channel_setting"', page)
        self.assertEqual(4, page.count('<div class="amp-tag"'))

    def test_existing_tag_is_kept_over_the_section(self):
        tag = self.tag_html(self.page(), 1)
        self.assertIn('data-saved="HF_B"', tag)
        self.assertIn('<option value="HF" selected>', tag)
        self.assertNotIn('<option value="LF" selected>', tag)
        self.assertIn('<option value="B" selected>', tag)
        self.assertIn('amp-tag-hint" hidden', tag)

    def test_zone_is_prefilled_from_the_section_but_not_saved(self):
        tag = self.tag_html(self.page(), 2)
        self.assertIn('data-saved=""', tag)
        self.assertIn('<option value="SB" selected>', tag)
        self.assertNotIn('selected>A<', tag)
        self.assertNotIn('amp-tag-hint" hidden', tag)        # "pick a slot"
        self.assertEqual('', AmpChannel.objects.get(pk=self.channel(self.la12x, 2).pk).channel_setting)

    def test_no_suggestion_without_a_zone(self):
        for n in (3, 4):
            tag = self.tag_html(self.page(), n)
            self.assertNotIn('" selected>', tag, n)
            self.assertIn('amp-tag-hint" hidden', tag)

    def test_section_options_carry_their_zone(self):
        page = self.page()
        kara_lf = section('Kara II', 'LF')
        self.assertIn(f'<option value="{kara_lf.pk}" data-zone="LF"', page)
        self.assertIn(f'<option value="{section("K1", "MF").pk}" data-zone=""', page)

    def test_viewer_sees_the_tag_as_text(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        page = self.page()
        self.assertNotIn('<div class="amp-tag"', page)
        self.assertIn('Tag HF_B', page)
        self.assertEqual(1, page.count('class="amp-tag-text"'))


class TagSaveTests(Fixture):

    def setUp(self):
        super().setUp()
        self.ch = self.channel(self.la12x)
        self.url = reverse('planner:amp_channel_inline_update', args=[self.ch.pk])

    def post(self, value):
        return self.client.post(self.url, {'field': 'channel_setting', 'value': value})

    def test_whole_tags_save_and_blank_clears(self):
        self.use(self.owner)
        self.assertEqual(200, self.post('LF_B').status_code)
        self.ch.refresh_from_db()
        self.assertEqual('LF_B', self.ch.channel_setting)
        self.assertEqual(200, self.post('').status_code)
        self.ch.refresh_from_db()
        self.assertEqual('', self.ch.channel_setting)

    def test_half_or_unknown_tags_are_refused(self):
        self.use(self.owner)
        for value in ('LF_', '_B', 'LF', 'XX_A', 'LF_E', 'lf_b'):
            self.assertEqual(400, self.post(value).status_code, value)
        self.ch.refresh_from_db()
        self.assertEqual('', self.ch.channel_setting)

    def test_viewer_is_refused(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        self.assertEqual(403, self.post('LF_B').status_code)


class TagStillPrintsTests(Fixture):

    def test_amp_pdf_and_system_report_print_the_tag(self):
        AmpChannel.objects.filter(pk=self.channel(self.la12x, 2).pk).update(channel_setting='SB_D')
        channels = sorted(self.la12x.channels.all(), key=lambda c: c.channel_number)
        from planner.utils.pdf_exports import report_kit, system_report
        for module in (report_kit, system_report):
            texts = table_texts(module._amp_middle(self.la12x, channels))
            self.assertIn('SB_D', texts, module.__name__)
            self.assertIn('2', texts, module.__name__)


class TagMismatchTests(Fixture):
    """A stored tag whose zone isn't the cabinet's gets an amber chip; the
    tag itself is never changed."""

    def setUp(self):
        super().setUp()
        self.ch = self.assign(self.channel(self.la12x), section('Kara II', 'HF'), 1)
        AmpChannel.objects.filter(pk=self.ch.pk).update(channel_setting='LF_B')
        self.ch.refresh_from_db()
        self.url = reverse('admin:planner_amp_changelist')

    def test_when_it_is_reported(self):
        self.assertEqual('tag says LF, cabinet is HF', self.ch.routing_mismatch)
        self.ch.cabinet_section = section('Kara II', 'LF')
        self.assertEqual('', self.ch.routing_mismatch)            # agrees
        self.ch.cabinet_section = section('K1', 'MF')
        self.assertEqual('', self.ch.routing_mismatch)            # MF implies nothing
        self.ch.cabinet_section = None
        self.assertEqual('', self.ch.routing_mismatch)            # no cabinet
        self.ch.cabinet_section = section('Kiva')
        self.assertEqual('tag says LF, cabinet is PA', self.ch.routing_mismatch)
        self.ch.channel_setting = ''
        self.assertEqual('', self.ch.routing_mismatch)            # no tag

    def test_chip_in_the_cell_and_the_tag_is_left_alone(self):
        self.use(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertIn('<span class="amp-cabinet-chip amp-tag-mismatch">tag says LF, cabinet is HF</span>',
                      page)
        self.assertEqual(3, page.count('<span class="amp-cabinet-chip amp-tag-mismatch" hidden>'))
        self.ch.refresh_from_db()
        self.assertEqual('LF_B', self.ch.channel_setting)

    def test_viewer_sees_the_chip_too(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        self.assertContains(self.client.get(self.url), 'tag says LF, cabinet is HF')

    def test_a_cabinet_change_keeps_the_tag(self):
        self.use(self.owner)
        url = reverse('planner:amp_channel_inline_update', args=[self.ch.pk])
        self.client.post(url, {'field': 'cabinet', 'cabinet_section': section('KS28').pk,
                               'cabinet_quantity': '1'})
        self.ch.refresh_from_db()
        self.assertEqual('LF_B', self.ch.channel_setting)
        self.assertEqual('tag says LF, cabinet is SB', self.ch.routing_mismatch)

    def test_pdf_row_carries_it_in_amber(self):
        from planner.utils.pdf_exports import report_kit as kit
        channels = sorted(self.la12x.channels.all(), key=lambda c: c.channel_number)
        _title, table = kit.amp_cabinets_table(channels)
        first = table._cellvalues[0][0].text
        self.assertIn('Kara II · HF ×1', first)
        self.assertIn('tag says LF, cabinet is HF', first)
        cell_xml = table._cellvalues[0][0].frags  # rendered fragments carry the colour
        amber = [f for f in cell_xml if 'tag says' in f.text]
        self.assertTrue(amber)
        self.assertEqual(kit.AMP_WARN.hexval(), amber[0].textColor.hexval())
        for row in table._cellvalues:
            for cell in row[1:] if row is table._cellvalues[0] else row:
                if cell:
                    self.assertNotIn('tag says', cell.text)

    def test_system_report_card_builds_with_it(self):
        from planner.utils.pdf_exports.report_kit import styles
        from planner.utils.pdf_exports.system_report import _section_amplifiers
        from planner.models import Amp
        self.assertTrue(_section_amplifiers(self.project, styles(), Amp))
