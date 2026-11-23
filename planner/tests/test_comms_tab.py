"""The Wiring Diagram's Comms tab and the Dante tab's network headers (PR B).

The comms patch itself (pages, rules, the Connections table on the other
tabs) is test_comm_devices.py.

    python manage.py test planner.tests.test_comms_tab \\
        --settings=audiopatch.test_settings
"""
import io
import json
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from planner.connections import layout as L
from planner.connections import svg
from planner.connections import tabs as T
from planner.connections.comms_tab import comms_view
from planner.connections.graph import digest, project_graph
from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, Device, DeviceInput, DeviceOutput, Project,
)
from planner.tests.test_comm_devices import PLAIN_STATIC, CommFixture, make_comm, make_device
from planner.tests.test_wiring_view import svg_of

NAME = '<img src=x onerror=alert(1)>'
ESCAPED = '&lt;img src=x onerror=alert(1)&gt;'


class CommsShow(CommFixture):
    """Program: FOH Aux 12 -> Rio Out 5 -> Arcadia 4W 1 receive; 4W 1 send ->
    Rio In 3 -> FOH Ch 5. Camera comm on the MK88 and prod comm on the DVS
    Mac over Dante, a wired 2-wire chain, and a second main station."""

    def setUp(self):
        super().setUp()
        self.foh = Console.objects.create(project=self.project, name='FOH')
        aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='12', name='Program')
        out5 = self.out(self.rio, 5)
        out5.console_output = aux
        out5.signal_name = 'Program'
        out5.save()
        ch = ConsoleInput.objects.create(console=self.foh, input_ch='5', source='Comm ret')
        DeviceInput.objects.filter(pk=self.inp(self.rio, 3).pk).update(
            console_input=ch, signal_name='Comm ret')
        Device.objects.filter(pk=self.rio.pk).update(console_connection='dante')
        DeviceOutput.objects.filter(pk=self.out(self.mk88, 3).pk).update(signal_name='Camera PL')
        self.arc_b = make_comm(self.project, 'Arcadia B', ins=2, outs=2, four=0, two=0)
        r = self.post(din1='MK88 In 3', din2='DVS FOH In 1',
                      dout1='Camera PL · MK88 Out 3', dout2='DVS FOH Out 1',
                      dout3='Arcadia B Dante In 1',
                      **{'4w1_send': 'Comm ret · Rio SL In 3',
                         '4w1_recv': 'Program · Rio SL Out 5',
                         '2w1_dest': 'Wired BP chain SL', '2w1_cable': 'XLR3'})
        assert r.status_code == 302, r.content.decode()[:2000]

    def view(self):
        return comms_view(project_graph(self.project))

    def lay(self, view=None):
        return L.layout(view or self.view(), **T.layout_options(T.COMMS))

    def node(self, view, label):
        return next(n for n in view['nodes'] if n['label'] == label)

    def box(self, lay, box_id):
        return next(b for b in lay.boxes if b.id == box_id)

    def route(self, lay, view, frm, to):
        ids = [e['id'] for e in view['edges']
               if (e['from_ports'], e['to_ports']) == (frm, to)]
        self.assertEqual(len(ids), 1, (frm, to))
        return next(r for r in lay.routes if r.id == ids[0])


