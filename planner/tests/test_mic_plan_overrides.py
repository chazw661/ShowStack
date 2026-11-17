"""Mic Planner walkthrough PR 2: row overrides into the plan, which row is
"the same row" after a re-import, day overrides (not a person, VOG pack),
"same as", and people to confirm.

Run with::

    python manage.py test planner.tests.test_mic_plan_overrides --settings=audiopatch.test_settings
"""

from types import SimpleNamespace

from django.test import SimpleTestCase

from planner.mic_plan import importer, overrides, planning, rowkey, solver
from planner.mic_plan.parser import is_vog
from planner.models import MicPlannerDayOverride, ShowflowImport, ShowflowPerson
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase


def _row(order, line='', start='', desc='', speaker='', minute=None):
    return SimpleNamespace(order=order, line_no=line, start_text=start, end_text='', duration_text='',
                           description=desc, speaker_text=speaker, bsm_text='', audio_text='', notes_text='',
                           est_time=minute)


class RowKeyTests(SimpleTestCase):

    def rows(self, specs):
        return [_row(i, *spec) for i, spec in enumerate(specs)]

    def test_a_unique_line_label_is_the_row(self):
        old = self.rows([('1', '8:00 AM', 'Opening'), ('2', '', 'PPT'), ('3', '', 'Talk')])
        new = self.rows([('1', '8:00 AM', 'Opening'), ('9', '', 'Inserted'), ('2', '', 'PPT'), ('3', '', 'Talk')])
        found, exact = rowkey.find(rowkey.describe(old[1], old), new)
        self.assertIs(new[2], found)
        self.assertTrue(exact)

    def test_changed_text_is_found_but_not_exact(self):
        old = self.rows([('1', '8:00 AM', 'Opening'), ('2', '', 'Alex speaks')])
        new = self.rows([('1', '8:00 AM', 'Opening'), ('2', '', 'Alex and Kim speak')])
        found, exact = rowkey.find(rowkey.describe(old[1], old), new)
        self.assertIs(new[1], found)
        self.assertFalse(exact)

    def test_without_labels_start_time_and_text_find_it(self):
        old = self.rows([('', '8:00 AM', 'Opening', '', 480), ('', '', 'Alex speaks', 'Alex Host', 485)])
        new = [_row(0, '', '8:00 AM', 'Opening', '', 480), _row(1, '', '', 'Inserted', '', 485),
               _row(2, '', '', 'Alex speaks', 'Alex Host', 485)]
        found, exact = rowkey.find(rowkey.describe(old[1], old), new)
        self.assertIs(new[2], found)
        self.assertTrue(exact)

    def test_a_repeated_label_falls_back_to_time_and_text(self):
        old = self.rows([('5', '8:00 AM', 'Opening', '', 480), ('5', '', 'PPT', '', 485)])
        found, _ = rowkey.find(rowkey.describe(old[1], old), old)
        self.assertIs(old[1], found)

    def test_twins_keep_their_place_in_a_run(self):
        specs = [('', '', 'PPT', '', 485)] * 3 + [('', '', 'Talk', '', 485)]
        old = self.rows(specs)
        new = self.rows([('', '', 'Inserted', '', 485)] + specs)
        for i, r in enumerate(old):
            self.assertIs(new[i + 1], rowkey.find(rowkey.describe(r, old), new)[0], i)

    def test_a_row_that_is_gone_is_not_found(self):
        old = self.rows([('1', '8:00 AM', 'Opening'), ('2', '', 'Alex speaks')])
        new = self.rows([('1', '8:00 AM', 'Opening')])
        self.assertEqual((None, False), rowkey.find(rowkey.describe(old[1], old), new))

    def test_an_inserted_segment_leaves_every_other_row_itself(self):
        # The real files (A-G, with and without line labels) pass the same
        # check in the corpus harness; this is the committed version.
        old = [SimpleNamespace(order=i, line_no=r[0], start_text=r[1], end_text=r[2], duration_text=r[3],
                               description=r[4], speaker_text=r[5], bsm_text=r[12], audio_text=r[10],
                               notes_text=r[13], est_time=480 + i)
               for i, r in enumerate(row for page in F.CLIENT_E_PAGES for row in page[1 if page is F.CLIENT_E_PAGES[0] else 0:])]
        mid = len(old) // 2
        inserted = [_row(0, 'X{}'.format(k), '', 'New segment {}'.format(k), '', old[mid].est_time) for k in range(3)]
        new = old[:mid] + inserted + [SimpleNamespace(**vars(r)) for r in old[mid:]]
        for k, r in enumerate(new):
            r.order = k
        for i, r in enumerate(old):
            found, exact = rowkey.find(rowkey.describe(r, old), new)
            self.assertIs(new[i if i < mid else i + 3], found, r.line_no)
            self.assertTrue(exact, r.line_no)


