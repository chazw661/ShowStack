"""Comm devices and the comms patch (PR A: data and pages), server side.

A comm device (Device.kind == 'comm') is added from the device list, patched
on its own page, and shown read-only on the devices it is patched to. The
browser half is test_comm_devices_browser.py; the Comms tab is PR B.

    python manage.py test planner.tests.test_comm_devices \\
        --settings=audiopatch.test_settings
"""
import json

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from planner.connections import amp_sources, comm_patch, processor_sources
from planner.connections.graph import project_graph
from planner.connections.layout import layout
from planner.connections.tabs import ANALOG, DANTE, graph_view
from planner.models import (
    Amp, AmpChannel, AmpLocation, CommPort, Connection, Console, ConsoleInput, Device,
    DeviceInput, DeviceOutput, Location, Project, ProjectMember, UserProfile,
)
from planner.utils.console_patch import PortIndex

PLAIN_STATIC = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


def make_user(name, plan='paid', group='Editor'):
    user = User.objects.create_user(name, password='pw', is_staff=True)
    UserProfile.objects.update_or_create(user=user, defaults={'account_type': plan})
    user.groups.add(Group.objects.get(name=group))
    return User.objects.get(pk=user.pk)


def make_device(project, name, ins=8, outs=8, network='', **kw):
    d = Device.objects.create(project=project, name=name, input_count=ins, output_count=outs,
                              dante_network=network, **kw)
    DeviceInput.objects.bulk_create(
        DeviceInput(device=d, input_number=n, signal_name='') for n in range(1, ins + 1))
    DeviceOutput.objects.bulk_create(
        DeviceOutput(device=d, output_number=n, signal_name='') for n in range(1, outs + 1))
    return d


def make_comm(project, name, ins=4, outs=4, four=2, two=2, network='Comms 48k'):
    d = Device.objects.create(project=project, name=name, kind=Device.COMM, input_count=ins,
                              output_count=outs, four_wire_count=four, two_wire_count=two,
                              dante_network=network)
    comm_patch.sync_ports(d)
    return d


def inline_data(page):
    """The I/O grids of a device page, as it would post them back."""
    data = {}
    for formset in page.context['inline_admin_formsets']:
        fs = formset.formset
        data.update({f'{fs.prefix}-{k}': v for k, v in fs.management_form.initial.items()})
        for form in fs.forms:
            for name in form.fields:
                value = form[name].value()
                data[form[name].html_name] = value if value is not None else ''
    return data


def ct(model):
    return ContentType.objects.get_for_model(model)


class CommFixture:
    def setUp(self):
        super().setUp()
        call_command('setup_user_groups', stdout=open('/dev/null', 'w'))
        self.owner = make_user('paidtest')
        self.project = Project.objects.create(name='Show', owner=self.owner)
        self.rio = make_device(self.project, 'Rio SL', network='Main 96k')
        self.mk88 = make_device(self.project, 'MK88', network='Comms 48k')
        self.dvs = make_device(self.project, 'DVS FOH', ins=2, outs=2, network='comms 48K ')
        self.arc = make_comm(self.project, 'Arcadia')
        self.login(self.owner)

    def login(self, user, project=None):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = (project or self.project).pk
        session.save()

    def viewer(self):
        viewer = make_user('viewer1', 'free', 'Viewer')
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.owner)
        return viewer

    def url(self, device=None):
        return reverse('admin:planner_device_change', args=[(device or self.arc).pk])

    def inp(self, device, n):
        return DeviceInput.objects.get(device=device, input_number=n)

    def out(self, device, n):
        return DeviceOutput.objects.get(device=device, output_number=n)

    def comm_port(self, device, kind, n):
        return CommPort.objects.get(device=device, kind=kind, number=n)

    def post(self, device=None, fields=None, **patch):
        """Save the comm device's page: its stored values, with ``patch``
        ({'din1': text, 'dout2': text, '4w1_send': ..., '4w1_recv': ...,
        '4w1_cable': ..., '2w1_dest': ..., '2w1_cable': ...}) on top."""
        device = Device.objects.get(pk=(device or self.arc).pk)
        page = comm_patch.build(device)
        data = {'name': device.name, 'location': device.location_id or '',
                'input_count': device.input_count, 'output_count': device.output_count,
                'four_wire_count': device.four_wire_count,
                'two_wire_count': device.two_wire_count,
                'dante_network': device.dante_network,
                'primary_ip_address': device.primary_ip_address or '',
                'secondary_ip_address': device.secondary_ip_address or '',
                comm_patch.PRESENT: '1', '_continue': '1'}
        data.update(fields or {})
        names = {}
        for n, row in enumerate(page.din, 1):
            names[f'din{n}'] = row.cells['link']
        for n, row in enumerate(page.dout, 1):
            names[f'dout{n}'] = row.cells['link']
        for row in page.four_wire + page.two_wire:
            for key, cell in row.cells.items():
                names[f'{row.port.kind}{row.port.number}_{key}'] = cell
        for cell in names.values():
            data[cell.name] = cell.value
        for key, value in patch.items():
            data[names[key].name] = value
        return self.client.post(self.url(device), data)

    def links(self):
        """Every Connection as (from label, to label, transport, cable type)."""
        labels = comm_patch.port_labels(self.project.pk)
        return sorted((labels[(c.from_ct.model, c.from_id)], labels[(c.to_ct.model, c.to_id)],
                       c.transport, c.cable_type)
                      for c in Connection.objects.filter(project=self.project)
                      .select_related('from_ct', 'to_ct'))


