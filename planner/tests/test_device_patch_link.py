"""The I/O device combobox saves the console link, not just the name.

From #95 a pick on the I/O device page wrote only ``signal_name`` -- the
``console_input`` link stayed empty, so the device PDF and the System Report
printed a blank Console Source for every port patched since. These tests pin
the rules in planner/utils/device_patch.py, driven through the real admin
change page wherever a browser would be involved:

  * picking a channel sets the link and the name; a free-typed name (even one
    that happens to equal a channel name) leaves the link empty;
  * a picked name edited to something else loses its link; clearing clears both;
  * a renamed channel carries its ports' names along, and deleting it leaves
    the name without a link;
  * outputs do the same for Aux and Matrix; Stereo is name only;
  * link_device_inputs_by_name backfills only what a name identifies uniquely.

Run with::

    python manage.py test planner.tests.test_device_patch_link \\
        --settings=audiopatch.test_settings
"""

import re
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput,
    ConsoleStereoOutput, Device, DeviceInput, DeviceOutput, Project,
)


def page_form_data(html):
    """Every field a browser would submit from an admin change page."""
    data = {}
    for tag in re.findall(r'<input[^>]*>', html):
        name = re.search(r'\bname="([^"]+)"', tag)
        if not name:
            continue
        if re.search(r'type="(checkbox|submit|button)"', tag) and 'checked' not in tag:
            continue
        value = re.search(r'\bvalue="([^"]*)"', tag)
        data[name.group(1)] = value.group(1) if value else ''
    for name, body in re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        chosen = re.search(r'<option value="([^"]*)"[^>]*selected', body)
        data[name] = chosen.group(1) if chosen else ''
    return data


class PatchLinkBase(TestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('a1', 'a1@example.com', 'pw')
        self.project = Project.objects.create(name='Show', owner=self.user)
        self.foh = Console.objects.create(project=self.project, name='FOH PM7')
        self.kick = ConsoleInput.objects.create(console=self.foh, input_ch='1', source='Kick')
        self.snare = ConsoleInput.objects.create(console=self.foh, input_ch='2', source='Snare')
        self.aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='1', name='Drum Wedge')
        self.mtx = ConsoleMatrixOutput.objects.create(console=self.foh, matrix_number='1', name='Lobby')
        ConsoleStereoOutput.objects.create(console=self.foh, stereo_type='L', name='PA Left')
        self.box = self.make_device(self.project, 'Stage Box A')

        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    @staticmethod
    def make_device(project, name, ins=4, outs=4):
        device = Device.objects.create(project=project, name=name,
                                       input_count=ins, output_count=outs)
        for n in range(1, ins + 1):
            DeviceInput.objects.create(device=device, input_number=n, signal_name='')
        for n in range(1, outs + 1):
            DeviceOutput.objects.create(device=device, output_number=n, signal_name='')
        return device

    def url(self, device=None):
        return reverse('admin:planner_device_change', args=[(device or self.box).pk])

    def submit(self, inputs=None, outputs=None, device=None, before_post=None):
        """Load the page, set ports {number: (name, ref)}, post it back.

        ``ref`` None leaves the hidden link field as the page rendered it --
        what happens when the engineer does not touch that port.
        """
        html = self.client.get(self.url(device)).content.decode()
        data = page_form_data(html)
        for prefix, number_field, ports in (('inputs', 'input_number', inputs or {}),
                                            ('outputs', 'output_number', outputs or {})):
            for port, (name, ref) in ports.items():
                key = next(k for k, v in data.items()
                           if k.startswith(prefix + '-') and k.endswith('-' + number_field)
                           and v == str(port))
                form = key.rsplit('-', 1)[0]
                data[form + '-signal_name'] = name
                if ref is not None:
                    data[form + '-link_ref'] = ref
        if before_post:
            before_post()
        response = self.client.post(self.url(device), data)
        self.assertEqual(response.status_code, 302, response.content[:2000])

    def port(self, n, device=None):
        return DeviceInput.objects.get(device=device or self.box, input_number=n)

    def out(self, n, device=None):
        return DeviceOutput.objects.get(device=device or self.box, output_number=n)


