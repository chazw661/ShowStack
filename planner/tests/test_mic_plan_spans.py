"""Mic Planner: where in the showflow each person's name came from (the
walkthrough highlights those characters).

Run with::

    python manage.py test planner.tests.test_mic_plan_spans --settings=audiopatch.test_settings
"""

from django.test import SimpleTestCase

from planner.mic_plan.extract import extract
from planner.mic_plan.parser import Roster, analyse, split_cell
from planner.models import ShowflowImport
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase


class SpanTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = extract(F.build_pdf(F.MAIN_PAGES))[0]
        cls.result = analyse(cls.rows)
        cls.at = {row['line']: i for i, row in enumerate(cls.rows)}

    def texts(self, name, line, column):
        """The text of each of ``name``'s spans on ``line`` in ``column``."""
        i = self.at[line]
        return [self.rows[i][column][s:e] for r, col, s, e in self.result.people[name]['spans']
                if r == i and col == column]

    def test_a_speaker_cell(self):
        self.assertEqual(['Pat Guest'], self.texts('Pat Guest', '106', 'speaker'))
        self.assertEqual(['Alex Host'], self.texts('Alex Host', '104', 'speaker'))

    def test_a_titles_prefix_does_not_shift_the_place(self):
        # "Titles: Alex Host": the prefix is blanked, not cut, before reading.
        self.assertEqual(['Alex Host'], self.texts('Alex Host', '103', 'speaker'))

    def test_a_welcome_line(self):
        self.assertEqual(['Alex Host'], self.texts('Alex Host', '103', 'description'))

    def test_a_cue(self):
        self.assertEqual(['Pat Guest', 'Pat'], self.texts('Pat Guest', '106', 'bsm'))

    def test_a_cue_split_by_a_page_break_has_each_name_where_it_is(self):
        self.assertEqual(['Dana'], self.texts('Dana Able', '110', 'bsm'))
        self.assertEqual(['Chris'], self.texts('Chris Baker', '111', 'bsm'))
        self.assertEqual(['Robin'], self.texts('Robin Cole', '111', 'bsm'))

    def test_every_span_is_text_of_that_person(self):
        for name, info in self.result.people.items():
            self.assertTrue(info['spans'], name)
            for r, col, s, e in info['spans']:
                text = self.rows[r][col][s:e]
                self.assertTrue(any(w in text for w in name.replace('-', ' ').split()), (name, text))

    def test_stage_notes_are_blanked_in_place(self):
        roster = Roster()
        spans = []
        text = '(SL) Robin Cole {CLICKER 1}, Taylor Eve'
        names, _ = split_cell(text, roster, discover=True, spans=spans)
        self.assertEqual(['Robin Cole', 'Taylor Eve'], names)
        self.assertEqual(['Robin Cole', 'Taylor Eve'], [text[s:e] for _, s, e in spans])


class SpansStoredTests(MicPlanBase):

    def test_an_import_stores_each_persons_spans_by_row_order(self):
        self.use(self.editor)
        self.upload()
        part = ShowflowImport.objects.get(day=self.day)
        rows = {r.order: r for r in part.rows.all()}
        spans = self.person('Pat Guest').flags['spans'][str(part.pk)]
        self.assertIn(['speaker', 'Pat Guest'],
                      [[col, getattr(rows[o], col + '_text')[s:e]] for o, col, s, e in spans if col == 'speaker'])
        self.assertTrue(all(col in ('speaker', 'description', 'bsm') for _, col, _, _ in spans))
