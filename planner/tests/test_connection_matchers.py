"""The connection matchers: rules (a), (b), (c) and their verdicts.

The rules and verdicts are documented in planner/connections/matchers.py.

Run with::

    python manage.py test planner.tests.test_connection_matchers \\
        --settings=audiopatch.test_settings
"""
from django.test import TestCase

from planner.connections import matchers as m
from planner.tests.connection_fixtures import ConnectionFixtures


def _refs(ports):
    return {p if isinstance(p, str) else p.ref for p in ports}


def _ref(model, obj):
    return f'{model}:{obj.pk}'


class RuleATests(ConnectionFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.sl = self.p1('SL P1')
        self.desk = self.console()
        self.box = self.device('Stage Box')

    def match_for(self, source_ref):
        index = m.ProjectIndex.load(self.project)
        return next(x for x in m.rule_a(index) if x.source.ref == source_ref)

    def test_io_output_matches_a_unique_input_label(self):
        port = self.p1_in(self.sl, 'AES', 1, 'L Main')
        out = self.device_output(self.box, 1, 'L Main')
        match = self.match_for(_ref('deviceoutput', out))
        self.assertEqual(match.verdict, m.MATCHED)
        self.assertEqual(_refs(match.targets), {_ref('p1input', port)})

    def test_matrix_destination_by_label(self):
        port = self.p1_in(self.sl, 'AES', 2, 'R Main')
        mtx = self.matrix(self.desk, 2, 'Main R', destination='R Main')
        match = self.match_for(_ref('consolematrixoutput', mtx))
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'label'))
        self.assertEqual(_refs(match.targets), {_ref('p1input', port)})

    def test_matrix_destination_as_processor_type_and_number(self):
        port = self.p1_in(self.sl, 'AES', 3, '')
        mtx = self.matrix(self.desk, 3, destination='sl p1  AES 3')
        match = self.match_for(_ref('consolematrixoutput', mtx))
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'typed'))
        self.assertEqual(_refs(match.targets), {_ref('p1input', port)})

    def test_matrix_destination_as_processor_name_is_device_level(self):
        mtx = self.matrix(self.desk, 4, destination='SL P1')
        match = self.match_for(_ref('consolematrixoutput', mtx))
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'name'))
        self.assertEqual(match.targets, (f'processor:{self.sl.pk}',))

    def test_same_label_on_aes_and_analog_of_one_processor_is_certain(self):
        aes = self.p1_in(self.sl, 'AES', 1, 'L Main')
        analog = self.p1_in(self.sl, 'ANALOG', 1, 'L Main')
        mtx = self.matrix(self.desk, 1, destination='L Main')
        match = self.match_for(_ref('consolematrixoutput', mtx))
        self.assertEqual(match.verdict, m.SAME_PROCESSOR)
        self.assertEqual(_refs(match.targets), {_ref('p1input', aes), _ref('p1input', analog)})
        self.assertEqual(match.candidates, ())

    def test_same_label_on_two_processors_is_ambiguous(self):
        sr = self.p1('SR P1')
        a = self.p1_in(self.sl, 'AES', 1, 'Main')
        b = self.p1_in(sr, 'AES', 1, 'Main')
        out = self.device_output(self.box, 1, 'Main')
        match = self.match_for(_ref('deviceoutput', out))
        self.assertEqual(match.verdict, m.AMBIGUOUS)
        self.assertEqual(match.targets, ())
        self.assertEqual(_refs(match.candidates), {_ref('p1input', a), _ref('p1input', b)})

    def test_two_processors_sharing_a_name_is_ambiguous(self):
        twin = self.p1('SL P1')
        mtx = self.matrix(self.desk, 5, destination='SL P1')
        match = self.match_for(_ref('consolematrixoutput', mtx))
        self.assertEqual(match.verdict, m.AMBIGUOUS)
        self.assertEqual(set(match.candidates),
                         {f'processor:{self.sl.pk}', f'processor:{twin.pk}'})

    def test_matrix_out_through_a_matched_io_output_is_not_counted_twice(self):
        self.p1_in(self.sl, 'AES', 1, 'L Main')
        mtx = self.matrix(self.desk, 1, 'L Main', destination='L Main')
        out = self.device_output(self.box, 1, 'L Main', bus=mtx)
        self.assertEqual(self.match_for(_ref('deviceoutput', out)).verdict, m.MATCHED)
        self.assertEqual(self.match_for(_ref('consolematrixoutput', mtx)).verdict, m.VIA_IO)

    def test_matrix_out_through_an_io_output_to_another_processor_still_counts(self):
        sr = self.p1('SR P1')
        self.p1_in(self.sl, 'AES', 1, 'Fill')
        self.p1_in(sr, 'AES', 1, 'Front')
        mtx = self.matrix(self.desk, 1, 'Fill', destination='Front')
        self.device_output(self.box, 1, 'Fill', bus=mtx)
        self.assertEqual(self.match_for(_ref('consolematrixoutput', mtx)).verdict, m.MATCHED)

    def test_dash_case_and_whitespace_variants_match(self):
        port = self.p1_in(self.sl, 'AES', 1, 'Front  Fill – L')
        out = self.device_output(self.box, 1, 'front fill - l')
        match = self.match_for(_ref('deviceoutput', out))
        self.assertEqual(_refs(match.targets), {_ref('p1input', port)})

    def test_blank_text_is_not_a_source_and_blank_labels_never_match(self):
        self.device_output(self.box, 1, '')
        self.matrix(self.desk, 1, destination='   ')
        index = m.ProjectIndex.load(self.project)
        self.assertEqual(m.rule_a(index), [])
        out = self.device_output(self.box, 2, 'Spare')   # every P1 input label is blank
        self.assertEqual(self.match_for(_ref('deviceoutput', out)).verdict, m.UNMATCHED)

    def test_template_consoles_and_other_projects_are_ignored(self):
        other = self.make_project('other show')
        theirs = self.p1('Other P1', project=other)
        self.p1_in(theirs, 'AES', 1, 'L Main')
        self.matrix(self.console('Template', is_template=True), 1, destination='L Main')
        out = self.device_output(self.box, 1, 'L Main')
        index = m.ProjectIndex.load(self.project)
        self.assertEqual([x.source.ref for x in m.rule_a(index)], [_ref('deviceoutput', out)])
        self.assertEqual(m.rule_a(index)[0].verdict, m.UNMATCHED)


