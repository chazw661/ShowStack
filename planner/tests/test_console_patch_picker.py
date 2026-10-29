"""Patching from the Console page: the picker endpoint and the editable cell.

Under test: planner/utils/console_patch_edit.py, planner/views_console_patch.py
and the Patch column's editable / read-only rendering. The browser half (touch,
iPad sizes, unsaved edits survive) is test_console_patch_picker_browser.py.

Run with::

    python manage.py test planner.tests.test_console_patch_picker \\
        --settings=audiopatch.test_settings
"""

import json
from unittest import mock

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from planner.forms import DeviceInputInlineForm, DeviceOutputInlineForm
from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput,
    ConsoleStereoOutput, Device, DeviceInput, DeviceOutput, Project, ProjectMember,
)
from planner.utils import device_patch

# Static files by their own names, whatever is in staticfiles/.
PLAIN_STATIC = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


CONSOLE_MODELS = ('console', 'consoleinput', 'consoleauxoutput', 'consolematrixoutput',
                  'consolestereooutput', 'device', 'deviceinput', 'deviceoutput')


def staff(name):
    """A staff user holding the global Editor group's console permissions --
    what every invited user has in prod. Deliberately the worst case for a
    viewer: global edit rights, viewer on this project. Only the per-project
    role may decide."""
    user = User.objects.create_user(name, password='pw', is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(
        content_type__app_label='planner', content_type__model__in=CONSOLE_MODELS))
    return user


def make_device(project, name, ins=8, outs=4):
    d = Device.objects.create(project=project, name=name, input_count=ins, output_count=outs)
    DeviceInput.objects.bulk_create(
        DeviceInput(device=d, input_number=n, signal_name='') for n in range(1, ins + 1))
    DeviceOutput.objects.bulk_create(
        DeviceOutput(device=d, output_number=n, signal_name='') for n in range(1, outs + 1))
    return d


class PickerFixture:
    """The shows, users and helpers; mixed into a TestCase here and into a
    live-server case by the browser tests."""

    def setUp(self):
        super().setUp()
        self.owner = staff('owner')
        self.project = Project.objects.create(name='Show A', owner=self.owner)
        self.foh = Console.objects.create(project=self.project, name='FOH')
        self.kick = ConsoleInput.objects.create(console=self.foh, input_ch='1', source='Kick')
        self.snare = ConsoleInput.objects.create(console=self.foh, input_ch='2', source='Snare')
        self.blank = ConsoleInput.objects.create(console=self.foh, input_ch='3', source='')
        self.aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='1', name='Drum Wedge')
        self.mtx = ConsoleMatrixOutput.objects.create(console=self.foh, matrix_number='1', name='Lobby')
        self.st_l = ConsoleStereoOutput.objects.create(console=self.foh, stereo_type='L', name='PA Left')
        self.box = make_device(self.project, 'Stage Box A')
        self.box_b = make_device(self.project, 'Stage Box B')

        # Another show, another owner.
        self.other_owner = staff('other')
        self.other = Project.objects.create(name='Show B', owner=self.other_owner)
        self.other_console = Console.objects.create(project=self.other, name='FOH B')
        self.other_kick = ConsoleInput.objects.create(console=self.other_console,
                                                      input_ch='1', source='Kick')
        self.other_box = make_device(self.other, 'Their Box')

        self.as_user(self.owner, self.project)

    def as_user(self, user, project):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = project.pk
        session.save()

    def member(self, name, role, project=None):
        user = staff(name)
        self.join(user, project or self.project, role)
        return user

    def join(self, user, project, role):
        ProjectMember.objects.create(user=user, project=project, role=role,
                                     invited_by=project.owner)

    def url(self, channel):
        kind = {ConsoleInput: 'in', ConsoleAuxOutput: 'aux',
                ConsoleMatrixOutput: 'mtx', ConsoleStereoOutput: 'st'}[type(channel)]
        return reverse('planner:console_patch', args=[kind, channel.pk])

    def inport(self, n, device=None):
        return DeviceInput.objects.get(device=device or self.box, input_number=n)

    def out(self, n, device=None):
        return DeviceOutput.objects.get(device=device or self.box, output_number=n)

    def picker(self, channel):
        r = self.client.get(self.url(channel))
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def post(self, channel, port, action='patch', mode='', state=None, name=''):
        if state is None:
            state = self.picker(channel)['state']
        return self.client.post(self.url(channel), json.dumps(
            {'action': action, 'port': port.pk, 'mode': mode, 'state': state, 'name': name}),
            content_type='application/json')

    def link(self, port, channel):
        DeviceInput.objects.filter(pk=port.pk).update(console_input=channel,
                                                      signal_name=channel.source)

    def snapshot(self):
        return (list(DeviceInput.objects.order_by('pk').values_list(
                    'signal_name', 'console_input_id')),
                list(DeviceOutput.objects.order_by('pk').values_list(
                    'signal_name', 'content_type_id', 'object_id')))


