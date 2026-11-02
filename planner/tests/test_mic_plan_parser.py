"""Mic Plan parser: header detection, times, people, send/catch and flags.

Runs the real pipeline (ReportLab-built PDF -> pdfplumber -> parser) on the
scrubbed fixture in showflow_fixture.py, plus a few pure-function checks.

Run with::

    python manage.py test planner.tests.test_mic_plan_parser --settings=audiopatch.test_settings
"""

from unittest import mock

from django.test import SimpleTestCase

from planner.mic_plan.extract import ShowflowError, extract, header_map, rows_from_tables
from planner.mic_plan.parser import (
    analyse, hm, name_key, parse_clock, resolve_clock, segment_heading,
)
from planner.tests import showflow_fixture as F


def _flags(result, kind):
    return [f for f in result.flags if f[0] == kind]


class MainFixtureTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows, cls.columns, cls.warnings, cls.pages = extract(F.build_pdf(F.MAIN_PAGES))
        cls.result = analyse(cls.rows)
        cls.by_line = {row['line']: i for i, row in enumerate(cls.rows)}

    def events(self, kind, name):
        return [self.rows[e.row]['line'] for e in self.result.events
                if e.kind == kind and e.name == name]

    def test_header_on_page_one_maps_the_later_pages(self):
        self.assertEqual(3, self.pages)
        self.assertEqual([], self.warnings)
        self.assertEqual(['100', '118'], [self.rows[0]['line'], self.rows[-1]['line']])
        self.assertEqual({1, 2, 3}, {row['page_no'] for row in self.rows})
        fields = [c['field'] for c in self.columns]
        self.assertEqual('line', fields[0])          # the blank first column
        self.assertIn('bsm', fields)
        self.assertIsNone(fields[HEADER_INDEX['Location']])

    def test_crew_is_detected_on_a_first_import(self):
        self.assertEqual({'Sam', 'Lee', 'Rio'}, set(self.result.crew))

    def test_people_come_from_welcome_titles_and_speaker_cells(self):
        self.assertEqual(
            {'Alex Host', 'Jo Emcee', 'Pat Guest', 'Dana Able', 'Chris Baker', 'Robin Cole',
             'Taylor Eve', 'Morgan Dee', 'Kim Keynote', 'KK'},
            set(self.result.people))

    def test_pickle_is_a_clicker_not_a_person_or_a_mic(self):
        self.assertFalse(any('pickle' in name.lower() for name in self.result.people))
        self.assertEqual('', self.result.people['Robin Cole']['mic_hint'])
        self.assertEqual('', self.result.people['Dana Able']['mic_hint'])

    def test_mic_hints_only_from_explicit_callouts(self):
        hints = {n: p['mic_hint'] for n, p in self.result.people.items() if p['mic_hint']}
        self.assertEqual({'Jo Emcee': 'backup', 'Pat Guest': 'HH'}, hints)

    def test_send_list_stops_at_the_first_word_that_is_not_joined(self):
        # "Sam sends Dana, Chris, Robin and Morgan Robin and Dana have pickles"
        sent = {e.name for e in self.result.events if e.kind == 'send'
                and self.rows[e.row]['line'] == '108'}
        self.assertEqual({'Dana Able', 'Chris Baker', 'Robin Cole', 'Morgan Dee'}, sent)
        self.assertEqual(['108'], self.events('send', 'Robin Cole'))

    def test_catch_split_across_a_page_break_is_joined(self):
        # Line 110 (page 2) "Lee Catches Dana," + line 111 (page 3) "Chris, and Robin".
        for name in ('Dana Able', 'Chris Baker', 'Robin Cole'):
            with self.subTest(name=name):
                self.assertEqual(['110'], self.events('catch', name))
        # ...and the cue after it on line 111 still reads.
        self.assertIn('111', self.events('send', 'Alex Host'))

    def test_run_times_are_not_clock_times_and_missing_am_pm_resolves(self):
        times = self.result.times
        self.assertFalse(times[self.by_line['101']].exact)           # 0:05:13
        self.assertEqual('8:10a', hm(times[self.by_line['105']].minute))  # 8:10:00
        self.assertTrue(times[self.by_line['104']].is_segment)
        self.assertEqual(('8:00a', '8:30a'), (hm(times[self.by_line['104']].t0),
                                              hm(times[self.by_line['104']].t1)))

    def test_event_times(self):
        minute = {(e.kind, e.name, self.rows[e.row]['line']): hm(e.minute) for e in self.result.events}
        self.assertEqual('8:00a', minute[('send', 'Alex Host', '103')])   # next segment
        self.assertEqual('9:00a', minute[('catch', 'Dana Able', '110')])  # next segment
        # Sent and caught on one row: the send plus the row's 0:05:00.
        self.assertEqual('8:35a', hm(minute_of(self.result, 'catch', 'Pat Guest') ))

    def test_caught_but_still_listed(self):
        flagged = {f[3] for f in _flags(self.result, 'caught_but_listed')}
        self.assertEqual({'Alex Host', 'Kim Keynote'}, flagged)
        text = next(f[2] for f in _flags(self.result, 'caught_but_listed') if f[3] == 'Kim Keynote')
        self.assertIn('Keynote Conversation', text)
        # The flag stands in for "no cue" in that segment; it is not both.
        self.assertFalse([f for f in _flags(self.result, 'no_cue')
                          if f[3] == 'Kim Keynote'])

    def test_sent_but_never_caught(self):
        self.assertEqual({'Morgan Dee'}, {f[3] for f in _flags(self.result, 'never_caught')})

    def test_speaker_with_no_send_or_catch(self):
        flagged = {(f[3], self.rows[f[1]]['line']) for f in _flags(self.result, 'no_cue')}
        self.assertIn(('Taylor Eve', '109'), flagged)
        self.assertIn(('Jo Emcee', '102'), flagged)

    def test_unmatched_speaker_text(self):
        texts = [f[2] for f in _flags(self.result, 'unmatched_speaker')]
        self.assertEqual(1, len(texts), texts)
        self.assertIn('"Customer Panel Group 1-5"', texts[0])

    def test_bsm_only_name(self):
        self.assertTrue(self.result.people['KK']['bsm_only'])
        self.assertEqual(['KK'], [f[3] for f in _flags(self.result, 'bsm_only')])

    def test_a_merge_turns_a_nickname_into_its_person(self):
        result = analyse(self.rows, crew=['Sam', 'Lee', 'Rio'], known=[('Kim Keynote', ['KK'])])
        self.assertNotIn('KK', result.people)
        self.assertEqual(['117'], [self.rows[e.row]['line'] for e in result.events
                                   if e.name == 'Kim Keynote' and e.kind == 'send'
                                   and self.rows[e.row]['line'] == '117'])
        self.assertFalse(_flags(result, 'bsm_only'))

    def test_crew_names_decide_which_cues_are_read(self):
        result = analyse(self.rows, crew=['Sam', 'Rio'])
        self.assertFalse([e for e in result.events if self.rows[e.row]['line'] == '110'])
        unknown = _flags(result, 'unknown_crew')
        self.assertTrue(any('Lee' in f[2] for f in unknown))

    def test_span(self):
        self.assertEqual(('7:00a', '10:30a'), (hm(self.result.span[0]), hm(self.result.span[1])))


