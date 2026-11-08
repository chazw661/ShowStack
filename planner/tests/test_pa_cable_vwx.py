"""Import from VWX: the Vectorworks cable worksheet into the PA Cable Schedule.

Run with::

    python manage.py test planner.tests.test_pa_cable_vwx \\
        --settings=audiopatch.test_settings
"""
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from planner.models import (PACableSchedule, PACoupler, PAFanOut, PAFanOutExtension, PAZone, Project,
                            ProjectMember, UserProfile)
from planner.utils import pa_cable_math, pa_cable_vwx as vwx
from planner.utils.pdf_exports.pa_cable_pdf import _quick_order_rows

FIXTURE = Path(__file__).parent / 'fixtures' / 'pa_cable_vwx_export.csv'
HEADER = 'Cable Label,Destination,Connector,Fan-Out,Length (ft),Extension Of\n'


class ParseTests(SimpleTestCase):

    def fixture_rows(self):
        return vwx.parse(vwx.decode(FIXTURE.read_bytes())).rows

    def test_the_fixture_is_the_real_cr_only_export(self):
        raw = FIXTURE.read_bytes()
        self.assertIn(b'\r', raw)
        self.assertNotIn(b'\n', raw)

    def test_the_summary_and_trailing_rows_are_dropped(self):
        rows = self.fixture_rows()
        self.assertEqual([r.label for r in rows], ['KARA 3', 'SUB SL Main Run', 'Sub', 'X8 1'])
        self.assertEqual(rows[0].connector, 'CA-COM 8 pin speaker')
        self.assertEqual(rows[2].extension_of, 'SUB SL Main Run')
        self.assertEqual(rows[1].line, 4)

    def test_a_cable_labelled_with_a_number_is_not_the_summary_row(self):
        rows = vwx.parse(HEADER + '4,2,4,2,135.1,2\n4,SL,SC32,,20,\n').rows
        self.assertEqual([(r.label, r.connector) for r in rows], [('4', 'SC32')])

    def test_columns_match_by_name_in_any_order_and_case(self):
        rows = vwx.parse(' length (FT) ,CONNECTOR,cable label,Fan-Out,Destination\n30,SC32,HL,,Rack\n').rows
        self.assertEqual((rows[0].label, rows[0].connector, rows[0].length, rows[0].destination),
                         ('HL', 'SC32', '30', 'Rack'))

    def test_extension_of_is_optional(self):
        parsed = vwx.parse('Cable Label,Destination,Connector,Fan-Out,Length (ft)\nHL,R,SC32,,30\n')
        self.assertFalse(parsed.has_extension_column)
        self.assertTrue(vwx.parse(HEADER + 'HL,R,SC32,,30,\n').has_extension_column)

    def test_crlf_lf_and_bom(self):
        for text in (HEADER.replace('\n', '\r\n') + 'HL,R,SC32,,30,\r\n', '﻿'.encode().decode() + HEADER + 'HL,R,SC32,,30,\n'):
            self.assertEqual(vwx.parse(vwx.decode(text.encode())).rows[0].label, 'HL')

    def test_macroman_text_survives(self):
        raw = (HEADER + 'HL,Café,SC32,,30,\n').encode('mac_roman')
        self.assertEqual(vwx.parse(vwx.decode(raw)).rows[0].destination, 'Café')

    def test_binary_is_refused(self):
        with self.assertRaises(vwx.VwxFileError):
            vwx.decode(b'PK\x03\x04\x00\x00')

    def test_other_csvs_are_refused(self):
        with self.assertRaisesMessage(vwx.VwxFileError, 'Missing column'):
            vwx.parse('name,email\nA,b\n')

    def test_a_file_with_no_cables_is_refused(self):
        with self.assertRaisesMessage(vwx.VwxFileError, 'no cable rows'):
            vwx.parse(HEADER + '4,2,4,2,135.1,2\n,,,,,\n')

    def test_the_row_cap(self):
        rows = ''.join('L{},R,SC32,,30,\n'.format(i) for i in range(vwx.MAX_ROWS + 1))
        with self.assertRaisesMessage(vwx.VwxFileError, 'more than'):
            vwx.parse(HEADER + rows)

    def test_the_size_cap(self):
        upload = SimpleUploadedFile('big.csv', b'x' * (vwx.MAX_BYTES + 1))
        with self.assertRaisesMessage(vwx.VwxFileError, '2 MB'):
            vwx.read_upload(upload)


