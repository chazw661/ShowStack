"""B input patches: DeviceInput.console_input_b, end to end (server side).

The Console page's B view, its Patch (B) picker, the I/O device page's B
column, the one-B-per-channel rule, the same-port warning, deletes, project
duplication, and that names never make a B. The wiring diagram's B edges are
test_wiring_b_links.py; the browser half is test_console_b_patch_browser.py.

    python manage.py test planner.tests.test_console_b_patch \\
        --settings=audiopatch.test_settings
"""
import json
import re

from django.contrib.auth.models import Group, User
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from planner.models import UserProfile
from planner.forms import DeviceInputInlineForm
from planner.models import (
    Console, ConsoleInput, Device, DeviceInput, DeviceOutput, Project, ProjectMember,
)
from planner.utils.console_patch import LINKED, PortIndex, feed_label

PLAIN_STATIC = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


def make_user(name, plan='paid', group='Editor'):
    user = User.objects.create_user(name, password='pw', is_staff=True)
    UserProfile.objects.update_or_create(user=user, defaults={'account_type': plan})
    user.groups.add(Group.objects.get(name=group))
    return User.objects.get(pk=user.pk)


def make_device(project, name, ins=8, outs=2):
    d = Device.objects.create(project=project, name=name, input_count=ins, output_count=outs)
    DeviceInput.objects.bulk_create(
        DeviceInput(device=d, input_number=n, signal_name='') for n in range(1, ins + 1))
    DeviceOutput.objects.bulk_create(
        DeviceOutput(device=d, output_number=n, signal_name='') for n in range(1, outs + 1))
    return d


