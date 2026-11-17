"""Mic Planner walkthrough (mic_plan/walkthrough.py, PR W3): one panel per
showflow row, what the parse read from it, confirm / reopen, locks, the day
strip, blockers, and the JSON endpoint.

Run with::

    python manage.py test planner.tests.test_mic_planner_walkthrough --settings=audiopatch.test_settings
"""

import json
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import importer, overrides, planning, push, walkthrough
from planner.models import MicPlan, MicPlannerDayOverride, MicPlannerRowCheck, ShowflowImport, ShowflowPerson
from planner.tests import showflow_fixture as F
from planner.tests.test_mic_plan_import import MicPlanBase


def _row(order, page, line='', start='', desc='', speaker=''):
    r = SimpleNamespace(order=order, page_no=page, line_no=line, start_text=start, description=desc,
                        speaker_text=speaker, bsm_text='', audio_text='', notes_text='')
    r.is_blank = not any((start, desc, speaker))
    return r


class FoldTests(SimpleTestCase):

    def test_a_row_running_on_past_a_page_break_folds_into_the_row_above(self):
        rows = [_row(0, 1, '1', '9:00', 'Opening'), _row(1, 1, '2', '', 'Panel with'),
                _row(2, 2, '', '', 'three more names'), _row(3, 2, '3', '', 'Close')]
        self.assertEqual([[0], [1, 2], [3]], [[r.order for r in g] for g in walkthrough.fold(rows)])

    def test_a_new_page_starting_with_a_line_label_or_a_time_does_not_fold(self):
        rows = [_row(0, 1, '1', '', 'Opening'), _row(1, 2, '2', '', 'Next'),
                _row(2, 3, '', '9:30', 'Timed'), _row(3, 3, '', '', 'Same page, no label')]
        self.assertEqual([[0], [1], [2], [3]], [[r.order for r in g] for g in walkthrough.fold(rows)])

    def test_an_unlabelled_sub_row_opening_a_page_is_not_a_run_on(self):
        rows = [_row(0, 1, '1', '9:00', 'Opening'), _row(1, 1, '', '', 'Video, preset 5'),
                _row(2, 2, '', '', 'Presenter intro, then departs')]
        self.assertEqual([[0], [1], [2]], [[r.order for r in g] for g in walkthrough.fold(rows)])

    def test_only_the_first_row_with_text_on_the_page_folds(self):
        rows = [_row(0, 1, '1', '', 'Opening'), _row(1, 2), _row(2, 2, '', '', 'run-on'),
                _row(3, 2, '', '', 'not a run-on')]
        self.assertEqual([[0, 2], [3]], [[r.order for r in g] for g in walkthrough.fold(rows)])


class WalkBase(MicPlanBase):

    pages = 'MAIN_PAGES'

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload(self.pages)
        self.part = ShowflowImport.objects.get(day=self.day)

    def walk(self):
        return walkthrough.build(self.day)

    def panel(self, line, walk=None):
        return next(p for p in (walk or self.walk())['panels'] if p['line'] == line)

    def on(self, line, walk=None):
        return {o['name']: o for o in self.panel(line, walk)['on']}

    def off(self, line, walk=None):
        return {o['name']: o for o in self.panel(line, walk)['off']}

    def confirm(self, line, ack=False):
        p = self.panel(line)
        return walkthrough.confirm(self.day, p['id'], p['digest'], self.editor, ack=ack)

    def post(self, action, body, user=None):
        return self.client.post(reverse('planner:mic_plan_walk', args=[self.day.pk, action]),
                                json.dumps(body), content_type='application/json')

    def replace_with(self, pages):
        pending = importer.stage_upload(self.day, F.build_pdf(pages), 'revised.pdf', self.editor)
        importer.confirm(pending, replace=self.part)
        self.part = ShowflowImport.objects.get(day=self.day, status='active')