@override_settings(STORAGES=PLAIN_STATIC)
class CommsViewTests(CommsShow, TestCase):
    def test_one_line_per_port_and_rows_per_side(self):
        view = self.view()
        self.assertEqual([(e['from_ports'], e['to_ports'], e['transports'][0], e['label'])
                          for e in view['edges']], [
            ('Dante Out 1', 'Out 3', 'dante', ''),               # from the Arcadia, by row
            ('Dante Out 2', 'Out 1', 'dante', ''),
            ('Dante Out 3', 'Dante In 1', 'dante', ''),
            ('4W 1', 'In 3', 'analog', '4W adapter'),
            ('2W 1', '', 'analog', 'XLR3'),
            ('In 1', 'Dante In 2', 'dante', ''),                 # DVS FOH
            ('In 3', 'Dante In 1', 'dante', ''),                 # MK88
            ('Out 5', '4W 1', 'analog', '4W adapter'),           # Rio SL
        ])
        rows = {n['label']: {box: [r['label'] for r in rs] for box, rs in n['rows'].items()}
                for n in view['nodes'] if 'rows' in n}
        self.assertEqual(rows['Arcadia'], {'main': [
            'Dante In 1', 'Dante In 2', 'Dante Out 1', 'Dante Out 2', 'Dante Out 3',
            '4W 1', '2W 1']})
        # A Rio row says where its signal comes from / goes, and its name.
        self.assertEqual(rows['Rio SL'], {'to': ['Out 5 ← FOH Aux 12 (Program)'],
                                          'from': ['In 3 → FOH Ch 5 (Comm ret)']})
        self.assertEqual(rows['MK88'], {'to': ['In 3'], 'from': ['Out 3 (Camera PL)']})
        self.assertEqual(rows['DVS FOH'], {'to': ['In 1'], 'from': ['Out 1']})
        self.assertEqual(rows['Arcadia B'], {'from': ['Dante In 1']})
        self.assertEqual([n['label'] for n in view['nodes'] if n['kind'] == 'destination'],
                         ['Wired BP chain SL'])
        self.assertNotIn('FOH', [n['label'] for n in view['nodes']])     # no console column

    def test_the_port_convention(self):
        """Dante Out -> a device Output, Dante In <- a device Input, 4W send
        -> a device Input, 4W receive <- a device Output."""
        for e in self.view()['edges']:
            if not e['links']:
                continue
            frm, to = e['links'][0]['from_ref'], e['links'][0]['to_ref']
            pair = (e['from_ports'].rsplit(' ', 1)[0], frm.split(':')[0],
                    e['to_ports'].rsplit(' ', 1)[0], to.split(':')[0])
            self.assertIn(pair, {
                ('Dante Out', 'deviceoutput', 'Out', 'deviceoutput'),
                ('In', 'deviceinput', 'Dante In', 'deviceinput'),
                ('Dante Out', 'deviceoutput', 'Dante In', 'deviceinput'),
                ('4W', 'commport', 'In', 'deviceinput'),
                ('Out', 'deviceoutput', '4W', 'commport'),
            })

    def test_the_project_graph_is_not_changed_by_the_view(self):
        full = project_graph(self.project)
        before = json.dumps(full, sort_keys=True)
        comms_view(full)
        T.graph_view(full, T.DANTE)
        self.assertEqual(json.dumps(full, sort_keys=True), before)

    def test_a_project_with_no_comm_device_reads_as_before(self):
        plain = Project.objects.create(name='Plain', owner=self.owner)
        box = make_device(plain, 'Box')
        graph = project_graph(plain)
        self.assertEqual([sorted(n) for n in graph['nodes']],
                         [['console_connection', 'id', 'kind', 'label', 'ports', 'primary_ip',
                           'secondary_ip']])
        text = json.dumps(graph)
        for key in ('comm', 'two_wire', 'dante_network', 'from_name', 'group'):
            self.assertNotIn(key, text)
        self.assertEqual(comms_view(graph)['nodes'], [])
        # and its digest does not depend on comm data elsewhere
        before = digest(graph)
        self.post(dout4='MK88 Out 8')
        self.assertEqual(digest(project_graph(plain)), before)
        self.assertEqual(box.kind, 'io')


