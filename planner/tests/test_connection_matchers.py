"""The connection matchers: rules (a), (b), (c) and their verdicts.

The rules and verdicts are documented in planner/connections/matchers.py.

Run with::

    python manage.py test planner.tests.test_connection_matchers \\
        --settings=audiopatch.test_settings
"""
from django.test import TestCase

from planner.connections import matchers as m
from planner.models import P1Output
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

    def test_amp_end_without_fk_is_never_guessed_from_an_amp_name(self):
        self.amp('Sub Amp', rack='SL Racks')
        cm = self.match(self.text_cable(destination='Sub Amp'))
        self.assertEqual((cm.amp.verdict, cm.speaker.verdict, cm.speaker.via),
                         (m.UNMATCHED, m.UNMATCHED, 'text'))

    def test_linked_rows_are_not_matched(self):
        self.linked_cable(self.amp('A'), self.array(self.pred, 'X'))
        self.assertEqual(m.rule_c(m.ProjectIndex.load(self.project)), [])


class RuleBProdStringsTests(ConnectionFixtures, TestCase):
    """Amp input text as it is really typed (strings from the prod report)."""

    def setUp(self):
        super().setUp()
        self.sl = self.p1('SL P1')
        self.amp_ = self.amp('SL LA12X #1')

    def index(self):
        return m.ProjectIndex.load(self.project)

    def only(self):
        [match] = m.rule_b(self.index())
        return match

    def test_x_dash_and_na_are_placeholders_not_unmatched(self):
        self.amp_channel(self.amp_, 1, avb_stream='x', aes_input='X')
        self.amp_channel(self.amp_, 2, analog_input='-', aes_input='n/a')
        self.amp_channel(self.amp_, 3, avb_stream='  ')
        index = self.index()
        self.assertEqual(m.rule_b(index), [])
        self.assertEqual(sorted(p.text for p in index.amp_placeholders), ['-', 'X', 'n/a', 'x'])

    def test_avb_n_and_a_bare_number_are_avb_output_n(self):
        port = P1Output.objects.get(p1_processor__system_processor=self.sl,
                                    output_type='AVB', channel_number=1)
        for text in ('AVB 1', '1'):
            with self.subTest(text=text):
                self.amp_channel(self.amp_, 1, avb_stream=text)
                match = self.only()
                self.assertEqual((match.verdict, match.via), (m.MATCHED, 'number'))
                self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_single_p1_with_unlabelled_avb_1_is_matched(self):
        port = P1Output.objects.get(p1_processor__system_processor=self.sl,
                                    output_type='AVB', channel_number=1)
        self.assertEqual(port.label, '')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 1')
        match = self.only()
        self.assertEqual((match.verdict, match.excluded), (m.MATCHED, 0))
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_two_p1s_neither_labels_avb_1_is_ambiguous(self):
        self.p1('SR P1')                        # every P1 has AVB 1-8, all blank
        self.amp_channel(self.amp_, 1, avb_stream='AVB 1')
        match = self.only()
        self.assertEqual((match.verdict, len(match.candidates), match.excluded),
                         (m.AMBIGUOUS, 2, 0))

    def test_two_p1s_only_one_labels_avb_1_is_matched(self):
        self.p1('SR P1')
        port = self.p1_out(self.sl, 'AVB', 1, 'Main L')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 1')
        match = self.only()
        self.assertEqual((match.verdict, match.excluded), (m.MATCHED, 1))
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_two_p1s_both_label_avb_1_is_ambiguous(self):
        sr = self.p1('SR P1')
        self.p1_out(self.sl, 'AVB', 1, 'Main L')
        self.p1_out(sr, 'AVB', 1, 'Main R')
        self.amp_channel(self.amp_, 1, avb_stream='AVB 1')
        self.assertEqual(self.only().verdict, m.AMBIGUOUS)

    def test_an_assigned_bus_breaks_a_tie_like_a_label(self):
        self.p1('SR P1')
        port = self.p1_out(self.sl, 'AVB', 2, '', bus=3)
        self.amp_channel(self.amp_, 1, avb_stream='2')
        match = self.only()
        self.assertEqual((match.verdict, match.excluded), (m.MATCHED, 1))
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_label_then_number_is_output_n_of_that_type(self):
        port = self.p1_out(self.sl, 'AES', 3, '')
        self.amp_channel(self.amp_, 1, aes_input='Center - 3')
        match = self.only()
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'number'))
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_number_then_label_works_too(self):
        port = self.p1_out(self.sl, 'AES', 3, '')
        self.amp_channel(self.amp_, 1, aes_input='3 - Center')
        self.assertEqual(_refs(self.only().targets), {_ref('p1output', port)})

    def test_analog_label_number_needs_both_to_be_certain(self):
        gx = self.galaxy('Delay Galaxy')
        port = self.galaxy_out(gx, 'ANALOG', 5, '')
        self.amp_channel(self.amp_, 1, analog_input='FB - 5')
        match = self.only()                         # number fits, label does not
        self.assertEqual(match.verdict, m.AMBIGUOUS)
        self.assertEqual(_refs(match.candidates), {_ref('galaxyoutput', port)})
        port.label = 'FB'
        port.save()
        self.assertEqual(_refs(self.only().targets), {_ref('galaxyoutput', port)})

    def test_label_breaks_a_tie_between_processors_with_output_n(self):
        sr = self.p1('SR P1')
        self.p1_out(self.sl, 'AES', 3, '')
        port = self.p1_out(sr, 'AES', 3, 'Center')
        self.amp_channel(self.amp_, 1, aes_input='Center - 3')
        self.assertEqual(_refs(self.only().targets), {_ref('p1output', port)})

    def test_number_on_two_processors_with_no_label_to_tell_is_ambiguous(self):
        self.p1('SR P1')
        self.amp_channel(self.amp_, 1, aes_input='Center - 3')
        self.assertEqual(self.only().verdict, m.AMBIGUOUS)

    def test_a_name_no_processor_has_matches_an_io_output(self):
        out = self.device_output(self.device('Stage Box'), 1, 'LEFT')
        self.amp_channel(self.amp_, 1, aes_input='LEFT')
        match = self.only()
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'io'))
        self.assertEqual(_refs(match.targets), {_ref('deviceoutput', out)})

    def test_a_processor_label_wins_over_an_io_output_of_the_same_name(self):
        port = self.p1_out(self.sl, 'AES', 1, 'Left')
        self.device_output(self.device('Stage Box'), 1, 'LEFT')
        self.amp_channel(self.amp_, 1, aes_input='LEFT')
        self.assertEqual(_refs(self.only().targets), {_ref('p1output', port)})

    def test_one_name_twice_on_one_io_device_is_same_device(self):
        box = self.device('Stage Box')
        a = self.device_output(box, 1, 'L&R')
        b = self.device_output(box, 2, 'L&R')
        self.amp_channel(self.amp_, 1, analog_input='L&R')
        match = self.only()
        self.assertEqual((match.verdict, match.via), (m.SAME_DEVICE, 'io'))
        self.assertEqual(_refs(match.targets), {_ref('deviceoutput', a), _ref('deviceoutput', b)})

    def test_one_name_on_two_io_devices_is_ambiguous(self):
        a = self.device_output(self.device('Stage Box A'), 1, 'L&R')
        b = self.device_output(self.device('Stage Box B'), 1, 'L&R')
        self.amp_channel(self.amp_, 1, analog_input='L&R')
        match = self.only()
        self.assertEqual(match.verdict, m.AMBIGUOUS)
        self.assertEqual(_refs(match.candidates), {_ref('deviceoutput', a), _ref('deviceoutput', b)})


