"""Speaker cells that are not just names (Client H): upper-case notes, a list
label, and "Name, Company" lists with the next name glued to a company.

Run with::

    python manage.py test planner.tests.test_mic_plan_speaker_cells --settings=audiopatch.test_settings
"""

import json

from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import importer, walkthrough
from planner.mic_plan.parser import analyse
from planner.models import ShowflowImport, ShowflowRow
from planner.tests.test_mic_plan_import import MicPlanBase

SEATING = ('IN SPEAKER SEATING ORDER: Ann Lee, Acme Bo Chen, The Big Health Network Jo Pike, '
           'Provider Solutions, Acme Dr. Sol Tate, Coast Cancer Specialists')


def _row(line, desc='', speaker='', bsm=''):
    return {'line': line, 'start': '', 'end': '', 'duration': '', 'description': desc,
            'speaker': speaker, 'bsm': bsm, 'audio': '', 'notes': ''}


def _read(*speakers):
    """analyse() over one row per Speaker cell: (people, {row: leftovers},
    {row: [(text, kind)]})."""
    rows = [_row(str(100 + i), 'Segment', s) for i, s in enumerate(speakers)]
    a = analyse(rows)
    leftovers = {i: [rows[i]['speaker'][s:e] for s, e in sp] for i, sp in a.leftovers.items()}
    marks = {i: [(rows[i]['speaker'][s:e], k) for s, e, k in m] for i, m in a.marks.items()}
    return sorted(a.people), leftovers, marks


def _named(speakers, row):
    rows = [_row(str(100 + i), 'Segment', s) for i, s in enumerate(speakers)]
    a = analyse(rows)
    return sorted(n for n, info in a.people.items() if any(sp[0] == row for sp in info['spans']))


class CapsNoteTests(SimpleTestCase):

    def test_an_upper_case_run_in_a_mixed_case_file_is_a_note(self):
        people, leftovers, marks = _read('ROOM AND FOYER', 'Ann Lee', 'MISSING SLIDES', 'Bo Chen',
                                         'Cy Dunn', 'Dee Fox')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Cy Dunn', 'Dee Fox'], people)
        self.assertEqual({}, leftovers)
        self.assertEqual([('ROOM AND FOYER', 'note')], marks[0])
        self.assertEqual([('MISSING SLIDES', 'note')], marks[2])

    def test_a_note_beside_a_name_leaves_the_name(self):
        people, _, marks = _read('Ann Lee SCRIPT HERE', 'Bo Chen')
        self.assertEqual(['Ann Lee', 'Bo Chen'], people)
        self.assertEqual([('SCRIPT HERE', 'note')], marks[0])

    def test_an_upper_case_file_keeps_its_names(self):
        people, _, marks = _read('ANN LEE', 'BO CHEN', 'CY DUNN & DEE FOX')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Cy Dunn', 'Dee Fox'], people)
        self.assertEqual({}, marks)

    def test_an_upper_case_run_naming_someone_known_is_that_person(self):
        speakers = ['Ann Lee', 'Bo Chen', 'ANN LEE', 'Cy Dunn']
        self.assertEqual(['Ann Lee'], _named(speakers, 2))
        self.assertNotIn(2, _read(*speakers)[2])

    def test_one_upper_case_word_is_not_a_note(self):
        people, _, marks = _read('Ann Lee, ACME Health', 'Bo Chen')
        self.assertEqual(['Ann Lee', 'Bo Chen'], people)
        self.assertEqual([('ACME Health', 'company')], marks[0])


class LabelTests(SimpleTestCase):

    def test_a_list_label_opening_the_cell_is_passed_over(self):
        people, leftovers, marks = _read('PANEL: Ann Lee & Bo Chen', 'Cy Dunn')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Cy Dunn'], people)
        self.assertEqual({}, leftovers)
        self.assertEqual([('PANEL:', 'note')], marks[0])

    def test_a_label_needs_a_name_after_it(self):
        _, leftovers, marks = _read('VIDEO: 356 - Lyric Video', 'Ann Lee')
        self.assertNotIn(0, marks)
        self.assertEqual(['VIDEO: 356'], leftovers[0][:1])

    def test_a_labelled_plain_list_is_still_names(self):
        people, leftovers, marks = _read('PANEL: Ann Lee, Bo Chen, Cy Dunn', 'Dee Fox')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Cy Dunn', 'Dee Fox'], people)
        self.assertEqual({}, leftovers)
        self.assertEqual([('PANEL:', 'note')], marks[0])

    def test_a_label_is_read_in_an_upper_case_file_too(self):
        people, _, marks = _read('SEATING ORDER: ANN LEE, BO CHEN', 'CY DUNN')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Cy Dunn'], people)
        self.assertEqual([('SEATING ORDER:', 'note')], marks[0])


