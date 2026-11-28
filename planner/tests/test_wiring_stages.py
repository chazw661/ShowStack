"""The Overview's PDF paged by signal-flow stage, and the slot text a
console and an I/O device keep when the network feeds are hidden.

An Overview that would be tiled is drawn as A Inputs → Console → Outputs,
B Outputs → Processors → Amps, C Amps → Speakers: each laid out on its own,
a box on the boundary on both pages, no line leaving its page. The screen's
Overview and the DXF stay one drawing.

Run with::

    python manage.py test planner.tests.test_wiring_stages --settings=audiopatch.test_settings
"""
import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from planner.connections import layout as L
from planner.connections import svg
from planner.connections import tabs as T
from planner.connections import tiling
from planner.connections.graph import project_graph
from planner.models import ConsoleAuxOutput
from planner.tests.test_wiring_layout import WiringShow
from planner.tests.test_wiring_network_and_wrapping import NetworkShow, svg_of, texts
from planner.tests.test_wiring_pdf import read
from planner.tests.test_wiring_wrap import amp_graph
from planner.utils.pdf_exports import wiring_pdf
from planner.views_wiring import staged, tab_view

TABLOID, SHEET = wiring_pdf.PAPER['11x17'], wiring_pdf.PAPER['24x36']
AREA = wiring_pdf.diagram_area(TABLOID)


class StageShow(WiringShow):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def big(self, n=60):
        for i in range(n):
            box = self.device(f'Rack Box {i:02d}')
            self.device_output(box, 1, f'Feed {i:02d}')
            amp = self.amp(f'Amp {i:02d}', rack=f'Rack {i // 4}')
            self.amp_channel(amp, 1, analog_input=f'Feed {i:02d}')

    def overview(self, network=True):
        self.full = project_graph(self.project)
        return tab_view(self.project, self.full, T.OVERVIEW, network)

    def stages(self, network=True):
        return {stage: graph for stage, _, graph in T.stage_views(self.overview(network)['graph'])}

    def pdf(self, **params):
        response = self.client.get(reverse('planner:wiring_diagram_pdf'), {'tabs': 'overview', **params})
        self.assertEqual(response.status_code, 200)
        return read(response.content)[1]


