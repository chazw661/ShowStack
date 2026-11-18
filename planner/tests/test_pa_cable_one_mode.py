"""PA cable runs: one entry mode (PR 2b-1).

From an amp or an amp rack, to a typed destination, optionally linked to the
Soundvision arrays it feeds. New runs need both ends; runs saved before keep
saving as they are.

Run with::

    python manage.py test planner.tests.test_pa_cable_one_mode \\
        --settings=audiopatch.test_settings

The migration tests need real migrations, so they run only in the plain
suite (``python manage.py test planner.tests.test_pa_cable_one_mode``).
"""
import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from planner.forms import PACableInlineForm
from planner.models import (AmpLocation, PACableSchedule, PAFanOut, Project,
                            ProjectMember)
from planner.tests.connection_fixtures import ConnectionFixtures

CHANGELIST = 'admin:planner_pacableschedule_changelist'
ADD = 'admin:planner_pacableschedule_add'


class _Run(ConnectionFixtures):
    def setUp(self):
        super().setUp()
        self.user.is_superuser = self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        self.amp_a = self.amp('SL LA12X #1', rack='SL Racks')
        self.rack = self.amp_a.location

    def form(self, instance=None, **data):
        base = {'project': self.project.pk, 'count': 1, 'cable': 'NL_4', 'length': 100,
                'color': '#FFFFFF', 'notes': '', 'drawing_ref': ''}
        base.update(data)
        return PACableInlineForm(data=base, instance=instance)


class OneModeFormTests(_Run, TestCase):

    def test_a_new_run_needs_a_from(self):
        form = self.form(destination='KIVA DELAY 2 & 3')
        self.assertFalse(form.is_valid())
        self.assertIn('amp', form.errors)

    def test_an_amp_rack_alone_is_a_from(self):
        form = self.form(amp_location=self.rack.pk, destination='Sub L')
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_new_run_needs_a_to_unless_an_array_is_linked(self):
        form = self.form(amp=self.amp_a.pk)
        self.assertFalse(form.is_valid())
        self.assertIn('destination', form.errors)
        arr = self.array(self.prediction(), 'K2 L')
        form = self.form(amp=self.amp_a.pk, speaker_arrays=[arr.pk])
        self.assertTrue(form.is_valid(), form.errors)

    def test_picking_an_amp_sets_its_rack(self):
        other = AmpLocation.objects.create(project=self.project, name='Elsewhere')
        form = self.form(amp=self.amp_a.pk, amp_location=other.pk, destination='X')
        self.assertTrue(form.is_valid(), form.errors)
        row = form.save()
        self.assertEqual(row.amp_location, self.rack)

    def test_a_run_saved_before_keeps_saving_with_neither_end(self):
        row = self.text_cable(destination='')
        form = self.form(instance=row, destination='', count=3)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().count, 3)

    def test_the_form_has_no_entry_mode(self):
        self.assertNotIn('entry_mode', PACableInlineForm().fields)
        self.assertNotIn('speaker_array', PACableInlineForm().fields)


