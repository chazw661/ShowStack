"""Mic Plan edits (PR 3): pins, minimal change, conflicts, the edit log
through re-generate / Re-read / Replace, undo, and access. Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_edits --settings=audiopatch.test_settings
"""

from unittest import TestCase

from django.urls import reverse

from planner.mic_plan import planning, solver
from planner.mic_plan.solver import BODY, HH, Fixed, Settings, solve
from planner.models import MicPlan, MicPlanEdit, ShowflowImport
from planner.tests.test_mic_plan_import import MicPlanBase
from planner.tests.test_mic_plan_solver import Show, panel_day

TIMES = ['9:00', '9:10', '9:20', '9:30', '9:40', '9:50', '10:00', '10:10', '10:20', '10:30', '10:40']
S = Settings(premic_lead_min=10)


def relay_day(n=5):
    """``n`` people one after another, ten minutes each, no break: under
    recycle_at_breaks each needs a new pack, RF 1..n in walk-on order."""
    s = Show()
    for k, t in enumerate(TIMES[:2 * n + 1]):
        s.line(k + 1, t)
    for k in range(n):
        s.segment(2 * k + 1, 2 * k + 2, 'Seg {}'.format(k + 1), TIMES[2 * k], TIMES[2 * k + 2])
        s.person(k + 1, 'Person {}'.format(k + 1)).lists(k + 1, 2 * k + 1).exits(k + 1, 2 * k + 2)
    return s.day()


def rfs(plan):
    return {plan.appearances[a.appearance].skey: a.rf for a in plan.assignments if not a.backup}


def pools(plan):
    return {p.rf: p.pool for p in plan.packs if not p.spare and p.backup_of is None}


def key_of(plan, person):
    return next(a.skey for a in plan.appearances if a.person == person)


def edited(day, base, pins=None, types=None, settings=S):
    """``day`` re-solved with ``pins`` and every other RF preferred as in ``base``."""
    pins = pins or {}
    return solve(day, settings, suggest=False, fixed=Fixed(
        pins=pins, types=types or {}, prefer=rfs(base)))


class PinTests(TestCase):

    def test_a_pin_is_honoured_for_the_whole_wearing(self):
        day = relay_day()
        base = solve(day, S)
        k3 = key_of(base, 3)
        plan = edited(day, base, {k3: 5})
        self.assertEqual(5, rfs(plan)[k3])
        acts = [a for a in plan.actions if a.person == 3]
        self.assertEqual(['mic', 'demic'], [a.kind for a in acts])
        self.assertEqual({5}, {a.rf_number for a in acts})
        self.assertEqual('pinned', next(s.how for s in plan.assignments if s.appearance == acts[0].appearance))

    def test_a_pin_covers_appearances_that_share_one_pack(self):
        # On at 9:00 and again at 9:20: within the lead, so one wearing.
        s = Show()
        for k, t in enumerate(['9:00', '9:10', '9:20', '9:30', '9:40']):
            s.line(k + 1, t)
        s.segment(1, 2, 'A', '9:00', '9:20').segment(3, 4, 'B', '9:20', '9:40')
        s.person(1, 'Person 1').lists(1, 1, 3).person(2, 'Person 2').lists(2, 2)
        day = s.day()
        base = solve(day, Settings(premic_lead_min=30))
        second = [a.skey for a in base.appearances if a.person == 1][-1]
        plan = solve(day, Settings(premic_lead_min=30), fixed=Fixed(pins={second: 7}))
        self.assertEqual({7}, {a.rf_number for a in plan.actions if a.person == 1})
        self.assertEqual(1, len([a for a in plan.actions if a.person == 1 and a.kind == 'mic']))

    def test_a_type_pin_moves_it_to_the_other_pool(self):
        day = relay_day(3)
        base = solve(day, S)
        k2 = key_of(base, 2)
        plan = solve(day, S, fixed=Fixed(types={k2: HH}, prefer=rfs(base)))
        hh = {p.rf for p in plan.packs if p.pool == HH}
        self.assertEqual(1, len(hh))
        self.assertIn(rfs(plan)[k2], hh)
        self.assertEqual(HH, next(a.mic_type for a in plan.appearances if a.skey == k2))

    def test_appearance_keys_are_name_line_and_occurrence(self):
        plan = solve(relay_day(2), S)
        self.assertEqual(['person 1|1|0', 'person 2|3|0'], [a.skey for a in plan.appearances])


