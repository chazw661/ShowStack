"""Wiring Diagram PDF (Download PDF): the tiling plan, the PDF itself and
its endpoint. PDF text is read with PyPDF2 (pinned in requirements.txt):
it reads the Symbol-font arrows as "←" / "→", where pdfplumber does not.

Run with::

    python manage.py test planner.tests.test_wiring_pdf --settings=audiopatch.test_settings
"""
import io
import re
import warnings
from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from planner.connections import layout as L
from planner.connections import tabs as T
from planner.connections import tiling
from planner.connections.graph import digest, project_graph
from planner.models import ProjectMember
from planner.tests.test_wiring_layout import WiringShow
from planner.utils.pdf_exports import wiring_pdf
from planner.views_wiring import tab_view

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from PyPDF2 import PdfReader

NAME = '<img src=x onerror=alert(1)>'
QUOTED = '"\'><b>&amp; ]]> Łódź'

TABLOID = wiring_pdf.PAPER['11x17']
W = TABLOID[0] - 2 * wiring_pdf.MARGIN
H = TABLOID[1] - 2 * wiring_pdf.MARGIN - wiring_pdf.FOOTER_H - wiring_pdf.HEAD_H - wiring_pdf.HEAD_GAP - 1


def read(pdf):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        reader = PdfReader(io.BytesIO(pdf))
        return reader, [page.extract_text() or '' for page in reader.pages]


# -- synthetic layouts for the tiling plan -----------------------------------------

def box(name, x, y, rows=1, column=0):
    b = L.Box(name, name, column, 'device', node=name, x=x, y=y)
    b.out_h = [L.SLOT] * rows
    b.in_h = []
    b.h = b.head + rows * L.SLOT + L.PAD
    return b


def route(rid, points):
    return L.Route(rid, 'a', 'b', points, '', points[0][0] + 10, points[0][1] - 4, '',
                   ('confirmed',), False, lines=[])


def lay_of(boxes, routes=(), columns=None):
    xs = sorted({b.x for b in boxes})
    columns = columns or [(f'Col {i}', x, L.BOX_W) for i, x in enumerate(xs)]
    width = max(b.x for b in boxes) + L.BOX_W + L.MARGIN
    height = max(b.y + b.h for b in boxes) + L.MARGIN
    return L.Layout(width, height, columns, boxes, [], list(routes))


def stack(x, n, rows=3, start=L.MARGIN + L.TITLE_H, gap=L.GAP_Y, column=0, prefix='b'):
    out, y = [], start
    for i in range(n):
        b = box(f'{prefix}{i}', x, y, rows, column)
        out.append(b)
        y += b.h + gap
    return out