class BFixture:
    """paidtest: a non-superuser paid owner, the way prod has one."""

    def setUp(self):
        super().setUp()
        call_command('setup_user_groups', stdout=open('/dev/null', 'w'))
        self.owner = make_user('paidtest')
        self.project = Project.objects.create(name='Show', owner=self.owner)
        self.foh = Console.objects.create(project=self.project, name='FOH')
        self.mon = Console.objects.create(project=self.project, name='MON')
        self.kick = ConsoleInput.objects.create(console=self.foh, input_ch='1', source='Kick',
                                                source_b='Kick spare')
        self.snare = ConsoleInput.objects.create(console=self.foh, input_ch='2', source='Snare')
        self.vox = ConsoleInput.objects.create(console=self.foh, input_ch='5', source='Vox')
        self.mon_kick = ConsoleInput.objects.create(console=self.mon, input_ch='1', source='Kick')
        self.box = make_device(self.project, 'Stage Box A')
        self.box_b = make_device(self.project, 'Stage Box B')
        self.login(self.owner)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def inport(self, n, device=None):
        return DeviceInput.objects.get(device=device or self.box, input_number=n)

    def set_a(self, port, channel):
        DeviceInput.objects.filter(pk=port.pk).update(console_input=channel,
                                                      signal_name=channel.source)

    def set_b(self, port, channel):
        DeviceInput.objects.filter(pk=port.pk).update(console_input_b=channel)

    def state(self):
        return list(DeviceInput.objects.order_by('pk').values_list(
            'signal_name', 'console_input_id', 'console_input_b_id'))

    def cells(self, console=None):
        index = PortIndex(self.project.pk)
        rows = list((console or self.foh).consoleinput_set.all())
        index.register(rows)
        return {r.input_ch: index.cell_for(r) for r in rows}

    # -- Console page picker ------------------------------------------------

    def b_url(self, channel):
        return reverse('planner:console_patch', args=['inb', channel.pk])

    def a_url(self, channel):
        return reverse('planner:console_patch', args=['in', channel.pk])

    def picker(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def post(self, url, port, action='patch', mode='', name=''):
        state = self.picker(url)['state']
        return self.client.post(url, json.dumps({'action': action, 'port': port.pk,
                                                 'mode': mode, 'state': state, 'name': name}),
                                content_type='application/json')

    # -- I/O device page ------------------------------------------------------

    def device_url(self, device=None):
        return reverse('admin:planner_device_change', args=[(device or self.box).pk])

    def device_post(self, b=None, a=None, names=None, device=None):
        """Post the device page with every port as loaded, then ``b`` /
        ``a`` / ``names`` = {port number: value} on top."""
        device = device or self.box
        page = self.client.get(self.device_url(device))
        form = page.context['adminform'].form
        data = {'name': device.name, 'input_count': device.input_count,
                'output_count': device.output_count, 'primary_ip_address': '',
                'secondary_ip_address': '', 'location': '', 'console_connection': '',
                '_continue': '1'}
        for formset in page.context['inline_admin_formsets']:
            fs = formset.formset
            prefix = fs.prefix
            data.update({f'{prefix}-TOTAL_FORMS': len(fs.forms),
                         f'{prefix}-INITIAL_FORMS': fs.initial_form_count(),
                         f'{prefix}-MIN_NUM_FORMS': 0, f'{prefix}-MAX_NUM_FORMS': 1000})
            for i, f in enumerate(fs.forms):
                for name, field in f.fields.items():
                    value = f.initial.get(name, field.initial)
                    if hasattr(value, 'pk'):
                        value = value.pk
                    data[f'{prefix}-{i}-{name}'] = '' if value is None else value
                data[f'{prefix}-{i}-id'] = f.instance.pk or ''
                data[f'{prefix}-{i}-device'] = device.pk
                n = f.instance.input_number if prefix == 'inputs' else None
                if prefix == 'inputs' and n is not None:
                    if b and n in b:
                        data[f'{prefix}-{i}-b_ref'] = '' if b[n] is None else str(b[n].pk)
                    if a and n in a:
                        ch = a[n]
                        data[f'{prefix}-{i}-link_ref'] = f'in:{ch.pk}' if ch else ''
                        data[f'{prefix}-{i}-signal_name'] = ch.source if ch else ''
                    if names and n in names:
                        data[f'{prefix}-{i}-signal_name'] = names[n]
                        data[f'{prefix}-{i}-link_ref'] = ''
        del form
        return self.client.post(self.device_url(device), data)


@override_settings(STORAGES=PLAIN_STATIC)
class ConsoleBViewTests(BFixture, TestCase):

    def page(self):
        r = self.client.get(reverse('admin:planner_console_change', args=[self.foh.pk]))
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    @staticmethod
    def b_cells(page):
        return re.findall(r'<td class="field-patch_b">(.*?)</td>', page, re.S)

    def test_b_view_is_blank_where_only_a_is_patched(self):
        self.set_a(self.inport(1), self.kick)
        self.set_a(self.inport(2), self.snare)
        cells = self.cells()
        self.assertEqual(cells['1'].only('B').feeds, [])
        self.assertEqual([f.slot for f in cells['1'].feeds], ['A'])
        page = self.page()
        b = self.b_cells(page)[:3]       # the three channels (the last is the empty-form row)
        self.assertEqual(len(b), 3)
        for cell in b:
            self.assertIn('ss-patch-none', cell)
            self.assertNotIn('Stage Box', cell)
        # The A column still shows A.
        self.assertIn('Stage Box A</span><span class="ss-patch-port"> · In 1', page)

    def test_b_view_shows_only_the_stored_b(self):
        self.set_a(self.inport(1), self.kick)
        self.set_b(self.inport(3, self.box_b), self.kick)
        cells = self.cells()
        self.assertEqual([(f.port.device_name, f.port.number, f.how, f.slot)
                          for f in cells['1'].only('B').feeds],
                         [('Stage Box B', 3, LINKED, 'B')])
        a_cells = re.findall(r'<td class="field-patch">(.*?)</td>', self.page(), re.S)
        self.assertNotIn('Stage Box B', a_cells[0])
        self.assertIn('Stage Box B', self.b_cells(self.page())[0])

    def test_a_name_column_is_read_only_text(self):
        page = self.page()
        self.assertIn('<th class="column-a_name', page)
        cells = re.findall(r'<td class="field-a_name">(.*?)</td>', page, re.S)
        self.assertIn('Kick', cells[0])
        self.assertNotIn('<input', cells[0])
        # Source (B) is its own field, blank unless set, never copied from A.
        self.assertIn('name="consoleinput_set-1-source_b"', page)
        self.assertEqual(ConsoleInput.objects.get(pk=self.snare.pk).source_b, None)

    def test_names_never_make_a_b_feed(self):
        # A port named after Source (B), and one named after the A name of
        # a channel, do nothing B-side.
        DeviceInput.objects.filter(pk=self.inport(4).pk).update(signal_name='Kick spare')
        DeviceInput.objects.filter(pk=self.inport(5).pk).update(signal_name='Snare')
        cells = self.cells()
        for ch in ('1', '2', '5'):
            self.assertEqual(cells[ch].only('B').feeds, [], ch)
        self.assertEqual(self.picker(self.b_url(self.kick))['feeds'], [])
        form = DeviceInputInlineForm(instance=self.inport(4), project_id=self.project.pk)
        self.assertNotIn('b_ref', form.initial)
        # A's by-name logic is untouched: the "Snare" port is still A by name.
        self.assertEqual([f.how for f in cells['2'].feeds], ['by_name'])

    def test_same_port_a_and_b_is_flagged(self):
        self.set_a(self.inport(1), self.kick)
        self.set_b(self.inport(1), self.kick)
        (feed,) = self.cells()['1'].only('B').feeds
        self.assertTrue(feed.same_port)
        self.assertIn('same port as A', feed_label(feed, 'In'))
        self.assertIn('ss-patch-same', self.b_cells(self.page())[0])

    def test_two_b_ports_that_slipped_through_are_a_conflict(self):
        self.set_b(self.inport(1), self.kick)
        self.set_b(self.inport(2), self.kick)
        cell = self.cells()['1'].only('B')
        self.assertEqual([f.conflict for f in cell.feeds], [True, True])

    def test_free_ports_count_a_b_link_as_used(self):
        self.set_b(self.inport(1), self.kick)
        self.assertRegex(self.page(), r'<strong>7</strong> free inputs: 2-8')


class ConsoleBPickerTests(BFixture, TestCase):

    def test_set_and_clear_b_from_the_console_page_never_touches_a(self):
        self.set_a(self.inport(2), self.kick)
        r = self.post(self.b_url(self.kick), self.inport(5))
        self.assertEqual(r.status_code, 200, r.content)
        p = self.inport(5)
        self.assertEqual((p.console_input_b_id, p.console_input_id, p.signal_name),
                         (self.kick.pk, None, ''))
        self.assertEqual(self.inport(2).console_input_id, self.kick.pk)
        self.assertIn('Stage Box A', r.json()['cell_html'])
        self.assertEqual(r.json()['slot'], 'B')
        r = self.post(self.b_url(self.kick), self.inport(5), action='unpatch')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(self.inport(5).console_input_b_id)
        self.assertEqual(self.inport(2).console_input_id, self.kick.pk)

    def test_b_ignores_a_typed_name(self):
        self.post(self.b_url(self.kick), self.inport(5), name='Typed')
        self.assertEqual(self.inport(5).signal_name, '')

    def test_editing_a_from_the_console_page_never_touches_b(self):
        self.set_b(self.inport(3), self.kick)
        self.assertEqual(self.post(self.a_url(self.kick), self.inport(1)).status_code, 200)
        self.assertEqual(self.inport(3).console_input_b_id, self.kick.pk)
        self.assertEqual(self.post(self.a_url(self.kick), self.inport(1),
                                   action='unpatch').status_code, 200)
        self.assertEqual(self.inport(3).console_input_b_id, self.kick.pk)

    def test_second_b_is_refused_and_replace_moves_it(self):
        self.set_b(self.inport(1), self.kick)
        before = self.state()
        for mode in ('', 'add'):
            r = self.post(self.b_url(self.kick), self.inport(2), mode=mode)
            self.assertEqual(r.status_code, 409, mode)
            self.assertEqual(r.json()['error'], 'one_b')
        self.assertEqual(self.state(), before)
        r = self.post(self.b_url(self.kick), self.inport(2), mode='replace')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(self.inport(1).console_input_b_id)
        self.assertEqual(self.inport(2).console_input_b_id, self.kick.pk)

    def test_a_port_already_b_elsewhere_is_not_offered_for_b(self):
        self.set_b(self.inport(1), self.snare)
        ports = {p['number']: p for p in self.picker(self.b_url(self.kick))['devices'][0]['ports']}
        self.assertEqual((ports[1]['free'], ports[1]['use']), (False, 'B for Ch 2'))
        self.assertEqual(self.post(self.b_url(self.kick), self.inport(1)).status_code, 409)

    def test_b_picker_offers_named_and_a_linked_ports_with_their_use(self):
        self.set_a(self.inport(1), self.kick)       # this channel's own A
        self.set_a(self.inport(2), self.mon_kick)   # another console's A
        DeviceInput.objects.filter(pk=self.inport(3).pk).update(signal_name='Wless 3')
        ports = {p['number']: p for p in self.picker(self.b_url(self.kick))['devices'][0]['ports']}
        self.assertEqual((ports[1]['free'], ports[1]['warn']), (True, 'same port as A'))
        self.assertEqual((ports[2]['free'], ports[2]['use']), (True, 'A for MON Ch 1 · Kick'))
        self.assertEqual((ports[3]['free'], ports[3]['use']), (True, 'Wless 3'))
        r = self.post(self.b_url(self.kick), self.inport(1))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('same port as A', r.json()['cell_html'])
        self.assertEqual(self.inport(1).console_input_id, self.kick.pk)

    def test_a_picker_shows_b_linked_ports_with_their_use(self):
        self.set_b(self.inport(4), self.vox)
        self.set_b(self.inport(6), self.mon_kick)
        ports = {p['number']: p for p in self.picker(self.a_url(self.kick))['devices'][0]['ports']}
        # Port.free is unchanged for A: a B-only port is still free to patch A.
        self.assertEqual((ports[4]['free'], ports[4]['use']), (True, 'B for Ch 5'))
        self.assertEqual((ports[6]['free'], ports[6]['use']), (True, 'B for MON Ch 1'))
        self.assertEqual(self.post(self.a_url(self.kick), self.inport(4)).status_code, 200)
        p = self.inport(4)
        self.assertEqual((p.console_input_id, p.console_input_b_id), (self.kick.pk, self.vox.pk))

    def test_viewer_cannot_read_or_write_b(self):
        viewer = make_user('viewer1', 'free', 'Viewer')
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.owner)
        self.login(viewer)
        before = self.state()
        self.assertEqual(self.client.get(self.b_url(self.kick)).status_code, 403)
        r = self.client.post(self.b_url(self.kick), json.dumps(
            {'action': 'patch', 'port': self.inport(1).pk, 'state': ''}),
            content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.state(), before)

    def test_another_projects_port_is_404(self):
        other = Project.objects.create(name='Other', owner=make_user('other'))
        theirs = make_device(other, 'Their Box')
        r = self.post(self.b_url(self.kick), DeviceInput.objects.filter(device=theirs).first())
        self.assertEqual(r.status_code, 404)


