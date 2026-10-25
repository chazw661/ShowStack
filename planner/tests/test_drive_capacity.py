"""Drive capacity per amp model and cabinet (Preset Guide v25.0 pp.119-120).

Run with::

    python manage.py test planner.tests.test_drive_capacity \\
        --settings=audiopatch.test_settings
"""

import re
from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from planner.management.commands.load_amp_profiles import (
    MIN_LOADS, SUPERSEDED_MIN_LOAD_SOURCES,
)
from planner.models import Amp, AmpModel, AmplifierProfile, CabinetDriveCapacity
from planner.tests.test_amp_output_cabinets import Fixture, section
from planner.utils.cabinet_load import (
    BELOW_MINIMUM, NOT_DRIVEN, OVER_PER_OUTPUT, amp_drive_note, amp_drive_warnings,
)
from planner.utils.pdf_exports import report_kit as kit


def load_drive_capacity(*args):
    out = StringIO()
    call_command('load_drive_capacity', *args, stdout=out)
    return out.getvalue()


def offered(page, sec):
    """How many cabinet pickers on the page list ``sec``. Counted inside the
    pickers only: other selects on the rack page share the id numbers."""
    pickers = re.findall(r'<select class="amp-cabinet-select".*?</select>', page, re.S)
    return sum(f'<option value="{sec.pk}"' in p for p in pickers)


def cell(amp, cabinet):
    return CabinetDriveCapacity.objects.get(profile__model=amp, cabinet__model=cabinet)


class DriveFixture(Fixture):

    def setUp(self):
        super().setUp()
        load_drive_capacity()
        self.la4x = self.amp(self.project, 'LA4X', 'Amp 2')
        self.la8 = self.amp(self.project, 'LA8', 'Amp 3')

    def fetch(self, amp):
        # Fixture's AmpModel instances predate the profile link; read fresh.
        return Amp.objects.select_related('amp_model__power_profile').prefetch_related(
            'channels__cabinet_section__cabinet',
            'amp_model__power_profile__drive_capacities').get(pk=amp.pk)

    def channels(self, amp):
        return sorted(self.fetch(amp).channels.all(), key=lambda c: c.channel_number)

    def totals(self, amp):
        return amp_drive_warnings(self.fetch(amp).amp_model.power_profile, self.channels(amp))


class SeedTests(DriveFixture):

    def test_every_catalogue_cabinet_on_each_amp_in_the_table(self):
        # 31 catalogue cabinets x LA4X, LA7.16i, LA12X from v25.0, plus the
        # 26 the v22.0 LA8 table lists (not X6i, X8i, Soka, L2, SB6i).
        self.assertEqual(93, CabinetDriveCapacity.objects.exclude(profile__model='LA8').count())
        la8 = CabinetDriveCapacity.objects.filter(profile__model='LA8')
        self.assertEqual(26, la8.count())
        self.assertFalse(la8.filter(cabinet__model__in=[
            'X6i', 'X8i', 'Soka', 'L2 / L2D', 'SB6i']).exists())

    def test_la8_cells_from_v22(self):
        for cabinet, expected in (
            ('Kara II', (3, 6)), ('K2', (3, 3)), ('Kiva II', (4, 16)),
            ('X8', (3, 8)), ('K3', (2, 4)), ('SB28', (1, 4)),
            ('KS28', (None, None)), ('Syva Low', (1, 4)),
        ):
            row = cell('LA8', cabinet)
            self.assertEqual(expected, (row.per_output, row.per_amp), cabinet)
        self.assertIn('v22.0, p.110', cell('LA8', 'Kara II').source)
        self.assertIn('v22.0, p.111', cell('LA8', 'KS21').source)
        self.assertTrue(cell('LA8', 'X8').note.startswith('a:'))
        self.assertTrue(cell('LA8', 'SB15m').note.startswith('d:'))

    def test_cells_as_printed(self):
        for amp, cabinet, expected in (
            ('LA12X', 'Kara II', (3, 6)),
            ('LA12X', 'K2', (3, 3)),
            ('LA12X', 'X4i', (6, 24)),
            ('LA7.16i', 'X4i', (4, 64)),
            ('LA7.16i', 'X12', (1, 14)),
            ('LA7.16i', 'L2 / L2D', (1, 1)),
            ('LA4X', 'K2', (1, 1)),
            ('LA4X', 'KS28', (None, None)),
            ('LA7.16i', 'Kara', (None, None)),
            ('LA12X', 'L2 / L2D', (None, None)),
        ):
            row = cell(amp, cabinet)
            self.assertEqual(expected, (row.per_output, row.per_amp), (amp, cabinet))

    def test_guide_row_page_and_footnotes(self):
        kiva = cell('LA12X', 'Kiva')
        self.assertEqual(('Kiva / Kilo', 3, 12), (kiva.guide_row, kiva.per_output, kiva.per_amp))
        self.assertIn('v25.0, p.120', kiva.source)
        self.assertIn('v25.0, p.119', cell('LA12X', 'X8').source)
        self.assertTrue(cell('LA12X', 'Syva Low').note.startswith('c:'))
        self.assertEqual('', cell('LA4X', 'Syva Low').note)
        self.assertTrue(cell('LA7.16i', 'X8').note.startswith('b:'))

    def test_rerun_keeps_edits_and_force_resets_them(self):
        CabinetDriveCapacity.objects.filter(pk=cell('LA12X', 'KS28').pk).update(per_output=2)
        self.assertIn('0 created, 0 reset', load_drive_capacity())
        self.assertEqual(2, cell('LA12X', 'KS28').per_output)
        load_drive_capacity('--force')
        self.assertEqual(1, cell('LA12X', 'KS28').per_output)

    def test_reports_rows_outside_the_catalogue(self):
        out = load_drive_capacity()
        self.assertIn('Not in the cabinet catalogue: 8XT', out)
        self.assertIn('dV-SUB', out)

    def test_la8_minimum_load_citation_is_corrected_value_kept(self):
        AmplifierProfile.objects.filter(model='LA8').update(
            min_load_source=SUPERSEDED_MIN_LOAD_SOURCES['LA8'])
        call_command('load_amp_profiles', stdout=StringIO())
        la8 = AmplifierProfile.objects.get(model='LA8')
        self.assertEqual(MIN_LOADS['LA8'][1], la8.min_load_source)
        self.assertIn('v22.0 pp.110-111', la8.min_load_source)
        self.assertEqual('2.70', f'{la8.min_load_ohms:.2f}')