@override_settings(STORAGES=PLAIN_STATIC)
class CommsLayoutTests(CommsShow, TestCase):
    def test_three_columns_and_which_box_is_where(self):
        lay = self.lay()
        self.assertEqual([title for title, _, _ in lay.columns], list(L.COMMS_TITLES))
        x = {title: x for title, x, _ in lay.columns}
        where = {b.id.split('#')[-1] if '#' in b.id else 'dest': set() for b in lay.boxes}
        for b in lay.boxes:
            where['dest' if '#' not in b.id else b.id.split('#')[-1]].add((b.label, b.x))
        self.assertEqual(where['to'], {(n, x['To comms']) for n in ('Rio SL', 'MK88', 'DVS FOH')})
        self.assertEqual(where['main'], {(n, x['Comm devices']) for n in ('Arcadia', 'Arcadia B')})
        self.assertEqual(where['from'], {(n, x['From comms'])
                                         for n in ('Rio SL', 'MK88', 'DVS FOH', 'Arcadia B')})
        self.assertEqual(where['dest'], {('Wired BP chain SL', x['From comms'])})
        self.assertEqual(self.box(lay, f'device:{self.arc.pk}#main').sub, 'Comm device')

    def test_every_route_runs_left_to_right(self):
        lay = self.lay()
        self.assertEqual(lay.not_drawn, [])
        self.assertEqual(len(lay.routes), 8)
        for route in lay.routes:
            xs = [x for x, _ in route.points]
            self.assertEqual(xs, sorted(xs), route.id)
            self.assertLess(xs[0], xs[-1], route.id)
            for (x0, y0), (x1, y1) in zip(route.points, route.points[1:]):
                self.assertTrue(abs(x0 - x1) < 0.01 or abs(y0 - y1) < 0.01, route.id)   # orthogonal

    def test_a_4w_ports_receive_and_send_share_one_row(self):
        view = self.view()
        lay = self.lay(view)
        arc = self.box(lay, f'device:{self.arc.pk}#main')
        recv = self.route(lay, view, 'Out 5', '4W 1')
        send = self.route(lay, view, '4W 1', 'In 3')
        # in on the left edge, out on the right edge, at one height
        self.assertEqual(recv.points[-1], (arc.x, recv.points[-1][1]))
        self.assertEqual(send.points[0], (arc.x + arc.w, send.points[0][1]))
        self.assertEqual(recv.points[-1][1], send.points[0][1])
        row = arc.slots.index('4W 1')
        self.assertEqual(recv.points[-1][1], arc.row_y(row))
        self.assertEqual((send.lines, recv.lines), (['4W adapter'], ['4W adapter']))

    def test_dante_in_rows_take_lines_on_the_left_dante_out_and_2w_on_the_right(self):
        view = self.view()
        lay = self.lay(view)
        arc = self.box(lay, f'device:{self.arc.pk}#main')
        self.assertEqual(arc.slots, ['Dante In 1', 'Dante In 2', 'Dante Out 1', 'Dante Out 2',
                                     'Dante Out 3', '4W 1', '2W 1'])
        ins = {arc.slots[i] for i in arc.in_slot.values()}
        outs = {arc.slots[i] for i in arc.out_slot.values()}
        self.assertEqual(ins, {'Dante In 1', 'Dante In 2', '4W 1'})
        self.assertEqual(outs, {'Dante Out 1', 'Dante Out 2', 'Dante Out 3', '4W 1', '2W 1'})
        # every line meets its own row, and no two lines share a side of a row
        for seg, i in list(arc.in_slot.items()) + list(arc.out_slot.items()):
            self.assertEqual(arc.slot_y(seg), arc.row_y(i))
        self.assertEqual(len(set(arc.in_slot.values())), len(arc.in_slot))
        self.assertEqual(len(set(arc.out_slot.values())), len(arc.out_slot))
        two_wire = self.route(lay, view, '2W 1', '')
        self.assertEqual(two_wire.lines, ['XLR3'])
        self.assertEqual(two_wire.points[0][0], arc.x + arc.w)

    def test_boxes_do_not_overlap_and_rows_fit_their_box(self):
        lay = self.lay()
        by_x = {}
        for b in lay.boxes:
            by_x.setdefault(b.x, []).append(b)
        for boxes in by_x.values():
            boxes.sort(key=lambda b: b.y)
            for a, b in zip(boxes, boxes[1:]):
                self.assertLessEqual(a.y + a.h, b.y)
        for b in lay.boxes:
            for i in range(len(b.slots)):
                self.assertLess(b.row_y(i), b.y + b.h)
                self.assertGreater(b.row_y(i), b.y + b.head - 1)
        self.assertGreater(lay.width, max(b.x + b.w for b in lay.boxes))

    def test_a_comm_device_with_no_patch_is_still_drawn(self):
        lone = Project.objects.create(name='Lone', owner=self.owner)
        make_comm(lone, 'Spare station')
        view = comms_view(project_graph(lone))
        lay = self.lay(view)
        self.assertEqual([(b.label, b.slots) for b in lay.boxes], [('Spare station', [])])
        self.assertEqual(lay.routes, [])

    def test_the_seven_column_layout_is_the_default(self):
        full = project_graph(self.project)
        lay = L.layout(full)
        self.assertEqual([t for t, _, _ in lay.columns][:3],
                         ['Device inputs', 'Console', 'Device outputs'])
        self.assertTrue(all(not b.out_slot for b in lay.boxes))


