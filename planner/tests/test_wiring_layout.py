"""Wiring diagram layout: which boxes and edges a show draws, and where.

Run with::

    python manage.py test planner.tests.test_wiring_layout \\
        --settings=audiopatch.test_settings
"""
import xml.etree.ElementTree as ET

from django.test import SimpleTestCase, TestCase

from planner.connections import layout as L
from planner.connections import svg
from planner.connections.graph import project_graph
from planner.models import AmpLocation, ConsoleAuxOutput
from planner.tests.connection_fixtures import ConnectionFixtures

SVG_NS = '{http://www.w3.org/2000/svg}'


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
        # The column titles say inputs / outputs; the box is the device's name.
        self.assertEqual(self.boxes[f'{box}#in'].label, 'Stage Box')
        self.assertEqual(self.boxes[f'{box}#out'].label, 'Stage Box')

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
        self.assertEqual(self.route(box, sl).label, 'Out 2')
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


class UnlinkedFeedsTests(ConnectionFixtures, TestCase):
    """Amp input text that names no single output: the "Unlinked feeds" column."""

    def draw(self):
        self.graph = project_graph(self.project)
        self.lay = L.layout(self.graph)
        self.boxes = {b.id: b for b in self.lay.boxes}
        return self.lay

    def titles(self):
        return [title for title, _, _ in self.lay.columns]

    def feeds(self):
        return sorted((b for b in self.lay.boxes if b.column == L.FEEDS), key=lambda b: b.label)

    def test_no_processor_project_has_no_processors_column_and_its_feeds_are_unlinked(self):
        amp = self.amp('SL Amp 1')
        self.amp_channel(amp, 1, avb_stream='1')
        self.amp_channel(amp, 2, aes_input='Left')
        self.amp_channel(amp, 3, analog_input='Center')
        self.draw()
        self.assertNotIn('Processors', self.titles())
        self.assertEqual(self.titles()[-3:], ['Unlinked feeds', 'Amps', 'Speakers'])
        self.assertFalse([b for b in self.lay.boxes if b.column == L.PROCESSOR])
        self.assertEqual([(b.label, b.sub, b.style) for b in self.feeds()], [
            ('AES: Left', 'not matched to an output', 'unlinked'),
            ('AVB 1', 'no processor in project', 'unlinked'),
            ('Analog: Center', 'not matched to an output', 'unlinked')])
        self.assertEqual(len(self.lay.routes), 3)
        for route in self.lay.routes:
            self.assertEqual(route.to_node, f'amp:{amp.pk}')
            self.assertTrue(route.question)
            self.assertTrue(route.label.startswith(('? AVB 1', '? AES: Left', '? Analog: Center')),
                            route.label)

    def test_the_feeds_column_sits_immediately_left_of_the_amps(self):
        self.p1('SL P1')
        amp = self.amp('SL Amp 1')
        self.amp_channel(amp, 1, avb_stream='AVB 40')
        self.draw()
        titles = self.titles()
        self.assertEqual(titles.index('Unlinked feeds') + 1, titles.index('Amps'))
        self.assertEqual(titles.index('Processors') + 1, titles.index('Unlinked feeds'))
        x = {title: x for title, x, _ in self.lay.columns}
        self.assertLess(x['Processors'], x['Unlinked feeds'])
        self.assertLess(x['Unlinked feeds'], x['Amps'])
        [feed] = self.feeds()
        self.assertEqual((feed.label, feed.sub, feed.x),
                         ('AVB 40', 'not matched to a processor output', x['Unlinked feeds']))

    def test_the_same_text_on_two_channels_is_one_node(self):
        a, b = self.amp('SL Amp 1'), self.amp('SL Amp 2')
        self.amp_channel(a, 1, aes_input='Left')
        self.amp_channel(a, 2, aes_input=' left ')         # the same text, normalised
        self.amp_channel(b, 1, aes_input='Left')
        self.amp_channel(b, 2, analog_input='Left')        # another field: its own node
        self.draw()
        self.assertEqual([f.label for f in self.feeds()], ['AES: Left', 'Analog: Left'])
        aes = next(f for f in self.feeds() if f.label == 'AES: Left')
        self.assertEqual(sorted(r.to_node for r in self.lay.routes if r.from_node == aes.node),
                         sorted([f'amp:{a.pk}', f'amp:{b.pk}']))
        feed_nodes = [n for n in self.graph['nodes'] if n.get('feed')]
        self.assertEqual(len(feed_nodes), 2)

    def test_labels_are_never_a_bare_number(self):
        amp, other = self.amp('SL Amp 1'), self.amp('SL Amp 2')
        self.amp_channel(amp, 1, avb_stream='1')
        self.amp_channel(amp, 2, avb_stream='12')
        self.amp_channel(amp, 3, aes_input='3')
        self.amp_channel(amp, 4, analog_input='4')
        self.amp_channel(other, 1, avb_stream='AVB 7')     # already says AVB: not "AVB AVB 7"
        self.draw()
        labels = sorted(f.label for f in self.feeds())
        self.assertEqual(labels, ['AES: 3', 'AVB 1', 'AVB 12', 'AVB 7', 'Analog: 4'])
        for label in labels + [r.label for r in self.lay.routes]:
            self.assertNotRegex(label.lstrip('? '), r'^\d+$')

    def test_an_ambiguous_feed_counts_its_sources_and_warns_with_them(self):
        self.p1('SL P1')
        self.p1('SR P1')
        amp = self.amp('SL Amp 1')
        self.amp_channel(amp, 1, avb_stream='1')            # AVB 1 on both, neither in use
        self.draw()
        [feed] = self.feeds()
        self.assertEqual((feed.label, feed.sub), ('AVB 1', '2 possible sources'))
        from planner.views_wiring import warnings_for
        [warning] = [w for w in warnings_for(self.graph, self.lay) if w['kind'] == 'ambiguous']
        self.assertEqual(warning['edge'], f'AVB 1 → SL Amp 1')
        self.assertEqual(sorted(warning['candidates']), ['SL P1 AVB 1', 'SR P1 AVB 1'])

    def test_with_no_unlinked_feed_the_column_is_hidden(self):
        self.p1('SL P1')
        self.amp('SL Amp 1')
        self.draw()
        self.assertNotIn('Unlinked feeds', self.titles())
        self.assertIn('Processors', self.titles())

    def test_a_line_crosses_a_hidden_column_with_no_lane_of_its_own(self):
        box = self.device('Stage Box')
        self.device_output(box, 1, 'Fill')
        amp = self.amp('FF Amp')
        self.amp_channel(amp, 1, analog_input='Fill')       # I/O output -> amp, no processor
        self.draw()
        self.assertEqual(self.titles(), ['I/O inputs', 'Console', 'I/O outputs', 'Amps', 'Speakers'])
        [route] = [r for r in self.lay.routes if r.to_node == f'amp:{amp.pk}']
        xs = [x for x, _ in route.points]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual(route.points[-1][0], self.boxes[f'amp:{amp.pk}'].x)


