"""Wiring Diagram PR 3.3: the "Show network feeds" toggle, and nothing cut
short (wrapped labels, keys and the Connections table). Amp input slots
stay numbered ("XLR n", "AES n"): L-Acoustics panels are numbered. Since the
wiring PDF PR they also name their source; an AVB slot names its stream.

Run with::

    python manage.py test planner.tests.test_wiring_network_and_wrapping \\
        --settings=audiopatch.test_settings
"""
import re
import xml.etree.ElementTree as ET

from django.test import TestCase
from django.urls import reverse

from planner.connections import layout as L
from planner.connections import svg
from planner.connections import tabs as T
from planner.connections.graph import project_graph
from planner.models import Amp, AmpModel, ConsoleAuxOutput, ConsoleMatrixOutput
from planner.tests.connection_fixtures import ConnectionFixtures
from planner.tests.test_wiring_view import svg_of
from planner.views_wiring import connection_rows

SVG_NS = '{http://www.w3.org/2000/svg}'


def texts(svg):
    root = ET.fromstring(svg)
    return [''.join(t.itertext()) for t in root.iter(f'{SVG_NS}text')]


def vertical_runs(route):
    return [(x0, min(y0, y1), max(y0, y1)) for (x0, y0), (x1, y1) in zip(route.points, route.points[1:])
            if abs(x0 - x1) < 0.01 and abs(y0 - y1) > 0.01]


def horizontal_runs(route):
    return [(min(x0, x1), max(x0, x1), y0) for (x0, y0), (x1, y1) in zip(route.points, route.points[1:])
            if abs(y0 - y1) < 0.01]


class LAmpSlotsStayNumberedTests(ConnectionFixtures, TestCase):
    def test_an_la12x_has_numbered_slots(self):
        model, _ = AmpModel.objects.get_or_create(
            manufacturer='L-Acoustics', model_name='LA12X', defaults={'channel_count': 4})
        amp = self.amp('SL Amp')
        Amp.objects.filter(pk=amp.pk).update(amp_model=model)
        box, sl = self.device('Stage Box'), self.p1('SL P1')
        self.device_output(box, 1, 'Fill')
        self.p1_out(sl, 'AES', 1, 'Main L')
        self.p1_out(sl, 'AVB', 3, 'Delay')
        self.amp_channel(amp, 1, analog_input='Fill')
        self.amp_channel(amp, 2, aes_input='Main L')
        self.amp_channel(amp, 3, avb_stream='AVB 3 - Delay')
        self.amp_channel(amp, 4, analog_input='Fill')
        graph = project_graph(self.project)
        node = next(n for n in graph['nodes'] if n['id'] == f'amp:{amp.pk}')
        self.assertEqual([s['label'] for s in node['slots']],
                         ['AVB ← SL P1 stream 3 (Delay) · Ch 3',
                          'XLR 1 ← Stage Box Analog Out 1 (Fill) · Ch 1, 4',
                          'AES 2 ← SL P1 AES Out 1 (Main L)'])
        drawn = next(b for b in L.layout(graph).boxes if b.node == node['id'])
        self.assertEqual(drawn.slots, [s['label'] for s in node['slots']])
        self.assertNotIn('IN ', ' '.join(texts(svg.render(L.layout(graph)))))


class NetworkShow(ConnectionFixtures):
    """A processor feeding an amp on AVB and on AES, and a Dante box."""

    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        self.sl = self.p1('SL P1')
        self.p1_out(self.sl, 'AES', 1, 'Main L')
        self.p1_out(self.sl, 'AVB', 2, 'Delay')
        self.amp_ = self.amp('SL Amp')
        self.amp_channel(self.amp_, 1, aes_input='Main L', avb_stream='AVB 2 - Delay')
        self.desk = self.console('FOH Desk')
        self.dante = self.device('Dante Box')
        self.dante.console_connection = 'dante'
        self.dante.save()
        self.device_input(self.dante, 1, self.channel(self.desk, 1, 'Kick'))

    def page(self, **params):
        return self.client.get(reverse('planner:wiring_diagram'), params)