HEADER_INDEX = {name: i for i, name in enumerate(F.HEADER_14)}


def minute_of(result, kind, name):
    return next(e.minute for e in result.events if e.kind == kind and e.name == name)


class LayoutTests(SimpleTestCase):

    def test_nine_column_layout_with_line_hash(self):
        rows, columns, warnings, _ = extract(F.build_pdf(F.NINE_COLUMN_PAGES))
        self.assertEqual(['1', '2', '3', '4'], [r['line'] for r in rows])
        self.assertEqual('', rows[0]['notes'])  # no Notes column: blank, not an error
        result = analyse(rows)
        self.assertEqual({('send', 'Pat Guest'), ('catch', 'Pat Guest')},
                         {(e.kind, e.name) for e in result.events})
        # Caught after the last segment starts: off when that segment ends.
        self.assertEqual('9:40a', hm(minute_of(result, 'catch', 'Pat Guest')))

    def test_unknown_layout_is_a_clear_error(self):
        with self.assertRaisesMessage(ShowflowError, "Couldn't find the column header"):
            extract(F.build_pdf(F.NO_HEADER_PAGES))

    def test_not_a_pdf(self):
        with self.assertRaisesMessage(ShowflowError, 'not a PDF'):
            extract(b'hello')

    def test_too_many_pages_is_refused_before_reading(self):
        with self.assertRaisesMessage(ShowflowError, 'reads up to 2'):
            extract(F.build_pdf(F.MAIN_PAGES), max_pages=2)

    def test_a_slow_file_stops_at_the_time_budget(self):
        with self.assertRaisesMessage(ShowflowError, 'taking too long'):
            extract(F.build_pdf(F.MAIN_PAGES), time_budget=-1)

    def test_header_needs_more_than_start(self):
        self.assertIsNone(header_map(['Start', 'Description']))
        self.assertEqual({0: 'line', 1: 'start', 2: 'description', 3: 'bsm'},
                         header_map(['LINE #', 'Start', 'Description', 'BSM']))

    def test_missing_bsm_column_is_a_warning(self):
        rows, _, warnings = rows_from_tables([[[
            ['', 'Start', 'End', 'Description', 'Speaker Name'],
            ['1', '9:00 AM', '9:10 AM', 'Hi', 'Pat Guest'],
        ]]])
        self.assertEqual(1, len(rows))
        self.assertTrue(any('No BSM column' in w for w in warnings))


