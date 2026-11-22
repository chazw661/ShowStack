"""report_patch_by_name_changes: read-only before/after of Patch cells once
Source (B) stopped taking part in name matching (PR #219).

    python manage.py test planner.tests.test_report_patch_by_name_changes \\
        --settings=audiopatch.test_settings
"""
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from planner.management.commands.report_patch_by_name_changes import changes
from planner.models import ConsoleInput, DeviceInput
from planner.tests.test_console_patch import PatchBase


class ReportTests(PatchBase):

    def run_report(self, *args):
        out = StringIO()
        call_command('report_patch_by_name_changes', *args, stdout=out)
        return out.getvalue()

    def rows(self):
        return [(console.name, c.input_ch, before, after, lost)
                for console, c, before, after, lost in changes(self.project)]

    def snapshot(self):
        return (list(DeviceInput.objects.order_by('pk').values_list(
                    'signal_name', 'console_input_id', 'console_input_b_id')),
                list(ConsoleInput.objects.order_by('pk').values_list('source', 'source_b')))

    def test_another_consoles_source_b_made_an_a_name_ambiguous(self):
        self.ch(self.foh, 1, 'Lectern B')
        self.ch(self.mon, 1, 'Lectern', source_b='Lectern B')
        self.port(self.box_b, 1, 'Lectern B')
        self.assertEqual(self.rows(), [
            ('FOH', '1', ['Stage Box B · In 1 — ambiguous (FOH, MON)'],
             ['Stage Box B · In 1 — by name'], []),
            ('MON', '1', [], [], ['B: Stage Box B · In 1 — ambiguous (FOH, MON)']),
        ])

    def test_same_consoles_source_b_made_an_a_name_ambiguous(self):
        self.ch(self.foh, 1, 'Spare')
        self.ch(self.foh, 2, 'Talkback', source_b='Spare')
        self.port(self.box_a, 4, 'Spare')
        self.assertEqual(self.rows(), [
            ('FOH', '1', ['Stage Box A · In 4 — ambiguous (ch 1, ch 2)'],
             ['Stage Box A · In 4 — by name'], []),
            ('FOH', '2', [], [], ['B: Stage Box A · In 4 — ambiguous (ch 1, ch 2)']),
        ])

    def test_a_b_by_name_alone_changes_no_a_cell(self):
        self.ch(self.foh, 2, 'Lectern', source_b='Lectern B')
        self.port(self.box_b, 2, 'Lectern B')
        self.assertEqual(self.rows(), [('FOH', '2', [], [], ['B: Stage Box B · In 2 — by name'])])
        out = self.run_report()
        self.assertIn('0 channel(s) whose A patch reads differently; 1 channel(s) losing a '
                      'by-name B feed (list them with --b)', out)
        self.assertNotIn('Project', out)
        self.assertIn('FOH ch 2 B no longer shown: B: Stage Box B · In 2 — by name',
                      self.run_report('--b'))

    def test_unaffected_a_patches_are_not_listed(self):
        kick = self.ch(self.foh, 1, 'Kick')
        self.ch(self.foh, 2, 'Snare')
        self.ch(self.foh, 3, 'Spare')
        self.ch(self.foh, 4, 'Spare')
        self.ch(self.mon, 1, 'Kick')
        self.port(self.box_a, 1, 'Kick', kick)      # linked
        self.port(self.box_a, 2, 'Snare')           # by name
        self.port(self.box_a, 3, 'Spare')           # ambiguous, A names only
        self.port(self.box_b, 1, 'Kick')            # ambiguous across consoles, A names only
        self.assertEqual(self.rows(), [])
        self.assertIn('0 channel(s) whose A patch reads differently; 0', self.run_report())

    def test_prints_the_change_and_writes_nothing(self):
        self.ch(self.foh, 1, 'Spare')
        self.ch(self.foh, 2, 'Talkback', source_b='Spare')
        self.port(self.box_a, 4, 'Spare')
        before = self.snapshot()
        out = self.run_report('--project', str(self.project.pk))
        self.assertIn(f'Project {self.project.pk}: Show', out)
        self.assertIn('  FOH ch 1 "Spare"\n'
                      '    before: Stage Box A · In 4 — ambiguous (ch 1, ch 2)\n'
                      '    after:  Stage Box A · In 4 — by name', out)
        self.assertIn('1 channel(s) whose A patch reads differently', out)
        self.assertIn('Nothing was written.', out)
        self.assertEqual(self.snapshot(), before)

    def test_runs_on_mains_schema_reading_no_b_column_and_writing_nothing(self):
        self.ch(self.foh, 1, 'Spare')
        self.ch(self.foh, 2, 'Talkback', source_b='Spare')
        self.port(self.box_a, 4, 'Spare')
        with CaptureQueriesContext(connection) as queries:
            self.run_report('--b')
        sql = [q['sql'] for q in queries.captured_queries]
        self.assertFalse([s for s in sql if 'console_input_b' in s], sql)
        self.assertFalse([s for s in sql if s.lstrip().upper().startswith(
            ('INSERT', 'UPDATE', 'DELETE', 'ALTER', 'CREATE', 'DROP'))], sql)

    def test_another_project_is_not_reported_with_project(self):
        self.ch(self.foh, 1, 'Spare')
        self.ch(self.foh, 2, 'Talkback', source_b='Spare')
        self.port(self.box_a, 4, 'Spare')
        self.assertNotIn('Project', self.run_report('--project', str(self.project.pk + 999)))