class RuleCProdStringsTests(ConnectionFixtures, TestCase):
    """PA Destination text as it is really typed (strings from the prod report)."""

    def match(self, row):
        [cm] = [x for x in m.rule_c(m.ProjectIndex.load(self.project)) if x.row.pk == row.pk]
        return cm

    def test_amp_rack_text_is_the_amp_end_not_the_speaker(self):
        cm = self.match(self.text_cable(destination='SR Amp Racks'))
        self.assertEqual(cm.speaker.verdict, m.RACK)
        self.assertEqual((cm.amp.verdict, cm.amp.via, cm.amp.text),
                         (m.UNMATCHED, 'rack_text', 'SR Amp Racks'))

    def test_amp_rack_text_naming_an_amp_location_is_that_location(self):
        amp = self.amp('SR LA12X #1', rack='SR Amp Racks')
        cm = self.match(self.text_cable(destination='SR Amp Racks'))
        self.assertEqual((cm.amp.verdict, cm.amp.target),
                         (m.MATCHED, f'amp_location:{amp.location_id}'))

    def test_an_amp_location_name_is_a_rack_even_without_the_words(self):
        amp = self.amp('SL LA12X #1', rack='SL Racks')
        cm = self.match(self.text_cable(destination='sl racks'))
        self.assertEqual((cm.speaker.verdict, cm.amp.target),
                         (m.RACK, f'amp_location:{amp.location_id}'))

    def test_the_amp_fk_still_wins_over_rack_text(self):
        amp = self.amp('SR LA12X #1')
        cm = self.match(self.text_cable(destination='SR Amp Racks', amp=amp))
        self.assertEqual((cm.speaker.verdict, cm.amp.via), (m.RACK, 'fk'))

    def test_text_that_is_no_array_stays_text(self):
        for text in ('KIVA DELAY 2 & 3', '5XT FF 1&8, 2&7'):
            with self.subTest(text=text):
                end = self.match(self.text_cable(destination=text)).speaker
                self.assertEqual((end.verdict, end.via, end.text), (m.UNMATCHED, 'text', text))