@override_settings(STORAGES=PLAIN_STATIC)
class CommsPageTests(CommsShow, TestCase):
    wiring = reverse('planner:wiring_diagram')

    def test_the_tab_draws_the_patch(self):
        r = self.client.get(self.wiring + '?view=comms')
        page = r.content.decode()
        self.assertIn('<a href="?view=comms" aria-current="page">Comms</a>', page)
        drawing = svg_of(r)
        for text in ('To comms', 'Comm devices', 'From comms', 'Arcadia', 'Arcadia B',
                     'data-slot="Out 5 ← FOH Aux 12 (Program)"', 'data-slot="4W 1"',
                     'data-slot="In 3 → FOH Ch 5 (Comm ret)"', 'data-slot="Dante In 2"',
                     'Wired BP chain SL', '2-wire destination', '4W adapter', 'XLR3'):
            self.assertIn(text, drawing, text)
        self.assertEqual(drawing.count('class="wd-link"'), 8)
        self.assertEqual(drawing.count('class="wd-edge confirmed network"'), 5)     # Dante
        self.assertNotIn('see the Comms tab', page)
        self.assertNotIn('Not drawn', page)
        self.assertNotIn('No comm device yet', page)

    def test_the_other_tabs_list_the_links_and_send_you_here(self):
        for view, count in (('overview', 7), ('dante', 5), ('analog', 2)):
            page = self.client.get(f'{self.wiring}?view={view}').content.decode()
            self.assertEqual(page.count('see the Comms tab'), count, view)
            self.assertNotIn('data-slot="4W 1"', page)
            self.assertNotIn('Not drawn', page)
        # a device this tab does not draw is still named in the table
        page = self.client.get(f'{self.wiring}?view=dante').content.decode()
        self.assertIn('<td>Arcadia · Dante Out 1</td><td>MK88 · Out 3</td>', page)
        self.assertIn('<td>DVS FOH · In 1</td><td>Arcadia · Dante In 2</td>', page)

    def test_a_link_between_two_dante_networks_is_warned_about_here_too(self):
        self.post(dout4='Rio SL Out 2 [Main 96k]')
        page = self.client.get(self.wiring + '?view=comms').content.decode()
        self.assertIn('Dante link between different Dante networks', page)
        self.assertIn('Arcadia → Rio SL', page)
        self.assertIn('Comms 48k / Main 96k', page)
        self.assertIn('Warnings (1)', page)
        # not when one side has no network, nor for the 4-wire cables to the same box
        Device.objects.filter(pk=self.rio.pk).update(dante_network='')
        self.assertNotIn('different Dante networks',
                         self.client.get(self.wiring + '?view=comms').content.decode())

    def test_no_comm_device_says_so(self):
        plain = Project.objects.create(name='Plain', owner=self.owner)
        make_device(plain, 'Box')
        self.login(self.owner, plain)
        page = self.client.get(self.wiring + '?view=comms').content.decode()
        self.assertIn('No comm device yet', page)

    def test_names_are_text_in_the_drawing(self):
        Device.objects.filter(pk=self.mk88.pk).update(name=NAME)
        Device.objects.filter(pk=self.arc.pk).update(name=NAME + ' comm')
        DeviceOutput.objects.filter(pk=self.out(self.rio, 5).pk).update(signal_name=NAME)
        self.arc.comm_ports.filter(kind='2w', number=1).update(destination=NAME, cable_type=NAME)
        page = self.client.get(self.wiring + '?view=comms').content.decode()
        self.assertNotIn(NAME, page)
        self.assertIn(f'({ESCAPED})', page)
        self.assertGreaterEqual(page.count(ESCAPED), 6)

    def test_download_pdf_has_the_comms_tab(self):
        from PyPDF2 import PdfReader     # pinned in requirements.txt; pypdf is not
        r = self.client.get(reverse('planner:wiring_diagram_pdf'), {'tabs': 'comms'})
        self.assertEqual(r.status_code, 200)
        pages = [p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages]
        text = '\n'.join(pages)
        self.assertTrue(pages[0].split('\n')[1].startswith('Comms'), pages[0][:200])
        for word in ('TO COMMS', 'COMM DEVICES', 'FROM COMMS', 'Arcadia B', '4W 1',
                     'Out 5 ← FOH Aux 12 (Program)', 'Wired BP chain SL', '4W adapter'):
            self.assertIn(word, text, word)
        everything = self.client.get(reverse('planner:wiring_diagram_pdf'))
        heads = [p.extract_text().split('\n')[1].split(' ')[0]
                 for p in PdfReader(io.BytesIO(everything.content)).pages
                 if p.extract_text().startswith(self.project.name)]
        self.assertEqual(heads, ['Overview', 'Dante', 'Analogue/AES', 'Speaker', 'Comms'])


