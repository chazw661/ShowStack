"""Mic Plan PR 5.3: de-mic helpers per segment. A helper only de-mics, only
in its segment; a helper at a short break lets its packs turn over; busy
figures are split; the fix suggestion; stored by the heading's line (Re-read
and Replace keep it); editors only; and a helper's a2_index (0) never
reaches a per-A2 lookup. Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_helpers --settings=audiopatch.test_settings
"""

from dataclasses import replace

from django.test import SimpleTestCase
from django.urls import reverse

from planner.mic_plan import page, planning, schedule
from planner.mic_plan.solver import HELPER, HELPERS, is_helper, summary
from planner.models import MicPlanSettings, ShowflowImport
from planner.tests.test_mic_plan_edits import EditBase
from planner.tests.test_mic_plan_solver import Settings, Show, solve

BREAK = 3                    # the break's heading row key in turnover_day


def turnover_day(helpers=0):
    """Five people off at 11:15, a 15-min break, nine more on at 11:35."""
    s = Show()
    for k, t in enumerate(['10:30', '10:35', '11:15', '11:20', '11:30', '11:35', '12:00']):
        s.line(k + 1, t)
    s.segment(1, 2, 'Talk', '10:30', '11:15').segment(3, 4, 'Break', '11:15', '11:30', is_break=True)
    s.segment(5, 7, 'Panel', '11:30', '12:00')
    for p in range(1, 6):
        s.person(p, 'Off {}'.format(p)).lists(p, 2)
    for p in range(6, 15):
        s.person(p, 'On {}'.format(p)).lists(p, 6)
    day = s.day()
    return replace(day, segments=tuple(replace(x, helpers=helpers) if x.key == BREAK else x for x in day.segments))


class HelperSolverTests(SimpleTestCase):

    RIG = Settings(wireless_channels=9)

    def test_a_helper_only_de_mics_and_only_in_its_segment(self):
        plan = solve(turnover_day(1))
        mine = [a for a in plan.actions if is_helper(a)]
        self.assertEqual(5, len(mine))
        self.assertEqual({'demic'}, {a.kind for a in mine})
        self.assertTrue(all(11 * 60 + 15 <= a.start_min < 11 * 60 + 30 for a in mine))
        self.assertEqual({HELPER}, {a.a2_index for a in mine})
        self.assertFalse([a for a in plan.actions if a.kind == 'mic' and is_helper(a)])

    def test_a_helper_at_the_break_lets_its_packs_turn_over(self):
        # 5 off, 9 on after a 15-min break: alone the A2 must mic first, so
        # the rig runs over; with a helper the five packs come back in time.
        alone, helped = solve(turnover_day(0), self.RIG), solve(turnover_day(1), self.RIG)
        self.assertEqual((2, 1), (summary(alone)['over'], summary(alone)['shortage']))
        self.assertEqual((0, 0, 0, 9), (summary(helped)['over'], summary(helped)['shortage'],
                                        summary(helped)['late'], summary(helped)['body']))
        self.assertFalse([f for f in helped.flags if f['kind'] == 'break'])
        # With no rig the day needs four fewer packs.
        self.assertEqual((14, 10), (summary(solve(turnover_day(0)))['body'], summary(solve(turnover_day(1)))['body']))

    def test_busy_figures_are_split(self):
        plan = solve(turnover_day(1))
        self.assertEqual(15.0, plan.helper_busy[BREAK])
        a2 = sum(min(a.end_min, 690) - max(a.start_min, 675) for a in plan.actions
                 if not is_helper(a) and a.start_min < 690 and a.end_min > 675)
        self.assertEqual([round(a2, 1)], plan.busy[BREAK])
        self.assertNotIn(BREAK, solve(turnover_day(0)).helper_busy)

    def test_on_a_two_a2_day_each_a2s_busy_figures_are_its_own_actions(self):
        # A helper's a2_index is 0: busy[0 - 1] would be A2 2's figure.
        plan = solve(turnover_day(1), Settings(a2_count=2))
        self.assertTrue(any(is_helper(a) for a in plan.actions))
        for seg in turnover_day().segments:
            for a2 in (1, 2):
                own = sum(max(0, min(a.end_min, seg.t1) - max(a.start_min, seg.t0)) for a in plan.actions
                          if a.a2_index == a2 and not is_helper(a))
                self.assertAlmostEqual(round(own, 1), plan.busy[seg.key][a2 - 1], places=1,
                                       msg='A2 {} in {}'.format(a2, seg.name))
            self.assertEqual(2, len(plan.busy[seg.key]))

    def test_the_fix_suggests_a_helper_at_the_break(self):
        plan = solve(turnover_day(0), self.RIG)
        short, = [f for f in plan.flags if f['kind'] == 'shortage']
        self.assertTrue(short['text'].endswith('Fix: 1 de-mic helper at the 11:15a break (line 3).'), short['text'])
        self.assertEqual(BREAK, short['fix']['helper'])
        quiet = solve(turnover_day(0), self.RIG, suggest=False)          # an edit's re-solve
        self.assertFalse([f for f in quiet.flags if 'de-mic helper' in f['text']])

    def test_at_most_three_helpers(self):
        self.assertEqual(summary(solve(turnover_day(3)))['body'], summary(solve(turnover_day(9)))['body'])
        self.assertEqual(5, sum(1 for a in solve(turnover_day(9)).actions if is_helper(a)))


