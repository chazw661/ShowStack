"""project_graph(): existing links plus live rules, aggregated into edges.

Run with::

    python manage.py test planner.tests.test_connection_graph \\
        --settings=audiopatch.test_settings
"""
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from planner.connections.graph import project_graph
from planner.models import ConsoleAuxOutput
from planner.tests.connection_fixtures import ConnectionFixtures


def _edges(graph, frm=None, to=None):
    return [e for e in graph['edges']
            if (frm is None or e['from'] == frm) and (to is None or e['to'] == to)]


class GraphTests(ConnectionFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.desk = self.console()
        self.box = self.device('Stage Box')
        self.desk_id = f'console:{self.desk.pk}'
        self.box_id = f'device:{self.box.pk}'

    def graph(self):
        return project_graph(self.project)

    # -- existing foreign keys ----------------------------------------------

    def test_fifteen_linked_inputs_are_one_edge_with_a_range_label(self):
        for n in range(1, 16):
            self.device_input(self.box, n, self.channel(self.desk, n, f'Src {n}'))
        [edge] = _edges(self.graph(), self.box_id, self.desk_id)
        self.assertEqual(edge['label'], 'In 1–15 → Ch 1–15')
        self.assertEqual((edge['status'], edge['unlinked'], edge['network']),
                         ('confirmed', False, False))
        self.assertEqual(len(edge['links']), 15)
        self.assertEqual(edge['sources'],
                         [{'kind': 'fk', 'field': 'DeviceInput.console_input', 'count': 15}])

    def test_gaps_in_a_run_are_listed(self):
        for n in (1, 2, 3, 4, 7):
            self.device_input(self.box, n, self.channel(self.desk, n))
        [edge] = _edges(self.graph(), self.box_id, self.desk_id)
        self.assertEqual(edge['label'], 'In 1–5 → Ch 1–4, 7')

    def test_a_bus_out_to_two_stage_boxes_is_two_edges(self):
        aux = ConsoleAuxOutput.objects.create(console=self.desk, aux_number='1', name='Wedge 1')
        other = self.device('Drum Box')
        self.device_output(self.box, 1, 'Wedge 1', bus=aux)
        self.device_output(other, 1, 'Wedge 1', bus=aux)
        graph = self.graph()
        self.assertEqual({e['to'] for e in _edges(graph, self.desk_id)},
                         {self.box_id, f'device:{other.pk}'})
        for edge in _edges(graph, self.desk_id):
            self.assertEqual(edge['label'], 'Aux 1 → Out 1')

    def test_linked_pa_row_is_a_confirmed_amp_to_array_edge_with_its_cable(self):
        amp = self.amp('SL LA12X #1')
        arr = self.array(self.prediction(), 'K2 Main L')
        row = self.linked_cable(amp, arr, count=3, length=150)
        [edge] = _edges(self.graph(), f'amp:{amp.pk}', f'speaker_array:{arr.pk}')
        self.assertEqual((edge['status'], edge['transports']), ('confirmed', ['speaker']))
        self.assertEqual(edge['cable'], {'recorded': True, 'ids': [], 'count': 3,
                                         'type': 'NL 4', 'length_ft': 150})
        self.assertEqual(edge['sources'], [{'kind': 'pa_cable', 'pk': row.pk}])
        self.assertEqual(edge['label'], "3× NL 4 150'")

    def test_linked_pa_row_whose_array_is_gone_is_unlinked(self):
        amp = self.amp('SL LA12X #1')
        arr = self.array(self.prediction(), 'K2 Main L')
        row = self.linked_cable(amp, arr, label=self.zone('Main L'))
        arr.delete()   # what a Soundvision re-import does; the FK is SET_NULL
        graph = self.graph()
        [edge] = _edges(graph, f'amp:{amp.pk}')
        self.assertEqual((edge['status'], edge['unlinked']), ('confirmed', True))
        self.assertEqual(edge['to'], f'unlinked:pa:{row.pk}:speaker')
        self.assertEqual(edge['label'], "Main L · 1× NL 4 150'")
        node = next(n for n in graph['nodes'] if n['id'] == edge['to'])
        self.assertEqual(node['label'], 'Speaker array — not linked')

    # -- live rules ---------------------------------------------------------------

    def test_same_processor_aes_and_analog_is_one_certain_edge(self):
        sl = self.p1('SL P1')
        self.p1_in(sl, 'AES', 1, 'L Main')
        self.p1_in(sl, 'ANALOG', 1, 'L Main')
        self.matrix(self.desk, 1, destination='L Main')
        [edge] = _edges(self.graph(), self.desk_id, f'processor:{sl.pk}')
        self.assertEqual(edge['status'], 'inferred')
        self.assertEqual(edge['transports'], ['aes', 'analog'])
        self.assertEqual(edge['match'], ['same_processor'])
        self.assertNotIn('ambiguous', edge)
        self.assertEqual({l['to_port'] for l in edge['links']}, {'AES 1', 'Analog 1'})
        self.assertEqual(edge['cable'], {'recorded': False})

    def test_a_label_edit_shows_without_running_anything(self):
        sl, sr = self.p1('SL P1'), self.p1('SR P1')
        port = self.p1_in(sl, 'AES', 1, 'Front')
        self.device_output(self.box, 1, 'Front')
        self.assertEqual(len(_edges(self.graph(), self.box_id, f'processor:{sl.pk}')), 1)

        port.label = 'Old'
        port.save()
        self.p1_in(sr, 'AES', 2, 'Front')
        graph = self.graph()
        self.assertEqual(_edges(graph, self.box_id, f'processor:{sl.pk}'), [])
        [edge] = _edges(graph, self.box_id, f'processor:{sr.pk}')
        self.assertEqual(edge['label'], 'Out 1 → AES 2')

    def test_ambiguous_match_is_an_unlinked_edge_with_candidates_and_a_warning(self):
        sl, sr = self.p1('SL P1'), self.p1('SR P1')
        self.p1_in(sl, 'AES', 1, 'Main')
        self.p1_in(sr, 'AES', 1, 'Main')
        out = self.device_output(self.box, 1, 'Main')
        graph = self.graph()
        self.assertEqual(_edges(graph, self.box_id, f'processor:{sl.pk}'), [])
        self.assertEqual(_edges(graph, self.box_id, f'processor:{sr.pk}'), [])

        [edge] = _edges(graph, self.box_id)
        self.assertTrue(edge['ambiguous'])
        self.assertTrue(edge['unlinked'])
        self.assertEqual({c['node'] for c in edge['candidates']},
                         {f'processor:{sl.pk}', f'processor:{sr.pk}'})
        node = next(n for n in graph['nodes'] if n['id'] == edge['to'])
        self.assertEqual((node['kind'], node['label'], node['ambiguous']),
                         ('unlinked', 'Main', True))
        [warning] = graph['warnings']
        self.assertEqual((warning['kind'], warning['rule'], warning['edge'], warning['source']),
                         ('ambiguous', 'a', edge['id'], f'deviceoutput:{out.pk}'))

    def test_avb_feed_is_a_network_edge_and_aes_a_cable_edge(self):
        sl = self.p1('SL P1')
        amp = self.amp('SL LA12X #1')
        self.p1_out(sl, 'AVB', 1, 'Main L')
        self.p1_out(sl, 'AES', 1, 'Main L')
        self.amp_channel(amp, 1, avb_stream='AVB 1 - Main L', aes_input='Main L')
        edges = _edges(self.graph(), f'processor:{sl.pk}', f'amp:{amp.pk}')
        by_network = {e['network']: e for e in edges}
        self.assertEqual(set(by_network), {True, False})
        self.assertEqual((by_network[True]['transports'], by_network[True]['cable']),
                         (['avb'], None))
        self.assertEqual((by_network[False]['transports'], by_network[False]['cable']),
                         (['aes'], {'recorded': False}))
        self.assertEqual(by_network[True]['label'], 'AVB 1 → Ch 1')

    def test_amp_input_text_that_matches_nothing_is_an_unlinked_edge(self):
        amp = self.amp('SL LA12X #1')
        self.amp_channel(amp, 2, analog_input='from somewhere')
        [edge] = _edges(self.graph(), to=f'amp:{amp.pk}')
        self.assertTrue(edge['unlinked'])
        self.assertEqual(edge['text'], {'source': 'from somewhere', 'field': 'analog_input'})
        self.assertEqual(edge['label'], '→ Ch 2')

    def test_free_text_pa_row_is_amp_to_array_labelled_with_its_zone_and_cable(self):
        amp = self.amp('SL LA12X #1')
        arr = self.array(self.prediction(), 'KS28 L')
        self.text_cable(self.zone('HR'), destination='KS28 L', amp=amp,
                        cable='NL_8', count=2, length=75)
        graph = self.graph()
        [edge] = _edges(graph, f'amp:{amp.pk}', f'speaker_array:{arr.pk}')
        self.assertEqual((edge['status'], edge['unlinked'], edge['match']),
                         ('inferred', False, ['matched']))
        self.assertEqual(edge['label'], "HR · 2× NL 8 75'")
        self.assertNotIn('HR', {n['label'] for n in graph['nodes']})   # the zone is no node

    def test_runs_with_no_amp_share_one_amp_rack_node(self):
        a = self.array(self.prediction(), 'Front Fill')
        b = self.array(self.prediction(file_name='b.pdf'), 'Delay')
        self.amp('Fill Amp')            # never matched from text
        self.text_cable(self.zone('FF'), destination='Front Fill')
        self.text_cable(self.zone('D1'), destination='Delay')
        graph = self.graph()
        racks = [n for n in graph['nodes'] if n['kind'] == 'amp_rack']
        self.assertEqual(racks, [{'id': 'amp_rack:unlinked', 'kind': 'amp_rack',
                                  'label': 'Amp rack — not linked', 'unlinked': True}])
        edges = _edges(graph, 'amp_rack:unlinked')
        self.assertEqual({e['to'] for e in edges},
                         {f'speaker_array:{a.pk}', f'speaker_array:{b.pk}'})
        for edge in edges:
            self.assertTrue(edge['unlinked'])

    def test_unknown_destination_is_an_unlinked_node_with_its_text(self):
        row = self.text_cable(self.zone('OFL'), destination='Nowhere')
        graph = self.graph()
        [edge] = _edges(graph, 'amp_rack:unlinked')
        self.assertEqual(edge['to'], f'unlinked:pa:{row.pk}:speaker')
        nodes = {n['id']: n for n in graph['nodes']}
        self.assertEqual(nodes[edge['to']]['label'], 'Nowhere')
        self.assertEqual(edge['label'], "OFL · 2× NL 4 100'")
        self.assertEqual(graph['warnings'], [])

    def test_ambiguous_destination_is_an_unlinked_edge_with_candidates(self):
        a = self.array(self.prediction(), 'Sub L')
        b = self.array(self.prediction(file_name='day2.pdf'), 'Sub L')
        amp = self.amp('Sub Amp')
        self.text_cable(self.zone('SL'), destination='Sub L', amp=amp)
        graph = self.graph()
        [edge] = _edges(graph, f'amp:{amp.pk}')
        self.assertTrue(edge['ambiguous'] and edge['unlinked'])
        self.assertEqual({c['node'] for c in edge['candidates']},
                         {f'speaker_array:{a.pk}', f'speaker_array:{b.pk}'})
        [warning] = graph['warnings']
        self.assertEqual((warning['kind'], warning['rule'], warning['edge']),
                         ('ambiguous', 'c', edge['id']))

    # -- shape, scope, cost ----------------------------------------------------

    def test_other_projects_do_not_leak_in(self):
        other = self.make_project('other show')
        theirs = self.console('Their Desk', project=other)
        box = self.device('Their Box', project=other)
        self.device_input(box, 1, self.channel(theirs, 1))
        self.p1('Their P1', project=other)
        graph = self.graph()
        ids = {n['id'] for n in graph['nodes']}
        self.assertEqual(ids, {self.desk_id, self.box_id})
        self.assertEqual(graph['edges'], [])

    def test_schema_keys(self):
        self.device_input(self.box, 1, self.channel(self.desk, 1))
        graph = self.graph()
        self.assertEqual(set(graph), {'schema', 'project', 'nodes', 'edges', 'warnings'})
        self.assertEqual(graph['schema'], 1)
        self.assertEqual(set(graph['edges'][0]),
                         {'id', 'from', 'to', 'label', 'transports', 'network', 'status',
                          'unlinked', 'cable', 'links', 'sources'})
        self.assertEqual(set(graph['edges'][0]['links'][0]),
                         {'transport', 'from_port', 'from_ref', 'to_port', 'to_ref'})

    def test_query_count_does_not_grow_with_the_project(self):
        ContentType.objects.clear_cache()
        project_graph(self.project)   # warm the content-type cache

        def build(project, size):
            desk = self.console('Desk', project=project)
            box = self.device('Box', project=project)
            proc = self.p1('Proc', project=project)
            amp = self.amp('Amp', project=project)
            for n in range(1, size + 1):
                self.device_input(box, n, self.channel(desk, n))
                self.device_output(box, n, f'Feed {n}')
            self.p1_in(proc, 'AES', 1, 'Feed 1')
            self.p1_out(proc, 'AVB', 1, 'Out 1')
            self.amp_channel(amp, 1, avb_stream='AVB 1 - Out 1')
            self.text_cable(self.zone('Z', project=project), destination='Arr',
                            project=project)

        small, big = self.make_project('small'), self.make_project('big')
        build(small, 1)
        build(big, 20)
        counts = []
        for project in (small, big):
            with CaptureQueriesContext(connection) as ctx:
                project_graph(project)
            counts.append(len(ctx))
        self.assertEqual(counts[0], counts[1])
