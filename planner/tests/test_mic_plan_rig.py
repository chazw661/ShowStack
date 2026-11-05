"""Mic Plan PR 5.1: plan RFs are the rig's channel numbers. Numbering on the
rig (body from 1, handhelds down from the top of their zone, spares at the
end, over the rig past its end); PR 5.1b: one shared pool (either type
overflows into the other zone before over; transmitter cards and swaps);
no rig unchanged; capacity flags at the rig's limits;
pins and preferences across a rig change; edits on the rig; the pack chart's
whole rack; Send to Mic Tracker in channel numbers, renumbered, blocked
while over the rig, reverted; the settings form; the 0225 conversion.
Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_rig --settings=audiopatch.test_settings
"""

import importlib
import re

from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import page, planning, push, revert
from planner.mic_plan.display import rig_text
from planner.mic_plan.solver import BODY, HH, Person, Rig, summary
from planner.models import MicAssignment, MicPlan, MicPlanSettings, MicSession, PresenterSlot
from planner.tests.test_mic_plan_edits import EditBase
from planner.tests.test_mic_plan_solver import Settings, Show, panel_day, rf, solve

to_rig = importlib.import_module('planner.migrations.0225_mic_plan_rig').to_rig


def mixed_day(body=2, hh=2):
    """``body`` body packs and ``hh`` handhelds on together, 9:00-9:30."""
    s = panel_day(body + hh)
    s.people[:] = [Person(k, 'Person {}'.format(k), BODY if k <= body else HH) for k in range(1, body + hh + 1)]
    return s


