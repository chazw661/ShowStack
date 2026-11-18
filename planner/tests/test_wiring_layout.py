"""Wiring diagram layout: which boxes and edges a show draws, and where.

Run with::

    python manage.py test planner.tests.test_wiring_layout \\
        --settings=audiopatch.test_settings
"""
from django.test import SimpleTestCase, TestCase

from planner.connections import layout as L
from planner.connections.graph import project_graph
from planner.models import AmpLocation, ConsoleAuxOutput
from planner.tests.connection_fixtures import ConnectionFixtures


class WiringShow(ConnectionFixtures):
    """One small show covering every kind of box and line."""

    def setUp(self):
        super().setUp()
        self.desk = self.console('FOH Desk')
        self.box = self.device('Stage Box')
        # I/O input -> console (confirmed)
        self.device_input(self.box, 1, self.channel(self.desk, 1, 'Kick'))
        # console bus -> I/O output (confirmed)
        aux = ConsoleAuxOutput.objects.create(console=self.desk, aux_number='1', name='Wedge 1')
        self.device_output(self.box, 1, 'Wedge 1', bus=aux)
        # I/O output -> processor -> amp (inferred: the processor path)
        self.sl = self.p1('SL P1')
        self.p1_in(self.sl, 'AES', 1, 'Main L')
        self.device_output(self.box, 2, 'Main L')
        self.p1_out(self.sl, 'AES', 1, 'Main L')
        self.sl_amp = self.amp('SL Amp', rack='SL Racks')
        self.amp_channel(self.sl_amp, 1, aes_input='Main L')
        # I/O output -> amp, skipping the processor column
        self.device_output(self.box, 3, 'Fill')
        self.ff_amp = self.amp('FF Amp', rack='FOH Racks')
        self.amp_channel(self.ff_amp, 1, analog_input='Fill')
        # An output two processors could take: an ambiguous "?" edge
        self.sr = self.p1('SR P1')
        self.p1_in(self.sl, 'AES', 2, 'Delay')
        self.p1_in(self.sr, 'AES', 1, 'Delay')
        self.device_output(self.box, 4, 'Delay')
        # A second SL amp (Amp.location is required: only the "not linked"
        # amp rack falls under "No location")
        self.sl_amp2 = self.amp('SL Amp 2', rack='SL Racks')
        AmpLocation.objects.filter(project=self.project, name='SL Racks').update(sort_order=1)
        AmpLocation.objects.filter(project=self.project, name='FOH Racks').update(sort_order=2)
        # Amp -> speaker array (confirmed), and a run to text no array matches
        self.k2 = self.array(self.prediction(), 'K2 L')
        self.linked_cable(self.sl_amp, self.k2, label=self.zone('HL'), count=2, length=100)
        self.text_cable(self.zone('OFL'), destination='Nowhere')
        # Devices with one side only
        self.drums = self.device('Drum Box')
        self.device_output(self.drums, 1, '')
        self.mics = self.device('Mic Box')
        self.device_input(self.mics, 1)

    def draw(self):
        self.graph = project_graph(self.project)
        self.lay = L.layout(self.graph)
        self.boxes = {b.id: b for b in self.lay.boxes}
        return self.lay

    def route(self, frm, to):
        [route] = [r for r in self.lay.routes if r.from_node == frm and r.to_node == to]
        return route