class StageViewTests(StageShow, TestCase):

    def test_every_drawn_line_is_on_exactly_one_stage(self):
        graph = self.overview()['graph']
        drawn = sorted(e['id'] for e in graph['edges'] if not e.get('comm'))
        staged_ids = sorted(e['id'] for part in self.stages().values() for e in part['edges'])
        self.assertTrue(drawn)
        self.assertEqual(staged_ids, drawn)

    def test_a_line_is_on_the_stage_it_arrives_on(self):
        stages = self.stages()
        kinds = {n['id']: n['kind'] for n in self.full['nodes']}
        self.assertTrue(all(kinds[e['to']] in ('console', 'device') for e in stages[T.STAGE_A]['edges']))
        self.assertTrue(all('speaker' in e['transports'] for e in stages[T.STAGE_C]['edges']))
        for edge in stages[T.STAGE_B]['edges']:
            self.assertNotIn('speaker', edge['transports'])
            self.assertNotIn(kinds.get(edge['to']), ('console', 'device'))

    def test_every_box_of_the_overview_is_on_a_stage(self):
        whole = {b.node for b in self.overview()['layout'].boxes}
        on_stage = set()
        for stage, graph in self.stages().items():
            on_stage |= {b.node for b in L.layout(graph, **T.stage_options(stage)).boxes}
        self.assertEqual(on_stage, whole)

    def test_each_stage_has_only_its_own_columns(self):
        titles = {stage: [c[0] for c in L.layout(graph, **T.stage_options(stage)).columns]
                  for stage, graph in self.stages().items()}
        self.assertEqual(titles[T.STAGE_A], ['Device inputs', 'Console', 'Device outputs'])
        self.assertEqual(titles[T.STAGE_B], ['Device outputs', 'Processors', 'Amps'])
        self.assertEqual(titles[T.STAGE_C], ['Amps', 'Speakers'])

    def test_a_boundary_box_is_on_both_pages(self):
        lays = {stage: {b.id: b for b in L.layout(graph, **T.stage_options(stage)).boxes}
                for stage, graph in self.stages().items()}
        out, amp = f'device:{self.box.pk}#out', f'amp:{self.sl_amp.pk}'
        # the outputs box: what arrives on A, what leaves on B
        self.assertEqual(lays[T.STAGE_A][out].slots, ['Out 1 ← FOH Desk Aux 1'])
        self.assertEqual(lays[T.STAGE_A][out].outs, [])
        self.assertEqual(lays[T.STAGE_B][out].slots, [])
        self.assertIn(['Out 2'], lays[T.STAGE_B][out].out_text)
        self.assertNotIn(f'device:{self.box.pk}#in', lays[T.STAGE_B])
        # the amp: its inputs on B, only its speaker cable on C
        self.assertEqual(lays[T.STAGE_B][amp].slots, ['AES 1 ← SL P1 AES Out 1 (Main L)'])
        self.assertEqual(lays[T.STAGE_C][amp].slots, [])
        self.assertEqual(len(lays[T.STAGE_C][amp].outs), 1)

    def test_only_the_stage_that_owns_a_kind_boxes_the_unconnected(self):
        stages = self.stages()
        lone_amp, mics = f'amp:{self.sl_amp2.pk}', f'device:{self.mics.pk}'
        self.assertIn(lone_amp, {n['id'] for n in stages[T.STAGE_B]['nodes']})
        self.assertNotIn(lone_amp, {n['id'] for n in stages[T.STAGE_C]['nodes']})
        self.assertIn(mics, {n['id'] for n in stages[T.STAGE_A]['nodes']})
        self.assertNotIn(mics, {n['id'] for n in stages[T.STAGE_B]['nodes']})

    def test_a_stage_with_nothing_is_left_out(self):
        empty = {'nodes': [{'id': 'console:1', 'kind': 'console', 'label': 'Desk'}],
                 'edges': [], 'warnings': []}
        self.assertEqual([stage for stage, _, _ in T.stage_views(empty)], [T.STAGE_A])