class OverrideBase(MicPlanBase):

    pages = 'CLIENT_E_PAGES'

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload(self.pages)
        self.part = ShowflowImport.objects.get(day=self.day)

    def row(self, line, part=None):
        return (part or self.part).rows.get(line_no=line)

    def apps(self):
        data, _, _ = planning.build_day(self.day)
        plan = solver.solve(data, solver.Settings())
        ix = solver._Index(data)
        names = {p.key: p.name for p in data.people}
        out = {}
        for a in plan.appearances:
            out.setdefault(names[a.person], []).append(
                {'on': ix.line(a.on_row), 'off': ix.line(a.off_row), 'mic': a.mic_type})
        return out, plan, data

    def set(self, line, **changes):
        return overrides.set_row(self.part, self.row(line), changes, self.editor)


class CueFreeOverrideTests(OverrideBase):
    """Client E: no cues, on/off from lines (baseline in test_mic_plan_exits)."""

    def test_off_ends_their_appearance_at_that_row(self):
        self.assertEqual('307', self.apps()[0]['Ola Brand'][0]['off'])
        self.set('305', off=['Ola Brand'])
        self.assertEqual('305', self.apps()[0]['Ola Brand'][0]['off'])

    def test_not_off_keeps_them_on_past_an_exit_line(self):
        self.assertEqual(['304', '308'], [a['off'] for a in self.apps()[0]['Max Pine']])
        self.set('304', not_off=['Max Pine'])
        self.assertEqual([('301', '308')], [(a['on'], a['off']) for a in self.apps()[0]['Max Pine']])

    def test_not_off_keeps_them_on_through_a_group_exit(self):
        self.assertEqual('320', self.apps()[0]['Ann Pike'][-1]['off'])
        self.set('320', not_off=['Ann Pike'])
        self.assertNotEqual('320', self.apps()[0]['Ann Pike'][-1]['off'])

    def test_not_on_drops_their_walk_on_at_that_row(self):
        self.assertEqual('308', self.apps()[0]['Gil Ware'][0]['on'])
        self.set('308', not_on=['Gil Ware'])
        self.assertEqual('309', self.apps()[0]['Gil Ware'][0]['on'])

    def test_on_brings_them_on_at_that_row(self):
        self.set('316', on=['Bo Lark'])
        self.assertIn('316', [a['on'] for a in self.apps()[0]['Bo Lark']])

    def test_mic_sets_the_type_of_the_appearance_on_at_that_row(self):
        self.assertEqual(solver.BODY, self.apps()[0]['Ned Quill'][0]['mic'])
        self.set('305', mic={'Ned Quill': 'HH'})
        self.assertEqual(solver.HH, self.apps()[0]['Ned Quill'][0]['mic'])

    def test_an_override_marks_the_plan_stale_and_nothing_left_drops_it(self):
        self.client.post('/audiopatch/mic-plan/day/{}/generate/'.format(self.day.pk), {'replace': '1'})
        self.set('305', off=['Ola Brand'])
        self.assertTrue(self.day.mic_plan.stale)
        self.set('305')
        self.part.refresh_from_db()
        self.assertEqual([], self.part.row_overrides)

    def test_one_entry_per_row(self):
        self.set('305', off=['Ola Brand'])
        self.set('305', off=['Ola Brand'], mic={'Ned Quill': 'HH'})
        self.part.refresh_from_db()
        self.assertEqual(1, len(self.part.row_overrides))

    def test_contradictions_are_refused(self):
        with self.assertRaises(ValueError):
            self.set('305', off=['Ola Brand'], not_off=['Ola Brand'])
        with self.assertRaises(ValueError):
            self.set('305', mic={'Ola Brand': 'wired'})


