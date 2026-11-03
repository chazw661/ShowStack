"""Mic Plan solver (planner/mic_plan/solver.py): appearances, hosts, packs
and A2 actions, on plain inputs with made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_solver --settings=audiopatch.test_settings
"""

from datetime import date
from unittest import TestCase

from django.contrib.auth.models import User
from django.test import TestCase as DbTestCase

from planner.mic_plan import importer, planning, solver
from planner.mic_plan.display import format_action
from planner.mic_plan.solver import BODY, HH, Cue, Day, Person, Row, Segment, Settings, solve
from planner.models import Project, ShowDay
from planner.tests import showflow_fixture as F

PART = 1


def h(text):
    """'9:30' -> minutes."""
    hh, mm = text.split(':')
    return int(hh) * 60 + int(mm)


class Show:
    """A one-part day built line by line: ``line(no, time)``, ``segment(...)``,
    ``lists(person, *lines)``, ``cue(kind, person, line)``."""

    def __init__(self):
        self.rows, self.segments, self.people, self.cues, self.listings = [], [], [], [], {}
        self.cued = False

    def line(self, no, time=None):
        self.rows.append(Row(len(self.rows) + 1, PART, len(self.rows), str(no),
                             h(time) if time else None))
        return self

    def key(self, no):
        return next(r.key for r in self.rows if r.line == str(no))

    def segment(self, first, last, name, t0, t1, is_break=False):
        """Lines ``first``..``last`` (inclusive) under heading ``first``."""
        start = self.key(first) - 1
        end = self.key(last)
        self.segments.append(Segment(self.key(first), PART, start, end, name, h(t0), h(t1), is_break))
        return self

    def person(self, key, name, mic=BODY, backup=None):
        self.people.append(Person(key, name, mic, backup))
        return self

    def lists(self, person, *lines):
        self.listings.setdefault(person, []).extend(self.key(n) for n in lines)
        return self

    def cue(self, kind, person, line, time):
        self.cued = True
        self.cues.append(Cue(kind, person, self.key(line), h(time)))
        return self

    def day(self):
        return Day(tuple(self.rows), tuple(self.segments), tuple(self.people), tuple(self.cues),
                   dict(self.listings), frozenset([PART]) if self.cued else frozenset())


def panel_day(n_people=4, mic=BODY):
    """Opening 9:00-9:30 with ``n_people`` on together; nobody else."""
    s = Show().line(1, '9:00').line(2).line(3, '9:30').line(4, '10:00')
    s.segment(1, 2, 'Opening', '9:00', '9:30').segment(3, 4, 'Close', '9:30', '10:00')
    for k in range(1, n_people + 1):
        s.person(k, 'Person {}'.format(k), mic).lists(k, 2)
    return s


def mics(plan, person=None):
    return [a for a in plan.actions if a.kind == 'mic' and (person is None or a.person == person)]


def rf(plan, person, backup=False):
    return {s.rf for s in plan.assignments
            if plan.appearances[s.appearance].person == person and s.backup == backup}


