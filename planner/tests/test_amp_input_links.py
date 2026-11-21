"""Amp input pickers: linking an amp channel's input to its source output (PR 2b-2).

The rack view's datalists are the picker; text that is exactly one entry
links the input (a Connection), anything else unlinks it. The wiring diagram
draws a linked input from its source, confirmed.

Run with::

    python manage.py test planner.tests.test_amp_input_links \\
        --settings=audiopatch.test_settings
"""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from planner.admin import AmpAdmin, AmpChannelInline
from planner.admin_site import showstack_admin_site
from planner.connections import amp_sources as S
from planner.connections import layout as L
from planner.connections.graph import project_graph
from planner.connections.matchers import ProjectIndex
from planner.models import (Amp, AmpChannel, AmpModel, Connection, DeviceOutput,
                            P1Output, ProjectMember)
from planner.tests.connection_fixtures import ConnectionFixtures


def ct(model):
    return ContentType.objects.get_for_model(model)


class _Rig(ConnectionFixtures):
    """One P1 (AVB 3 "L Main", AES 1 "L Main", Analog 2 unlabelled), one
    Galaxy, one stage box (Out 1 "CENTER", Out 2 unlabelled) and one amp."""

    def setUp(self):
        super().setUp()
        self.sl = self.p1('SL P1')
        self.avb3 = self.p1_out(self.sl, 'AVB', 3, 'L Main')
        self.aes1 = self.p1_out(self.sl, 'AES', 1, 'L Main')
        self.ana2 = P1Output.objects.get(p1_processor__system_processor=self.sl,
                                         output_type='ANALOG', channel_number=2)
        self.gx = self.galaxy('FOH Galaxy')
        self.gx_aes = self.galaxy_out(self.gx, 'AES', 4, 'Front Fill')
        self.box = self.device('Stage Box')
        self.out1 = self.device_output(self.box, 1, 'CENTER')
        self.out2 = self.device_output(self.box, 2, '')
        self.amp_a = self.amp('SL Amp 1')
        self.ch1 = self.amp_a.channels.get(channel_number=1)
        self.ch2 = self.amp_a.channels.get(channel_number=2)

    def link(self, channel, source, transport, project=None):
        return Connection.objects.create(
            project=project or self.project, from_ct=ct(type(source)), from_id=source.pk,
            to_ct=ct(AmpChannel), to_id=channel.pk, transport=transport)

    def links(self, channel=None):
        rows = Connection.objects.all()
        return rows.filter(to_id=channel.pk) if channel else rows


# -- the model -----------------------------------------------------------------