class CuedOverrideTests(OverrideBase):

    pages = 'MAIN_PAGES'

    def test_off_in_a_cued_part_is_a_catch_at_that_row(self):
        self.assertEqual('115', self.apps()[0]['Kim Keynote'][0]['off'])
        self.set('114', off=['Kim Keynote'])
        self.assertEqual('114', self.apps()[0]['Kim Keynote'][0]['off'])

    def test_not_on_in_a_cued_part_drops_that_rows_send(self):
        before = [a['on'] for a in self.apps()[0]['Kim Keynote']]
        self.assertIn('113', before)
        self.set('113', not_on=['Kim Keynote'])
        self.assertNotIn('113', [a['on'] for a in self.apps()[0].get('Kim Keynote', [])])


class ReplaceTests(OverrideBase):

    def replace_with(self, pages):
        pending = importer.stage_upload(self.day, F.build_pdf(pages), 'revised.pdf', self.editor)
        importer.confirm(pending, replace=self.part)
        self.part = ShowflowImport.objects.get(day=self.day, status='active')

    def issues(self):
        return [i for i in self.apps()[2].issues]

    def test_the_same_file_again_keeps_the_override_applied(self):
        self.set('305', off=['Ola Brand'])
        self.replace_with(F.CLIENT_E_PAGES)
        self.assertEqual('305', self.apps()[0]['Ola Brand'][0]['off'])
        self.assertEqual([], self.issues())

    def test_a_changed_row_is_reported_with_old_and_new_text_and_not_applied(self):
        self.set('305', off=['Ola Brand'])
        changed = [[r[:4] + ['Scheduling demo, longer'] + r[5:] if r[0] == '305' else r for r in page]
                   for page in F.CLIENT_E_PAGES]
        self.replace_with(changed)
        [issue] = self.issues()
        self.assertEqual('override_changed', issue['kind'])
        self.assertIn('Scheduling demo |', issue['was'])
        self.assertIn('Scheduling demo, longer', issue['now'])
        self.assertEqual('307', self.apps()[0]['Ola Brand'][0]['off'])       # not applied
        overrides.accept(self.part, issue['entry'])
        self.assertEqual('305', self.apps()[0]['Ola Brand'][0]['off'])
        self.assertEqual([], self.issues())

    def test_a_row_that_is_gone_is_a_day_issue(self):
        self.set('305', off=['Ola Brand'])
        self.replace_with([[r for r in page if r[0] != '305'] for page in F.CLIENT_E_PAGES])
        [issue] = self.issues()
        self.assertEqual('override_gone', issue['kind'])
        self.assertIsNone(issue['row'])
        overrides.drop(self.part, issue['entry'])
        self.assertEqual([], self.issues())

    def test_issues_reach_the_plans_flags(self):
        self.set('305', off=['Ola Brand'])
        self.replace_with([[r for r in page if r[0] != '305'] for page in F.CLIENT_E_PAGES])
        planning.generate(self.day, self.editor, mode='fresh')
        self.assertIn('override_gone', [f['kind'] for f in self.day.mic_plan.flags])