class AppearanceTests(TestCase):

    def test_cue_free_on_is_the_first_row_and_off_the_next_rows_time(self):
        s = (Show().line(1, '9:00').line(2, '9:05').line(3, '9:20').line(4, '9:30').line(5, '10:00')
             .segment(1, 3, 'Opening', '9:00', '9:30').segment(4, 5, 'Keynote', '9:30', '10:00')
             .person(1, 'Ana Bell').lists(1, 2))
        app, = solve(s.day()).appearances
        self.assertEqual((h('9:05'), h('9:20'), 'listed'), (app.on, app.off, app.source))

    def test_cue_free_off_is_capped_at_the_end_of_the_segment(self):
        s = (Show().line(1, '9:00').line(2, '9:05').line(3, '10:00')
             .segment(1, 2, 'Opening', '9:00', '9:30').segment(3, 3, 'Next', '10:00', '10:30')
             .person(1, 'Ana Bell').lists(1, 2))
        app, = solve(s.day()).appearances
        self.assertEqual(h('9:30'), app.off)

    def test_listings_in_consecutive_segments_merge_and_a_gap_splits(self):
        s = (Show().line(1, '9:00').line(2).line(3, '9:30').line(4).line(5, '10:00').line(6)
             .line(7, '10:30').line(8)
             .segment(1, 2, 'A', '9:00', '9:30').segment(3, 4, 'B', '9:30', '10:00')
             .segment(5, 6, 'C', '10:00', '10:30').segment(7, 8, 'D', '10:30', '11:00')
             .person(1, 'Ana Bell').lists(1, 2, 4)        # A and B: one appearance
             .person(2, 'Cy Dunn').lists(2, 2, 6))        # A and C, B between: two
        apps = solve(s.day()).appearances
        self.assertEqual([(h('9:00'), h('10:00'))], [(a.on, a.off) for a in apps if a.person == 1])
        self.assertEqual([(h('9:00'), h('9:30')), (h('10:00'), h('10:30'))],
                         [(a.on, a.off) for a in apps if a.person == 2])

    def test_cued_send_to_catch_and_never_caught_is_assumed(self):
        s = (Show().line(1, '9:00').line(2).line(3, '9:30').line(4).line(5, '10:00')
             .segment(1, 2, 'A', '9:00', '9:30').segment(3, 4, 'B', '9:30', '10:00')
             .segment(5, 5, 'C', '10:00', '10:30')
             .person(1, 'Ana Bell').person(2, 'Cy Dunn').lists(1, 2).lists(2, 4)
             .cue('send', 1, 1, '9:00').cue('catch', 1, 3, '9:30').cue('send', 2, 3, '9:30'))
        apps = {a.person: a for a in solve(s.day()).appearances}
        self.assertEqual((h('9:00'), h('9:30'), ''), (apps[1].on, apps[1].off, apps[1].assumed))
        self.assertEqual(h('10:00'), apps[2].off)
        self.assertIn('never caught', apps[2].assumed)

    def test_caught_but_still_listed_stays_on(self):
        s = (Show().line(1, '9:00').line(2).line(3, '9:30').line(4).line(5, '10:00')
             .segment(1, 2, 'A', '9:00', '9:30').segment(3, 4, 'B', '9:30', '10:00')
             .segment(5, 5, 'C', '10:00', '10:30')
             .person(1, 'Ana Bell').lists(1, 1, 3)       # in the Speaker cells of A and B
             .cue('send', 1, 1, '9:00').cue('catch', 1, 3, '9:30'))
        app, = solve(s.day()).appearances
        self.assertEqual(h('10:00'), app.off)
        self.assertIn('still listed', app.assumed)

    def test_cued_parts_count_a_segment_only_from_its_heading_speakers(self):
        # Welcomed on the line before B's heading, listed in B's Speaker cell:
        # on for B, not for A (the parser's "No cue" rule reads it the same way).
        s = (Show().line(1, '9:00').line(2, '9:25').line(3, '9:30').line(4).line(5, '10:00')
             .segment(1, 2, 'A', '9:00', '9:30').segment(3, 4, 'B', '9:30', '10:00')
             .segment(5, 5, 'C', '10:00', '10:30')
             .person(1, 'Ana Bell').person(2, 'Cy Dunn').lists(1, 2, 3).lists(2, 1)
             .cue('send', 2, 1, '9:00').cue('catch', 2, 3, '9:30'))
        app, = [a for a in solve(s.day()).appearances if a.person == 1]
        self.assertEqual((h('9:30'), h('10:00'), 'listed'), (app.on, app.off, app.source))


