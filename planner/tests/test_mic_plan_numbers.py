"""Mic Plan: mic numbers read from the showflow (lists and row cells), and
what the plan does with them (compare card, "Use the showflow's numbers",
follow mode, no all-day pack for someone whose mic changes). Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_numbers --settings=audiopatch.test_settings
"""

from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import importer, planning, solver
from planner.mic_plan.parser import analyse, mic_callouts
from planner.models import MicPlanSettings, ShowflowImport, ShowflowPerson, ShowflowRow
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase


def row(line='', start='', end='', dur='', desc='', speaker='', audio='', bsm='', notes=''):
    return {'line': line, 'start': start, 'end': end, 'duration': dur, 'description': desc, 'speaker': speaker,
            'audio': audio, 'bsm': bsm, 'notes': notes, 'page_no': 1}


def seg(line, start, end, speaker, audio='', **kw):
    return row(line, start, end, '0:30:00', 'Talk', speaker, audio, **kw)


class CalloutTests(SimpleTestCase):

    def test_list_items(self):
        self.assertEqual([('Lav', [1], 'Ann Reed'), ('Lav', [2], 'Bo Lund'), ('Lav', [5], 'Sue Tran')],
                         mic_callouts('Walk-In A2: Mic Presenters Lav #1: Ann Reed Lav #2: Bo Lund Lav #5 - Sue Tran'))

    def test_every_word(self):
        for text, kind, n in (('Lav 2', 'Lav', 2), ('LAV 2', 'Lav', 2), ('Lavalier 2', 'Lav', 2), ('HH 3', 'HH', 3),
                              ('HH3', 'HH', 3), ('Handheld 3', 'HH', 3), ('hand-held 3', 'HH', 3),
                              ('Headset 4', 'Headset', 4), ('Mic 5', 'Mic', 5), ('RF 6', 'RF', 6), ('RF #6', 'RF', 6)):
            with self.subTest(text):
                self.assertEqual([(kind, [n], '')], mic_callouts(text))

    def test_several_numbers(self):
        self.assertEqual([('Lav', [1, 2, 3], '')], mic_callouts('Lav 1,2,3'))
        self.assertEqual([('Lav', [3, 6], '')], mic_callouts('Lav 3, 6'))
        self.assertEqual([('Lav', [1, 2], '')], mic_callouts('Lav 1 & 2'))
        self.assertEqual([('Lav', [1, 2, 3], '')], mic_callouts('Lav 1-3'))

    def test_inside_other_text(self):
        self.assertEqual([('Lav', [2], '')], mic_callouts('IR 8 Play-On: Song replay (1.3) Lav 2'))

    def test_not_callouts(self):
        for text in ('IR 5', 'Preset 2', 'GFX 1', 'DSM 1A', 'Mic Presenters', 'Mic 5:30', 'Fade music',
                     '2 handhelds for runners', 'Podium mic 1', 'Lectern Mic 2', 'Stand mic 3', 'Aisle mic 1',
                     'Mic 1.2', 'Slav 2', ''):
            with self.subTest(text):
                self.assertEqual([], mic_callouts(text))