class OneModeAdminTests(_Run, TestCase):

    def test_the_add_form_shows_from_and_cable_label_and_no_mode(self):
        body = self.client.get(reverse(ADD)).content.decode()
        self.assertIn('name="source"', body)                  # one grouped From picker
        self.assertNotIn('name="amp"', body)
        self.assertNotIn('name="amp_location"', body)
        self.assertNotIn('name="entry_mode"', body)
        self.assertIn('Cable Label', body)
        self.assertIn('<optgroup label="SL Racks">', body)
        self.assertIn('SL LA12X #1 · TEST4', body)            # the amp option label
        self.assertNotIn('pa_cable_entry_mode.js', body)

    def test_linked_arrays_only_when_the_project_has_arrays(self):
        self.assertNotIn('name="speaker_arrays"', self.client.get(reverse(ADD)).content.decode())
        self.array(self.prediction(), 'K2 L')
        self.assertIn('name="speaker_arrays"', self.client.get(reverse(ADD)).content.decode())

    def test_another_projects_amp_and_arrays_are_refused(self):
        theirs = self.make_project('theirs')
        their_amp = self.amp('Theirs', project=theirs)
        their_array = self.array(self.prediction(project=theirs), 'Their K2')
        self.array(self.prediction(), 'K2 L')                 # so the field is shown
        for source in (f'amp:{their_amp.pk}', f'rack:{their_amp.location_id}'):
            response = self.client.post(reverse(ADD), self.admin_post(
                source=source, destination='X', speaker_arrays=[their_array.pk]))
            self.assertEqual(response.status_code, 200)        # the form came back
            errors = response.context['adminform'].form.errors
            self.assertIn('Select a valid choice', str(errors['source']))
            self.assertIn('speaker_arrays', errors)
        self.assertFalse(PACableSchedule.objects.filter(project=self.project).exists())

    def test_adding_through_the_admin(self):
        arr = self.array(self.prediction(), 'K2 L')
        response = self.client.post(reverse(ADD), self.admin_post(
            source=f'amp:{self.amp_a.pk}', label=self.zone('HL').pk, speaker_arrays=[arr.pk]))
        self.assertEqual(response.status_code, 302)
        row = PACableSchedule.objects.get(project=self.project)
        self.assertEqual((row.amp, row.amp_location, list(row.speaker_arrays.all())),
                         (self.amp_a, self.rack, [arr]))

    def admin_post(self, **data):
        out = {'count': 1, 'cable': 'NL_4', 'length': 100, 'color': '#FFFFFF',
               'notes': '', 'drawing_ref': '', 'destination': ''}
        for prefix in ('fan_outs', 'fan_out_extensions', 'couplers'):
            out.update({f'{prefix}-TOTAL_FORMS': 0, f'{prefix}-INITIAL_FORMS': 0})
        out.update(data)
        return out

    def test_changelist_columns_and_a_fixed_query_count(self):
        arr = self.array(self.prediction(), 'K2 L')

        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse(CHANGELIST))
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries), response

        self.linked_cable(self.amp_a, arr, label=self.zone('HL'))
        few, _ = count_queries()
        for n in range(8):
            self.linked_cable(self.amp(f'Amp {n}', rack=f'Rack {n}'), arr,
                              label=self.zone(f'Z{n}'), destination=f'Fill {n}')
        many, response = count_queries()
        self.assertEqual(few, many)
        body = response.content.decode()
        for heading in ('Cable Label', 'From', 'To', 'Arrays'):
            self.assertIn(f'>{heading}<', body.replace('</a>', '<'))

    def test_duplicate_copies_linked_arrays_and_fan_outs(self):
        arr = self.array(self.prediction(), 'K2 L')
        row = self.linked_cable(self.amp_a, arr, destination='Main L')
        PAFanOut.objects.create(cable_schedule=row, fan_out_type='NL4_Y', quantity=2)
        self.client.post(reverse(CHANGELIST), {'action': 'duplicate_cable_runs',
                                               '_selected_action': [row.pk]})
        copy = PACableSchedule.objects.exclude(pk=row.pk).get(project=self.project)
        self.assertEqual(list(copy.speaker_arrays.all()), [arr])
        self.assertEqual((copy.amp, copy.amp_location), (self.amp_a, self.rack))
        self.assertEqual(copy.fan_outs.count(), 1)

    def test_a_viewer_can_still_read_the_list(self):
        viewer = get_user_model().objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.text_cable(destination='X', amp=self.amp_a)
        self.client.force_login(viewer)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        self.assertEqual(self.client.get(reverse(CHANGELIST)).status_code, 200)