class PickerBase(PickerFixture, TestCase):
    pass


class PickerReadTests(PickerBase):

    def test_picker_lists_project_devices_with_free_counts_and_ports(self):
        self.link(self.inport(2), self.snare)
        DeviceInput.objects.filter(pk=self.inport(3).pk).update(signal_name='Talkback')
        data = self.picker(self.kick)
        self.assertEqual([d['name'] for d in data['devices']], ['Stage Box A', 'Stage Box B'])
        box = data['devices'][0]
        self.assertEqual((box['free'], box['total']), (6, 8))
        ports = {p['number']: p for p in box['ports']}
        self.assertTrue(ports[1]['free'])
        self.assertEqual((ports[2]['free'], ports[2]['name']), (False, 'Snare'))
        self.assertEqual((ports[3]['free'], ports[3]['name']), (False, 'Talkback'))
        self.assertEqual(data['channel']['label'], 'Ch 1')
        self.assertEqual(data['feeds'], [])
        self.assertIn('ss-patch-edit', data['cell_html'])
        # Only this project's devices, never another show's.
        self.assertNotIn('Their Box', json.dumps(data))

    def test_output_picker_lists_output_ports(self):
        data = self.picker(self.st_l)
        self.assertEqual(data['side'], 'Out')
        self.assertEqual(data['devices'][0]['total'], 4)


class PatchTests(PickerBase):

    def test_patch_an_input_links_and_names_the_port(self):
        r = self.post(self.kick, self.inport(1))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.inport(1).console_input, self.kick)
        self.assertEqual(self.inport(1).signal_name, 'Kick')
        data = r.json()
        self.assertIn('Stage Box A</span><span class="ss-patch-port"> · In 1', data['cell_html'])
        self.assertIn('<strong>7</strong> free inputs', data['free_html'])

    def test_patch_aux_matrix_and_stereo(self):
        for n, bus in ((1, self.aux), (2, self.mtx), (3, self.st_l)):
            self.assertEqual(self.post(bus, self.out(n)).status_code, 200)
            self.assertEqual(self.out(n).console_output, bus)
            self.assertEqual(self.out(n).signal_name, bus.name)
        self.assertIn('ss-patch-linked', self.picker(self.st_l)['cell_html'])

    def test_same_storage_as_the_device_page(self):
        """A port patched here is stored exactly as a pick on the device page."""
        self.post(self.kick, self.inport(1))
        form = DeviceInputInlineForm(
            data={'input_number': 1, 'signal_name': 'Kick',
                  'link_ref': device_patch.input_ref(self.kick.pk)},
            instance=self.inport(1, self.box_b), project_id=self.project.pk)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        here, there = self.inport(1), self.inport(1, self.box_b)
        self.assertEqual((here.signal_name, here.console_input_id),
                         (there.signal_name, there.console_input_id))
        # And the device page shows it as a linked pick.
        reread = DeviceInputInlineForm(instance=here, project_id=self.project.pk)
        self.assertEqual(reread.initial['link_ref'], f'in:{self.kick.pk}')

        for n, bus in ((1, self.aux), (2, self.st_l)):
            self.post(bus, self.out(n))
            form = DeviceOutputInlineForm(
                data={'output_number': n, 'signal_name': bus.name,
                      'link_ref': device_patch.output_ref(type(bus), bus.pk)},
                instance=self.out(n, self.box_b), project_id=self.project.pk)
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
            here, there = self.out(n), self.out(n, self.box_b)
            self.assertEqual((here.signal_name, here.content_type_id, here.object_id),
                             (there.signal_name, there.content_type_id, there.object_id))

    def test_used_port_is_refused(self):
        DeviceInput.objects.filter(pk=self.inport(1).pk).update(signal_name='Talkback')
        before = self.snapshot()
        r = self.post(self.kick, self.inport(1))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['error'], 'port_taken')
        self.assertEqual(self.snapshot(), before)