class ReadingTests(SimpleTestCase):

    def labels(self, result, name):
        return [e['label'] for e in result.people[name]['mics']]

    def analyse(self, rows):
        return analyse(rows, crew=[])

    def test_cell_on_one_speakers_row(self):
        r = self.analyse([seg('1', '9:00 AM', '9:30 AM', 'Ann Reed', 'Lav 2')])
        self.assertEqual(['Lav 2'], self.labels(r, 'Ann Reed'))
        self.assertEqual({'row': 0, 'kind': 'Lav', 'n': 2, 'label': 'Lav 2', 'pool': 'body', 'via': 'cell'},
                         r.people['Ann Reed']['mics'][0])

    def test_kinds_set_the_pool(self):
        r = self.analyse([seg('1', '9:00 AM', '9:30 AM', 'Ann Reed', 'HH 3'),
                          seg('2', '9:30 AM', '10:00 AM', 'Bo Lund', 'Headset 4'),
                          seg('3', '10:00 AM', '10:30 AM', 'Sue Tran', 'Mic 5')])
        self.assertEqual('HH', r.people['Ann Reed']['mics'][0]['pool'])
        self.assertEqual('body', r.people['Bo Lund']['mics'][0]['pool'])
        self.assertIsNone(r.people['Sue Tran']['mics'][0]['pool'])

    def test_bsm_and_notes_are_read_too(self):
        r = self.analyse([seg('1', '9:00 AM', '9:30 AM', 'Ann Reed', bsm='Lav 2'),
                          seg('2', '9:30 AM', '10:00 AM', 'Bo Lund', notes='Lav 3 no clicker')])
        self.assertEqual(['Lav 2'], self.labels(r, 'Ann Reed'))
        self.assertEqual(['Lav 3'], self.labels(r, 'Bo Lund'))

    def test_a_cell_with_no_speaker_is_ignored(self):
        r = self.analyse([seg('1', '9:00 AM', '9:30 AM', 'Ann Reed'), row('1A', desc='Restore preset', audio='Lav 1')])
        self.assertEqual([], self.labels(r, 'Ann Reed'))
        self.assertEqual([], [f for f in r.flags if f[0].startswith('mic_')])

    def test_a_list_block_names_people_listed_later(self):
        r = self.analyse([row('1', '8:00 AM', '8:30 AM', '0:30:00', 'Doors', audio='Lav #1: Ann Reed Lav #2: Bo Lund'),
                          seg('2', '9:00 AM', '9:30 AM', 'Ann Reed'), seg('3', '9:30 AM', '10:00 AM', 'Bo Lund')])
        self.assertEqual('list', r.people['Ann Reed']['mics'][0]['via'])
        self.assertEqual(['Lav 2'], self.labels(r, 'Bo Lund'))

    def test_a_list_spelling_a_little_off_is_that_person(self):
        r = self.analyse([row('1', audio='Lav #2: Kit Harlans'), seg('2', '9:00 AM', '9:30 AM', 'Kit Harlan')])
        self.assertEqual(['Lav 2'], self.labels(r, 'Kit Harlan'))
        self.assertNotIn('Kit Harlans', r.people)

    def test_a_list_name_with_a_title(self):
        r = self.analyse([row('1', audio='Lav #5 - Dr. Una Reyes'), seg('2', '9:00 AM', '9:30 AM', 'Dr. Una Reyes')])
        self.assertEqual(['Lav 5'], self.labels(r, 'Dr. Una Reyes'))

    def test_text_after_a_list_name_is_ignored(self):
        r = self.analyse([row('1', audio='Lav #1: Ann Reed Fade music'), seg('2', '9:00 AM', '9:30 AM', 'Ann Reed')])
        self.assertEqual(['Lav 1'], self.labels(r, 'Ann Reed'))

    def test_a_list_name_nobody_has_is_flagged_not_made(self):
        r = self.analyse([row('7', audio='Lav #1: Zed Quill'), seg('2', '9:00 AM', '9:30 AM', 'Ann Reed')])
        self.assertNotIn('Zed Quill', r.people)
        self.assertIn('Line 7: Lav 1 is listed for "Zed Quill"', [f for f in r.flags if f[0] == 'mic_name'][0][2])

    def test_a_close_name_two_people_could_be_is_not_guessed(self):
        r = self.analyse([row('1', audio='Lav #1: Don Baker'), seg('2', '9:00 AM', '9:30 AM', 'Jon Baker, Ron Baker')])
        self.assertEqual([], self.labels(r, 'Jon Baker') + self.labels(r, 'Ron Baker'))
        self.assertTrue([f for f in r.flags if f[0] == 'mic_name'])

    def test_several_numbers_are_never_matched_by_position(self):
        r = self.analyse([seg('5', '9:00 AM', '9:30 AM', 'Ann Reed, Bo Lund', 'Lav 3,6')])
        self.assertEqual([], self.labels(r, 'Ann Reed') + self.labels(r, 'Bo Lund'))
        self.assertIn('Line 5: Lav 3, Lav 6 for 2 people', [f for f in r.flags if f[0] == 'mic_which'][0][2])

    def test_several_numbers_agreeing_with_a_list_are_quiet(self):
        r = self.analyse([row('1', audio='Lav #3: Bo Lund Lav #6: Ann Reed'),
                          seg('5', '9:00 AM', '9:30 AM', 'Ann Reed, Bo Lund', 'Lav 3,6')])
        self.assertEqual([], [f for f in r.flags if f[0] == 'mic_which'])
        self.assertEqual(['Lav 6'], self.labels(r, 'Ann Reed'))

    def test_the_latest_list_decides_after_a_cell(self):
        r = self.analyse([row('1', audio='Lav #1: Ann Reed Lav #2: Bo Lund'),
                          seg('2', '8:00 AM', '8:30 AM', 'Ann Reed', 'Lav 1'),
                          row('3', audio='Lav #3: Ann Reed Lav #6: Bo Lund'),
                          seg('5', '9:00 AM', '9:30 AM', 'Ann Reed, Bo Lund', 'Lav 3,6')])
        self.assertEqual([], [f for f in r.flags if f[0] == 'mic_which'])

    def test_one_number_for_two_people_is_flagged(self):
        r = self.analyse([seg('5', '9:00 AM', '9:30 AM', 'Ann Reed, Bo Lund', 'Lav 3')])
        self.assertTrue([f for f in r.flags if f[0] == 'mic_which'])

    def test_a_callout_is_no_hand_held_hint(self):
        r = self.analyse([seg('1', '9:00 AM', '9:30 AM', 'Ann Reed', 'HH 3')])
        self.assertEqual('', r.people['Ann Reed']['mic_hint'])