class ConnectionModelTests(_Rig, TestCase):

    def test_deleting_either_end_deletes_the_link(self):
        cases = [
            ('a P1 output', lambda: self.avb3.delete(), self.avb3, 'avb'),
            ('a Galaxy output', lambda: self.gx_aes.delete(), self.gx_aes, 'aes'),
            ('an I/O output', lambda: self.out1.delete(), self.out1, 'analog'),
        ]
        for what, delete, source, transport in cases:
            with self.subTest(what):
                self.link(self.ch1, source, transport)
                delete()
                self.assertFalse(self.links(self.ch1).exists())

    def test_deleting_a_processor_or_device_deletes_its_links(self):
        self.link(self.ch1, self.avb3, 'avb')
        self.link(self.ch1, self.out1, 'analog')
        self.sl.delete()
        self.assertEqual([c.transport for c in self.links(self.ch1)], ['analog'])
        self.box.delete()
        self.assertFalse(self.links().exists())

    def test_deleting_the_amp_channel_or_project_deletes_its_links(self):
        self.link(self.ch1, self.avb3, 'avb')
        self.link(self.ch2, self.aes1, 'aes')
        self.ch1.delete()
        self.assertEqual(self.links().count(), 1)
        self.amp_a.delete()
        self.assertFalse(self.links().exists())
        self.link(self.amp('SL Amp 2').channels.get(channel_number=1), self.avb3, 'avb')
        self.project.delete()
        self.assertFalse(Connection.objects.exists())

    def test_channels_dropped_by_an_amp_model_change_lose_their_links(self):
        ch4 = self.amp_a.channels.get(channel_number=4)
        self.link(ch4, self.avb3, 'avb')
        self.link(self.ch1, self.aes1, 'aes')
        self.amp_a.amp_model = AmpModel.objects.create(manufacturer="L'Acoustics",
                                                       model_name='TEST2', channel_count=2)
        self.amp_a.save()
        self.amp_a.setup_channels()
        self.assertFalse(AmpChannel.objects.filter(pk=ch4.pk).exists())
        self.assertEqual([c.to_id for c in self.links()], [self.ch1.pk])

    def test_ends_in_another_project_are_refused(self):
        theirs = self.make_project('theirs')
        their_out = self.p1_out(self.p1('Their P1', project=theirs), 'AVB', 1, 'X')
        their_ch = self.amp('Their Amp', project=theirs).channels.get(channel_number=1)
        for source, channel in ((their_out, self.ch1), (self.avb3, their_ch)):
            with self.assertRaisesMessage(ValidationError, 'in its project'):
                self.link(channel, source, 'avb')
        self.assertFalse(Connection.objects.exists())

    def test_a_transport_the_source_cannot_carry_is_refused(self):
        for source, transport in ((self.out1, 'avb'), (self.aes1, 'analog'), (self.avb3, 'aes')):
            with self.subTest(source=str(source), transport=transport):
                with self.assertRaisesMessage(ValidationError, 'cannot carry'):
                    self.link(self.ch1, source, transport)

    def test_only_an_amp_channel_can_be_fed(self):
        with self.assertRaisesMessage(ValidationError, 'goes to an amp channel'):
            Connection.objects.create(project=self.project, from_ct=ct(P1Output),
                                      from_id=self.avb3.pk, to_ct=ct(DeviceOutput),
                                      to_id=self.out1.pk, transport='avb')

    def test_one_link_per_channel_and_transport(self):
        self.link(self.ch1, self.avb3, 'avb')
        self.link(self.ch1, self.aes1, 'aes')            # another transport: fine
        avb4 = self.p1_out(self.sl, 'AVB', 4, 'R Main')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.link(self.ch1, avb4, 'avb')
        self.assertEqual(self.links(self.ch1).count(), 2)

    def test_project_duplication_copies_links_onto_the_copy(self):
        self.link(self.ch1, self.avb3, 'avb')
        self.link(self.ch1, self.out1, 'analog')
        copy = self.project.duplicate(new_name='copy')
        rows = Connection.objects.filter(project=copy)
        self.assertEqual(rows.count(), 2)
        for row in rows:
            self.assertEqual(row.to_obj.amp.project, copy)
            source = row.from_obj
            owner = (source.device.project if isinstance(source, DeviceOutput)
                     else source.p1_processor.system_processor.project)
            self.assertEqual(owner, copy)
        self.assertEqual(Connection.objects.filter(project=self.project).count(), 2)


# -- the entries -----------------------------------------------------------------