class UnnamedChannelTests(PickerBase):
    """An unnamed channel can be patched: the link is stored, the port takes
    the name the page shows (typed and unsaved, else saved, else blank), and
    saving a name later fills the port."""

    def setUp(self):
        super().setUp()
        self.blank_aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='2', name='')

    def test_unnamed_input_is_linked_with_a_blank_name(self):
        r = self.post(self.blank, self.inport(1))
        self.assertEqual(r.status_code, 200, r.content)
        port = self.inport(1)
        self.assertEqual((port.console_input, port.signal_name), (self.blank, ''))
        self.assertIn('Stage Box A</span><span class="ss-patch-port"> · In 1', r.json()['cell_html'])

    def test_unnamed_bus_is_linked_with_a_blank_name(self):
        self.assertEqual(self.post(self.blank_aux, self.out(1)).status_code, 200)
        self.assertEqual((self.out(1).console_output, self.out(1).signal_name),
                         (self.blank_aux, ''))

    def test_naming_and_saving_the_channel_later_fills_the_port(self):
        """The rename propagation covers blank -> a name."""
        self.post(self.blank, self.inport(1))
        self.post(self.blank_aux, self.out(1))
        self.blank.source = 'Spare Vox'
        self.blank.save()
        self.blank_aux.name = 'Sidefill'
        self.blank_aux.save()
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.blank, 'Spare Vox'))
        self.assertEqual((self.out(1).console_output, self.out(1).signal_name),
                         (self.blank_aux, 'Sidefill'))

    def test_a_typed_unsaved_name_names_the_port_and_leaves_the_channel(self):
        r = self.post(self.blank, self.inport(1), name='  Spare Vox ')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.blank, 'Spare Vox'))
        self.blank.refresh_from_db()
        self.assertEqual(self.blank.source, '')   # the console form was not saved
        # Saving the page with that name: they agree, and the link holds.
        self.blank.source = 'Spare Vox'
        self.blank.save()
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.blank, 'Spare Vox'))

    def test_a_typed_rename_of_a_named_channel_is_used_too(self):
        self.post(self.kick, self.inport(1), name='Kick In')
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.kick, 'Kick In'))
        self.kick.refresh_from_db()
        self.assertEqual(self.kick.source, 'Kick')

    def test_a_blank_typed_name_falls_back_to_the_saved_one(self):
        self.post(self.kick, self.inport(1), name='')
        self.assertEqual(self.inport(1).signal_name, 'Kick')

    def test_a_name_too_long_for_a_port_is_refused(self):
        before = self.snapshot()
        r = self.post(self.blank, self.inport(1), name='x' * 101)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error'], 'name_too_long')
        self.assertEqual(self.snapshot(), before)

    def test_a_linked_port_with_a_blank_name_is_used_not_free(self):
        self.post(self.blank, self.inport(1))
        data = self.picker(self.kick)
        box = data['devices'][0]
        port1 = next(p for p in box['ports'] if p['number'] == 1)
        self.assertEqual((port1['free'], port1['linked'], port1['name']), (False, True, ''))
        self.assertEqual(box['free'], 7)
        self.assertIn('<strong>7</strong> free inputs', data['free_html'])
        self.assertIn('2-8', data['free_html'])
        # And it cannot be patched to another channel.
        before = self.snapshot()
        r = self.post(self.kick, self.inport(1))
        self.assertEqual((r.status_code, r.json()['error']), (409, 'port_taken'))
        self.assertEqual(self.snapshot(), before)

    def test_unpatch_an_unnamed_channel(self):
        self.post(self.blank, self.inport(1))
        self.assertEqual(self.post(self.blank, self.inport(1), action='unpatch').status_code, 200)
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name), (None, ''))

    def test_device_page_keeps_the_link_of_a_blank_named_port(self):
        """Saving the device page with that row untouched (blank name, link
        still in the hidden field) must not silently unlink it; clearing a
        name that was there still clears both."""
        self.post(self.blank, self.inport(1))
        page = DeviceInputInlineForm(instance=self.inport(1), project_id=self.project.pk)
        form = DeviceInputInlineForm(
            data={'input_number': 1, 'signal_name': '', 'link_ref': page.initial['link_ref']},
            instance=self.inport(1), project_id=self.project.pk, initial=page.initial)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(self.inport(1).console_input, self.blank)

        self.post(self.kick, self.inport(2))
        page = DeviceInputInlineForm(instance=self.inport(2), project_id=self.project.pk)
        form = DeviceInputInlineForm(
            data={'input_number': 2, 'signal_name': '', 'link_ref': page.initial['link_ref']},
            instance=self.inport(2), project_id=self.project.pk)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual((self.inport(2).console_input, self.inport(2).signal_name), (None, ''))