class MinimalChangeTests(TestCase):

    def test_one_move_changes_only_what_it_must(self):
        day = relay_day(5)
        base = solve(day, S)
        self.assertEqual([1, 2, 3, 4, 5], [rfs(base)[key_of(base, k)] for k in range(1, 6)])
        k1 = key_of(base, 1)
        # A plain re-solve with only the pin renumbers everyone after it...
        naive = solve(day, S, fixed=Fixed(pins={k1: 6}))
        self.assertGreaterEqual(sum(1 for k, rf in rfs(naive).items() if k != k1 and rf != rfs(base)[k]), 3)
        # ...preferring the previous RFs moves nobody else.
        plan = edited(day, base, {k1: 6})
        self.assertEqual({**rfs(base), k1: 6}, rfs(plan))

    def test_moving_onto_a_worn_pack_moves_its_wearer_not_everyone(self):
        day = panel_day(4).day()
        base = solve(day, S)
        k1, k2 = key_of(base, 1), key_of(base, 2)
        plan = edited(day, base, {k1: rfs(base)[k2]})
        changed = {k for k, rf in rfs(plan).items() if rf != rfs(base)[k]}
        self.assertEqual({k1, k2}, changed)
        self.assertFalse([f for f in plan.flags if f['kind'] == 'conflict'])

    def test_previous_rfs_never_override_the_pack_policy(self):
        # Fewest packs hands its packs down the relay; kept as preferences
        # under Recycle at breaks, that would reuse them mid-session.
        day = relay_day(5)
        fewest = solve(day, Settings(premic_lead_min=10, pack_policy=solver.FEWEST_PACKS))
        self.assertLess(len(fewest.packs), 5)
        plan = edited(day, fewest)
        self.assertEqual(0, plan.mid_session)
        self.assertEqual(len(solve(day, S).packs), len(plan.packs))

    def test_re_solving_with_its_own_rfs_preferred_gives_the_same_plan(self):
        for day in (relay_day(5), panel_day(6).day()):
            base = solve(day, S, suggest=False)
            again = edited(day, base)
            self.assertEqual(rfs(base), rfs(again))
            self.assertEqual([(a.kind, a.start_min, a.rf_number, a.person) for a in base.actions],
                             [(a.kind, a.start_min, a.rf_number, a.person) for a in again.actions])


class ConflictTests(TestCase):

    def test_two_pins_on_one_rf_at_once_are_solved_and_flagged(self):
        day = panel_day(4).day()
        base = solve(day, S)
        k1, k2 = key_of(base, 1), key_of(base, 2)
        plan = edited(day, base, {k1: 1, k2: 1})
        self.assertEqual((1, 1), (rfs(plan)[k1], rfs(plan)[k2]))
        conflicts = [f for f in plan.flags if f['kind'] == 'conflict']
        self.assertEqual(1, len(conflicts))
        self.assertRegex(conflicts[0]['text'], r'^RF 1 on two people \d+:\d\d[ap]–\d+:\d\d[ap] '
                                               r'\(Person 1 and Person 2\) — your change at line 2\.$')
        self.assertEqual(1, solver.summary(plan)['conflict'])

    def test_a_pin_waits_for_its_pack_when_the_wearer_comes_off_first(self):
        day = relay_day(5)
        base = solve(day, S)
        k1, k2 = key_of(base, 1), key_of(base, 2)
        plan = edited(day, base, {k1: 1, k2: 1})
        self.assertFalse([f for f in plan.flags if f['kind'] == 'conflict'])
        tight = [f for f in plan.flags if f['kind'] in ('late', 'tight')]
        self.assertEqual(['pin'], [f['cause'] for f in tight])
        self.assertIn('RF 1 is with Person 1 until', tight[0]['text'])
        self.assertIn('your change at line 3', tight[0]['text'])

    def test_a_pin_may_reuse_a_pack_mid_session_and_says_so(self):
        day = relay_day(5)
        base = solve(day, S)
        plan = edited(day, base, {key_of(base, 3): 1})
        info = [f for f in plan.flags if f['kind'] == 'pin_reuse']
        self.assertEqual(1, len(info))
        self.assertIn('RF 1 goes to Person 3 mid-session because of your change', info[0]['text'])