class NumberingTests(SimpleTestCase):

    def test_body_from_1_handhelds_down_from_the_top_of_their_zone_spares_at_the_end(self):
        plan = solve(mixed_day().day(), Settings(wireless_channels=10, handheld_channels=4, spare_handhelds=1))
        self.assertEqual(({1}, {2}, {9}, {8}), tuple(rf(plan, k) for k in (1, 2, 3, 4)))
        self.assertEqual([10], [p.rf for p in plan.packs if p.spare])
        self.assertFalse([p for p in plan.packs if p.over])
        self.assertFalse([f for f in plan.flags if f['kind'] == 'shortage'])

    def test_backups_follow_their_types_handhelds(self):
        s = mixed_day(1, 1)
        s.people[0] = Person(1, 'Person 1', BODY, HH)            # a handheld backup
        plan = solve(s.day(), Settings(wireless_channels=10, handheld_channels=4))
        # Handhelds, then handheld backups, counting down.
        self.assertEqual(({1}, {9}, {10}), (rf(plan, 1), rf(plan, 1, backup=True), rf(plan, 2)))

    def test_no_rig_is_numbered_as_before_with_the_spares_after_the_last_pack(self):
        plan = solve(mixed_day().day(), Settings(spare_handhelds=2))
        self.assertEqual(({1}, {2}, {3}, {4}), tuple(rf(plan, k) for k in (1, 2, 3, 4)))
        self.assertEqual([5, 6], [p.rf for p in plan.packs if p.spare])
        self.assertEqual(solve(mixed_day().day()).packs, [p for p in plan.packs if not p.spare])

    def test_at_the_limit_exactly_there_is_no_flag_one_more_is_over_the_rig(self):
        plan = solve(panel_day(3).day(), Settings(wireless_channels=3))
        self.assertFalse([f for f in plan.flags if f['kind'] in ('shortage', 'late', 'tight')])
        plan = solve(panel_day(3).day(), Settings(wireless_channels=2))
        self.assertEqual([3], [p.rf for p in plan.packs if p.over])
        self.assertEqual(1, summary(plan)['over'])
        self.assertEqual(['Line 2: need 1 more pack than the rig has — 2 channels (3 in use from 9:00a).'],
                         [f['text'] for f in plan.flags if f['kind'] == 'shortage'])

    def test_a_body_overflow_takes_the_handheld_zone_before_going_over(self):
        plan = solve(panel_day(3).day(), Settings(wireless_channels=4, handheld_channels=2))
        self.assertEqual([(1, BODY, False), (2, BODY, False), (3, BODY, False)],
                         [(p.rf, p.pool, p.over) for p in plan.packs])
        self.assertFalse([f for f in plan.flags if f['kind'] == 'shortage'])
        self.assertEqual(['RF 3 used as a body pack — needs a beltpack transmitter'],
                         [f['text'] for f in plan.flags if f['kind'] == 'rig_use'])

    def test_a_handheld_overflow_takes_the_body_zone_counting_down_and_never_the_spare(self):
        plan = solve(panel_day(3, HH).day(), Settings(wireless_channels=4, handheld_channels=2, spare_handhelds=1))
        self.assertEqual([(1, HH, False, False), (2, HH, False, False), (3, HH, False, False), (4, HH, True, False)],
                         [(p.rf, p.pool, p.spare, p.over) for p in plan.packs])
        self.assertNotIn(4, {a.rf_number for a in plan.actions})
        self.assertEqual(['RF 1 used as a handheld — needs a handheld transmitter',
                          'RF 2 used as a handheld — needs a handheld transmitter'],
                         sorted(f['text'] for f in plan.flags if f['kind'] == 'rig_use'))

    def test_over_only_when_every_channel_but_the_spares_is_busy(self):
        s = mixed_day(3, 2)
        plan = solve(s.day(), Settings(wireless_channels=6, handheld_channels=2, spare_handhelds=1))
        self.assertFalse([p for p in plan.packs if p.over])           # 5 on at once, 5 channels
        plan = solve(s.day(), Settings(wireless_channels=5, handheld_channels=2, spare_handhelds=1))
        self.assertEqual([6], [p.rf for p in plan.packs if p.over])   # past the spare
        self.assertEqual([5], [p.rf for p in plan.packs if p.spare])
        self.assertEqual(['Line 2: need 1 more pack than the rig has — 4 channels, 1 kept spare (5 in use from 9:00a).'],
                         [f['text'] for f in plan.flags if f['kind'] == 'shortage'])

    def test_rig_text(self):
        self.assertEqual('Body 1–20 · Handheld 21–23 · Spare 24',
                         rig_text({'wireless_channels': 24, 'handheld_channels': 4, 'spare_handhelds': 1}))
        self.assertEqual('Body 1–12', rig_text({'wireless_channels': 12, 'handheld_channels': 0, 'spare_handhelds': 0}))
        self.assertEqual('Body 1–12 · Spare 13',
                         rig_text({'wireless_channels': 13, 'handheld_channels': 1, 'spare_handhelds': 1}))
        self.assertEqual('No rig set: body from 1, handhelds after the last body pack, 1 spare after them',
                         rig_text({'wireless_channels': None, 'handheld_channels': 0, 'spare_handhelds': 1}))
        R = Rig(24, 4, 1)
        self.assertEqual((BODY, BODY, HH, HH, 'spare', None), tuple(R.pool_at(c) for c in (1, 20, 21, 23, 24, 25)))


def turnover_day(is_break=True):
    """Two body packs 9:05-9:30, then (after a break, or not) two handhelds 10:05-10:30."""
    s = Show()
    for k, t in enumerate(['9:00', '9:05', '9:30', '9:40', '10:00', '10:05', '10:30']):
        s.line(k + 1, t)
    s.segment(1, 2, 'Talk', '9:00', '9:30').segment(3, 4, 'Break', '9:30', '10:00', is_break=is_break)
    s.segment(5, 7, 'Panel', '10:00', '10:30')
    s.person(1, 'Body One').lists(1, 2).person(2, 'Body Two').lists(2, 2)
    s.person(3, 'Hand One', HH).lists(3, 6).person(4, 'Hand Two', HH).lists(4, 6)
    return s.day()