class NameNotSavedTests(PickerBase):
    """A linked port whose name is not its channel's saved name -- patched
    with a typed name and the console page never saved -- is flagged in the
    Patch cell, in the picker, and on the I/O device page. An unnamed
    channel's blank port gets a placeholder on the device page instead."""

    def setUp(self):
        super().setUp()
        self.blank_aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='2', name='')

    def device_page(self, device=None):
        r = self.client.get(reverse('admin:planner_device_change', args=[(device or self.box).pk]))
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    def test_cell_flags_a_typed_name_until_the_channel_is_saved(self):
        r = self.post(self.blank, self.inport(1), name='Spare Vox')
        self.assertIn('name not saved', r.json()['cell_html'])
        feed, = self.picker(self.blank)['feeds']
        self.assertEqual((feed['unsaved'], feed['port_name'], feed['saved_name']),
                         (True, 'Spare Vox', ''))
        self.blank.source = 'Spare Vox'
        self.blank.save()
        data = self.picker(self.blank)
        self.assertNotIn('name not saved', data['cell_html'])
        self.assertFalse(data['feeds'][0]['unsaved'])

    def test_cell_flags_a_typed_rename_with_the_saved_name(self):
        self.post(self.kick, self.inport(1), name='Kick In')
        data = self.picker(self.kick)
        self.assertEqual(data['feeds'][0]['saved_name'], 'Kick')
        self.assertIn('saved name is “Kick”', data['cell_html'])
        self.assertIn('name not saved', data['cell_html'])

    def test_bus_is_flagged_too(self):
        self.post(self.blank_aux, self.out(1), name='Sidefill')
        self.assertIn('name not saved', self.picker(self.blank_aux)['cell_html'])

    def test_no_flag_when_names_agree_or_the_port_is_blank(self):
        self.post(self.kick, self.inport(1))
        self.post(self.blank, self.inport(2))
        self.assertNotIn('name not saved', self.picker(self.kick)['cell_html'])
        self.assertNotIn('name not saved', self.picker(self.blank)['cell_html'])

    def test_read_only_cell_is_flagged(self):
        self.post(self.kick, self.inport(1), name='Kick In')
        viewer = self.member('viewer', 'viewer')
        self.as_user(viewer, self.project)
        page = self.client.get(reverse('admin:planner_console_change', args=[self.foh.pk]))
        html = page.content.decode()
        self.assertNotIn('ss-patch-edit', html)
        self.assertIn('ss-patch-unsaved', html)

    def test_device_page_placeholder_for_an_unnamed_channel(self):
        self.post(self.blank, self.inport(1))
        self.post(self.blank_aux, self.out(1))
        page = self.device_page()
        self.assertIn('placeholder="linked to FOH Ch 3 (unnamed)"', page)
        self.assertIn('placeholder="linked to FOH Aux 2 (unnamed)"', page)
        self.assertNotIn('ss-link-note">', page)

    def test_device_page_notes_a_name_not_saved(self):
        self.post(self.kick, self.inport(1), name='Kick In')
        self.post(self.blank, self.inport(2), name='Spare Vox')
        self.post(self.blank_aux, self.out(1), name='Sidefill')
        page = self.device_page()
        self.assertIn('value="Kick In"', page)   # shown as stored, not as the channel
        self.assertIn('name not saved — FOH Ch 1 is saved as “Kick”', page)
        self.assertIn('name not saved — FOH Ch 3 is unnamed', page)
        self.assertIn('name not saved — FOH Aux 2 is unnamed', page)

    def test_device_page_has_no_note_once_saved(self):
        self.post(self.kick, self.inport(1))
        self.post(self.blank, self.inport(2), name='Spare Vox')
        self.blank.source = 'Spare Vox'
        self.blank.save()
        page = self.device_page()
        self.assertNotIn('name not saved', page)
        self.assertNotIn('linked to', page)

    def test_device_page_save_leaves_a_flagged_port_alone(self):
        """Untouched on the device page, the row has not changed, so saving
        the page (which saves changed rows only) keeps its name and link."""
        self.post(self.kick, self.inport(1), name='Kick In')
        page = DeviceInputInlineForm(instance=self.inport(1), project_id=self.project.pk)
        self.assertEqual(page.initial.get('signal_name', self.inport(1).signal_name), 'Kick In')
        form = DeviceInputInlineForm(
            data={'input_number': 1, 'signal_name': 'Kick In',
                  'link_ref': page.initial['link_ref']},
            instance=self.inport(1), project_id=self.project.pk)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.has_changed())

    def test_device_page_queries_do_not_grow_with_linked_ports(self):
        def count():
            with CaptureQueriesContext(connection) as q:
                self.device_page()
            return len(q)
        # One of each bus type first: each linked type is one more prefetch.
        self.post(self.kick, self.inport(1))
        for n, bus in ((1, self.aux), (2, self.mtx), (3, self.st_l)):
            self.post(bus, self.out(n))
        few = count()
        for n, ch in ((2, self.snare), (3, self.blank), (4, self.blank)):
            DeviceInput.objects.filter(pk=self.inport(n).pk).update(console_input=ch)
        self.post(self.blank_aux, self.out(4), name='Sidefill')
        self.assertEqual(count(), few)