class SuggestionRefTests(PatchLinkBase):

    def test_page_carries_a_reference_for_every_linkable_suggestion(self):
        html = self.client.get(self.url()).content.decode()
        self.assertIn(f'data-ref="in:{self.kick.pk}"', html)
        self.assertIn(f'data-ref="aux:{self.aux.pk}"', html)
        self.assertIn(f'data-ref="mtx:{self.mtx.pk}"', html)
        # Stereo has no link to carry.
        self.assertRegex(html, r'value="PA Left"[^>]*data-ref=""')
        # Each signal-name box names its own hidden link field.
        self.assertIn('data-link-field="id_inputs-0-link_ref"', html)
        self.assertIn('data-link-field="id_outputs-0-link_ref"', html)


class InputLinkTests(PatchLinkBase):

    def test_picking_a_channel_sets_link_and_name(self):
        self.submit(inputs={1: ('Kick', f'in:{self.kick.pk}')})
        port = self.port(1)
        self.assertEqual(port.console_input, self.kick)
        self.assertEqual(port.signal_name, 'Kick')

    def test_free_typed_name_leaves_link_empty(self):
        self.submit(inputs={1: ('Talkback Mic', '')})
        self.assertIsNone(self.port(1).console_input)
        self.assertEqual(self.port(1).signal_name, 'Talkback Mic')

    def test_typing_a_channel_name_without_picking_is_still_free_typed(self):
        self.submit(inputs={1: ('Kick', '')})
        self.assertIsNone(self.port(1).console_input)

    def test_picked_name_edited_afterwards_drops_the_link(self):
        # The script clears the hidden field on typing; the server holds the
        # same rule in case it did not run.
        self.submit(inputs={1: ('Kick 2', f'in:{self.kick.pk}')})
        self.assertIsNone(self.port(1).console_input)
        self.assertEqual(self.port(1).signal_name, 'Kick 2')

    def test_case_and_spacing_do_not_break_a_pick(self):
        self.submit(inputs={1: ('  kick ', f'in:{self.kick.pk}')})
        self.assertEqual(self.port(1).console_input, self.kick)
        self.assertEqual(self.port(1).signal_name, 'Kick')

    def test_clearing_the_field_clears_both(self):
        DeviceInput.objects.filter(pk=self.port(1).pk).update(
            console_input=self.kick, signal_name='Kick')
        self.submit(inputs={1: ('', None)})
        self.assertIsNone(self.port(1).console_input)
        self.assertEqual(self.port(1).signal_name, '')

    def test_untouched_linked_port_survives_saving_the_page(self):
        DeviceInput.objects.filter(pk=self.port(1).pk).update(
            console_input=self.kick, signal_name='Kick')
        self.submit(inputs={2: ('Snare', f'in:{self.snare.pk}')})
        self.assertEqual(self.port(1).console_input, self.kick)
        self.assertEqual(self.port(2).console_input, self.snare)

    def test_legacy_link_with_blank_name_shows_the_channel_and_keeps_it(self):
        # The pre-#95 dropdown set the link and never the name.
        DeviceInput.objects.filter(pk=self.port(1).pk).update(
            console_input=self.kick, signal_name='')
        html = self.client.get(self.url()).content.decode()
        self.assertRegex(html, r'name="inputs-0-signal_name"[^>]*value="Kick"')
        self.submit(inputs={2: ('Snare', f'in:{self.snare.pk}')})
        self.assertEqual(self.port(1).console_input, self.kick)

    def test_channel_deleted_while_the_page_was_open_saves_the_name(self):
        self.submit(inputs={1: ('Kick', f'in:{self.kick.pk}')},
                    before_post=self.kick.delete)
        self.assertIsNone(self.port(1).console_input)
        self.assertEqual(self.port(1).signal_name, 'Kick')

    def test_garbage_reference_is_ignored(self):
        self.submit(inputs={1: ('Kick', 'in:not-a-number')})
        self.assertIsNone(self.port(1).console_input)
        self.submit(inputs={2: ('Kick', f'aux:{self.aux.pk}')})
        self.assertIsNone(self.port(2).console_input)


