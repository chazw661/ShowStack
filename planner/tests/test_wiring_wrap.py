"""Wiring diagram: a tall column of the Dante and AVB tabs wraps into
sub-columns, and the PDF's "Warnings: none".

Run with::

    python manage.py test planner.tests.test_wiring_wrap \\
        --settings=audiopatch.test_settings
"""
import types

from django.test import SimpleTestCase
from django.utils import timezone

from planner.connections import layout as L
from planner.connections import svg, tiling
from planner.connections import tabs as T
from planner.tests.test_wiring_pdf import H, W, read
from planner.utils.pdf_exports import wiring_pdf


def amp_graph(amps, locations=('PA LEFT', 'PA RIGHT'), streams=4):
    """A processor whose AVB outputs feed ``amps`` amps, shared out over
    ``locations`` in turn and over ``streams`` outputs."""
    nodes = [{'id': 'processor:1', 'kind': 'processor', 'label': 'P1',
              'out_slots': [{'id': f'avb:{s}', 'lines': [f'AVB Out {s}']}
                            for s in range(1, streams + 1)]}]
    edges = []
    per = -(-amps // len(locations))
    for i in range(amps):
        where = i // per
        stream = i % streams + 1
        nodes.append({'id': f'amp:{i}', 'kind': 'amp', 'label': f'Amp {i + 1}', 'model': 'LA12X',
                      'location': {'kind': 'amp_location', 'id': where, 'name': locations[where],
                                   'sort_order': where},
                      'slots': [{'id': 'avb:1', 'label': f'AVB ← P1 stream {stream}'}]})
        edges.append({'id': f'e{i}', 'from': 'processor:1', 'to': f'amp:{i}', 'label': f'Amp {i + 1}',
                      'status': 'confirmed', 'network': True, 'stream': stream,
                      'from_slot': f'avb:{stream}', 'to_slot': 'avb:1', 'links': []})
    return {'nodes': nodes, 'edges': edges, 'warnings': []}


def draw(graph, **options):
    return L.layout(graph, hide_empty=L.ALL_COLUMNS, trunks='T', **options)


class WrapTests(SimpleTestCase):

    def setUp(self):
        self.graph = amp_graph(16)
        self.plain = draw(self.graph)
        self.lay = draw(self.graph, wrap=True)

    def column_of(self, lay, box):
        [title] = [title for title, x, _ in lay.columns if abs(x - box.x) < 0.01]
        return title

    def test_the_dante_and_avb_tabs_wrap_and_no_other_tab_does(self):
        for tab in T.TAB_KEYS:
            self.assertEqual(bool(T.layout_options(tab).get('wrap')), tab in (T.DANTE, T.AVB), tab)

    def test_a_tall_column_becomes_sub_columns_side_by_side(self):
        self.assertEqual([t for t, _, _ in self.plain.columns], ['Processors', 'Amps'])
        self.assertEqual([t for t, _, _ in self.lay.columns], ['Processors', 'Amps', 'Amps (cont.)'])
        xs = [x for _, x, _ in self.lay.columns]
        self.assertEqual(xs, sorted(xs))
        self.assertLess(self.lay.height, self.plain.height)
        self.assertGreater(L._fit(self.lay), L._fit(self.plain))

    def test_every_box_and_line_is_still_drawn_once(self):
        self.assertEqual(sorted(b.id for b in self.lay.boxes), sorted(b.id for b in self.plain.boxes))
        self.assertEqual(sorted(r.id for r in self.lay.routes), sorted(r.id for r in self.plain.routes))
        self.assertEqual(self.lay.not_drawn, [])
        self.assertEqual(len(self.lay.trunks), len(self.plain.trunks))
        for route in self.lay.routes:
            xs = [x for x, _ in route.points]
            self.assertEqual(xs, sorted(xs), route.id)          # never leftward

    def test_whole_groups_go_side_by_side_in_their_order(self):
        self.assertEqual([g.label for g in self.lay.groups], ['PA LEFT', 'PA RIGHT'])
        where = {g.label: {self.column_of(self.lay, b) for b in self.lay.boxes if b.group == g.key}
                 for g in self.lay.groups}
        self.assertEqual(where, {'PA LEFT': {'Amps'}, 'PA RIGHT': {'Amps (cont.)'}})

    def test_a_group_cut_by_the_wrap_is_headed_continued(self):
        lay = draw(amp_graph(16, locations=('PA LEFT',)), wrap=True)
        self.assertEqual([g.label for g in lay.groups][:2], ['PA LEFT', 'PA LEFT (continued)'])
        for group in lay.groups:
            mine = [b for b in lay.boxes if b.group == group.key]
            self.assertTrue(mine, group.label)
            self.assertEqual({b.x for b in mine}, {group.x})
            self.assertLessEqual(group.y + group.head, min(b.y for b in mine) + 0.01)
        # the boxes keep their order: down the first sub-column, then the next
        order = [b.label for b in sorted(lay.boxes, key=lambda b: (b.x, b.y)) if b.kind == 'amp']
        plain = [b.label for b in sorted(draw(amp_graph(16, locations=('PA LEFT',))).boxes,
                                         key=lambda b: b.y) if b.kind == 'amp']
        self.assertEqual(sorted(order), sorted(plain))
        first = [b for b in lay.boxes if b.kind == 'amp' and self.column_of(lay, b) == 'Amps']
        self.assertEqual({b.label for b in first}, set(plain[:len(first)]))

    def test_a_line_passing_a_sub_column_runs_above_its_first_header(self):
        first = [b for b in self.lay.boxes if b.kind == 'amp' and self.column_of(self.lay, b) == 'Amps']
        left, right = min(b.x for b in first), max(b.x + b.w for b in first)
        header = min(g.y for g in self.lay.groups if abs(g.x - left) < 0.01)
        later = {b.node for b in self.lay.boxes if self.column_of(self.lay, b) == 'Amps (cont.)'}
        passing = [r for r in self.lay.routes if r.to_node in later]
        self.assertTrue(passing)
        for route in passing:
            for (x0, y0), (x1, y1) in zip(route.points, route.points[1:]):
                if abs(y0 - y1) < 0.01 and x0 < right and x1 > left:
                    self.assertLess(y0, header, route.id)
        # and through no box
        for route in self.lay.routes:
            for (x0, y0), (x1, y1) in zip(route.points, route.points[1:]):
                for b in self.lay.boxes:
                    inside = (min(x0, x1) < b.x + b.w - 0.01 and max(x0, x1) > b.x + 0.01
                              and min(y0, y1) < b.y + b.h - 0.01 and max(y0, y1) > b.y + 0.01)
                    self.assertFalse(inside, f'{route.id} through {b.label}')

    def test_a_tab_that_fits_a_page_is_left_alone(self):
        graph = amp_graph(4)
        self.assertGreaterEqual(L._fit(draw(graph)), 1)
        self.assertEqual([t for t, _, _ in draw(graph, wrap=True).columns], ['Processors', 'Amps'])

    def test_one_tall_box_cannot_wrap(self):
        graph = amp_graph(1)
        graph['nodes'][1]['slots'] = [{'id': f'avb:{i}', 'label': f'In {i}', 'kept': True}
                                      for i in range(1, 80)]
        lay = draw(graph, wrap=True)
        self.assertEqual([t for t, _, _ in lay.columns], ['Processors', 'Amps'])

    def test_it_wraps_no_further_than_helps(self):
        # 16 amps fit a page in two sub-columns: a third would only be wider.
        self.assertEqual(len(self.lay.columns), 3)
        self.assertEqual(len(tiling.plan(self.lay, W, H).tiles), 1)

    def test_the_page_cuts_fall_between_sub_columns(self):
        lay = draw(amp_graph(60, streams=6), wrap=True)
        plan = tiling.plan(lay, W, H)
        for tile in plan.tiles:
            for r in tile.regions:
                for b in lay.boxes:
                    self.assertFalse(b.x < r.x0 - 0.01 < b.x + b.w or b.x < r.x1 - 0.01 < b.x + b.w,
                                     b.label)

    def test_svg_titles_each_sub_column_and_header(self):
        out = svg.render(draw(amp_graph(16, locations=('PA LEFT',)), wrap=True))
        self.assertIn('>Amps (cont.)</text>', out)
        self.assertIn('>PA LEFT (continued)</text>', out)

    def test_partition_is_the_most_even_cut(self):
        self.assertEqual(L._partition([5, 5, 5, 5], 2), (10, (0, 2)))
        self.assertEqual(L._partition([9, 1, 1, 1], 2), (9, (0, 1)))
        self.assertEqual(L._partition([1, 2, 3], 3), (3, (0, 1, 2)))


class BadgeTextTests(SimpleTestCase):
    def test_a_badge_is_never_under_6pt_in_the_pdf(self):
        self.assertGreaterEqual(L.BADGE_PX * tiling.MIN_SCALE, wiring_pdf.MIN_PT)
        self.assertIn(f'.wd-badge text {{ font: 700 {L.BADGE_PX}px', svg.STYLE)


class NoWarningsPdfTests(SimpleTestCase):
    """A tab with no warnings says so in its title block and has no page
    for them; one with warnings keeps its list."""

    def pages(self, warnings, connections=()):
        lay = draw(amp_graph(4), wrap=True)
        view = {'tab': T.AVB, 'tab_label': 'AVB', 'layout': lay, 'tab_empty': False,
                'tab_empty_text': '', 'show_unset_legend': False, 'show_b_legend': False,
                'connections': list(connections), 'warnings': list(warnings)}
        pdf = wiring_pdf.build_wiring_pdf(project=types.SimpleNamespace(name='Tidy show'), views=[view],
                                          digest='abc123', paper='11x17', printed=timezone.now())
        return read(pdf)[1]

    def test_none(self):
        pages = self.pages([])
        self.assertEqual(len(pages), 1)
        self.assertIn('Graph abc123 · Warnings: none', ' '.join(pages[0].split()))
        self.assertNotIn('Warnings —', pages[0])

    def test_some(self):
        pages = self.pages([{'title': 'Not linked', 'edge': 'Amp 1 AVB Ch 1', 'text': 'Nowhere'}])
        self.assertEqual(len(pages), 2)
        self.assertNotIn('Warnings: none', pages[0])
        self.assertIn('Warnings (1) — AVB', pages[1])
        self.assertIn('Nowhere', pages[1])

    def test_a_connections_table_still_gets_its_page(self):
        pages = self.pages([], [{'key': 'C1', 'from': 'A · Out 1', 'to': 'B · In 1', 'cable': 'Dante'}])
        self.assertEqual(len(pages), 2)
        self.assertIn('Warnings: none', pages[0])
        self.assertIn('Connections (1) — AVB', pages[1])
        self.assertNotIn('Warnings', pages[1])
