"""Wiring Diagram: B input links (DeviceInput.console_input_b).

Each B link is its own edge (``b: true``), lighter than A's, labelled the way
an A console link is plus " (B)" and " · <Source (B)>" when set; on Overview,
Dante and Analogue/AES by the device's Console connection, like A. A device
patched only on B is on its tab. Download PDF and Download DXF draw them too.

    python manage.py test planner.tests.test_wiring_b_links \\
        --settings=audiopatch.test_settings
"""
import io
import warnings
import xml.etree.ElementTree as ET
from unittest import mock

import ezdxf

from django.test import TestCase
from django.urls import reverse

from planner.connections import dxf
from planner.connections import layout as L
from planner.connections import svg
from planner.connections import tabs as T
from planner.connections.graph import project_graph
from planner.models import DeviceInput
from planner.tests.connection_fixtures import ConnectionFixtures
from planner.utils.pdf_exports import wiring_pdf
from planner.views_wiring import connection_rows, tab_view

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from PyPDF2 import PdfReader

SVG_NS = '{http://www.w3.org/2000/svg}'


class BShow(ConnectionFixtures):

    def setUp(self):
        super().setUp()
        self.desk = self.console('FOH Desk')
        self.kick = self.channel(self.desk, 1, 'Kick')
        self.kick.source_b = 'Kick wireless'
        self.kick.save()
        self.snare = self.channel(self.desk, 2, 'Snare')
        self.tom = self.channel(self.desk, 3, 'Tom')
        # Dante box: A on In 1, B of the same channel on In 2.
        self.dante = self.connected(self.device('Dante Box'), 'dante')
        self.device_input(self.dante, 1, self.kick)
        self.b(self.device_input(self.dante, 2), self.kick)
        # An analogue box patched ONLY on B.
        self.madi = self.connected(self.device('B Only Box'), 'analog')
        self.b(self.device_input(self.madi, 1), self.snare)
        self.b(self.device_input(self.madi, 2), self.tom)

    def connected(self, device, connection):
        device.console_connection = connection
        device.save()
        return device

    @staticmethod
    def b(port, channel):
        DeviceInput.objects.filter(pk=port.pk).update(console_input_b=channel)
        return port

    def graph(self):
        return project_graph(self.project)

    @staticmethod
    def b_edges(graph):
        return [e for e in graph['edges'] if e.get('b')]