class PackTests(TestCase):

    def test_three_appearances_make_a_host_with_one_pack_all_day(self):
        s = Show()
        for k, t in enumerate(('9:00', '9:30', '10:00', '10:30', '11:00', '11:30', '12:00')):
            s.line(k + 1, t)
        s.segment(1, 1, 'A', '9:00', '9:30').segment(2, 2, 'B', '9:30', '10:00') \
         .segment(3, 3, 'C', '10:00', '10:30').segment(4, 4, 'D', '10:30', '11:00') \
         .segment(5, 5, 'E', '11:00', '11:30').segment(6, 7, 'F', '11:30', '12:30')
        s.person(1, 'Hal Host').lists(1, 1, 3, 5)
        plan = solve(s.day())
        app, = plan.appearances
        self.assertTrue(app.is_host)
        self.assertEqual(['mic'], [a.kind for a in plan.actions])
        self.assertEqual('host', plan.actions[0].reason)
        self.assertTrue(plan.packs[0].host)

    def test_a_returner_gets_the_same_pack(self):
        s = (Show().line(1, '9:00').line(2).line(3, '10:00').line(4).line(5, '11:00').line(6)
             .segment(1, 2, 'A', '9:00', '10:00').segment(3, 4, 'B', '10:00', '11:00')
             .segment(5, 6, 'C', '11:00', '12:00')
             .person(1, 'Ana Bell').person(2, 'Cy Dunn').person(3, 'Eve Ford')
             .lists(1, 2, 6).lists(2, 2).lists(3, 4))
        plan = solve(s.day())
        self.assertEqual(1, len(rf(plan, 1)))
        self.assertEqual(['new pack', 'same pack'], [a.reason for a in mics(plan, 1)])

    def test_handhelds_are_their_own_pool_numbered_after_body_packs(self):
        s = (Show().line(1, '9:00').line(2).line(3, '10:30').line(4)
             .segment(1, 2, 'A', '9:00', '10:00').segment(3, 4, 'B', '10:30', '11:30')
             .person(1, 'Ana Bell', HH).person(2, 'Cy Dunn').person(3, 'Eve Ford')
             .lists(1, 2).lists(2, 2).lists(3, 4))
        plan = solve(s.day())
        self.assertEqual([BODY, HH], [p.pool for p in plan.packs])
        self.assertEqual({2}, rf(plan, 1))           # body RF 1, then the handheld
        self.assertEqual(rf(plan, 2), rf(plan, 3))   # Eve recycles Cy's body pack, not the HH

    def test_the_emergency_spare_is_never_assigned_and_counts_against_handhelds(self):
        plan = solve(panel_day(2, HH).day(), Settings(hh_count=2, emergency_spare_hh=True))
        spare = [p for p in plan.packs if p.spare]
        self.assertEqual(1, len(spare))
        self.assertEqual(spare[0].rf, max(p.rf for p in plan.packs))
        self.assertNotIn(spare[0].rf, {s.rf for s in plan.assignments})
        self.assertEqual(['shortage'], [f['kind'] for f in plan.flags])
        self.assertIn('need 1 more handheld than the 1 set', plan.flags[0]['text'])

    def test_a_shortage_is_one_flag_per_stretch_with_its_peak(self):
        plan = solve(panel_day(3).day(), Settings(body_pack_count=1))
        shortages = [f for f in plan.flags if f['kind'] == 'shortage']
        self.assertEqual(['Line 2: need 2 more body packs than the 1 set (3 in use from 9:00a).'],
                         [f['text'] for f in shortages])
        self.assertEqual(3, len(plan.packs))                 # the plan is still made

    def test_separate_stretches_over_the_limit_get_a_flag_each_at_their_line(self):
        s = (Show().line(1, '9:00').line(2).line(3, '10:00').line(4, '11:00').line(5).line(6, '12:00')
             .segment(1, 2, 'A', '9:00', '10:00').segment(3, 3, 'Gap', '10:00', '11:00')
             .segment(4, 5, 'B', '11:00', '12:00').segment(6, 6, 'End', '12:00', '12:30'))
        for k, line in ((1, 2), (2, 2), (3, 5), (4, 5), (5, 5)):
            s.person(k, 'Person {}'.format(k)).lists(k, line)
        plan = solve(s.day(), Settings(body_pack_count=1))
        texts = [f['text'] for f in plan.flags if f['kind'] == 'shortage']
        self.assertEqual(['Line 2: need 1 more body pack than the 1 set (2 in use from 9:00a).',
                          'Line 5: need 2 more body packs than the 1 set (3 in use from 11:00a).'], texts)

    def test_handheld_shortages_are_counted_the_same_way(self):
        plan = solve(panel_day(3, HH).day(), Settings(hh_count=2))
        self.assertEqual(['Line 2: need 1 more handheld than the 2 set (3 in use from 9:00a).'],
                         [f['text'] for f in plan.flags if f['kind'] == 'shortage'])

    def test_a_backup_reserves_its_own_pack_counted_and_mic_d_by_the_a2(self):
        s = panel_day(1)
        s.people[0] = Person(1, 'Person 1', BODY, HH)
        plan = solve(s.day())
        self.assertEqual(2, len(plan.packs))
        backup = [p for p in plan.packs if p.backup_of == 1]
        self.assertEqual(('HH', 'Person 1 backup'), (backup[0].pool, backup[0].label))
        acts = [(a.kind, a.backup) for a in plan.actions]
        self.assertEqual(2, acts.count(('mic', False)) + acts.count(('mic', True)))
        self.assertIn(('demic', True), acts)
        self.assertEqual({backup[0].rf}, rf(plan, 1, backup=True))
        self.assertEqual(1, solver.summary(plan)['backups'])
        self.assertEqual(1, solver.summary(plan)['hh'])

    def test_back_on_within_the_lead_keeps_the_pack_on(self):
        s = (Show().line(1, '9:00').line(2).line(3, '9:30').line(4).line(5, '9:40').line(6, '9:45')
             .segment(1, 2, 'A', '9:00', '9:30').segment(3, 4, 'B', '9:30', '9:40')
             .segment(5, 6, 'C', '9:40', '10:10')
             .person(1, 'Ana Bell').lists(1, 2, 6))
        plan = solve(s.day())
        self.assertEqual(2, len(plan.appearances))
        self.assertEqual(['mic', 'demic'], [a.kind for a in plan.actions])
        self.assertEqual(1, len(rf(plan, 1)))


