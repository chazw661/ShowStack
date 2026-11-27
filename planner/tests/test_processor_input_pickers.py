"""Processor input pickers: a P1 / Galaxy AES or Analog input linked to its source (PR 2b-3).

The processor page's datalist is the picker: every I/O output and console
Aux / Matrix / Stereo output of the project. Text that is exactly one entry
links the input (a Connection, transport from the input's own type);
anything else unlinks it. The wiring diagram draws a linked input from its
source, confirmed. Also here: entries alike are lengthened (both pickers),
"(duplicate device)" as the last resort, and what a rename costs.

Run with::

    python manage.py test planner.tests.test_processor_input_pickers \\
        --settings=audiopatch.test_settings
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from planner.admin import (GalaxyInputInline, GalaxyProcessorAdmin, P1InputInline,
                           P1ProcessorAdmin)
from planner.admin_site import showstack_admin_site
from planner.connections import amp_sources
from planner.connections import processor_sources as S
from planner.connections import sources
from planner.connections.graph import project_graph
from planner.models import (Connection, ConsoleAuxOutput, ConsoleStereoOutput, Device,
                            DeviceOutput, GalaxyInput, GalaxyProcessor, P1Input, P1Processor,
                            ProjectMember)
from planner.tests.connection_fixtures import ConnectionFixtures
from planner.views_wiring import duplicate_warning_rows


def ct(model):
    return ContentType.objects.get_for_model(model)


class _Rig(ConnectionFixtures):
    """A P1 ("SL P1"), a Galaxy, a stage box (Out 1 "Left", Out 2 unnamed),
    a second box, and a console with Mtx 3 "Lobby", Aux 1 unnamed, St L."""

    def setUp(self):
        super().setUp()
        self.sl = self.p1('SL P1')
        self.aes1 = P1Input.objects.get(p1_processor__system_processor=self.sl,
                                        input_type='AES', channel_number=1)
        self.ana2 = P1Input.objects.get(p1_processor__system_processor=self.sl,
                                        input_type='ANALOG', channel_number=2)
        self.avb1 = P1Input.objects.get(p1_processor__system_processor=self.sl,
                                        input_type='AVB', channel_number=1)
        self.gx = self.galaxy('FOH Galaxy')
        self.gx_aes = GalaxyInput.objects.create(galaxy_processor=self.gx.galaxy_config,
                                                 input_type='AES', channel_number=1)
        self.box = self.device('Y001')
        self.left = self.device_output(self.box, 1, 'Left')
        self.out2 = self.device_output(self.box, 2, '')
        self.box2 = self.device('Rio 2')
        self.rio1 = self.device_output(self.box2, 1, 'Sub')
        self.desk = self.console('FOH PM5')
        self.mtx3 = self.matrix(self.desk, 3, name='Lobby')
        self.aux1 = ConsoleAuxOutput.objects.create(console=self.desk, aux_number='1')
        self.stl = ConsoleStereoOutput.objects.create(console=self.desk, stereo_type='L',
                                                      name='Main L')

    def link(self, target, source, transport, project=None):
        return Connection.objects.create(
            project=project or self.project, from_ct=ct(type(source)), from_id=source.pk,
            to_ct=ct(type(target)), to_id=target.pk, transport=transport)

    def links(self, target=None):
        rows = Connection.objects.all()
        return rows.filter(to_ct=ct(type(target)), to_id=target.pk) if target else rows

    def set_label(self, target, text, entries=None):
        target.label = text
        target.save()
        return S.link_from_text(target, entries)

    def entries(self):
        return S.picker(self.project)


# -- the model -----------------------------------------------------------------

class ConnectionModelTests(_Rig, TestCase):

    def test_a_processor_input_takes_an_io_or_console_output(self):
        for source, target, transport in ((self.left, self.aes1, 'aes'),
                                          (self.mtx3, self.ana2, 'analog'),
                                          (self.aux1, self.gx_aes, 'aes')):
            with self.subTest(source=type(source).__name__):
                self.link(target, source, transport)
        self.assertEqual(self.links().count(), 3)

    def test_the_transport_is_the_inputs_own_type(self):
        for target, transport in ((self.aes1, 'analog'), (self.ana2, 'aes'),
                                  (self.avb1, 'avb'), (self.aes1, 'dante')):
            with self.subTest(target=target.input_type, transport=transport):
                with self.assertRaisesMessage(ValidationError, 'cannot carry'):
                    self.link(target, self.left, transport)
        self.assertFalse(self.links().exists())

    def test_only_allowed_pairs(self):
        p1_out = self.p1_out(self.sl, 'AES', 1, 'X')
        with self.assertRaisesMessage(ValidationError, 'cannot be fed from that output'):
            self.link(self.aes1, p1_out, 'aes')              # processor -> processor
        ch = self.amp('Amp').channels.get(channel_number=1)
        with self.assertRaisesMessage(ValidationError, 'cannot be fed from that output'):
            self.link(ch, self.mtx3, 'aes')                  # console -> amp: not this PR
        with self.assertRaisesMessage(ValidationError, 'goes to an amp channel or a processor'):
            self.link(self.left, self.mtx3, 'aes')

    def test_ends_in_another_project_are_refused(self):
        theirs = self.make_project('theirs')
        their_out = self.device_output(self.device('Their Box', project=theirs), 1, 'X')
        their_in = P1Input.objects.get(p1_processor__system_processor=self.p1('Theirs', theirs),
                                       input_type='AES', channel_number=1)
        for source, target in ((their_out, self.aes1), (self.left, their_in)):
            with self.assertRaisesMessage(ValidationError, 'in its project'):
                self.link(target, source, 'aes')
        self.assertFalse(Connection.objects.exists())

    def test_a_template_console_cannot_feed(self):
        template = self.console('Template Desk', is_template=True)
        bus = self.matrix(template, 1, name='T')
        with self.assertRaisesMessage(ValidationError, 'console template'):
            self.link(self.aes1, bus, 'aes')

    def test_one_feed_per_input_and_transport(self):
        self.link(self.aes1, self.left, 'aes')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.link(self.aes1, self.mtx3, 'aes')

    def test_deleting_the_source_device_console_or_processor_deletes_the_link(self):
        cases = [
            ('an I/O output', lambda: self.left.delete(), self.left, self.aes1),
            ('an I/O device', lambda: self.box2.delete(), self.rio1, self.aes1),
            ('a console bus', lambda: self.mtx3.delete(), self.mtx3, self.ana2),
            ('a console', lambda: self.desk.delete(), self.aux1, self.ana2),
        ]
        for what, delete, source, target in cases:
            with self.subTest(what):
                self.link(target, source, S.INPUT_TRANSPORT[target.input_type])
                delete()
                self.assertFalse(self.links(target).exists())
        self.link(self.aes1, self.out2, 'aes')
        self.link(self.gx_aes, self.out2, 'aes')
        self.sl.delete()                               # P1: system processor -> config -> inputs
        self.assertEqual([c.to_id for c in self.links()], [self.gx_aes.pk])
        GalaxyProcessor.objects.all().delete()
        self.assertFalse(self.links().exists())

    def test_project_duplication_copies_links_onto_the_copy(self):
        self.link(self.aes1, self.left, 'aes')
        self.link(self.ana2, self.mtx3, 'analog')
        self.link(self.gx_aes, self.stl, 'aes')
        copy = self.project.duplicate(new_name='copy')
        rows = Connection.objects.filter(project=copy)
        self.assertEqual(rows.count(), 3)
        for row in rows:
            target, source = row.to_obj, row.from_obj
            owner = getattr(target, 'p1_processor', None) or target.galaxy_processor
            self.assertEqual(owner.system_processor.project, copy)
            self.assertEqual((source.device if isinstance(source, DeviceOutput)
                              else source.console).project, copy)
        self.assertEqual(Connection.objects.filter(project=self.project).count(), 3)


# -- the entries -----------------------------------------------------------------

class EntryTests(_Rig, TestCase):

    def test_every_io_output_and_console_output_is_listed_naming_its_device(self):
        e = self.entries()
        for text, source in (('Left · Y001 Out 1', self.left), ('Y001 Out 2', self.out2),
                             ('Sub · Rio 2 Out 1', self.rio1),
                             ('Lobby · FOH PM5 Mtx 3', self.mtx3),
                             ('FOH PM5 Aux 1', self.aux1), ('Main L · FOH PM5 St L', self.stl)):
            with self.subTest(text):
                self.assertEqual(e[text].pk, source.pk)
        self.assertEqual(len(e), 6)               # no processor outputs, no console inputs

    def test_the_list_is_in_device_order_grouped_by_device(self):
        listed = [(s.group, s.text) for s in S.listing(S.all_sources(self.project))]
        self.assertEqual([g for g, _ in listed],
                         ['Rio 2', 'Y001', 'Y001', 'FOH PM5', 'FOH PM5', 'FOH PM5'])
        self.assertEqual([t for g, t in listed if g == 'FOH PM5'],
                         ['FOH PM5 Aux 1', 'Lobby · FOH PM5 Mtx 3', 'Main L · FOH PM5 St L'])

    def test_another_projects_and_template_consoles_outputs_are_not_listed(self):
        theirs = self.make_project('theirs')
        self.device_output(self.device('Their Box', project=theirs), 1, 'Theirs')
        self.matrix(self.console('Their Desk', project=theirs), 1, name='Theirs')
        self.matrix(self.console('Template Desk', is_template=True), 1, name='Tmpl')
        text = ' '.join(self.entries())
        self.assertNotIn('Their', text)
        self.assertNotIn('Template', text)


class CollisionTests(_Rig, TestCase):
    """Two sources that would read the same are lengthened, never left out."""

    def twin_box(self, location=None, ip=None):
        box = Device.objects.create(project=self.project, name='Y001', location=location,
                                    primary_ip_address=ip)
        return self.device_output(box, 1, 'Left')

    def test_location_tells_two_devices_of_one_name_apart(self):
        self.box.location = self.location(self.project, 'Stage Left')
        self.box.save()
        twin = self.twin_box(self.location(self.project, 'Stage Right'))
        e = self.entries()
        self.assertNotIn('Left · Y001 Out 1', e)
        self.assertEqual(e['Left · Y001 Out 1 (Stage Left)'].pk, self.left.pk)
        self.assertEqual(e['Left · Y001 Out 1 (Stage Right)'].pk, twin.pk)
        self.assertEqual(e['Y001 Out 2'].pk, self.out2.pk)           # no clash: unchanged

    def test_then_the_ip(self):
        loc = self.location(self.project, 'Stage')
        Device.objects.filter(pk=self.box.pk).update(location=loc, primary_ip_address='10.0.0.1')
        twin = self.twin_box(loc, '10.0.0.2')
        e = self.entries()
        self.assertEqual(e['Left · Y001 Out 1 (Stage, 10.0.0.1)'].pk, self.left.pk)
        self.assertEqual(e['Left · Y001 Out 1 (Stage, 10.0.0.2)'].pk, twin.pk)

    def test_still_alike_reads_duplicate_device_links_nothing_and_is_warned(self):
        twin = self.twin_box()
        all_sources = S.all_sources(self.project)
        texts = [s.text for s in S.listing(all_sources)]
        self.assertEqual(texts.count('Left · Y001 Out 1 (duplicate device)'), 1)   # listed once
        self.assertNotIn('Left · Y001 Out 1 (duplicate device)', self.entries())   # picks nothing
        self.assertIsNone(self.set_label(self.aes1, 'Left · Y001 Out 1 (duplicate device)'))
        self.assertFalse(self.links().exists())
        self.assertEqual(sources.duplicate_warnings(all_sources), [['Y001', 'Y001']])
        self.assertEqual(twin.device.name, 'Y001')

    def test_amp_entries_are_lengthened_the_same_way(self):
        self.box.location = self.location(self.project, 'Stage Left')
        self.box.save()
        twin = self.twin_box(self.location(self.project, 'Stage Right'))
        e = amp_sources.picker(self.project)['aes_input']
        self.assertEqual(e['Left · Y001 Out 1 (Stage Left)'].pk, self.left.pk)
        self.assertEqual(e['Left · Y001 Out 1 (Stage Right)'].pk, twin.pk)

    def test_a_linked_text_follows_its_entry_when_a_twin_appears(self):
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        self.box.location = self.location(self.project, 'Stage Left')
        self.box.save()
        self.twin_box(self.location(self.project, 'Stage Right'))
        self.aes1.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Left · Y001 Out 1 (Stage Left)')
        self.assertEqual(self.links(self.aes1).get().from_id, self.left.pk)

    def test_duplicates_are_warned_on_the_wiring_diagram(self):
        self.twin_box()
        rows = duplicate_warning_rows(self.project)
        self.assertEqual([(r['kind'], r['edge']) for r in rows],
                         [('duplicate', 'Y001 and Y001')])


# -- saving: the processor page -------------------------------------------------

class _Client(_Rig):
    def setUp(self):
        super().setUp()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def post_inputs(self, proc, **labels):
        """Save the processor page's input inline, as its change form would."""
        request = RequestFactory().post('/')
        request.user = self.user
        request.current_project = self.project
        if proc.device_type == 'P1':
            config, inline, admin_cls = proc.p1_config, P1InputInline, P1ProcessorAdmin
            model, fk = P1Processor, 'p1_processor'
        else:
            config, inline, admin_cls = proc.galaxy_config, GalaxyInputInline, GalaxyProcessorAdmin
            model, fk = GalaxyProcessor, 'galaxy_processor'
        FormSet = inline(model, showstack_admin_site).get_formset(request, config)
        rows = list(config.inputs.order_by('input_type', 'channel_number'))
        data = {'inputs-TOTAL_FORMS': len(rows), 'inputs-INITIAL_FORMS': len(rows),
                'inputs-MIN_NUM_FORMS': 0, 'inputs-MAX_NUM_FORMS': 1000}
        for i, row in enumerate(rows):
            row.refresh_from_db()
            data.update({f'inputs-{i}-id': row.pk, f'inputs-{i}-{fk}': config.pk,
                         f'inputs-{i}-label': labels.get(f'{row.input_type}{row.channel_number}',
                                                         row.label or '')})
        formset = FormSet(data, instance=config, prefix='inputs')
        self.assertTrue(formset.is_valid(), formset.errors)
        admin_cls(model, showstack_admin_site).save_formset(request, None, formset, True)