class PanelTests(WalkBase):
    """The cued fixture: on/off come from sends and catches."""

    def test_one_panel_per_row_with_text_in_show_order_and_no_rf(self):
        walk = self.walk()
        self.assertEqual([str(n) for n in range(100, 119)], [p['line'] for p in walk['panels']])
        self.assertNotIn('RF', json.dumps(walkthrough.page_data(walk)['panels']))

    def test_people_come_on_and_off_on_the_row_that_did_it(self):
        self.assertEqual('send', self.on('103')['Alex Host']['how'])        # "Rio Sends Alex"
        self.assertEqual('catch', self.off('107')['Alex Host']['how'])      # "Rio Catches Alex"
        self.assertEqual(('send', 'catch'), (self.on('106')['Pat Guest']['how'], self.off('106')['Pat Guest']['how']))
        self.assertNotIn('Alex Host', self.on('104'))                       # named there, but the cue put them on

    def test_a_host_keeps_each_time_on_stage(self):
        self.assertTrue(self.on('103')['Alex Host']['host'])
        self.assertIn('Alex Host', self.on('111'))                          # sent again after the panel

    def test_never_caught_is_off_on_the_segments_last_row_as_an_assumption(self):
        morgan = self.off('111')['Morgan Dee']                             # 109–111 is "Building the Future"
        self.assertEqual(('end', 'end of segment'), (morgan['how'], morgan['assumed']))

    def test_the_words_of_each_name_and_leftover_text_are_marked(self):
        p = self.panel('106')
        speaker = p['rows'][0]['cells']['speaker']
        marks = {(m['kind'], speaker[m['start']:m['end']]) for m in p['rows'][0]['marks'] if m['col'] == 'speaker'}
        self.assertIn(('name', 'Pat Guest'), marks)
        self.assertIn(('leftover', 'Customer Panel Group 1-5'), marks)
        self.assertIn('leftover', [l['kind'] for l in p['locks']])

    def test_a_row_where_no_one_comes_on_or_off_is_confirmed_automatically(self):
        self.assertEqual('auto', self.panel('101')['state'])               # VIDEO: walk-in loop
        self.assertEqual('open', self.panel('103')['state'])

    def test_cue_sourced_names_get_a_first_row_highlight_and_no_lock(self):
        self.assertTrue(self.on('103')['Alex Host'].get('first'))
        self.assertFalse(self.on('111')['Alex Host'].get('first'))
        self.assertEqual([], self.panel('103')['person_locks'])

    def test_a_name_with_no_cue_behind_it_is_locked_on_its_first_row(self):
        locked = {pl['name'] for p in self.walk()['panels'] for pl in p['person_locks']}
        self.assertIn('Taylor Eve', locked)                                 # listed, never sent
        self.assertNotIn('Alex Host', locked)
        self.assertNotIn('Dana Able', locked)

    def test_plan_flags_are_badges_on_their_row_and_never_reopen_it(self):
        self.confirm('108')
        plan = planning.generate(self.day, self.editor)
        keys = {a.person_name: a.skey for a in plan.appearances.all()}
        plan, _ = planning.edit(self.day, plan.version, 'move_rf', keys['Dana Able'], {'rf': 3, 'pool': 'body'},
                                self.editor)
        plan, _ = planning.edit(self.day, plan.version, 'move_rf', keys['Chris Baker'], {'rf': 3, 'pool': 'body'},
                                self.editor)
        walk = self.walk()
        self.assertEqual('confirmed', self.panel('108', walk)['state'])
        self.assertIn({'kind': 'conflict', 'label': 'Conflict'}, self.panel('108', walk)['badges'])
        self.assertEqual(['conflict'], sorted({b['kind'] for b in walk['blockers']}))
        self.assertIn(self.panel('108', walk)['id'], walkthrough.progress(walk)['plan_rows'])