class SharedPoolTests(SimpleTestCase):
    """PR 5.1b: a channel freed by one type takes the other rather than go over."""

    RIG = Settings(wireless_channels=2, handheld_channels=1)

    def test_handhelds_take_the_freed_body_packs_at_the_break_instead_of_going_over(self):
        plan = solve(turnover_day(), self.RIG)
        self.assertEqual([(1, BODY, False), (2, BODY, False)], [(p.rf, p.pool, p.over) for p in plan.packs])
        self.assertEqual({3, 4}, {a.person for a in plan.actions if a.kind == 'mic' and a.rf_number in (1, 2)} - {1, 2})
        self.assertFalse([f for f in plan.flags if f['kind'] == 'shortage'])
        self.assertEqual([('rig_use', 'RF 2 used as a body pack — needs a beltpack transmitter'),
                          ('swap', 'RF 1: handheld from 9:36a after a body pack — swap the transmitter at the 9:30a break'),
                          ('swap', 'RF 2: handheld from 9:39a after a body pack — swap the transmitter at the 9:30a break')],
                         sorted((f['kind'], f['text']) for f in plan.flags))
        self.assertEqual(2, summary(plan)['tx_swaps'])

    def test_with_no_break_between_the_swap_is_mid_session(self):
        plan = solve(turnover_day(is_break=False), self.RIG)
        self.assertFalse([p for p in plan.packs if p.over])
        self.assertEqual(['swap_mid', 'swap_mid'], [f['kind'] for f in plan.flags if f['kind'].startswith('swap')])
        self.assertTrue(all(f['text'].endswith("swap mid-session (A2 is mic'ing others then)")
                            for f in plan.flags if f['kind'] == 'swap_mid'))

    def test_below_the_limit_each_type_gets_its_own_channels_and_no_card(self):
        plan = solve(turnover_day(), Settings(wireless_channels=4, handheld_channels=2))
        self.assertEqual([(1, BODY), (2, BODY), (3, HH), (4, HH)], [(p.rf, p.pool) for p in plan.packs])
        self.assertFalse([f for f in plan.flags if f['kind'] in ('rig_use', 'swap', 'swap_mid')])

    def test_a_pack_kept_on_between_appearances_is_freed_by_its_de_mic(self):
        # On at 9:00 and again at 9:40 (one wearing, de-mic'd at the second
        # appearance), then someone else at 10:30: never two in use at once.
        s = Show()
        for k, t in enumerate(['9:00', '9:10', '9:20', '9:30', '9:40', '9:50', '10:30', '10:50']):
            s.line(k + 1, t)
        s.segment(1, 2, 'A', '9:00', '9:20').segment(3, 4, 'B', '9:20', '9:40')
        s.segment(5, 6, 'C', '9:40', '10:00').segment(7, 8, 'D', '10:30', '11:00')
        s.person(1, 'Person 1').lists(1, 1, 5).person(2, 'Person 2').lists(2, 7)
        plan = solve(s.day(), Settings(wireless_channels=1))
        self.assertEqual(1, len([a for a in plan.actions if a.person == 1 and a.kind == 'mic']))
        self.assertFalse([f for f in plan.flags if f['kind'] == 'shortage'])

    def test_no_rig_no_zones(self):
        plan = solve(turnover_day())
        self.assertEqual(4, len(plan.packs))
        self.assertFalse([f for f in plan.flags if f['kind'] in ('rig_use', 'swap', 'swap_mid')])


class MigrationTests(SimpleTestCase):
    """0225's conversion of the old pack counts (capacity unchanged: the old
    spare came out of the handheld count)."""

    def test_conversion(self):
        self.assertEqual((24, 4, 1), to_rig(20, 4, True))
        self.assertEqual((13, 1, 1), to_rig(12, 1, True))
        self.assertEqual((12, 3, 0), to_rig(9, 3, False))
        self.assertEqual((None, 0, 0), to_rig(12, None, False))      # only one count: no rig
        self.assertEqual((None, 0, 1), to_rig(None, None, True))     # the spare, with no rig
        self.assertEqual((None, 0, 0), to_rig(0, 0, False))
        self.assertEqual((12, 0, 0), to_rig(12, 0, True))            # no handheld to keep spare

    def test_an_old_plans_settings_read_the_same_way(self):
        plan = MicPlan(settings={'a2_count': 1, 'body_pack_count': 20, 'hh_count': 4, 'emergency_spare_hh': True})
        values = planning.plan_values(plan)
        self.assertEqual((24, 4, 1, 'fewest_packs'), (values['wireless_channels'], values['handheld_channels'],
                                                      values['spare_handhelds'], values['pack_policy']))
        self.assertNotIn('body_pack_count', values)
        self.assertTrue(planning.before_rig(plan))
        self.assertFalse(planning.before_rig(MicPlan(settings={'body_pack_count': None, 'hh_count': None,
                                                               'emergency_spare_hh': True})))