@override_settings(STORAGES=PLAIN_STATIC)
class AddAndEditTests(CommFixture, TestCase):
    def test_device_list_has_both_add_buttons(self):
        page = self.client.get(reverse('admin:planner_device_changelist')).content.decode()
        add = reverse('admin:planner_device_add')
        self.assertIn(f'href="{add}" class="addlink">Add I/O device</a>', page)
        self.assertIn(f'href="{add}?kind=comm" class="addlink" id="add-comm-device">'
                      'Add comm device</a>', page)
        self.assertIn('Comm device', page)        # the Type column

    def test_add_form_asks_for_the_comm_fields(self):
        page = self.client.get(reverse('admin:planner_device_add') + '?kind=comm').content.decode()
        for label in ('Dante inputs', 'Dante outputs', '4-wire ports', '2-wire ports',
                      'Dante network'):
            self.assertIn(label, page)
        self.assertNotIn('Console connection', page)
        self.assertIn('New comm device', page)

    def test_adding_makes_a_comm_device_with_its_ports(self):
        r = self.client.post(reverse('admin:planner_device_add') + '?kind=comm', {
            'name': 'Arcadia B', 'location': '', 'input_count': 3, 'output_count': 2,
            'four_wire_count': 1, 'two_wire_count': 2, 'dante_network': 'Comms 48k',
            'primary_ip_address': '10.0.0.9', 'secondary_ip_address': ''})
        device = Device.objects.get(name='Arcadia B')
        self.assertRedirects(r, self.url(device))
        self.assertEqual((device.kind, device.project_id), ('comm', self.project.pk))
        self.assertEqual(device.inputs.count(), 3)
        self.assertEqual(device.outputs.count(), 2)
        self.assertEqual(sorted(device.comm_ports.values_list('kind', 'number')),
                         [('2w', 1), ('2w', 2), ('4w', 1)])

    def test_the_plain_add_form_still_makes_an_io_device(self):
        add = self.client.get(reverse('admin:planner_device_add'))
        self.assertNotContains(add, '4-wire ports')
        r = self.client.post(reverse('admin:planner_device_add'), {
            'name': 'Box', 'location': '', 'primary_ip_address': '', 'secondary_ip_address': '',
            'console_connection': '', 'dante_network': 'Main 96k', 'input_count': 2,
            'output_count': 2, **inline_data(add)})
        self.assertEqual(r.status_code, 302)
        device = Device.objects.get(name='Box')
        self.assertEqual((device.kind, device.dante_network), ('io', 'Main 96k'))
        self.assertFalse(device.comm_ports.exists())

    def test_comm_page_has_the_patch_grids_and_no_io_grids(self):
        page = self.client.get(self.url()).content.decode()
        self.assertIn('id="comm-patch"', page)
        for text in ('Dante In 1', 'Dante Out 4', '4W 2', '2W 1', 'name="comm-patch-present"'):
            self.assertIn(text, page)
        self.assertNotIn('device-input-cell', page)
        self.assertNotIn('dynamic-deviceoutput_set', page)
        self.assertIn('value="4W adapter"', page)       # the 4W cable type's default
        self.assertNotIn(' disabled>', page.split('id="comm-patch"')[1])    # an editor's boxes

    def test_io_page_is_unchanged_and_offers_the_dante_network(self):
        page = self.client.get(self.url(self.rio)).content.decode()
        self.assertNotIn('id="comm-patch"', page)
        self.assertIn('name="dante_network"', page)
        self.assertIn('<option value="Comms 48k"></option>', page)   # the project's networks

    def test_raising_a_count_adds_rows(self):
        self.post(fields={'input_count': 6, 'two_wire_count': 3})
        self.assertEqual(self.arc.inputs.count(), 6)
        self.assertEqual(self.arc.comm_ports.filter(kind='2w').count(), 3)

    def test_lowering_a_count_is_refused_while_a_port_past_it_is_patched(self):
        self.post(dout4='MK88 Out 1')
        r = self.post(fields={'output_count': 2})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'clear it before lowering the count')
        self.assertEqual(self.arc.outputs.count(), 4)
        self.assertEqual(len(self.links()), 1)
        # cleared in the same save: the rows go
        self.post(fields={'output_count': 2}, dout4='')
        self.assertEqual(self.arc.outputs.count(), 2)
        self.assertEqual(self.links(), [])

    def test_a_viewer_reads_the_page_and_cannot_save_it(self):
        self.post(dout1='MK88 Out 1')
        self.login(self.viewer())
        page = self.client.get(self.url())
        self.assertEqual(page.status_code, 200)
        text = page.content.decode()
        self.assertIn('value="MK88 Out 1"', text)
        self.assertIn(' disabled>', text)
        self.assertNotIn('autocomplete="off" list="comm-list-dout" data-comm-field="dout">', text)
        self.assertEqual(self.post(dout1='').status_code, 403)
        self.assertEqual(len(self.links()), 1)