@override_settings(STORAGES=PLAIN_STATIC)
class DanteNetworkHeaderTests(CommsShow, TestCase):
    def dante(self):
        view = T.graph_view(project_graph(self.project), T.DANTE)
        return view, L.layout(view, **T.layout_options(T.DANTE))

    def test_device_boxes_sit_under_their_network_and_no_network_is_last(self):
        loose = make_device(self.project, 'Loose box')
        Device.objects.filter(pk=loose.pk).update(console_connection='dante')
        view, lay = self.dante()
        ins = [g for g in lay.groups if g.column == L.IO_IN]
        outs = [g for g in lay.groups if g.column == L.IO_OUT]
        self.assertEqual([g.label for g in ins], ['Comms 48k', 'Main 96k', 'No network set'])
        self.assertEqual([g.label for g in outs], ['Main 96k'])
        self.assertEqual([g.label for g in lay.groups if g.column == L.CONSOLE], [])
        under = {}
        for g in ins:
            under[g.label] = sorted(b.label for b in lay.boxes
                                    if b.column == L.IO_IN and b.group == g.key)
        self.assertEqual(under, {'Comms 48k': ['Arcadia', 'Arcadia B', 'DVS FOH', 'MK88'],
                                 'Main 96k': ['Rio SL'], 'No network set': ['Loose box']})
        # headers top to bottom, each above its own boxes and below the last group's
        ys = [g.y for g in ins]
        self.assertEqual(ys, sorted(ys))
        for g in ins:
            for b in lay.boxes:
                if b.group == g.key:
                    self.assertGreaterEqual(b.y, g.y + g.head)
        console = next(b for b in lay.boxes if b.kind == 'console')
        self.assertIsNone(console.group)
        drawing = svg.render(lay)
        self.assertEqual(drawing.count('class="wd-group"'), 4)
        self.assertIn('No network set', drawing)

    def test_every_device_on_dante_is_boxed_with_or_without_a_console_link(self):
        """Console connection Dante, or a Dante network set, or a comm
        device: each puts a device on the tab. Nothing else does."""
        make_device(self.project, 'Net only', network='Main 96k')
        make_device(self.project, 'Dante only', console_connection='dante')
        make_device(self.project, 'MADI rack', console_connection='madi')
        make_device(self.project, 'Unset rack')
        view, lay = self.dante()
        devices = {n['label']: n for n in view['nodes'] if n['kind'] == 'device'}
        self.assertEqual(sorted(devices), ['Arcadia', 'Arcadia B', 'DVS FOH', 'Dante only',
                                           'MK88', 'Net only', 'Rio SL'])
        self.assertEqual({name: n['group']['label'] for name, n in devices.items()}, {
            'Arcadia': 'Comms 48k', 'Arcadia B': 'Comms 48k', 'DVS FOH': 'Comms 48k',
            'MK88': 'Comms 48k', 'Net only': 'Main 96k', 'Rio SL': 'Main 96k',
            'Dante only': 'No network set'})
        for n in devices.values():
            self.assertEqual(n['lines'], ['No IP'], n['label'])
        # one box each for the comms-only devices, and no line to any of them
        ids = {devices[name]['id'] for name in ('MK88', 'DVS FOH', 'Net only', 'Dante only')}
        boxes = [b for b in lay.boxes if b.node in ids]
        self.assertEqual(len(boxes), 4)
        self.assertEqual([r for r in lay.routes if {r.from_node, r.to_node} & ids], [])
        # comms links are still only listed here, never drawn
        self.assertEqual(len(lay.routes), len([e for e in view['edges'] if not e.get('comm')]))
        self.assertTrue(any(e.get('comm') for e in view['edges']))

    def test_a_network_on_a_madi_device_boxes_it_and_keeps_its_links_on_analogue(self):
        Device.objects.filter(pk=self.rio.pk).update(console_connection='madi')
        view, lay = self.dante()
        rio = next(n for n in view['nodes'] if n['label'] == 'Rio SL')
        self.assertEqual(rio['group']['label'], 'Main 96k')
        self.assertEqual(lay.routes, [])
        analog = T.graph_view(project_graph(self.project), T.ANALOG)
        self.assertEqual(len([e for e in analog['edges'] if T.is_console_link(e)]), 2)

    def test_the_banner_leaves_out_devices_used_only_for_comms(self):
        """MK88 and DVS FOH are patched to the Arcadia only, with no Console
        connection: nothing to set. A console link with none set is listed."""
        graph = project_graph(self.project)
        self.assertEqual(T.unset_devices(graph), [])
        wiring = reverse('planner:wiring_diagram')
        for tab in ('dante', 'analog'):
            page = self.client.get(f'{wiring}?view={tab}')
            self.assertEqual(page.context['unset'], [], tab)
            self.assertNotContains(page, 'no Console connection set')
        Device.objects.filter(pk=self.rio.pk).update(console_connection='')
        self.assertEqual([n['label'] for n in T.unset_devices(project_graph(self.project))],
                         ['Rio SL'])
        page = self.client.get(f'{wiring}?view=dante')
        self.assertContains(page, '1 I/O device has no Console connection set')
        # B only is a console link too
        DeviceInput.objects.filter(device=self.rio).update(console_input=None)
        for output in DeviceOutput.objects.filter(device=self.rio):
            output.console_output = None        # a generic key: no queryset update
            output.save()
        self.assertEqual(T.unset_devices(project_graph(self.project)), [])
        ch = ConsoleInput.objects.get(console=self.foh, input_ch='5')
        DeviceInput.objects.filter(pk=self.inp(self.mk88, 1).pk).update(console_input_b=ch)
        self.assertEqual([n['label'] for n in T.unset_devices(project_graph(self.project))],
                         ['MK88'])

    def test_the_same_network_typed_two_ways_is_one_header(self):
        Device.objects.filter(pk=self.rio.pk).update(dante_network=' comms 48K')
        _, lay = self.dante()
        self.assertEqual({g.label for g in lay.groups}, {'Comms 48k'})

    def test_no_headers_until_a_network_is_set(self):
        Device.objects.filter(project=self.project).update(dante_network='')
        view, lay = self.dante()
        self.assertEqual(lay.groups, [])
        self.assertNotIn('group', json.dumps(view['nodes']))

    def test_a_network_name_with_markup_is_text(self):
        Device.objects.filter(pk=self.rio.pk).update(dante_network=NAME)
        page = self.client.get(reverse('planner:wiring_diagram') + '?view=dante').content.decode()
        self.assertNotIn(NAME, page)
        self.assertIn(ESCAPED, page)