# The fixture day with no rig: body RF 1-7, Pat Guest's handheld RF 8 and
# Jo Emcee's handheld backup RF 9.
class RigBase(EditBase):

    def rig(self, channels, handhelds=0, spares=0):
        s = planning.project_settings(self.project)
        s.wireless_channels, s.handheld_channels, s.spare_handhelds = channels, handhelds, spares
        s.save()

    def rf_of(self, name):
        return self.rfs()[self.key(name)][0]


class RigPlanTests(RigBase):

    def test_a_rig_change_renumbers_the_handhelds_and_keeps_the_body_packs(self):
        before = self.rfs()
        self.rig(12, 3, 1)
        self.generate()
        plan = self.plan()
        # RF 8 is in the body zone now: a rig change puts the handheld back in its zone.
        self.assertEqual(11, self.rf_of('Pat Guest'))
        self.assertEqual({k: v for k, v in before.items() if v[1] == 'body'},
                         {k: v for k, v in self.rfs().items() if v[1] == 'body'})
        self.assertEqual([(10, 'HH')], [(p['rf'], p['pool']) for p in plan.packs if p.get('backup_of')])
        self.assertFalse([f for f in plan.flags if f['kind'] in ('rig_use', 'swap', 'swap_mid')])
        self.assertEqual([12], [p['rf'] for p in plan.packs if p.get('spare')])
        self.assertIn('Pat (line', ' '.join(c['text'] for c in plan.changes))
        self.assertEqual('8–9', page.unused_channels(plan))

    def test_the_pack_chart_shows_the_whole_rack(self):
        self.rig(12, 3, 1)
        self.generate()
        resp = self.client.get(reverse('planner:mic_plan'))
        chart = resp.context['chart']
        self.assertEqual(list(range(1, 13)), [lane['rf'] for lane in chart['lanes']])
        lanes = {lane['rf']: lane for lane in chart['lanes']}
        self.assertTrue(lanes[8]['unused'] and lanes[9]['unused'])
        self.assertEqual(('SPARE', True), (lanes[12]['sub'], lanes[12]['spare']))
        self.assertIsNone(chart['new_rf'])                             # no "New pack" lane on a rig
        self.assertNotContains(resp, 'class="lane target newlane"')
        self.assertIn(8, [lane['rf'] for lane in resp.context['lanes']])        # an unused lane takes a move
        self.assertNotIn(12, [lane['rf'] for lane in resp.context['lanes']])
        self.assertContains(resp, 'Body 1–9 · Handheld 10–11 · Spare 12')

    def test_a_pin_survives_a_rig_change(self):
        key = self.key('Kim Keynote')
        self.assertEqual(200, self.edit('move_rf', key, rf=6, pool='body').status_code)
        self.rig(12, 3, 1)
        self.generate()
        app = self.plan().appearances.get(skey=key)
        self.assertEqual((6, 6), (self.rf_of('Kim Keynote'), app.pinned_rf))
        self.assertFalse([f for f in self.plan().flags if f['kind'] == 'rig'])

    def test_a_pin_on_the_other_zone_stays_and_says_which_transmitter(self):
        key = self.key('Kim Keynote')
        self.assertEqual(200, self.edit('move_rf', key, rf=8, pool='HH').status_code)     # Pat's handheld lane
        self.assertEqual([8, 'body'], self.rfs()[key])
        self.rig(12, 3, 1)                                             # RF 8 is a body channel now
        self.generate()
        self.assertEqual([8, 'body'], self.rfs()[key])
        self.assertFalse([f for f in self.plan().flags if f['kind'] == 'rig'])

    def test_a_pin_on_a_spare_keeps_its_type_gets_a_channel_and_is_flagged(self):
        key = self.key('Kim Keynote')
        self.assertEqual(200, self.edit('move_rf', key, rf=12, pool='body').status_code)    # no rig: a new pack
        self.rig(12, 3, 1)                                             # RF 12 is kept spare now
        self.generate()
        now, pool = self.rfs()[key]
        self.assertEqual('body', pool)
        self.assertNotEqual(12, now)
        flag, = [f for f in self.plan().flags if f['kind'] == 'rig']
        self.assertRegex(flag['text'], r'^Line \S+: your RF 12 pin is kept spare on this rig — now RF {} '
                                       r'\(body pack\)\.$'.format(now))
        app = self.plan().appearances.get(skey=key)
        self.assertEqual((None, 'body'), (app.pinned_rf, app.pinned_type))

    def test_moves_on_the_rig(self):
        self.rig(12, 3, 1)
        self.generate()
        key = self.key('Kim Keynote')
        resp = self.edit('move_rf', key, rf=13, pool='body')
        self.assertEqual((400, "RF 13 isn't in the rig (1–12)."), (resp.status_code, resp.json()['error']))
        resp = self.edit('move_rf', key, rf=12, pool='HH')
        self.assertEqual(400, resp.status_code)
        self.assertEqual('RF 12 is kept spare — lower the spare count in settings to use it.', resp.json()['error'])
        resp = self.edit('move_rf', key, rf=10, pool='HH')
        self.assertEqual('RF 10 is a backup pack.', resp.json()['error'])
        # Onto a handheld channel: still a body pack, which that channel now needs.
        self.assertEqual(200, self.edit('move_rf', key, rf=11, pool='HH').status_code)
        self.assertEqual([11, 'body'], self.rfs()[key])
        # Pat wears RF 11 first, so its transmitter is swapped at the break before Kim.
        cards = [(f['kind'], f['text']) for f in self.plan().flags if f['kind'] in ('rig_use', 'swap', 'swap_mid')]
        self.assertEqual([('swap', 'RF 11: body pack from 9:15a after a handheld — swap the transmitter at the '
                                   '9:00a break')], cards)
        resp = self.client.get(reverse('planner:mic_plan'))
        lane = {lane['rf']: lane for lane in resp.context['chart']['lanes']}[11]
        self.assertEqual(('HH', 'handheld → beltpack'), (lane['pool'], lane['tx']))
        self.assertContains(resp, ' k-swap"')
        a2 = self.client.get(reverse('planner:mic_plan_a2', args=[self.day.pk]))
        self.assertContains(a2, 'Swap RF 11 to beltpack transmitter')
        self.assertEqual(200, self.edit('move_rf', key, rf=8, pool='HH').status_code)        # an unused body channel
        self.assertEqual([8, 'body'], self.rfs()[key])

    def test_a_plan_numbered_before_the_rig_waits_for_a_re_generate(self):
        plan = self.plan()
        plan.settings = {k: v for k, v in plan.settings.items()
                         if k not in ('wireless_channels', 'handheld_channels', 'spare_handhelds')}
        plan.settings.update(body_pack_count=7, hh_count=2, emergency_spare_hh=False)
        plan.save()
        resp = self.edit('move_rf', self.key('Kim Keynote'), rf=6, pool='body')
        self.assertEqual((409, planning.BEFORE_RIG), (resp.status_code, resp.json()['error']))
        self.assertEqual(planning.BEFORE_RIG, push.refusal(plan, list(plan.appearances.all())))
        page_ = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page_, 'was numbered before rig channels')
        self.assertFalse(page_.context['editable'])
        # Old counts left blank: numbered the same as no rig today, so still editable.
        plan.settings.update(body_pack_count=None, hh_count=None)
        plan.save()
        self.assertEqual(200, self.edit('move_rf', self.key('Kim Keynote'), rf=6, pool='body').status_code)