class AnalogPoolTests(ConnectionFixtures, TestCase):
    """Analogue Input: processor analogue outputs and I/O outputs are one
    pool, neither preferred (strings from the prod report)."""

    def setUp(self):
        super().setUp()
        self.sl = self.p1('SL P1')                  # analog outs 1-4, unlabelled
        self.box = self.device('Stage Box')
        self.amp_ = self.amp('SL LA12X #1')

    def only(self):
        [match] = m.rule_b(m.ProjectIndex.load(self.project))
        return match

    def box_outputs(self, names):
        return [self.device_output(self.box, n, name) for n, name in enumerate(names, 1)]

    def test_center_3_on_io_out_3_only_is_io(self):
        out3 = self.box_outputs(['L', 'R', 'CENTER'])[2]
        self.amp_channel(self.amp_, 1, analog_input='Center - 3')
        match = self.only()
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'io'))
        self.assertEqual(_refs(match.targets), {_ref('deviceoutput', out3)})

    def test_center_3_on_p1_analog_3_only_is_processor(self):
        self.box_outputs(['L', 'R', 'Spare'])
        port = self.p1_out(self.sl, 'ANALOG', 3, 'Center')
        self.amp_channel(self.amp_, 1, analog_input='Center - 3')
        match = self.only()
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'number'))
        self.assertEqual(_refs(match.targets), {_ref('p1output', port)})

    def test_center_3_on_both_is_ambiguous(self):
        out3 = self.box_outputs(['L', 'R', 'CENTER'])[2]
        port = self.p1_out(self.sl, 'ANALOG', 3, 'Center')
        self.amp_channel(self.amp_, 1, analog_input='Center - 3')
        match = self.only()
        self.assertEqual(match.verdict, m.AMBIGUOUS)
        self.assertEqual(_refs(match.candidates),
                         {_ref('deviceoutput', out3), _ref('p1output', port)})

    def test_left_label_only_with_an_unlabelled_p1_analog_out_is_io(self):
        left = self.box_outputs(['LEFT'])[0]
        self.amp_channel(self.amp_, 1, analog_input='LEFT')
        match = self.only()
        self.assertEqual((match.verdict, match.via), (m.MATCHED, 'io'))
        self.assertEqual(_refs(match.targets), {_ref('deviceoutput', left)})

    def test_label_on_both_a_processor_and_an_io_output_is_ambiguous(self):
        self.box_outputs(['LEFT'])
        self.p1_out(self.sl, 'ANALOG', 1, 'Left')
        self.amp_channel(self.amp_, 1, analog_input='LEFT')
        self.assertEqual(self.only().verdict, m.AMBIGUOUS)

    def test_a_bare_number_uses_the_in_use_tie_breaker(self):
        named = self.box_outputs(['Fill', 'Delay'])[1]     # box out 2 named; P1 analog 2 not
        self.amp_channel(self.amp_, 1, analog_input='2')
        match = self.only()
        self.assertEqual((match.verdict, match.excluded), (m.MATCHED, 1))
        self.assertEqual(_refs(match.targets), {_ref('deviceoutput', named)})

    def test_a_and_b_stay_unmatched(self):
        self.box_outputs(['A', 'B'])
        for text in ('A', 'B'):
            with self.subTest(text=text):
                self.amp_channel(self.amp_, 1, analog_input=text)
                self.assertEqual(self.only().verdict, m.UNMATCHED)

    def test_aes_still_prefers_the_processor(self):
        port = self.p1_out(self.sl, 'AES', 1, 'Left')
        self.box_outputs(['LEFT'])
        self.amp_channel(self.amp_, 1, aes_input='LEFT')
        self.assertEqual(_refs(self.only().targets), {_ref('p1output', port)})