class FixtureBase(MicPlanBase):

    pages = F.MIC_NUMBER_PAGES

    def setUp(self):
        super().setUp()
        self.settings_obj = planning.project_settings(self.project)
        self.load(self.pages)

    def load(self, pages):
        self.part = importer.stage_upload(self.day, F.build_pdf(pages), 'f.pdf', self.owner)
        importer.confirm(self.part)

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self.settings_obj, k, v)
        self.settings_obj.save()

    def plan(self, **kw):
        return planning.generate(self.day, self.owner, **kw)

    def card(self, plan):
        return next((f for f in plan.flags if f['kind'] == planning.SHOWFLOW_CARD), None)

    def rfs(self, plan):
        return [(a.person_name, a.assignments.get(backup=False).rf_number)
                for a in plan.appearances.order_by('on_min')]


class StorageTests(FixtureBase):

    def test_numbers_are_kept_by_line_and_rebuilt_on_reread(self):
        host = ShowflowPerson.objects.get(day=self.day, display_name='Kit Moss')
        self.assertEqual(['Lav 2', 'Lav 2', 'Lav 4', 'Lav 4'],
                         [e['label'] for e in host.flags['mics'][str(self.part.pk)]])
        ShowflowRow.objects.filter(showflow_import=self.part, line_no__in=['200', '202']).update(audio_text='')
        importer.reread(self.part)
        host.refresh_from_db()
        self.assertEqual(['Lav 2', 'Lav 2'], [e['label'] for e in host.flags['mics'][str(self.part.pk)]])


class HostTests(FixtureBase):

    def test_two_numbers_is_no_host(self):
        apps = self.plan().appearances.filter(person_name='Kit Moss')
        self.assertGreater(apps.count(), 1)
        self.assertFalse(apps.filter(is_host=True).exists())

    def test_a_number_given_to_someone_later_is_no_host(self):
        self.assertFalse(self.plan().appearances.filter(person_name='Lee Voss', is_host=True).exists())

    def test_one_number_nobody_else_gets_can_host(self):
        changes = planning._mic_changes(self.day.showflow_people.all(), importer.active_parts(self.day))
        self.assertNotIn(ShowflowPerson.objects.get(day=self.day, display_name='Pia Wren').pk, changes)

    def test_no_numbers_keeps_the_hosts_rule(self):
        self.assertEqual(set(), planning._mic_changes(self.day.showflow_people.none(), []))