class WiringLayoutTests(WiringShow, TestCase):
    def setUp(self):
        super().setUp()
        self.draw()

    def column(self, box_id):
        return self.boxes[box_id].column

    def test_each_kind_of_box_is_in_its_column(self):
        box = f'device:{self.box.pk}'
        self.assertEqual(self.column(f'{box}#in'), L.IO_IN)
        self.assertEqual(self.column(f'console:{self.desk.pk}'), L.CONSOLE)
        self.assertEqual(self.column(f'{box}#out'), L.IO_OUT)
        self.assertEqual(self.column(f'processor:{self.sl.pk}'), L.PROCESSOR)
        self.assertEqual(self.column(f'amp:{self.ff_amp.pk}'), L.AMP)
        self.assertEqual(self.column('amp_rack:unlinked'), L.AMP)
        self.assertEqual(self.column(f'speaker_array:{self.k2.pk}'), L.SPEAKER)
        self.assertEqual(self.boxes[f'{box}#in'].label, 'Stage Box · inputs')
        self.assertEqual(self.boxes[f'{box}#out'].label, 'Stage Box · outputs')

    def test_a_device_with_one_side_gets_one_box(self):
        self.assertIn(f'device:{self.drums.pk}#out', self.boxes)
        self.assertNotIn(f'device:{self.drums.pk}#in', self.boxes)
        self.assertIn(f'device:{self.mics.pk}#in', self.boxes)
        self.assertNotIn(f'device:{self.mics.pk}#out', self.boxes)

    def test_expected_edges(self):
        box, desk = f'device:{self.box.pk}', f'console:{self.desk.pk}'
        sl, sl_amp = f'processor:{self.sl.pk}', f'amp:{self.sl_amp.pk}'
        self.assertEqual(self.route(box, desk).classes, ('confirmed',))
        bus = self.route(desk, box)
        self.assertEqual(bus.label, 'Aux 1 → Out 1')
        self.assertEqual(bus.points[-1][0], self.boxes[f'{box}#out'].x)     # into the outputs box
        # the processor path
        self.assertEqual(self.route(box, sl).label, 'Out 2 → AES 1')
        self.assertEqual(self.route(sl, sl_amp).classes, ('inferred',))
        # direct I/O -> amp starts at the outputs box
        direct = self.route(box, f'amp:{self.ff_amp.pk}')
        out_box = self.boxes[f'{box}#out']
        self.assertEqual(direct.points[0][0], out_box.x + out_box.w)
        # the confirmed PA run carries its cable label
        self.assertEqual(self.route(sl_amp, f'speaker_array:{self.k2.pk}').label, "HL · 2× NL 4 100'")

    def test_text_only_speaker_is_an_unlinked_box_in_the_speaker_column(self):
        node = self.boxes['unlinked:text:nowhere']
        self.assertEqual((node.column, node.style, node.label), (L.SPEAKER, 'unlinked', 'Nowhere'))
        route = self.route('amp_rack:unlinked', 'unlinked:text:nowhere')
        self.assertTrue(route.question)
        self.assertEqual(route.label, "? Nowhere · OFL · 2× NL 4 100'")
        self.assertEqual(route.classes, ('unlinked',))

    def test_ambiguous_feed_is_a_question_edge_to_its_text(self):
        [route] = [r for r in self.lay.routes if 'ambiguous' in r.classes]
        target = self.boxes[route.to_node]
        self.assertEqual((target.column, target.style, target.label, target.sub),
                         (L.PROCESSOR, 'unlinked', 'Delay', 'ambiguous'))
        self.assertTrue(route.question)
        self.assertEqual(route.label, '? Delay · Out 4')

    # -- geometry -------------------------------------------------------------

    def test_the_outputs_box_sits_between_console_and_processor(self):
        out = self.boxes[f'device:{self.box.pk}#out']
        desk = self.boxes[f'console:{self.desk.pk}']
        proc = self.boxes[f'processor:{self.sl.pk}']
        self.assertLess(desk.x + desk.w, out.x)
        self.assertLess(out.x + out.w, proc.x)

    def test_no_route_runs_right_to_left(self):
        self.assertEqual(self.lay.not_drawn, [])
        self.assertTrue(self.lay.routes)
        for route in self.lay.routes:
            for (x0, y0), (x1, y1) in zip(route.points, route.points[1:]):
                self.assertGreaterEqual(x1, x0, route.id)
                self.assertTrue(x0 == x1 or y0 == y1, f'{route.id} is not orthogonal')

    def test_routes_start_and_end_on_box_sides(self):
        for route in self.lay.routes:
            (x0, _), (x1, _) = route.points[0], route.points[-1]
            sides_out = {b.x + b.w for b in self.lay.boxes if b.node == route.from_node}
            sides_in = {b.x for b in self.lay.boxes if b.node == route.to_node}
            self.assertIn(x0, sides_out, route.id)
            self.assertIn(x1, sides_in, route.id)

    def test_a_skipping_edge_crosses_the_processor_column_clear_of_its_boxes(self):
        route = self.route(f'device:{self.box.pk}', f'amp:{self.ff_amp.pk}')
        procs = [b for b in self.lay.boxes if b.column == L.PROCESSOR]
        left = procs[0].x
        crossing = [(x0, x1, y0) for (x0, y0), (x1, y1) in zip(route.points, route.points[1:])
                    if y0 == y1 and x0 <= left < x1]
        self.assertEqual(len(crossing), 1)
        y = crossing[0][2]
        for box in procs:
            self.assertFalse(box.y <= y <= box.y + box.h, box.label)

    def test_boxes_in_a_column_do_not_overlap(self):
        for c in range(len(L.COLUMN_TITLES)):
            column = sorted((b for b in self.lay.boxes if b.column == c), key=lambda b: b.y)
            for a, b in zip(column, column[1:]):
                self.assertLessEqual(a.y + a.h, b.y, f'{a.label} / {b.label}')

    def test_amps_of_one_location_are_contiguous_in_location_order(self):
        amps = sorted((b for b in self.lay.boxes if b.column == L.AMP), key=lambda b: b.y)
        names = {g.key: g.label for g in self.lay.groups}
        runs = []
        for box in amps:
            label = names[box.group]
            if not runs or runs[-1] != label:
                runs.append(label)
        self.assertEqual(runs, ['SL Racks', 'FOH Racks', L.NO_LOCATION])
        self.assertEqual([b.label for b in amps if b.group == ''], ['Amp rack — not linked'])
        self.assertEqual({b.label for b in amps if names[b.group] == 'SL Racks'},
                         {'SL Amp', 'SL Amp 2'})

    def test_group_headers_sit_above_their_first_amp(self):
        for group in self.lay.groups:
            first = min((b for b in self.lay.boxes if b.group == group.key), key=lambda b: b.y)
            self.assertLessEqual(group.y + L.GROUP_HEAD, first.y + 0.01)

    def test_the_layout_needs_no_database(self):
        with self.assertNumQueries(0):
            L.layout(self.graph)