@override_settings(STORAGES=PLAIN_STATIC)
class CommsNoteTests(CommsShow, TestCase):
    """A device whose only links are comms links says so on the Overview and
    the Dante tab, where none of its lines are drawn."""
    wiring = reverse('planner:wiring_diagram')
    LINK = '<a class="wd-note" href="?view=comms">'

    def notes(self, tab):
        full = project_graph(self.project)
        view = T.comms_notes(T.graph_view(full, tab), full)
        return {n['label']: n['comms_note'] for n in view['nodes'] if 'comms_note' in n}

    def test_each_comms_only_device_counts_its_own_patches(self):
        expected = {
            'Arcadia': '8 comms patches · see Comms tab',       # 7 links and a 2-wire
            'Arcadia B': '1 comms patch · see Comms tab',
            'MK88': '2 comms patches · see Comms tab',
            'DVS FOH': '2 comms patches · see Comms tab',
        }
        for tab in (T.OVERVIEW, T.DANTE):
            self.assertEqual(self.notes(tab), expected, tab)      # not the Rio: console links

    def test_a_device_with_no_patch_or_another_link_has_no_note(self):
        make_comm(self.project, 'Spare station')
        make_device(self.project, 'Idle box', network='Main 96k')
        notes = self.notes(T.DANTE)
        for name in ('Spare station', 'Idle box', 'Rio SL', 'FOH'):
            self.assertNotIn(name, notes)
        # one console link and the MK88 is no longer comms only
        ch = ConsoleInput.objects.get(console=self.foh, input_ch='5')
        DeviceInput.objects.filter(pk=self.inp(self.mk88, 1).pk).update(console_input=ch)
        self.assertNotIn('MK88', self.notes(T.OVERVIEW))
        self.assertNotIn('MK88', self.notes(T.DANTE))

    def test_the_project_graph_is_untouched(self):
        full = project_graph(self.project)
        before = digest(full)
        T.comms_notes(full, full)
        self.assertEqual(digest(full), before)
        self.assertNotIn('comms_note', json.dumps(full['nodes']))

    def test_the_note_is_a_line_in_the_box_linking_to_the_comms_tab(self):
        for tab, boxes in (('overview', 6), ('dante', 4)):      # Overview: an I/O device's in and out box
            r = self.client.get(f'{self.wiring}?view={tab}')
            drawing = svg_of(r)
            self.assertEqual(drawing.count(self.LINK), boxes, tab)
            self.assertIn(f'{self.LINK}<text class="s ln note"', drawing)
            # two lines, broken after the dot, in one link
            for count in ('8 comms patches ·', '1 comms patch ·', '2 comms patches ·'):
                self.assertRegex(drawing, re.escape(self.LINK) + r'<text class="s ln note"[^>]*>'
                                 + re.escape(count) + r'</text><text class="s ln note"[^>]*>'
                                 r'see Comms tab</text></a>', (tab, count))
        for tab in ('analog', 'speakers', 'comms'):
            page = self.client.get(f'{self.wiring}?view={tab}').content.decode()
            self.assertNotIn('class="wd-note"', page, tab)
            self.assertNotIn('see Comms tab', page, tab)

    def test_the_note_is_inside_its_box(self):
        full = project_graph(self.project)
        view = T.comms_notes(T.graph_view(full, T.DANTE), full)
        lay = L.layout(view, **T.layout_options(T.DANTE))
        noted = [b for b in lay.boxes if b.note]
        self.assertEqual(sorted(b.label for b in noted), ['Arcadia', 'Arcadia B', 'DVS FOH', 'MK88'])
        for b in noted:
            first, last = b.text_rows[-2:]
            self.assertEqual((first[0], last[0]), ('s ln note', 's ln note'))
            self.assertEqual(f'{first[1]} {last[1]}', b.note)
            self.assertEqual(last[1], 'see Comms tab')
            self.assertEqual(last[2] - first[2], L.LINE_H)
            self.assertLess(last[2], b.h)
            self.assertEqual(b.text_rows[-3][1], 'No IP')         # under the IP line
            for _, line, _ in b.text_rows:
                self.assertLessEqual(len(line) * L.CHAR_W, L.TEXT_W)
        self.assertTrue(all(not b.note for b in lay.boxes if b.label == 'Rio SL'))

    def test_the_pdf_has_the_same_text(self):
        from PyPDF2 import PdfReader     # pinned in requirements.txt; pypdf is not
        for tab in ('overview', 'dante'):
            r = self.client.get(reverse('planner:wiring_diagram_pdf'), {'tabs': tab})
            self.assertEqual(r.status_code, 200)
            text = ' '.join('\n'.join(
                p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages).split())
            for note in ('8 comms patches · see Comms tab', '1 comms patch · see Comms tab',
                         '2 comms patches · see Comms tab'):
                self.assertIn(note, text, (tab, note))
        r = self.client.get(reverse('planner:wiring_diagram_pdf'), {'tabs': 'analog'})
        text = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
        self.assertNotIn('see Comms tab', text)