class NetworkToggleTests(NetworkShow, TestCase):
    def test_on_by_default(self):
        response = self.page()
        self.assertContains(response, 'role="switch" aria-checked="true"')
        self.assertContains(response, 'href="?view=overview&amp;network=0"')
        svg = svg_of(response)
        self.assertIn('class="wd-edge confirmed network"', svg)       # Dante Box -> desk
        self.assertIn('class="wd-edge inferred network"', svg)        # the AVB feed

    def test_off_hides_every_network_line_and_keeps_its_slot_named(self):
        response = self.page(view='overview', network='0')
        self.assertContains(response, 'aria-checked="false"')
        self.assertContains(response, 'Show network feeds (2 hidden)')
        svg = svg_of(response)
        self.assertNotIn(' network"', svg)
        self.assertNotIn('Dante Box', ''.join(re.findall(r'<g class="wd-link".*?</g>', svg)))
        slots = [t for t in texts(svg) if t.startswith(('AVB', 'AES'))]
        # channel 1's AVB row still names its stream, once
        self.assertTrue(any(t.startswith('AVB ← SL P1 stream 2') for t in slots), slots)
        self.assertNotIn('Stream 2', ' '.join(slots))
        self.assertIn('AES 1 ← SL P1 AES Out 1 (Main L)', slots)

    def test_the_layout_is_recomputed(self):
        graph = project_graph(self.project)
        on, off = L.layout(graph), L.layout(T.without_network(graph))
        self.assertEqual(len(on.routes) - len(off.routes), 2)
        amp = next(b for b in off.boxes if b.node == f'amp:{self.amp_.pk}')
        # the hidden AVB feed keeps its slot, so the box stays two slots tall
        self.assertEqual(len(amp.slots), 2)
        self.assertEqual([r.to_node for r in off.routes if r.to_node == amp.node], [amp.node])

    def test_only_on_the_overview(self):
        for tab in ('dante', 'analog', 'speakers'):
            response = self.page(view=tab, network='0')
            self.assertNotContains(response, 'role="switch"')
        self.assertIn('wd-edge confirmed network', svg_of(self.page(view='dante', network='0')))

    def test_the_tab_is_called_analogue_aes(self):
        response = self.page()
        self.assertContains(response, '>Analogue/AES</a>')
        self.assertNotContains(response, 'Analog signal flow')


class LongShow(ConnectionFixtures):
    """Long names everywhere: a console sending Aux and Matrix buses to one
    box, one bus group too long for a line, a long PA run, long titles."""

    LONG_NAME = 'Upstage Left Wireless Receiver Rack Number Two Spare'
    BOX = 'Stage Box With A Rather Long Descriptive Name'

    def setUp(self):
        super().setUp()
        self.desk = self.console(self.LONG_NAME)
        self.box = self.device(self.BOX)
        for n in (1, 2):
            bus = ConsoleAuxOutput.objects.create(console=self.desk, aux_number=str(n), name=f'Wedge {n}')
            self.device_output(self.box, n, f'Wedge {n}', bus=bus)
        mtx = ConsoleMatrixOutput.objects.create(console=self.desk, matrix_number=1, name='Fill')
        self.device_output(self.box, 3, 'Fill', bus=mtx)
        # every other bus to every other output: one group far too wide for a line
        self.far = self.device('Far Box')
        self.far_2 = self.device('Far Box 2')
        for far, base in ((self.far, 10), (self.far_2, 100)):
            for n in range(1, 50, 2):
                bus = ConsoleAuxOutput.objects.create(console=self.desk, aux_number=str(n + base),
                                                      name=f'Mix {n}')
                self.device_output(far, n, f'Mix {n}', bus=bus)
        self.amp_ = self.amp('SL Amp', rack='Stage Left Amplifier Rack Behind The Scrim Wall')
        self.k2 = self.array(self.prediction(), 'K2 Left Main Hang Downstage')
        self.linked_cable(self.amp_, self.k2, label=self.zone('HL'), count=2, length=100)

    def draw(self, tab=T.OVERVIEW):
        graph = T.graph_view(project_graph(self.project), tab)
        return graph, L.layout(graph, **T.layout_options(tab))

    def wide(self):
        """The Overview with room for the long box name on one label line."""
        return L.layout(project_graph(self.project), label_max=560)