class ClockTests(SimpleTestCase):

    def test_parse_clock(self):
        self.assertEqual((7, 45, 'A'), parse_clock('7:45A'))
        self.assertEqual((7, 0, 'A'), parse_clock('7:00 AM'))
        self.assertEqual((8, 46, None), parse_clock('8:46:00'))
        self.assertIsNone(parse_clock('0:05:13'))       # video run time
        self.assertIsNone(parse_clock('00:04:08:00'))   # timecode
        self.assertIsNone(parse_clock('0:25'))

    def test_missing_am_pm_reads_closest_after_the_last_anchor(self):
        self.assertEqual(10 * 60 + 18, resolve_clock((10, 18, None), 10 * 60 + 10))
        self.assertEqual(15 * 60 + 49, resolve_clock((3, 49, None), 15 * 60 + 45))
        self.assertIsNone(resolve_clock((3, 49, None), 9 * 60))  # too far ahead either way

    def test_explicit_time_drops_an_earlier_guess_past_it(self):
        rows = [dict(line=str(n), start=s, end=e, duration=d, description='x', speaker='', bsm='',
                     notes='')
                for n, (s, e, d) in enumerate([('10:40 AM', '10:41 AM', '0:01:00'),
                                               ('10:45:00', '', ''),
                                               ('10:41 AM', '11:10 AM', '0:29:00')])]
        result = analyse(rows, crew=[])
        self.assertTrue(result.times[2].exact)
        self.assertFalse(result.times[1].exact)
        self.assertFalse(_flags(result, 'time_backwards'))