class TilingPlanTests(SimpleTestCase):

    def assert_never_through_a_box(self, plan, lay, allowed=()):
        for tile in plan.tiles:
            for r in tile.regions:
                for b in lay.boxes:
                    if not (r.x0 - 0.01 <= b.x <= r.x1 + 0.01) or b.id in allowed:
                        continue
                    for edge in (r.y0, r.y1):
                        self.assertFalse(b.y + 0.01 < edge < b.y + b.h - 0.01,
                                         f'{b.id} cut at {edge} on tile {tile.index}')
                # a strip edge is never inside a box either
                for b in lay.boxes:
                    self.assertFalse(b.x < r.x0 - 0.01 < b.x + b.w or b.x < r.x1 - 0.01 < b.x + b.w,
                                     f'{b.id} cut across on tile {tile.index}')

    def assert_largest_scale_for_its_pages(self, plan, lay):
        """Tiled: as few pages as 6pt text needs, and no smaller than it
        has to be for that many."""
        self.assertGreater(len(plan.tiles), 1)
        self.assertGreaterEqual(plan.scale, tiling.MIN_SCALE)
        self.assertLessEqual(plan.scale, tiling.MAX_SCALE)
        at_6pt = tiling._tiles(lay, W, H, tiling.MIN_SCALE)
        self.assertEqual(len(plan.tiles), len(at_6pt))
        step = (tiling.MAX_SCALE - tiling.MIN_SCALE) / tiling.SCALE_STEPS
        if plan.scale + step <= tiling.MAX_SCALE + 1e-9:
            self.assertGreater(len(tiling._tiles(lay, W, H, plan.scale + step)), len(plan.tiles))

    def test_a_tiled_tab_is_printed_larger_when_that_costs_no_page(self):
        # 30 boxes down one column: 6pt needs so many pages, and each has
        # room to spare, so the print is larger than 6pt.
        lay = lay_of(stack(L.MARGIN, 30))
        plan = tiling.plan(lay, W, H)
        self.assertGreater(plan.scale, tiling.MIN_SCALE)
        self.assert_largest_scale_for_its_pages(plan, lay)
        for t in plan.tiles:
            for r in t.regions:
                self.assertLessEqual((r.y1 - t.top) * plan.scale, H + 0.01)
                self.assertLessEqual((r.x1 - t.x0) * plan.scale, W + 0.01)

    def assert_every_box_whole(self, plan, lay):
        for b in lay.boxes:
            covered = sum(y1 - y0 for t in plan.tiles for y0, y1 in tiling.box_regions(t, b))
            self.assertAlmostEqual(covered, b.h, places=1, msg=b.id)

    def test_a_small_diagram_is_one_page_enlarged_at_most_one_and_a_half(self):
        lay = lay_of(stack(L.MARGIN, 2))
        plan = tiling.plan(lay, W, H)
        self.assertEqual(len(plan.tiles), 1)
        self.assertEqual(plan.scale, tiling.MAX_SCALE)

    def test_a_diagram_that_fits_at_6pt_is_one_page(self):
        lay = lay_of(stack(L.MARGIN, 4) + stack(L.MARGIN + 1100, 4, column=1, prefix='c'))
        plan = tiling.plan(lay, W, H)
        self.assertEqual(len(plan.tiles), 1)
        self.assertGreaterEqual(plan.scale, tiling.MIN_SCALE)
        self.assertAlmostEqual(plan.scale, min(W / lay.width, H / lay.height, 1.5))

    def test_wide_is_cut_between_columns(self):
        boxes = [b for i in range(7) for b in stack(L.MARGIN + i * 420, 2, column=i, prefix=f'c{i}-')]
        lay = lay_of(boxes)
        plan = tiling.plan(lay, W, H)
        self.assert_largest_scale_for_its_pages(plan, lay)
        self.assertEqual(plan.strips, 2)
        self.assertTrue(all(t.row == 0 for t in plan.tiles))
        # the cut is just left of a column's boxes
        cut = min(r.x0 for r in plan.tiles[1].regions)
        self.assertIn(round(cut + tiling.X_CUT, 2), {round(x, 2) for _, x, _ in lay.columns})
        self.assert_never_through_a_box(plan, lay)
        self.assert_every_box_whole(plan, lay)
        # each strip fits the page at 6pt
        for t in plan.tiles:
            right = max(r.x1 for r in t.regions)
            self.assertLessEqual((right - t.x0) * plan.scale, W + 0.01)

    def test_tall_is_cut_between_boxes(self):
        lay = lay_of(stack(L.MARGIN, 30))
        plan = tiling.plan(lay, W, H)
        self.assert_largest_scale_for_its_pages(plan, lay)
        self.assertGreater(len(plan.tiles), 1)
        self.assertEqual(plan.strips, 1)
        self.assert_never_through_a_box(plan, lay)
        self.assert_every_box_whole(plan, lay)
        for t in plan.tiles:
            for r in t.regions:
                self.assertLessEqual((r.y1 - t.top) * plan.scale, H + 0.01)

    def test_staggered_columns_get_a_stepped_cut(self):
        # Column 0's boxes and column 1's never leave a common gap: one
        # straight cut would go through a box, so each column is cut at its own.
        a = stack(L.MARGIN, 14, rows=5)
        b = stack(L.MARGIN + 420, 14, rows=5, start=L.MARGIN + L.TITLE_H + 60, column=1, prefix='s')
        lay = lay_of(a + b)
        plan = tiling.plan(lay, W, H)
        first = plan.tiles[0]
        bottoms = {r.column: round(r.y1, 1) for r in first.regions}
        self.assertEqual(len(bottoms), 2)
        self.assertNotEqual(bottoms[0], bottoms[1])
        self.assert_never_through_a_box(plan, lay)
        self.assert_every_box_whole(plan, lay)

    def test_an_amp_location_header_stays_with_its_first_box(self):
        boxes, groups, y = [], [], L.MARGIN + L.TITLE_H
        for i in range(30):
            if i % 3 == 0:
                g = L.Group(f'g{i}', f'Rack {i}', len(groups), column=0, x=L.MARGIN)
                g.y = y
                y += g.head
                groups.append(g)
            b = box(f'b{i}', L.MARGIN, y, rows=3)
            boxes.append(b)
            y += b.h + L.GAP_Y
        base = lay_of(boxes)
        lay = L.Layout(base.width, base.height, base.columns, boxes, groups, [])
        plan = tiling.plan(lay, W, H)
        self.assertGreater(len(plan.tiles), 1)
        for t in plan.tiles:
            for r in t.regions:
                for g in groups:
                    self.assertFalse(g.y - 0.01 < r.y1 < g.y + g.head + 0.01, f'{g.label} split')
        self.assert_never_through_a_box(plan, lay)

    def test_a_box_taller_than_a_page_is_cut_between_rows_and_continued(self):
        tall = box('Rio 64', L.MARGIN, L.MARGIN + L.TITLE_H, rows=96)
        lay = lay_of([tall, box('After', L.MARGIN, tall.y + tall.h + L.GAP_Y)])
        plan = tiling.plan(lay, W, H)
        self.assert_largest_scale_for_its_pages(plan, lay)
        cuts = [r.y1 for t in plan.tiles for r in t.regions if tall.y < r.y1 < tall.y + tall.h]
        self.assertTrue(cuts)
        rows = {round(tall.y + tall.head + i * L.SLOT, 2) for i in range(97)}
        for y in cuts:
            self.assertIn(round(y, 2), rows)                 # between two rows
        self.assertTrue(any(b is tall for t in plan.tiles for b, _ in t.continued))
        self.assert_never_through_a_box(plan, lay, allowed={'Rio 64'})
        self.assert_every_box_whole(plan, lay)

    def test_lines_across_a_cut_are_paired(self):
        boxes = [b for i in range(7) for b in stack(L.MARGIN + i * 420, 2, column=i, prefix=f'c{i}-')]
        y = boxes[0].y + boxes[0].head + L.SLOT / 2
        r = route('e1', [(boxes[0].x + L.BOX_W, y), (L.MARGIN + 6 * 420, y)])
        lay = lay_of(boxes, [r])
        plan = tiling.plan(lay, W, H)
        crossings = tiling.crossings(plan, lay.routes)
        self.assertEqual([(c.leaves, c.enters, c.direction) for c in crossings], [(0, 1, 'right')])
        marks = wiring_pdf.tile_marks(plan, crossings, {0: 1, 1: 2})
        self.assertEqual([m['text'] for m in marks[0]], ['→ p.2'])
        self.assertEqual([m['text'] for m in marks[1]], ['from p.1'])

    def test_one_page_has_no_crossings(self):
        lay = lay_of(stack(L.MARGIN, 2), [route('e1', [(L.MARGIN, 80), (L.MARGIN + 400, 80)])])
        self.assertEqual(tiling.crossings(tiling.plan(lay, W, H), lay.routes), [])