class MappingTests(SimpleTestCase):

    def test_every_connector(self):
        for name, code in (('Speaker Twist 4', 'NL_4'), ('SpeakerTwist4', 'NL_4'),
                           ('Speaker Twist 8', 'NL_8'), ('SpeakerTwist8', 'NL_8'),
                           ('CA-COM 8 pin speaker', 'CA-COM'), ('CACOM-8', 'CA-COM'),
                           ('SC32', 'SC32'), ('  speaker twist 4 ', 'NL_4')):
            self.assertEqual(vwx.connector_cable(name), code, name)
            self.assertTrue(pa_cable_math.is_known_cable_type(code))

    def test_an_unknown_connector(self):
        self.assertIsNone(vwx.connector_cable('Speakon 2'))

    def test_every_fan_out_and_the_alias(self):
        for name, code in (('NL4 Y', 'NL4_Y'), ('NL4 to 2XNL2', 'NL4_TO_2XNL2'), ('NL8 Y', 'NL8_Y'),
                           ('NL8 to 2XNL4', 'NL4_TO_NL8'), ('NL8 to 4XNL2', 'NL8_TO_4XNL2'),
                           ('DOFill', 'DOFILL'), ('DOSub', 'DOSUB'), ('dosub', 'DOSUB'),
                           ('SUB Cable', 'NL8_TO_4XNL2')):
            self.assertEqual(vwx.fan_out_code(name), code, name)

    def test_an_unknown_fan_out(self):
        self.assertIsNone(vwx.fan_out_code('Octopus'))

    def test_length_rounds_up_to_whole_feet(self):
        for value, feet in (('76.1', 77), ('36.5', 37), ('50.2', 51), ('50', 50), ('.5', 1)):
            self.assertEqual(vwx.whole_feet(value), feet, value)

    def test_things_that_are_not_lengths(self):
        for value in ('', '0', '-5', 'abc', 'NaN', '1e3', "12'", '5001'):
            self.assertIsNone(vwx.whole_feet(value), value)

    def test_extension_stock_rounds_up(self):
        for feet, stock in ((7.6, 25), (25, 25), (25.1, 50), (50.5, 100), (100.1, 150), (150, 150), (150.1, None)):
            self.assertEqual(vwx.stock_length(feet), stock, feet)


class Base(TestCase):

    URL = '/audiopatch/pa-cables/import-vwx/'
    CONFIRM = '/audiopatch/pa-cables/import-vwx/confirm/'

    def setUp(self):
        self.owner = User.objects.create_user('vwx_owner', password='pw', is_staff=True)
        UserProfile.objects.update_or_create(user=self.owner, defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='VWX', owner=self.owner)
        self.login(self.owner, self.project)

    def login(self, user, project):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = project.pk
        session.save()

    def upload(self, body, name='plot.csv'):
        if isinstance(body, str):
            body = body.encode()
        return self.client.post(self.URL, {'csv_file': SimpleUploadedFile(name, body, content_type='text/csv')})

    def preview(self, body, name='plot.csv'):
        response = self.upload(body, name)
        self.assertEqual(response.status_code, 200)
        return response.context['plan']

    def confirm(self, body, name='plot.csv'):
        response = self.upload(body, name)
        return self.client.post(self.CONFIRM, {
            'csv_text': response.context['csv_text'], 'filename': name, 'digest': response.context['digest'],
        }, follow=True)

    def messages(self, response):
        return ' '.join(str(m) for m in response.context['messages'])

    def entry(self, label):
        return PACableSchedule.objects.get(project=self.project, label__name=label)

    def hand_entry(self, label, *, fan='DOSUB', mode='text', cable='NL_4', length=10, destination='Hand'):
        zone, _ = PAZone.objects.get_or_create(project=self.project, name=label)
        entry = PACableSchedule.objects.create(project=self.project, label=zone, cable=cable, length=length,
                                               destination=destination, entry_mode=mode, count=3,
                                               notes='keep', drawing_ref='hand')
        return entry, PAFanOut.objects.create(cable_schedule=entry, fan_out_type=fan, quantity=2) if fan else None