class UpperCaseLayoutTests(SimpleTestCase):
    """Legend rows above the header, upper-case and wrapped headers, blank
    Duration, stage directions in Speaker cells."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows, cls.columns, _, _ = extract(F.build_pdf(F.UPPER_PAGES))
        cls.result = analyse(cls.rows)

    def test_header_below_legend_rows_maps_case_insensitively(self):
        mapped = {c['header']: c['field'] for c in self.columns if c['field']}
        self.assertEqual({'LINE #': 'line', 'START': 'start', 'END': 'end',
                          'DURATIO N': 'duration', 'DESCRIPTION': 'description',
                          'SPEAKER': 'speaker', 'BSM': 'bsm'}, mapped)
        self.assertEqual('201', self.rows[0]['line'])   # legend rows are not rows

    def test_segments_without_a_duration(self):
        self.assertEqual(['201', '208', '217', '230'],
                         [self.rows[i]['line'] for i in self.result.segments])

    def test_people_without_titles_companies_or_stage_notes(self):
        self.assertEqual({'Robin Cole', 'Dana Able', 'Kim Keynote', 'Kym', 'Lee Panel',
                          'Max Second'}, set(self.result.people))

    def test_cues_stop_before_bsm_chatter(self):
        sent = [(self.rows[e.row]['line'], e.name) for e in self.result.events if e.kind == 'send']
        self.assertIn(('215', 'Kim Keynote'), sent)   # "...Sends Kim Needs Clicker"
        self.assertEqual({'Ivo', 'Uma'}, set(self.result.crew))
        self.assertTrue(self.result.people['Kym']['bsm_only'])


class LineColumnAndShortDurationTests(SimpleTestCase):
    """Line numbers under an "a" header, H:MM durations, crewless cues, a
    stray clock time, an empty grid page."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pdf = F.build_pdf(F.A_COLUMN_PAGES)
        cls.rows, cls.columns, _, cls.pages = extract(cls.pdf)
        cls.result = analyse(cls.rows)

    def test_line_numbers_found_under_an_odd_header(self):
        self.assertEqual(['101', '105', '106', '119', '120', '121'], [r['line'] for r in self.rows])

    def test_h_mm_durations_mark_segments(self):
        self.assertEqual(['101', '120', '121'], [self.rows[i]['line'] for i in self.result.segments])

    def test_one_stray_time_is_dropped_not_the_ones_after_it(self):
        self.assertEqual(['time_backwards'], [f[0] for f in _flags(self.result, 'time_backwards')])
        self.assertTrue(_flags(self.result, 'time_backwards')[0][2].startswith('Line 119:'))
        self.assertTrue(self.result.times[4].exact)   # 9:00 AM on line 120 kept

    def test_crewless_send_and_no_title_people(self):
        self.assertEqual({'Alex Host', 'Pat Guest'}, set(self.result.people))
        self.assertEqual([('send', 'Alex Host', '9:00a')],
                         [(e.kind, e.name, hm(e.minute)) for e in self.result.events])

    def test_an_empty_grid_page_is_not_searched_for_tables(self):
        import pdfplumber.page
        real = pdfplumber.page.Page.extract_tables
        calls = []

        def counting(page, *args, **kwargs):
            calls.append(page.page_number)
            return real(page, *args, **kwargs)
        with mock.patch.object(pdfplumber.page.Page, 'extract_tables', counting):
            extract(self.pdf)
        self.assertEqual(2, self.pages)
        self.assertEqual([1], calls)


class CueFreeLayoutTests(SimpleTestCase):
    """No send/catch at all, a colour legend and an image, "+" between
    speakers, particles, and handheld callouts that name nobody."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows, _, cls.warnings, _ = extract(F.build_pdf(F.CUE_FREE_PAGES))
        cls.result = analyse(cls.rows)

    def test_reads_with_no_cues(self):
        self.assertEqual([], self.result.events)
        self.assertEqual([], self.result.crew)
        self.assertEqual('101', self.rows[0]['line'])

    def test_names_with_plus_particles_and_st(self):
        self.assertEqual({'Nina Host', 'Nell Avery', 'Rory vandeberg', 'Ike Morrow',
                          'Tess St Clair', 'Clair Dunn'}, set(self.result.people))
        self.assertFalse(_flags(self.result, 'unmatched_speaker'))   # "DJ Audio Throughout"

    def test_a_handheld_callout_naming_nobody_means_the_rows_speakers(self):
        hints = {n: p['mic_hint'] for n, p in self.result.people.items() if p['mic_hint']}
        self.assertEqual({'Nina Host': 'HH', 'Nell Avery': 'HH', 'Rory vandeberg': 'HH',
                          'Ike Morrow': 'HH'}, hints)


class ClientELayoutTests(SimpleTestCase):
    """TITLE: prefixes, "Dr." names, first names that mean whoever was
    introduced last, VOG segment rows, and people named only in a
    description (Client E)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows, cls.columns, _, _ = extract(F.build_pdf(F.CLIENT_E_PAGES))
        cls.result = analyse(cls.rows)

    def lines(self, name):
        return [self.rows[i]['line'] for i in self.result.people[name]['rows']]

    def intro(self, name):
        return self.rows[self.result.people[name]['intro']]['line']

    def test_title_and_n_up_title_prefixes_read_like_titles(self):
        self.assertEqual('304', self.intro('Vic Stone'))
        self.assertIn('Gil Ware', self.result.people)
        self.assertIn('Bo Lark', self.result.people)       # "2-UP TITLE: Bo Lark & Zed Moss"
        self.assertIn('Zed Moss', self.result.people)
        for name in ('Kit Ames', 'Dr. Lou Penn', 'Dr. Sol Tate'):   # "4-UP TITLE: ..."
            self.assertIn('315', self.lines(name))
        self.assertFalse(_flags(self.result, 'unmatched_speaker'))

    def test_dr_stays_in_the_name_and_title_plus_surname_is_no_one_new(self):
        self.assertIn('Dr. Una Reyes', self.result.people)
        self.assertNotIn('Dr Reyes', self.result.people)
        self.assertNotIn('Dr. Reyes', self.result.people)
        self.assertEqual(['306', '307'], self.lines('Dr. Una Reyes'))   # "Ned, Max, Dr. Reyes"

    def test_a_first_name_is_whoever_was_introduced_last(self):
        self.assertIn('305', self.lines('Vic Stone'))      # 304 introduced Vic Stone
        self.assertNotIn('305', self.lines('Vic Dahl'))    # not the later Vic
        self.assertIn('317', self.lines('Vic Dahl'))       # 316 introduced Vic Dahl
        self.assertNotIn('317', self.lines('Vic Stone'))
        self.assertEqual(['308', '309'], self.lines('Gil Ware'))   # "TITLE: Gil Ware", then "Gil"

    def test_two_people_introduced_together_make_a_bare_first_name_ambiguous(self):
        which = _flags(self.result, 'which_first')
        self.assertEqual(['319'], [self.rows[f[1]]['line'] for f in which])
        self.assertTrue(which[0][2].startswith('Line 319: which Vic?'))
        self.assertNotIn('319', self.lines('Vic Stone') + self.lines('Vic Dahl'))

    def test_description_naming_people_no_speaker_cell_has_is_flagged(self):
        flags = _flags(self.result, 'description_names')
        self.assertEqual(['311'], [self.rows[f[1]]['line'] for f in flags])
        self.assertEqual('Line 311: description names people not in the Speaker column — check '
                         'who goes on', flags[0][2])
        self.assertNotIn('Cy Dorn', self.result.people)    # flagged only, not made a person

    def test_intro_is_the_first_line_naming_them_in_full(self):
        self.assertEqual('306', self.intro('Dr. Una Reyes'))
        self.assertEqual('314', self.intro('Dr. Lou Penn'))   # the VOG welcome
        self.assertEqual('301', self.intro('Max Pine'))

    def test_segment_names_skip_vog_and_records_rows_and_breaks_are_marked(self):
        segs = self.result.segments + [len(self.rows)]
        got = [segment_heading(self.rows, s, e) for s, e in zip(segs, segs[1:])]
        self.assertEqual([('Opening Session', False), ('BREAK', True),
                          ('The Future Panel', False)], got)

    def test_no_cues_means_no_no_cue_flags(self):
        self.assertEqual([], self.result.events)
        self.assertFalse(_flags(self.result, 'no_cue'))