@override_settings(STORAGES=PLAIN_STATIC)
class PickerTests(CommFixture, TestCase):
    def lists(self, device=None):
        return comm_patch.listing(comm_patch.all_sources(device or self.arc))

    def test_each_list_has_every_port_of_every_other_device(self):
        lists = self.lists()
        ins = [f'{d} In {n}' for d, count in (('DVS FOH', 2), ('MK88', 8)) for n in range(1, count + 1)]
        outs = [f'{d} Out {n}' for d, count in (('DVS FOH', 2), ('MK88', 8)) for n in range(1, count + 1)]
        far_in = [f'Rio SL In {n} [Main 96k]' for n in range(1, 9)]
        far_out = [f'Rio SL Out {n} [Main 96k]' for n in range(1, 9)]
        # Dante: this device's network first (compared ignoring case and
        # spaces), then the rest; an entry on another network names it.
        self.assertEqual(lists['din'], ins + far_in)
        self.assertEqual(lists['dout'], outs + far_out)
        # 4-wire is a cable: plain name order, no network.
        plain = sorted(ins + [f'Rio SL In {n}' for n in range(1, 9)])
        self.assertEqual(sorted(lists['send']), plain)
        self.assertEqual(lists['send'][:2], ['DVS FOH In 1', 'DVS FOH In 2'])
        self.assertEqual(lists['recv'][-1], 'Rio SL Out 8')
        self.assertFalse([t for texts in lists.values() for t in texts if 'Arcadia' in t])

    def test_another_comm_device_lists_its_dante_ports_only(self):
        make_comm(self.project, 'Arcadia B', ins=1, outs=1)
        lists = self.lists()
        self.assertIn('Arcadia B Dante Out 1', lists['din'])
        self.assertIn('Arcadia B Dante In 1', lists['dout'])
        self.assertFalse([t for f in ('send', 'recv') for t in lists[f] if 'Arcadia B' in t])

    def test_a_signal_name_leads_its_entry(self):
        DeviceOutput.objects.filter(pk=self.out(self.mk88, 3).pk).update(signal_name='Camera PL')
        self.assertIn('Camera PL · MK88 Out 3', self.lists()['dout'])

    def test_devices_of_one_name_stay_pickable(self):
        make_device(self.project, 'MK88', ins=1, outs=1, network='Comms 48k',
                    location=Location.objects.create(project=self.project, name='Truck'))
        lists = self.lists()
        self.assertIn('MK88 Out 1 (Truck)', lists['dout'])

    def test_comm_ports_are_in_no_other_picker(self):
        names = [s.text for s in amp_sources.all_sources(self.project)]
        names += [s.text for s in processor_sources.all_sources(self.project)]
        self.assertTrue(any('Rio SL Out 1' in n for n in names))
        self.assertFalse([n for n in names if 'Arcadia' in n])
        index = PortIndex(self.project.pk)
        self.assertFalse([p for p in list(index.inputs) + list(index.outputs)
                          if p.device_id == self.arc.pk])
        self.assertTrue([p for p in index.inputs if p.device_id == self.rio.pk])

    def test_the_console_page_cannot_patch_a_comm_port(self):
        foh = Console.objects.create(project=self.project, name='FOH')
        ch = ConsoleInput.objects.create(console=foh, input_ch='1', source='Kick')
        url = reverse('planner:console_patch', args=['input', ch.pk])
        state = self.client.get(url).json().get('state', '')
        r = self.client.post(url, json.dumps({'action': 'patch', 'state': state,
                                              'port': self.inp(self.arc, 1).pk}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 404)
        self.assertIsNone(self.inp(self.arc, 1).console_input_id)


@override_settings(STORAGES=PLAIN_STATIC)
class PatchTests(CommFixture, TestCase):
    def test_dante_rows_save_one_link_per_signal_the_way_the_signal_runs(self):
        r = self.post(din1='MK88 In 3', dout2='MK88 Out 3', dout3='DVS FOH Out 1')
        self.assertRedirects(r, self.url())
        self.assertEqual(self.links(), [
            ('Arcadia Dante Out 2', 'MK88 Out 3', 'dante', ''),
            ('Arcadia Dante Out 3', 'DVS FOH Out 1', 'dante', ''),
            ('MK88 In 3', 'Arcadia Dante In 1', 'dante', ''),
        ])
        page = self.client.get(self.url()).content.decode()
        for value in ('MK88 In 3', 'MK88 Out 3', 'DVS FOH Out 1'):
            self.assertIn(f'value="{value}"', page)
        self.assertFalse([m for m in get_messages(r.wsgi_request) if m.level_tag == 'warning'])

    def test_a_4w_row_sets_both_directions_with_the_default_cable(self):
        self.post(**{'4w1_send': 'Rio SL In 3', '4w1_recv': 'Rio SL Out 5'})
        self.assertEqual(self.links(), [
            ('Arcadia 4W 1', 'Rio SL In 3', 'analog', '4W adapter'),
            ('Rio SL Out 5', 'Arcadia 4W 1', 'analog', '4W adapter'),
        ])
        self.post(**{'4w1_cable': 'XLR pair'})
        self.assertEqual({c for *_, c in self.links()}, {'XLR pair'})
        self.post(**{'4w1_send': ''})
        self.assertEqual(self.links(), [('Rio SL Out 5', 'Arcadia 4W 1', 'analog', 'XLR pair')])

    def test_a_2w_row_is_free_text(self):
        self.post(**{'2w1_dest': 'Wired BP chain SL', '2w1_cable': 'XLR3',
                     '2w2_dest': 'Venue RTS tie-line'})
        self.assertEqual(list(self.arc.comm_ports.filter(kind='2w')
                              .values_list('number', 'destination', 'cable_type')),
                         [(1, 'Wired BP chain SL', 'XLR3'), (2, 'Venue RTS tie-line', '')])
        self.assertEqual(self.links(), [])
        self.assertContains(self.client.get(self.url()), 'value="Wired BP chain SL"')

    def test_text_that_is_no_entry_is_an_error_and_nothing_is_saved(self):
        r = self.post(dout1='MK88 Out 3', dout2='the truck')
        self.assertEqual(r.status_code, 200)
        text = r.content.decode()
        self.assertIn('Pick an entry from the list', text)
        self.assertIn('value="the truck"', text)        # what was typed is kept
        self.assertIn('value="MK88 Out 3"', text)
        self.assertEqual(self.links(), [])

    def test_a_dante_in_does_not_take_an_output_nor_a_4w_send(self):
        for patch in ({'din1': 'MK88 Out 3'}, {'dout1': 'MK88 In 3'},
                      {'4w1_send': 'MK88 Out 3'}, {'4w1_recv': 'MK88 In 3'}):
            self.assertContains(self.post(**patch), 'Pick an entry from the list')
        self.assertEqual(self.links(), [])

    def test_a_patch_moves_between_rows_in_one_save(self):
        self.post(dout1='MK88 Out 3')
        self.assertRedirects(self.post(dout1='', dout2='MK88 Out 3'), self.url())
        self.assertEqual(self.links(), [('Arcadia Dante Out 2', 'MK88 Out 3', 'dante', '')])

    def test_one_output_is_not_fed_twice(self):
        r = self.post(dout1='MK88 Out 3', dout2='MK88 Out 3')
        self.assertContains(r, 'MK88 Out 3 is already picked on Dante Out 1.')
        self.post(dout1='MK88 Out 3')
        other = make_comm(self.project, 'Arcadia B')
        r = self.post(other, dout1='MK88 Out 3')
        self.assertContains(r, 'MK88 Out 3 is already fed by Arcadia Dante Out 1.')
        self.assertEqual(len(self.links()), 1)
        # an input can feed several Dante Ins
        self.post(din1='MK88 In 1', din2='MK88 In 1')
        self.assertEqual(len(self.links()), 3)

    def test_two_comm_devices_share_one_link_seen_from_both_pages(self):
        other = make_comm(self.project, 'Arcadia B')
        self.post(dout1='Arcadia B Dante In 2')
        self.assertEqual(self.links(), [('Arcadia Dante Out 1', 'Arcadia B Dante In 2', 'dante', '')])
        self.assertContains(self.client.get(self.url(other)), 'value="Arcadia Dante Out 1"')
        # its Dante Out goes to one place: B cannot take it for another In
        self.assertContains(self.post(other, din1='Arcadia Dante Out 1'),
                            'already picked on Dante In 1')
        # cleared from B's page
        self.post(other, din2='')
        self.assertEqual(self.links(), [])

    def test_a_dante_out_already_going_somewhere_is_not_taken_from_the_other_page(self):
        other = make_comm(self.project, 'Arcadia B')
        self.post(dout1='MK88 Out 1')
        r = self.post(other, din1='Arcadia Dante Out 1')
        self.assertContains(r, 'Arcadia Dante Out 1 already goes to MK88 Out 1.')

    def test_another_network_is_allowed_and_warned_about(self):
        r = self.post(dout1='Rio SL Out 2 [Main 96k]', din1='MK88 In 1')
        self.assertRedirects(r, self.url())
        warnings = [str(m) for m in get_messages(r.wsgi_request) if m.level_tag == 'warning']
        self.assertEqual(len(warnings), 1)
        self.assertIn('Dante Out 1: Rio SL is on Dante network “Main 96k”, not “Comms 48k”',
                      warnings[0])
        page = self.client.get(self.url()).content.decode()
        self.assertEqual(page.count('class="comm-warning">'), 1)
        self.assertIn('"Rio SL Out 2 [Main 96k]": "Main 96k"', page)     # for the live warning
        graph = project_graph(self.project)
        self.assertEqual([(w['kind'], w['networks']) for w in graph['warnings']],
                         [('dante_network', ['Comms 48k', 'Main 96k'])])
        wiring = self.client.get(reverse('planner:wiring_diagram')).content.decode()
        self.assertIn('Dante link between different Dante networks', wiring)
        self.assertIn('Arcadia → Rio SL', wiring)

    def test_no_warning_when_a_network_is_not_set_or_the_cable_is_analog(self):
        Device.objects.filter(pk=self.rio.pk).update(dante_network='')
        self.post(dout1='Rio SL Out 2', **{'4w1_send': 'Rio SL In 1'})
        self.assertEqual(project_graph(self.project)['warnings'], [])
        Device.objects.filter(pk=self.rio.pk).update(dante_network='Main 96k')
        self.assertEqual(len(project_graph(self.project)['warnings']), 1)   # the Dante one only

    def test_a_post_without_the_grids_changes_no_patch(self):
        self.post(dout1='MK88 Out 3')
        r = self.client.post(self.url(), {
            'name': 'Arcadia 2', 'location': '', 'input_count': 4, 'output_count': 4,
            'four_wire_count': 2, 'two_wire_count': 2, 'dante_network': 'Comms 48k',
            'primary_ip_address': '', 'secondary_ip_address': ''})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.links(), [('Arcadia 2 Dante Out 1', 'MK88 Out 3', 'dante', '')])


