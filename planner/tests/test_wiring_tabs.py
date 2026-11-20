"""Wiring Diagram tabs: Device.console_connection, and the Overview / Dante /
Analog signal flow / Speaker cables views of one project graph.

Run with::

    python manage.py test planner.tests.test_wiring_tabs \\
        --settings=audiopatch.test_settings
"""
import xml.etree.ElementTree as ET

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.connections import layout as L
from planner.connections import svg
from planner.connections import tabs as T
from planner.connections.graph import project_graph
from planner.models import (ConsoleAuxOutput, Device, PAFanOut, PAFanOutExtension, Project,
                            ProjectMember)
from planner.tests.connection_fixtures import ConnectionFixtures
from planner.tests.test_device_patch_link import PatchLinkBase, page_form_data
from planner.tests.test_wiring_view import svg_of

SVG_NS = '{http://www.w3.org/2000/svg}'
NAME = '<img src=x onerror=alert(1)>'


class TabShow(ConnectionFixtures):
    """A Dante box, a MADI box and one with no Console connection set, a
    processor path into an amp, and a PA run with a fan-out extension."""

    def setUp(self):
        super().setUp()
        self.desk = self.console('FOH Desk', primary_ip_address='10.0.0.1',
                                 secondary_ip_address='10.0.1.1')
        self.dante = self.connected(self.device('Dante Box'), 'dante',
                                    primary_ip_address='10.0.0.20')
        self.device_input(self.dante, 1, self.channel(self.desk, 1, 'Kick'))
        aux = ConsoleAuxOutput.objects.create(console=self.desk, aux_number='1', name='Wedge 1')
        self.device_output(self.dante, 1, 'Wedge 1', bus=aux)
        self.madi = self.connected(self.device('MADI Box'), 'madi')
        self.device_input(self.madi, 1, self.channel(self.desk, 2, 'Snare'))
        self.plain = self.device('Plain Box')
        self.device_input(self.plain, 1, self.channel(self.desk, 3, 'Tom'))
        self.spare = self.connected(self.device('Spare Dante'), 'dante')     # no links yet
        # Plain Box -> SL P1 -> amp, on AES; the processor also sends AVB
        self.sl = self.p1('SL P1')
        self.p1_in(self.sl, 'AES', 1, 'Main L')
        self.device_output(self.plain, 2, 'Main L')
        self.p1_out(self.sl, 'AES', 1, 'Main L')
        self.p1_out(self.sl, 'AVB', 1, 'Main L')
        self.amp_ = self.amp('SL Amp')
        self.amp_channel(self.amp_, 1, aes_input='Main L', avb_stream='AVB 1 - Main L')
        # Amp -> array, with a fan-out and its extension; and an uncabled array
        self.k2 = self.array(self.prediction(), 'K2 L')
        self.array(self.prediction(file_name='b.pdf'), 'K2 R')
        row = self.linked_cable(self.amp_, self.k2, label=self.zone('HL'), count=2, length=100)
        fan = PAFanOut.objects.create(cable_schedule=row, fan_out_type='NL4_Y', quantity=2)
        PAFanOutExtension.objects.create(cable_schedule=row, fan_out=fan, extension_cable='NL4',
                                         extension_length=25, quantity=1)

    def connected(self, device, connection, **ips):
        Device.objects.filter(pk=device.pk).update(console_connection=connection, **ips)
        device.refresh_from_db()
        return device

    def ids(self):
        return {name: f'device:{d.pk}' for name, d in (
            ('dante', self.dante), ('madi', self.madi), ('plain', self.plain),
            ('spare', self.spare))} | {'desk': f'console:{self.desk.pk}',
                                       'sl': f'processor:{self.sl.pk}',
                                       'amp': f'amp:{self.amp_.pk}',
                                       'k2': f'speaker_array:{self.k2.pk}'}

    def tab(self, tab):
        self.full = project_graph(self.project)
        self.graph = T.graph_view(self.full, tab)
        self.lay = L.layout(self.graph, **T.layout_options(tab))
        self.boxes = {b.id: b for b in self.lay.boxes}
        return self.graph

    def nodes(self):
        return {n['id'] for n in self.graph['nodes']}

    def titles(self):
        return [title for title, _, _ in self.lay.columns]