class PreviewAndWriteTests(Base):

    def test_preview_writes_nothing(self):
        for model in (PACableSchedule, PAZone, PAFanOut, PAFanOutExtension):
            before = model.objects.count()
            self.upload(FIXTURE.read_bytes())
            self.assertEqual(model.objects.count(), before, model.__name__)

    def test_the_real_export_end_to_end(self):
        response = self.confirm(FIXTURE.read_bytes(), 'ShowStack Cable Export.csv')
        self.assertIn('2 created, 0 updated, 0 skipped, 2 extensions set', self.messages(response))

        kara = self.entry('KARA 3')
        self.assertEqual((kara.cable, kara.length, kara.destination, kara.count, kara.drawing_ref),
                         ('CA-COM', 77, 'SR Rack IP 01', 1, 'ShowStack Cable Export.csv'))
        self.assertEqual([(f.fan_out_type, f.quantity) for f in kara.fan_outs.all()], [('DOSUB', 1)])
        self.assertFalse(kara.fan_out_extensions.exists())

        sub = self.entry('SUB SL Main Run')
        self.assertEqual(sub.length, 37)
        extensions = list(sub.fan_out_extensions.all())
        self.assertEqual([(e.extension_cable, e.extension_length, e.quantity) for e in extensions], [('NL4', 25, 2)])
        self.assertEqual(extensions[0].fan_out, sub.fan_outs.get())
        self.assertEqual(sorted(z.name for z in PAZone.objects.filter(project=self.project)),
                         ['KARA 3', 'SUB SL Main Run'])

    def test_new_zones_take_the_same_defaults_as_the_plus_button(self):
        self.confirm(HEADER + 'HL,R,SC32,,30,\n')
        zone = PAZone.objects.get(project=self.project, name='HL')
        self.assertEqual((zone.zone_type, zone.sort_order), ('CUSTOM', 100))

    def test_quick_order_matches_extensions_entered_by_hand(self):
        self.confirm(HEADER + 'HL,R,Speaker Twist 4,NL4 Y,60,\n'
                              'a,,Speaker Twist 4,,20,HL\nb,,Speaker Twist 4,,24.5,HL\n')
        imported = _quick_order_rows(PACableSchedule.objects.filter(project=self.project))

        other = Project.objects.create(name='By hand', owner=self.owner)
        zone = PAZone.objects.create(project=other, name='HL')
        entry = PACableSchedule.objects.create(project=other, label=zone, cable='NL_4', length=60, destination='R')
        fan = PAFanOut.objects.create(cable_schedule=entry, fan_out_type='NL4_Y', quantity=1)
        PAFanOutExtension.objects.create(cable_schedule=entry, fan_out=fan, extension_cable='NL4',
                                         extension_length=25, quantity=2)
        self.assertEqual(imported, _quick_order_rows(PACableSchedule.objects.filter(project=other)))

    def test_errors_are_skipped_and_the_rest_import(self):
        response = self.confirm(HEADER + 'HL,R,SC32,,30,\nHR,R,Banana,,30,\n,R,SC32,,30,\n')
        self.assertIn('1 created, 0 updated, 2 skipped', self.messages(response))
        self.assertEqual(PACableSchedule.objects.filter(project=self.project).count(), 1)

    def test_a_blank_destination_is_a_warning_and_still_imports(self):
        plan = self.preview(HEADER + 'HL,,SC32,,30,\n')
        self.assertEqual(plan.runs[0].status, 'new')
        self.assertIn('No Destination', plan.runs[0].warnings[0])

    def test_a_long_label_is_an_error_not_truncated(self):
        plan = self.preview(HEADER + '{},R,SC32,,30,\n'.format('L' * 21))
        self.assertIn('20 characters', plan.runs[0].errors[0])

    def test_a_long_destination_is_an_error(self):
        plan = self.preview(HEADER + 'HL,{},SC32,,30,\n'.format('D' * 51))
        self.assertIn('50 characters', plan.runs[0].errors[0])

    def test_duplicate_labels_flag_every_copy_and_import_none(self):
        response = self.confirm(HEADER + 'HL,R,SC32,,30,\nHL,R,SC32,,40,\nHR,R,SC32,,30,\n')
        self.assertIn('1 created, 0 updated, 2 skipped', self.messages(response))
        self.assertFalse(PACableSchedule.objects.filter(project=self.project, label__name='HL').exists())