class ScheduleTests(TestCase):

    def test_impossible_deadlines_are_flagged_late_and_the_solver_finishes(self):
        plan = solve(panel_day(6).day(), Settings(mic_min=10, premic_lead_min=0, margin_min=0))
        self.assertEqual(6, len(mics(plan)))
        self.assertTrue(any(f['kind'] == 'late' for f in plan.flags))
        self.assertTrue(any(a.late for a in plan.actions))

    def test_a_tight_mic_is_flagged(self):
        plan = solve(panel_day(1).day(), Settings(mic_min=3, premic_lead_min=6, margin_min=5))
        self.assertEqual(['tight'], [f['kind'] for f in plan.flags])

    def test_two_a2s_share_the_work_and_never_overlap(self):
        plan = solve(panel_day(8).day(), Settings(a2_count=2))
        self.assertEqual({1, 2}, {a.a2_index for a in plan.actions})
        for k in (1, 2):
            mine = sorted((a for a in plan.actions if a.a2_index == k), key=lambda a: a.start_min)
            for a, b in zip(mine, mine[1:]):
                self.assertLessEqual(a.end_min, b.start_min)
            self.assertEqual(list(range(1, len(mine) + 1)), [a.seq for a in mine])
        self.assertFalse(any(a.late for a in plan.actions))

    def test_one_a2_never_overlaps_either(self):
        plan = solve(panel_day(8).day())
        acts = sorted(plan.actions, key=lambda a: a.start_min)
        for a, b in zip(acts, acts[1:]):
            self.assertLessEqual(a.end_min, b.start_min)

    def test_mics_are_done_as_people_arrive_not_at_the_last_minute(self):
        plan = solve(panel_day(1).day())
        mic, = mics(plan)
        self.assertEqual(h('9:00') - 30, mic.start_min)     # released at on - lead, done then

    def test_a_de_mic_is_at_the_catch_when_the_a2_is_free(self):
        plan = solve(panel_day(1).day())
        demic = next(a for a in plan.actions if a.kind == 'demic')
        self.assertEqual(('when off', 0), (demic.reason, demic.wait_min))

    def test_busy_minutes_per_segment_per_a2(self):
        plan = solve(panel_day(2).day(), Settings(a2_count=2))
        opening, close = plan.busy[1], plan.busy[3]
        self.assertEqual([0.0, 0.0], opening)          # both mics are done before 9:00
        self.assertEqual([3.0, 3.0], close)            # one de-mic each at 9:30

    def test_overlapping_segments_never_count_a_minute_twice(self):
        # "Doors" 8:00-9:00 holds "Pre-Show" 8:30-9:00: a mic at 8:30 counts in Pre-Show only.
        s = (Show().line(1, '8:00').line(2, '8:30').line(3).line(4, '9:00').line(5)
             .segment(1, 1, 'Doors', '8:00', '9:00').segment(2, 3, 'Pre-Show', '8:30', '9:00')
             .segment(4, 5, 'Opening', '9:00', '9:30')
             .person(1, 'Ana Bell').lists(1, 5))
        plan = solve(s.day())
        inside = sum(max(0, min(a.end_min, h('9:30')) - max(a.start_min, h('8:00'))) for a in plan.actions)
        self.assertEqual(inside, sum(sum(m) for m in plan.busy.values()))
        self.assertEqual([0.0], plan.busy[1])
        self.assertEqual([3.0], plan.busy[2])

    def spill_day(self, off_together, due_in_next=False, transition='9:35'):
        # A: 9:00-9:30, everyone in it comes off at 9:30, into a short
        # transition T (9:30-``transition``), then C until 10:00.
        s = (Show().line(1, '9:00').line(2).line(3, '9:30').line(4, transition).line(5, '9:50')
             .line(6, '10:00')
             .segment(1, 2, 'A', '9:00', '9:30').segment(3, 3, 'T', '9:30', transition)
             .segment(4, 6, 'C', transition, '10:00'))
        for k in range(1, off_together + 1):
            s.person(k, 'Person {}'.format(k)).lists(k, 2)
        if due_in_next:
            s.person(99, 'Late Comer').lists(99, 5)
        return solve(s.day())

    def test_de_mics_running_past_a_short_segment_are_spill_on_its_meter_and_in_review(self):
        plan = self.spill_day(4)                          # 4 de-mics from 9:30: busy until 9:42
        self.assertEqual({'minutes': 7, 'into': 4}, plan.spill[3])
        self.assertEqual([5.0], plan.busy[3])             # the meter itself never passes 100 %
        flag, = [f for f in plan.flags if f['kind'] == 'spill']
        self.assertEqual('Line 3: the A2 is still busy 7 min after "T" ends at 9:35a, into "C".', flag['text'])
        self.assertNotIn('overload', {f['kind'] for f in plan.flags})

    def test_a_short_spill_stays_on_the_meter_unless_a_mic_is_due_next(self):
        plan = self.spill_day(2)                          # busy until 9:36: 1 min over
        self.assertEqual(1, plan.spill[3]['minutes'])
        self.assertFalse([f for f in plan.flags if f['kind'] == 'spill'])
        plan = self.spill_day(2, due_in_next=True)        # a mic is due in C at 9:45
        flag, = [f for f in plan.flags if f['kind'] == 'spill']
        self.assertIn('where a mic is due', flag['text'])

    def test_segments_shorter_than_a_mic_never_spill(self):
        plan = self.spill_day(4, transition='9:31')       # a 1-minute T
        self.assertNotIn(3, plan.spill)
        self.assertFalse([f for f in plan.flags if f['kind'] == 'spill'])

    def test_the_same_day_gives_the_same_plan_whatever_order_people_were_created_in(self):
        def signature(keys):
            s = panel_day(0)
            for key, name in zip(keys, ('Ana Bell', 'Cy Dunn', 'Eve Ford', 'Gus Hale')):
                s.person(key, name).lists(key, 2)
            plan = solve(s.day(), Settings(body_pack_count=2))
            names = {p.key: p.name for p in s.people}
            return ([(a.kind, a.start_min, names[a.person], a.rf_number) for a in plan.actions],
                    [f['text'] for f in plan.flags])
        self.assertEqual(signature([1, 2, 3, 4]), signature([4, 3, 2, 1]))

    def test_actions_read_the_same_everywhere(self):
        plan = solve(panel_day(1).day(), Settings(a2_count=2))
        f = format_action(plan.actions[0], 2)
        self.assertEqual(('8:30a', 'MIC', 'Person 1', 'RF 1', 'new pack', 'A2 1'),
                         (f['time'], f['verb'], f['name'], f['rf'], f['reason'], f['a2']))
        self.assertEqual('A2 1 8:30a MIC Person 1 RF 1 (new pack)', f['text'])