class ConsoleConnectionGraphTests(TabShow, TestCase):

    def edges_between(self, a, b):
        return [e for e in project_graph(self.project)['edges']
                if {e['from'], e['to']} == {a, b}]

    def test_dante_console_links_are_network_feeds_with_no_cable(self):
        ids = self.ids()
        edges = self.edges_between(ids['dante'], ids['desk'])
        self.assertEqual(len(edges), 2)                     # input -> channel, aux -> output
        for edge in edges:
            self.assertEqual((edge['transports'], edge['network'], edge['cable']),
                             (['dante'], True, None))

    def test_madi_console_links_are_cables(self):
        [edge] = self.edges_between(self.ids()['madi'], self.ids()['desk'])
        self.assertEqual((edge['transports'], edge['network'], edge['cable']),
                         (['madi'], False, {'recorded': False}))

    def test_a_device_with_no_connection_set_is_as_before(self):
        [edge] = self.edges_between(self.ids()['plain'], self.ids()['desk'])
        self.assertEqual((edge['transports'], edge['network'], edge['cable']),
                         ([], False, {'recorded': False}))

    def test_the_overview_draws_dante_links_as_network_lines(self):
        self.tab(T.OVERVIEW)
        ids = self.ids()
        routes = [r for r in self.lay.routes if {r.from_node, r.to_node} == {ids['dante'], ids['desk']}]
        self.assertEqual(len(routes), 2)
        for route in routes:
            self.assertIn('network', route.classes)

    def test_a_fan_out_extension_is_in_the_run_label(self):
        [edge] = self.edges_between(self.ids()['amp'], self.ids()['k2'])
        self.assertEqual(edge['label'], "HL · 2× NL 4 100' · NL4 Y ×2 +NL4 25' ×1")

    def test_project_duplication_keeps_the_connection(self):
        copy = self.project.duplicate('Copy')
        self.assertEqual(Device.objects.get(project=copy, name='Dante Box').console_connection,
                         'dante')
        self.assertEqual(Device.objects.get(project=copy, name='Plain Box').console_connection, '')


class OverviewTabTests(TabShow, TestCase):

    def test_the_overview_is_the_whole_graph(self):
        full = project_graph(self.project)
        self.assertIs(T.graph_view(full, T.OVERVIEW), full)
        self.assertIs(T.graph_view(full, 'nonsense'), full)
        self.assertEqual(T.tab_or_default('nonsense'), T.OVERVIEW)
        self.assertEqual(T.tab_or_default(None), T.OVERVIEW)


class DanteTabTests(TabShow, TestCase):

    def setUp(self):
        super().setUp()
        self.tab(T.DANTE)
        self.id = self.ids()

    def test_only_consoles_and_dante_devices_and_their_console_links(self):
        self.assertEqual(self.nodes(), {self.id['desk'], self.id['dante'], self.id['spare']})
        self.assertEqual(len(self.graph['edges']), 2)
        for edge in self.graph['edges']:
            self.assertTrue(T.is_console_link(edge))
            self.assertEqual(edge['transports'], ['dante'])

    def test_a_dante_device_with_no_link_yet_is_shown(self):
        self.assertIn(f"{self.id['spare']}#in", self.boxes)

    def test_boxes_show_the_ip_address_managers_ips(self):
        desk = self.boxes[self.id['desk']]
        self.assertEqual(desk.lines, ['Pri 10.0.0.1 · Sec 10.0.1.1'])
        self.assertEqual(self.boxes[f"{self.id['dante']}#in"].lines, ['Pri 10.0.0.20'])
        self.assertEqual(self.boxes[f"{self.id['spare']}#in"].lines, ['No IP'])
        self.assertEqual(desk.head, L.HEAD + L.LINE_H)
        texts = [t.text for t in ET.fromstring(svg.render(self.lay)).iter(f'{SVG_NS}text')]
        self.assertIn('Pri 10.0.0.1 · Sec 10.0.1.1', texts)

    def test_only_the_columns_it_uses(self):
        self.assertEqual(self.titles(), ['I/O inputs', 'Console', 'I/O outputs'])
        last = max(x for _, x, _ in self.lay.columns)
        self.assertEqual(self.lay.width, last + L.BOX_W + L.MARGIN)

    def test_each_device_gets_only_the_sides_it_uses(self):
        # MADI and Plain Box are not here; Dante Box uses both sides.
        self.assertIn(f"{self.id['dante']}#in", self.boxes)
        self.assertIn(f"{self.id['dante']}#out", self.boxes)