class ReimportTests(Base):

    def test_reimport_updates_in_place(self):
        entry, fan = self.hand_entry('HL', fan='NL4_Y')
        response = self.confirm(HEADER + 'HL,New Rack,Speaker Twist 8,DOSub,88.2,\n')
        self.assertIn('0 created, 1 updated, 0 skipped', self.messages(response))
        entry.refresh_from_db()
        fan.refresh_from_db()
        self.assertEqual((entry.cable, entry.length, entry.destination), ('NL_8', 89, 'New Rack'))
        self.assertEqual((fan.fan_out_type, fan.quantity), ('DOSUB', 1))
        self.assertEqual((entry.count, entry.notes, entry.drawing_ref), (3, 'keep', 'hand'))

    def test_entries_not_in_the_file_are_never_deleted(self):
        self.hand_entry('Other')
        self.confirm(HEADER + 'HL,R,SC32,,30,\n')
        self.assertTrue(PACableSchedule.objects.filter(project=self.project, label__name='Other').exists())

    def test_couplers_are_not_touched(self):
        entry, _ = self.hand_entry('HL')
        PACoupler.objects.create(cable_schedule=entry, coupler_type='NL4_COUPLER', quantity=2)
        self.confirm(HEADER + 'HL,R,Speaker Twist 4,DOSub,30,\n')
        self.assertEqual(entry.couplers.get().quantity, 2)

    def test_blank_fields_keep_the_existing_values_and_warn(self):
        entry, fan = self.hand_entry('HL')
        plan = self.preview(HEADER + 'HL,,Speaker Twist 4,,30,\n')
        self.assertEqual(plan.runs[0].status, 'update')
        self.assertIn('Keeps "Hand"', ' '.join(plan.runs[0].warnings))
        self.assertIn('Keeps DOSub', ' '.join(plan.runs[0].warnings))
        self.confirm(HEADER + 'HL,,Speaker Twist 4,,30,\n')
        entry.refresh_from_db()
        fan.refresh_from_db()
        self.assertEqual(entry.destination, 'Hand')
        self.assertEqual(fan.fan_out_type, 'DOSUB')

    def test_a_label_on_two_entries_is_refused(self):
        self.hand_entry('HL')
        self.hand_entry('HL')
        plan = self.preview(HEADER + 'HL,R,SC32,,30,\n')
        self.assertIn('2 entries', plan.runs[0].errors[0])

    def test_a_soundvision_linked_entry_is_refused(self):
        self.hand_entry('HL', mode='linked')
        plan = self.preview(HEADER + 'HL,R,SC32,,30,\n')
        self.assertIn('Soundvision', plan.runs[0].errors[0])

    def test_an_entry_with_two_fan_outs_is_refused(self):
        entry, _ = self.hand_entry('HL')
        PAFanOut.objects.create(cable_schedule=entry, fan_out_type='NL4_Y', quantity=1)
        plan = self.preview(HEADER + 'HL,R,SC32,DOSub,30,\n')
        self.assertIn('2 fan-outs', plan.runs[0].errors[0])