@override_settings(STORAGES=PLAIN_STATIC)
class OtherDevicePageTests(CommFixture, TestCase):
    def test_each_port_shows_its_comms_link_read_only(self):
        self.post(din1='MK88 In 3', dout2='MK88 Out 3',
                  **{'4w1_send': 'Rio SL In 3', '4w1_recv': 'Rio SL Out 5'})
        href = f'href="{self.url()}#comm-patch"'
        mk88 = self.client.get(self.url(self.mk88)).content.decode()
        self.assertIn(f'<div class="ss-comm-note"><a {href}>← Arcadia Dante Out 2</a></div>', mk88)
        self.assertIn(f'<div class="ss-comm-note"><a {href}>→ Arcadia Dante In 1</a></div>', mk88)
        self.assertEqual(mk88.count('class="ss-comm-note"'), 2)
        rio = self.client.get(self.url(self.rio)).content.decode()
        self.assertIn(f'<a {href}>← Arcadia 4W 1 send</a>', rio)
        self.assertIn(f'<a {href}>→ Arcadia 4W 1 receive</a>', rio)
        notes = comm_patch.port_notes(self.mk88)
        self.assertEqual(notes[('out', self.out(self.mk88, 3).pk)][0]['text'],
                         '← Arcadia Dante Out 2')
        self.assertEqual(notes[('in', self.inp(self.mk88, 3).pk)][0]['text'],
                         '→ Arcadia Dante In 1')

    def test_saving_the_other_device_keeps_the_links(self):
        self.post(dout2='MK88 Out 3')
        page = self.client.get(self.url(self.mk88))
        data = {'name': 'MK88 renamed', 'location': '', 'primary_ip_address': '',
                'secondary_ip_address': '', 'console_connection': '', 'dante_network': 'Comms 48k'}
        data.update(inline_data(page))
        r = self.client.post(self.url(self.mk88), data)
        self.assertEqual(r.status_code, 302, r.content.decode()[:300] if r.status_code == 200 else '')
        self.assertEqual(self.links(), [('Arcadia Dante Out 2', 'MK88 renamed Out 3', 'dante', '')])
        self.assertContains(self.client.get(self.url()), 'value="MK88 renamed Out 3"')