class CueFreeTests(WalkBase):
    """Client E: on/off from lines naming people, exits and re-entries."""

    pages = 'CLIENT_E_PAGES'

    def test_exits_are_on_their_line_and_lock_it(self):
        self.assertEqual('named', self.on('301')['Max Pine']['how'])
        self.assertEqual('exit', self.off('304')['Max Pine']['how'])
        self.assertEqual('enter', self.on('306')['Max Pine']['how'])
        self.assertIn('exit', [l['kind'] for l in self.panel('304')['locks']])

    def test_every_parsed_name_is_locked_once_on_its_first_row(self):
        walk = self.walk()
        locked = [pl['name'] for p in walk['panels'] for pl in p['person_locks']]
        self.assertEqual(len(locked), len(set(locked)))
        self.assertEqual('301', next(p['line'] for p in walk['panels']
                                     if any(pl['name'] == 'Max Pine' for pl in p['person_locks'])))
        people = {p.display_name for p in ShowflowPerson.objects.filter(day=self.day)}
        self.assertEqual(people, set(locked))

    def test_person_lifts_the_lock_and_confirms_that_row_only(self):
        p = self.panel('301')
        self.assertRaises(walkthrough.Refused, walkthrough.confirm, self.day, p['id'], p['digest'], self.editor)
        resp = self.post('person', {'row': p['id'], 'person': self.person('Max Pine').pk, 'decision': 'person'})
        self.assertTrue(resp.json()['ok'])
        self.assertEqual('confirmed', self.panel('301')['state'])
        self.assertTrue(self.person('Max Pine').flags['confirmed'])
        self.assertNotEqual('confirmed', self.panel('306')['state'])       # a later row: no lock, not confirmed

    def test_not_a_person_rejects_the_phrase_and_can_be_undone_from_the_strip(self):
        p = self.panel('301')
        self.post('person', {'row': p['id'], 'person': self.person('Max Pine').pk, 'decision': 'not'})
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='Max Pine').exists())
        item, = [i for i in self.walk()['strip'] if i['kind'] == 'rejected']
        self.post('unreject', {'key': item['key']})
        self.assertTrue(ShowflowPerson.objects.filter(day=self.day, display_name='Max Pine').exists())

    def test_same_as_a_typed_name_close_to_someone_asks_first(self):
        p = self.panel('302')
        ola = self.person('Ola Brand').pk
        resp = self.post('person', {'row': p['id'], 'person': ola, 'decision': 'same', 'name': 'Max Pyne'}).json()
        self.assertEqual(('close', ['Max Pine']), (resp['why'], [c['name'] for c in resp['close']]))
        self.assertTrue(ShowflowPerson.objects.filter(pk=ola).exists())     # nothing changed yet
        resp = self.post('person', {'row': p['id'], 'person': ola, 'decision': 'same', 'name': 'Max Pyne',
                                    'force': True}).json()
        self.assertTrue(resp['ok'])
        self.assertIn('Ola Brand', self.person('Max Pyne').aliases)

    def test_assumed_off_sits_on_the_segments_last_row(self):
        bo = self.off('311')['Bo Lark']
        self.assertEqual(('end', 'end of segment'), (bo['how'], bo['assumed']))

    def test_a_row_lock_needs_looks_right(self):
        importer.confirm_person(self.person('Max Pine'), self.editor)
        importer.confirm_person(self.person('Vic Stone'), self.editor)
        self.assertRaises(walkthrough.Refused, self.confirm, '304')
        self.confirm('304', ack=True)
        self.assertEqual('confirmed', self.panel('304')['state'])