class NothingCutShortTests(LongShow, TestCase):
    def test_no_ellipsis_in_any_svg_text_on_any_tab(self):
        for tab in T.TAB_KEYS:
            _, lay = self.draw(tab)
            for text in texts(svg.render(lay)):
                self.assertNotIn('…', text, tab)

    def test_bus_groups_are_one_line_each(self):
        lay = self.wide()
        route = next(r for r in lay.routes if r.to_node == f'device:{self.box.pk}')
        self.assertEqual(route.lines, [f'{self.BOX} Out 1–2', f'{self.BOX} Out 3'])
        self.assertIsNone(route.key)
        self.assertEqual(route.label_full, f'{self.BOX} Out 1–2 · {self.BOX} Out 3')
        # ... and the buses are named in the console box, where the line leaves
        desk = next(b for b in lay.boxes if b.node == f'console:{self.desk.pk}')
        self.assertIn(['Aux 1–2', 'Mtx 1'], desk.out_text)

    def test_a_label_too_wide_for_a_line_becomes_a_key(self):
        _, lay = self.draw()
        route = next(r for r in lay.routes if r.to_node == f'device:{self.box.pk}')
        self.assertEqual(route.lines, [f'[{route.key}]'])
        self.assertEqual(lay.keys, [(route.key, route.id)])
        self.assertIn(f'{self.BOX} Out 3', route.label_full)      # the tooltip keeps it all

    def test_a_long_run_of_ports_wraps_inside_its_box(self):
        _, lay = self.draw()
        desk = next(b for b in lay.boxes if b.node == f'console:{self.desk.pk}')
        for far in (self.far, self.far_2):
            route = next(r for r in lay.routes if r.to_node == f'device:{far.pk}')
            self.assertEqual(route.lines, [f'{far.name} Out 1–25'])    # the far end is short
        ports = [' '.join(lines) for lines in desk.out_text if len(lines) > 2]
        self.assertEqual(len(ports), 2)
        self.assertTrue(ports[0].startswith('Aux 11, 13, 15') and ports[0].endswith('57, 59'), ports)
        self.assertTrue(ports[1].startswith('Aux 101, 103') and ports[1].endswith('147, 149'), ports)
        for lines in desk.out_text:
            for line in lines:
                self.assertLessEqual(L.text_width(line, L.SLOT_CHAR_W), L.TEXT_W)

    def test_port_names_stay_inside_their_box_and_clear_of_each_other(self):
        for tab in T.TAB_KEYS:
            _, lay = self.draw(tab)
            for box in lay.boxes:
                drawn = []
                for anchor, x, y, lines, name in box.port_texts():
                    for i, line in enumerate(lines):
                        w = L.text_width(line, L.SLOT_CHAR_W)
                        x0 = x - w if anchor == 'end' else x
                        base = y + i * L.SLOT_LH
                        drawn.append((x0, base - 8, x0 + w, base + 2, name))
                for x0, y0, x1, y1, name in drawn:
                    self.assertGreaterEqual(x0, box.x, f'{tab}: {name}')
                    self.assertLessEqual(x1, box.x + box.w, f'{tab}: {name}')
                    self.assertGreaterEqual(y0, box.y + box.head - L.SLOT, f'{tab}: {name}')
                    self.assertLessEqual(y1, box.y + box.h, f'{tab}: {name}')
                for i, a in enumerate(drawn):
                    for b in drawn[i + 1:]:
                        self.assertFalse(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3],
                                         f'{tab}: {a[4]} / {b[4]}')

    def test_a_key_is_a_badge_on_the_line_next_to_its_source_box(self):
        _, lay = self.draw()
        desk = next(b for b in lay.boxes if b.node == f'console:{self.desk.pk}')
        keyed = [r for r in lay.routes if r.key]
        self.assertEqual(len(keyed), 1)
        for route in keyed:
            x0, y0, x1, y1 = route.badge
            line_y = route.points[0][1]
            self.assertEqual(x0, desk.x + desk.w + L.LABEL_PAD)            # next to the box
            self.assertAlmostEqual((y0 + y1) / 2, line_y)                   # centred on the line
            self.assertAlmostEqual(x1 - x0, L.key_width(route.key))
            self.assertLess(x1, route.points[1][0])         # before its first bend or its target
        drawn = svg.render(lay)
        for route in keyed:
            self.assertRegex(drawn, rf'<g class="wd-key"><rect [^>]*rx="3"/>'
                                    rf'<text data-key="{route.key}" [^>]*>\[{route.key}\]</text></g>')
        self.assertIn('.wd-key text { font: 700 11px', drawn)               # bold
        # Drawn after the line, so the badge's white fill sits over it.
        link = re.search(rf'<g class="wd-link" data-edge="{keyed[0].id}">.*?</g></g>', drawn).group()
        self.assertLess(link.index('class="wd-edge'), link.index('class="wd-key"'))

    def test_a_badge_clears_the_labels_beside_it(self):
        # [1] and two one-line labels leave one box one under another.
        _, lay = self.draw()
        from_desk = [r for r in lay.routes if r.from_node == f'console:{self.desk.pk}']
        self.assertEqual(sorted(bool(r.key) for r in from_desk), [False, False, True])
        for route in (r for r in from_desk if r.key):
            _, top, _, bottom = route.badge
            for other in from_desk:
                if other is route:
                    continue
                for _, y0, _, y1 in other.line_boxes():
                    gap = max(y0 - bottom, top - y1)
                    self.assertGreaterEqual(gap, 3, f'[{route.key}] / {other.lines}')

    def test_long_titles_wrap(self):
        _, lay = self.draw()
        desk = next(b for b in lay.boxes if b.node == f'console:{self.desk.pk}')
        titles = [text for cls, text, _ in desk.text_rows if cls == 't']
        self.assertGreater(len(titles), 1)
        self.assertEqual(' '.join(titles), self.LONG_NAME)
        self.assertEqual(desk.head, L.HEAD + L.TITLE_LH * (len(titles) - 1))
        group = next(g for g in lay.groups if g.label.startswith('Stage Left'))
        self.assertEqual(' '.join(group.lines), group.label)
        self.assertGreater(len(group.lines), 1)

    def test_labels_overlap_no_track_and_no_other_label(self):
        for tab in T.TAB_KEYS:
            _, lay = self.draw(tab)
            labels = [(r, b) for r in lay.routes for b in r.line_boxes()]
            for route, (x0, y0, x1, y1) in labels:
                for other in lay.routes:
                    for x, top, bottom in vertical_runs(other):
                        self.assertFalse(x0 <= x <= x1 and top < y1 and bottom > y0,
                                         f'{tab}: {route.lines} over a track of {other.id}')
                    if other is route:
                        continue
                    for left, right, y in horizontal_runs(other):
                        self.assertFalse(left < x1 and right > x0 and y0 < y < y1,
                                         f'{tab}: {route.lines} over the line of {other.id}')
            for i, (a, (ax0, ay0, ax1, ay1)) in enumerate(labels):
                for b, (bx0, by0, bx1, by1) in labels[i + 1:]:
                    if a is b:
                        continue
                    self.assertFalse(ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1,
                                     f'{tab}: {a.lines} / {b.lines}')

    def test_a_stacked_label_stays_above_its_line_and_inside_its_row(self):
        lay = self.wide()
        route = next(r for r in lay.routes if r.to_node == f'device:{self.box.pk}')
        desk = next(b for b in lay.boxes if b.node == route.from_node)
        boxes = route.line_boxes()
        self.assertEqual(len(boxes), 2)
        self.assertLess(boxes[-1][3], route.points[0][1] + 0.01)
        self.assertGreaterEqual(boxes[0][1], desk.y + desk.head - L.SLOT / 2)
        self.assertLessEqual(route.points[0][1], desk.y + desk.h)