@override_settings(STORAGES=PLAIN_STATIC)
class RulesTests(CommFixture, TestCase):
    def conn(self, frm, to, transport, project=None):
        return Connection(project=project or self.project, from_ct=ct(type(frm)), from_id=frm.pk,
                          to_ct=ct(type(to)), to_id=to.pk, transport=transport)

    def test_the_five_comms_links_and_nothing_else(self):
        arc, rio = self.arc, self.rio
        four, two = self.comm_port(arc, '4w', 1), self.comm_port(arc, '2w', 1)
        good = [
            (self.out(arc, 1), self.out(rio, 1), 'dante'),
            (self.inp(rio, 1), self.inp(arc, 1), 'dante'),
            (four, self.inp(rio, 2), 'analog'),
            (self.out(rio, 2), four, 'analog'),
        ]
        for frm, to, transport in good:
            self.conn(frm, to, transport).save()
        bad = [
            (self.out(rio, 1), self.out(self.mk88, 1), 'dante'),     # I/O to I/O
            (self.inp(rio, 1), self.inp(self.mk88, 1), 'dante'),
            (self.out(arc, 2), self.inp(rio, 5), 'dante'),           # Dante Out to an input
            (self.out(rio, 3), self.inp(arc, 2), 'dante'),           # an output to Dante In
            (self.out(arc, 2), self.inp(arc, 2), 'dante'),           # itself
            (self.out(arc, 2), self.out(rio, 3), 'analog'),          # wrong transport
            (four, self.out(rio, 3), 'analog'),                      # 4W send to an output
            (two, self.inp(rio, 4), 'analog'),                       # a 2W port
            (self.out(arc, 1), self.out(rio, 4), 'dante'),           # that Dante Out is taken
        ]
        for frm, to, transport in bad:
            with self.assertRaises(ValidationError, msg=(frm, to, transport)):
                self.conn(frm, to, transport).save()
        self.assertEqual(Connection.objects.count(), len(good))

    def test_both_ends_must_be_in_the_project(self):
        elsewhere = Project.objects.create(name='Other', owner=self.owner)
        box = make_device(elsewhere, 'MK88')
        with self.assertRaises(ValidationError):
            self.conn(self.out(self.arc, 1), self.out(box, 1), 'dante').save()
        with self.assertRaises(ValidationError):
            self.conn(self.out(self.arc, 1), self.out(box, 1), 'dante', elsewhere).save()
        # and its ports are in no list here: "Truck Out 1" is not an entry
        Device.objects.filter(pk=box.pk).update(name='Truck')
        self.assertContains(self.post(dout1='Truck Out 1'), 'Pick an entry from the list')
        self.assertEqual(Connection.objects.count(), 0)

    def test_a_comm_port_never_feeds_an_amp(self):
        amp = Amp.objects.create(project=self.project, name='A1',
                                 location=AmpLocation.objects.create(project=self.project,
                                                                     name='SL'))
        channel = (AmpChannel.objects.filter(amp=amp).first()
                   or AmpChannel.objects.create(amp=amp, channel_number=1))
        with self.assertRaises(ValidationError):
            self.conn(self.out(self.arc, 1), channel, 'analog').save()
        self.conn(self.out(self.rio, 1), channel, 'analog').save()      # an I/O output still does