class NotAPersonTests(OverrideBase):

    pages = 'CLIENT_F_PAGES'

    def test_a_rejected_phrase_is_no_one_anywhere_and_raises_no_flag(self):
        people = set(ShowflowPerson.objects.filter(day=self.day).values_list('display_name', flat=True))
        victim = sorted(people)[0]
        importer.reject_phrase(self.day, victim.upper(), self.editor)
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name=victim).exists())
        self.part.refresh_from_db()
        self.assertFalse([w for w in self.part.warnings if victim.lower() in w['text'].lower()])

    def test_it_holds_across_replace_and_can_be_taken_back(self):
        victim = sorted(ShowflowPerson.objects.filter(day=self.day).values_list('display_name', flat=True))[0]
        importer.reject_phrase(self.day, victim, self.editor)
        pending = importer.stage_upload(self.day, F.build_pdf(F.CLIENT_F_PAGES), 'again.pdf', self.editor)
        importer.confirm(pending, replace=self.part)
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name=victim).exists())
        importer.unreject_phrase(self.day, MicPlannerDayOverride.objects.get(day=self.day).key)
        self.assertTrue(ShowflowPerson.objects.filter(day=self.day, display_name=victim).exists())


class SameAsTests(OverrideBase):

    pages = 'MAIN_PAGES'

    def test_same_as_a_typed_name_makes_that_person_and_keeps_the_spelling(self):
        importer.same_as(self.person('Pat Guest'), new_name='Patricia Guest')
        person = self.person('Patricia Guest')
        self.assertEqual(['Pat Guest'], person.aliases)
        self.assertTrue(person.flags['rows'][str(self.part.pk)])      # found by the old spelling
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='Pat Guest').exists())

    def test_same_as_an_existing_person_is_a_merge(self):
        importer.same_as(self.person('KK'), target=self.person('Kim Keynote'))
        self.assertIn('KK', self.person('Kim Keynote').aliases)

    def test_one_of_the_two(self):
        with self.assertRaises(ValueError):
            importer.same_as(self.person('KK'))


class VogTests(OverrideBase):

    def test_vog_lines(self):
        self.assertTrue(is_vog('VOG: Please welcome ...'))
        self.assertTrue(is_vog('[GFX] VOG: Please welcome ...'))
        self.assertTrue(is_vog('Voice of God - doors'))
        self.assertFalse(is_vog('VO can be cut'))                  # a video voice-over
        self.assertFalse(is_vog('Ned welcomes the VOG'))

    def test_no_pack_no_vog(self):
        self.assertNotIn('VOG', self.apps()[0])

    def test_a_vog_pack_is_one_fixed_pack_from_its_first_line_to_its_last(self):
        importer.set_vog_pack(self.day, 'HH', self.editor)
        [vog] = self.apps()[0]['VOG']
        self.assertEqual(('314', '314', solver.HH), (vog['on'], vog['off'], vog['mic']))
        importer.rebuild_day(self.day)                              # kept: the parse never names it
        self.assertIn('VOG', self.apps()[0])
        importer.set_vog_pack(self.day, None, self.editor)
        self.assertNotIn('VOG', self.apps()[0])
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, name_key='vog').exists())

    def test_the_vog_is_never_on_stage(self):
        importer.set_vog_pack(self.day, 'body', self.editor)
        _, _, data = self.apps()
        vog = next(p for p in data.people if p.name == 'VOG')
        self.assertEqual([], data.listings[vog.key])


class ConfirmTests(OverrideBase):

    def test_line_estimate_people_start_unconfirmed(self):
        names = {p.display_name for p in planning.people_to_confirm(self.day)}
        self.assertIn('Ola Brand', names)
        importer.confirm_person(self.person('Ola Brand'), self.editor)
        importer.rebuild_day(self.day)                               # a rebuild keeps it
        self.assertNotIn('Ola Brand', {p.display_name for p in planning.people_to_confirm(self.day)})

    def test_a_cued_day_has_no_one_to_confirm(self):
        day = self.other_day
        self.use(self.other_owner, self.other)
        self.upload('MAIN_PAGES', day=day)
        self.assertEqual([], planning.people_to_confirm(day))