@override_settings(STORAGES=PLAIN_STATIC)
class DevicePageBTests(BFixture, TestCase):

    def test_set_and_clear_b_from_the_device_page_never_touches_a(self):
        self.set_a(self.inport(1), self.kick)
        r = self.device_post(b={2: self.kick, 3: self.snare})
        self.assertEqual(r.status_code, 302, r.context and r.context.get('errors'))
        self.assertEqual(self.inport(2).console_input_b_id, self.kick.pk)
        self.assertEqual(self.inport(3).console_input_b_id, self.snare.pk)
        p = self.inport(1)
        self.assertEqual((p.console_input_id, p.signal_name, p.console_input_b_id),
                         (self.kick.pk, 'Kick', None))
        self.assertEqual((self.inport(2).signal_name, self.inport(2).console_input_id), ('', None))
        r = self.device_post(b={2: None})
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(self.inport(2).console_input_b_id)
        self.assertEqual(self.inport(3).console_input_b_id, self.snare.pk)
        self.assertEqual(self.inport(1).console_input_id, self.kick.pk)

    def test_editing_a_on_the_device_page_never_touches_b(self):
        self.set_b(self.inport(1), self.snare)
        self.assertEqual(self.device_post(a={1: self.kick}).status_code, 302)
        p = self.inport(1)
        self.assertEqual((p.console_input_id, p.console_input_b_id), (self.kick.pk, self.snare.pk))
        self.assertEqual(self.device_post(names={1: ''}).status_code, 302)
        p = self.inport(1)
        self.assertEqual((p.console_input_id, p.console_input_b_id), (None, self.snare.pk))

    def test_b_column_is_on_every_port_and_lists_channels_by_console(self):
        page = self.client.get(self.device_url()).content.decode()
        self.assertEqual(page.count('class="ss-b-pick"'), 8)
        self.assertIn('<optgroup label="FOH">', page)
        self.assertIn('>FOH Ch 1 · Kick</option>', page)
        self.assertIn('>MON Ch 1 · Kick</option>', page)
        self.assertIn('<optgroup label="MON">', page)

    def test_two_ports_on_one_device_cannot_both_be_a_channels_b(self):
        before = self.state()
        r = self.device_post(b={2: self.kick, 3: self.kick})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'already has a B source on this device (In 2)')
        self.assertEqual(self.state(), before)

    def test_a_port_on_another_device_already_holding_the_b_is_refused(self):
        self.set_b(self.inport(4, self.box_b), self.kick)
        before = self.state()
        r = self.device_post(b={2: self.kick})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'is already B on Stage Box B In 4')
        self.assertEqual(self.state(), before)

    def test_moving_a_b_between_ports_in_one_save(self):
        self.set_b(self.inport(3), self.kick)
        r = self.device_post(b={1: self.kick, 3: None})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.inport(1).console_input_b_id, self.kick.pk)
        self.assertIsNone(self.inport(3).console_input_b_id)

    def test_same_port_a_and_b_saves_with_a_warning(self):
        r = self.device_post(a={1: self.kick}, b={1: self.kick})
        self.assertEqual(r.status_code, 302)
        p = self.inport(1)
        self.assertEqual((p.console_input_id, p.console_input_b_id), (self.kick.pk, self.kick.pk))
        texts = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(any('both A and B of FOH Ch 1 (same port as A)' in t for t in texts), texts)
        page = self.client.get(self.device_url()).content.decode()
        self.assertIn('<div class="ss-b-note">same port as A</div>', page)

    def test_another_projects_channel_is_refused(self):
        other = Project.objects.create(name='Other', owner=make_user('other'))
        theirs = ConsoleInput.objects.create(
            console=Console.objects.create(project=other, name='X'), input_ch='1', source='Kick')
        r = self.device_post(b={1: theirs})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.inport(1).console_input_b_id)

    def test_viewer_sees_b_disabled_and_cannot_change_it(self):
        self.set_b(self.inport(1), self.kick)
        viewer = make_user('viewer1', 'free', 'Viewer')
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.owner)
        self.login(viewer)
        page = self.client.get(self.device_url()).content.decode()
        select = re.search(r'<select name="inputs-0-b_ref"[^>]*>', page).group(0)
        self.assertIn('disabled', select)
        before = self.state()
        self.device_post(b={1: self.snare, 2: self.kick})
        self.assertEqual(self.state(), before)

    def test_an_editor_after_a_viewer_can_still_set_b_and_a(self):
        """A viewer's page used to disable the shared declared fields for
        everyone after them in the same process (BaseEquipmentInline)."""
        viewer = make_user('viewer1', 'free', 'Viewer')
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.owner)
        self.login(viewer)
        self.client.get(self.device_url())
        self.login(self.owner)
        page = self.client.get(self.device_url()).content.decode()
        select = re.search(r'<select name="inputs-0-b_ref"[^>]*>', page).group(0)
        self.assertNotIn('disabled', select)
        self.assertEqual(self.device_post(a={1: self.kick}, b={2: self.snare}).status_code, 302)
        self.assertEqual(self.inport(1).console_input_id, self.kick.pk)
        self.assertEqual(self.inport(2).console_input_b_id, self.snare.pk)


