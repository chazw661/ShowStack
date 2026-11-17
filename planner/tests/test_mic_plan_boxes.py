"""Mic Planner: where each showflow row is on its page, and which rows a cue
came from (for the walkthrough's PDF highlights).

Run with::

    python manage.py test planner.tests.test_mic_plan_boxes --settings=audiopatch.test_settings
"""

import hashlib
import io
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import importer
from planner.mic_plan.extract import _box, extract, rows_from_tables
from planner.mic_plan.parser import analyse
from planner.models import ShowflowEvent, ShowflowImport, ShowflowRow
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase, pdf


def _line_words(data):
    """{(page_no, line label): (x, y)}: the middle of each line number in
    the first column, as fractions of the page as shown (its crop box)."""
    import pdfplumber

    out = {}
    with pdfplumber.open(io.BytesIO(data)) as doc:
        for page in doc.pages:
            x0, top, x1, bottom = page.cropbox
            for w in page.extract_words():
                if w['text'].isdigit() and w['x0'] - x0 < (x1 - x0) / 14:
                    out[(page.page_number, w['text'])] = (
                        ((w['x0'] + w['x1']) / 2 - x0) / (x1 - x0),
                        ((w['top'] + w['bottom']) / 2 - top) / (bottom - top))
    return out


def _inside(point, box):
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


class RowBoxTests(SimpleTestCase):

    def assert_boxes_hold_their_rows(self, data):
        rows = extract(data)[0]
        words = _line_words(data)
        self.assertTrue(rows)
        for row in rows:
            box = row['box']
            self.assertTrue(0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1, box)
            point = words[(row['page_no'], row['line'])]
            self.assertTrue(_inside(point, box), (row['line'], point, box))
            # ...and in no other row's box on that page.
            others = [r['line'] for r in rows if r is not row and r['page_no'] == row['page_no']
                      and _inside(point, r['box'])]
            self.assertEqual([], others, row['line'])
        return rows

    def test_every_row_has_the_box_its_line_number_is_in(self):
        rows = self.assert_boxes_hold_their_rows(F.build_pdf(F.MAIN_PAGES))
        self.assertEqual({1, 2, 3}, {r['page_no'] for r in rows})

    def test_rows_on_a_page_run_down_it(self):
        rows = extract(F.build_pdf(F.MAIN_PAGES))[0]
        for page in {r['page_no'] for r in rows}:
            tops = [r['box'][1] for r in rows if r['page_no'] == page]
            self.assertEqual(sorted(tops), tops)

    def test_boxes_are_fractions_of_the_crop_box(self):
        # What pdf.js shows is the crop box: a box measured from the media
        # box would sit off by the margin. (This crop trims margins only.)
        self.assert_boxes_hold_their_rows(F.build_pdf(F.MAIN_PAGES, crop=(10, 8, 782, 604)))

    def test_box_arithmetic(self):
        page = SimpleNamespace(cropbox=(100, 50, 500, 250))       # 400 x 200 shown
        self.assertEqual([0.25, 0.5, 0.5, 1.0], _box((200, 150, 300, 250), page))
        # Past the crop box is clamped to the page edge.
        self.assertEqual([0.0, 0.0, 1.0, 1.0], _box((0, 0, 900, 900), page))

    def test_skipped_header_and_title_rows_keep_the_boxes_in_step(self):
        header = ['', 'Start', 'End', 'Description', 'Speaker', 'BSM']
        page1 = [['Acme Summit', '', '', '', '', ''], header,
                 ['1', '8:00 AM', '8:30 AM', 'Opening', 'Alex Host', '']]
        page2 = [['Acme Summit', '', '', '', '', ''], header,
                 ['2', '8:30 AM', '9:00 AM', 'Keynote', 'Kim Keynote', ''],
                 ['', '', '', '', '', ''],
                 ['3', '9:00 AM', '', 'Break', '', '']]
        boxes = [[['t1', 'h1', 'r1']], [['t2', 'h2', 'r2', 'blank', 'r3']]]
        rows, _, _ = rows_from_tables([[page1], [page2]], boxes=boxes)
        self.assertEqual([('1', 'r1'), ('2', 'r2'), ('3', 'r3')], [(r['line'], r['box']) for r in rows])

    def test_rows_without_boxes_have_none(self):
        header = ['', 'Start', 'End', 'Description', 'Speaker', 'BSM']
        rows, _, _ = rows_from_tables([[[header, ['1', '8:00 AM', '', 'Opening', '', '']]]])
        self.assertIsNone(rows[0]['box'])