class EntryTests(_Rig, TestCase):

    def entries(self):
        return S.picker(self.project)

    def test_each_field_lists_its_sources_naming_the_device(self):
        e = self.entries()
        self.assertIn('AVB 3 - L Main (SL P1)', e['avb_stream'])
        self.assertIn('AVB 1 (SL P1)', e['avb_stream'])                 # unlabelled
        self.assertIn('L Main · SL P1 AES 1', e['aes_input'])
        self.assertIn('Front Fill · FOH Galaxy AES 4', e['aes_input'])
        self.assertIn('CENTER · Stage Box Out 1', e['aes_input'])
        self.assertIn('SL P1 Analog 2', e['analog_input'])              # unlabelled
        self.assertIn('CENTER · Stage Box Out 1', e['analog_input'])
        self.assertIn('Stage Box Out 2', e['analog_input'])
        # AVB lists processor AVB outputs only; AES / analogue no AVB.
        self.assertTrue(all(t.startswith('AVB ') for t in e['avb_stream']))
        self.assertFalse([t for t in e['avb_stream'] if 'Stage Box' in t])
        self.assertFalse([t for f in ('aes_input', 'analog_input') for t in e[f]
                          if t.startswith('AVB ')])
        self.assertEqual(e['avb_stream']['AVB 3 - L Main (SL P1)'].key, ('p1output', self.avb3.pk))

    def test_io_outputs_are_numbered_by_position(self):
        DeviceOutput.objects.filter(pk=self.out1.pk).update(output_number=10)
        DeviceOutput.objects.filter(pk=self.out2.pk).update(output_number=20)
        e = self.entries()['analog_input']
        self.assertEqual(e['CENTER · Stage Box Out 1'].pk, self.out1.pk)
        self.assertEqual(e['Stage Box Out 2'].pk, self.out2.pk)

    def test_repeats_are_lengthened_with_the_location_so_both_stay_pickable(self):
        twin = self.p1('SL P1')                                  # same name
        twin.location = self.location(self.project, 'Delay Tower')
        twin.save()
        twin_avb3 = self.p1_out(twin, 'AVB', 3, 'L Main')
        e = self.entries()
        self.assertNotIn('AVB 3 - L Main (SL P1)', e['avb_stream'])
        self.assertEqual(e['avb_stream']['AVB 3 - L Main (SL P1) (SL P1 loc)'].pk, self.avb3.pk)
        self.assertEqual(e['avb_stream']['AVB 3 - L Main (SL P1) (Delay Tower)'].pk, twin_avb3.pk)
        for field, entries in e.items():
            sources = [s.key for s in entries.values()]
            self.assertEqual(len(sources), len(set(sources)), field)
        # The old, shorter text names neither now: it links nothing.
        self.ch1.avb_stream = 'AVB 3 - L Main (SL P1)'
        self.ch1.save()
        self.assertIsNone(S.link_from_text(self.ch1, 'avb_stream'))

    def test_repeats_still_alike_are_listed_once_as_duplicates_and_link_nothing(self):
        twin = self.p1('SL P1')                                  # same name, location text, IP
        self.p1_out(twin, 'AVB', 3, 'L Main')
        text = 'AVB 3 - L Main (SL P1) (duplicate device)'
        self.assertNotIn(text, self.entries()['avb_stream'])
        self.assertEqual(S.listing(S.all_sources(self.project))['avb_stream'].count(text), 1)
        self.ch1.avb_stream = text
        self.ch1.save()
        self.assertIsNone(S.link_from_text(self.ch1, 'avb_stream'))

    def test_another_projects_outputs_are_not_listed(self):
        theirs = self.make_project('theirs')
        self.p1_out(self.p1('Their P1', project=theirs), 'AVB', 1, 'Theirs')
        self.device_output(self.device('Their Box', project=theirs), 1, 'Theirs')
        text = ' '.join(t for f in self.entries().values() for t in f)
        self.assertNotIn('Their', text)

    def test_an_entry_too_long_to_store_is_left_out(self):
        self.device_output(self.box, 3, 'X' * 110)
        self.assertFalse([t for t in self.entries()['analog_input'] if t.startswith('XXX')])


# -- saving: the rack view and the admin inline --------------------------------

class _Client(_Rig):
    def setUp(self):
        super().setUp()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def save(self, channel, field, value, **extra):
        return self.client.post(reverse('planner:amp_channel_inline_update', args=[channel.pk]),
                                {'field': field, 'value': value, **extra})