class OutputLinkTests(PatchLinkBase):

    def test_picking_an_aux_sets_the_generic_link(self):
        self.submit(outputs={1: ('Drum Wedge', f'aux:{self.aux.pk}')})
        out = self.out(1)
        self.assertEqual(out.console_output, self.aux)
        self.assertEqual(out.signal_name, 'Drum Wedge')

    def test_picking_a_matrix_sets_the_generic_link(self):
        self.submit(outputs={1: ('Lobby', f'mtx:{self.mtx.pk}')})
        self.assertEqual(self.out(1).console_output, self.mtx)

    def test_stereo_is_name_only(self):
        self.submit(outputs={1: ('PA Left', '')})
        self.assertIsNone(self.out(1).content_type)
        self.assertEqual(self.out(1).signal_name, 'PA Left')

    def test_free_typed_and_cleared_outputs_carry_no_link(self):
        self.submit(outputs={1: ('Drum Wedge', f'aux:{self.aux.pk}')})
        self.submit(outputs={1: ('Comms Feed', '')})
        self.assertIsNone(self.out(1).object_id)
        self.submit(outputs={1: ('Drum Wedge', f'aux:{self.aux.pk}')})
        self.submit(outputs={1: ('', None)})
        self.assertIsNone(self.out(1).object_id)
        self.assertEqual(self.out(1).signal_name, '')

    def test_untouched_linked_output_survives_saving_the_page(self):
        self.submit(outputs={1: ('Drum Wedge', f'aux:{self.aux.pk}')})
        self.submit(outputs={2: ('Lobby', f'mtx:{self.mtx.pk}')})
        self.assertEqual(self.out(1).console_output, self.aux)


class RenameAndDeleteTests(PatchLinkBase):

    def setUp(self):
        super().setUp()
        DeviceInput.objects.filter(pk=self.port(1).pk).update(
            console_input=self.kick, signal_name='Kick')
        DeviceOutput.objects.filter(pk=self.out(1).pk).update(
            content_type=ContentType.objects.get_for_model(ConsoleAuxOutput),
            object_id=self.aux.pk, signal_name='Drum Wedge')

    def test_renaming_a_channel_moves_the_port_name_and_keeps_the_link(self):
        self.kick.source = 'Kick In'
        self.kick.save()
        self.assertEqual(self.port(1).signal_name, 'Kick In')
        self.assertEqual(self.port(1).console_input, self.kick)

    def test_renaming_a_channel_to_blank_leaves_the_last_name(self):
        self.kick.source = ''
        self.kick.save()
        self.assertEqual(self.port(1).signal_name, 'Kick')
        self.assertEqual(self.port(1).console_input, self.kick)
        # ...and saving the device page untouched does not unlink it.
        self.submit(inputs={2: ('Snare', f'in:{self.snare.pk}')})
        self.assertEqual(self.port(1).console_input, self.kick)

    def test_deleting_a_channel_keeps_the_name_without_a_link(self):
        self.kick.delete()
        self.assertIsNone(self.port(1).console_input_id)
        self.assertEqual(self.port(1).signal_name, 'Kick')

    def test_renaming_an_aux_moves_the_output_name(self):
        self.aux.name = 'Drum Fill'
        self.aux.save()
        self.assertEqual(self.out(1).signal_name, 'Drum Fill')

    def test_deleting_an_aux_clears_the_dangling_generic_link(self):
        self.aux.delete()
        out = self.out(1)
        self.assertIsNone(out.content_type_id)
        self.assertIsNone(out.object_id)
        self.assertEqual(out.signal_name, 'Drum Wedge')

    def test_unlinked_ports_with_the_old_name_are_not_renamed(self):
        DeviceInput.objects.filter(pk=self.port(2).pk).update(signal_name='Kick')
        self.kick.source = 'Kick In'
        self.kick.save()
        self.assertEqual(self.port(2).signal_name, 'Kick')