class RigPushTests(RigBase):

    def preview(self):
        return push.preview(self.day)

    def send(self, expect=302):
        p = self.preview()
        resp = self.client.post(reverse('planner:mic_plan_push', args=[self.day.pk]),
                                {'version': p.plan.version, 'digest': p.digest})
        self.assertEqual(expect, resp.status_code)
        return p

    def slot(self, name):
        return PresenterSlot.objects.select_related('assignment').get(
            assignment__session__day=self.day, presenter__name=name)

    def test_push_uses_channel_numbers_and_listen_defaults_to_them(self):
        self.rig(12, 3, 1)
        self.generate()
        self.send()
        slot = self.slot('Pat Guest')
        self.assertEqual(11, slot.assignment.rf_number)
        self.assertIsNone(slot.assignment.input_channel)
        self.assertEqual(11, slot.assignment.effective_input_channel)
        self.assertTrue(PresenterSlot.objects.filter(assignment__session__day=self.day, assignment__rf_number=12,
                                                     notes='SPARE').exists())

    def test_a_rig_change_after_a_push_shows_each_renumbered_slot_and_its_label_then_reverts(self):
        self.send()
        self.assertEqual(8, self.slot('Pat Guest').assignment.rf_number)
        after_first = sorted(MicAssignment.objects.filter(session__day=self.day).values_list('session_id', 'rf_number'))
        self.rig(12, 3, 1)
        self.generate()
        p = self.preview()
        texts = [i['text'] for i in p.items]
        self.assertTrue(any(re.search(r'^RF 11 · .*: Pat Guest RF 8 → RF 11$', t) for t in texts), texts)
        self.assertTrue(any(lbl.startswith('RF 11 (') for lbl in p.labels), p.labels)
        self.assertEqual('Body 1–9 · Handheld 10–11 · Spare 12', p.rig)
        self.assertTrue(p.rig_was.startswith('No rig set'))
        resp = self.client.get(reverse('planner:mic_plan_push', args=[self.day.pk]))
        self.assertContains(resp, 'Rig changed since the last push')
        self.send()
        self.assertEqual(11, self.slot('Pat Guest').assignment.rf_number)
        # The revert from #174 still puts Mic Tracker back as the first push left it.
        r = revert.preview(self.day)
        self.assertTrue(any(re.search(r'· Pat Guest: back to RF 8 · ', a) for a in r.actions), r.actions)
        resp = self.client.post(reverse('planner:mic_plan_revert', args=[self.day.pk]),
                                {'push': r.push.pk, 'digest': r.digest})
        self.assertEqual(302, resp.status_code)
        self.assertEqual(8, self.slot('Pat Guest').assignment.rf_number)
        self.assertEqual(after_first, sorted(MicAssignment.objects.filter(session__day=self.day)
                                             .values_list('session_id', 'rf_number')))

    def cards(self):
        """{session name: {rf: [presenter names or None]}} of the day."""
        out = {}
        for r in MicAssignment.objects.filter(session__day=self.day).select_related('session'):
            out.setdefault(r.session.name, {})[r.rf_number] = [
                sl.presenter.name if sl.presenter else sl.notes for sl in r.presenter_slots.order_by('order')]
        return out

    def test_every_session_has_a_card_for_every_channel(self):
        self.rig(12, 3, 1)
        self.generate()
        resp = self.client.get(reverse('planner:mic_plan_push', args=[self.day.pk]))
        self.assertContains(resp, ', 1 spare')
        self.send()
        cards = self.cards()
        self.assertTrue(cards)
        for name, rows in cards.items():
            with self.subTest(session=name):
                self.assertEqual(list(range(1, 13)), sorted(rows))
                self.assertEqual(['SPARE'], rows[12])
                self.assertEqual(12, MicSession.objects.get(day=self.day, name=name).num_mics)
        # Unused channels (8-9 on this rig) are empty cards: a row, no slot, blank type.
        empty = MicAssignment.objects.filter(session__day=self.day, rf_number=8)
        self.assertTrue(empty.exists())
        self.assertFalse(PresenterSlot.objects.filter(assignment__in=empty).exists())
        self.assertEqual({''}, set(empty.values_list('mic_type', flat=True)))

    def test_a_smaller_rig_removes_empty_rows_above_it_and_keeps_rows_with_a2_data(self):
        self.rig(16, 3, 1)
        self.generate()
        self.send()
        first = MicSession.objects.filter(day=self.day).order_by('order').first()
        MicAssignment.objects.filter(session=first, rf_number=13).update(notes='batteries swapped')
        self.rig(12, 3, 1)
        self.generate()
        p = self.preview()
        self.assertIn('{}: row kept — has A2 data (notes)'.format(push._label(first.name, 13)),
                      [i['text'] for i in p.group('kept')])
        self.send()
        self.assertEqual(list(range(1, 14)), sorted(first.mic_assignments.values_list('rf_number', flat=True)))
        for s in MicSession.objects.filter(day=self.day).exclude(pk=first.pk):
            self.assertEqual(list(range(1, 13)), sorted(s.mic_assignments.values_list('rf_number', flat=True)))
        self.assertEqual(['SPARE'], self.cards()[first.name][12])

    def test_slot_notes_say_which_transmitter_and_the_swap(self):
        self.rig(12, 3, 1)
        self.generate()
        self.assertEqual(200, self.edit('move_rf', self.key('Kim Keynote'), rf=11).status_code)
        self.send()
        self.assertEqual('beltpack on HH channel · Swap RF 11 to beltpack transmitter at the 9:00a break',
                         self.slot('Kim Keynote').notes)
        self.assertEqual('', self.slot('Pat Guest').notes)

    def test_send_is_blocked_while_the_plan_is_over_the_rig(self):
        self.rig(6, 1)                     # body 1-5, handheld 6 for a handheld and a backup
        self.generate()
        plan = self.plan()
        self.assertEqual([(7, 'body'), (8, 'HH')], [(p['rf'], p['pool']) for p in plan.packs if p.get('over')])
        self.assertIn("Line 102: no channel left for Jo Emcee's backup, RF 8 is past the rig — 6 channels.",
                      [f['text'] for f in plan.flags])
        # Over only once all 6 channels are in use: the handheld first takes a
        # free body pack mid-session, and a body pack the handheld channel.
        self.assertIn('Line 109: need 1 more pack than the rig has — 6 channels (7 in use from 8:30a).',
                      [f['text'] for f in plan.flags])
        self.assertEqual(['swap_mid'], [f['kind'] for f in plan.flags if f['kind'] in ('swap', 'swap_mid')])
        text = 'The rig is short by 1 body pack and 1 handheld (RF 7–8). Add channels, or move people, then send.'
        self.assertEqual(text, self.preview().short)
        resp = self.client.get(reverse('planner:mic_plan_push', args=[self.day.pk]))
        self.assertContains(resp, text)
        self.assertNotContains(resp, '<button class="mp-btn primary" type="submit"')
        self.send(expect=302)
        self.assertFalse(MicAssignment.objects.filter(session__day=self.day).exists())
        chart = self.client.get(reverse('planner:mic_plan')).context['chart']
        self.assertEqual([7, 8], [lane['rf'] for lane in chart['lanes'] if lane['over']])
        self.rig(9, 2)
        self.generate()
        self.assertEqual('', self.preview().short)
        self.send()
        self.assertTrue(MicAssignment.objects.filter(session__day=self.day).exists())