class ExtensionTests(Base):

    RUN = 'HL,R,Speaker Twist 4,NL4 Y,30,\n'

    def extension(self, entry_fan, length=50, cable='NL8', quantity=1):
        entry, fan = entry_fan
        return PAFanOutExtension.objects.create(cable_schedule=entry, fan_out=fan, extension_cable=cable,
                                                extension_length=length, quantity=quantity)

    def rows(self, label='HL'):
        return [(e.extension_cable, e.extension_length, e.quantity)
                for e in self.entry(label).fan_out_extensions.order_by('id')]

    def test_identical_extensions_group_and_different_ones_do_not(self):
        self.confirm(HEADER + self.RUN + 'a,,Speaker Twist 4,,10,HL\nb,,Speaker Twist 4,,20,HL\n'
                                         'c,,Speaker Twist 4,,30,HL\nd,,SpeakerTwist8,,10,HL\n')
        self.assertEqual(sorted(self.rows()), [('NL4', 25, 2), ('NL4', 50, 1), ('NL8', 25, 1)])

    def test_the_extension_rows_own_label_is_not_a_run(self):
        self.confirm(HEADER + self.RUN + 'Sub,,Speaker Twist 4,,10,HL\n')
        self.assertFalse(PAZone.objects.filter(project=self.project, name='Sub').exists())

    def test_extension_connector_must_be_nl4_or_nl8(self):
        plan = self.preview(HEADER + self.RUN + 'a,,SC32,,10,HL\n')
        self.assertIn('NL4 or NL8', plan.runs[0].extensions[0].error)

    def test_longer_than_the_longest_stock_is_an_error(self):
        plan = self.preview(HEADER + self.RUN + 'a,,Speaker Twist 4,,150.5,HL\n')
        self.assertIn('longest', plan.runs[0].extensions[0].error)

    def test_an_unknown_parent_is_an_error(self):
        plan = self.preview(HEADER + self.RUN + 'a,,Speaker Twist 4,,10,Nope\n')
        self.assertIn('No run labelled', plan.orphans[0].error)
        self.assertEqual(plan.skipped, 1)

    def test_a_parent_with_no_fan_out_is_an_error(self):
        plan = self.preview(HEADER + 'HL,R,Speaker Twist 4,,30,\na,,Speaker Twist 4,,10,HL\n')
        self.assertIn('no fan-out', plan.runs[0].extensions[0].error)

    def test_a_parent_row_with_an_error_fails_its_extensions(self):
        plan = self.preview(HEADER + 'HL,R,Banana,NL4 Y,30,\na,,Speaker Twist 4,,10,HL\n')
        self.assertIn('error', plan.runs[0].extensions[0].error)

    def test_a_parent_only_in_the_project(self):
        pair = self.hand_entry('HL')
        self.confirm(HEADER + 'a,,Speaker Twist 4,,10,HL\n')
        self.assertEqual(self.rows(), [('NL4', 25, 1)])
        entry = pair[0]
        entry.refresh_from_db()
        self.assertEqual((entry.cable, entry.length, entry.destination), ('NL_4', 10, 'Hand'))

    def test_the_file_replaces_the_fan_outs_extensions_and_the_preview_says_so(self):
        pair = self.hand_entry('HL', fan='NL4_Y')
        self.extension(pair)
        body = HEADER + self.RUN + 'a,,Speaker Twist 4,,10,HL\n'
        self.assertIn("Replaces extensions on this fan-out: NL8 50' x1", ' '.join(self.preview(body).runs[0].warnings))
        self.confirm(body)
        self.assertEqual(self.rows(), [('NL4', 25, 1)])

    def test_a_run_in_the_file_with_no_extension_rows_clears_them(self):
        self.extension(self.hand_entry('HL', fan='NL4_Y'))
        self.confirm(HEADER + self.RUN)
        self.assertEqual(self.rows(), [])

    def test_an_older_export_leaves_extensions_alone(self):
        self.extension(self.hand_entry('HL', fan='NL4_Y'))
        self.confirm('Cable Label,Destination,Connector,Fan-Out,Length (ft)\nHL,R,Speaker Twist 4,NL4 Y,30\n')
        self.assertEqual(self.rows(), [('NL8', 50, 1)])

    def test_a_blank_fan_out_with_no_extension_rows_leaves_extensions_alone(self):
        self.extension(self.hand_entry('HL'))
        self.confirm(HEADER + 'HL,R,Speaker Twist 4,,30,\n')
        self.assertEqual(self.rows(), [('NL8', 50, 1)])

    def test_a_failed_extension_row_leaves_stored_extensions_alone(self):
        self.extension(self.hand_entry('HL', fan='NL4_Y'))
        body = HEADER + self.RUN + 'a,,Speaker Twist 4,,10,HL\nb,,SC32,,10,HL\n'
        self.assertIn('left as they are', ' '.join(self.preview(body).runs[0].warnings))
        self.confirm(body)
        self.assertEqual(self.rows(), [('NL8', 50, 1)])