class EditBase(MicPlanBase):

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload()
        self.part = self.parts()[0]
        self.generate()

    def generate(self, mode='keep'):
        return self.client.post(reverse('planner:mic_plan_generate', args=[self.day.pk]),
                                {'replace': '1', 'mode': mode})

    def plan(self):
        return MicPlan.objects.get(day=self.day)

    def edit(self, kind, key, version=None, **fields):
        return self.client.post(reverse('planner:mic_plan_edit', args=[self.day.pk]), dict(
            kind=kind, key=key, version=self.plan().version if version is None else version, **fields))

    def undo(self, version=None):
        return self.client.post(reverse('planner:mic_plan_undo', args=[self.day.pk]), {
            'version': self.plan().version if version is None else version})

    def rfs(self):
        return planning.snapshot(self.plan())

    def actions(self):
        return [(a.kind, a.start_min, a.rf_number, a.person_id, a.a2_index)
                for a in self.plan().actions.order_by('start_min', 'a2_index', 'seq')]

    def key(self, name):
        return self.plan().appearances.get(person_name=name).skey


class EditViewTests(EditBase):

    def test_a_move_is_pinned_logged_and_shown(self):
        before = self.rfs()
        key = self.key('Kim Keynote')                              # RF 1 after the emcee
        resp = self.edit('move_rf', key, rf=7, pool='body')
        self.assertEqual(200, resp.status_code, resp.content)
        plan = self.plan()
        self.assertEqual((2, 1), (plan.version, plan.edits.count()))
        app = plan.appearances.get(skey=key)
        self.assertEqual((7, 'body'), (app.pinned_rf, app.pinned_type))
        self.assertEqual([7, 'body'], self.rfs()[key])
        # Taylor wore RF 7 before 9:00; Kim walks on at 9:30: nobody else moves.
        self.assertEqual({k: v for k, v in before.items() if k != key},
                         {k: v for k, v in self.rfs().items() if k != key})
        self.assertEqual([key], [c['key'] for c in plan.changes])
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'Undo: Kim → RF 7')
        self.assertContains(page, '1 change')
        self.assertContains(page, '1 changed')
        self.assertContains(page, 'class="mp-pin"')
        self.assertContains(page, 'Kim → RF 7.')                # the message after the reload

    def test_a_cross_pool_move_keeps_the_type(self):
        # PR 5.1b: a body pack dropped on a handheld's lane stays a body pack;
        # only "Switch body/HH" changes the type.
        key = self.key('Kim Keynote')
        self.assertEqual(200, self.edit('move_rf', key, rf=8, pool='HH').status_code)     # RF 8 is Pat's handheld
        app = self.plan().appearances.get(skey=key)
        self.assertEqual(('body', 8, 'body'), (app.mic_type, app.pinned_rf, app.pinned_type))
        self.assertEqual('Kim (line 113) RF 1 → RF 8', self.plan().changes[0]['text'])
        self.assertEqual({'rf': 8, 'pool': 'body'}, {k: self.plan().edits.get().value[k] for k in ('rf', 'pool')})
        self.assertContains(self.client.get(reverse('planner:mic_plan')), 'Kim → RF 8')

    def test_an_old_cross_pool_move_stays_switched(self):
        # Before PR 5.1b a cross-pool move stored the lane's type: replayed as stored.
        key = self.key('Kim Keynote')
        self.edit('move_rf', key, rf=8)
        e = self.plan().edits.get()
        e.value = dict(e.value, pool='HH')
        e.save()
        self.generate()
        self.assertEqual('HH', self.plan().appearances.get(skey=key).mic_type)

    def test_switch_body_hh_and_unpin(self):
        key = self.key('Kim Keynote')
        self.assertEqual(200, self.edit('set_mic_type', key, mic_type='HH').status_code)
        app = self.plan().appearances.get(skey=key)
        self.assertEqual(('HH', None, 'HH'), (app.mic_type, app.pinned_rf, app.pinned_type))
        self.assertEqual(200, self.edit('unpin', key).status_code)
        app = self.plan().appearances.get(skey=key)
        self.assertEqual(('body', None, ''), (app.mic_type, app.pinned_rf, app.pinned_type))
        self.assertEqual(400, self.edit('unpin', key).status_code)    # not pinned any more

    def test_undo_restores_the_previous_plan_exactly(self):
        rfs, actions, flags = self.rfs(), self.actions(), self.plan().flags
        self.edit('move_rf', self.key('Dana Able'), rf=3, pool='body')          # onto Chris, same walk-on
        self.edit('move_rf', self.key('Kim Keynote'), rf=8, pool='HH')
        self.assertNotEqual(rfs, self.rfs())
        self.undo()
        self.assertContains(self.client.get(reverse('planner:mic_plan')), 'Undone: Kim → RF 8')
        self.undo()
        self.assertEqual(rfs, self.rfs())
        self.assertEqual(actions, self.actions())
        self.assertEqual([f['kind'] for f in flags if 'fix' not in f],
                         [f['kind'] for f in self.plan().flags])
        self.assertEqual(0, self.plan().edits.count())
        self.assertEqual(400, self.undo().status_code)                         # nothing left

    def test_keep_changes_replays_the_log_and_start_over_clears_it(self):
        key = self.key('Kim Keynote')
        self.edit('move_rf', key, rf=7, pool='body')
        self.generate('keep')
        self.assertEqual([7, 'body'], self.rfs()[key])
        self.assertEqual(1, self.plan().edits.count())
        self.assertEqual([], self.plan().changes)                 # same data and settings: nothing moved
        self.generate('over')
        self.assertEqual(0, self.plan().edits.count())
        self.assertEqual([1, 'body'], self.rfs()[key])
        self.assertIsNone(self.plan().appearances.get(skey=key).pinned_rf)

    def test_keep_changes_after_a_settings_change_keeps_rf_numbers(self):
        self.edit('move_rf', self.key('Kim Keynote'), rf=7, pool='body')
        before = self.rfs()
        self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 2, 'mic_min': 3, 'demic_min': 3, 'premic_lead_min': 30, 'margin_min': 5,
            'pack_policy': 'fewest_packs'})
        self.generate('keep')
        self.assertEqual(2, self.plan().settings['a2_count'])
        self.assertEqual(before, self.rfs())
        self.generate('over')                                      # fresh numbering does differ
        self.assertNotEqual(before, self.rfs())

    def test_version_conflict_is_refused(self):
        version = self.plan().version
        self.edit('move_rf', self.key('Kim Keynote'), rf=7, pool='body')
        resp = self.edit('move_rf', self.key('Dana Able'), version=version, rf=3, pool='body')
        self.assertEqual(409, resp.status_code)
        self.assertIn('Reload', resp.json()['error'])
        self.assertEqual(1, self.plan().edits.count())
        self.assertEqual(409, self.undo(version=version).status_code)

    def test_a_stale_plan_refuses_edits_until_re_generated(self):
        self.client.post(reverse('planner:mic_plan_reread', args=[self.part.pk]))
        self.assertTrue(self.plan().stale)
        resp = self.edit('move_rf', self.key('Kim Keynote'), rf=7, pool='body')
        self.assertEqual(409, resp.status_code)
        self.assertIn('Re-generate', resp.json()['error'])
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'Moving packs is off until then.')
        self.assertNotContains(page, 'id="mp-edit"')

    def test_bad_input_is_refused(self):
        key = self.key('Kim Keynote')
        for fields in ({'kind': 'move_rf', 'key': key}, {'kind': 'move_rf', 'key': key, 'rf': 'x'},
                       {'kind': 'move_rf', 'key': key, 'rf': 9},          # Jo's backup pack
                       {'kind': 'move_rf', 'key': 'nobody|1|0', 'rf': 3}, {'kind': 'nope', 'key': key},
                       {'kind': 'set_mic_type', 'key': key, 'mic_type': 'body'}):
            with self.subTest(fields=fields):
                self.assertEqual(400, self.edit(**fields).status_code)
        self.assertEqual(0, self.plan().edits.count())