class ConfirmTests(WalkBase):

    def test_confirm_needs_the_digest_the_user_saw(self):
        p = self.panel('103')
        with self.assertRaises(walkthrough.Refused) as e:
            walkthrough.confirm(self.day, p['id'], 'not-it', self.editor)
        self.assertEqual(p['id'], e.exception.panel['id'])
        resp = self.post('confirm', {'row': p['id'], 'digest': 'not-it'}).json()
        self.assertFalse(resp['ok'])
        self.assertEqual([p['id']], [x['id'] for x in resp['panels']])        # the row as it is now
        resp = self.post('confirm', {'row': p['id'], 'digest': p['digest']}).json()
        self.assertTrue(resp['ok'])
        self.assertEqual(('confirmed', 'mp_editor'), (resp['panels'][0]['state'], resp['panels'][0]['by']))

    def test_progress_counts_confirmed_reopened_and_open(self):
        before = walkthrough.progress(self.walk())
        self.confirm('103')
        after = walkthrough.progress(self.walk())
        self.assertEqual(before['confirmed'] + 1, after['confirmed'])
        self.assertEqual(before['open'] - 1, after['open'])
        self.assertNotEqual(self.panel('103')['id'], after['first_open'])

    def test_unconfirm(self):
        self.confirm('103')
        self.post('unconfirm', {'row': self.panel('103')['id']})
        self.assertEqual('open', self.panel('103')['state'])

    def test_editing_a_row_sets_its_override_and_confirms_it(self):
        p = self.panel('106')
        resp = self.post('row', {'row': p['id'], 'on': [], 'off': [], 'not_on': [], 'not_off': [],
                                 'mic': {'pat guest': 'body'}}).json()
        self.assertTrue(resp['ok'])
        self.assertEqual({'pat guest': 'body'}, ShowflowImport.objects.get(pk=self.part.pk).row_overrides[0]['mic'])
        p = self.panel('106')
        self.assertEqual(('confirmed', 'body'), (p['state'], self.on('106')['Pat Guest']['mic']))

    def test_a_changed_row_reopens_and_says_what_changed(self):
        self.confirm('103')
        changed = [[r[:4] + ['EMCEE: please welcome Alex Host'] + r[5:] if r[0] == '103' else r for r in page]
                   for page in F.MAIN_PAGES]
        self.replace_with(changed)
        p = self.panel('103')
        self.assertEqual('reopened', p['state'])
        self.assertEqual(['Showflow text'], [w['what'] for w in p['was']])

    def test_regenerate_with_no_data_change_reopens_nothing(self):
        for p in self.walk()['panels']:
            if p['state'] == 'open' and not p['person_locks']:
                walkthrough.confirm(self.day, p['id'], p['digest'], self.editor, ack=True)
        confirmed = {p['id'] for p in self.walk()['panels'] if p['state'] == 'confirmed'}
        planning.generate(self.day, self.editor)
        planning.generate(self.day, self.editor, mode='over')
        self.replace_with(F.MAIN_PAGES)                                     # the same file again
        walk = self.walk()
        self.assertEqual(0, walkthrough.progress(walk)['reopened'])
        self.assertEqual(len(confirmed), sum(1 for p in walk['panels'] if p['state'] == 'confirmed'))

    def test_an_inserted_segment_reopens_only_the_rows_whose_output_changed(self):
        for p in self.walk()['panels']:
            if p['state'] == 'open' and not p['person_locks']:
                walkthrough.confirm(self.day, p['id'], p['digest'], self.editor, ack=True)
        before = {p['line']: p for p in self.walk()['panels']}
        page_3 = F.PAGE_3[:1] + [F._row14('111A', '9:00 AM', '9:10 AM', '0:10:00', 'Sponsor Video'),
                                 F._row14('111B', '', '', '', 'VIDEO: sponsor reel')] + F.PAGE_3[1:]
        self.replace_with([F.PAGE_1, F.PAGE_2, page_3])
        walk = self.walk()
        after = {p['line']: p for p in walk['panels']}
        self.assertEqual({'111A', '111B'}, set(after) - set(before))
        for line, p in after.items():
            if line not in before or before[line]['state'] != 'confirmed':
                continue
            was = before[line]
            same = (was['digest'] == p['digest'])
            self.assertEqual('confirmed' if same else 'reopened', p['state'], line)
        # Only rows whose time or people really moved are reopened.
        reopened = {line for line, p in after.items() if p['state'] == 'reopened'}
        for line in reopened:
            self.assertTrue(after[line]['was'], line)
            self.assertTrue({w['what'] for w in after[line]['was']} <= {'Time', 'On', 'Off'}, line)
        self.assertLess(len(reopened), len([p for p in before.values() if p['state'] == 'confirmed']))

    def test_a_check_follows_its_row_through_replace(self):
        self.confirm('103')
        self.replace_with(F.MAIN_PAGES)
        self.assertEqual(1, MicPlannerRowCheck.objects.filter(part=self.part).count())
        self.assertEqual('confirmed', self.panel('103')['state'])


class StripAndBlockerTests(WalkBase):

    pages = 'CLIENT_E_PAGES'

    def test_a_held_back_override_is_on_the_strip_blocks_send_and_accept_confirms_the_row(self):
        overrides.set_row(self.part, self.part.rows.get(line_no='305'), {'off': ['Ola Brand']}, self.editor)
        changed = [[r[:4] + ['Scheduling demo, longer'] + r[5:] if r[0] == '305' else r for r in page]
                   for page in F.CLIENT_E_PAGES]
        self.replace_with(changed)
        walk = self.walk()
        item, = [i for i in walk['strip'] if i['kind'] == 'override_changed']
        self.assertIn('Scheduling demo, longer', item['now'])
        self.assertEqual(['override_changed'], [b['kind'] for b in walk['blockers']])
        plan = planning.generate(self.day, self.editor)
        self.assertIn('held back', push.refusal(plan, list(plan.appearances.all())))
        self.post('override', {'part': self.part.pk, 'entry': item['entry'], 'do': 'accept'})
        walk = self.walk()
        self.assertEqual([], walk['blockers'])
        self.assertEqual('confirmed', self.panel('305', walk)['state'])

    def test_add_people_from_a_line_confirms_it(self):
        p = self.panel('311')
        self.assertEqual(['Cy Dorn', 'Eli Fay', 'Hal Grey'], p['leftovers'])
        resp = self.post('add', {'row': p['id'], 'names': ['Cy Dorn', '']}).json()
        self.assertTrue(resp['ok'])
        self.assertIn('Cy Dorn', self.on('311'))
        self.assertEqual('added', self.on('311')['Cy Dorn']['how'])

    def test_the_vog_with_a_pack_leaves_the_names_it_welcomes_as_people(self):
        importer.set_vog_pack(self.day, 'body', self.editor)
        walk = self.walk()
        self.assertIn('Kit Ames', self.on('315', walk))                     # named on the panel row
        self.assertTrue(ShowflowPerson.objects.filter(day=self.day, display_name='Dr. Lou Penn').exists())
        vog = self.on('314', walk)['VOG']
        self.assertEqual('fixed', vog['how'])
        self.assertEqual([], [pl for p in walk['panels'] for pl in p['person_locks'] if pl['name'] == 'VOG'])