class ConfirmTests(Base):

    BODY = HEADER + 'HL,R,SC32,,30,\n'

    def form(self):
        response = self.upload(self.BODY)
        return {'csv_text': response.context['csv_text'], 'filename': 'plot.csv', 'digest': response.context['digest']}

    def test_a_changed_project_is_refused(self):
        form = self.form()
        self.hand_entry('HL')
        response = self.client.post(self.CONFIRM, form, follow=True)
        self.assertIn('nothing was imported', self.messages(response))
        self.assertEqual(self.entry('HL').cable, 'NL_4')

    def test_a_double_submit_is_refused(self):
        form = self.form()
        self.client.post(self.CONFIRM, form)
        response = self.client.post(self.CONFIRM, form, follow=True)
        self.assertIn('nothing was imported', self.messages(response))
        self.assertEqual(PACableSchedule.objects.filter(project=self.project).count(), 1)

    def test_switching_project_after_the_preview_is_refused(self):
        form = self.form()
        other = Project.objects.create(name='Other', owner=self.owner)
        self.login(self.owner, other)
        self.client.post(self.CONFIRM, form)
        self.assertFalse(PACableSchedule.objects.filter(project=other).exists())

    def test_edited_text_is_refused(self):
        form = self.form()
        form['csv_text'] = form['csv_text'].replace('30', '99')
        self.client.post(self.CONFIRM, form)
        self.assertFalse(PACableSchedule.objects.filter(project=self.project).exists())


class PermissionAndPageTests(Base):

    def make_member(self, role):
        user = User.objects.create_user('vwx_' + role, password='pw', is_staff=True)
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'paid'})
        ProjectMember.objects.create(project=self.project, user=user, role=role, invited_by=self.owner)
        self.login(user, self.project)

    def schedule(self):
        return self.client.get(reverse('admin:planner_pacableschedule_changelist')).content.decode()

    def test_a_viewer_gets_403_everywhere(self):
        self.make_member('viewer')
        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.assertEqual(self.upload(FIXTURE.read_bytes()).status_code, 403)
        self.assertEqual(self.client.post(self.CONFIRM, {}).status_code, 403)

    def test_a_viewer_does_not_see_the_button(self):
        self.make_member('viewer')
        self.assertNotIn('Import from VWX', self.schedule())

    def test_owners_and_editors_see_the_button(self):
        self.assertIn('Import from VWX', self.schedule())
        self.make_member('editor')
        self.assertIn('Import from VWX', self.schedule())

    def test_an_editor_can_import(self):
        self.make_member('editor')
        self.confirm(HEADER + 'HL,R,SC32,,30,\n')
        self.assertTrue(PACableSchedule.objects.filter(project=self.project).exists())

    def test_a_non_csv_is_turned_away_politely(self):
        response = self.client.post(self.URL, {'csv_file': SimpleUploadedFile('x.xlsx', b'PK\x03\x04\x00')}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('not a CSV', self.messages(response))

    def test_file_text_is_escaped_in_the_preview(self):
        name = '<script>alert(1)</script>'
        for body in (HEADER + '{0},{0},{0},{0},{0},\n'.format(name), HEADER + 'a,,{0},,10,{0}\n'.format(name)):
            html = self.upload(body, 'a.csv').content.decode()
            self.assertNotIn(name, html)
            self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)

    def test_the_file_name_is_escaped_in_the_preview(self):
        html = self.upload(HEADER + 'HL,R,SC32,,30,\n', '"><img src=x onerror=alert(1)>.csv').content.decode()
        self.assertNotIn('<img src=x', html)