class HelperPageTests(EditBase):

    def heads(self):
        rows = list(self.part.rows.order_by('order'))
        return planning.part_segments(self.part, rows, planning.named_orders(self.day, self.part))

    def set(self, row, n):
        return self.client.post(reverse('planner:mic_plan_helpers', args=[self.part.pk]),
                                {'row': row.pk, 'helpers': str(n)})

    def help_everywhere(self, n=1):
        for seg in self.heads():
            self.assertEqual(302, self.set(seg['row'], n).status_code)

    def test_set_shown_and_kept_with_the_break_override(self):
        seg = self.heads()[0]
        self.set(seg['row'], 2)
        self.assertTrue(self.plan().stale)
        self.client.post(reverse('planner:mic_plan_break', args=[self.part.pk]),
                         {'row': seg['row'].pk, 'is_break': '0' if seg['is_break'] else '1'})
        self.part.refresh_from_db()
        now = self.heads()[0]
        self.assertEqual((2, not seg['is_break']), (now['helpers'], now['is_break']))
        self.client.post(reverse('planner:mic_plan_break', args=[self.part.pk]),
                         {'row': seg['row'].pk, 'is_break': '1' if seg['is_break'] else '0'})
        self.part.refresh_from_db()
        self.assertEqual((2, None), (self.heads()[0]['helpers'], self.heads()[0]['override']))
        resp = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(resp, '2 helpers · set by you')
        self.set(seg['row'], 0)
        self.part.refresh_from_db()
        self.assertEqual({}, self.part.break_overrides)
        self.assertEqual(302, self.set(seg['row'], 4).status_code)                  # refused: 0 to 3
        self.part.refresh_from_db()
        self.assertEqual({}, self.part.break_overrides)

    def test_survives_re_read_and_replace(self):
        seg = self.heads()[1]
        self.set(seg['row'], 1)
        self.client.post(reverse('planner:mic_plan_reread', args=[self.part.pk]))
        self.part.refresh_from_db()
        self.assertEqual(1, self.heads()[1]['helpers'])
        self.upload()
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]), {'choice': f'replace:{self.part.pk}'})
        self.part = ShowflowImport.objects.get(day=self.day, status='active')
        self.assertEqual(pending.pk, self.part.pk)
        self.assertEqual(1, self.heads()[1]['helpers'])

    def test_a_viewer_cannot_set_helpers(self):
        self.use(self.viewer)
        self.assertEqual(403, self.set(self.heads()[0]['row'], 1).status_code)
        self.part.refresh_from_db()
        self.assertEqual({}, self.part.break_overrides)
        self.assertNotContains(self.client.get(reverse('planner:mic_plan')), 'name="helpers"')

    def test_a_helper_never_reaches_an_a2s_figures(self):
        # Two A2s and helpers everywhere: A2 2's busy figures and schedule are
        # exactly what they are with the helper's actions taken out.
        s = MicPlanSettings.objects.get(project=self.project)
        s.a2_count = 2
        s.save()
        self.help_everywhere()
        self.generate()
        plan = self.plan()
        _, actions = page.load(plan)
        mine = [a for a in actions if is_helper(a)]
        self.assertTrue(mine)
        parts = [self.part]
        for a2 in (1, 2):
            with self.subTest(a2=a2):
                with_helpers = schedule.build(plan, actions, a2, parts)
                bare = replace_plan(plan)
                self.assertEqual(schedule.build(bare, [a for a in actions if not is_helper(a)], a2, parts),
                                 with_helpers)
        for seg in plan.segments:
            self.assertEqual(2, len(seg['busy']))
        rows = page.segment_rows(plan)
        self.assertTrue(all(m['a2'] in ('A2 1', 'A2 2') for r in rows.values() for m in r['meters']))
        helpers = schedule.build(plan, actions, HELPERS, parts)
        listed = [a for sess in helpers['sessions'] for seg in sess['segments'] for a in seg['actions']]
        self.assertEqual(len(mine), len(listed))
        self.assertTrue(all(a['kind'] == 'demic' and a['a2'] == 'Helper' for a in listed))

    def test_the_schedule_and_pdf_have_a_helpers_list_and_a2_0_is_not_it(self):
        self.help_everywhere()
        self.generate()
        url = reverse('planner:mic_plan_a2', args=[self.day.pk])
        resp = self.client.get(url + '?a2=helpers')
        self.assertTrue(resp.context['sched']['helpers'])
        self.assertContains(resp, 'De-mic helpers')
        zero = self.client.get(url + '?a2=0')
        self.assertEqual(1, zero.context['sched']['a2'])
        self.assertFalse(zero.context['sched']['helpers'])
        self.assertContains(zero, 'href="?a2=helpers"')
        self.assertEqual(1, schedule.a2_choice('0', 1, helpers=True))
        self.assertEqual(1, schedule.a2_choice('helpers', 1, helpers=False))
        pdf = self.client.get(reverse('planner:mic_plan_pdf', args=[self.day.pk]) + '?a2=helpers')
        self.assertEqual(200, pdf.status_code)
        self.assertIn(b'-a2-helpers', pdf['Content-Disposition'].encode())
        data = self.client.get(reverse('planner:mic_plan_json', args=[self.day.pk])).json()
        self.assertTrue(any(a['helper'] for a in data['actions']))


def replace_plan(plan):
    """``plan`` as if it had no helpers: helper minutes taken off its segments."""
    from types import SimpleNamespace
    return SimpleNamespace(settings=plan.settings, flags=plan.flags, packs=plan.packs,
                           segments=[dict(s, helper_busy=0) for s in plan.segments])