class CompareTests(FixtureBase):

    def test_card_lists_differences_and_changes_nothing(self):
        plan = self.plan()
        self.assertEqual(0, plan.edits.count())
        self.assertFalse(plan.appearances.exclude(pinned_rf=None).exists())
        card = self.card(plan)
        self.assertRegex(card['text'], r'Showflow: \w+ \w+ on Lav \d · Plan: RF \d')

    def test_review_shows_the_card_and_button(self):
        self.plan()
        self.use(self.editor)
        resp = self.client.get(reverse('planner:mic_plan') + '?day={}'.format(self.day.pk))
        self.assertContains(resp, "Use the showflow's numbers")
        self.assertContains(resp, 'Plan: RF')
        self.assertContains(resp, 'showflow mic: Lav 2 (line 100), Lav 4 (line 200)')
        self.assertContains(resp, 'class="mp-micnote"')

    def test_viewer_sees_the_card_without_the_button(self):
        self.plan()
        self.use(self.viewer)
        resp = self.client.get(reverse('planner:mic_plan') + '?day={}'.format(self.day.pk))
        self.assertContains(resp, 'Plan: RF')
        self.assertNotContains(resp, 'mp-use-showflow')

    def test_use_pins_them_all_and_clears_the_card(self):
        plan = self.plan()
        plan, count = planning.use_showflow(self.day, plan.version, self.owner)
        self.assertGreater(count, 0)
        self.assertEqual(count, plan.edits.count())
        self.assertEqual({'move_rf'}, set(plan.edits.values_list('kind', flat=True)))
        self.assertIsNone(self.card(plan))
        self.assertEqual([], [f for f in plan.flags if f['kind'] == 'conflict'])

    def test_one_undo_removes_the_whole_batch(self):
        plan = self.plan()
        first = self.rfs(plan)
        plan, _ = planning.use_showflow(self.day, plan.version, self.owner)
        plan, removed = planning.undo(self.day, plan.version, self.owner)
        self.assertEqual(0, plan.edits.count())
        self.assertEqual(first, self.rfs(plan))
        self.assertIsNotNone(self.card(plan))
        from planner.mic_plan.display import describe_edit
        self.assertIn("the showflow's numbers", describe_edit(removed))

    def test_a_later_move_undoes_alone(self):
        plan = self.plan()
        plan, count = planning.use_showflow(self.day, plan.version, self.owner)
        app = plan.appearances.first()
        plan, _ = planning.edit(self.day, plan.version, 'move_rf', app.skey, {'rf': 9}, self.owner)
        plan, _ = planning.undo(self.day, plan.version, self.owner)
        self.assertEqual(count, plan.edits.count())

    def test_endpoint_needs_the_current_version_and_edit_rights(self):
        plan = self.plan()
        url = reverse('planner:mic_plan_use_showflow', args=[self.day.pk])
        self.use(self.viewer)
        self.assertEqual(403, self.client.post(url, {'version': plan.version}).status_code)
        self.use(self.editor)
        self.assertEqual(409, self.client.post(url, {'version': plan.version + 1}).status_code)
        resp = self.client.post(url, {'version': plan.version})
        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.json()['ok'])

    def test_nothing_to_use(self):
        plan = self.plan()
        plan, _ = planning.use_showflow(self.day, plan.version, self.owner)
        with self.assertRaisesMessage(planning.EditRefused, 'Nothing here differs'):
            planning.use_showflow(self.day, plan.version, self.owner)

    def test_old_plan_settings_read_as_compare(self):
        plan = self.plan()
        plan.settings.pop('showflow_numbers')
        self.assertEqual('compare', planning.plan_values(plan)['showflow_numbers'])


