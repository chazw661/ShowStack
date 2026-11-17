"""infer_connections: a read-only report of what the matchers find.

Run with::

    python manage.py test planner.tests.test_infer_connections_command \\
        --settings=audiopatch.test_settings
"""
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from planner.tests.connection_fixtures import ConnectionFixtures


class InferConnectionsCommandTests(ConnectionFixtures, TestCase):
    def setUp(self):
        super().setUp()
        sl, sr = self.p1('SL P1'), self.p1('SR P1')
        desk, box = self.console(), self.device()
        # (a): one same-processor pair, one ambiguous, one unmatched
        self.p1_in(sl, 'AES', 1, 'L Main')
        self.p1_in(sl, 'ANALOG', 1, 'L Main')
        self.p1_in(sl, 'AES', 2, 'Fill')
        self.p1_in(sr, 'AES', 2, 'Fill')
        self.matrix(desk, 1, destination='L Main')
        self.device_output(box, 1, 'Fill')
        self.device_output(box, 2, 'Record')
        # (b): one AVB match, one drift, one AES with nothing to match
        self.p1_out(sl, 'AVB', 1, 'Main L')
        self.p1_out(sl, 'AVB', 2, 'Renamed')
        amp = self.amp('SL LA12X #1', rack='SL Amp Rack')
        self.amp_channel(amp, 1, avb_stream='AVB 1 - Main L')
        self.amp_channel(amp, 2, avb_stream='AVB 2 - Main R', aes_input='Nothing')
        # (c): destination matched (with and without amp FK), ambiguous, unmatched
        self.array(self.prediction(), 'K2 L')
        self.array(self.prediction(), 'Sub L')
        self.array(self.prediction(file_name='day2.pdf'), 'Sub L')
        self.text_cable(self.zone('HL'), destination='K2 L', amp=amp)
        self.text_cable(self.zone('HL'), destination='K2 L')
        self.text_cable(self.zone('SL'), destination='Sub L')
        self.text_cable(self.zone('FF'), destination='Not An Array')

    def run_command(self, *args):
        out = StringIO()
        call_command('infer_connections', *args, stdout=out)
        return out.getvalue()

    def test_writes_nothing(self):
        with CaptureQueriesContext(connection) as ctx:
            self.run_command('-v', '2')
        writes = [q['sql'] for q in ctx.captured_queries
                  if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writes, [])

    def test_counts(self):
        out = self.run_command('--project', str(self.project.pk))
        self.assertIn('(a) matched 1 (same-processor 1)  ambiguous 1  unmatched 1  via I/O 0'
                      '   [same-processor type pairs: 1]', out)
        self.assertIn('(b) matched 1 (same-processor 0)  ambiguous 0  unmatched 1  drift 1', out)
        self.assertIn('Amp channels (n=4): avb 1 · aes 0 · analog 0 · multiple 1 · none 2', out)
        self.assertIn('AES/analog input with no recorded cable: 1', out)
        self.assertIn('(c) Free-text PA rows (n=4): amp FK set 1 · not set 3'
                      '   [amp_location set: 0]', out)
        self.assertIn('destination → speaker array: matched 2  ambiguous 1  unmatched 1', out)
        self.assertNotIn('report only, not matched): 1', out)

    def test_detail_lists_what_did_not_resolve(self):
        out = self.run_command('--project', str(self.project.pk), '-v', '2')
        self.assertIn("ambiguous from deviceoutput:", out)
        self.assertIn("'Fill'", out)
        self.assertIn("unmatched pa_cable:", out)
        self.assertIn("'Not An Array'", out)
        self.assertIn("drift     avb ampchannel:", out)
        self.assertNotIn("'L Main'", out)   # resolved items are not listed

    def test_project_and_rule_narrow_the_output(self):
        other = self.make_project('other show')
        self.device_output(self.device(project=other), 1, 'Elsewhere')
        out = self.run_command('--project', str(self.project.pk), '--rule', 'c')
        self.assertIn(f'Project {self.project.pk}:', out)
        self.assertNotIn(f'Project {other.pk}:', out)
        self.assertNotIn('(a)', out)
        self.assertNotIn('(b)', out)
        self.assertIn('(c)', out)


class InferConnectionsProdStringsTests(ConnectionFixtures, TestCase):
    """The placeholder, via-I/O and amp-rack lines, on strings from prod."""

    def test_counts(self):
        sl = self.p1('SL P1')
        self.p1_out(sl, 'AES', 3, '')
        amp = self.amp('SL LA12X #1')
        self.device_output(self.device(), 1, 'LEFT')
        self.amp_channel(amp, 1, avb_stream='AVB 1', aes_input='x')
        self.amp_channel(amp, 2, avb_stream='1', aes_input='X')
        self.amp_channel(amp, 3, aes_input='Center - 3')
        self.amp_channel(amp, 4, aes_input='LEFT')
        self.text_cable(self.zone('SR'), destination='SR Amp Racks')
        self.text_cable(self.zone('D2'), destination='KIVA DELAY 2 & 3')
        self.text_cable(self.zone('D3'), destination='KIVA DELAY 2 & 3')
        self.text_cable(self.zone('FF'), destination='5XT FF 1&8, 2&7')
        out = StringIO()
        call_command('infer_connections', '--project', str(self.project.pk), stdout=out)
        out = out.getvalue()
        self.assertIn('(b) matched 4 (same-processor 0)  ambiguous 0  unmatched 0  drift 0  '
                      'placeholder 2   [via I/O output: 1]', out)
        self.assertIn('resolve to one processor 3 · to one I/O output 1', out)
        self.assertIn('placeholder (x, -, n/a) 2', out)
        self.assertNotIn('tie decided', out)    # one P1: no tie to decide
        self.assertIn('analog input: resolved to I/O output 0 · to processor 0 · '
                      'ambiguous between both 0', out)
        self.assertIn('destination → speaker array: matched 0  ambiguous 0  unmatched 3 '
                      '(2 distinct texts)', out)
        self.assertIn('destination looked like amp rack: 1   [Amp Location 0 · text only 1]', out)

    def test_analog_breakdown(self):
        sl = self.p1('SL P1')
        box = self.device('Stage Box')
        for n, name in enumerate(['LEFT', 'R', 'CENTER'], 1):
            self.device_output(box, n, name)
        self.p1_out(sl, 'ANALOG', 3, 'Center')
        self.p1_out(sl, 'ANALOG', 4, 'Sub')
        amp = self.amp('SL LA12X #1')
        self.amp_channel(amp, 1, analog_input='LEFT')         # I/O
        self.amp_channel(amp, 2, analog_input='Sub')          # processor
        self.amp_channel(amp, 3, analog_input='Center - 3')   # both
        out = StringIO()
        call_command('infer_connections', '--project', str(self.project.pk), stdout=out)
        self.assertIn('analog input: resolved to I/O output 1 · to processor 1 · '
                      'ambiguous between both 1', out.getvalue())

    def test_a_tie_decided_by_use_is_reported(self):
        sl = self.p1('SL P1')
        self.p1('SR P1')
        self.p1_out(sl, 'AVB', 1, 'Main L')
        self.amp_channel(self.amp('SL LA12X #1'), 1, avb_stream='AVB 1')
        out = StringIO()
        call_command('infer_connections', '--project', str(self.project.pk), stdout=out)
        self.assertIn('tie decided by excluding unused outputs (no label, no bus): '
                      '1 match(es), 1 output(s) excluded', out.getvalue())