class StagedPdfTests(StageShow, TestCase):

    def test_an_overview_too_big_for_a_page_is_paged_by_stage(self):
        view = self.overview(network=False)
        self.assertTrue(tiling.plan(view['layout'], *AREA).tiled)       # it would be tiled
        pages = self.pdf()
        heads = [' '.join(p.split('\n')[1].split()) for p in pages if p.startswith(self.project.name)]
        self.assertEqual(len(heads), 3)
        for head, title in zip(heads, ('Overview · A Inputs → Console → Outputs',
                                       'Overview · B Outputs → Processors → Amps',
                                       'Overview · C Amps → Speakers')):
            self.assertTrue(head.startswith(title + ' Printed '), head)
            self.assertNotIn('Part ', head)
        joined = '\n'.join(pages)
        self.assertNotRegex(joined, r'→ p\.\d')
        self.assertNotRegex(joined, r'from p\.\d')
        # a boundary box is drawn on both pages
        diagram = [p for p in pages if p.startswith(self.project.name)]
        self.assertIn('Stage Box', diagram[0])
        self.assertIn('Stage Box', diagram[1])
        self.assertIn('SL Amp', diagram[1])
        self.assertIn('SL Amp', diagram[2])
        self.assertIn('K2 L', diagram[2])
        self.assertNotIn('K2 L', diagram[1])

    def test_an_overview_that_fits_one_page_stays_whole(self):
        view = staged(self.overview(network=False), self.full, '24x36')
        self.assertNotIn('stages', view)
        pages = self.pdf(paper='24x36')
        heads = [' '.join(p.split('\n')[1].split()) for p in pages if p.startswith(self.project.name)]
        self.assertEqual(len(heads), 1)
        self.assertTrue(heads[0].startswith('Overview Printed '), heads[0])

    def test_any_other_tab_is_never_staged(self):
        self.big()
        full = project_graph(self.project)
        for tab in (T.DANTE, T.AVB, T.ANALOG, T.SPEAKERS, T.COMMS):
            view = tab_view(self.project, full, tab, False)
            self.assertIs(staged(view, full, '11x17'), view)

    def test_a_stage_too_tall_is_tiled_downward_only(self):
        self.big()
        view = staged(self.overview(network=False), self.full, '11x17')
        plans = wiring_pdf.plans_for([view], TABLOID)[T.OVERVIEW]
        self.assertEqual([part['stage'] for part, _, _ in plans], [T.STAGE_A, T.STAGE_B, T.STAGE_C])
        self.assertTrue(any(plan.tiled for _, plan, _ in plans))
        for part, plan, _ in plans:
            self.assertEqual(plan.strips, 1, part['title'])
            self.assertGreaterEqual(plan.scale, tiling.MIN_SCALE - 1e-9)
            # never wider than prints at the smallest scale
            self.assertLessEqual(part['layout'].width, AREA[0] / tiling.MIN_SCALE + 0.01)
        # only a stage cut downward says where its lines go on
        pages = self.pdf()
        for text in pages:
            head = ' '.join(text.split('\n')[1].split()) if text.startswith(self.project.name) else ''
            if head and ' Part ' not in head:
                self.assertNotRegex(text, r'(→|from) p\.\d')

    def test_the_stages_keys_run_on_in_one_connections_table(self):
        for i in range(3):
            box = self.device(f'A box with a very long name to make its label a key {i}')
            self.device_output(box, 1, f'A feed with a long name, long enough to be a key {i:02d}')
            amp = self.amp(f'An amp with a very long name to make the label a key {i}', rack='Keys')
            self.amp_channel(amp, 1, analog_input=f'A feed with a long name, long enough to be a key {i:02d}')
        view = staged(self.overview(network=False), self.full, '11x17')
        keys = [key for part in view['stages'] for key, _ in part['layout'].keys]
        self.assertGreaterEqual(len(keys), 3)
        self.assertEqual(keys, list(range(1, len(keys) + 1)))
        self.assertEqual([row['key'] for row in view['connections']], keys)

    def test_the_screen_and_the_dxf_stay_one_drawing(self):
        self.big()
        page = self.client.get(reverse('planner:wiring_diagram')).content.decode()
        self.assertNotIn('(cont.)', page)
        self.assertNotIn('A  Inputs', page)
        whole = tab_view(self.project, project_graph(self.project), T.OVERVIEW, True)
        self.assertNotIn('stages', whole)
        self.assertIn(svg.render(whole['layout'], title=f'Wiring diagram: {self.project.name} — Overview'),
                      page)
        response = self.client.get(reverse('planner:wiring_diagram_dxf'), {'tabs': 'overview'})
        self.assertEqual(response.status_code, 200)
        text = response.content.decode('utf-8', 'replace')
        self.assertNotIn('(cont.)', text)
        self.assertNotIn('Inputs -> Console', text)

    def test_the_panel_counts_the_stage_pages(self):
        page = self.client.get(reverse('planner:wiring_diagram')).content.decode()
        self.assertRegex(page, r'value="overview"[^>]*> [^<]+ <span class="wd-pages"'
                               r' data-p-11x17-0="3" data-p-24x36-0="1"')
        self.assertEqual(len([p for p in self.pdf() if p.startswith(self.project.name)]), 3)