class ReplaceAddTests(PickerBase):

    def setUp(self):
        super().setUp()
        self.link(self.inport(1), self.kick)

    def test_choice_is_required_once_a_channel_is_patched(self):
        before = self.snapshot()
        r = self.post(self.kick, self.inport(2))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['error'], 'choose')
        self.assertEqual(self.snapshot(), before)

    def test_replace_frees_the_old_port_and_links_the_new(self):
        r = self.post(self.kick, self.inport(2), mode='replace')
        self.assertEqual(r.status_code, 200, r.content)
        old, new = self.inport(1), self.inport(2)
        self.assertEqual((old.signal_name, old.console_input_id), ('', None))
        self.assertEqual((new.signal_name, new.console_input_id), ('Kick', self.kick.pk))

    def test_replace_also_frees_a_by_name_feed(self):
        DeviceInput.objects.filter(pk=self.inport(1).pk).update(console_input=None)
        self.assertEqual(self.picker(self.kick)['feeds'][0]['how'], 'by_name')
        self.post(self.kick, self.inport(2), mode='replace')
        self.assertEqual(self.inport(1).signal_name, '')
        self.assertEqual(self.inport(2).console_input, self.kick)

    def test_replace_is_atomic(self):
        """If linking the new port fails, the old one is still patched."""
        target = self.inport(2).pk
        real_save = DeviceInput.save

        def failing_save(row, *args, **kwargs):
            if row.pk == target:
                raise RuntimeError('disk full')
            return real_save(row, *args, **kwargs)

        state = self.picker(self.kick)['state']
        with mock.patch.object(DeviceInput, 'save', failing_save):
            with self.assertRaises(RuntimeError):
                self.post(self.kick, self.inport(2), mode='replace', state=state)
        old = self.inport(1)
        self.assertEqual((old.signal_name, old.console_input_id), ('Kick', self.kick.pk))
        self.assertIsNone(self.inport(2).console_input_id)

    def test_add_on_an_input_is_a_conflict_once_confirmed(self):
        r = self.post(self.kick, self.inport(2), mode='add')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(DeviceInput.objects.filter(console_input=self.kick).count(), 2)
        self.assertEqual(r.json()['cell_html'].count('ss-patch-conflict'), 2)
        self.assertTrue(all(f['conflict'] for f in r.json()['feeds']))

    def test_add_on_an_output_is_normal(self):
        self.post(self.aux, self.out(1))
        r = self.post(self.aux, self.out(2), mode='add')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('ss-patch-conflict', r.json()['cell_html'])
        self.assertEqual(self.out(1).console_output, self.aux)
        self.assertEqual(self.out(2).console_output, self.aux)


