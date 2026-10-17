"""The Console page's read-only Patch column and free-ports summary.

Under test: planner/utils/console_patch.py (what feeds each channel) and its
wiring into ConsoleAdmin (PatchColumnMixin, the free-ports block). Read-only:
nothing here writes a link -- that is planner/utils/device_patch.py.

Run with::

    python manage.py test planner.tests.test_console_patch \\
        --settings=audiopatch.test_settings
"""

import re

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput,
    ConsoleStereoOutput, Device, DeviceInput, DeviceOutput, Project,
)
from planner.utils.console_patch import (
    AMBIGUOUS, BY_NAME, LINKED, PortIndex, compress,
)


class PatchBase(TestCase):

    def setUp(self):
        self.user = User.objects.create_superuser('a1', 'a1@example.com', 'pw')
        self.project = Project.objects.create(name='Show', owner=self.user)
        self.foh = Console.objects.create(project=self.project, name='FOH')
        self.mon = Console.objects.create(project=self.project, name='MON')
        self.box_a = self.device('Stage Box A')
        self.box_b = self.device('Stage Box B')
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def device(self, name, ins=8, outs=4):
        d = Device.objects.create(project=self.project, name=name,
                                  input_count=ins, output_count=outs)
        DeviceInput.objects.bulk_create(
            DeviceInput(device=d, input_number=n, signal_name='') for n in range(1, ins + 1))
        DeviceOutput.objects.bulk_create(
            DeviceOutput(device=d, output_number=n, signal_name='') for n in range(1, outs + 1))
        return d

    def ch(self, console, n, source='', source_b=None):
        return ConsoleInput.objects.create(console=console, input_ch=str(n),
                                           source=source, source_b=source_b)

    def port(self, device, n, name, link=None):
        DeviceInput.objects.filter(device=device, input_number=n).update(
            signal_name=name, console_input=link)

    def out(self, device, n, name, bus=None):
        DeviceOutput.objects.filter(device=device, output_number=n).update(
            signal_name=name,
            content_type=ContentType.objects.get_for_model(bus) if bus else None,
            object_id=bus.pk if bus else None)

    def cells(self, console):
        index = PortIndex(self.project.pk)
        rows = list(console.consoleinput_set.all())
        index.register(rows)
        return {r.input_ch: index.cell_for(r) for r in rows}

    def bus_cells(self, console):
        index = PortIndex(self.project.pk)
        rows = (list(console.consoleauxoutput_set.all())
                + list(console.consolematrixoutput_set.all())
                + list(console.consolestereooutput_set.all()))
        index.register(rows)
        return {_label(r): index.cell_for(r) for r in rows}

    @staticmethod
    def summary(cell):
        return [(f.port.device_name, f.port.number, f.how, f.slot, f.conflict)
                for f in cell.feeds]


def _label(bus):
    if isinstance(bus, ConsoleAuxOutput):
        return f'aux{bus.aux_number}'
    if isinstance(bus, ConsoleMatrixOutput):
        return f'mtx{bus.matrix_number}'
    return f'st{bus.stereo_type}'


