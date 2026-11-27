"""Wiring diagram trunks: the Dante and AVB tabs draw one line per source
port, branching to its receivers, in a colour and with a name of its own.

Run with::

    python manage.py test planner.tests.test_wiring_trunks \\
        --settings=audiopatch.test_settings
"""
import io
import itertools
import math
import xml.etree.ElementTree as ET

import ezdxf
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from planner import views_wiring as V
from planner.connections import dxf, svg, tiling
from planner.connections import layout as L
from planner.connections import tabs as T
from planner.connections.graph import digest, project_graph
from planner.tests.test_wiring_pdf import read as read_pdf
from planner.tests.test_wiring_tabs import TabShow
from planner.utils.pdf_exports.wiring_pdf import build_wiring_pdf

SVG_NS = '{http://www.w3.org/2000/svg}'
BOX_FILL = '#f4f7fb'
DIAGRAM_INK = ('#111111', '#2b4c7e', '#4a6f9a', '#555555')    # title, slot text, border, subtitle


# -- colour arithmetic, for the palette -------------------------------------------

def _linear(hex_colour):
    out = []
    for i in (1, 3, 5):
        c = int(hex_colour[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def contrast(a, b):
    lum = sorted((0.2126 * r + 0.7152 * g + 0.0722 * bl for r, g, bl in (_linear(a), _linear(b))),
                 reverse=True)
    return (lum[0] + 0.05) / (lum[1] + 0.05)


# Linear-RGB simulations of the three colour-vision deficiencies (Viénot et
# al. 1999 for protan and deutan; the usual tritan approximation).
VISION = {
    'normal': ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    'protan': ((0.11238, 0.88762, 0), (0.11238, 0.88762, 0), (0.00401, -0.00401, 1)),
    'deutan': ((0.29275, 0.70725, 0), (0.29275, 0.70725, 0), (-0.02234, 0.02234, 1)),
    'tritan': ((1, 0.1273989, -0.1273989), (0, 0.8739093, 0.1260907), (0, 0.8739093, 0.1260907)),
}


def seen(hex_colour, vision):
    """CIE L*a*b* of a colour as ``vision`` sees it."""
    rgb = _linear(hex_colour)
    r, g, b = (min(max(sum(m * c for m, c in zip(row, rgb)), 0), 1) for row in VISION[vision])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116   # noqa: E731
    return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))


def apart(a, b, vision):
    return math.dist(seen(a, vision), seen(b, vision))


class PaletteTests(SimpleTestCase):
    def test_six_colours(self):
        self.assertEqual(len(L.STREAM_COLOURS), 6)
        self.assertEqual(len(set(L.STREAM_COLOURS)), 6)

    def test_each_reads_as_small_text_on_a_box_and_on_paper(self):
        for colour in L.STREAM_COLOURS:
            self.assertGreaterEqual(contrast(colour, BOX_FILL), 4.5, colour)
            self.assertGreaterEqual(contrast(colour, '#ffffff'), 4.5, colour)

    def test_they_stay_apart_for_every_kind_of_colour_vision(self):
        for vision in VISION:
            for a, b in itertools.combinations(L.STREAM_COLOURS, 2):
                self.assertGreaterEqual(apart(a, b, vision), 17, (vision, a, b))

    def test_none_reads_as_the_diagrams_own_text_or_borders(self):
        for colour in L.STREAM_COLOURS:
            for ink in DIAGRAM_INK:
                self.assertGreaterEqual(apart(colour, ink, 'normal'), 20, (colour, ink))


class PiecesTests(SimpleTestCase):
    def test_a_shared_stretch_is_one_piece(self):
        stem = [(0, 10), (50, 10), (50, 40), (90, 40)]
        other = [(0, 10), (50, 10), (50, 80), (90, 80)]
        pieces = L._pieces([(stem, False), (other, False)])
        self.assertEqual(sorted(pieces), sorted([
            (0, 10, 50, 10, False), (50, 10, 50, 80, False),
            (50, 40, 90, 40, False), (50, 80, 90, 80, False)]))

    def test_only_what_a_faded_path_runs_alone_is_faded(self):
        a = [(0, 10), (50, 10), (50, 40), (90, 40)]
        b = [(0, 10), (50, 10), (50, 80), (90, 80)]
        pieces = L._pieces([(a, False), (b, True)])
        self.assertIn((50, 40, 50, 80, True), pieces)
        self.assertIn((50, 80, 90, 80, True), pieces)
        self.assertIn((50, 10, 50, 40, False), pieces)
        self.assertEqual(sum(p[4] for p in pieces), 2)