@override_settings(STORAGES=PLAIN_STATIC)
class CascadeTests(CommFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.post(din1='MK88 In 3', dout2='MK88 Out 3',
                  **{'4w1_send': 'Rio SL In 3', '4w1_recv': 'Rio SL Out 5'})
        self.assertEqual(Connection.objects.count(), 4)

    def test_deleting_the_other_device_deletes_its_links(self):
        self.mk88.delete()
        self.assertEqual([t for *_, t, _ in self.links()], ['analog', 'analog'])

    def test_deleting_the_comm_device_deletes_them_all(self):
        self.arc.delete()
        self.assertEqual(Connection.objects.count(), 0)

    def test_deleting_one_port_deletes_its_link(self):
        self.out(self.mk88, 3).delete()
        self.inp(self.rio, 3).delete()
        self.comm_port(self.arc, '4w', 1).delete()
        self.assertEqual(self.links(), [('MK88 In 3', 'Arcadia Dante In 1', 'dante', '')])

    def test_deleting_through_the_admin(self):
        r = self.client.post(reverse('admin:planner_device_delete', args=[self.rio.pk]),
                             {'post': 'yes'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Connection.objects.count(), 2)


@override_settings(STORAGES=PLAIN_STATIC)
class DuplicationTests(CommFixture, TestCase):
    def test_a_copy_has_the_comm_device_its_ports_and_its_links(self):
        self.post(din1='MK88 In 3', dout2='MK88 Out 3',
                  **{'4w1_send': 'Rio SL In 3', '4w1_recv': 'Rio SL Out 5',
                     '2w1_dest': 'Wired BP chain SL', '2w1_cable': 'XLR3'})
        before = self.links()
        copy = self.project.duplicate(new_name='Copy')
        arc = Device.objects.get(project=copy, name='Arcadia')
        self.assertEqual((arc.kind, arc.dante_network, arc.four_wire_count, arc.two_wire_count),
                         ('comm', 'Comms 48k', 2, 2))
        self.assertEqual(Device.objects.get(project=copy, name='Rio SL').dante_network, 'Main 96k')
        self.assertEqual(list(arc.comm_ports.filter(kind='2w', number=1)
                              .values_list('destination', 'cable_type')),
                         [('Wired BP chain SL', 'XLR3')])
        labels = comm_patch.port_labels(copy.pk)
        copied = sorted((labels[(c.from_ct.model, c.from_id)], labels[(c.to_ct.model, c.to_id)],
                         c.transport, c.cable_type)
                        for c in Connection.objects.filter(project=copy))
        self.assertEqual(copied, before)
        self.assertEqual(self.links(), before)          # the original is untouched
        self.login(self.owner, copy)
        self.assertContains(self.client.get(self.url(arc)), 'value="MK88 Out 3"')


@override_settings(STORAGES=PLAIN_STATIC)
class WiringTests(CommFixture, TestCase):
    def test_a_project_with_no_comm_device_reads_as_before(self):
        plain = Project.objects.create(name='Plain', owner=self.owner)
        make_device(plain, 'Box')
        graph = project_graph(plain)
        self.assertEqual([sorted(n) for n in graph['nodes']],
                         [['console_connection', 'id', 'kind', 'label', 'ports', 'primary_ip',
                           'secondary_ip']])
        self.assertNotIn('comm', json.dumps(graph))

    def test_comm_links_are_listed_not_drawn(self):
        self.post(din1='MK88 In 3', dout2='MK88 Out 3', dout3='MK88 Out 4',
                  **{'4w1_send': 'Rio SL In 3', '4w1_recv': 'Rio SL Out 5'})
        graph = project_graph(self.project)
        comm = [e for e in graph['edges'] if e.get('comm')]
        self.assertEqual(sorted((e['label'], e['transports'][0]) for e in comm), [
            ('4W 1 → In 3', 'analog'), ('Dante Out 2–3 → Out 3–4', 'dante'),
            ('In 3 → Dante In 1', 'dante'), ('Out 5 → 4W 1', 'analog')])
        self.assertTrue(all(e['status'] == 'confirmed' for e in comm))
        node = next(n for n in graph['nodes'] if n['label'] == 'Arcadia')
        self.assertEqual((node['device_kind'], node['dante_network']), ('comm', 'Comms 48k'))
        lay = layout(graph)
        self.assertEqual(lay.not_drawn, [])
        self.assertEqual(lay.routes, [])
        self.assertIn('Comm device', [b.sub for b in lay.boxes if b.label == 'Arcadia'])

        page = self.client.get(reverse('planner:wiring_diagram')).content.decode()
        self.assertIn('Connections (4)', page)
        self.assertIn('<td>Arcadia · Dante Out 2–3</td><td>MK88 · Out 3–4</td>'
                      '<td>Dante (network) · see the Comms tab</td>', page)
        self.assertIn('<td>Arcadia · 4W 1</td><td>Rio SL · In 3</td>'
                      '<td>Analogue · 4W adapter · see the Comms tab</td>', page)
        self.assertNotIn('Not drawn', page)

    def test_each_tab_lists_its_own_transport_and_dante_shows_the_comm_device(self):
        self.post(dout2='MK88 Out 3', **{'4w1_recv': 'Rio SL Out 5'})
        full = project_graph(self.project)
        dante, analog = graph_view(full, DANTE), graph_view(full, ANALOG)
        self.assertEqual([e['transports'] for e in dante['edges']], [['dante']])
        self.assertEqual([e['transports'] for e in analog['edges']], [['analog']])
        self.assertEqual([n['label'] for n in dante['nodes']], ['Arcadia'])
        self.assertEqual(analog['nodes'], [])
        page = self.client.get(reverse('planner:wiring_diagram') + '?view=dante').content.decode()
        self.assertIn('Connections (1)', page)
        self.assertNotIn('No console or Dante I/O device yet', page)
        # a comm device has no Console connection to set
        self.assertNotIn(f'{self.url()}"', page.split('wd-banner')[-1] if 'wd-banner' in page else '')
        pdf = self.client.get(reverse('planner:wiring_diagram_pdf'))
        self.assertEqual(pdf.status_code, 200)

    def test_other_pages_that_list_devices_include_comm_devices(self):
        Device.objects.filter(pk=self.arc.pk).update(primary_ip_address='10.9.9.9')
        for name in ('planner:all_devices_pdf_export', 'planner:wiring_diagram_pdf'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get(
            reverse('planner:device_pdf_export', args=[self.arc.pk])).status_code, 200)