class RigSettingsTests(RigBase):

    def save(self, **rig):
        return self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 1, 'mic_min': 3, 'demic_min': 3, 'premic_lead_min': 30, 'margin_min': 5, **rig},
            follow=True)

    def stored(self):
        s = MicPlanSettings.objects.get(project=self.project)
        return s.wireless_channels, s.handheld_channels, s.spare_handhelds

    def test_saves_and_previews_the_rig(self):
        resp = self.save(wireless_channels='24', handheld_channels='4', spare_handhelds='1')
        self.assertEqual((24, 4, 1), self.stored())
        self.assertContains(resp, 'id="mp-rig"')
        self.assertContains(resp, 'Body 1–20 · Handheld 21–23 · Spare 24')
        self.save(wireless_channels='', handheld_channels='', spare_handhelds='')
        self.assertEqual((None, 0, 0), self.stored())

    def test_refuses_more_handhelds_than_channels_or_more_spares_than_handhelds(self):
        self.save(wireless_channels='24', handheld_channels='4', spare_handhelds='1')
        for rig, text in ((('8', '9', '0'), 'Handhelds: at most the 8 wireless channels.'),
                          (('8', '2', '3'), 'Spare handhelds: at most the 2 handhelds.'),
                          (('', '2', '0'), 'set Wireless channels first'),
                          (('101', '0', '0'), 'Mic Tracker holds at most 100 channels per session'),
                          (('0', '0', '0'), 'Wireless channels: enter a whole number in range')):
            with self.subTest(rig=rig):
                resp = self.save(wireless_channels=rig[0], handheld_channels=rig[1], spare_handhelds=rig[2])
                self.assertContains(resp, text)
                self.assertEqual((24, 4, 1), self.stored())
