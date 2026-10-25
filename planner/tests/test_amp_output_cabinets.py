"""Cabinets per amp output (phase 2), the voltage rule, and who may edit the
shared AmpModel catalogue.

Run with::

    python manage.py test planner.tests.test_amp_output_cabinets \\
        --settings=audiopatch.test_settings
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from planner.models import (
    Amp, AmpChannel, AmpLocation, AmpModel, AmplifierProfile, CabinetModel,
    CabinetSection, PowerDistributionPlan, Project, ProjectMember,
)
from planner.utils.cabinet_load import (
    BELOW_MINIMUM, UNASSIGNED, format_ohms, nearest_published_load,
)
from planner.utils.pdf_exports import report_kit as kit


def seed():
    call_command('load_amp_profiles', stdout=StringIO())
    call_command('load_cabinets', stdout=StringIO())


def section(model, name=None):
    qs = CabinetSection.objects.filter(cabinet__model=model)
    return qs.get(name=name) if name else qs.get()


def staff(name):
    """Staff with the global Editor group's AmpModel permissions -- the worst
    case: only the per-project role may decide."""
    user = User.objects.create_user(name, password='pw', is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(
        content_type__app_label='planner',
        content_type__model__in=['ampmodel', 'amp', 'ampchannel']))
    return user


class Fixture(TestCase):

    def setUp(self):
        seed()
        self.owner = staff('owner')
        self.project = Project.objects.create(name='Show A', owner=self.owner)
        self.other = Project.objects.create(name='Show B', owner=staff('other_owner'))
        self.models = {}
        for name, channels in (('LA12X', 4), ('LA8', 4), ('LA4X', 4)):
            self.models[name] = AmpModel.objects.create(
                manufacturer='L-Acoustics', model_name=name, channel_count=channels)
        seed()  # links the AmpModels to their profiles
        self.la12x = self.amp(self.project, 'LA12X')

    def amp(self, project, model, name='Amp 1'):
        location = AmpLocation.objects.get_or_create(project=project, name='HL')[0]
        return Amp.objects.create(project=project, location=location,
                                  amp_model=self.models[model], name=name)

    def channel(self, amp, number=1):
        return amp.channels.get(channel_number=number)

    def assign(self, channel, sec, quantity):
        channel.cabinet_section = sec
        channel.cabinet_quantity = quantity
        channel.save()
        return AmpChannel.objects.get(pk=channel.pk)

    def join(self, user, project, role):
        ProjectMember.objects.create(user=user, project=project, role=role,
                                     invited_by=project.owner)

    def use(self, user, project=None):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = (project or self.project).pk
        session.save()


class VoltageTests(TestCase):

    def setUp(self):
        seed()
        self.la12x = AmplifierProfile.objects.get(model='LA12X')
        self.la8 = AmplifierProfile.objects.get(model='LA8')

    def test_230_v_is_the_published_figure(self):
        self.assertEqual(Decimal(1), self.la12x.voltage_factor(230)[0])

    def test_any_other_voltage_is_the_230_v_ratio(self):
        for volts, expected in ((208, '1.1058'), (240, '0.9583'), (110, '2.0909')):
            factor, source = self.la12x.voltage_factor(volts)
            self.assertEqual(Decimal(expected), factor, volts)
            self.assertEqual("derived: L-Acoustics multipliers are the 230 V ratio", source)

    def test_a_published_multiplier_wins(self):
        factor, source = self.la8.voltage_factor(120)
        self.assertEqual(Decimal('2.0'), factor)
        self.assertIn('LA8 user manual', source)
        self.assertEqual(Decimal('1.15'), self.la12x.voltage_factor(200)[0])

    def test_nonsense_voltage_is_refused(self):
        with self.assertRaises(ValueError):
            self.la12x.voltage_factor(0)

    def test_plan_default_is_208_v(self):
        self.assertEqual(208, PowerDistributionPlan().get_voltage())


class LoadMathTests(TestCase):

    def test_format(self):
        self.assertEqual(['2.67', '4', '2.7', '5.33', '16'],
                         [format_ohms(Decimal(v)) for v in
                          ('2.6667', '4.00', '2.70', '5.3333', '16')])

    def test_nearest_is_on_a_log_scale_and_a_tie_goes_low(self):
        loads = [Decimal('2.7'), Decimal(4), Decimal(8)]
        self.assertEqual(Decimal('2.7'), nearest_published_load(Decimal(8) / 3, loads))
        # 5.33 is 1.33 from 4 and 2.67 from 8 -- and nearer 4 on a log scale too.
        self.assertEqual(Decimal(4), nearest_published_load(Decimal(16) / 3, loads))
        # 5.9 is linearly nearer 4 (1.9 vs 2.1) but logarithmically nearer 8.
        self.assertEqual(Decimal(8), nearest_published_load(Decimal('5.9'), loads))
        # 4 sits exactly between 2 and 8 on a log scale: the lower wins.
        self.assertEqual(Decimal(2), nearest_published_load(Decimal(4), [Decimal(8), Decimal(2)]))
        self.assertIsNone(nearest_published_load(Decimal(4), []))


class OutputLoadTests(Fixture):

    def test_spec_example(self):
        ch = self.assign(self.channel(self.la12x), section('Kara II', 'LF'), 3)
        load = ch.cabinet_load
        self.assertEqual('Kara II · LF ×3 → 2.67 Ω (2.7 Ω)', load.label)
        self.assertEqual('', load.warning)   # 8/3 counts as the 2.7 ohm minimum

    def test_bracket_left_out_when_it_repeats_the_load(self):
        ch = self.assign(self.channel(self.la12x), section('Kara II', 'HF'), 2)
        self.assertEqual('Kara II · HF ×2 → 4 Ω', ch.cabinet_load.label)

    def test_single_section_cabinet_label(self):
        ch = self.assign(self.channel(self.la12x), section('KS28'), 1)
        self.assertEqual('KS28 ×1 → 4 Ω', ch.cabinet_load.label)

    def test_below_the_minimum(self):
        ch = self.assign(self.channel(self.la12x), section('KS28'), 2)
        load = ch.cabinet_load
        self.assertEqual(BELOW_MINIMUM, load.warning)
        self.assertEqual('Below 2.7 Ω minimum', load.warning_text)
        self.assertEqual('KS28 ×2 → 2 Ω (2.7 Ω)', load.label)

    def test_la8_snaps_2_67_to_its_lowest_published_column(self):
        amp = self.amp(self.project, 'LA8', 'LA8-1')
        ch = self.assign(self.channel(amp), section('Kara II', 'LF'), 3)
        self.assertEqual('Kara II · LF ×3 → 2.67 Ω (4 Ω)', ch.cabinet_load.label)
        self.assertEqual('', ch.cabinet_load.warning)

    def test_la4x_minimum_is_4_ohm_and_its_table_has_no_columns(self):
        amp = self.amp(self.project, 'LA4X', 'LA4X-1')
        ch = self.assign(self.channel(amp), section('Kara II', 'LF'), 3)
        self.assertEqual('Kara II · LF ×3 → 2.67 Ω', ch.cabinet_load.label)
        self.assertEqual(BELOW_MINIMUM, ch.cabinet_load.warning)
        ok = self.assign(self.channel(amp, 2), section('Kara II', 'LF'), 2)
        self.assertEqual('', ok.cabinet_load.warning)

    def test_nothing_assigned(self):
        load = self.channel(self.la12x).cabinet_load
        self.assertEqual(UNASSIGNED, load.warning)
        self.assertEqual('No cabinet', load.warning_text)
        self.assertEqual('', load.label)

    def test_amp_model_without_a_profile_shows_the_load_only(self):
        AmpModel.objects.filter(pk=self.models['LA12X'].pk).update(power_profile=None)
        ch = self.assign(self.channel(self.la12x), section('KS28'), 3)
        self.assertEqual('KS28 ×3 → 1.33 Ω', ch.cabinet_load.label)
        self.assertEqual('', ch.cabinet_load.warning)

    def test_minimum_loads_are_seeded_with_a_source(self):
        mins = {p.model: p.min_load_ohms for p in AmplifierProfile.objects.all()}
        self.assertEqual({'LA8': Decimal('2.7'), 'LA4X': Decimal(4),
                          'LA12X': Decimal('2.7'), 'LA7.16i': Decimal(4)}, mins)
        for p in AmplifierProfile.objects.all():
            self.assertIn('Preset Guide', p.min_load_source)

    def test_a_superusers_minimum_survives_a_redeploy(self):
        AmplifierProfile.objects.filter(model='LA8').update(min_load_ohms=4)
        seed()
        self.assertEqual(Decimal(4), AmplifierProfile.objects.get(model='LA8').min_load_ohms)

    def test_a_section_in_use_cannot_be_deleted(self):
        from django.db.models import ProtectedError
        self.assign(self.channel(self.la12x), section('KS28'), 1)
        with self.assertRaises(ProtectedError):
            section('KS28').delete()


class InlineUpdateTests(Fixture):

    def setUp(self):
        super().setUp()
        self.ch = self.channel(self.la12x)
        self.url = reverse('planner:amp_channel_inline_update', args=[self.ch.pk])
        self.kara_lf = section('Kara II', 'LF')

    def post(self, field, value, url=None):
        return self.client.post(url or self.url, {'field': field, 'value': value})

    def test_editor_sets_section_and_quantity(self):
        editor = staff('editor')
        self.join(editor, self.project, 'editor')
        self.use(editor)
        r = self.post('cabinet_section', self.kara_lf.pk)
        self.assertEqual(200, r.status_code, r.content)
        self.assertEqual('Kara II · LF ×1 → 8 Ω', r.json()['label'])
        r = self.post('cabinet_quantity', '3')
        self.assertEqual('Kara II · LF ×3 → 2.67 Ω (2.7 Ω)', r.json()['label'])
        self.assertEqual('', r.json()['warning'])
        self.ch.refresh_from_db()
        self.assertEqual((self.kara_lf, 3), (self.ch.cabinet_section, self.ch.cabinet_quantity))

    def test_warning_comes_back(self):
        self.use(self.owner)
        self.post('cabinet_section', section('KS28').pk)
        r = self.post('cabinet_quantity', '2')
        self.assertEqual(BELOW_MINIMUM, r.json()['warning'])
        r = self.post('cabinet_section', '')
        self.assertEqual((UNASSIGNED, 'No cabinet'),
                         (r.json()['warning'], r.json()['warning_text']))
        self.ch.refresh_from_db()
        self.assertIsNone(self.ch.cabinet_section)

    def test_viewer_is_refused(self):
        # A viewer here who edits another show: the role HERE decides.
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.join(viewer, self.other, 'editor')
        self.use(viewer)
        for field, value in (('cabinet_section', self.kara_lf.pk),
                             ('cabinet_quantity', '2'), ('channel_name', 'x')):
            self.assertEqual(403, self.post(field, value).status_code, field)
        self.ch.refresh_from_db()
        self.assertEqual((None, 1, ''), (self.ch.cabinet_section, self.ch.cabinet_quantity,
                                         self.ch.channel_name))

    def test_another_shows_channel_is_404(self):
        theirs = self.channel(self.amp(self.other, 'LA12X'))
        self.use(self.owner)
        url = reverse('planner:amp_channel_inline_update', args=[theirs.pk])
        self.assertEqual(404, self.post('cabinet_section', self.kara_lf.pk, url).status_code)

    def test_bad_values_are_refused(self):
        self.use(self.owner)
        CabinetModel.objects.filter(model='K1').update(is_active=False)
        for field, value in (('cabinet_section', section('K1', 'LF').pk),
                             ('cabinet_section', '999999'), ('cabinet_section', 'x'),
                             ('cabinet_quantity', '0'), ('cabinet_quantity', '25'),
                             ('cabinet_quantity', 'two')):
            self.assertEqual(400, self.post(field, value).status_code, (field, value))
        self.ch.refresh_from_db()
        self.assertEqual((None, 1), (self.ch.cabinet_section, self.ch.cabinet_quantity))


class RackViewTests(Fixture):

    def setUp(self):
        super().setUp()
        self.assign(self.channel(self.la12x), section('Kara II', 'LF'), 3)
        self.assign(self.channel(self.la12x, 2), section('KS28'), 2)
        self.url = reverse('admin:planner_amp_changelist')

    def test_editor_gets_the_picker_with_summary_and_chips(self):
        self.use(self.owner)
        page = self.client.get(self.url)
        self.assertContains(page, 'data-field="cabinet_section"', count=4)
        self.assertContains(page, 'data-field="cabinet_quantity"', count=4)
        self.assertContains(page, 'Kara II · LF ×3 → 2.67 Ω (2.7 Ω)')
        self.assertContains(page, 'Below 2.7 Ω minimum')
        self.assertContains(page, 'No cabinet', count=2)
        kara_lf = section('Kara II', 'LF')
        self.assertContains(page, f'<option value="{kara_lf.pk}" selected>Kara II · LF</option>',
                            html=True)

    def test_viewer_reads_but_gets_no_controls(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        page = self.client.get(self.url)
        self.assertEqual(200, page.status_code)
        self.assertNotContains(page, 'data-field="cabinet_section"')
        self.assertNotContains(page, 'data-field="cabinet_quantity"')
        self.assertContains(page, 'Kara II · LF ×3 → 2.67 Ω (2.7 Ω)')

    def test_a_retired_cabinet_stays_selected(self):
        CabinetModel.objects.filter(model='KS28').update(is_active=False)
        self.use(self.owner)
        page = self.client.get(self.url)
        self.assertContains(page, 'KS28 (retired)')

    def test_query_count_does_not_grow_with_amps(self):
        self.use(self.owner)
        self.client.get(self.url)  # warm caches (session, content types)
        base = self._count()
        for n in range(5):
            amp = self.amp(self.project, 'LA12X', f'More {n}')
            self.assign(self.channel(amp), section('Kara II', 'LF'), 2)
        self.assertEqual(base, self._count())

    def _count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.url)
        return len(ctx.captured_queries)


class SheetTests(Fixture):

    def setUp(self):
        super().setUp()
        self.assign(self.channel(self.la12x), section('Kara II', 'LF'), 3)
        self.assign(self.channel(self.la12x, 2), section('KS28'), 2)

    def cell_texts(self):
        amp = Amp.objects.prefetch_related('channels').get(pk=self.la12x.pk)
        channels = sorted(amp.channels.all(), key=lambda c: c.channel_number)
        _title, table = kit.amp_cabinets_table(channels)
        return [cell.text for row in table._cellvalues for cell in row if cell]

    def test_pdf_cells(self):
        texts = self.cell_texts()
        self.assertEqual(4, len(texts))
        self.assertIn('Kara II · LF ×3 → 2.67 Ω (2.7 Ω)', texts[0])
        self.assertNotIn('minimum', texts[0])
        self.assertIn('Below 2.7 Ω minimum', texts[1])
        self.assertIn('No cabinet', texts[2])

    def test_amp_pdf_and_system_report_build(self):
        from planner.utils.pdf_exports.amplifier_pdf import export_all_amps_pdf
        r = export_all_amps_pdf(self.project)
        self.assertEqual('application/pdf', r['Content-Type'])
        self.assertTrue(r.content.startswith(b'%PDF'))
        from planner.utils.pdf_exports.system_report import _section_amplifiers
        from planner.utils.pdf_exports.report_kit import styles
        story = _section_amplifiers(self.project, styles(), Amp)
        self.assertTrue(story)


class DuplicateTests(Fixture):

    def test_duplicate_copies_cabinets(self):
        self.assign(self.channel(self.la12x), section('Kara II', 'LF'), 3)
        copy = self.project.duplicate(new_name='Copy')
        ch = AmpChannel.objects.get(amp__project=copy, channel_number=1)
        self.assertEqual((section('Kara II', 'LF'), 3), (ch.cabinet_section, ch.cabinet_quantity))
        self.assertEqual(1, AmpChannel.objects.get(amp__project=copy, channel_number=2)
                         .cabinet_quantity)


class AmpModelCatalogueTests(Fixture):
    """Adding stays open to owners/editors; editing and deleting are
    superuser-only (the Source Hardware rule from #125)."""

    def setUp(self):
        super().setUp()
        # Show B's amps use this model; the editor is on show A only.
        self.shared = AmpModel.objects.create(manufacturer='Powersoft', model_name='X8',
                                              channel_count=8)
        location = AmpLocation.objects.create(project=self.other, name='SR')
        Amp.objects.create(project=self.other, location=location, amp_model=self.shared,
                           name='B amp')
        self.editor = staff('editor')
        self.join(self.editor, self.project, 'editor')
        self.change = reverse('admin:planner_ampmodel_change', args=[self.shared.pk])
        self.delete = reverse('admin:planner_ampmodel_delete', args=[self.shared.pk])
        self.add = reverse('admin:planner_ampmodel_add')

    def form(self, **overrides):
        data = {'manufacturer': 'Powersoft', 'model_name': 'X8', 'channel_count': 8,
                'nl4_connector_count': 0, 'nl8_connector_count': 0,
                'cacom_output_count': 0, 'sc32_connector_count': 0,
                'has_analog_inputs': 'on'}
        data.update(overrides)
        return data

    def test_editor_on_a_cannot_change_a_model_used_on_b(self):
        self.use(self.editor)
        self.assertEqual(200, self.client.get(self.change).status_code)   # read-only view
        r = self.client.post(self.change, self.form(model_name='PWNED', channel_count=2))
        self.assertEqual(403, r.status_code)
        self.assertEqual(403, self.client.post(self.delete, {'post': 'yes'}).status_code)
        self.shared.refresh_from_db()
        self.assertEqual(('X8', 8), (self.shared.model_name, self.shared.channel_count))

    def test_owner_and_editor_can_add(self):
        for user in (self.owner, self.editor):
            with self.subTest(user=user.username):
                self.use(user)
                name = f'{user.username} amp'
                r = self.client.post(self.add, self.form(model_name=name))
                self.assertEqual(302, r.status_code, r.content[:2000])
                self.assertTrue(AmpModel.objects.filter(model_name=name).exists())

    def test_viewer_cannot_add(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.join(viewer, self.other, 'editor')
        self.use(viewer)
        self.assertEqual(403, self.client.get(self.add).status_code)

    def test_superuser_can_change_and_delete(self):
        root = User.objects.create_superuser('root', 'root@example.com', 'pw')
        self.use(root)
        unused = AmpModel.objects.create(manufacturer='Lab', model_name='Spare',
                                         channel_count=2)
        r = self.client.post(self.change, self.form(model_name='X8 v2'))
        self.assertEqual(302, r.status_code)
        self.shared.refresh_from_db()
        self.assertEqual('X8 v2', self.shared.model_name)
        r = self.client.post(reverse('admin:planner_ampmodel_delete', args=[unused.pk]),
                             {'post': 'yes'})
        self.assertEqual(302, r.status_code)
        self.assertFalse(AmpModel.objects.filter(pk=unused.pk).exists())


class CabinetSaveAgreementTests(Fixture):
    """Charlie's #129 test: the quantity box read 3 while the summary still
    said ×2. The page now sends section and quantity together, and the reply
    echoes what was stored, so the two can't disagree."""

    def setUp(self):
        super().setUp()
        self.ch = self.channel(self.la12x, 2)
        self.url = reverse('planner:amp_channel_inline_update', args=[self.ch.pk])
        self.kara_hf = section('Kara II', 'HF')
        self.use(self.owner)

    def save(self, sec, quantity):
        return self.client.post(self.url, {
            'field': 'cabinet', 'cabinet_section': sec, 'cabinet_quantity': quantity})

    def test_both_fields_save_together_and_are_echoed(self):
        r = self.save(self.kara_hf.pk, '3')
        self.assertEqual(200, r.status_code, r.content)
        body = r.json()
        self.assertEqual((self.kara_hf.pk, 3), (body['cabinet_section'], body['cabinet_quantity']))
        self.assertEqual('Kara II · HF ×3 → 2.67 Ω (2.7 Ω)', body['label'])
        self.ch.refresh_from_db()
        self.assertEqual((self.kara_hf, 3), (self.ch.cabinet_section, self.ch.cabinet_quantity))

    def test_the_summary_after_a_reload_matches_the_box(self):
        self.save(self.kara_hf.pk, '3')
        page = self.client.get(reverse('admin:planner_amp_changelist')).content.decode()
        self.assertIn('Kara II · HF ×3 → 2.67 Ω (2.7 Ω)', page)
        self.assertIn('value="3"\n                                       data-saved="3"', page)

    def test_a_single_field_reply_reads_the_other_field_from_the_database(self):
        # The old race: a quantity save that loaded the row before a section
        # save landed described the old section. The reply is now re-read.
        self.save(self.kara_hf.pk, '2')
        AmpChannel.objects.filter(pk=self.ch.pk).update(cabinet_quantity=3)
        r = self.client.post(self.url, {'field': 'cabinet_section', 'value': self.kara_hf.pk})
        self.assertEqual('Kara II · HF ×3 → 2.67 Ω (2.7 Ω)', r.json()['label'])

    def test_a_bad_quantity_saves_neither_field(self):
        r = self.save(self.kara_hf.pk, '0')
        self.assertEqual(400, r.status_code)
        self.ch.refresh_from_db()
        self.assertEqual((None, 1), (self.ch.cabinet_section, self.ch.cabinet_quantity))

    def test_resending_a_retired_section_the_output_already_has_is_fine(self):
        self.save(self.kara_hf.pk, '1')
        CabinetModel.objects.filter(model='Kara II').update(is_active=False)
        r = self.save(self.kara_hf.pk, '2')
        self.assertEqual(200, r.status_code, r.content)
        other = section('K2', 'LF')
        CabinetModel.objects.filter(model='K2').update(is_active=False)
        self.assertEqual(400, self.save(other.pk, '2').status_code)

    def test_viewer_is_refused(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.use(viewer)
        self.assertEqual(403, self.save(self.kara_hf.pk, '3').status_code)

    def test_fields_opt_out_of_browser_form_restore(self):
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertContains(page, '<select class="amp-cabinet-select" autocomplete="off"', count=4)
        self.assertContains(page, 'autocomplete="off"\n                                       min="1" max="24"',
                            count=4)


class CabinetStripLabelTests(Fixture):

    def setUp(self):
        super().setUp()
        self.url = reverse('admin:planner_amp_changelist')
        self.use(self.owner)

    def test_heading_and_help_link(self):
        page = self.client.get(self.url)
        self.assertContains(page, 'Cabinets per output — used for the power estimate')
        self.assertContains(page, reverse('help:topic', args=['power-amp-profiles']))

    def test_model_without_power_figures_says_so(self):
        page = self.client.get(self.url)
        self.assertNotContains(page, 'No power figures for this model')
        bare = AmpModel.objects.create(manufacturer='Powersoft', model_name='X4', channel_count=4)
        location = AmpLocation.objects.get(project=self.project, name='HL')
        Amp.objects.create(project=self.project, location=location, amp_model=bare, name='PS')
        page = self.client.get(self.url)
        self.assertContains(page, 'No power figures for this model', count=1)

    def test_picker_is_grouped_under_headings(self):
        page = self.client.get(self.url).content.decode()
        headings = ['Line source', 'Constant curvature', 'Coaxial', 'Colinear', 'Subwoofer']
        positions = [page.index(f'<optgroup label="{h}">') for h in headings]
        self.assertEqual(sorted(positions), positions)
        line = page[positions[0]:positions[1]]
        for label in ('Kara · LF', 'Kara · HF', 'Kiva', 'Kara II · LF'):
            self.assertIn(f'>{label}</option>', line)
        subs = page[positions[4]:page.index('</optgroup>', positions[4])]
        self.assertIn('>KS28</option>', subs)
        self.assertIn('>K1-SB</option>', subs)


class LegacyCabinetTests(TestCase):

    def setUp(self):
        seed()

    def test_kara_and_kiva_are_seeded_with_their_source(self):
        kara = CabinetModel.objects.get(model='Kara')
        self.assertEqual([('LF', Decimal('8.0')), ('HF', Decimal('8.0'))],
                         [(s.name, s.nominal_impedance_ohms) for s in kara.sections.all()])
        self.assertIn('p.57', kara.source)
        kiva = CabinetModel.objects.get(model='Kiva')
        self.assertEqual([('Full range', Decimal('8.0'))],
                         [(s.name, s.nominal_impedance_ohms) for s in kiva.sections.all()])
        self.assertIn('p.59', kiva.source)
        self.assertIn('p.118', kiva.source)
        self.assertEqual(CabinetModel.LINE_SOURCE, kiva.category)

    def test_every_seeded_cabinet_has_a_heading(self):
        self.assertFalse(CabinetModel.objects.filter(category='').exists())

    def test_headings_fill_old_rows_but_keep_a_superusers_choice(self):
        CabinetModel.objects.filter(model='KS28').update(category='')
        CabinetModel.objects.filter(model='Syva').update(category=CabinetModel.LINE_SOURCE)
        seed()
        self.assertEqual(CabinetModel.SUBWOOFER, CabinetModel.objects.get(model='KS28').category)
        self.assertEqual(CabinetModel.LINE_SOURCE, CabinetModel.objects.get(model='Syva').category)


class AmpModelDuplicateTests(Fixture):
    """Adding "LA LA12X" when "L-Acoustics LA12X" exists offers the existing
    row instead."""

    def setUp(self):
        super().setUp()
        self.add = reverse('admin:planner_ampmodel_add')
        self.use(self.owner)

    def form(self, manufacturer, model_name):
        return {'manufacturer': manufacturer, 'model_name': model_name, 'channel_count': 4,
                'nl4_connector_count': 0, 'nl8_connector_count': 0,
                'cacom_output_count': 0, 'sc32_connector_count': 0,
                'has_analog_inputs': 'on'}

    def test_spelling_variants_are_one_model(self):
        from planner.utils.amp_models import model_key
        key = model_key('L-Acoustics', 'LA12X')
        for variant in (('LA', 'LA12X'), ('l acoustics', 'la-12x'), ("L'Acoustics", 'LA 12X'),
                        ('Lacoustics', 'la12x')):
            self.assertEqual(key, model_key(*variant), variant)
        self.assertNotEqual(key, model_key('L-Acoustics', 'LA12'))
        self.assertNotEqual(key, model_key('Powersoft', 'LA12X'))

    def test_add_offers_the_existing_model(self):
        before = AmpModel.objects.count()
        r = self.client.post(self.add, self.form('LA', 'la-12x'))
        self.assertEqual(200, r.status_code)
        self.assertEqual(before, AmpModel.objects.count())
        existing = self.models['LA12X']
        self.assertContains(r, 'already in the catalogue as <strong>L-Acoustics LA12X</strong>')
        self.assertContains(r, reverse('admin:planner_ampmodel_change', args=[existing.pk]))

    def test_the_popup_offer_picks_the_existing_model_in_the_amp_form(self):
        r = self.client.post(self.add + '?_popup=1', dict(self.form('LA', 'LA12X'), _popup='1'))
        existing = self.models['LA12X']
        use = reverse('admin:planner_ampmodel_use_existing', args=[existing.pk])
        self.assertContains(r, use)
        r = self.client.get(use)
        self.assertEqual(200, r.status_code)
        self.assertContains(r, f'<script id="use-existing-value" type="application/json">{existing.pk}</script>',
                            html=False)

    def test_a_new_model_still_adds(self):
        r = self.client.post(self.add, self.form('L-Acoustics', 'LA2Xi'))
        self.assertEqual(302, r.status_code)
        self.assertTrue(AmpModel.objects.filter(model_name='LA2Xi').exists())


class MergeAmpModelsTests(TestCase):

    def setUp(self):
        seed()
        self.owner = User.objects.create_user('o')
        self.project = Project.objects.create(name='Show', owner=self.owner)
        self.location = AmpLocation.objects.create(project=self.project, name='HL')
        full = dict(channel_count=4, has_aes_inputs=True, has_avb_inputs=True,
                    nl4_connector_count=2, cacom_output_count=1)
        self.linked = AmpModel.objects.create(manufacturer='L-Acoustics', model_name='LA12X', **full)
        seed()  # links it to the LA12X profile
        self.linked.refresh_from_db()
        self.copy = AmpModel.objects.create(manufacturer='L-Acoustics', model_name='LA12X',
                                            channel_count=4)
        self.abbrev = AmpModel.objects.create(manufacturer='LA', model_name='LA12X', channel_count=4)
        # More amps on the unlinked copies than on the linked row: the
        # profile still decides the survivor.
        self.amps = [self.amp(self.copy, 'A'), self.amp(self.copy, 'B'), self.amp(self.abbrev, 'C')]
        self.solo = AmpModel.objects.create(manufacturer='Powersoft', model_name='X8', channel_count=8)

    def amp(self, model, name):
        return Amp.objects.create(project=self.project, location=self.location,
                                  amp_model=model, name=name)

    def run_command(self, *args):
        out = StringIO()
        call_command('merge_amp_models', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_lists_the_group_and_writes_nothing(self):
        self.assertIsNotNone(self.linked.power_profile_id)
        out = self.run_command()
        self.assertIn('DRY RUN', out)
        self.assertIn(f'keep    #{self.linked.pk} "L-Acoustics LA12X"', out)
        self.assertIn(f'merge   #{self.copy.pk}', out)
        self.assertIn(f'merge   #{self.abbrev.pk} "LA LA12X"', out)
        self.assertIn('3 amps move, 2 rows deleted', out)
        self.assertNotIn('X8', out)
        self.assertEqual(4, AmpModel.objects.count())
        self.assertEqual(2, Amp.objects.filter(amp_model=self.copy).count())

    def test_apply_moves_the_amps_then_deletes_the_extras(self):
        out = self.run_command('--apply')
        self.assertIn('3 amps moved, 2 rows deleted', out)
        self.assertEqual({self.linked.pk, self.solo.pk}, set(AmpModel.objects.values_list('pk', flat=True)))
        for amp in self.amps:
            amp.refresh_from_db()
            self.assertEqual(self.linked.pk, amp.amp_model_id)
            self.assertEqual(4, amp.channels.count())
        self.assertIn('No duplicate amp models', self.run_command())

    def test_a_group_that_would_lose_outputs_is_skipped(self):
        AmpModel.objects.filter(pk=self.abbrev.pk).update(sc32_connector_count=1)
        out = self.run_command('--apply')
        self.assertIn('SKIPPED', out)
        self.assertIn('sc32 connector count', out)
        self.assertEqual(4, AmpModel.objects.count())

    def test_a_different_channel_count_is_skipped(self):
        AmpModel.objects.filter(pk=self.copy.pk).update(channel_count=8)
        out = self.run_command('--apply')
        self.assertIn('SKIPPED', out)
        self.assertEqual(4, AmpModel.objects.count())