class NotCabledTests(WiringShow, TestCase):

    def test_arrays_with_no_cable_sit_last_under_not_cabled(self):
        pred = self.prediction(file_name='more.pdf')
        spare = self.array(pred, 'Spare Sub')
        lay = self.draw()
        speakers = sorted((b for b in lay.boxes if b.column == L.SPEAKER), key=lambda b: b.y)
        self.assertEqual(speakers[-1].node, f'speaker_array:{spare.pk}')
        self.assertEqual(speakers[-1].group, L.NOT_CABLED)
        cabled = self.boxes[f'speaker_array:{self.k2.pk}']
        self.assertIsNone(cabled.group)
        [header] = [g for g in lay.groups if g.key == L.NOT_CABLED]
        self.assertEqual((header.label, header.x), ('Not cabled', speakers[-1].x))
        self.assertLess(cabled.y, header.y)
        self.assertLessEqual(header.y + L.GROUP_HEAD, speakers[-1].y + 0.01)
        self.assertIn('>Not cabled<', svg.render(lay))

    def test_no_header_when_every_array_is_cabled(self):
        self.assertFalse([g for g in self.draw().groups if g.key == L.NOT_CABLED])


class InputSlotTests(ConnectionFixtures, TestCase):
    """PR 3.2: lines into amps and processors land on named input slots."""

    def setUp(self):
        super().setUp()
        self.box = self.device('Stage Box')
        self.sl = self.p1('SL P1')
        self.amp_ = self.amp('SL Amp')
        self.amp_id = f'amp:{self.amp_.pk}'

    def draw(self):
        self.graph = project_graph(self.project)
        self.lay = L.layout(self.graph)
        self.boxes = {b.id: b for b in self.lay.boxes}
        return self.lay

    def into(self, node_id):
        return [r for r in self.lay.routes if r.to_node == node_id]

    def assert_on_slots(self, box):
        """Every line into ``box`` ends on the slot its edge names."""
        edges = {e['id']: e for e in self.graph['edges']}
        node = next(n for n in self.graph['nodes'] if n['id'] == box.node)
        label = {s['id']: s['label'] for s in node['slots']}
        for route in self.into(box.node):
            slot = label[edges[route.id]['to_slot']]
            self.assertEqual(route.points[-1], (box.x, box.row_y(box.slots.index(slot))), slot)

    def test_amp_slots_match_the_channel_input_rows(self):
        self.device_output(self.box, 1, 'Fill')
        self.p1_out(self.sl, 'AES', 1, 'Main L')
        self.p1_out(self.sl, 'AVB', 3, 'Delay')
        self.amp_channel(self.amp_, 1, analog_input='Fill')
        self.amp_channel(self.amp_, 2, aes_input='Main L')
        self.amp_channel(self.amp_, 3, avb_stream='AVB 3 - Delay')
        self.draw()
        box = self.boxes[self.amp_id]
        # the rack view's rows: channel n's AVB stream, XLR and AES inputs
        self.assertEqual(box.slots, ['AVB 3', 'XLR 1', 'AES 2'])
        self.assertEqual(box.h, L.HEAD + 3 * L.SLOT + L.PAD)
        self.assert_on_slots(box)
        self.assertEqual(sorted(r.label for r in self.into(self.amp_id)), ['AES 1', 'AVB 3', 'Out 1'])

    def test_edge_labels_into_amps_have_no_channel(self):
        self.device_output(self.box, 1, 'Fill')
        self.p1_out(self.sl, 'AES', 1, 'Main L')
        self.amp_channel(self.amp_, 1, analog_input='Fill', avb_stream='Nope')
        self.amp_channel(self.amp_, 2, aes_input='Main L', avb_stream='Nope')
        self.amp_channel(self.amp_, 3, aes_input='Main L')
        self.draw()
        labels = [r.label for r in self.into(self.amp_id)]
        self.assertEqual(len(labels), 3)
        for label in labels:
            self.assertNotIn('→ Ch', label)
            self.assertNotIn('Ch ', label)
        self.assertIn('? AVB Nope', labels)
        for edge in self.graph['edges']:
            if edge['to'] == self.amp_id:
                self.assertNotIn('→', edge['label'])

    def test_one_source_into_several_channels_is_one_slot(self):
        self.device_output(self.box, 1, 'Fill')
        self.amp_channel(self.amp_, 1, analog_input='Fill', avb_stream='Nope')
        self.amp_channel(self.amp_, 2, analog_input='Fill', avb_stream='Nope')
        self.amp_channel(self.amp_, 4, analog_input='Fill')
        self.draw()
        box = self.boxes[self.amp_id]
        self.assertEqual(box.slots, ['AVB 1 → Ch 1–2', 'XLR 1 → Ch 1–2, 4'])
        self.assertEqual(len(self.into(self.amp_id)), 2)
        self.assert_on_slots(box)

    def test_two_sources_get_their_own_slots(self):
        self.device_output(self.box, 1, 'Left')
        self.device_output(self.box, 2, 'Right')
        self.amp_channel(self.amp_, 1, analog_input='Left')
        self.amp_channel(self.amp_, 2, analog_input='Right')
        self.amp_channel(self.amp_, 3, analog_input='Left')
        self.draw()
        box = self.boxes[self.amp_id]
        self.assertEqual(box.slots, ['XLR 1 → Ch 1, 3', 'XLR 2'])
        self.assertEqual(sorted(r.label for r in self.into(self.amp_id)), ['Out 1', 'Out 2'])
        self.assert_on_slots(box)

    def test_processor_inputs_are_named_slots(self):
        self.p1_in(self.sl, 'AES', 1, 'Main L')
        self.p1_in(self.sl, 'ANALOG', 2, 'Fill')
        self.device_output(self.box, 1, 'Main L')
        self.device_output(self.box, 2, 'Fill')
        self.draw()
        box = self.boxes[f'processor:{self.sl.pk}']
        self.assertEqual(box.slots, ['AES 1', 'Analog 2'])
        self.assertEqual(sorted(r.label for r in self.into(box.node)), ['Out 1', 'Out 2'])
        self.assert_on_slots(box)

    def test_the_svg_draws_each_slot_label(self):
        self.device_output(self.box, 1, 'Fill')
        self.p1_in(self.sl, 'AES', 1, 'Fill')
        self.amp_channel(self.amp_, 1, analog_input='Fill')
        self.amp_channel(self.amp_, 2, analog_input='Fill')
        root = ET.fromstring(svg.render(self.draw()))
        slots = {t.get('data-slot'): t.text for t in root.iter(f'{SVG_NS}text')
                 if t.get('class') == 'p'}
        self.assertEqual(slots, {'XLR 1 → Ch 1–2': 'XLR 1 → Ch 1–2', 'AES 1': 'AES 1'})

    def test_boxes_with_no_inputs_have_no_slots(self):
        self.amp_channel(self.amp_, 1)
        self.draw()
        self.assertEqual(self.boxes[self.amp_id].slots, [])
        self.assertEqual(self.boxes[f'device:{self.box.pk}#in'].slots, [])


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

    def test_a_slot_label_is_escaped(self):
        hostile = '"><img src=x onerror=1>'     # short enough not to be clipped
        graph = {'nodes': [{'id': 'device:1', 'kind': 'device', 'label': 'Box',
                            'ports': {'inputs': 0, 'outputs': 1}},
                           {'id': 'amp:1', 'kind': 'amp', 'label': 'Amp',
                            'slots': [{'id': 'analog:1', 'label': hostile}]}],
                 'edges': [{'id': 'e1', 'from': 'device:1', 'to': 'amp:1', 'label': 'Out 1',
                            'links': [{'from_ref': 'deviceoutput:1'}], 'status': 'inferred',
                            'to_slot': 'analog:1'}],
                 'warnings': []}
        out = svg.render(L.layout(graph))
        self.assertNotIn('<img', out)
        root = ET.fromstring(out)
        self.assertEqual([e for e in root.iter() if e.tag.endswith('img')], [])
        [text] = [t for t in root.iter(f'{SVG_NS}text') if t.get('class') == 'p']
        self.assertEqual((text.text, text.get('data-slot')), (hostile, hostile))
