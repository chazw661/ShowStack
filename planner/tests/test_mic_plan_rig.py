"""Mic Plan PR 5.1: plan RFs are the rig's channel numbers. Numbering on the
rig (body from 1, handhelds the last channels, spares at the end, over the
rig past its end); no rig unchanged; capacity flags at the rig's limits;
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
from planner.models import MicAssignment, MicPlan, MicPlanSettings, PresenterSlot
from planner.tests.test_mic_plan_edits import EditBase
from planner.tests.test_mic_plan_solver import Settings, panel_day, rf, solve

to_rig = importlib.import_module('planner.migrations.0225_mic_plan_rig').to_rig


def mixed_day(body=2, hh=2):
    """``body`` body packs and ``hh`` handhelds on together, 9:00-9:30."""
    s = panel_day(body + hh)
    s.people[:] = [Person(k, 'Person {}'.format(k), BODY if k <= body else HH) for k in range(1, body + hh + 1)]
    return s


class NumberingTests(SimpleTestCase):

    def test_body_from_1_handhelds_from_the_first_handheld_channel_spares_at_the_end(self):
        plan = solve(mixed_day().day(), Settings(wireless_channels=10, handheld_channels=4, spare_handhelds=1))
        self.assertEqual(({1}, {2}, {7}, {8}), tuple(rf(plan, k) for k in (1, 2, 3, 4)))
        self.assertEqual([10], [p.rf for p in plan.packs if p.spare])
        self.assertFalse([p for p in plan.packs if p.over])
        self.assertFalse([f for f in plan.flags if f['kind'] == 'shortage'])

    def test_backups_stay_in_their_pools_channels(self):
        s = mixed_day(1, 1)
        s.people[0] = Person(1, 'Person 1', BODY, HH)            # a handheld backup
        plan = solve(s.day(), Settings(wireless_channels=10, handheld_channels=4))
        # Handhelds, then handheld backups.
        self.assertEqual(({1}, {8}, {7}), (rf(plan, 1), rf(plan, 1, backup=True), rf(plan, 2)))

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
        self.assertEqual(['Line 2: need 1 more body pack than the rig has — 2 body channels (3 in use from 9:00a).'],
                         [f['text'] for f in plan.flags if f['kind'] == 'shortage'])

    def test_a_body_overflow_never_takes_a_handheld_channel_nor_the_other_way(self):
        plan = solve(panel_day(3).day(), Settings(wireless_channels=4, handheld_channels=2))
        self.assertEqual([(1, BODY, False), (2, BODY, False), (5, BODY, True)],
                         [(p.rf, p.pool, p.over) for p in plan.packs])
        plan = solve(panel_day(3, HH).day(), Settings(wireless_channels=4, handheld_channels=2, spare_handhelds=1))
        self.assertEqual([(3, HH, False, False), (4, HH, True, False), (5, HH, False, True), (6, HH, False, True)],
                         [(p.rf, p.pool, p.spare, p.over) for p in plan.packs])

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
        self.assertEqual(10, self.rf_of('Pat Guest'))                 # was RF 8: a body channel now
        self.assertEqual({k: v for k, v in before.items() if v[1] == 'body'},
                         {k: v for k, v in self.rfs().items() if v[1] == 'body'})
        self.assertEqual([(11, 'HH')], [(p['rf'], p['pool']) for p in plan.packs if p.get('backup_of')])
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

    def test_a_pin_the_rig_no_longer_fits_keeps_its_type_gets_a_channel_and_is_flagged(self):
        key = self.key('Kim Keynote')
        self.assertEqual(200, self.edit('move_rf', key, rf=8, pool='body').status_code)     # RF 8: a handheld
        self.assertEqual([8, 'HH'], self.rfs()[key])
        self.rig(12, 3, 1)                                             # RF 8 is a body channel now
        self.generate()
        now, pool = self.rfs()[key]
        self.assertEqual('HH', pool)
        self.assertIn(now, (10, 11))
        flag, = [f for f in self.plan().flags if f['kind'] == 'rig']
        self.assertRegex(flag['text'], r'^Line \S+: your RF 8 pin is a body channel on this rig — now RF {} '
                                       r'\(handheld\)\.$'.format(now))
        app = self.plan().appearances.get(skey=key)
        self.assertEqual((None, 'HH'), (app.pinned_rf, app.pinned_type))

    def test_moves_on_the_rig(self):
        self.rig(12, 3, 1)
        self.generate()
        key = self.key('Kim Keynote')
        resp = self.edit('move_rf', key, rf=13, pool='body')
        self.assertEqual((400, "RF 13 isn't in the rig (1–12)."), (resp.status_code, resp.json()['error']))
        resp = self.edit('move_rf', key, rf=12, pool='HH')
        self.assertEqual(400, resp.status_code)
        self.assertEqual('RF 12 is kept spare — lower the spare count in settings to use it.', resp.json()['error'])
        resp = self.edit('move_rf', key, rf=11, pool='HH')
        self.assertEqual('RF 11 is a backup pack.', resp.json()['error'])
        self.assertEqual(200, self.edit('move_rf', key, rf=10, pool='body').status_code)     # the channel's pool wins
        self.assertEqual([10, 'HH'], self.rfs()[key])
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
        self.assertEqual(10, slot.assignment.rf_number)
        self.assertIsNone(slot.assignment.input_channel)
        self.assertEqual(10, slot.assignment.effective_input_channel)
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
        self.assertTrue(any(re.search(r'^RF 10 · .*: Pat Guest RF 8 → RF 10$', t) for t in texts), texts)
        self.assertTrue(any(lbl.startswith('RF 10 (') for lbl in p.labels), p.labels)
        self.assertEqual('Body 1–9 · Handheld 10–11 · Spare 12', p.rig)
        self.assertTrue(p.rig_was.startswith('No rig set'))
        resp = self.client.get(reverse('planner:mic_plan_push', args=[self.day.pk]))
        self.assertContains(resp, 'Rig changed since the last push')
        self.send()
        self.assertEqual(10, self.slot('Pat Guest').assignment.rf_number)
        # The revert from #174 still puts Mic Tracker back as the first push left it.
        r = revert.preview(self.day)
        self.assertTrue(any(re.search(r'· Pat Guest: back to RF 8 · ', a) for a in r.actions), r.actions)
        resp = self.client.post(reverse('planner:mic_plan_revert', args=[self.day.pk]),
                                {'push': r.push.pk, 'digest': r.digest})
        self.assertEqual(302, resp.status_code)
        self.assertEqual(8, self.slot('Pat Guest').assignment.rf_number)
        self.assertEqual(after_first, sorted(MicAssignment.objects.filter(session__day=self.day)
                                             .values_list('session_id', 'rf_number')))

    def test_send_is_blocked_while_the_plan_is_over_the_rig(self):
        self.rig(6, 1)                     # body 1-5, handheld 6 for a handheld and a backup
        self.generate()
        plan = self.plan()
        self.assertEqual([(7, 'body'), (8, 'HH')], [(p['rf'], p['pool']) for p in plan.packs if p.get('over')])
        self.assertIn("Line 102: no handheld channel left for Jo Emcee's backup, RF 8 is past the rig — "
                      "1 handheld channel.", [f['text'] for f in plan.flags])
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
                          (('0', '0', '0'), 'Wireless channels: enter a whole number in range')):
            with self.subTest(rig=rig):
                resp = self.save(wireless_channels=rig[0], handheld_channels=rig[1], spare_handhelds=rig[2])
                self.assertContains(resp, text)
                self.assertEqual((24, 4, 1), self.stored())