class FollowTests(FixtureBase):

    def setUp(self):
        super().setUp()
        self.set(showflow_numbers='follow')

    def test_numbers_are_pins_from_the_start(self):
        plan = self.plan()
        self.assertEqual(0, plan.edits.count())
        self.assertIsNone(self.card(plan))
        kit = list(plan.appearances.filter(person_name='Kit Moss').order_by('on_min'))
        self.assertEqual([2, 4], sorted({a.pinned_rf for a in kit}))
        self.assertEqual([], [f for f in plan.flags if f['kind'] == 'conflict'])

    def test_summary_says_so(self):
        from planner.mic_plan import page
        self.assertIn("following the showflow's mic numbers", page.settings_summary(planning.plan_values(self.plan())))

    def test_unpin_beats_the_showflow(self):
        plan = self.plan()
        app = plan.appearances.filter(pinned_rf__isnull=False).first()
        plan, _ = planning.edit(self.day, plan.version, 'unpin', app.skey, {}, self.owner)
        self.assertIsNone(plan.appearances.get(skey=app.skey).pinned_rf)

    def test_a_move_beats_the_showflow_and_undo_gives_it_back(self):
        plan = self.plan()
        app = plan.appearances.filter(pinned_rf__isnull=False).first()
        was = app.pinned_rf
        plan, _ = planning.edit(self.day, plan.version, 'move_rf', app.skey, {'rf': 12}, self.owner)
        self.assertEqual(12, plan.appearances.get(skey=app.skey).pinned_rf)
        plan, _ = planning.undo(self.day, plan.version, self.owner)
        self.assertEqual(was, plan.appearances.get(skey=app.skey).pinned_rf)

    def test_conflict_says_the_showflow_not_you(self):
        self.load([[F.HEADER_F,
                    F._row_f('1', '9:00 AM', '10:00 AM', '1:00:00', 'Panel A', 'Ann Reed', 'Lav 1'),
                    F._row_f('2', '9:30 AM', '10:00 AM', '0:30:00', 'Panel B', 'Bo Lund', 'Lav 1')]])
        text = ' '.join(f['text'] for f in self.plan().flags if f['kind'] == 'conflict')
        self.assertIn("the showflow's number at line", text)
        self.assertNotIn('your change', text)

    def test_past_the_rig_gets_the_rig_card(self):
        self.set(wireless_channels=3, handheld_channels=0, spare_handhelds=0)
        plan = self.plan()
        text = ' '.join(f['text'] for f in plan.flags if f['kind'] == 'rig')
        self.assertIn("the showflow's RF 4 number is not in the rig (1–3)", text)


class HandheldNumberTests(SimpleTestCase):

    def entry(self, kind, n):
        return {'kind': kind, 'n': n}

    def test_hh_is_the_nth_channel_of_the_zone(self):
        R = solver.Rig(24, 4, 1)
        self.assertEqual(21, planning.showflow_rf(self.entry('HH', 1), R))
        self.assertEqual(23, planning.showflow_rf(self.entry('HH', 3), R))

    def test_hh_past_the_zone_is_a_spare_or_off_the_rig(self):
        R = solver.Rig(24, 4, 1)
        self.assertFalse(R.usable(planning.showflow_rf(self.entry('HH', 4), R)))
        self.assertFalse(R.usable(planning.showflow_rf(self.entry('HH', 5), R)))

    def test_hh_with_no_zone_or_no_rig_is_channel_n(self):
        self.assertEqual(3, planning.showflow_rf(self.entry('HH', 3), solver.Rig(24, 0, 0)))
        self.assertEqual(3, planning.showflow_rf(self.entry('HH', 3), solver.Rig()))

    def test_everything_else_is_channel_n(self):
        R = solver.Rig(24, 4, 1)
        for kind in ('Lav', 'Headset', 'Mic', 'RF'):
            self.assertEqual(6, planning.showflow_rf(self.entry(kind, 6), R))


class HandheldCompareTests(FixtureBase):

    pages = [[F.HEADER_F, F._row_f('1', '9:00 AM', '9:30 AM', '0:30:00', 'Talk', 'Ann Reed', 'HH 2')]]

    def test_card_shows_the_channel_and_use_makes_it_a_handheld(self):
        self.set(wireless_channels=24, handheld_channels=4, spare_handhelds=1)
        plan = self.plan()
        self.assertIn('on HH 2 (RF 22)', self.card(plan)['text'])
        plan, _ = planning.use_showflow(self.day, plan.version, self.owner)
        app = plan.appearances.get()
        self.assertEqual((22, 'HH'), (app.assignments.get().rf_number, app.mic_type))


class PinReuseTests(FixtureBase):

    def test_going_back_to_your_own_pack_is_no_reuse(self):
        self.set(showflow_numbers='follow')
        self.assertEqual([], [f['text'] for f in self.plan().flags if f['kind'] == 'pin_reuse'])


class SettingsFormTests(FixtureBase):

    def test_saved_from_the_form(self):
        self.use(self.editor)
        self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 1, 'mic_min': 3, 'demic_min': 3, 'premic_lead_min': 30, 'margin_min': 5,
            'wireless_channels': '', 'handheld_channels': 0, 'spare_handhelds': 0,
            'showflow_numbers': 'follow'})
        self.assertEqual('follow', MicPlanSettings.objects.get(project=self.project).showflow_numbers)

    def test_default_is_compare(self):
        self.assertEqual('compare', self.settings_obj.showflow_numbers)