class EndpointTests(WalkBase):

    def test_viewers_cannot_change_anything(self):
        self.use(self.viewer)
        p = self.panel('103')
        self.assertEqual(403, self.post('confirm', {'row': p['id'], 'digest': p['digest']}).status_code)
        self.assertFalse(MicPlannerRowCheck.objects.exists())

    def test_another_projects_day_and_rows_are_not_reachable(self):
        p = self.panel('103')
        resp = self.client.post(reverse('planner:mic_plan_walk', args=[self.other_day.pk, 'confirm']),
                                json.dumps({'row': p['id'], 'digest': p['digest']}), content_type='application/json')
        self.assertEqual(404, resp.status_code)

    def test_bad_input_is_a_400_not_a_500(self):
        for body in ('[1]', '{"row": "x"}', 'not json'):
            resp = self.client.post(reverse('planner:mic_plan_walk', args=[self.day.pk, 'confirm']), body,
                                    content_type='application/json')
            self.assertEqual(400, resp.status_code, body)
        self.assertEqual(404, self.post('nope', {}).status_code)

    def test_the_page_carries_the_walkthrough_as_json_only(self):
        resp = self.client.get(reverse('planner:mic_plan') + '?day={}'.format(self.day.pk))
        self.assertContains(resp, 'id="mp-walk-data"')
        self.assertContains(resp, 'id="t-walk"')
        self.assertNotContains(resp, 'v-review')
        self.assertContains(resp, 'Rows to confirm')


class CloseNameTests(WalkBase):

    def test_close_spellings_and_same_surname_with_the_same_initial(self):
        names = lambda n: [p.display_name for p in importer.close_names(self.day, n)]      # noqa: E731
        self.assertEqual(['Alex Host'], names('Alex Hoste'))
        self.assertEqual(['Kim Keynote'], names('K. Keynote'))
        self.assertEqual([], names('Alex Host'))                            # that person: not "close"
        self.assertEqual([], names('Quinn Zephyr'))


class MigrationGuardTests(SimpleTestCase):

    def test_the_guard_refuses_review_checks_with_notes(self):
        import importlib
        mod = importlib.import_module('planner.migrations.0232_mic_planner_walkthrough')

        class Q:
            def __init__(self, n):
                self.n = n

            def exclude(self, **kw):
                return self

            def count(self):
                return self.n

        class Apps:
            def __init__(self, n):
                self.n = n

            def get_model(self, *a):
                return SimpleNamespace(objects=Q(self.n))

        mod.refuse_notes(Apps(0), None)
        with self.assertRaises(RuntimeError):
            mod.refuse_notes(Apps(2), None)


class StatusTests(WalkBase):

    def test_the_dashboard_counts_open_and_reopened_rows(self):
        from planner.mic_plan.status import day_status
        pr = walkthrough.progress(self.walk())
        self.assertEqual(pr['open'] + pr['reopened'], day_status(self.day)['open_rows'])
        self.assertIsNone(MicPlan.objects.filter(day=self.day).first())
        self.assertEqual('imported', day_status(self.day)['state'])


class DayOverrideKeptTests(WalkBase):

    pages = 'CLIENT_E_PAGES'

    def test_rejected_phrases_are_on_the_strip_until_undone(self):
        importer.reject_phrase(self.day, 'Gil Ware', self.editor)
        self.assertTrue(any(i['kind'] == 'rejected' for i in self.walk()['strip']))
        importer.unreject_phrase(self.day, MicPlannerDayOverride.objects.get(day=self.day).key)
        self.assertFalse(any(i['kind'] == 'rejected' for i in self.walk()['strip']))