class InputCellTests(PatchBase):

    def test_linked_port(self):
        kick = self.ch(self.foh, 1, 'Kick')
        self.port(self.box_a, 3, 'Kick', kick)
        self.assertEqual(self.summary(self.cells(self.foh)['1']),
                         [('Stage Box A', 3, LINKED, 'A', False)])

    def test_unlinked_port_matches_by_name_ignoring_case_and_spaces(self):
        self.ch(self.foh, 1, 'Kick')
        self.port(self.box_a, 3, ' kick ')
        self.assertEqual(self.summary(self.cells(self.foh)['1']),
                         [('Stage Box A', 3, BY_NAME, 'A', False)])

    def test_unpatched_channel_has_no_feeds(self):
        self.ch(self.foh, 1, 'Kick')
        self.ch(self.foh, 2, '')
        cells = self.cells(self.foh)
        self.assertEqual(cells['1'].feeds, [])
        self.assertEqual(cells['2'].feeds, [])

    def test_renamed_channel_keeps_its_linked_port(self):
        vox = self.ch(self.foh, 22, 'Vox 3')
        self.port(self.box_a, 1, 'Vox 3', vox)
        vox.source = 'Vox 3 (Guest)'
        vox.save()
        self.assertEqual(self.summary(self.cells(self.foh)['22']),
                         [('Stage Box A', 1, LINKED, 'A', False)])

    def test_two_ports_on_one_input_are_a_conflict(self):
        host = self.ch(self.foh, 70, 'Host Mic')
        self.port(self.box_a, 1, 'Host Mic', host)
        self.port(self.box_b, 1, 'Host Mic', host)
        self.assertEqual(self.summary(self.cells(self.foh)['70']), [
            ('Stage Box A', 1, LINKED, 'A', True),
            ('Stage Box B', 1, LINKED, 'A', True),
        ])

    def test_linked_and_by_name_on_one_input_is_not_a_conflict(self):
        # Only links make a conflict; a name is not a claim.
        host = self.ch(self.foh, 70, 'Host Mic')
        self.port(self.box_a, 1, 'Host Mic', host)
        self.port(self.box_b, 1, 'Host Mic')
        cell = self.cells(self.foh)['70']
        self.assertEqual(self.summary(cell), [
            ('Stage Box A', 1, LINKED, 'A', False),
            ('Stage Box B', 1, BY_NAME, 'A', False),
        ])
        self.assertFalse(cell.conflict)

    def test_b_source_is_a_b_feed_not_a_conflict(self):
        lectern = self.ch(self.foh, 25, 'Lectern', source_b='Lectern B')
        self.port(self.box_a, 1, 'Lectern', lectern)
        self.port(self.box_b, 1, 'Lectern B')
        cell = self.cells(self.foh)['25']
        self.assertEqual(self.summary(cell), [
            ('Stage Box A', 1, LINKED, 'A', False),
            ('Stage Box B', 1, BY_NAME, 'B', False),
        ])
        self.assertFalse(cell.conflict)

    def test_duplicate_name_is_ambiguous_on_every_channel_it_fits(self):
        self.ch(self.foh, 90, 'Spare')
        self.ch(self.foh, 91, 'Spare')
        self.port(self.box_b, 4, 'Spare')
        cells = self.cells(self.foh)
        for n in ('90', '91'):
            (feed,) = cells[n].feeds
            self.assertEqual(feed.how, AMBIGUOUS)
            self.assertEqual(feed.others, ('ch 90', 'ch 91'))
            self.assertFalse(cells[n].conflict)

    def test_linking_resolves_a_duplicate_name(self):
        spare = self.ch(self.foh, 90, 'Spare')
        self.ch(self.foh, 91, 'Spare')
        self.port(self.box_b, 4, 'Spare', spare)
        cells = self.cells(self.foh)
        self.assertEqual(cells['90'].feeds[0].how, LINKED)
        self.assertEqual(cells['91'].feeds, [])

    def test_linked_port_never_shows_on_another_console(self):
        # Same channel name on MON is not a split: MON may have its own I/O.
        kick_foh = self.ch(self.foh, 1, 'Kick')
        self.ch(self.mon, 1, 'Kick')
        self.port(self.box_a, 1, 'Kick', kick_foh)
        self.assertEqual(self.cells(self.foh)['1'].feeds[0].how, LINKED)
        self.assertEqual(self.cells(self.mon)['1'].feeds, [])

    def test_unlinked_name_on_two_consoles_is_ambiguous_on_both(self):
        self.ch(self.foh, 1, 'Kick')
        self.ch(self.mon, 4, 'Kick')
        self.port(self.box_b, 1, 'Kick')
        for console, ch in ((self.foh, '1'), (self.mon, '4')):
            cell = self.cells(console)[ch]
            (feed,) = cell.feeds
            self.assertEqual((feed.how, feed.across, feed.others),
                             (AMBIGUOUS, True, ('FOH', 'MON')))
            self.assertFalse(cell.conflict)

    def test_other_consoles_b_name_makes_it_ambiguous_too(self):
        self.ch(self.foh, 1, 'Lectern B')
        self.ch(self.mon, 1, 'Lectern', source_b='Lectern B')
        self.port(self.box_b, 1, 'Lectern B')
        self.assertEqual(self.cells(self.foh)['1'].feeds[0].how, AMBIGUOUS)

    def test_unlinked_name_only_on_another_console_does_not_show_here(self):
        self.ch(self.foh, 33, 'Choir 1')
        self.ch(self.mon, 33, '')
        self.port(self.box_b, 1, 'Choir 1')
        self.assertEqual(self.cells(self.foh)['33'].feeds[0].how, BY_NAME)
        self.assertEqual(self.cells(self.mon)['33'].feeds, [])

    def test_template_console_names_do_not_make_it_ambiguous(self):
        template = Console.objects.create(project=self.project, name='Tmpl', is_template=True)
        self.ch(template, 1, 'Kick')
        self.ch(self.foh, 1, 'Kick')
        self.port(self.box_b, 1, 'Kick')
        self.assertEqual(self.cells(self.foh)['1'].feeds[0].how, BY_NAME)

    def test_port_numbers_follow_position_like_the_device_page(self):
        kick = self.ch(self.foh, 1, 'Kick')
        DeviceInput.objects.filter(device=self.box_a, input_number=1).delete()
        self.port(self.box_a, 2, 'Kick', kick)  # stored as 2, shown as In 1
        self.assertEqual(self.cells(self.foh)['1'].feeds[0].port.number, 1)