class GroupedFromPickerTests(_Run, TestCase):
    """One <optgroup> per rack: the rack itself, then its amps."""

    def picker(self, url=None):
        response = self.client.get(url or reverse(ADD))
        self.assertEqual(response.status_code, 200)
        return response, response.context['adminform'].form.fields['source'].choices

    def admin_post(self, **data):
        return OneModeAdminTests.admin_post(self, **data)

    def test_every_amp_on_the_rack_page_is_in_the_picker_in_the_same_order(self):
        AmpLocation.objects.filter(pk=self.rack.pk).update(sort_order=2)
        self.amp('SL LA12X #2', rack='SL Racks')
        self.amp('Amp 01 - Kara L - Top & Mid', rack='House Left')
        self.amp('Amp 02 - Spare', rack='House Left')
        AmpLocation.objects.filter(project=self.project, name='House Left').update(sort_order=1)
        AmpLocation.objects.create(project=self.project, name='Empty rack', sort_order=3)
        self.amp('Theirs', project=self.make_project('theirs'), rack='House Left')

        rack_page = self.client.get(reverse('admin:planner_amp_changelist')).context
        expected = [(g['location'].name, [f'rack:{g["location"].pk}']
                     + [f'amp:{a.pk}' for a in g['amps']])
                     for g in rack_page['grouped_amps']]
        _, choices = self.picker()
        self.assertEqual(choices[0], ('', '---------'))
        got = [(group, [value for value, _ in options]) for group, options in choices[1:]]
        self.assertEqual(got, expected)
        self.assertEqual([g for g, _ in got], ['House Left', 'SL Racks', 'Empty rack'])
        self.assertEqual(sum(len(v) - 1 for _, v in got), 4)   # not the other project's amp

    def test_option_labels(self):
        _, choices = self.picker()
        group, options = choices[1]
        self.assertEqual(group, 'SL Racks')
        self.assertEqual([label for _, label in options],
                         ['SL Racks \u2014 whole rack', 'SL LA12X #1 \u00b7 TEST4'])

    def test_picking_the_rack_saves_the_rack_only(self):
        response = self.client.post(reverse(ADD), self.admin_post(
            source=f'rack:{self.rack.pk}', destination='KIVA DELAY 2 & 3'))
        self.assertEqual(response.status_code, 302)
        row = PACableSchedule.objects.get(project=self.project)
        self.assertEqual((row.amp, row.amp_location), (None, self.rack))
        self.assertEqual(row.from_display, 'SL Racks')

    def test_picking_an_amp_saves_the_amp_and_its_rack(self):
        response = self.client.post(reverse(ADD), self.admin_post(
            source=f'amp:{self.amp_a.pk}', destination='KIVA DELAY 2 & 3'))
        self.assertEqual(response.status_code, 302)
        row = PACableSchedule.objects.get(project=self.project)
        self.assertEqual((row.amp, row.amp_location), (self.amp_a, self.rack))

    def test_a_new_run_needs_a_from(self):
        response = self.client.post(reverse(ADD), self.admin_post(destination='X'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Pick the amp, or the amp rack',
                      str(response.context['adminform'].form.errors['source']))

    def test_the_change_form_shows_what_the_run_has(self):
        amp_row = self.text_cable(destination='A', amp=self.amp_a)
        rack_row = self.text_cable(destination='B', amp_location=self.rack)
        old_row = self.text_cable(destination='Amp 01 typed before')
        change = 'admin:planner_pacableschedule_change'
        for row, initial in ((amp_row, f'amp:{self.amp_a.pk}'),
                             (rack_row, f'rack:{self.rack.pk}'), (old_row, None)):
            response, _ = self.picker(reverse(change, args=[row.pk]))
            self.assertEqual(response.context['adminform'].form['source'].value(), initial)

    def test_switching_an_amp_run_to_the_whole_rack_clears_the_amp(self):
        row = self.text_cable(destination='A', amp=self.amp_a)
        response = self.client.post(
            reverse('admin:planner_pacableschedule_change', args=[row.pk]),
            self.admin_post(source=f'rack:{self.rack.pk}', destination='A'))
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual((row.amp, row.amp_location), (None, self.rack))

    def test_a_viewer_reads_the_from_as_text(self):
        row = self.text_cable(destination='A', amp=self.amp_a)
        viewer = get_user_model().objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.client.force_login(viewer)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        response = self.client.get(reverse('admin:planner_pacableschedule_change', args=[row.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn('name="source"', body)
        self.assertIn('SL LA12X #1', body)


class SoundvisionReimportTests(_Run, TestCase):

    def test_a_reimport_removes_the_links_and_keeps_the_text(self):
        pred = self.prediction()
        row = self.linked_cable(self.amp_a, self.array(pred, 'K2 L'), destination='Main L')
        pred.speaker_arrays.all().delete()      # what soundvision_parser does on re-import
        row.refresh_from_db()
        self.assertEqual(list(row.speaker_arrays.all()), [])
        self.assertEqual((row.destination, row.amp), ('Main L', self.amp_a))
        row.save()


class ProjectDuplicateTests(_Run, TestCase):

    def test_amp_rack_and_arrays_are_mapped_to_the_copy(self):
        arr = self.array(self.prediction(), 'K2 L')
        self.linked_cable(self.amp_a, arr, destination='Main L')
        self.text_cable(destination='Sub', amp_location=self.rack)
        copy = self.project.duplicate(new_name='copy', duplicate_for_user=self.user)
        runs = {r.destination: r for r in PACableSchedule.objects.filter(project=copy)}
        main = runs['Main L']
        self.assertEqual(main.amp.project, copy)
        self.assertEqual(main.amp.name, 'SL LA12X #1')
        self.assertEqual(main.amp_location.project, copy)
        [linked] = main.speaker_arrays.all()
        self.assertEqual((linked.prediction.project, linked.array_base_name), (copy, 'K2 L'))
        self.assertEqual((runs['Sub'].amp_location.project, runs['Sub'].amp_location.name),
                         (copy, 'SL Racks'))


@unittest.skipIf(type(getattr(settings, 'MIGRATION_MODULES', None)).__name__ == '_DisableMigrations',
                 'needs real migrations: run in the plain suite')
class OneModeMigrationTests(TransactionTestCase):
    """0233 (refuse a written amp_location; re-point it) and 0234 (copy arrays)."""

    before = [('planner', '0232_mic_planner_walkthrough')]
    after = [('planner', '0234_pa_cable_arrays_from_linked')]

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.before)
        self.executor.loader.build_graph()
        apps = self.executor.loader.project_state(self.before).apps
        self.models = apps
        User = apps.get_model('auth', 'User')
        user = User.objects.create(username='mig')
        self.project = apps.get_model('planner', 'Project').objects.create(name='mig', owner=user)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def array(self, name):
        Prediction = self.models.get_model('planner', 'SoundvisionPrediction')
        pred = Prediction.objects.create(project=self.project, file_name=f'{name}.pdf')
        return self.models.get_model('planner', 'SpeakerArray').objects.create(
            prediction=pred, source_name=name, array_base_name=name,
            configuration='vertical_flown', bumper_type='K2-BUMP')

    def test_linked_rows_carry_their_array_into_the_m2m(self):
        Run = self.models.get_model('planner', 'PACableSchedule')
        main, stale = self.array('Main'), self.array('Stale')
        linked = Run.objects.create(project=self.project, entry_mode='linked',
                                    speaker_array=main, destination='')
        text = Run.objects.create(project=self.project, entry_mode='text',
                                  speaker_array=stale, destination='Typed')
        plain = Run.objects.create(project=self.project, entry_mode='text', destination='X')

        apps = self.migrate(self.after)
        Run = apps.get_model('planner', 'PACableSchedule')
        arrays = {r.pk: sorted(r.speaker_arrays.values_list('array_base_name', flat=True))
                  for r in Run.objects.all()}
        self.assertEqual(arrays, {linked.pk: ['Main'], text.pk: [], plain.pk: []})
        self.assertEqual(Run.objects.get(pk=text.pk).destination, 'Typed')
        self.assertEqual(Run.objects.get(pk=linked.pk).speaker_array_id, main.pk)  # kept

    def test_a_written_amp_location_stops_the_migration(self):
        Location = self.models.get_model('planner', 'Location')
        Run = self.models.get_model('planner', 'PACableSchedule')
        loc = Location.objects.create(project=self.project, name='FOH')
        row = Run.objects.create(project=self.project, destination='X', amp_location=loc)
        with self.assertRaisesRegex(RuntimeError, 'amp_location is set on rows'):
            self.migrate(self.after)
        Run.objects.filter(pk=row.pk).update(amp_location=None)
        apps = self.migrate(self.after)
        field = apps.get_model('planner', 'PACableSchedule')._meta.get_field('amp_location')
        self.assertEqual(field.related_model._meta.model_name, 'amplocation')