class DeleteAndDuplicateTests(BFixture, TestCase):

    def test_deleting_the_channel_nulls_b_and_leaves_the_port(self):
        self.set_a(self.inport(1), self.snare)
        self.set_b(self.inport(1), self.kick)
        self.kick.delete()
        p = self.inport(1)
        self.assertEqual((p.console_input_b_id, p.console_input_id), (None, self.snare.pk))

    def test_deleting_the_port_removes_its_b_and_nothing_else(self):
        self.set_b(self.inport(1), self.kick)
        self.inport(1).delete()
        self.assertTrue(ConsoleInput.objects.filter(pk=self.kick.pk).exists())
        self.assertFalse(self.kick.device_inputs_b.exists())

    def test_deleting_the_device_or_console_cascades_cleanly(self):
        self.set_b(self.inport(1), self.kick)
        self.foh.delete()
        self.assertIsNone(self.inport(1).console_input_b_id)
        self.box.delete()
        self.assertFalse(DeviceInput.objects.filter(device_id=self.box.pk).exists())

    def test_duplication_copies_a_b_and_source_b(self):
        self.set_a(self.inport(1), self.kick)
        self.set_b(self.inport(2), self.kick)
        self.set_a(self.inport(3), self.mon_kick)
        self.set_b(self.inport(3), self.snare)
        copy = self.project.duplicate(new_name='Show copy')
        new_box = Device.objects.get(project=copy, name='Stage Box A')
        new_foh = Console.objects.get(project=copy, name='FOH')
        new_mon = Console.objects.get(project=copy, name='MON')

        def ch(console, n):
            return ConsoleInput.objects.get(console=console, input_ch=n)

        got = {p.input_number: (p.signal_name, p.console_input_id, p.console_input_b_id)
               for p in new_box.inputs.all()}
        self.assertEqual(got[1], ('Kick', ch(new_foh, '1').pk, None))
        self.assertEqual(got[2], ('', None, ch(new_foh, '1').pk))
        self.assertEqual(got[3], ('Kick', ch(new_mon, '1').pk, ch(new_foh, '2').pk))
        self.assertEqual(ch(new_foh, '1').source_b, 'Kick spare')
        # The copy points at the copy, never back at the original show.
        originals = set(ConsoleInput.objects.filter(console__project=self.project)
                        .values_list('pk', flat=True))
        for _, a, b in got.values():
            self.assertNotIn(a, originals)
            self.assertNotIn(b, originals)
        # And the original is untouched.
        self.assertEqual(self.inport(2).console_input_b_id, self.kick.pk)