class CompanyListTests(SimpleTestCase):

    def test_seating_order_with_companies_and_glued_names(self):
        people, leftovers, marks = _read(SEATING, 'Eve Moss')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Dr. Sol Tate', 'Eve Moss', 'Jo Pike'], people)
        self.assertEqual({}, leftovers)
        self.assertEqual([('IN SPEAKER SEATING ORDER:', 'note'), ('Acme', 'company'),
                          ('The Big Health Network', 'company'), ('Provider Solutions', 'company'),
                          ('Acme', 'company'), ('Coast Cancer Specialists', 'company')], marks[0])

    def test_name_comma_company(self):
        people, leftovers, marks = _read('Ann Lee, Acme', 'Bo Chen, Initech')
        self.assertEqual(['Ann Lee', 'Bo Chen'], people)
        self.assertEqual({}, leftovers)
        self.assertEqual([('Acme', 'company')], marks[0])

    def test_a_plain_comma_list_is_still_names(self):
        people, leftovers, marks = _read('Ann Lee, Bo Chen, Cy Dunn')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Cy Dunn'], people)
        self.assertEqual(({}, {}), (leftovers, marks))

    def test_a_title_after_the_comma_is_still_a_title(self):
        people, leftovers, marks = _read('SEATING ORDER: Ann Lee, Acme Bo Chen, MD, Coast Health Cy Dunn, Initech')
        self.assertEqual(['Ann Lee', 'Bo Chen', 'Cy Dunn'], people)
        self.assertEqual({}, leftovers)
        self.assertEqual(['SEATING ORDER:', 'Acme', 'Coast Health', 'Initech'], [t for t, _ in marks[0]])

    def test_a_company_ending_the_cell_is_not_a_person(self):
        people, _, _ = _read('SEATING ORDER: Ann Lee, Acme Bo Chen, Coast Cancer Specialists')
        self.assertNotIn('Cancer Specialists', people)

    def test_dash_affiliations_are_marked(self):
        _, _, marks = _read('Ted Ash - Acme AI (Partner) Kim Bo - Initech')
        self.assertEqual([('Acme AI', 'company'), ('Initech', 'company')], marks[0])


class WalkthroughMarkTests(MicPlanBase):
    """Notes and companies on the walkthrough: grey, never locked, and a
    note's row can still add people."""

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.part = ShowflowImport.objects.create(day=self.day, status='active', source_filename='t.pdf')
        cells = [('100', '8:00 AM', 'Doors', 'ROOM AND FOYER'), ('101', '8:30 AM', 'Opening', 'Ann Lee, Acme'),
                 ('102', '9:00 AM', 'Panel', SEATING), ('103', '9:30 AM', 'Close', 'Eve Moss')]
        ShowflowRow.objects.bulk_create([
            ShowflowRow(showflow_import=self.part, order=i, line_no=line, start_text=start, description=desc,
                        speaker_text=spk)
            for i, (line, start, desc, spk) in enumerate(cells)])
        importer.rebuild_day(self.day)

    def panel(self, line):
        return next(p for p in walkthrough.build(self.day)['panels'] if p['line'] == line)

    def marks(self, line):
        p = self.panel(line)
        text = p['rows'][0]['cells']['speaker']
        return [(text[m['start']:m['end']], m['kind']) for m in p['rows'][0]['marks'] if m['kind'] != 'name']

    def test_a_note_is_marked_unlocked_and_can_add_people(self):
        p = self.panel('100')
        self.assertEqual([('ROOM AND FOYER', 'note')], self.marks('100'))
        self.assertEqual(([], []), (p['locks'], p['person_locks']))
        self.assertEqual([], p['issues'])
        self.assertTrue(p['can_add'])
        self.assertFalse(self.day.showflow_people.filter(name_key='room and foyer').exists())

    def test_a_company_is_marked_and_is_no_issue(self):
        p = self.panel('101')
        self.assertEqual([('Acme', 'company')], self.marks('101'))
        self.assertEqual([], p['issues'])
        self.assertFalse(p['can_add'])

    def test_seating_order_people_are_found(self):
        names = set(self.day.showflow_people.values_list('display_name', flat=True))
        self.assertTrue({'Ann Lee', 'Bo Chen', 'Jo Pike', 'Dr. Sol Tate', 'Eve Moss'} <= names)
        self.assertFalse(names & {'Provider Solutions', 'Cancer Specialists', 'Room And Foyer'})

    def test_add_people_from_a_note_row(self):
        p = self.panel('100')
        r = self.client.post(reverse('planner:mic_plan_walk', args=[self.day.pk, 'add']),
                             json.dumps({'row': p['id'], 'names': ['Gil Hart']}), content_type='application/json')
        self.assertEqual(200, r.status_code)
        self.assertTrue(r.json()['ok'])
        added = self.day.showflow_people.get(display_name='Gil Hart').flags['added']
        self.assertEqual(['100'], [e['line'] for e in added])

    def test_marks_are_not_counted_as_issues_on_re_read(self):
        self.assertFalse([w for w in self.part.__class__.objects.get(pk=self.part.pk).warnings
                          if w['kind'] not in ('parse', importer.MARKS) and w.get('row_order') == 0])