class OutputWarningTests(DriveFixture):

    def test_over_per_output(self):
        ch = self.assign(self.channel(self.la12x), section('Kara II', 'LF'), 4)
        self.assertEqual((OVER_PER_OUTPUT, 'Over 3 per output'),
                         (ch.cabinet_load.warning, ch.cabinet_load.warning_text))
        ch = self.assign(ch, section('Kara II', 'LF'), 3)
        self.assertEqual('', ch.cabinet_load.warning)

    def test_not_driven(self):
        ch = self.assign(self.channel(self.la4x), section('KS28'), 1)
        self.assertEqual((NOT_DRIVEN, 'LA4X does not drive this'),
                         (ch.cabinet_load.warning, ch.cabinet_load.warning_text))

    def test_table_overrides_minimum_for_paralleled_4_ohm(self):
        # Two Syva Low (4 ohm) is 2 ohm, under the LA12X's 2.7 minimum, but
        # the table allows two per output (p.120, and p.118's exception):
        # no minimum-load warning, and no note either.
        ch = self.assign(self.channel(self.la12x), section('Syva Low'), 2)
        self.assertEqual(('', ''), (ch.cabinet_load.warning, ch.cabinet_load.note))
        self.assertLess(ch.cabinet_load.ohms, ch.cabinet_load.min_ohms)
        ch = self.assign(ch, section('Syva Low'), 3)
        self.assertEqual(OVER_PER_OUTPUT, ch.cabinet_load.warning)
        # SB6i likewise: 2 per output on an LA12X.
        ch = self.assign(ch, section('SB6i'), 2)
        self.assertEqual('', ch.cabinet_load.warning)

    def test_la8_uses_its_v22_column(self):
        ch = self.assign(self.channel(self.la8), section('KS28'), 1)
        self.assertEqual(NOT_DRIVEN, ch.cabinet_load.warning)
        ch = self.assign(ch, section('Kara II', 'LF'), 4)
        self.assertEqual('Over 3 per output', ch.cabinet_load.warning_text)

    def test_cabinet_without_a_cell_is_impedance_only_and_says_so(self):
        # SB6i is not in the v22.0 LA8 table. Two of them (2 ohm) are under
        # the LA8's 2.7 minimum; one is not.
        ch = self.assign(self.channel(self.la8), section('SB6i'), 2)
        load = ch.cabinet_load
        self.assertEqual(BELOW_MINIMUM, load.warning)
        self.assertEqual('No published drive limit for LA8, impedance check only', load.note)
        ch = self.assign(ch, section('SB6i'), 1)
        self.assertEqual('', ch.cabinet_load.warning)
        self.assertTrue(ch.cabinet_load.note)

    def test_amp_with_no_table_at_all(self):
        CabinetDriveCapacity.objects.filter(profile__model='LA8').delete()
        ch = self.assign(self.channel(self.la8), section('KS28'), 2)
        self.assertEqual(BELOW_MINIMUM, ch.cabinet_load.warning)
        self.assertTrue(ch.cabinet_load.no_drive_limit)