class LayoutOfAHandBuiltGraphTests(SimpleTestCase):
    """layout() reads only the dict: no project, no ORM."""

    def test_an_empty_graph(self):
        lay = L.layout({'nodes': [], 'edges': [], 'warnings': []})
        self.assertEqual((lay.boxes, lay.routes), ([], []))
        self.assertGreater(lay.width, 0)

    def test_an_edge_that_would_run_backwards_is_not_drawn(self):
        graph = {'nodes': [{'id': 'console:1', 'kind': 'console', 'label': 'A'},
                           {'id': 'device:1', 'kind': 'device', 'label': 'B',
                            'ports': {'inputs': 1, 'outputs': 0}}],
                 'edges': [{'id': 'e1', 'from': 'console:1', 'to': 'device:1', 'label': 'x',
                            'links': [{'to_ref': 'deviceinput:1'}], 'status': 'confirmed'}],
                 'warnings': []}
        lay = L.layout(graph)
        self.assertEqual(lay.not_drawn, ['e1'])
        self.assertEqual(lay.routes, [])

    def test_long_labels_are_clipped_with_the_full_text_kept(self):
        self.assertEqual(L.clip('abcdefghij', L.CHAR_W * 5), 'abcd…')
        self.assertEqual(L.clip('abc', L.CHAR_W * 5), 'abc')