class UnpatchTests(PickerBase):

    def test_unpatch_frees_a_linked_port(self):
        self.link(self.inport(1), self.kick)
        r = self.post(self.kick, self.inport(1), action='unpatch')
        self.assertEqual(r.status_code, 200)
        self.assertEqual((self.inport(1).signal_name, self.inport(1).console_input_id), ('', None))
        self.assertIn('ss-patch-none', r.json()['cell_html'])

    def test_unpatch_frees_a_by_name_port(self):
        DeviceInput.objects.filter(pk=self.inport(1).pk).update(signal_name='Kick')
        self.post(self.kick, self.inport(1), action='unpatch')
        self.assertEqual(self.inport(1).signal_name, '')

    def test_unpatch_a_stereo_output(self):
        self.post(self.st_l, self.out(1))
        self.post(self.st_l, self.out(1), action='unpatch')
        self.assertIsNone(self.out(1).object_id)

    def test_ambiguous_and_b_feeds_are_not_unpatched_here(self):
        ConsoleInput.objects.create(console=self.foh, input_ch='90', source='Spare')
        spare = ConsoleInput.objects.create(console=self.foh, input_ch='91', source='Spare')
        DeviceInput.objects.filter(pk=self.inport(1).pk).update(signal_name='Spare')
        self.snare.source_b = 'Snare B'
        self.snare.save()
        DeviceInput.objects.filter(pk=self.inport(2).pk).update(signal_name='Snare B')
        before = self.snapshot()
        data = self.picker(spare)
        self.assertEqual([f['can_unpatch'] for f in data['feeds']], [False])
        self.assertEqual(self.post(spare, self.inport(1), action='unpatch').status_code, 409)
        self.assertEqual(self.picker(self.snare)['feeds'][0]['slot'], 'B')
        self.assertEqual(self.post(self.snare, self.inport(2), action='unpatch').status_code, 409)
        self.assertEqual(self.snapshot(), before)


class StaleTests(PickerBase):

    def test_patch_changed_elsewhere_is_409_with_the_current_state(self):
        state = self.picker(self.kick)['state']
        self.link(self.inport(5), self.kick)          # another tab patched it
        before = self.snapshot()
        r = self.post(self.kick, self.inport(1), state=state)
        self.assertEqual(r.status_code, 409)
        data = r.json()
        self.assertEqual(data['error'], 'stale')
        self.assertNotEqual(data['state'], state)
        self.assertIn('In 5', data['cell_html'])
        self.assertEqual(self.snapshot(), before)

    def test_channel_renamed_mid_pick(self):
        state = self.picker(self.kick)['state']
        self.kick.source = 'Kick In'
        self.kick.save()
        before = self.snapshot()
        r = self.post(self.kick, self.inport(1), state=state)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['channel']['name'], 'Kick In')
        self.assertEqual(self.snapshot(), before)
        # With the fresh state it goes through, under the new name.
        self.assertEqual(self.post(self.kick, self.inport(1)).status_code, 200)
        self.assertEqual(self.inport(1).signal_name, 'Kick In')

    def test_channel_deleted_mid_pick(self):
        state = self.picker(self.kick)['state']
        url = self.url(self.kick)
        self.kick.delete()
        before = self.snapshot()
        r = self.client.post(url, json.dumps(
            {'action': 'patch', 'port': self.inport(1).pk, 'state': state}),
            content_type='application/json')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_a_missing_state_is_stale(self):
        self.assertEqual(self.post(self.kick, self.inport(1), state='').status_code, 409)