class BEdgeTests(BShow, TestCase):

    def test_b_links_are_their_own_edges_with_the_b_label(self):
        g = self.graph()
        a = [e for e in g['edges'] if not e.get('b') and e['from'].startswith('device:')]
        self.assertEqual([(e['from_ports'], e['label']) for e in a], [('In 1', 'FOH Desk Ch 1')])
        labels = sorted(e['label'] for e in self.b_edges(g))
        self.assertEqual(labels, ['FOH Desk Ch 1 (B) · Kick wireless', 'FOH Desk Ch 2–3 (B)'])
        self.assertEqual(sorted(e['from_ports'] for e in self.b_edges(g)), ['In 1–2', 'In 2'])
        edge = next(e for e in self.b_edges(g) if 'Kick' in e['label'])
        self.assertEqual(edge['sources'], [{'kind': 'fk', 'field': 'DeviceInput.console_input_b',
                                            'count': 1}])
        self.assertEqual(edge['to_ports'], 'Ch 1 (B)')
        self.assertEqual(edge['transports'], ['dante'])
        self.assertTrue(edge['network'])

    def test_one_aggregated_b_line_per_device_pair_beside_the_a_line(self):
        g = self.graph()
        pairs = [(e['from'], e['to'], bool(e.get('b'))) for e in g['edges']]
        dante = f'device:{self.dante.pk}'
        self.assertEqual(sorted(p for p in pairs if p[0] == dante),
                         [(dante, f'console:{self.desk.pk}', False),
                          (dante, f'console:{self.desk.pk}', True)])
        self.assertEqual(sum(p[0] == f'device:{self.madi.pk}' for p in pairs), 1)

    def test_an_a_label_has_no_b_mark(self):
        self.assertIn('FOH Desk Ch 1', [e['label'] for e in self.graph()['edges']])

    def test_source_b_text_never_makes_a_link(self):
        DeviceInput.objects.filter(device=self.dante, input_number=2).update(console_input_b=None)
        self.device_input(self.dante, 3, name='Kick wireless')
        labels = [e['label'] for e in self.b_edges(self.graph())]
        self.assertFalse(any('Kick' in x for x in labels), labels)

    def test_b_on_every_tab_by_its_devices_connection(self):
        g = self.graph()
        overview = self.b_edges(T.graph_view(g, T.OVERVIEW))
        dante = self.b_edges(T.graph_view(g, T.DANTE))
        analog = self.b_edges(T.graph_view(g, T.ANALOG))
        self.assertEqual(len(overview), 2)
        self.assertEqual([e['label'] for e in dante], ['FOH Desk Ch 1 (B) · Kick wireless'])
        self.assertEqual([e['label'] for e in analog], ['FOH Desk Ch 2–3 (B)'])
        self.assertEqual(self.b_edges(T.graph_view(g, T.SPEAKERS)), [])

    def test_a_device_patched_only_on_b_is_on_its_tab(self):
        view = T.graph_view(self.graph(), T.ANALOG)
        node = next(n for n in view['nodes'] if n['id'] == f'device:{self.madi.pk}')
        self.assertEqual(node['ports'], {'inputs': 2, 'outputs': 0})
        self.assertNotIn(f'device:{self.dante.pk}', {n['id'] for n in view['nodes']})

    def test_a_port_that_is_a_and_b_counts_once_on_the_box(self):
        self.b(DeviceInput.objects.get(device=self.dante, input_number=1), self.tom)
        view = T.graph_view(self.graph(), T.DANTE)
        node = next(n for n in view['nodes'] if n['id'] == f'device:{self.dante.pk}')
        self.assertEqual(node['ports']['inputs'], 2)

    def test_b_edges_are_drawn_lighter_on_every_tab(self):
        for tab in (T.OVERVIEW, T.DANTE, T.ANALOG):
            lay = L.layout(T.graph_view(self.graph(), tab), **T.layout_options(tab))
            b_routes = [r for r in lay.routes if 'b' in r.classes]
            self.assertTrue(b_routes, tab)
            root = ET.fromstring(svg.render(lay, title='t'))
            # a line of its own, or (Dante: trunks) the stretch of a trunk only B runs along
            classes = [p.get('class', '').split() for tag in ('path', 'line')
                       for p in root.iter(f'{SVG_NS}{tag}')]
            self.assertTrue(any(c[0] == 'wd-edge' and 'b' in c for c in classes if c), tab)
        self.assertIn('.wd-edge.b { stroke-opacity: .45; }', svg.STYLE)

    def test_b_rows_get_keys_in_the_connections_table(self):
        self.kick.source_b = 'A very long wireless backup source name ' * 3
        self.kick.save()
        view = tab_view(self.project, self.graph(), T.OVERVIEW)
        rows = [r for r in view['connections'] if '(B)' in r['to']]
        self.assertTrue(rows, view['connections'])
        self.assertIsInstance(rows[0]['key'], int)
        self.assertIn('Ch 1 (B)', rows[0]['to'])
        self.assertTrue(view['show_b_legend'])

    def login(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def test_download_pdf_draws_b_lighter_and_labelled(self):
        self.login()
        seen = {}
        real = wiring_pdf.build_wiring_pdf

        def spy(**kw):
            seen.update(kw)
            return real(**kw)
        with mock.patch('planner.utils.pdf_exports.wiring_pdf.build_wiring_pdf', spy):
            r = self.client.get(reverse('planner:wiring_diagram_pdf'), {'network': '1'})
        self.assertEqual(r.status_code, 200)
        by_tab = {view['tab']: view for view in seen['views']}
        for tab in (T.OVERVIEW, T.DANTE, T.ANALOG):
            self.assertTrue(self.b_edges(by_tab[tab]['graph']), tab)
            self.assertTrue(by_tab[tab]['show_b_legend'], tab)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            pages = [p.extract_text() or '' for p in PdfReader(io.BytesIO(r.content)).pages]
        text = ' '.join(' '.join(pages).split())
        self.assertIn('FOH Desk Ch 1 (B) · Kick wireless', text)
        self.assertIn('FOH Desk Ch 2–3 (B)', text)
        self.assertIn('B input (lighter; labelled “(B)”)', text)
        # Lighter: the line at 45%, its label at 80%, as on screen.
        line = wiring_pdf._cascade(wiring_pdf.EDGE_STYLES, ('confirmed', 'b'))
        label = wiring_pdf._cascade(wiring_pdf.LABEL_STYLES, ('confirmed', 'b'))
        self.assertEqual((line['alpha'], label['alpha']), (0.45, 0.8))
        self.assertEqual(wiring_pdf._cascade(wiring_pdf.EDGE_STYLES, ('confirmed',))['alpha'], 1)
        self.assertIn(b'/CA .45', r.content)          # the stroke opacity is in the file

    def test_a_pdf_with_no_b_link_has_no_b_legend(self):
        DeviceInput.objects.update(console_input_b=None)
        self.login()
        r = self.client.get(reverse('planner:wiring_diagram_pdf'))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            text = ' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(r.content)).pages)
        self.assertNotIn('B input', text)
        self.assertNotIn('(B)', text)

    def test_download_dxf_draws_b_on_its_status_layer_lighter_and_labelled(self):
        self.login()
        # The Dante B link is a network feed: still on its status layer.
        for tab in (T.DANTE, T.ANALOG, T.OVERVIEW):
            r = self.client.get(reverse('planner:wiring_diagram_dxf'), {'tabs': tab, 'network': '1'})
            self.assertEqual(r.status_code, 200)
            doc = ezdxf.read(io.StringIO(r.content.decode('utf-8')))
            msp = doc.modelspace()
            view = tab_view(self.project, self.graph(), tab)
            b_routes = [route for route in view['layout'].routes if 'b' in route.classes]
            self.assertTrue(b_routes, tab)
            # Every line states its own colour; only a B link has the faded one.
            if tab == T.DANTE:
                # Drawn as trunks: the stretches only a B link runs along,
                # in its trunk's colour, faded.
                colours = {dxf._fade(int(c[1:], 16)) for c in L.STREAM_COLOURS}
                faded = [e for e in msp.query('LINE') if e.dxf.get('true_color') in colours]
                self.assertTrue(faded, tab)
            else:
                faded = [e for e in msp.query('LWPOLYLINE')
                         if not e.closed and e.dxf.true_color == dxf._fade(0x2b4c7e)]
                self.assertEqual(len(faded), len(b_routes), tab)
            names = dxf.layer_names()
            for line in faded:
                self.assertIn(line.dxf.layer, [names[r] for r in (dxf.CONFIRMED, dxf.INFERRED, dxf.UNLINKED)], tab)
            texts = [e.plain_text() for e in msp.query('TEXT')]
            self.assertTrue(any(t.startswith('FOH Desk Ch') and '(B)' in t for t in texts), tab)
            self.assertIn(dxf.B_LEGEND[0], texts)
        self.assertEqual(dxf.edge_layer(T.DANTE, ('confirmed', 'network', 'b'), {}), dxf.CONFIRMED)
        self.assertEqual(dxf.edge_layer(T.DANTE, ('confirmed', 'network'), {}), dxf.NETWORK)

    def test_the_page_still_draws_them_with_the_legend(self):
        self.login()
        page = self.client.get(reverse('planner:wiring_diagram')).content.decode()
        self.assertIn('B input (lighter', page)