class RotatedPageTests(MicPlanBase):
    """A page stored portrait and turned by /Rotate shows the same landscape
    table as an unturned page (build_rotated_pdf; poppler renders them
    alike). Boxes are of the page as shown, so they match the unturned
    page's, measured on that page: the truth doesn't come from the same read."""

    @classmethod
    def setUpTestData(cls):
        cls.flat = F.build_rotated_pdf(F.MAIN_PAGES, 0)
        cls.flat_rows = extract(cls.flat)[0]
        cls.flat_words = _line_words(cls.flat)

    def import_rows(self, data):
        self.use(self.editor)
        self.client.post(reverse('planner:mic_plan_upload'), {
            'day': self.day.pk,
            'showflow': SimpleUploadedFile('turned.pdf', data, content_type='application/pdf')})
        part = ShowflowImport.objects.get(day=self.day)
        return list(ShowflowRow.objects.filter(showflow_import=part).order_by('order'))

    def test_turned_pages_store_the_boxes_of_the_page_as_shown(self):
        for rotate in (90, 180, 270):
            with self.subTest(rotate=rotate):
                ShowflowImport.objects.filter(day=self.day).delete()
                rows = self.import_rows(F.build_rotated_pdf(F.MAIN_PAGES, rotate))
                self.assertEqual([r['line'] for r in self.flat_rows], [r.line_no for r in rows])
                self.assertEqual([r['description'] for r in self.flat_rows], [r.description for r in rows])
                for flat, row in zip(self.flat_rows, rows):
                    self.assertEqual(flat['page_no'], row.page_no)
                    for a, b in zip(flat['box'], row.bbox):
                        self.assertAlmostEqual(a, b, delta=0.0002)
                    point = self.flat_words[(row.page_no, row.line_no)]
                    self.assertTrue(_inside(point, row.bbox), (rotate, row.line_no, point, row.bbox))

    def test_the_unturned_drawing_matches_the_main_fixture(self):
        # The comparison page is a real showflow page: same rows as MAIN_PAGES.
        self.assertEqual([r['line'] for r in extract(F.build_pdf(F.MAIN_PAGES))[0]],
                         [r['line'] for r in self.flat_rows])


class CueRowsTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = extract(F.build_pdf(F.MAIN_PAGES))[0]
        cls.result = analyse(cls.rows)
        cls.line = {i: row['line'] for i, row in enumerate(cls.rows)}

    def cue(self, kind, name, line):
        [e] = [e for e in self.result.events
               if e.kind == kind and e.name == name and self.line[e.row] == line]
        return self.line[e.row], [self.line[i] for i in e.rows]

    def test_a_cue_split_by_a_page_break_has_both_rows(self):
        # "Lee Catches Dana," at the foot of page 2, "Chris, and Robin" at the
        # top of page 3: one cue, two pieces.
        self.assertEqual(('110', ['110', '111']), self.cue('catch', 'Chris Baker', '110'))
        self.assertEqual(('110', ['110', '111']), self.cue('catch', 'Robin Cole', '110'))
        pages = {self.rows[i]['page_no'] for i, r in enumerate(self.rows) if r['line'] in ('110', '111')}
        self.assertEqual({2, 3}, pages)

    def test_a_cue_in_one_cell_has_its_own_row_only(self):
        self.assertEqual(('103', ['103']), self.cue('send', 'Alex Host', '103'))
        self.assertEqual(('106', ['106']), self.cue('send', 'Pat Guest', '106'))

    def test_the_next_cue_in_the_cell_is_not_part_of_the_split_one(self):
        # "Chris, and Robin Rio Sends Alex": Rio's send is row 111's alone.
        sends = [(self.line[e.row], [self.line[i] for i in e.rows]) for e in self.result.events
                 if e.kind == 'send' and e.name == 'Alex Host']
        self.assertIn(('111', ['111']), sends)

    def test_every_cue_lists_its_own_row(self):
        self.assertTrue(self.result.events)
        for e in self.result.events:
            self.assertIn(e.row, e.rows)


class ImportStoresBoxesTests(MicPlanBase):

    def test_an_import_keeps_row_boxes_cue_rows_and_the_files_hash(self):
        self.use(self.editor)
        self.upload()
        part = ShowflowImport.objects.get(day=self.day)
        self.assertEqual(hashlib.sha256(pdf('MAIN_PAGES')).hexdigest(), part.file_sha256)
        rows = list(part.rows.all())
        self.assertTrue(all(len(r.bbox) == 4 for r in rows))
        by_line = {r.line_no: r for r in rows}
        split = ShowflowEvent.objects.get(row__showflow_import=part, kind='catch',
                                          person__display_name='Chris Baker', row__line_no='110')
        self.assertEqual([by_line['110'].order, by_line['111'].order], split.source_rows)
        self.assertEqual(by_line['110'].pk, split.row_id)

    def test_a_rebuild_keeps_the_cue_rows(self):
        self.use(self.editor)
        self.upload()
        part = ShowflowImport.objects.get(day=self.day)
        before = sorted(ShowflowEvent.objects.filter(row__showflow_import=part)
                        .values_list('kind', 'person__display_name', 'source_rows'))
        importer.rebuild_day(self.day)
        after = sorted(ShowflowEvent.objects.filter(row__showflow_import=part)
                       .values_list('kind', 'person__display_name', 'source_rows'))
        self.assertEqual(before, after)