class RuleBTests(ConnectionFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.sl = self.p1('SL P1')
        self.amp_ = self.amp('SL LA12X #1')

    def matches(self):
        return m.rule_b(m.ProjectIndex.load(self.project))

    def test_avb_stream_matches_channel_and_label(self):
        port = self.p1_out(self.sl, 'AVB', 3, 'L Main')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 3 - L Main')
        [match] = self.matches()
        self.assertEqual((match.verdict, match.field, match.transport),
                         (m.MATCHED, 'avb_stream', 'avb'))
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_avb_stream_on_two_processors_without_suffix_is_ambiguous(self):
        sr = self.p1('SR P1')
        self.p1_out(self.sl, 'AVB', 3, 'L Main')
        self.p1_out(sr, 'AVB', 3, 'L Main')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 3 - L Main')
        [match] = self.matches()
        self.assertEqual(match.verdict, m.AMBIGUOUS)
        self.assertEqual(len(match.candidates), 2)

    def test_processor_suffix_picks_the_processor(self):
        sr = self.p1('SR P1')
        self.p1_out(self.sl, 'AVB', 3, 'L Main')
        port = self.p1_out(sr, 'AVB', 3, 'L Main')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 3 - L Main (SR P1)')
        [match] = self.matches()
        self.assertEqual(match.verdict, m.MATCHED)
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_a_bracket_that_is_not_a_processor_is_part_of_the_label(self):
        port = self.p1_out(self.sl, 'AES', 1, 'Sub (Cardioid)')
        self.amp_channel(self.amp_, 1, aes_input='Sub (Cardioid)')
        [match] = self.matches()
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_two_outputs_of_one_type_on_one_processor_is_same_processor(self):
        a = self.p1_out(self.sl, 'AES', 1, 'Sub')
        b = self.p1_out(self.sl, 'AES', 2, 'Sub')
        self.amp_channel(self.amp_, 1, aes_input='Sub')
        [match] = self.matches()
        self.assertEqual(match.verdict, m.SAME_PROCESSOR)
        self.assertEqual(_refs(match.targets), {_ref('p1output', a), _ref('p1output', b)})

    def test_renamed_avb_output_is_drift(self):
        port = self.p1_out(self.sl, 'AVB', 3, 'Left Main')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 3 - L Main')
        [match] = self.matches()
        self.assertEqual(match.verdict, m.DRIFT)
        self.assertEqual(_refs(match.candidates), {_ref('p1output', port)})

    def test_aes_text_only_matches_aes_outputs(self):
        self.p1_out(self.sl, 'AVB', 1, 'Front')
        self.p1_out(self.sl, 'ANALOG', 1, 'Front')
        self.amp_channel(self.amp_, 1, aes_input='Front')
        [match] = self.matches()
        self.assertEqual(match.verdict, m.UNMATCHED)

    def test_avb_and_aes_on_one_channel_are_two_matches(self):
        self.p1_out(self.sl, 'AVB', 1, 'Front')
        self.p1_out(self.sl, 'AES', 1, 'Front')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 1 - Front', aes_input='Front')
        fields = sorted((x.field, x.verdict) for x in self.matches())
        self.assertEqual(fields, [('aes_input', m.MATCHED), ('avb_stream', m.MATCHED)])

    def test_galaxy_outputs_match_too(self):
        gx = self.galaxy('Delay Galaxy')
        port = self.galaxy_out(gx, 'ANALOG', 2, 'Delay 2')
        self.amp_channel(self.amp_, 2, analog_input='Delay 2')
        [match] = self.matches()
        self.assertEqual(_refs(match.targets), {_ref('galaxyoutput', port)})

    def test_free_text_that_parses_as_nothing_is_unmatched(self):
        self.amp_channel(self.amp_, 1, analog_input='from the P1 somewhere')
        [match] = self.matches()
        self.assertEqual(match.verdict, m.UNMATCHED)


class RuleCTests(ConnectionFixtures, TestCase):
    """Free-text PA rows: Destination is the speaker array; the amp end is the
    Amp FK or nothing; the PA Zone (Label) is the cable's label, never an end."""

    def setUp(self):
        super().setUp()
        self.pred = self.prediction()

    def match(self, row):
        [cm] = [x for x in m.rule_c(m.ProjectIndex.load(self.project)) if x.row.pk == row.pk]
        return cm

    def test_destination_matches_an_array_by_base_display_or_source_name(self):
        arr = self.array(self.pred, 'K2 Main L', source_name='K2 Main L_YZ Sym')
        for text in ('k2  main l', 'K2 Main L_YZ Sym'):
            with self.subTest(text=text):
                end = self.match(self.text_cable(destination=text)).speaker
                self.assertEqual((end.verdict, end.target, end.via),
                                 (m.MATCHED, f'speaker_array:{arr.pk}', 'array'))

    def test_same_array_name_in_two_predictions_is_ambiguous(self):
        a = self.array(self.pred, 'Sub L')
        b = self.array(self.prediction(file_name='day2.pdf'), 'Sub L')
        end = self.match(self.text_cable(destination='Sub L')).speaker
        self.assertEqual(end.verdict, m.AMBIGUOUS)
        self.assertEqual(set(end.candidates), {f'speaker_array:{a.pk}', f'speaker_array:{b.pk}'})

    def test_unknown_or_blank_destination_is_unmatched(self):
        for text in ('Somewhere', ''):
            with self.subTest(text=text):
                end = self.match(self.text_cable(destination=text)).speaker
                self.assertEqual((end.verdict, end.text), (m.UNMATCHED, text))

    def test_the_pa_zone_is_never_matched_against_arrays(self):
        self.array(self.pred, 'HR')
        end = self.match(self.text_cable(self.zone('HR'), destination='')).speaker
        self.assertEqual(end.verdict, m.UNMATCHED)

    def test_amp_end_is_the_fk(self):
        amp = self.amp('SL LA12X #1')
        end = self.match(self.text_cable(destination='x', amp=amp)).amp
        self.assertEqual((end.verdict, end.via, end.target), (m.MATCHED, 'fk', f'amp:{amp.pk}'))

    def test_amp_end_without_fk_is_never_guessed_from_text(self):
        self.amp('Sub Amp', rack='Sub Amp')
        end = self.match(self.text_cable(destination='Sub Amp')).amp
        self.assertEqual(end.verdict, m.UNMATCHED)

    def test_linked_rows_are_not_matched(self):
        self.linked_cable(self.amp('A'), self.array(self.pred, 'X'))
        self.assertEqual(m.rule_c(m.ProjectIndex.load(self.project)), [])