class SaveRuleTests(_Client, TestCase):

    def test_selecting_an_entry_links_the_input(self):
        r = self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        self.assertEqual(r.json(), {'success': True, 'linked': 'AVB 3 - L Main (SL P1)'})
        [row] = self.links(self.ch1)
        self.assertEqual((row.from_obj, row.transport, row.project), (self.avb3, 'avb', self.project))
        r = self.save(self.ch1, 'analog_input', 'CENTER · Stage Box Out 1')
        self.assertEqual(r.json()['linked'], 'CENTER · Stage Box Out 1')
        self.assertEqual(self.links(self.ch1).count(), 2)

    def test_picking_another_entry_moves_the_link(self):
        self.save(self.ch1, 'aes_input', 'L Main · SL P1 AES 1')
        [first] = self.links(self.ch1)
        self.save(self.ch1, 'aes_input', 'CENTER · Stage Box Out 1')
        [row] = self.links(self.ch1)
        self.assertEqual((row.pk, row.from_obj), (first.pk, self.out1))

    def test_editing_away_unlinks_and_keeps_what_was_typed(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        r = self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main')
        self.assertEqual(r.json(), {'success': True, 'linked': ''})
        self.assertFalse(self.links(self.ch1).exists())
        self.ch1.refresh_from_db()
        self.assertEqual(self.ch1.avb_stream, 'AVB 3 - L Main')

    def test_no_fuzzy_matching(self):
        for text in ('avb 3 - l main (sl p1)', ' AVB 3 - L Main (SL P1)', 'AVB 3 - L Main (SL P1) ',
                     'L Main'):
            with self.subTest(text=text):
                self.assertEqual(self.save(self.ch1, 'avb_stream', text).json()['linked'], '')
                self.assertFalse(self.links(self.ch1).exists())

    def test_an_entry_of_another_field_does_not_link(self):
        self.assertEqual(self.save(self.ch1, 'avb_stream', 'L Main · SL P1 AES 1').json()['linked'], '')
        self.assertFalse(self.links().exists())

    def test_unlink_keeps_the_text(self):
        self.save(self.ch1, 'analog_input', 'CENTER · Stage Box Out 1')
        r = self.save(self.ch1, 'analog_input', '', unlink='1')
        self.assertEqual(r.json(), {'success': True, 'linked': ''})
        self.assertFalse(self.links().exists())
        self.ch1.refresh_from_db()
        self.assertEqual(self.ch1.analog_input, 'CENTER · Stage Box Out 1')

    def test_a_viewer_cannot_link_or_unlink(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        viewer = get_user_model().objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.client.force_login(viewer)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        self.assertEqual(self.save(self.ch2, 'avb_stream', 'AVB 3 - L Main (SL P1)').status_code, 403)
        self.assertEqual(self.save(self.ch1, 'avb_stream', '', unlink='1').status_code, 403)
        self.assertEqual([c.to_id for c in self.links()], [self.ch1.pk])

    def test_another_projects_channel_is_not_found(self):
        theirs = self.make_project('theirs')
        their_ch = self.amp('Their Amp', project=theirs).channels.get(channel_number=1)
        self.assertEqual(self.save(their_ch, 'avb_stream', 'AVB 3 - L Main (SL P1)').status_code, 404)
        self.assertFalse(self.links().exists())

    def test_the_admin_inline_follows_the_same_rule(self):
        request = RequestFactory().post('/')
        request.user = self.user
        request.current_project = self.project
        inline = AmpChannelInline(Amp, showstack_admin_site)
        FormSet = inline.get_formset(request, self.amp_a)

        def post(**values):
            data = {'channels-TOTAL_FORMS': 4, 'channels-INITIAL_FORMS': 4,
                    'channels-MIN_NUM_FORMS': 0, 'channels-MAX_NUM_FORMS': 1000}
            for i, ch in enumerate(self.amp_a.channels.order_by('channel_number')):
                ch.refresh_from_db()
                data.update({f'channels-{i}-id': ch.pk, f'channels-{i}-amp': self.amp_a.pk,
                             f'channels-{i}-channel_name': ch.channel_name,
                             f'channels-{i}-avb_stream': ch.avb_stream or '',
                             f'channels-{i}-aes_input': ch.aes_input,
                             f'channels-{i}-analog_input': ch.analog_input})
            data.update(values)
            formset = FormSet(data, instance=self.amp_a, prefix='channels')
            self.assertTrue(formset.is_valid(), formset.errors)
            AmpAdmin(Amp, showstack_admin_site).save_formset(request, None, formset, True)

        post(**{'channels-0-aes_input': 'L Main · SL P1 AES 1'})
        self.assertEqual([c.from_obj for c in self.links(self.ch1)], [self.aes1])
        post()                                                # nothing changed: kept
        self.assertEqual(self.links(self.ch1).count(), 1)
        post(**{'channels-0-aes_input': 'L Main'})
        self.assertFalse(self.links().exists())


class RenameTests(_Client, TestCase):
    """A linked input's text is a copy of its source's entry, kept current."""

    def test_renaming_the_output_processor_or_device_rewrites_the_text(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        self.save(self.ch1, 'analog_input', 'CENTER · Stage Box Out 1')
        self.save(self.ch2, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        self.avb3.label = 'Left Main'
        self.avb3.save()
        self.sl.name = 'Stage Left P1'
        self.sl.save()
        self.out1.signal_name = 'CTR'
        self.out1.save()
        self.box.name = 'Rio 1'
        self.box.save()
        for ch in (self.ch1, self.ch2):
            ch.refresh_from_db()
            self.assertEqual(ch.avb_stream, 'AVB 3 - Left Main (Stage Left P1)')
        self.assertEqual(self.ch1.analog_input, 'CTR · Rio 1 Out 1')
        self.assertEqual(self.links().count(), 3)       # still linked: the new text is an entry
        self.assertIn(self.ch1.avb_stream, S.picker(self.project)['avb_stream'])

    def test_an_io_output_deleted_before_it_renumbers_the_linked_text(self):
        self.save(self.ch1, 'analog_input', 'Stage Box Out 2')
        self.out1.delete()
        self.ch1.refresh_from_db()
        self.assertEqual(self.ch1.analog_input, 'Stage Box Out 1')

    def test_unlinked_inputs_with_the_same_text_are_left_alone(self):
        AmpChannel.objects.filter(pk=self.ch2.pk).update(avb_stream='AVB 3 - L Main (SL P1)')
        self.avb3.label = 'Left Main'
        self.avb3.save()
        self.ch2.refresh_from_db()
        self.assertEqual(self.ch2.avb_stream, 'AVB 3 - L Main (SL P1)')


class RackViewTests(_Client, TestCase):

    def test_the_page_carries_the_entries_as_json_and_the_link_state(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        response = self.client.get(reverse('admin:planner_amp_changelist'))
        body = response.content.decode()
        self.assertIn('<datalist id="amp-avb-input-options"></datalist>', body)
        self.assertIn('AVB 3 - L Main (SL P1)', body.split('id="amp-input-sources"')[1].split('</script>')[0])
        self.assertIn('title="Linked to AVB 3 - L Main (SL P1)"', body)
        self.assertEqual(body.count('class="amp-link-btn linked"'), 1)
        self.assertIn('amp-input-cell linked', body)

    def test_the_tooltip_names_the_source_even_when_the_text_does_not(self):
        self.link(self.ch2, self.out1, 'aes')                    # text left blank
        body = self.client.get(reverse('admin:planner_amp_changelist')).content.decode()
        self.assertIn('title="Linked to CENTER · Stage Box Out 1"', body)


# -- the wiring diagram ------------------------------------------------------------

class GraphTests(_Client, TestCase):

    def draw(self):
        self.graph = project_graph(self.project)
        self.lay = L.layout(self.graph)
        return self.graph

    def edges_into(self, amp):
        return [e for e in self.draw()['edges'] if e['to'] == f'amp:{amp.pk}']

    def test_a_linked_input_is_a_confirmed_edge_from_its_source(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        self.save(self.ch2, 'analog_input', 'CENTER · Stage Box Out 1')
        edges = {e['from']: e for e in self.edges_into(self.amp_a)}
        avb = edges[f'processor:{self.sl.pk}']
        self.assertEqual((avb['status'], avb['unlinked'], avb['network']), ('confirmed', False, True))
        io = edges[f'device:{self.box.pk}']
        self.assertEqual((io['status'], io['unlinked']), ('confirmed', False))
        self.assertFalse([n for n in self.graph['nodes'] if n.get('feed')])
        boxes = {r.from_node: r for r in self.lay.routes}
        self.assertIn(f'device:{self.box.pk}', boxes)            # from the outputs box
        self.assertEqual({b.id for b in self.lay.boxes if b.node == f'device:{self.box.pk}'},
                         {f'device:{self.box.pk}#out'})

    def test_the_link_wins_over_the_text(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        AmpChannel.objects.filter(pk=self.ch1.pk).update(avb_stream='nothing like it')
        [edge] = self.edges_into(self.amp_a)
        self.assertEqual((edge['from'], edge['status']), (f'processor:{self.sl.pk}', 'confirmed'))
        self.assertFalse([n for n in self.graph['nodes'] if n.get('feed')])

    def test_text_fallback_for_an_input_with_no_link(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        AmpChannel.objects.filter(pk=self.ch2.pk).update(aes_input='Front Fill')
        statuses = {(e['from'], e['status']) for e in self.edges_into(self.amp_a)}
        self.assertEqual(statuses, {(f'processor:{self.sl.pk}', 'confirmed'),
                                    (f'processor:{self.gx.pk}', 'inferred')})

    def test_an_orphaned_link_is_skipped_and_counted(self):
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        Connection.objects.update(from_id=987654)               # its source gone, outside the ORM
        self.assertEqual(self.edges_into(self.amp_a), [])
        index = ProjectIndex.load(self.project)
        self.assertEqual([(s, c is not None) for _, s, c, _ in index.amp_links], [(None, True)])

    def test_the_query_count_does_not_grow_with_links(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                project_graph(self.project)
            return len(ctx.captured_queries)
        self.save(self.ch1, 'avb_stream', 'AVB 3 - L Main (SL P1)')
        few = count()
        for n in range(4, 9):
            self.p1_out(self.sl, 'AVB', n, f'Out {n}')
        for n, ch in enumerate(self.amp('SL Amp 2').channels.all(), start=4):
            self.save(ch, 'avb_stream', f'AVB {n} - Out {n} (SL P1)')
        self.assertEqual(Connection.objects.count(), 5)
        self.assertEqual(count(), few)


class BareNumberAndLabelTests(ConnectionFixtures, TestCase):
    """Folded in from the 3.1 review."""

    def boxes(self, n):
        # I/O outputs are numbered by position: each box has an Out 3.
        for i in range(n):
            box = self.device(f'Box {i}')
            for number in (1, 2, 3):
                self.device_output(box, number, f'Line {i}.{number}')

    def feed(self):
        graph = project_graph(self.project)
        return graph, [n for n in graph['nodes'] if n.get('feed')]

    def test_a_bare_number_with_more_than_three_candidates_is_not_matched(self):
        self.boxes(4)
        amp = self.amp('Amp')
        self.amp_channel(amp, 1, analog_input='3')
        graph, [node] = self.feed()
        self.assertEqual((node['label'], node['reason'], node['ambiguous']),
                         ('Analog: 3', 'not matched to an output', False))
        self.assertFalse(graph['warnings'])
        self.boxes(0)
        from planner.connections import matchers as m
        index = m.ProjectIndex.load(self.project)
        self.assertEqual(len([p for p, _ in index.device_outputs if p.number == 3]), 4)

    def test_with_three_or_fewer_it_stays_ambiguous(self):
        self.boxes(3)
        amp = self.amp('Amp')
        self.amp_channel(amp, 1, analog_input='3')
        _, [node] = self.feed()
        self.assertEqual((node['reason'], node['ambiguous']), ('3 possible sources', True))

    def test_a_question_label_has_no_dot_before_the_arrow(self):
        amp = self.amp('Amp')
        self.amp_channel(amp, 1, avb_stream='1')
        lay = L.layout(project_graph(self.project))
        [route] = lay.routes
        self.assertNotIn('· →', route.label)
        self.assertEqual(route.label, '? AVB 1')     # the slot names the input (PR 3.2)