class SaveRuleTests(_Client, TestCase):

    def test_picking_an_entry_links_editing_away_unlinks(self):
        self.post_inputs(self.sl, AES1='Left · Y001 Out 1', ANALOG2='Lobby · FOH PM5 Mtx 3')
        aes, ana = self.links(self.aes1).get(), self.links(self.ana2).get()
        self.assertEqual((aes.from_obj, aes.transport), (self.left, 'aes'))
        self.assertEqual((ana.from_obj, ana.transport), (self.mtx3, 'analog'))
        self.post_inputs(self.sl)                                   # nothing changed: kept
        self.assertEqual(self.links().count(), 2)
        self.post_inputs(self.sl, AES1='Sub · Rio 2 Out 1')          # another entry: moved
        self.assertEqual(self.links(self.aes1).get().from_obj, self.rio1)
        self.post_inputs(self.sl, AES1='Left')                       # edited away
        self.assertFalse(self.links(self.aes1).exists())
        self.aes1.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Left')

    def test_no_fuzzy_matching_and_avb_never_links(self):
        self.post_inputs(self.sl, AES1='left · y001 out 1', AVB1='Left · Y001 Out 1')
        self.assertFalse(self.links().exists())

    def test_galaxy_inputs_link_too(self):
        self.post_inputs(self.gx, AES1='Main L · FOH PM5 St L')
        self.assertEqual(self.links(self.gx_aes).get().from_obj, self.stl)

    def unlink(self, target, kind):
        name = {'p1input': 'planner:p1_input_unlink', 'galaxyinput': 'planner:galaxy_input_unlink'}
        return self.client.post(reverse(name[kind], args=[target.pk]))

    def test_unlink_keeps_the_text(self):
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        r = self.unlink(self.aes1, 'p1input')
        self.assertEqual(r.json(), {'success': True, 'linked': ''})
        self.assertFalse(self.links().exists())
        self.aes1.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Left · Y001 Out 1')

    def test_unlink_is_scoped_and_needs_edit_rights(self):
        theirs = self.make_project('theirs')
        their_in = P1Input.objects.get(p1_processor__system_processor=self.p1('Theirs', theirs),
                                       input_type='AES', channel_number=1)
        self.assertEqual(self.unlink(their_in, 'p1input').status_code, 404)
        self.assertEqual(self.unlink(self.aes1, 'galaxyinput').status_code, 404)   # not a Galaxy input
        self.set_label(self.gx_aes, 'Left · Y001 Out 1')
        self.assertEqual(self.unlink(self.gx_aes, 'galaxyinput').status_code, 200)
        self.assertFalse(self.links(self.gx_aes).exists())
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        viewer = get_user_model().objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.client.force_login(viewer)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        self.assertEqual(self.unlink(self.aes1, 'p1input').status_code, 403)
        self.assertEqual(self.links().count(), 1)
        self.assertEqual(self.client.get(reverse('planner:p1_input_unlink',
                                                 args=[self.aes1.pk])).status_code, 405)

    def test_the_page_lists_the_picker_once_and_marks_links(self):
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        r = self.client.get(reverse('admin:planner_p1processor_change',
                                    args=[self.sl.p1_config.pk]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertEqual(html.count('<datalist id="p1-input-suggestions">'), 1)
        self.assertIn('<option value="Lobby · FOH PM5 Mtx 3" data-console="FOH PM5">', html)
        self.assertIn('data-kind="p1input" data-input-id="%d" data-linked="Left · Y001 Out 1"'
                      % self.aes1.pk, html)
        self.assertEqual(html.count('class="proc-link-btn'), 8)     # AES 1-4 + Analog 1-4
        self.assertEqual(html.count('list="p1-input-suggestions"'), 8)   # AVB: free text


# -- keeping linked text current ------------------------------------------------

class RenameTests(_Client, TestCase):

    def test_renaming_the_source_or_its_device_rewrites_the_text(self):
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        self.set_label(self.ana2, 'Lobby · FOH PM5 Mtx 3')
        self.left.signal_name = 'Left Main'
        self.left.save()
        self.box.name = 'Y002'
        self.box.save()
        self.mtx3.name = 'Foyer'
        self.mtx3.save()
        self.desk.name = 'FOH Desk'
        self.desk.save()
        self.aes1.refresh_from_db()
        self.ana2.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Left Main · Y002 Out 1')
        self.assertEqual(self.ana2.label, 'Foyer · FOH Desk Mtx 3')
        self.assertEqual(self.links().count(), 2)
        self.assertIn(self.aes1.label, self.entries())

    def test_a_console_bus_rename_reaches_io_outputs_renamed_by_update(self):
        # The bus renames its linked I/O output with .update(), which sends no
        # signal; amp and processor text linked to that output follow anyway.
        out = self.device_output(self.box, 3, 'Lobby', bus=self.mtx3)
        self.set_label(self.aes1, 'Lobby · Y001 Out 3')
        ch = self.amp('Amp').channels.get(channel_number=1)
        ch.aes_input = 'Lobby · Y001 Out 3'
        ch.save()
        amp_sources.link_from_text(ch, 'aes_input')
        self.mtx3.name = 'Foyer'
        self.mtx3.save()
        out.refresh_from_db()
        self.assertEqual(out.signal_name, 'Foyer')
        self.aes1.refresh_from_db()
        ch.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Foyer · Y001 Out 3')
        self.assertEqual(ch.aes_input, 'Foyer · Y001 Out 3')

    def test_an_io_output_deleted_before_it_renumbers_the_text(self):
        self.set_label(self.aes1, 'Y001 Out 2')
        self.left.delete()
        self.aes1.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Y001 Out 1')

    def test_unlinked_inputs_are_left_alone(self):
        P1Input.objects.filter(pk=self.aes1.pk).update(label='Left · Y001 Out 1')
        self.box.name = 'Y002'
        self.box.save()
        self.aes1.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Left · Y001 Out 1')


class RewriteCostTests(_Client, TestCase):
    """What a rename costs, with linked amp and processor inputs in the project."""

    def setUp(self):
        super().setUp()
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        ch = self.amp('Amp').channels.get(channel_number=1)
        ch.aes_input = 'Left · Y001 Out 1'
        ch.save()
        amp_sources.link_from_text(ch, 'aes_input')

    def count(self, fn):
        with CaptureQueriesContext(connection) as ctx:
            fn()
        return len(ctx.captured_queries)

    def make_outputs(self, n):
        device = Device.objects.create(project=self.project, name=f'Box {n}', output_count=n)
        for i in range(1, n + 1):
            DeviceOutput.objects.create(device=device, output_number=i, signal_name='')

    def test_batched_the_rewrite_runs_once_however_many_outputs(self):
        def batched(n):
            def run():
                with sources.batched():
                    self.make_outputs(n)
            return run
        small, big = self.count(batched(4)), self.count(batched(32))
        self.assertEqual(big - small, 28 * 1)          # one INSERT per extra output, nothing else

    def test_the_admin_device_add_is_batched(self):
        url = reverse('admin:planner_device_add')
        data = {'name': 'Box 32', 'input_count': 0, 'output_count': 32,
                'inputs-TOTAL_FORMS': 0, 'inputs-INITIAL_FORMS': 0,
                'outputs-TOTAL_FORMS': 0, 'outputs-INITIAL_FORMS': 0}
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.post(url, data)
        self.assertEqual(r.status_code, 302, r.content[:2000])
        self.assertEqual(DeviceOutput.objects.filter(device__name='Box 32').count(), 32)
        connection_reads = [q for q in ctx.captured_queries
                            if 'FROM "planner_connection"' in q['sql']
                            and q['sql'].lstrip().upper().startswith('SELECT')]
        self.assertEqual(len(connection_reads), 1, [q['sql'] for q in connection_reads])

    def test_unbatched_with_nothing_linked_each_output_costs_one_query(self):
        Connection.objects.all().delete()
        device = Device.objects.create(project=self.project, name='Box')
        n = self.count(lambda: DeviceOutput.objects.create(device=device, output_number=1))
        self.assertEqual(n, 2)                         # the INSERT and the link check

    def test_a_location_rename_rewrites_a_lengthened_entry(self):
        loc = self.location(self.project, 'Stage Left')
        self.box.location = loc
        self.box.save()
        twin = Device.objects.create(project=self.project, name='Y001',
                                     location=self.location(self.project, 'Stage Right'))
        self.device_output(twin, 1, 'Left')
        loc.name = 'SL Wing'
        loc.save()
        self.aes1.refresh_from_db()
        self.assertEqual(self.aes1.label, 'Left · Y001 Out 1 (SL Wing)')


# -- the wiring diagram ---------------------------------------------------------

class GraphTests(_Client, TestCase):

    def edges_into(self, proc):
        self.graph = project_graph(self.project)
        return [e for e in self.graph['edges'] if e['to'] == f'processor:{proc.pk}']

    def test_a_linked_input_is_a_confirmed_edge_from_its_source(self):
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        self.set_label(self.ana2, 'Lobby · FOH PM5 Mtx 3')
        edges = {e['from']: e for e in self.edges_into(self.sl)}
        io = edges[f'device:{self.box.pk}']
        self.assertEqual((io['status'], io['unlinked'], io['network']), ('confirmed', False, False))
        self.assertEqual((io['from_ports'], io['label']), ('AES Out 1', 'SL P1 AES 1'))
        self.assertEqual(io['sources'], [{'kind': 'connection', 'pk': mock.ANY}])
        self.assertEqual(io['to_slot'], f'p1input:{self.aes1.pk}')
        self.assertEqual(io['transports'], ['aes'])
        desk = edges[f'console:{self.desk.pk}']
        self.assertEqual((desk['status'], desk['from_ports'], desk['label']),
                         ('confirmed', 'Mtx 3', 'SL P1 Analog 2'))
        slots = {s['id']: s['label'] for n in self.graph['nodes'] if n['id'] == f'processor:{self.sl.pk}'
                 for s in n['slots']}
        self.assertEqual(slots[f'p1input:{self.aes1.pk}'], 'AES 1 ← Y001 AES Out 1 (Left)')

    def test_an_unlinked_input_is_still_matched_by_text(self):
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        P1Input.objects.filter(pk=self.ana2.pk).update(label='Sub')     # Rio 2 Out 1's name
        statuses = {(e['from'], e['status']) for e in self.edges_into(self.sl)}
        self.assertEqual(statuses, {(f'device:{self.box.pk}', 'confirmed'),
                                    (f'device:{self.box2.pk}', 'inferred')})

    def test_a_linked_input_is_not_matched_by_text(self):
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        P1Input.objects.filter(pk=self.aes1.pk).update(label='Sub')     # text now names Rio 2
        edges = self.edges_into(self.sl)
        self.assertEqual([(e['from'], e['status']) for e in edges],
                         [(f'device:{self.box.pk}', 'confirmed')])

    def test_an_orphaned_link_is_skipped_and_reported(self):
        from io import StringIO
        from django.core.management import call_command
        self.set_label(self.aes1, 'Left · Y001 Out 1')
        Connection.objects.update(from_id=987654)               # its source gone, outside the ORM
        self.assertEqual(self.edges_into(self.sl), [])
        out = StringIO()
        call_command('infer_connections', '--project', str(self.project.pk), stdout=out)
        self.assertIn('processor inputs linked (confirmed): 0 · orphaned: 1', out.getvalue())

    def test_a_matrix_through_a_linked_io_output_is_not_drawn_twice(self):
        out = self.device_output(self.box, 3, 'Lobby', bus=self.mtx3)
        self.mtx3.destination = 'SL P1'
        self.mtx3.save()
        self.set_label(self.aes1, 'Lobby · Y001 Out 3')
        self.assertEqual(out.signal_name, 'Lobby')
        froms = [e['from'] for e in self.edges_into(self.sl)]
        self.assertEqual(froms, [f'device:{self.box.pk}'])
