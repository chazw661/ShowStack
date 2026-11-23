"""Wiring Diagram DXF (Download DXF) and the download panel's defaults.

Every file is read back with ezdxf: what is asserted is what a CAD program
would be handed. B input links in the DXF are in test_wiring_b_links.py.

    python manage.py test planner.tests.test_wiring_dxf --settings=audiopatch.test_settings
"""
import io
import re
import zipfile
from datetime import date

import ezdxf
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from planner.connections import dxf
from planner.connections import layout as L
from planner.connections import tabs as T
from planner.connections.graph import digest, project_graph
from planner.models import ConsoleAuxOutput, ProjectMember
from planner.tests.test_comm_devices import PLAIN_STATIC
from planner.tests.test_comms_tab import CommsShow
from planner.tests.test_wiring_layout import WiringShow
from planner.utils.pdf_exports import wiring_pdf
from planner.views_wiring import (MANY_PAGES, download_hints, file_part, suggestion_text,
                                  tab_view)

NAME = '<img src=x onerror=alert(1)>'
QUOTED = '"\'><b>&amp; ]]> Łódź'
TAB_FILES = ('Overview', 'Dante', 'Analogue-AES', 'Speaker cables', 'Comms')
EDGE_LAYERS = (dxf.CONFIRMED, dxf.INFERRED, dxf.UNLINKED, dxf.NETWORK, dxf.SPEAKER, dxf.COMMS)


def read(data):
    """The drawing, which must also pass ezdxf's audit untouched."""
    doc = ezdxf.read(io.StringIO(data.decode('utf-8')))
    auditor = doc.audit()
    assert not auditor.errors and not auditor.fixes, (auditor.errors, auditor.fixes)
    return doc


def texts(doc, layer=None):
    return [e.plain_text() for e in doc.modelspace().query('TEXT')
            if layer is None or e.dxf.layer == layer]


def squash(text):
    return re.sub(r'\s+', '', text)


def lines_of(doc, layers=EDGE_LAYERS):
    return [e for e in doc.modelspace().query('LWPOLYLINE')
            if not e.closed and e.dxf.layer in layers]