class BackfillTests(PatchLinkBase):

    def setUp(self):
        super().setUp()
        self.mon = Console.objects.create(project=self.project, name='MON CL5')
        self.spare1 = ConsoleInput.objects.create(console=self.foh, input_ch='90', source='Spare')
        ConsoleInput.objects.create(console=self.foh, input_ch='91', source='Spare')
        ConsoleInput.objects.create(console=self.foh, input_ch='5', source='Vox 1')
        ConsoleInput.objects.create(console=self.mon, input_ch='5', source='Vox 1')
        names = {1: 'kick ', 2: 'Spare', 3: 'Vox 1', 4: 'Talkback Mic'}
        for n, name in names.items():
            DeviceInput.objects.filter(pk=self.port(n).pk).update(signal_name=name)

    def run_cmd(self, *args):
        out = StringIO()
        call_command('link_device_inputs_by_name', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_reports_and_writes_nothing(self):
        output = self.run_cmd()
        self.assertIn('DRY RUN', output)
        self.assertIn('1 matched, 2 ambiguous, 0 B input only, 1 unmatched', output)
        # Listed per device, every candidate named.
        self.assertIn('    Stage Box A\n'
                      '      In 2 "Spare" -> FOH PM7 ch 90, FOH PM7 ch 91\n'
                      '      In 3 "Vox 1" -> FOH PM7 ch 5, MON CL5 ch 5\n', output)
        self.assertFalse(DeviceInput.objects.exclude(console_input=None).exists())

    def test_apply_links_only_unique_matches(self):
        self.run_cmd('--apply')
        self.assertEqual(self.port(1).console_input, self.kick)
        self.assertEqual(self.port(1).signal_name, 'Kick')
        for n in (2, 3, 4):  # duplicate Spare, FOH/MON split, free-typed
            self.assertIsNone(self.port(n).console_input, n)

    def test_a_source_b_name_is_never_linked(self):
        # ch 7's B is "Lectern B". Alone, a B match is listed, not linked: a
        # stored link always means the A input.
        ConsoleInput.objects.create(console=self.foh, input_ch='7',
                                    source='Lectern', source_b='Lectern B')
        DeviceInput.objects.filter(pk=self.port(4).pk).update(signal_name='Lectern B')
        output = self.run_cmd('--apply')
        self.assertIn('1 B input only', output)
        self.assertIn('In 4 "Lectern B" -> FOH PM7 ch 7 (B)', output)
        self.assertIsNone(self.port(4).console_input)

    def test_a_name_on_one_channels_a_and_anothers_b_is_ambiguous(self):
        # Before, only Source was indexed, so this linked to MON ch 8 -- a
        # guess: the port may well be FOH ch 7's B feed.
        ConsoleInput.objects.create(console=self.foh, input_ch='7',
                                    source='Lectern', source_b='Lectern B')
        ConsoleInput.objects.create(console=self.mon, input_ch='8', source='Lectern B')
        DeviceInput.objects.filter(pk=self.port(4).pk).update(signal_name='Lectern B')
        output = self.run_cmd('--apply')
        self.assertIn('In 4 "Lectern B" -> FOH PM7 ch 7 (B), MON CL5 ch 8', output)
        self.assertIsNone(self.port(4).console_input)

    def test_same_name_on_a_monitor_desk_with_its_own_io_is_not_linked(self):
        # No split involved: MON has its own stage box and happens to use
        # FOH's channel names. The name alone cannot say which desk.
        ConsoleInput.objects.create(console=self.mon, input_ch='1', source='Kick')
        output = self.run_cmd('--apply')
        self.assertIn('In 1 "kick " -> FOH PM7 ch 1, MON CL5 ch 1', output)
        self.assertIsNone(self.port(1).console_input)

    def test_stale_linked_names_are_refreshed(self):
        DeviceInput.objects.filter(pk=self.port(1).pk).update(
            console_input=self.kick, signal_name='Kik')
        self.assertIn('1 linked with a stale name', self.run_cmd())
        self.run_cmd('--apply')
        self.assertEqual(self.port(1).signal_name, 'Kick')

    def test_never_matches_another_projects_channel(self):
        other = Project.objects.create(name='Other', owner=self.user)
        other_console = Console.objects.create(project=other, name='Other FOH')
        ConsoleInput.objects.create(console=other_console, input_ch='1', source='Talkback Mic')
        self.run_cmd('--apply')
        self.assertIsNone(self.port(4).console_input)

    def test_project_flag_scopes_the_run(self):
        other = Project.objects.create(name='Other', owner=self.user)
        self.assertIn('Total: 0 matched', self.run_cmd('--project', str(other.pk)))
        with self.assertRaises(CommandError):
            self.run_cmd('--project', '999999')

    def test_template_consoles_are_not_candidates(self):
        template = Console.objects.create(project=self.project, name='Tmpl', is_template=True)
        ConsoleInput.objects.create(console=template, input_ch='1', source='Kick')
        self.run_cmd('--apply')
        self.assertEqual(self.port(1).console_input, self.kick)


class SeedPatchDemoTests(TestCase):

    def test_builds_every_case_and_replaces_itself(self):
        User.objects.create_superuser('seed', 'seed@example.com', 'pw')
        for _ in range(2):
            call_command('seed_patch_demo', stdout=StringIO())
        project = Project.objects.get(name='Patch Demo (seed)')
        self.assertEqual(Project.objects.filter(name='Patch Demo (seed)').count(), 1)
        foh = Console.objects.get(project=project, name='FOH Rivage PM7')
        self.assertEqual(foh.consoleinput_set.count(), 96)
        box_b = Device.objects.get(project=project, name='Stage Box B')
        self.assertFalse(box_b.inputs.filter(input_number=1).first().console_input)
        conflict = DeviceInput.objects.filter(device__project=project,
                                              console_input__input_ch='70')
        self.assertEqual(conflict.count(), 2)
        renamed = DeviceInput.objects.get(device__name='Stage Box A', input_number=22,
                                          device__project=project)
        self.assertEqual(renamed.signal_name, 'Vox 3 (Guest)')

    def test_backfill_on_the_seed_guesses_nothing(self):
        User.objects.create_superuser('seed', 'seed@example.com', 'pw')
        call_command('seed_patch_demo', stdout=StringIO())
        project = Project.objects.get(name='Patch Demo (seed)')
        out = StringIO()
        call_command('link_device_inputs_by_name', '--project', str(project.pk),
                     '--apply', stdout=out)
        output = out.getvalue()
        # Choir 1-12 are on FOH only: linked. Everything else is left alone.
        self.assertIn('12 matched, 3 ambiguous, 1 B input only, 2 unmatched', output)
        self.assertIn('    MON Stage Box\n'
                      '      In 9 "OH L" -> FOH Rivage PM7 ch 9, MON CL5 ch 9, MON PM5 ch 9\n',
                      output)
        mon_box = DeviceInput.objects.filter(device__project=project,
                                             device__name='MON Stage Box')
        self.assertFalse(mon_box.filter(input_number__in=[9, 10])
                         .exclude(console_input=None).exists())
        self.assertEqual(set(mon_box.exclude(console_input=None)
                             .values_list('console_input__console__name', flat=True)),
                         {'MON PM5'})

    def test_refuses_anything_but_sqlite(self):
        with mock.patch('planner.management.commands.seed_patch_demo.connection') as conn:
            conn.vendor = 'postgresql'
            with self.assertRaises(CommandError):
                call_command('seed_patch_demo', stdout=StringIO())