class WrapWidthTests(SimpleTestCase):
    """``layout(wrap=True, wrap_width=)``: sub-columns only while the tab
    is no wider than the cap; the best fit of those."""

    def test_never_wider_than_the_cap(self):
        graph = amp_graph(40)
        free = L.layout(graph, hide_empty=L.ALL_COLUMNS, wrap=True, wrap_width=10 ** 6)
        self.assertGreater(len(free.columns), 3)
        cap = free.width - 1
        capped = L.layout(graph, hide_empty=L.ALL_COLUMNS, wrap=True, wrap_width=cap)
        self.assertLessEqual(capped.width, cap)
        self.assertLess(len(capped.columns), len(free.columns))
        plain = L.layout(graph, hide_empty=L.ALL_COLUMNS)
        self.assertGreaterEqual(L._fit(capped), L._fit(plain))

    def test_a_cap_under_the_plain_width_wraps_nothing(self):
        graph = amp_graph(40)
        plain = L.layout(graph, hide_empty=L.ALL_COLUMNS)
        capped = L.layout(graph, hide_empty=L.ALL_COLUMNS, wrap=True, wrap_width=plain.width)
        self.assertEqual([c[0] for c in capped.columns], [c[0] for c in plain.columns])

    def test_it_keeps_the_best_fit_not_the_widest(self):
        graph = amp_graph(40)
        lay = L.layout(graph, hide_empty=L.ALL_COLUMNS, wrap=True, wrap_width=10 ** 6)
        one_more = L.layout(graph, hide_empty=L.ALL_COLUMNS, wrap=True, wrap_width=10 ** 6,
                            page=(L.WRAP_PAGE[0] * 4, L.WRAP_PAGE[1]))
        self.assertGreaterEqual(len(one_more.columns), len(lay.columns))    # a wider page takes more
        self.assertGreaterEqual(L._fit(lay), L._fit(L.layout(graph, hide_empty=L.ALL_COLUMNS)))

    def test_the_first_key_is_numbered_as_asked(self):
        graph = amp_graph(4)
        lay = L.layout(graph, hide_empty=L.ALL_COLUMNS, label_max=1, first_key=7)
        self.assertTrue(lay.keys)
        self.assertEqual([key for key, _ in lay.keys], list(range(7, 7 + len(lay.keys))))

    def test_a_vertical_plan_is_one_strip(self):
        lay = L.layout(amp_graph(60), hide_empty=L.ALL_COLUMNS)
        self.assertGreater(lay.height, AREA[1] / tiling.MIN_SCALE)
        plan = tiling.plan(lay, *AREA, vertical=True)
        self.assertTrue(plan.tiled)
        self.assertEqual(plan.strips, 1)
        self.assertLessEqual(plan.scale, AREA[0] / lay.width + 1e-9)


class KeptSlotTests(NetworkShow, TestCase):
    """Network feeds off: a console and an I/O device keep their slot text,
    as amps and processors do."""

    def setUp(self):
        super().setUp()
        aux = ConsoleAuxOutput.objects.create(console=self.desk, aux_number='1', name='Wedge 1')
        self.device_output(self.dante, 1, 'Wedge 1', bus=aux)

    def boxes(self, graph):
        return {b.id: b for b in L.layout(graph).boxes}

    def test_the_console_and_the_outputs_box_keep_their_slots(self):
        graph = project_graph(self.project)
        on, off = self.boxes(graph), self.boxes(T.without_network(graph))
        desk, out = f'console:{self.desk.pk}', f'device:{self.dante.pk}#out'
        self.assertEqual(on[desk].slots, ['Ch 1 ← Dante Box In 1'])
        self.assertEqual(off[desk].slots, on[desk].slots)
        self.assertEqual(off[desk].ins, [])                 # the line itself is hidden
        self.assertEqual(off[out].slots, on[out].slots)
        self.assertEqual(off[out].slots, ['Out 1 ← FOH Desk Aux 1'])

    def test_an_outputs_slot_is_never_kept_on_the_inputs_box(self):
        off = self.boxes(T.without_network(project_graph(self.project)))
        self.assertEqual(off[f'device:{self.dante.pk}#in'].slots, [])

    def test_the_screen_shows_them_with_the_feeds_off(self):
        drawn = texts(svg_of(self.page(view='overview', network='0')))
        self.assertIn('Ch 1 ← Dante Box In 1', drawn)
        self.assertIn('Out 1 ← FOH Desk Aux 1', drawn)
        self.assertEqual(drawn.count('Ch 1 ← Dante Box In 1'), 1)

    def test_the_pdf_and_the_dxf_show_them_too(self):
        pdf = self.client.get(reverse('planner:wiring_diagram_pdf'), {'tabs': 'overview'})
        text = '\n'.join(read(pdf.content)[1])
        self.assertIn('Ch 1 ← Dante Box In 1', text)
        self.assertIn('Out 1 ← FOH Desk Aux 1', text)
        dxf = self.client.get(reverse('planner:wiring_diagram_dxf'),
                              {'tabs': 'overview', 'arrows': 'ascii'}).content.decode('utf-8', 'replace')
        self.assertIn('Ch 1 <- Dante Box In 1', dxf)