class NameAndCoverageTests(SimpleTestCase):

    def test_dr_with_or_without_a_full_stop_is_one_key(self):
        self.assertEqual(name_key('Dr. Ann Lee'), name_key('Dr Ann Lee'))
        self.assertEqual('dr. ann lee', name_key('DR Ann Lee'))
        self.assertEqual('drew ann', name_key('Drew Ann'))

    @staticmethod
    def _row(line, start='', end='', dur='', desc='', speaker='', bsm=''):
        return {'line': line, 'start': start, 'end': end, 'duration': dur, 'description': desc,
                'speaker': speaker, 'bsm': bsm, 'notes': ''}

    def _speakers_in_segments(self, n, cued):
        rows = []
        for k in range(n):
            start, end = 8 * 60 + 15 * k, 8 * 60 + 15 * (k + 1)    # 15-minute talks from 8:00
            rows.append(self._row(str(10 + k), '{}:{:02d} AM'.format(*divmod(start, 60)),
                                  '{}:{:02d} AM'.format(*divmod(end, 60)), '0:15:00',
                                  'Talk {}'.format(k), 'Ann{} Lee'.format(chr(97 + k))))
        rows[0]['bsm'] = 'Sam sends ' + ', '.join('Ann{} Lee'.format(chr(97 + k)) for k in range(cued))
        return analyse(rows, crew=['Sam'])

    def test_a_stray_cue_does_not_turn_every_speaker_into_a_no_cue_flag(self):
        result = self._speakers_in_segments(6, cued=1)     # 1 of 6 cued
        self.assertTrue(result.events)
        self.assertFalse(_flags(result, 'no_cue'))

    def test_cues_for_half_the_speakers_keep_the_no_cue_flags(self):
        result = self._speakers_in_segments(6, cued=3)     # 3 of 6 cued
        self.assertEqual(3, len(_flags(result, 'no_cue')))