class EditsAcrossImportsTests(EditBase):

    def test_a_pin_survives_re_read_and_a_re_generate_after_it_changes_only_what_data_forces(self):
        key = self.key('Kim Keynote')
        self.edit('move_rf', key, rf=7, pool='body')
        before = self.rfs()
        self.client.post(reverse('planner:mic_plan_reread', args=[self.part.pk]))
        self.generate('keep')
        self.assertEqual(before, self.rfs())
        self.assertEqual([], self.plan().changes)
        # New data: Dana now needs a handheld. Only Dana moves.
        dana = self.person('Dana Able')
        self.client.post(reverse('planner:mic_plan_person', args=[dana.pk]), {'mic_hint': 'HH'})
        self.generate('keep')
        self.assertEqual([self.key('Dana Able')], [c['key'] for c in self.plan().changes])
        self.assertEqual({k: v for k, v in before.items() if not k.startswith('dana')},
                         {k: v for k, v in self.rfs().items() if not k.startswith('dana')})

    def test_a_pin_survives_replace_and_an_unmatched_one_is_reported(self):
        self.edit('move_rf', self.key('Kim Keynote'), rf=7, pool='body')
        MicPlanEdit.objects.create(plan=self.plan(), seq=99, kind='move_rf', key='lee gone|150|0',
                                   value={'rf': 4, 'pool': 'body', 'name': 'Lee Gone', 'line': '150',
                                          'from_rf': 2, 'from_pool': 'body'})
        self.upload('MAIN_PAGES', 'day1 again.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': f'replace:{self.part.pk}'})
        self.generate('keep')
        self.assertEqual([7, 'body'], self.rfs()[self.key('Kim Keynote')])
        unmatched = [f for f in self.plan().flags if f['kind'] == 'unmatched']
        self.assertEqual(1, len(unmatched))
        self.assertTrue(unmatched[0]['text'].startswith(
            'Your change to Lee Gone at line 150 no longer matches the showflow'))
        self.assertEqual(2, self.plan().edits.count())                       # kept, not applied
        self.assertContains(self.client.get(reverse('planner:mic_plan')), 'no longer matches the showflow')

    def test_conflicts_show_on_the_tiles_and_in_review(self):
        self.edit('move_rf', self.key('Dana Able'), rf=3, pool='body')
        self.edit('move_rf', self.key('Chris Baker'), rf=3, pool='body')      # both pinned, same stretch
        resp = self.edit('move_rf', self.key('Morgan Dee'), rf=5, pool='body')
        self.assertEqual(1, resp.json()['conflicts'])
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'RF conflict')
        self.assertContains(page, 'RF 3 on two people')
        self.assertContains(page, 'lane target conflict')


class EditAccessTests(EditBase):

    def test_viewers_see_pins_but_cannot_edit(self):
        key = self.key('Kim Keynote')
        self.edit('move_rf', key, rf=7, pool='body')
        self.use(self.viewer)
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'class="mp-pin"')
        self.assertNotContains(page, 'id="mp-edit"')
        self.assertNotContains(page, 'Undo:')
        self.assertNotContains(page, 'movable')
        self.assertEqual(403, self.edit('move_rf', key, rf=3, pool='body').status_code)
        self.assertEqual(403, self.undo().status_code)
        self.assertEqual(1, self.plan().edits.count())

    def test_another_project_gets_404(self):
        key = self.key('Kim Keynote')
        version = self.plan().version
        self.use(self.other_owner, self.other)
        self.assertEqual(404, self.edit('move_rf', key, version=version, rf=3, pool='body').status_code)
        self.assertEqual(404, self.undo(version=version).status_code)
        self.assertEqual(0, MicPlanEdit.objects.count())