class AnalogTabTests(TabShow, TestCase):

    def setUp(self):
        super().setUp()
        self.tab(T.ANALOG)
        self.id = self.ids()

    def test_no_avb_dante_or_speaker_edges(self):
        for edge in self.graph['edges']:
            self.assertFalse({'avb', 'dante', 'speaker'} & set(edge['transports']), edge)
        self.assertNotIn(self.id['dante'], self.nodes())
        self.assertNotIn(self.id['k2'], self.nodes())

    def test_madi_and_unset_console_links_are_kept(self):
        links = {e['from']: e for e in self.graph['edges'] if T.is_console_link(e)}
        self.assertEqual(set(links), {self.id['madi'], self.id['plain']})
        self.assertNotIn('connection_unset', links[self.id['madi']])
        self.assertTrue(links[self.id['plain']]['connection_unset'])

    def test_an_unset_link_has_its_own_style_and_label(self):
        [route] = [r for r in self.lay.routes if r.from_node == self.id['plain']
                   and r.to_node == self.id['desk']]
        self.assertIn('unset', route.classes)
        self.assertEqual(route.label, 'In 1 → Ch 3 · connection not set')
        [madi] = [r for r in self.lay.routes if r.from_node == self.id['madi']]
        self.assertNotIn('unset', madi.classes)
        self.assertNotIn('not set', madi.label)

    def test_the_processor_path_is_kept_and_amps_lose_their_avb_slots(self):
        froms = {(e['from'], e['to']) for e in self.graph['edges']}
        self.assertIn((self.id['plain'], self.id['sl']), froms)
        self.assertIn((self.id['sl'], self.id['amp']), froms)
        self.assertEqual(self.boxes[self.id['amp']].slots, ['AES 1'])

    def test_the_overview_still_has_the_avb_slot(self):
        self.tab(T.OVERVIEW)
        self.assertEqual(self.boxes[self.id['amp']].slots, ['AVB 1', 'AES 1'])

    def test_only_used_columns_and_nothing_left_undrawn(self):
        self.assertNotIn('Speakers', self.titles())
        self.assertEqual(self.lay.not_drawn, [])


class SpeakerTabTests(TabShow, TestCase):

    def setUp(self):
        super().setUp()
        self.tab(T.SPEAKERS)
        self.id = self.ids()

    def test_only_pa_cable_runs(self):
        self.assertTrue(self.graph['edges'])
        for edge in self.graph['edges']:
            self.assertEqual(edge['transports'], ['speaker'])
        kinds = {n['kind'] for n in self.graph['nodes']}
        self.assertLessEqual(kinds, {'amp', 'amp_location', 'amp_rack', 'speaker_array',
                                     'destination', 'unlinked'})
        self.assertEqual(self.titles(), ['Amps', 'Speakers'])

    def test_an_uncabled_array_is_not_shown(self):
        self.assertNotIn('K2 R', {b.label for b in self.lay.boxes})

    def test_the_label_carries_the_whole_cable_unclipped(self):
        [route] = [r for r in self.lay.routes if r.to_node == self.id['k2']]
        self.assertEqual(route.label, "HL · 2× NL 4 100' · NL4 Y ×2 +NL4 25' ×1")
        self.assertEqual(route.label, route.label_full)


class TabsAreLaidOutAloneTests(TabShow, TestCase):

    def test_each_tab_is_laid_out_from_its_own_graph(self):
        for tab in T.TAB_KEYS:
            self.tab(tab)
            alone = L.layout(T.graph_view(project_graph(self.project), tab), **T.layout_options(tab))
            self.assertEqual([(b.id, b.x, b.y, b.h) for b in alone.boxes],
                             [(b.id, b.x, b.y, b.h) for b in self.lay.boxes], tab)
            drawn = {e['id'] for e in self.graph['edges']}
            self.assertLessEqual({r.id for r in self.lay.routes}, drawn, tab)
            self.assertLessEqual({w['edge'] for w in self.graph['warnings']}, drawn, tab)

    def test_the_dante_tab_starts_at_the_top_whatever_the_overview_holds(self):
        self.tab(T.DANTE)
        top = L.MARGIN + L.TITLE_H
        self.assertEqual(min(b.y for b in self.lay.boxes), top)

    def test_warnings_are_per_tab(self):
        # An output two processors could take: an ambiguous rule (a) match.
        sr = self.p1('SR P1')
        self.p1_in(self.sl, 'AES', 2, 'Delay')
        self.p1_in(sr, 'AES', 1, 'Delay')
        self.device_output(self.plain, 3, 'Delay')
        full = project_graph(self.project)
        self.assertEqual(len(full['warnings']), 1)
        self.assertEqual(len(T.graph_view(full, T.ANALOG)['warnings']), 1)
        self.assertEqual(T.graph_view(full, T.DANTE)['warnings'], [])
        self.assertEqual(T.graph_view(full, T.SPEAKERS)['warnings'], [])