class AmpTotalTests(DriveFixture):

    def test_passive_counts_every_output(self):
        for n in (1, 2, 3, 4):
            self.assign(self.channel(self.la4x, n), section('X8'), 2)
        self.assertEqual([], self.totals(self.la4x))  # 8, max 8
        self.assign(self.channel(self.la4x, 4), section('X12'), 1)
        self.assign(self.channel(self.la4x, 3), section('X12'), 1)
        self.assertEqual([], self.totals(self.la4x))
        for n in (1, 2, 3, 4):
            self.assign(self.channel(self.la4x, n), section('X12'), 1)
        self.assertEqual([], self.totals(self.la4x))  # 4, max 4
        self.assign(self.channel(self.la4x, 4), section('X12'), 2)
        self.assertEqual(['X12: 5 on this amp, max 4'], self.totals(self.la4x))

    def test_active_counts_enclosures_not_sections(self):
        # LF x2, HF x2, LF x2, HF x2 on an LA4X: four Kara II, max 4.
        for n, name in ((1, 'LF'), (2, 'HF'), (3, 'LF'), (4, 'HF')):
            self.assign(self.channel(self.la4x, n), section('Kara II', name), 2)
        self.assertEqual([], self.totals(self.la4x))
        # Three LF outputs: six Kara II.
        self.assign(self.channel(self.la4x, 2), section('Kara II', 'LF'), 2)
        self.assertEqual(['Kara II: 6 on this amp, max 4'], self.totals(self.la4x))

    def test_k2_three_per_la12x(self):
        for n, name in ((1, 'LF'), (2, 'MF'), (3, 'HF')):
            self.assign(self.channel(self.la12x, n), section('K2', name), 3)
        self.assertEqual([], self.totals(self.la12x))

    def test_no_profile_no_totals(self):
        self.assertEqual([], amp_drive_warnings(None, self.channels(self.la12x)))


class EndpointTests(DriveFixture):

    def post(self, channel, sec, quantity=1):
        url = reverse('planner:amp_channel_inline_update', args=[channel.pk])
        return self.client.post(url, {'field': 'cabinet', 'cabinet_section': sec,
                                      'cabinet_quantity': quantity})

    def test_a_cabinet_the_amp_does_not_drive_is_refused(self):
        self.use(self.owner)
        ch = self.channel(self.la4x)
        r = self.post(ch, section('KS28').pk)
        self.assertEqual(400, r.status_code)
        self.assertEqual('LA4X does not drive KS28', r.json()['error'])
        ch.refresh_from_db()
        self.assertIsNone(ch.cabinet_section)

    def test_an_existing_assignment_can_be_resent(self):
        # Set before the table, or before the amp model changed.
        self.use(self.owner)
        ch = self.assign(self.channel(self.la4x), section('KS28'), 1)
        r = self.post(ch, section('KS28').pk, 1)
        self.assertEqual(200, r.status_code, r.content)
        self.assertEqual(NOT_DRIVEN, r.json()['warning'])

    def test_reply_carries_the_impedance_only_note(self):
        self.use(self.owner)
        r = self.post(self.channel(self.la8), section('SB6i').pk, 1)
        self.assertEqual('No published drive limit for LA8, impedance check only', r.json()['note'])
        r = self.post(self.channel(self.la8), section('Kara II', 'LF').pk, 3)
        self.assertEqual('', r.json()['note'])

    def test_reply_carries_the_amp_totals(self):
        self.use(self.owner)
        for n in (1, 2, 3):
            self.assign(self.channel(self.la4x, n), section('Kara II', 'LF'), 2)
        r = self.post(self.channel(self.la4x, 4), section('Kara II', 'HF').pk, 2)
        self.assertEqual(['Kara II: 6 on this amp, max 4'], r.json()['drive_warnings'])
        r = self.post(self.channel(self.la4x, 4), '', 1)
        self.assertEqual(['Kara II: 6 on this amp, max 4'], r.json()['drive_warnings'])
        r = self.post(self.channel(self.la4x, 3), section('Kara II', 'HF').pk, 2)
        self.assertEqual([], r.json()['drive_warnings'])