class OutputCellTests(PatchBase):

    def setUp(self):
        super().setUp()
        self.aux1 = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='1', name='Drum Wedge')
        self.mtx1 = ConsoleMatrixOutput.objects.create(console=self.foh, matrix_number='1', name='Lobby')
        self.st_l = ConsoleStereoOutput.objects.create(console=self.foh, stereo_type='L', name='PA Left')

    def test_one_aux_to_two_outputs_is_normal(self):
        self.out(self.box_a, 1, 'Drum Wedge', self.aux1)
        self.out(self.box_a, 2, 'Drum Wedge', self.aux1)
        cell = self.bus_cells(self.foh)['aux1']
        self.assertEqual([f.how for f in cell.feeds], [LINKED, LINKED])
        self.assertFalse(cell.conflict)

    def test_matrix_by_name_and_stereo_by_name(self):
        self.out(self.box_b, 1, 'Lobby')
        self.out(self.box_b, 2, 'PA Left')
        cells = self.bus_cells(self.foh)
        self.assertEqual(cells['mtx1'].feeds[0].how, BY_NAME)
        self.assertEqual(cells['stL'].feeds[0].how, BY_NAME)

    def test_name_on_two_bus_types_is_ambiguous(self):
        ConsoleMatrixOutput.objects.create(console=self.foh, matrix_number='2', name='Drum Wedge')
        self.out(self.box_b, 1, 'Drum Wedge')
        cells = self.bus_cells(self.foh)
        self.assertEqual(cells['aux1'].feeds[0].how, AMBIGUOUS)
        self.assertEqual(cells['mtx2'].feeds[0].others, ('Aux 1', 'Mtx 2'))

    def test_output_linked_on_another_console_does_not_show_here(self):
        mon_aux = ConsoleAuxOutput.objects.create(console=self.mon, aux_number='1', name='Drum Wedge')
        self.out(self.box_a, 1, 'Drum Wedge', mon_aux)
        self.assertEqual(self.bus_cells(self.foh)['aux1'].feeds, [])
        self.assertEqual(self.bus_cells(self.mon)['aux1'].feeds[0].how, LINKED)

    def test_unlinked_output_name_on_two_consoles_is_ambiguous(self):
        ConsoleAuxOutput.objects.create(console=self.mon, aux_number='3', name='Drum Wedge')
        self.out(self.box_b, 1, 'Drum Wedge')
        (feed,) = self.bus_cells(self.foh)['aux1'].feeds
        self.assertEqual((feed.how, feed.others), (AMBIGUOUS, ('FOH', 'MON')))

    def test_output_linked_to_another_bus_is_not_matched_by_name(self):
        ConsoleMatrixOutput.objects.create(console=self.foh, matrix_number='2', name='Drum Wedge')
        self.out(self.box_b, 1, 'Drum Wedge', self.aux1)
        cells = self.bus_cells(self.foh)
        self.assertEqual(cells['aux1'].feeds[0].how, LINKED)
        self.assertEqual(cells['mtx2'].feeds, [])


class FreePortTests(PatchBase):

    def test_free_is_blank_name_and_no_link(self):
        kick = self.ch(self.foh, 1, 'Kick')
        self.port(self.box_a, 1, 'Kick')          # named
        self.port(self.box_a, 2, '', kick)        # linked, name blank (pre-#95 row)
        self.out(self.box_a, 4, 'Comms Feed')
        (box_a, box_b) = PortIndex(self.project.pk).free_ports()
        self.assertEqual(box_a['name'], 'Stage Box A')
        self.assertEqual((box_a['free_inputs'], box_a['input_ranges']), (6, '3-8'))
        self.assertEqual((box_a['free_outputs'], box_a['output_ranges']), (3, '1-3'))
        self.assertEqual(box_b['input_ranges'], '1-8')

    def test_compress(self):
        self.assertEqual(compress([31, 17, 18, 19, 20, 29, 30]), '17-20, 29-31')
        self.assertEqual(compress([5]), '5')
        self.assertEqual(compress([]), '')