class WiringTabViewTests(TabShow, TestCase):
    url = reverse('planner:wiring_diagram')

    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()

    def get(self, view=None, user=None):
        self.client.force_login(user or self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        return self.client.get(self.url, {'view': view} if view else {})

    def active(self, response):
        return [t['key'] for t in response.context['tabs'] if t['active']]

    def test_every_tab_opens_and_marks_itself(self):
        for tab in T.TAB_KEYS:
            response = self.get(tab)
            self.assertEqual(response.status_code, 200, tab)
            self.assertEqual(self.active(response), [tab])
            self.assertContains(response, f'href="?view={tab}" aria-current="page"')

    def test_an_unknown_view_is_the_overview(self):
        self.assertEqual(self.active(self.get('<script>')), [T.OVERVIEW])
        self.assertEqual(self.active(self.get()), [T.OVERVIEW])

    def test_every_project_role_can_open_every_tab(self):
        users = [self.user]
        for name, role in (('ed', 'editor'), ('vi', 'viewer')):
            user = User.objects.create_user(name, password='pw', is_staff=True)
            ProjectMember.objects.create(user=user, project=self.project, role=role,
                                         invited_by=self.user)
            users.append(user)
        for user in users:
            for tab in T.TAB_KEYS:
                self.assertEqual(self.get(tab, user).status_code, 200, (user, tab))

    def test_the_banner_lists_unset_devices_on_dante_and_analog_only(self):
        link = reverse('admin:planner_device_change', args=[self.plain.pk])
        for tab in (T.DANTE, T.ANALOG):
            response = self.get(tab)
            self.assertEqual([d['name'] for d in response.context['unset']], ['Plain Box'])
            self.assertContains(response, '1 I/O device has no Console connection set')
            self.assertContains(response, f'<a href="{link}">Plain Box</a>', html=True)
        for tab in (T.OVERVIEW, T.SPEAKERS):
            response = self.get(tab)
            self.assertEqual(response.context['unset'], [])
            self.assertNotContains(response, 'no Console connection set')

    def test_the_banner_counts_several_and_goes_when_all_are_set(self):
        other = self.device('Other Box')
        self.assertContains(self.get(T.ANALOG), '2 I/O devices have no Console connection set')
        Device.objects.filter(pk__in=[self.plain.pk, other.pk]).update(console_connection='analog')
        self.assertNotContains(self.get(T.ANALOG), 'no Console connection set')

    def test_the_analog_legend_shows_the_unset_style(self):
        self.assertContains(self.get(T.ANALOG), 'Console connection not set')
        self.assertNotContains(self.get(T.SPEAKERS), 'Console connection not set')

    def test_a_tab_with_nothing_says_why(self):
        empty = Project.objects.create(name='Small show', owner=self.user)
        self.device('Lonely Box', project=empty)
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = empty.pk
        session.save()
        response = self.client.get(self.url, {'view': T.SPEAKERS})
        self.assertContains(response, 'No PA cable runs yet')
        self.assertIsNone(svg_of(response))

    def test_names_and_ips_are_escaped_on_the_dante_tab(self):
        Device.objects.filter(pk=self.dante.pk).update(name=NAME)
        Device.objects.filter(pk=self.plain.pk).update(name=NAME)
        response = self.get(T.DANTE)
        body = response.content.decode()
        self.assertNotIn('<img src=x', body)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', body)
        root = ET.fromstring(svg_of(response))
        self.assertIn(NAME, {t.text for t in root.iter(f'{SVG_NS}title')})
        self.assertIn('Pri 10.0.0.20', {t.text for t in root.iter(f'{SVG_NS}text')})


class DevicePageConsoleConnectionTests(PatchLinkBase):

    def test_the_device_page_edits_it(self):
        html = self.client.get(self.url()).content.decode()
        self.assertIn('name="console_connection"', html)
        data = page_form_data(html)
        data['console_connection'] = 'twinlane'
        response = self.client.post(self.url(), data)
        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.box.refresh_from_db()
        self.assertEqual(self.box.console_connection, 'twinlane')

    def test_a_viewer_cannot_change_it(self):
        viewer = User.objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.client.force_login(viewer)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('name="console_connection"', response.content.decode())
        self.client.post(self.url(), {'console_connection': 'dante'})
        self.box.refresh_from_db()
        self.assertEqual(self.box.console_connection, '')