class PermissionTests(PickerBase):
    """Owner / editor of the CURRENT project only -- the role on another show
    never leaks in, either way (the #18 / #121 shape)."""

    def test_viewer_on_this_project_is_403_even_if_editor_elsewhere(self):
        viewer = self.member('viewer', 'viewer')
        self.join(viewer, self.other, 'editor')
        state = self.picker(self.kick)['state']
        self.as_user(viewer, self.project)
        before = self.snapshot()
        self.assertEqual(self.client.get(self.url(self.kick)).status_code, 403)
        for action in ('patch', 'unpatch'):
            r = self.post(self.kick, self.inport(1), action=action, state=state)
            self.assertEqual(r.status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_editor_here_is_not_blocked_by_viewer_elsewhere(self):
        editor = self.member('editor', 'editor')
        self.join(editor, self.other, 'viewer')
        self.as_user(editor, self.project)
        self.assertEqual(self.post(self.kick, self.inport(1)).status_code, 200)

    def test_other_projects_channel_is_404(self):
        before = self.snapshot()
        self.assertEqual(self.client.get(self.url(self.other_kick)).status_code, 404)
        r = self.client.post(self.url(self.other_kick), json.dumps(
            {'action': 'patch', 'port': self.inport(1).pk, 'state': ''}),
            content_type='application/json')
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_other_projects_port_is_404(self):
        before = self.snapshot()
        r = self.post(self.kick, DeviceInput.objects.filter(device=self.other_box).first())
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_own_channel_is_404_while_another_project_is_current(self):
        self.as_user(self.other_owner, self.other)
        self.join(self.other_owner, self.project, 'editor')
        self.assertEqual(self.client.get(self.url(self.kick)).status_code, 404)

    def test_unknown_kind_is_404(self):
        r = self.client.get(reverse('planner:console_patch', args=['dca', self.kick.pk]))
        self.assertEqual(r.status_code, 404)


class ConsolePageCellTests(PickerBase):

    def page(self):
        r = self.client.get(reverse('admin:planner_console_change', args=[self.foh.pk]))
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    # Plain storage: with the manifest one these names come out hashed
    # whenever a local `collectstatic` has put the file in staticfiles/, so
    # the test would depend on a gitignored build folder.
    @override_settings(STORAGES=PLAIN_STATIC)
    def test_owner_gets_buttons_and_the_picker_script(self):
        self.link(self.inport(1), self.kick)
        page = self.page()
        self.assertIn(f'data-patch-url="{self.url(self.kick)}"', page)
        self.assertIn(f'data-patch-url="{self.url(self.st_l)}"', page)
        self.assertIn('console_patch_picker.js', page)
        cells = _patch_cells(page)
        self.assertIn('Stage Box A', cells)
        self.assertNotIn('<a href=', cells)

    def test_viewer_gets_the_read_only_cell(self):
        self.link(self.inport(1), self.kick)
        viewer = self.member('viewer', 'viewer')
        self.join(viewer, self.other, 'editor')
        self.as_user(viewer, self.project)
        page = self.page()
        self.assertNotIn('ss-patch-edit', page)
        self.assertNotIn('data-patch-url', page)
        device_url = reverse('admin:planner_device_change', args=[self.box.pk])
        self.assertIn(f'<a href="{device_url}"><span class="ss-patch-dev">Stage Box A</span>', page)

    def test_editor_gets_buttons(self):
        editor = self.member('editor', 'editor')
        self.as_user(editor, self.project)
        self.assertIn('ss-patch-edit', self.page())


def _patch_cells(page):
    """Just the Patch cells' markup, for asserting on what they contain."""
    import re
    return ''.join(re.findall(r'<td class="field-patch">(.*?)</td>', page, re.S))


class QueryCapTests(PickerBase):
    """The picker and a write cost the same however many devices and ports
    the project has -- no per-port or per-device query."""

    def count(self, fn):
        with CaptureQueriesContext(connection) as q:
            fn()
        return len(q)

    def measure(self):
        state = self.picker(self.kick)['state']
        read = self.count(lambda: self.client.get(self.url(self.kick)))
        port = DeviceInput.objects.filter(device__project=self.project, signal_name='',
                                          console_input=None).order_by('pk').first()
        write = self.count(lambda: self.post(self.kick, port, mode='replace', state=state))
        return read, write

    def test_query_count_does_not_grow_with_devices_or_ports(self):
        small = self.measure()
        for i in range(6):
            make_device(self.project, f'Rack {i}', ins=64, outs=32)
        for n in range(4, 40):
            ConsoleInput.objects.create(console=self.foh, input_ch=str(n), source=f'Ch {n}')
        DeviceInput.objects.filter(pk=self.inport(1).pk).update(console_input=None, signal_name='')
        DeviceInput.objects.filter(console_input=self.kick).update(console_input=None, signal_name='')
        large = self.measure()
        self.assertEqual(small, large)
        read, write = large
        # Measured: 7 are the framework's (session, user, project middleware,
        # session save); the picker's own are the channel, the console's rows,
        # all input ports and all output ports. A write adds the locked
        # channel and port, the console's rows and ports again (inside the
        # lock), and the UPDATEs.
        self.assertLessEqual(read, 13)
        self.assertLessEqual(write, 22)