class RackPickerTests(DriveFixture):

    def page(self):
        self.use(self.owner)
        return self.client.get(reverse('admin:planner_amp_changelist'))

    def test_picker_lists_only_cabinets_the_amp_drives(self):
        page = self.page().content.decode()
        # KS28 on the LA12X's 4 outputs only: not on the LA4X (v25.0) or
        # the LA8 (v22.0).
        self.assertEqual(4, offered(page, section('KS28')))
        self.assertEqual(12, offered(page, section('Kara II', 'LF')))
        # Not in the LA8 table: offered, with the impedance-only note.
        self.assertEqual(12, offered(page, section('SB6i')))

    def test_impedance_only_note_on_the_output(self):
        self.assign(self.channel(self.la8), section('SB6i'), 1)
        self.assertContains(self.page(),
                            'No published drive limit for LA8, impedance check only', count=1)

    def test_amp_with_no_table_says_so_once_in_the_heading(self):
        CabinetDriveCapacity.objects.filter(profile__model='LA8').delete()
        self.assign(self.channel(self.la8), section('KS28'), 1)
        page = self.page()
        self.assertContains(page, 'No published drive limits for LA8, impedance check only', count=1)
        self.assertNotContains(page, 'No published drive limit for LA8,')

    def test_unlisted_assignment_stays_selected(self):
        self.assign(self.channel(self.la4x), section('KS28'), 1)
        page = self.page()
        self.assertContains(page, 'KS28 (not driven by LA4X)')
        self.assertContains(page, 'LA4X does not drive this')

    def test_totals_line(self):
        for n in (1, 2, 3):
            self.assign(self.channel(self.la4x, n), section('Kara II', 'LF'), 2)
        self.assertContains(self.page(), 'Kara II: 6 on this amp, max 4')


class PdfTests(DriveFixture):

    def test_totals_row_and_red_output_warnings(self):
        for n in (1, 2, 3):
            self.assign(self.channel(self.la4x, n), section('Kara II', 'LF'), 2)
        self.assign(self.channel(self.la4x, 4), section('KS28'), 1)
        amp = self.fetch(self.la4x)
        channels = sorted(amp.channels.all(), key=lambda c: c.channel_number)
        _title, table = kit.amp_cabinets_table(channels, amp)
        texts = [c.text for row in table._cellvalues for c in row if c]
        self.assertIn('LA4X does not drive this', texts[3])
        self.assertIn('Kara II: 6 on this amp, max 4', texts[4])

    def test_pdfs_build(self):
        from planner.utils.pdf_exports.amplifier_pdf import export_all_amps_pdf
        self.assign(self.channel(self.la12x), section('Kara II', 'LF'), 4)
        r = export_all_amps_pdf(self.project)
        self.assertTrue(r.content.startswith(b'%PDF'))


class UncheckedAmpTests(DriveFixture):
    """An amp the drive table can't check at all says so: no power profile,
    or a profile with no drive rows. Drive capacity hangs off the profile,
    not the AmpModel name."""

    def setUp(self):
        super().setUp()
        self.models['Test Amp'] = AmpModel.objects.create(
            manufacturer='Acme', model_name='Test Amp', channel_count=4)
        self.test_amp = self.amp(self.project, 'Test Amp', 'Amp 9')
        self.assign(self.channel(self.test_amp), section('X6i'), 1)

    def page(self):
        self.use(self.owner)
        return self.client.get(reverse('admin:planner_amp_changelist'))

    def test_no_profile(self):
        note = 'No published drive limits for Test Amp, no load check'
        self.assertEqual(note, amp_drive_note(self.fetch(self.test_amp).amp_model))
        page = self.page()
        self.assertContains(page, note, count=1)
        self.assertContains(page, 'No power figures for this model', count=1)

    def test_profile_with_rows_restricts_by_profile_not_name(self):
        AmpModel.objects.filter(pk=self.models['Test Amp'].pk).update(
            power_profile=AmplifierProfile.objects.get(model='LA4X'))
        self.assertEqual('', amp_drive_note(self.fetch(self.test_amp).amp_model))
        page = self.page().content.decode()
        self.assertNotIn('No published drive limits for', page)
        # K1 is not driven by an LA4X: not offered on the Test Amp or the
        # LA4X, only on the LA12X and the LA8 (v22.0: 2 / 2).
        self.assertEqual(8, offered(page, section('K1', 'LF')))

    def test_profile_without_rows(self):
        bare = AmplifierProfile.objects.create(
            manufacturer='Acme', model='TA-1', idle_power_watts=50, rated_power_watts=500,
            peak_power_watts=900, max_power_watts=2000)
        AmpModel.objects.filter(pk=self.models['Test Amp'].pk).update(power_profile=bare)
        model = self.fetch(self.test_amp).amp_model
        self.assertEqual('No published drive limits for TA-1, no load check', amp_drive_note(model))
        AmplifierProfile.objects.filter(pk=bare.pk).update(min_load_ohms=4)
        model = self.fetch(self.test_amp).amp_model
        self.assertEqual('No published drive limits for TA-1, impedance check only',
                         amp_drive_note(model))

    def test_pdf_says_it_once(self):
        amp = self.fetch(self.test_amp)
        channels = sorted(amp.channels.all(), key=lambda c: c.channel_number)
        _title, table = kit.amp_cabinets_table(channels, amp)
        texts = [c.text for row in table._cellvalues for c in row if c]
        joined = ' '.join(texts)
        self.assertEqual(1, joined.count('No published drive limits for Test Amp, no load check'))
