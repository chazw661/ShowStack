"""Mic Plan: wider header detection (the Client F layout), the messages when
no header is found, and the Client F rules that came with it. Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_headers --settings=audiopatch.test_settings
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import planning
from planner.mic_plan.extract import ShowflowError, extract, header_map, rows_from_tables
from planner.mic_plan.parser import analyse, exits_and_entries, Refs, Roster, split_cell
from planner.models import ShowflowImport, ShowflowPerson, ShowflowRow
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase


def fields(cells):
    return set((header_map(cells) or {}).values())


class HeaderSynonymTests(SimpleTestCase):

    def test_line_column_names(self):
        for name in ('CUE', 'Cue #', 'cue#', 'Line', 'LINE #', 'Line#', '#', ''):
            with self.subTest(name):
                mapping = header_map([name, 'Start', 'End', 'Description'])
                self.assertEqual('line', mapping[0])

    def test_description_column_names(self):
        for name in ('Description', 'Event', 'EVENT', 'Segment', 'Item', 'Content', 'Event:'):
            with self.subTest(name):
                self.assertIn('description', fields(['Start', 'End', name]))

    def test_speaker_column_names(self):
        for name in ('Speaker Name', 'SPEAKER', 'Speaker', 'Presenter', 'Presenters', 'Talent', 'Speakers'):
            with self.subTest(name):
                self.assertEqual({'start', 'description', 'speaker'}, fields(['Start', 'Event', name]))

    def test_case_spaces_and_punctuation_are_ignored(self):
        self.assertEqual({'start', 'end', 'duration', 'description', 'bsm'},
                         fields(['START:', 'E N D', 'DURATIO N', 'De-scrip-tion', "BSM's"]))

    def test_audio_is_mapped_when_present(self):
        self.assertIn('audio', fields(['Start', 'End', 'Event', 'Audio']))
        self.assertNotIn('audio', fields(['Start', 'End', 'Event']))

    def test_speaker_timer_is_not_the_speaker(self):
        self.assertEqual({'start', 'description', 'bsm'}, fields(['Start', 'Event', 'Speaker Timer', 'BSM']))

    def test_rule_needs_start_a_description_and_one_more(self):
        self.assertIsNone(header_map(['Start', 'Event']))
        self.assertIsNone(header_map(['End', 'Event', 'Presenter']))
        self.assertIsNone(header_map(['Start', 'End', 'Presenter']))


class NoHeaderMessageTests(SimpleTestCase):

    def message(self, cells, document=False):
        with self.assertRaises(ShowflowError) as caught:
            rows_from_tables([[[cells]]], document)
        return caught.exception

    def test_names_the_best_row_and_the_missing_description(self):
        error = self.message(['CUE', 'Start', 'End', 'Duration', 'Topic', 'Presenter', 'Video', 'Audio'])
        self.assertEqual('Found a header row with CUE, Start, End, Duration, Topic, Presenter… but no '
                         'column Mic Planner recognises as the description.', str(error))
        self.assertEqual('unknown', error.layout)

    def test_names_a_missing_start(self):
        self.assertIn('recognises as the start time.', str(self.message(['Cue', 'Time', 'Event', 'Presenter'])))

    def test_start_and_description_alone(self):
        self.assertEqual('Found a header row with Start, Event but no End, Speaker or BSM column.',
                         str(self.message(['Start', 'Event'])))

    def test_the_closest_of_several_rows_is_named(self):
        table = [['Audio', 'Notes', '', ''], ['Start', 'End', 'Audio', 'Topic']]
        with self.assertRaisesMessage(ShowflowError, 'Found a header row with Start, End, Audio, Topic'):
            rows_from_tables([[table]])

    def test_nothing_like_a_header_keeps_the_general_message(self):
        self.assertIn("Couldn't find the column header", str(self.message(['When', 'What', 'Who'])))

    def test_a_near_header_beats_document_headings(self):
        self.assertIn('Found a header row', str(self.message(['Start', 'Event'], document=True)))

    def test_document_layout_from_a_real_pdf(self):
        with self.assertRaises(ShowflowError) as caught:
            extract(F.build_document_pdf(F.DOCUMENT_LINES))
        self.assertEqual('document', caught.exception.layout)
        self.assertIn('laid out as a document, not a table', str(caught.exception))

    def test_a_tableless_page_without_those_headings_is_no_document(self):
        with self.assertRaises(ShowflowError) as caught:
            extract(F.build_document_pdf(['A letter about the event, its time and support.', 'Hello.']))
        self.assertEqual('unknown', caught.exception.layout)

    def test_the_words_in_a_long_sentence_are_no_headings(self):
        line = 'At this time the event needs a presenter and some support from the crew on site'
        with self.assertRaises(ShowflowError) as caught:
            extract(F.build_document_pdf([line]))
        self.assertEqual('unknown', caught.exception.layout)


HEADER = ['Line', 'Start', 'End', 'Description', 'Speaker', 'Notes']


class RowFilterTests(SimpleTestCase):

    def rows(self, *tables):
        return rows_from_tables([[list(t)] for t in tables])

    def test_titles_above_a_repeated_header_are_dropped(self):
        rows, _, _ = self.rows(
            [HEADER, ['1', '8:00 AM', '8:30 AM', 'Open', 'Ann Reed', '']],
            [['Acme Forum', '', '', '', '', ''], ['Thursday', '', '', '', '', ''], HEADER,
             ['2', '8:30 AM', '9:00 AM', 'Close', 'Ann Reed', '']])
        self.assertEqual(['1', '2'], [r['line'] for r in rows])

    def test_a_line_number_or_real_row_above_a_repeated_header_stays(self):
        rows, _, _ = self.rows(
            [HEADER, ['1', '8:00 AM', '8:30 AM', 'Open', 'Ann Reed', ''],
             ['2', '', '', '', '', ''], ['', '', '', 'Stage note', '', ''], HEADER,
             ['3', '8:30 AM', '9:00 AM', 'Close', 'Ann Reed', '']])
        self.assertEqual(['1', '2', '', '3'], [r['line'] for r in rows])

    def test_a_note_in_the_line_column_with_no_repeated_header_stays(self):
        rows, _, _ = self.rows([HEADER, ['1', '8:00 AM', '8:30 AM', 'Open', '', ''],
                                ['Stage note', '', '', '', '', '']])
        self.assertEqual(['1', 'Stage note'], [r['line'] for r in rows])

    def test_a_cell_saying_nobody_is_blank(self):
        for cell in ('X', 'x', '-', '–', '—', 'n/a', 'N/A'):
            with self.subTest(cell):
                rows, _, _ = self.rows([HEADER, ['1', '8:00 AM', '8:30 AM', 'Open', cell, '']])
                self.assertEqual('', rows[0]['speaker'])

    def test_a_name_with_an_x_in_it_is_kept(self):
        rows, _, _ = self.rows([HEADER, ['1', '8:00 AM', '8:30 AM', 'Open', 'X Lee', '']])
        self.assertEqual('X Lee', rows[0]['speaker'])

    def test_appendix_stops_the_rows_for_the_rest_of_the_file(self):
        rows, _, warnings = self.rows(
            [HEADER, ['1', '8:00 AM', '8:30 AM', 'Open', '', ''], ['', 'Preset', 'Nickname', '', '', ''],
             ['', '1', 'Full Canvas', '', 'Screens', '']],
            [HEADER, ['', '2', 'Content', '', 'Backplate', '']])
        self.assertEqual(['1'], [r['line'] for r in rows])
        self.assertIn('Page 1: "Preset" starts a table', warnings[0])

    def test_text_in_start_alone_is_no_appendix(self):
        rows, _, warnings = self.rows([HEADER, ['1', '8:00 AM', '8:30 AM', 'Open', '', ''],
                                       ['', 'Roll Records', '', '', '', ''],
                                       ['', '0:05:13', 'End of video', 'Clip', '', ''],
                                       ['2', '8:30 AM', '9:00 AM', 'Close', '', '']])
        self.assertEqual(4, len(rows))
        self.assertFalse([w for w in warnings if 'starts a table' in w])

    def test_text_in_both_before_any_clock_time_is_no_appendix(self):
        rows, _, _ = self.rows([HEADER, ['', 'Setup', 'Crew', '', '', ''],
                                ['1', '8:00 AM', '8:30 AM', 'Open', '', '']])
        self.assertEqual(2, len(rows))


class ClientFLayoutTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows, cls.columns, cls.warnings, cls.pages = extract(F.build_pdf(F.CLIENT_F_PAGES))
        cls.result = analyse(cls.rows, crew=[])
        cls.by_line = {r['line']: i for i, r in enumerate(cls.rows) if r['line']}

    def lines(self, indexes):
        return [self.rows[i]['line'] or self.rows[i]['description'][:12] for i in indexes]

    def test_columns(self):
        mapped = {c['header']: c['field'] for c in self.columns if c['field']}
        self.assertEqual({'CUE': 'line', 'Start': 'start', 'End': 'end', 'Duration': 'duration',
                          'Event': 'description', 'Presenter': 'speaker', 'Audio': 'audio', 'Notes': 'notes'},
                         mapped)

    def test_rows_hold_no_titles_or_appendix(self):
        text = ' '.join(' '.join(str(v) for v in r.values()) for r in self.rows)
        for word in ('Acme Forum Day', 'Thursday', 'Nickname', 'Millumin', 'Outboard'):
            self.assertNotIn(word, text)
        self.assertEqual('PRESETS', self.rows[-1]['start'])
        self.assertTrue([w for w in self.warnings if 'Page 2: "Preset"' in w])

    def test_people_and_flags(self):
        self.assertEqual({'Ann Reed', 'Bo Lund', 'Cleo Hart', 'Ned Marsh', 'Tom Kerr', 'Sue Tran'},
                         set(self.result.people))
        self.assertEqual([], [f for f in self.result.flags if f[0] == 'unmatched_speaker'])

    def test_first_name_and_initial_is_on_the_chat(self):
        chat = self.by_line['105']
        for name in ('Cleo Hart', 'Ned Marsh', 'Tom Kerr'):
            self.assertIn(chat, self.result.people[name]['rows'])

    def test_x_lets_doors_and_breaks_read_as_breaks(self):
        from planner.mic_plan.parser import segment_heading
        doors = self.by_line['100']
        self.assertTrue(segment_heading(self.rows, doors, doors + 1, minutes=15)[1])

    def test_exit_lines(self):
        people = self.result.people
        self.assertEqual(['Ann departs'], [self.rows[i]['description'] for i in people['Ann Reed']['exits']])
        self.assertEqual(1, len(people['Bo Lund']['exits']))
        self.assertEqual(['Cleo intros Sue, shakes hands, then departs stage'],
                         [self.rows[i]['description'] for i in people['Cleo Hart']['exits']])
        self.assertEqual(['Sue Tran exits'], [self.rows[i]['description'] for i in people['Sue Tran']['exits']])

    def test_audio_is_read_with_the_row(self):
        self.assertEqual('Lav 2', self.rows[self.by_line['103']]['audio'])
        self.assertIn('A2: Mic Presenters', self.rows[self.by_line['100']]['audio'])


class ExitWordingTests(SimpleTestCase):

    def setUp(self):
        self.roster = Roster()
        for name in ('Gil Vale', 'Nia Bell', 'Jo Hart'):
            self.roster.add(name)
        self.refs = Refs(self.roster)

    def exits(self, text):
        return exits_and_entries(text, self.roster, self.refs)[0]

    def test_departs(self):
        self.assertEqual(['Gil Vale'], self.exits('Gil departs'))
        self.assertEqual(['Gil Vale'], self.exits('Gil Vale departing'))
        self.assertEqual(['Gil Vale', 'Nia Bell'], self.exits('Gil and Nia depart'))

    def test_walks_off(self):
        self.assertEqual(['Nia Bell'], self.exits('Nia walks off'))
        self.assertEqual(['Nia Bell'], self.exits('Slide 105, Nia walks off stage, Preset 5'))

    def test_then_departs_is_the_sentence_opener(self):
        self.assertEqual(['Nia Bell'], self.exits('Nia intros Jo, shakes hands, then departs stage'))

    def test_then_with_no_name_opening_is_nobody(self):
        self.assertEqual([], self.exits('Lights fade, then departs'))

    def test_departure_is_no_exit(self):
        self.assertEqual([], self.exits('Gil confirms departure'))

    def test_a_group_departs(self):
        from planner.mic_plan.parser import group_exit
        self.assertEqual(('all', []), group_exit('All depart'))


class InitialTests(SimpleTestCase):

    def names(self, text, *people):
        roster = Roster()
        for name in people:
            roster.add(name)
        return split_cell(text, roster, discover=True)

    def test_initial_of_the_surname_is_part_of_the_name(self):
        self.assertEqual((['Tom Kerr', 'Ned Marsh'], []), self.names('Tom K. Ned', 'Tom Kerr', 'Ned Marsh'))

    def test_another_initial_is_not(self):
        names, leftovers = self.names('Tom T. Ned', 'Tom Kerr', 'Ned Marsh')
        self.assertNotEqual(['Tom Kerr', 'Ned Marsh'], names)


class ClientFImportTests(MicPlanBase):

    def upload(self, data, name='client.pdf'):
        self.use(self.editor)
        return self.client.post(reverse('planner:mic_plan_upload'), {
            'day': self.day.pk, 'showflow': SimpleUploadedFile(name, data)}, follow=True)

    def test_imports_stores_audio_and_plans(self):
        self.upload(F.build_pdf(F.CLIENT_F_PAGES))
        part = ShowflowImport.objects.get(status='active')
        self.assertEqual('Lav 2', ShowflowRow.objects.get(showflow_import=part, line_no='103').audio_text)
        self.assertEqual(6, ShowflowPerson.objects.filter(day=self.day).count())
        plan = planning.generate(self.day)
        self.assertEqual('line estimates', plan.cue_mode)
        ann = plan.appearances.get(person_name='Ann Reed')
        self.assertLessEqual(ann.off_min, 9 * 60)     # off at "Ann departs", before Bo's segment

    def test_reread_keeps_audio_and_people(self):
        self.upload(F.build_pdf(F.CLIENT_F_PAGES))
        part = ShowflowImport.objects.get(status='active')
        from planner.mic_plan import importer
        importer.reread(part)
        self.assertEqual('Lav 1', part.rows.get(line_no='102').audio_text)
        self.assertEqual(6, ShowflowPerson.objects.filter(day=self.day).count())

    def test_document_on_an_empty_day_points_to_mic_tracker(self):
        resp = self.upload(F.build_document_pdf(F.DOCUMENT_LINES))
        self.assertContains(resp, 'laid out as a document, not a table')
        self.assertContains(resp, 'directly in Mic Tracker')
        self.assertNotContains(resp, 'Add person)')
        self.assertFalse(ShowflowImport.objects.exists())

    def test_document_on_a_day_with_a_part_offers_add_person(self):
        self.upload(F.build_pdf(F.CLIENT_F_PAGES))
        resp = self.upload(F.build_document_pdf(F.DOCUMENT_LINES))
        self.assertContains(resp, 'adding people by hand (People → Add person)')
        self.assertEqual(1, ShowflowImport.objects.count())

    def test_header_text_in_the_message_is_escaped(self):
        cells = ['<b>Cue</b>', 'Start', 'End']
        resp = self.upload(F.build_pdf([[cells, ['1', '8:00 AM', '8:30 AM']]]))
        self.assertContains(resp, '&lt;b&gt;Cue&lt;/b&gt;')
        self.assertNotContains(resp, '<b>Cue</b>')

    def test_layout_is_logged_without_the_file_name(self):
        for data, kind in ((F.build_document_pdf(F.DOCUMENT_LINES), 'layout document'),
                           (F.build_pdf(F.NO_HEADER_PAGES), 'layout unknown'),
                           (F.build_pdf(F.CLIENT_F_PAGES), 'layout table')):
            with self.subTest(kind), self.assertLogs('planner.mic_plan.importer', 'INFO') as logs:
                self.upload(data, name='secret-client-name.pdf')
            text = ' '.join(logs.output)
            self.assertIn(kind, text)
            self.assertNotIn('secret-client-name', text)