# -- a show with two AVB streams and a Dante box ----------------------------------

class TrunkShow(TabShow):
    """TabShow's AVB stream 1 feeds two amps; stream 2 feeds a third; a
    fourth amp's AVB text names no output."""

    def setUp(self):
        super().setUp()
        self.id = self.ids()
        self.amp2 = self.amp('SL Amp 2')
        self.amp_channel(self.amp2, 1, avb_stream='AVB 1 - Main L')
        self.p1_out(self.sl, 'AVB', 2, 'Sub')
        self.amp3 = self.amp('SL Amp 3')
        self.amp_channel(self.amp3, 1, avb_stream='AVB 2 - Sub')
        self.lost = self.amp('Lost Amp')
        self.amp_channel(self.lost, 1, avb_stream='Nowhere')

    def view(self, tab):
        self.full = project_graph(self.project)
        self.v = V.tab_view(self.project, self.full, tab)
        self.lay = self.v['layout']
        self.boxes = {b.id: b for b in self.lay.boxes}
        self.routes = {r.id: r for r in self.lay.routes}
        return self.lay


class AvbTrunkTests(TrunkShow, TestCase):
    def setUp(self):
        super().setUp()
        self.view(T.AVB)
        self.one, self.two = self.lay.trunks

    def test_one_trunk_per_output_named_with_its_real_number(self):
        self.assertEqual([(t.n, t.label, len(t.edges)) for t in self.lay.trunks],
                         [(1, '1', 2), (2, '2', 1)])
        self.assertEqual([t.colour for t in self.lay.trunks], [0, 1])
        self.assertEqual([t.port for t in self.lay.trunks], ['AVB Out 1', 'AVB Out 2'])

    def test_a_trunk_is_one_row_in_the_source_box(self):
        box = self.boxes[self.id['sl']]
        self.assertEqual(box.out_text, [['AVB Out 1'], ['AVB Out 2']])
        self.assertEqual(len(box.out_h), 2)
        self.assertEqual(box.port_streams(), [1, 2])

    def test_branches_share_one_track_and_every_piece_is_drawn_once(self):
        a, b = (self.routes[e] for e in self.one.edges)
        self.assertEqual((a.trunk, b.trunk), (1, 1))
        self.assertEqual(a.points[0], b.points[0])              # out of the same port
        self.assertEqual(a.points[-2][0], b.points[-2][0])      # the same track into the amps
        # one lane through the Unlinked feeds column, not one each
        self.assertEqual(a.points[:3], b.points[:3])
        self.assertLess(len(self.one.lines), len(a.points) + len(b.points) - 2)
        self.assertEqual(len(set(self.one.lines)), len(self.one.lines))
        for x0, y0, x1, y1, _ in self.one.lines:
            self.assertTrue(x0 == x1 or y0 == y1)

    def test_a_badge_on_every_tap_and_at_the_top(self):
        taps = [b for b in self.one.badges if b.edge]
        self.assertEqual(sorted(b.edge for b in taps), sorted(self.one.edges))
        self.assertEqual({b.text for b in self.one.badges}, {'1'})
        for badge in taps:
            route = self.routes[badge.edge]
            self.assertEqual(badge.y, route.points[-1][1])      # level with its receiver's slot
            self.assertLess(badge.box[2], route.points[-1][0] - 6)   # clear of the arrowhead
        top = min(p[1] for p in self.one.lines)
        self.assertTrue(any(abs(b.y - top) < 0.01 for b in self.one.badges))

    def test_an_inferred_tap_is_hollow_and_a_confirmed_one_filled(self):
        for trunk in self.lay.trunks:
            for badge in trunk.badges:
                if badge.edge:
                    self.assertEqual(badge.filled, 'inferred' not in self.routes[badge.edge].classes)
        # the same graph with the first link confirmed
        graph = dict(self.v['graph'])
        first = self.one.edges[0]
        graph['edges'] = [{**e, 'status': 'confirmed'} if e['id'] == first else e
                          for e in graph['edges']]
        lay = L.layout(graph, **T.layout_options(T.AVB))
        filled = {b.edge: b.filled for b in lay.trunks[0].badges if b.edge}
        self.assertTrue(filled[first])

    def test_labels_stack_on_the_trunk_and_nothing_overlaps(self):
        a, b = (self.routes[e] for e in self.one.edges)
        self.assertEqual(b.label_y - a.label_y, L.LABEL_LH)
        self.assertEqual(a.label_x, b.label_x)
        boxes = [box for r in self.lay.routes for box in r.line_boxes()]
        boxes += [b.box for t in self.lay.trunks for b in t.badges]
        for (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) in itertools.combinations(boxes, 2):
            self.assertFalse(ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1)

    def test_no_line_runs_through_another_trunks_badge(self):
        for trunk in self.lay.trunks:
            for other in self.lay.trunks:
                if other is trunk:
                    continue
                for badge in other.badges:
                    x0, y0, x1, y1 = badge.box
                    for px0, py0, px1, py1, _ in trunk.lines:
                        level = py0 == py1 and y0 <= py0 <= y1      # a run or a branch
                        self.assertFalse(level and px0 < x1 and x0 < px1, (trunk.n, other.n))

    def test_both_ends_carry_the_trunks_number(self):
        for trunk in self.lay.trunks:
            for edge in trunk.edges:
                box = self.boxes[self.routes[edge].to_node]
                self.assertIn(trunk.n, box.port_streams())

    def test_a_question_mark_feed_is_not_a_trunk(self):
        [lost] = [r for r in self.lay.routes if r.to_node == f'amp:{self.lost.pk}']
        self.assertIsNone(lost.trunk)
        self.assertIn('unlinked', lost.classes)
        self.assertNotIn('network', lost.classes)       # dashed, as the legend says
        self.assertEqual(self.boxes[f'amp:{self.lost.pk}'].port_streams(), [None])

    def test_the_project_graph_is_untouched(self):
        self.assertFalse(any('stream' in e for e in self.full['edges']))
        self.assertEqual(digest(self.full), digest(project_graph(self.project)))

    def test_svg(self):
        text = svg.render(self.lay)
        root = ET.fromstring(text)
        trunks = root.findall(f".//{SVG_NS}g[@class='wd-trunk wd-s1']")
        self.assertEqual(len(trunks), 1)
        self.assertEqual(len(trunks[0].findall(f'{SVG_NS}line')), len(self.one.lines))
        badges = root.findall(f".//{SVG_NS}g[@data-tap]")
        self.assertEqual(len(badges), sum(len(t.badges) for t in self.lay.trunks))
        # a branch draws no line of its own; nothing is dotted but the "?" feed
        for link in root.findall(f".//{SVG_NS}g[@data-edge]"):
            paths = [p for p in link.findall(f'{SVG_NS}path') if 'wd-edge' in p.get('class')]
            self.assertEqual(len(paths), 0 if link.get('data-stream') else 1)
        streams = {e.get('data-stream') for e in root.iter() if e.get('data-stream')}
        self.assertEqual(streams, {'1', '2'})
        ports = [e for e in root.iter(f'{SVG_NS}text') if e.get('data-slot') and e.get('data-stream')]
        self.assertEqual(len(ports), 2 + 3)     # two outputs, three receiving slots

    def test_page_cut_markers_are_not_repeated(self):
        plan = tiling.plan(self.lay, 260, 150)
        marks = [(round(c.x, 2), round(c.y, 2), c.leaves, c.enters)
                 for c in tiling.crossings(plan, self.lay.routes)]
        self.assertEqual(len(marks), len(set(marks)))

    def test_pdf(self):
        pdf = build_wiring_pdf(project=self.project, views=[self.v], digest=digest(self.full),
                               paper='11x17', printed=timezone.now(), empty=False)
        _, pages = read_pdf(pdf)
        text = ' '.join(pages[0].split())
        self.assertIn('One colour and name per stream', text)
        self.assertIn('Confirmed', text)
        self.assertIn('Inferred from labels', text)
        self.assertNotIn('AVB / Dante network (no cable)', text)
        self.assertIn('SL Amp 2 AVB Ch 1', text)

    def test_dxf(self):
        data = dxf.build_tab_dxf(project_name=self.project.name, view=self.v,
                                 digest=digest(self.full), printed='now')
        doc = ezdxf.read(io.StringIO(data.decode('utf-8')))
        auditor = doc.audit()
        self.assertFalse(auditor.errors or auditor.fixes)
        msp = doc.modelspace()
        colours = [int(c[1:], 16) for c in L.STREAM_COLOURS]
        lines = [e for e in msp.query('LINE') if e.dxf.get('true_color') == colours[0]
                 and e.dxf.layer.endswith('-Network')]
        self.assertEqual(len(lines), len(self.one.lines))
        self.assertTrue(all(e.dxf.linetype == dxf.CONTINUOUS for e in lines))
        filled = sum(b.filled for t in self.lay.trunks for b in t.badges)
        self.assertEqual(len(msp.query('HATCH')), filled + 1)       # and the legend's
        words = [e.plain_text() for e in msp.query('TEXT')]
        self.assertIn('One colour and name per stream', words)
        self.assertNotIn('AVB / Dante network (no cable)', words)
        # nothing is dotted: the "?" feed is dashed, on the Unlinked layer
        self.assertFalse([e for e in msp if e.dxf.get('linetype') == dxf.DOT])
        [lost] = [e for e in msp.query('LWPOLYLINE') if e.dxf.linetype == dxf.DASHED and not e.closed]
        self.assertTrue(lost.dxf.layer.endswith('-Unlinked'))