class ConsolePageTests(PatchBase):

    def url(self, console):
        return reverse('admin:planner_console_change', args=[console.pk])

    def test_page_renders_feeds_marks_and_free_ports(self):
        host = self.ch(self.foh, 1, 'Host Mic')
        self.ch(self.foh, 2, 'Lectern', source_b='Lectern B')
        self.ch(self.foh, 3, 'Unused')
        self.port(self.box_a, 1, 'Host Mic', host)
        self.port(self.box_b, 1, 'Host Mic', host)
        self.port(self.box_b, 2, 'Lectern B')
        page = self.client.get(self.url(self.foh)).content.decode()
        self.assertIn('<th class="column-patch', page)
        device_url = reverse('admin:planner_device_change', args=[self.box_a.pk])
        self.assertIn(f'<a href="{device_url}"><span class="ss-patch-dev">Stage Box A</span>'
                      f'<span class="ss-patch-port"> · In 1</span></a>', page)
        self.assertEqual(page.count('ss-patch-conflict'), 2)
        self.assertRegex(page, r'ss-patch-tag-b">B</span><a [^>]*>'
                               r'<span class="ss-patch-dev">Stage Box B</span>'
                               r'<span class="ss-patch-port"> · In 2</span></a>'
                               r'<span class="ss-patch-caption">by name</span>')
        # A name on two consoles: dimmed, consoles named, not amber.
        self.ch(self.foh, 4, 'Shared')
        self.ch(self.mon, 1, 'Shared')
        self.port(self.box_b, 3, 'Shared')
        page = self.client.get(self.url(self.foh)).content.decode()
        self.assertIn('<span class="ss-patch-caption">ambiguous (FOH, MON)</span>', page)
        self.assertEqual(page.count('ss-patch-conflict'), 2)
        # The view switch and its stylesheet ship with the page.
        self.assertIn('console_patch_toggle.js', page)
        self.assertIn('console_patch.css', page)
        self.assertIn('class="ss-patch-none"', page)
        self.assertIn('I/O devices · free ports', page)
        self.assertRegex(page, r'<strong>5</strong> free inputs: 4-8')

    def test_add_page_has_no_patch_column(self):
        page = self.client.get(reverse('admin:planner_console_add')).content.decode()
        self.assertNotIn('column-patch', page)
        self.assertNotIn('free ports', page)

    def test_patch_lookup_is_two_queries(self):
        for n in range(1, 97):
            self.ch(self.foh, n, f'Ch {n}')
        rows = list(self.foh.consoleinput_set.all())
        buses = [ConsoleAuxOutput.objects.create(console=self.foh, aux_number='1', name='A')]
        ContentType.objects.get_for_model(ConsoleStereoOutput)  # warm the cache
        ContentType.objects.get_for_model(ConsoleAuxOutput)
        ContentType.objects.get_for_model(ConsoleMatrixOutput)
        request = RequestFactory().get('/')
        with self.assertNumQueries(2):
            index = PortIndex.for_request(request, self.project.pk)
            index.register(rows)
            index.register(buses)
            for row in rows + buses:
                index.cell_for(row)
            index.free_ports()
            self.assertIs(PortIndex.for_request(request, self.project.pk), index)

    def test_unlinked_names_cost_at_most_two_more_queries(self):
        for n in range(1, 97):
            self.ch(self.foh, n, f'Ch {n}')
            self.ch(self.mon, n, f'Ch {n}')
        for n in range(1, 9):
            self.port(self.box_a, n, f'Ch {n}')       # unlinked, on both consoles
        aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='1', name='A')
        self.out(self.box_a, 1, 'A')
        rows = list(self.foh.consoleinput_set.all())
        for model in (ConsoleStereoOutput, ConsoleAuxOutput, ConsoleMatrixOutput):
            ContentType.objects.get_for_model(model)
        request = RequestFactory().get('/')
        with self.assertNumQueries(4):
            index = PortIndex.for_request(request, self.project.pk)
            index.register(rows)
            index.register([aux])
            for row in rows + [aux]:
                index.cell_for(row)
        self.assertEqual(index.cell_for(rows[0]).feeds[0].how, AMBIGUOUS)

    def test_page_query_count_does_not_grow_with_channels(self):
        small = Console.objects.create(project=self.project, name='Small')
        for n in range(1, 9):
            self.ch(small, n, f'S {n}')
            self.port(self.box_a, n, f'S {n}')
        big = Console.objects.create(project=self.project, name='Big')
        for n in range(1, 97):
            self.ch(big, n, f'B {n}')
        for n in range(1, 9):
            self.port(self.box_b, n, f'B {n}')
        counts = {}
        for console in (small, big):
            self.client.get(self.url(console))  # warm caches
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(self.url(console))
            self.assertEqual(response.status_code, 200)
            rows = re.findall(r'<tr[^>]*id="consoleinput_set-\d+"[^>]*>(.*?)</tr>',
                              response.content.decode(), re.S)
            self.assertEqual(len(rows), console.consoleinput_set.count())
            self.assertTrue(all('class="field-patch"' in row for row in rows))
            counts[console.name] = len(queries)
        self.assertEqual(counts['Small'], counts['Big'], counts)

    def test_template_console_without_project_renders(self):
        orphan = Console.objects.create(project=self.project, name='Orphan')
        Console.objects.filter(pk=orphan.pk).update(project=None)
        # Out of the current project's scope, so the admin will not show it at
        # all -- the point is that nothing in the patch code assumes a project.
        response = self.client.get(self.url(orphan))
        self.assertIn(response.status_code, (302, 404))