class DxfMixin:
    dxf_url = reverse('planner:wiring_diagram_dxf')

    def login(self, user=None):
        self.client.force_login(user or self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def get(self, **params):
        self.login()
        return self.client.get(self.dxf_url, params)

    def dxf(self, tab, **params):
        response = self.get(tabs=tab, **params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/vnd.dxf')
        return read(response.content)

    def tab(self, tab, network=False):
        return tab_view(self.project, project_graph(self.project), tab, network)


# -- the text sanitiser -----------------------------------------------------------------

class CleanTests(SimpleTestCase):
    def test_control_characters_never_reach_the_file(self):
        self.assertEqual(dxf.clean('a\x00b\x1bc\x7fd\x9fe'), 'abcde')
        self.assertEqual(dxf.clean('one\ntwo\r\nthree\tfour\u2028five'), 'one two three four five')
        self.assertEqual(dxf.clean('  0\nSECTION\n  2\nENTITIES'), '0 SECTION 2 ENTITIES')
        self.assertEqual(dxf.clean('x\ud800y\ufffez\u202eabc'), 'xyzabc')
        self.assertEqual(dxf.clean(None), '')
        self.assertEqual(dxf.clean(12), '12')

    def test_names_keep_their_letters(self):
        for text in ('Łódź', 'ễ 日本 🎤', NAME, QUOTED, 'In 1–2 → Ch 2–3 (B) · Kick', '100% wet'):
            self.assertEqual(dxf.clean(text), text)
        self.assertEqual(dxf.clean('e\u0302\u0303'), 'ễ')              # NFC

    def test_arrows_as_ascii_on_request(self):
        self.assertEqual(dxf.clean('XLR 1 ← Y001 → amp', dxf.ARROWS_ASCII), 'XLR 1 <- Y001 -> amp')
        self.assertEqual(dxf.clean('XLR 1 ← Y001 → amp'), 'XLR 1 ← Y001 → amp')

    def test_a_long_text_is_capped(self):
        self.assertEqual(len(dxf.clean('x' * 5000)), dxf.MAX_TEXT)

    def test_control_codes_read_back_as_typed(self):
        """"%%u" would underline and "^J" break the line in a CAD program;
        written escaped, ezdxf (as they do) reads them back literally."""
        hostile = ['50%%d %%u under %%c', '%%%', '%%%%', '^I ^J ^M^^.', 'x%%128y', '100%',
                   '\\P new {\\fArial;x} \\U+0041', '%%^%%']
        doc = ezdxf.new(dxf.DXF_VERSION)
        for i, text in enumerate(hostile):
            doc.modelspace().add_text(dxf.clean(text), height=1).set_placement((0, i))
        stream = io.StringIO()
        doc.write(stream)
        back = ezdxf.read(io.StringIO(stream.getvalue()))
        self.assertEqual([e.plain_text() for e in back.modelspace().query('TEXT')], hostile)
        self.assertEqual(dxf.clean('a^'), 'a^ ')        # "^ " is the format's literal caret


class RulesTests(SimpleTestCase):
    def test_the_kind_of_link_wins_the_layer_then_how_sure_it_is(self):
        speaker = {'transports': ['speaker']}
        self.assertEqual(dxf.edge_layer(T.OVERVIEW, ('confirmed',), {}), dxf.CONFIRMED)
        self.assertEqual(dxf.edge_layer(T.OVERVIEW, ('inferred',), {}), dxf.INFERRED)
        self.assertEqual(dxf.edge_layer(T.OVERVIEW, ('unlinked', 'ambiguous'), {}), dxf.UNLINKED)
        self.assertEqual(dxf.edge_layer(T.OVERVIEW, ('inferred', 'network'), {}), dxf.NETWORK)
        self.assertEqual(dxf.edge_layer(T.SPEAKERS, ('unlinked',), speaker), dxf.SPEAKER)
        self.assertEqual(dxf.edge_layer(T.COMMS, ('confirmed', 'network'), {}), dxf.COMMS)
        self.assertEqual(dxf.edge_layer(T.OVERVIEW, ('confirmed', 'unset'), {}), dxf.CONFIRMED)
        self.assertEqual(dxf.edge_layer(T.OVERVIEW, ('confirmed',), None), dxf.CONFIRMED)

    def test_linetypes_follow_the_screen(self):
        self.assertEqual(dxf.edge_linetype(('confirmed',)), 'CONTINUOUS')
        self.assertEqual(dxf.edge_linetype(('inferred',)), 'DASHED')
        self.assertEqual(dxf.edge_linetype(('unlinked', 'ambiguous')), 'DASHED')
        self.assertEqual(dxf.edge_linetype(('inferred', 'network')), 'DOT')
        self.assertEqual(dxf.edge_linetype(('confirmed', 'unset')), 'DOT')

    def test_file_names_cannot_leave_their_folder(self):
        self.assertEqual(file_part('Analogue/AES'), 'Analogue-AES')
        self.assertEqual(file_part('../../etc/passwd'), 'etc-passwd')
        self.assertEqual(file_part('..\\..\\x:y*?"<>|\x00\n'), 'x-y')
        self.assertEqual(file_part(' . '), 'project')
        self.assertEqual(file_part(''), 'project')
        self.assertLessEqual(len(file_part('n' * 500)), 80)


# -- one tab, one drawing -----------------------------------------------------------------

class WiringDxfTests(DxfMixin, WiringShow, TestCase):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()

    def test_one_tab_is_one_dxf_file(self):
        response = self.get(tabs='speakers')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/vnd.dxf')
        self.assertIn(f'Wiring Diagram - wiring show - Speaker cables - {date.today().isoformat()}.dxf',
                      response['Content-Disposition'])
        doc = read(response.content)
        self.assertEqual(doc.dxfversion, 'AC1024')

    def test_more_than_one_tab_is_a_zip_with_a_file_each(self):
        response = self.get(tabs='overview,speakers')
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('.zip', response['Content-Disposition'])
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        today = date.today().isoformat()
        self.assertEqual(archive.namelist(), [
            f'Wiring Diagram - wiring show - Overview - {today}.dxf',
            f'Wiring Diagram - wiring show - Speaker cables - {today}.dxf'])
        for name in archive.namelist():
            doc = read(archive.read(name))
            self.assertIn(self.project.name, texts(doc, dxf.TITLE))

    def test_no_tab_named_is_every_tab_in_page_order(self):
        for params in ({}, {'tabs': 'nonsense'}):
            archive = zipfile.ZipFile(io.BytesIO(self.get(**params).content))
            today = date.today().isoformat()
            self.assertEqual(archive.namelist(),
                             [f'Wiring Diagram - wiring show - {tab} - {today}.dxf' for tab in TAB_FILES])
            self.assertIsNone(archive.testzip())
            labels = dict(T.TABS)
            for name, key in zip(archive.namelist(), T.TAB_KEYS):
                doc = read(archive.read(name))
                self.assertIn(f'Wiring Diagram: {labels[key]}', texts(doc, dxf.TITLE), name)

    def test_units_layers_linetypes_and_fonts(self):
        doc = self.dxf('overview')
        self.assertEqual(doc.header['$INSUNITS'], 1)                    # inches
        self.assertEqual(doc.header['$MEASUREMENT'], 0)
        for name in ('WD-BOXES', 'WD-TEXT', 'WD-CONFIRMED', 'WD-INFERRED', 'WD-UNLINKED',
                     'WD-NETWORK', 'WD-SPEAKER', 'WD-COMMS', 'WD-TABLE', 'WD-TITLE'):
            self.assertTrue(doc.layers.has_entry(name), name)
        for name in ('CONTINUOUS', 'DASHED', 'DOT'):
            self.assertTrue(doc.linetypes.has_entry(name), name)
        self.assertEqual(doc.styles.get('Arial').dxf.font, 'arial.ttf')
        self.assertEqual(doc.styles.get('Arial-Bold').dxf.font, 'arialbd.ttf')
        self.assertEqual(doc.styles.get('Arial').get_extended_font_data()[0], 'Arial')
        # Nothing drawn off the WD- layers, and all text is real TEXT in Arial.
        kinds = {e.dxftype() for e in doc.modelspace()}
        self.assertEqual(kinds, {'TEXT', 'LWPOLYLINE', 'LINE', 'SOLID'})
        for e in doc.modelspace():
            self.assertTrue(e.dxf.layer.startswith('WD-'), e.dxf.layer)
        self.assertEqual({e.dxf.style for e in doc.modelspace().query('TEXT')},
                         {'Arial', 'Arial-Bold'})

    def test_ten_point_text_is_an_eighth_of_an_inch_and_a_box_keeps_its_shape(self):
        doc = self.dxf('overview')
        view = self.tab(T.OVERVIEW)
        slot = 'XLR 1 ← Stage Box Out 3 (Fill)'
        self.assertIn([slot], [lines for box in view['layout'].boxes for lines in box.slot_lines])
        [entity] = [e for e in doc.modelspace().query('TEXT') if e.plain_text() == slot]
        self.assertAlmostEqual(entity.dxf.height, 0.125, places=4)
        box = next(e for e in doc.modelspace().query('LWPOLYLINE')
                   if e.closed and e.dxf.layer == dxf.BOXES)
        xs = [p[0] for p in box.get_points('xy')]
        self.assertAlmostEqual(max(xs) - min(xs), L.BOX_W * dxf.UNIT, places=3)
        self.assertAlmostEqual(L.BOX_W * dxf.UNIT, 3.49, places=2)
        self.assertIn(dxf.scale_text(), texts(doc, dxf.TITLE))

    def test_entity_counts_per_tab(self):
        for tab in T.TAB_KEYS:
            if tab == T.COMMS:
                continue                    # no comm device in this show: CommsDxfTests
            view = self.tab(tab, network=True)
            lay = view['layout']
            doc = self.dxf(tab, network='1')
            msp = doc.modelspace()
            closed = [e for e in msp.query('LWPOLYLINE') if e.closed]
            self.assertEqual(sum(e.dxf.layer == dxf.BOXES for e in closed), len(lay.boxes), tab)
            self.assertEqual(sum(e.dxf.layer == dxf.TEXT for e in closed), len(lay.keys), tab)
            self.assertEqual(len(lines_of(doc)), len(lay.routes), tab)
            self.assertEqual(len(msp.query('SOLID')), len(lay.routes), tab)
            if tab in (T.OVERVIEW, T.SPEAKERS):
                self.assertTrue(lay.routes, tab)
            # every arrowhead is on its line's layer, at the line's end
            ends = sorted((e.dxf.layer, tuple(round(float(v), 4) for v in e.get_points('xy')[-1]))
                          for e in lines_of(doc))
            heads = sorted((e.dxf.layer, (round(e.dxf.vtx0.x, 4), round(e.dxf.vtx0.y, 4)))
                           for e in msp.query('SOLID'))
            self.assertEqual(ends, heads, tab)
            # group rules: one per group header
            rules = [e for e in msp.query('LINE') if e.dxf.layer == dxf.BOXES]
            self.assertEqual(len(rules), len(lay.groups), tab)

    def test_lines_are_on_the_layer_and_linetype_of_their_link(self):
        self.p1_out(self.sl, 'AVB', 2, 'Delay')
        self.amp_channel(self.sl_amp, 2, avb_stream='AVB 2 - Delay')
        view = self.tab(T.OVERVIEW, network=True)
        edges = {e['id']: e for e in view['graph']['edges']}
        doc = self.dxf('overview', network='1')
        got = sorted((e.dxf.layer, e.dxf.linetype.upper()) for e in lines_of(doc))
        want = sorted((dxf.edge_layer(T.OVERVIEW, r.classes, edges[r.id]), dxf.edge_linetype(r.classes))
                      for r in view['layout'].routes)
        self.assertEqual(got, want)
        layers = {layer for layer, _ in got}
        for layer in (dxf.CONFIRMED, dxf.INFERRED, dxf.UNLINKED, dxf.NETWORK, dxf.SPEAKER):
            self.assertIn(layer, layers)
        self.assertIn((dxf.NETWORK, 'DOT'), got)
        self.assertIn((dxf.CONFIRMED, 'CONTINUOUS'), got)
        self.assertIn((dxf.INFERRED, 'DASHED'), got)
        # the speaker run that matched no array: its layer says speaker, its dashes "?"
        self.assertIn((dxf.SPEAKER, 'DASHED'), got)
        self.assertIn((dxf.SPEAKER, 'CONTINUOUS'), got)
        # an unlinked box is dashed
        dashed = [e for e in doc.modelspace().query('LWPOLYLINE')
                  if e.closed and e.dxf.layer == dxf.BOXES and e.dxf.linetype == 'DASHED']
        self.assertEqual(len(dashed), sum(b.style == 'unlinked' for b in view['layout'].boxes))
        self.assertTrue(dashed)

    def test_network_feeds_are_off_unless_asked_for(self):
        self.p1_out(self.sl, 'AVB', 2, 'Delay')
        self.amp_channel(self.sl_amp, 2, avb_stream='AVB 2 - Delay')
        on = self.dxf('overview', network='1')
        self.assertTrue(lines_of(on, (dxf.NETWORK,)))
        for params in ({}, {'network': '0'}):
            off = self.dxf('overview', **params)
            self.assertEqual(lines_of(off, (dxf.NETWORK,)), [])
            # the amp's slot still names what feeds it
            self.assertIn('AVB ← SL P1 stream 2 (Delay)', ' '.join(texts(off, dxf.TEXT)))

    def test_the_diagrams_text_is_the_layouts_text(self):
        for tab in (T.OVERVIEW, T.DANTE, T.ANALOG, T.SPEAKERS):
            view = self.tab(tab, network=True)
            lay = view['layout']
            want = []
            for title, _, _ in lay.columns:
                want.append(title.upper())
                if title in L.COLUMN_HINTS:
                    want.append(L.COLUMN_HINTS[title])
            for group in lay.groups:
                want += group.lines
            for box in lay.boxes:
                want += [line for _, line, _ in box.text_rows]
                want += [line for label, lines in zip(box.slots, box.slot_lines) if label
                         for line in lines]
            for route in lay.routes:
                want += [f'[{route.key}]'] if route.key else route.lines
            got = texts(self.dxf(tab, network='1'), dxf.TEXT)
            self.assertEqual(sorted(got), sorted(t for t in want if t.strip()), tab)
        # the boxes of the show, by name, and an arrow as text
        got = texts(self.dxf('overview'), dxf.TEXT)
        for name in ('FOH Desk', 'Stage Box', 'SL P1', 'SL Amp', 'K2 L', 'SL Racks', 'CONSOLE',
                     '(mics & sources plug in here)', 'In 1 → Ch 1'):
            self.assertIn(name, got)

    def test_the_title_block(self):
        doc = self.dxf('dante', tz='America/Los_Angeles')
        title = texts(doc, dxf.TITLE)
        self.assertEqual(title[0], 'wiring show')
        self.assertEqual(title[1], 'Wiring Diagram: Dante')
        self.assertRegex(title[2], r'^Made \w{3} \d{1,2}, \d{4} \d\d:\d\d P[SD]T · Graph '
                         + digest(project_graph(self.project)) + '$')
        self.assertEqual(title[3], dxf.scale_text())
        for label, _ in dxf.LEGEND:
            self.assertIn(label, title)
        samples = [e for e in doc.modelspace().query('LINE') if e.dxf.layer == dxf.TITLE]
        self.assertEqual([e.dxf.linetype for e in samples], ['CONTINUOUS', 'DASHED', 'DASHED', 'DOT'])
        self.assertIn(' UTC ', texts(self.dxf('dante', tz='not/a_zone'), dxf.TITLE)[2])
        # no tiling, no page markers, in any tab
        every = ' '.join(t for tab in T.TAB_KEYS for t in texts(self.dxf(tab, network='1')))
        self.assertNotRegex(every, r'p\.\d|\(continued\)|Part \d')

    def test_a_big_tab_is_still_one_whole_drawing(self):
        for i in range(60):
            box = self.device(f'Rack Box {i:02d}')
            self.device_output(box, 1, f'Feed {i:02d}')
            amp = self.amp(f'Amp {i:02d}', rack=f'Rack {i // 4}')
            self.amp_channel(amp, 1, analog_input=f'Feed {i:02d}')
        view = self.tab(T.OVERVIEW)
        self.assertGreater(wiring_pdf.diagram_pages(view['layout'], '11x17'), 1)
        doc = self.dxf('overview')
        got = texts(doc)
        for i in range(60):
            self.assertEqual(got.count(f'Amp {i:02d}'), 1)
        self.assertEqual(len(lines_of(doc)), len(view['layout'].routes))
        self.assertNotRegex(' '.join(got), r'p\.\d|\(continued\)')
        # the view it opens on holds the whole diagram
        [vport] = doc.viewports.get('*Active')
        lay = view['layout']
        cx, cy = vport.dxf.center.x, vport.dxf.center.y
        self.assertGreater(vport.dxf.height, lay.height * dxf.UNIT)
        self.assertLess(cy - vport.dxf.height / 2, -lay.height * dxf.UNIT)
        self.assertGreater(cy + vport.dxf.height / 2, 0)
        self.assertAlmostEqual(cx, lay.width * dxf.UNIT / 2, delta=1)

    def test_keys_the_connections_table_and_warnings(self):
        # every other bus to every other output: a label far too wide for a line
        for name, base in (('Far Box', 10), ('Far Box 2', 100)):
            far = self.device(name)
            for n in range(1, 50, 2):
                bus = ConsoleAuxOutput.objects.create(console=self.desk, aux_number=str(n + base),
                                                      name=f'Mix {n}')
                self.device_output(far, n, f'Mix {n}', bus=bus)
        view = self.tab(T.OVERVIEW)
        rows, warnings = view['connections'], view['warnings']
        self.assertTrue(rows)
        self.assertTrue(warnings)
        doc = self.dxf('overview')
        diagram, table = texts(doc, dxf.TEXT), texts(doc, dxf.TABLE)
        self.assertIn(f'Connections ({len(rows)}) — Overview', table)
        self.assertIn(f'Warnings ({len(warnings)}) — Overview', table)
        for head in ('Key', 'From', 'To', 'Cable / transport'):
            self.assertIn(head, table)
        joined = squash(''.join(table))
        position = 0
        for row in rows:
            key = f"[{row['key']}]"
            self.assertEqual(diagram.count(key), 1, key)        # on its line
            self.assertEqual(table.count(key), 1, key)          # and in the table
            for cell in (row['from'], row['to'], row['cable']):
                found = joined.find(squash(cell), position)
                self.assertGreaterEqual(found, 0, cell)
            position = joined.find(squash(key), position)
            self.assertGreaterEqual(position, 0, key)           # rows in key order
        for w in warnings:
            self.assertIn(squash(dxf.warning_text(w)), joined)
        # the table sits below the diagram
        lowest_box = min(p[1] for e in doc.modelspace().query('LWPOLYLINE')
                         if e.dxf.layer == dxf.BOXES for p in e.get_points('xy'))
        for e in doc.modelspace().query('TEXT'):
            if e.dxf.layer == dxf.TABLE:
                self.assertLess(e.dxf.insert.y, lowest_box)

    def test_no_warnings_says_none(self):
        project = self.project
        self.project = self.make_project('Tidy show')
        desk = self.console('Desk')
        box = self.device('Box')
        self.device_input(box, 1, self.channel(desk, 1, 'Kick'))
        table = texts(self.dxf('overview'), dxf.TABLE)
        self.assertEqual(table, ['Warnings — Overview', 'None.'])
        self.project = project

    def test_arrows_are_text_and_ascii_on_request(self):
        got = ' '.join(texts(self.dxf('overview')))
        self.assertIn('→', got)
        self.assertIn('←', got)
        plain = ' '.join(texts(self.dxf('overview', arrows='ascii')))
        self.assertNotIn('→', plain)
        self.assertNotIn('←', plain)
        self.assertIn('In 1 -> Ch 1', plain)
        self.assertIn('XLR 1 <- Stage Box Out 3 (Fill)', plain)
        self.assertEqual(got.replace('→', '->').replace('←', '<-'), plain)

    def test_hostile_names_are_text_and_the_file_still_reads(self):
        codes = '%%uUnder%%d ^J^M \\P{\\fArial;x}'
        breaker = 'Line\r\n  0\nSECTION\x00\x1b\tend'
        self.device(NAME)
        box = self.device(QUOTED)
        self.device_output(box, 1, NAME)
        self.device_output(box, 2, codes)
        self.device(codes)
        self.device(breaker)
        self.device('🎤 ễ 日本')
        self.amp_channel(self.ff_amp, 2, analog_input=NAME)
        self.amp_channel(self.ff_amp, 3, analog_input=codes)
        self.project.name = f'{NAME} ../../x\n{codes}'
        self.project.save()
        response = self.get()                           # every tab; each must audit clean
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertEqual(len(archive.namelist()), 5)
        for name in archive.namelist():
            self.assertNotIn('/', name)
            self.assertNotIn('\\', name)
            self.assertNotIn('\n', name)
            self.assertNotIn('..', name)
            data = archive.read(name)
            self.assertNotRegex(data.decode('utf-8'), r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
            read(data)
        doc = read(archive.read(archive.namelist()[0]))
        got = texts(doc)
        joined = squash(''.join(got))
        self.assertIn(squash(NAME), joined)                             # the box, as typed
        self.assertIn(squash(QUOTED), joined)
        self.assertIn('Łódź', ' '.join(got))
        self.assertIn(squash(codes), joined)                            # read back literally
        self.assertIn('Line 0 SECTION end', got)
        self.assertIn('🎤 ễ 日本', got)
        self.assertEqual(got[0], f'{NAME} ../../x {codes}')              # the title block
        # only what the drawing means to hold: nothing was smuggled in as a section
        self.assertEqual({e.dxftype() for e in doc.modelspace()}, {'TEXT', 'LWPOLYLINE', 'LINE', 'SOLID'})

    def test_a_tab_with_nothing_and_an_empty_project(self):
        doc = self.dxf('comms')
        title = texts(doc, dxf.TITLE)
        self.assertEqual(title[1], 'Wiring Diagram: Comms')
        self.assertIn('No comm device yet. Add one on the Devices page ("Add comm device").', title)
        self.assertEqual(len(doc.modelspace().query('SOLID')), 0)
        self.project = self.make_project('Empty show')
        archive = zipfile.ZipFile(io.BytesIO(self.get().content))
        self.assertEqual(len(archive.namelist()), 5)
        for name in archive.namelist():
            self.assertIn(dxf.EMPTY_PROJECT, texts(read(archive.read(name)), dxf.TITLE), name)

    def test_any_project_role_can_download_and_only_their_project(self):
        viewer = type(self.user).objects.create_user(username='viewer', password='x', is_staff=True)
        ProjectMember.objects.create(project=self.project, user=viewer, role='viewer',
                                     invited_by=self.user)
        self.login(viewer)
        self.assertEqual(self.client.get(self.dxf_url, {'tabs': 'overview'}).status_code, 200)
        other = type(self.user).objects.create_user(username='other', password='x', is_staff=True)
        self.client.force_login(other)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        response = self.client.get(self.dxf_url, {'tabs': 'overview'})
        if response.status_code == 200:
            self.assertNotIn('FOH Desk', response.content.decode('utf-8', 'replace'))
        self.client.logout()
        self.assertEqual(self.client.get(self.dxf_url).status_code, 302)

    def test_post_is_refused(self):
        self.login()
        self.assertEqual(self.client.post(self.dxf_url).status_code, 405)


@override_settings(STORAGES=PLAIN_STATIC)
class CommsDxfTests(DxfMixin, CommsShow, TestCase):
    def setUp(self):
        super().setUp()
        self.user = self.owner

    def test_the_comms_tab_has_its_file_and_runs_left_to_right(self):
        archive = zipfile.ZipFile(io.BytesIO(self.get().content))
        [name] = [n for n in archive.namelist() if ' - Comms - ' in n]
        doc = read(archive.read(name))
        view = self.tab(T.COMMS)
        lay = view['layout']
        self.assertTrue(lay.routes)
        lines = lines_of(doc)
        self.assertEqual(len(lines), len(lay.routes))
        for line in lines:
            self.assertEqual(line.dxf.layer, dxf.COMMS)
            xs = [p[0] for p in line.get_points('xy')]
            self.assertEqual(xs, sorted(xs))                    # never right to left
            self.assertGreater(xs[-1], xs[0])
        heads = doc.modelspace().query('SOLID')
        self.assertEqual(len(heads), len(lay.routes))
        self.assertEqual({e.dxf.layer for e in heads}, {dxf.COMMS})
        boxes = [e for e in doc.modelspace().query('LWPOLYLINE')
                 if e.closed and e.dxf.layer == dxf.BOXES]
        self.assertEqual(len(boxes), len(lay.boxes))
        got = texts(doc, dxf.TEXT)
        for text in ('TO COMMS', 'COMM DEVICES', 'FROM COMMS', 'Arcadia', 'Arcadia B',
                     'Wired BP chain SL', '4W 1', 'Dante Out 3'):
            self.assertIn(text, got)
        self.assertIn(squash('Out 5 ← FOH Aux 12 (Program)'), squash(''.join(got)))
        self.assertIn('Wiring Diagram: Comms', texts(doc, dxf.TITLE))

    def test_the_other_tabs_list_comms_links_in_their_table(self):
        doc = self.dxf('overview', network='1')
        table = texts(doc, dxf.TABLE)
        rows = [r for r in self.tab(T.OVERVIEW, True)['connections'] if str(r['key']).startswith('C')]
        self.assertTrue(rows)
        for row in rows:
            self.assertIn(f"[{row['key']}]", table)
        self.assertIn(squash('see the Comms tab'), squash(''.join(table)))
        self.assertTrue(any('see Comms tab' in t for t in texts(doc, dxf.TEXT)))   # the box's note


# -- the download panel ---------------------------------------------------------------------

class DownloadPanelTests(DxfMixin, WiringShow, TestCase):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()
        self.login()

    def page(self, **params):
        return self.client.get(reverse('planner:wiring_diagram'), params).content.decode()

    def big(self, n=60):
        for i in range(n):
            box = self.device(f'Rack Box {i:02d}')
            self.device_output(box, 1, f'Feed {i:02d}')
            amp = self.amp(f'Amp {i:02d}', rack=f'Rack {i // 4}')
            self.amp_channel(amp, 1, analog_input=f'Feed {i:02d}')

    def test_both_downloads_and_network_feeds_off_by_default(self):
        page = self.page()
        self.assertIn('<summary class="wd-toggle">Download</summary>', page)
        self.assertRegex(page, r'<button type="submit" class="wd-toggle">Download PDF</button>')
        self.assertIn(f'formaction="{reverse("planner:wiring_diagram_dxf")}">Download DXF</button>', page)
        self.assertIn('<input type="checkbox" name="network" value="1">', page)
        self.assertNotRegex(page, r'name="network"[^>]*checked')
        for key in T.TAB_KEYS:
            self.assertRegex(page, rf'name="tabs" value="{key}"[^>]* checked>')

    def test_the_screens_own_network_toggle_is_unchanged(self):
        self.p1_out(self.sl, 'AVB', 2, 'Delay')
        self.amp_channel(self.sl_amp, 2, avb_stream='AVB 2 - Delay')
        page = self.page()
        self.assertIn('role="switch" aria-checked="true"', page)        # on until switched off
        self.assertIn('wd-edge inferred network', page)
        self.assertNotIn('wd-edge inferred network', self.page(network='0'))

    def test_each_tab_shows_its_diagram_pages_from_the_tiling_plan(self):
        hints = download_hints(project_graph(self.project))
        page = self.page()
        for tab in (T.OVERVIEW, T.DANTE, T.ANALOG, T.SPEAKERS):
            counts = dict(hints['tabs'][tab]['counts'])
            self.assertEqual(sorted(counts), ['11x17-0', '11x17-1', '24x36-0', '24x36-1'])
            for network in (0, 1):
                lay = self.tab(tab, bool(network))['layout']
                for paper in ('11x17', '24x36'):
                    self.assertEqual(counts[f'{paper}-{network}'], wiring_pdf.diagram_pages(lay, paper))
            self.assertEqual(hints['tabs'][tab]['text'], '1 diagram page')
            self.assertRegex(page, rf'value="{tab}"[^>]*> [^<]+ <span class="wd-pages"'
                                   r' data-p-11x17-0="1" data-p-24x36-0="1" data-p-11x17-1="1"'
                                   r' data-p-24x36-1="1">· 1 diagram page</span>')
        # no comm device: nothing to draw, and no page promised
        self.assertEqual(hints['tabs'][T.COMMS]['text'], 'nothing to draw')
        self.assertEqual(set(dict(hints['tabs'][T.COMMS]['counts']).values()), {0})
        self.assertEqual(hints['suggestion'], '')
        self.assertIn('<p class="wd-pdf-hint" id="wd-pdf-hint" role="status"></p>', page)

    def test_the_hint_is_the_pdfs_own_tile_count(self):
        self.big()
        hints = download_hints(project_graph(self.project))
        counts = dict(hints['tabs'][T.OVERVIEW]['counts'])
        self.assertGreater(counts['11x17-0'], 1)
        self.client.get(reverse('planner:wiring_diagram'))
        views = [self.tab(T.OVERVIEW)]
        plans = wiring_pdf.plans_for(views, wiring_pdf.PAPER['11x17'])
        self.assertEqual(counts['11x17-0'], len(plans[T.OVERVIEW][0].tiles))
        plans = wiring_pdf.plans_for(views, wiring_pdf.PAPER['24x36'])
        self.assertEqual(counts['24x36-0'], len(plans[T.OVERVIEW][0].tiles))
        self.assertLess(counts['24x36-0'], counts['11x17-0'])

    def test_a_tab_over_four_pages_at_tabloid_suggests_the_big_sheet(self):
        self.big(120)
        hints = download_hints(project_graph(self.project))
        n = dict(hints['tabs'][T.OVERVIEW]['counts'])['11x17-0']
        self.assertGreater(n, MANY_PAGES)
        self.assertIn(f'Overview is {n} diagram pages at 11 × 17. Try 24 × 36.', hints['suggestion'])
        page = self.page()
        self.assertIn(f'Overview is {n} diagram pages at 11 × 17. Try 24 × 36.', page)
        self.assertIn(f'· {n} diagram pages</span>', page)
        self.assertIn(f'data-many="{MANY_PAGES}"', page)

    def test_the_suggestion_starts_past_four_pages(self):
        self.assertEqual(MANY_PAGES, 4)
        self.assertEqual(suggestion_text([('Overview', 4), ('Dante', 1), ('Comms', 0)]), '')
        self.assertEqual(suggestion_text([('Overview', 5), ('Dante', 1)]),
                         'Overview is 5 diagram pages at 11 × 17. Try 24 × 36.')
        self.assertEqual(suggestion_text([('Overview', 5), ('Speaker cables', 9)]),
                         'Overview is 5 diagram pages at 11 × 17. Try 24 × 36. '
                         'Speaker cables is 9 diagram pages at 11 × 17. Try 24 × 36.')