class DanteTrunkTests(TrunkShow, TestCase):
    def test_trunks_are_named_t1_down_the_tab_and_confirmed_taps_are_filled(self):
        lay = self.view(T.DANTE)
        self.assertEqual([t.label for t in lay.trunks], ['T1', 'T2'])
        self.assertEqual([t.box for t in lay.trunks],
                         [f"{self.id['dante']}#in", self.id['desk']])
        self.assertTrue(all(b.filled for t in lay.trunks for b in t.badges))
        self.assertTrue(all(r.trunk for r in lay.routes))

    def test_the_other_tabs_are_drawn_as_before(self):
        full = project_graph(self.project)
        for tab in (T.OVERVIEW, T.ANALOG, T.SPEAKERS, T.COMMS):
            lay = V.tab_layout(full, tab)[1]
            self.assertEqual(lay.trunks, [], tab)
            self.assertTrue(all(r.trunk is None for r in lay.routes), tab)
            self.assertNotIn('data-stream="', svg.render(lay), tab)
            self.assertEqual({n for b in lay.boxes for n in b.port_streams()} - {None}, set(), tab)

    def test_the_overview_is_laid_out_exactly_as_without_the_option(self):
        graph = project_graph(self.project)
        self.assertEqual(svg.render(L.layout(graph)), svg.render(L.layout(graph, trunks=None)))
        self.assertIn('wd-edge inferred network', svg.render(L.layout(graph)))


class TrunkPageTests(TrunkShow, TestCase):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def page(self, view):
        return self.client.get(reverse('planner:wiring_diagram'), {'view': view})

    def test_the_legend_explains_streams_and_both_badges(self):
        for view in ('avb', 'dante'):
            response = self.page(view)
            self.assertContains(response, 'One colour and name per stream')
            self.assertContains(response, 'class="wd-tap"')
            self.assertContains(response, 'class="wd-tap hollow"')
            self.assertContains(response, 'Hover or tap a stream to highlight it')
            self.assertNotContains(response, 'AVB / Dante network (no cable)')
            self.assertContains(response, 'data-stream="1"')

    def test_the_overview_keeps_its_legend(self):
        response = self.page('overview')
        self.assertContains(response, 'AVB / Dante network (no cable)')
        self.assertNotContains(response, 'One colour and name per stream')
        self.assertNotContains(response, 'data-stream="')