class ConnectionsTableTests(LongShow, TestCase):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def test_keys_in_the_svg_match_the_table_rows(self):
        response = self.client.get(reverse('planner:wiring_diagram'))
        svg = svg_of(response)
        drawn = re.findall(r'data-key="(\d+)"', svg)
        html = response.content.decode()
        rows = re.findall(r'<tr data-key="(\d+)">', html)
        self.assertTrue(drawn)
        self.assertEqual(drawn, rows)
        for key in drawn:
            self.assertIn(f'>[{key}]</text>', svg)
            self.assertIn(f'<td class="k"><span class="wd-keybadge">[{key}]</span></td>', html)
        [row] = response.context['connections']
        self.assertEqual(row['from'], f'{self.LONG_NAME} · Aux 1–2, Mtx 1')
        self.assertEqual(row['to'], f'{self.BOX} · Out 1–3')
        self.assertEqual(row['cable'], 'Not known')

    def test_the_page_prints_the_diagram_whole_with_the_keys_boxed(self):
        response = self.client.get(reverse('planner:wiring_diagram'))
        html = response.content.decode()
        css = html[html.index('@media print'):]
        css = css[:css.index('</style>')]
        for rule in ('.wd-scroll { overflow: visible; max-height: none;',
                     '.wd-scroll svg { width: 100%; height: auto; }',
                     '.wd-keybadge { color: #000; border-color: #000; }',
                     '.wd-tabs, .wd-bar { display: none !important; }'):
            self.assertIn(rule, css)
        self.assertContains(response, '<p class="wd-print-tab">Overview</p>')

    def test_each_tab_has_its_own_table(self):
        response = self.client.get(reverse('planner:wiring_diagram'), {'view': 'speakers'})
        self.assertEqual(response.context['connections'], [])
        self.assertNotContains(response, 'id="wd-connections"')

    def test_a_speaker_run_lists_its_cable(self):
        graph = T.graph_view(project_graph(self.project), T.SPEAKERS)
        lay = L.layout(graph, label_max=50)      # narrow enough to key the run
        rows = connection_rows(graph, lay)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['cable'], "HL · 2× NL 4 100'")
        self.assertEqual(rows[0]['to'], 'K2 Left Main Hang Downstage')

    def test_table_cells_are_escaped(self):
        self.desk.name = '<img src=x onerror=alert(1)>'
        self.desk.save()
        response = self.client.get(reverse('planner:wiring_diagram'))
        html = response.content.decode()
        table = html[html.index('id="wd-connections"'):html.index('class="wd-warnings"')]
        self.assertNotIn('<img', table)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', table)