class FixtureStrategyTests(DbTestCase):
    """Mic'ing people as they arrive never needs more packs than the
    prototype's latest-safe mics, on the scrubbed cued and cue-free files."""

    def test_earliest_never_needs_more_packs_than_latest_safe(self):
        user = User.objects.create_user('fx', 'fx@example.com', 'pw', is_staff=True)
        for name in ('MAIN_PAGES', 'CLIENT_E_PAGES'):
            with self.subTest(name=name):
                project = Project.objects.create(name=name, owner=user)
                day = ShowDay.objects.create(project=project, date=date(2026, 4, 1))
                importer.confirm(importer.stage_upload(day, F.build_pdf(getattr(F, name)), 'x.pdf', user))
                data, _, _ = planning.build_day(day)
                early = solve(data, Settings(strategy='earliest'))
                late = solve(data, Settings(strategy='latest'))
                self.assertLessEqual(len(early.packs), len(late.packs))
                self.assertLessEqual(sum(a.start_min for a in mics(early)),
                                     sum(a.start_min for a in mics(late)))
                self.assertFalse(any(a.late for a in early.actions))


class StatTileTests(TestCase):

    def test_segments_shorter_than_a_mic_are_not_counted_as_busy(self):
        from types import SimpleNamespace
        from planner.mic_plan.page import stats
        plan = SimpleNamespace(settings={'mic_min': 3}, packs=[], swaps=0, segments=[
            {'t0': 600, 't1': 601, 'busy': [1.0]},        # 1-minute video: 100 %, left out
            {'t0': 601, 't1': 631, 'busy': [28.0]},       # 93 %
            {'t0': 631, 't1': 661, 'busy': [20.0]}])      # 67 %
        self.assertEqual(1, stats(plan)['hot'])