# -- the PDF ----------------------------------------------------------------------------

class WiringPdfTests(WiringShow, TestCase):
    url = reverse('planner:wiring_diagram_pdf')

    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()

    def get(self, user=None, **params):
        self.client.force_login(user or self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        return self.client.get(self.url, params)

    def pdf(self, **params):
        response = self.get(**params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        return read(response.content)

    def test_every_tab_by_default_each_on_its_own_page_with_a_title_block(self):
        reader, pages = self.pdf()
        stamp_digest = f'Graph {digest(project_graph(self.project))}'
        starts = [i for i, text in enumerate(pages) if text.startswith(self.project.name)]
        self.assertEqual(len(starts), 6)
        for i, label in zip(starts, ('Overview', 'Dante', 'AVB', 'Analogue/AES', 'Speaker cables',
                                     'Comms')):
            head = pages[i].split('\n')[1]
            self.assertTrue(head.startswith(label), head)
            self.assertIn('Printed ', head)
            self.assertIn(stamp_digest, head)
        n = len(pages)
        for i, text in enumerate(pages, 1):
            self.assertIn(f'Page {i} of {n}', text)
            self.assertIn(stamp_digest, text)

    def test_only_the_chosen_tabs(self):
        _, pages = self.pdf(tabs='overview,speakers')
        heads = [t.split('\n')[1] for t in pages if t.startswith(self.project.name)]
        self.assertEqual([h.split(' ')[0] for h in heads], ['Overview', 'Speaker'])
        _, pages = self.pdf(tabs=['analog'])
        heads = [t.split('\n')[1] for t in pages if t.startswith(self.project.name)]
        self.assertEqual(len(heads), 1)
        self.assertTrue(heads[0].startswith('Analogue/AES'))
        _, pages = self.pdf(tabs='nonsense')                # nothing known: every tab
        self.assertEqual(sum(t.startswith(self.project.name) for t in pages), 6)

    def test_paper_sizes(self):
        for paper, size in (('11x17', (1224, 792)), ('24x36', (2592, 1728)), ('A4', (1224, 792))):
            reader, _ = self.pdf(paper=paper)
            for page in reader.pages:
                self.assertEqual((round(float(page.mediabox.width)), round(float(page.mediabox.height))),
                                 size, paper)

    def test_boxes_slots_and_labels_are_real_text(self):
        _, pages = self.pdf(tabs='overview')
        text = pages[0]
        for word in ('Stage Box', 'FOH Desk', 'SL P1', 'SL Amp', 'DEVICE INPUTS',
                     '(mics & sources plug in here)', '(feeds processors, amps, IEMs)',
                     'AES 1 ← SL P1 AES Out 1 (Main', 'XLR 1 ← Stage Box Analog Out 3',
                     'Ch 1 ← Stage Box In 1', 'Analog Out 3', 'AES Out 2', 'Aux 1',
                     'Confirmed (linked on a page)'):
            self.assertIn(word, text)
        self.assertNotIn('…', ''.join(pages))

    def test_network_feeds_off(self):
        self.p1_out(self.sl, 'AVB', 2, 'Delay')
        self.amp_channel(self.sl_amp, 2, avb_stream='AVB 2 - Delay')
        _, on = self.pdf(tabs='overview', network='1')
        self.assertIn('SL Amp AVB Ch 2', on[0])
        # Off unless asked for: no parameter (the panel's box unticked), or 0.
        for params in ({}, {'network': '0'}):
            _, off = self.pdf(tabs='overview', **params)
            self.assertNotIn('SL Amp AVB Ch 2', off[0])
        self.assertIn('AVB ← SL P1 stream 2 (Delay)', re.sub(r'\s+', ' ', off[0]))

    def test_the_avb_tab_prints_its_streams_whatever_the_network_box_says(self):
        self.p1_out(self.sl, 'AVB', 2, 'Delay')
        self.amp_channel(self.sl_amp, 2, avb_stream='AVB 2 - Delay')
        for params in ({}, {'network': '0'}, {'network': '1'}):
            _, pages = self.pdf(tabs='avb', **params)
            text = re.sub(r'\s+', ' ', pages[0])
            self.assertTrue(pages[0].split('\n')[1].startswith('AVB'))
            for word in ('AVB Out 2', 'SL Amp AVB Ch 2', 'AVB ← SL P1 stream 2 (Delay)', 'No IP'):
                self.assertIn(word, text)

    def test_keys_and_the_connections_table(self):
        view = tab_view(self.project, project_graph(self.project), T.OVERVIEW)
        view['connections'] = [{'key': n, 'from': f'From-{n:03d} ← Box', 'to': f'To-{n:03d}',
                                'cable': 'AES'} for n in range(1, 241)]
        pdf = wiring_pdf.build_wiring_pdf(project=self.project, views=[view], digest='abcd1234',
                                          paper='11x17', printed=datetime.now(timezone.utc))
        _, pages = read(pdf)
        table = [t for t in pages if 'From-' in t]
        self.assertGreater(len(table), 1)
        for text in table:
            # the header row repeated on each page of the table
            self.assertIn('Key From To Cable / transport', ' '.join(text.split()))
        for n in range(1, 241):
            on = [i for i, t in enumerate(pages) if f'From-{n:03d} ← Box' in t]
            self.assertEqual(len(on), 1, n)                              # never split, never lost
            self.assertIn(f'[{n}]', pages[on[0]])
            self.assertIn(f'To-{n:03d}', pages[on[0]])
        # the table starts after the diagram's page
        self.assertNotIn('From-001', pages[0])

    def test_a_tiled_tab_marks_where_lines_continue(self):
        for i in range(60):
            box = self.device(f'Rack Box {i:02d}')
            self.device_output(box, 1, f'Feed {i:02d}')
            amp = self.amp(f'Amp {i:02d}', rack=f'Rack {i // 4}')
            self.amp_channel(amp, 1, analog_input=f'Feed {i:02d}')
        reader, pages = self.pdf(tabs='overview')
        parts = [t for t in pages if 'Part ' in t.split('\n')[1]]
        self.assertGreater(len(parts), 1)
        joined = '\n'.join(pages)
        self.assertRegex(joined, r'→ p\.\d+')
        self.assertRegex(joined, r'from p\.\d+')
        # every "→ p.N" names a page that says it comes "from" this one
        for i, text in enumerate(pages, 1):
            for target in re.findall(r'→ p\.(\d+)', text):
                self.assertIn(f'from p.{i}', pages[int(target) - 1])

    def test_hostile_names_are_text_and_the_pdf_still_builds(self):
        self.device(NAME)
        box = self.device(QUOTED)
        self.device_output(box, 1, NAME)
        self.amp_channel(self.ff_amp, 2, analog_input=NAME)
        self.project.name = NAME
        self.project.save()
        reader, pages = self.pdf()
        joined = '\n'.join(pages)
        self.assertIn(NAME, joined)
        self.assertIn('Łódź', joined)
        self.assertIn('"\'><b>&amp; ]]>', joined)
        self.assertGreater(len(reader.pages), 3)

    def test_an_empty_project_still_prints_its_title_blocks(self):
        self.project = self.make_project('Empty show')
        _, pages = self.pdf()
        self.assertEqual(sum(t.startswith('Empty show') for t in pages), 6)
        self.assertIn('Nothing to draw yet', pages[0])

    def test_any_project_role_can_download_and_only_their_project(self):
        viewer = User.objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        response = self.get(viewer)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('Stage Box', read(response.content)[1][0])
        outsider = User.objects.create_user('out', password='pw', is_staff=True)
        response = self.get(outsider)
        self.assertEqual(response.status_code, 302)              # no project of theirs
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_post_is_refused(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url).status_code, 405)


class WiringPageDownloadTests(WiringShow, TestCase):
    def setUp(self):
        super().setUp()
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def test_the_page_has_the_panel_and_the_digest(self):
        response = self.client.get(reverse('planner:wiring_diagram'))
        self.assertContains(response, 'Download PDF')
        self.assertContains(response, 'Download DXF')
        self.assertContains(response, f'action="{reverse("planner:wiring_diagram_pdf")}"')
        self.assertContains(response, f'formaction="{reverse("planner:wiring_diagram_dxf")}"')
        page = response.content.decode()
        for key in T.TAB_KEYS:
            self.assertRegex(page, rf'name="tabs" value="{key}"[^>]* checked>')
        # Network feeds: off until ticked.
        self.assertContains(response, '<input type="checkbox" name="network" value="1">')
        self.assertContains(response, 'name="paper" value="11x17" checked')
        self.assertContains(response, 'name="paper" value="24x36"')
        self.assertContains(response, f'Graph {digest(project_graph(self.project))}')

    def test_the_digest_follows_the_wiring(self):
        before = digest(project_graph(self.project))
        self.assertEqual(before, digest(project_graph(self.project)))
        self.device_output(self.box, 5, 'New feed')
        self.assertNotEqual(before, digest(project_graph(self.project)))
