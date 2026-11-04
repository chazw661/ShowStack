"""Mic Plan PR 5: Send to Mic Tracker. Sessions, RF rows and slots from the
stored plan; re-push in place; what is kept; started sessions; refusals;
access; fixed RF numbers (rf_from_plan). Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_push --settings=audiopatch.test_settings
"""

from datetime import date, time
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from planner.mic_plan import push
from planner.models import (
    MicAssignment, MicPlan, MicPlanAppearance, MicPlanAssignment, MicPlanPush, MicSession, Presenter, PresenterSlot,
    ShowDay, ShowflowPerson,
)
from planner.tests.test_mic_plan_edits import EditBase
from planner.tests.test_mic_plan_import import MicPlanBase


def seg(row, t0, t1, name, is_break=False):
    return {'row': row, 'part': 0, 'line': str(row), 'name': name, 't0': t0, 't1': t1, 'is_break': is_break,
            'busy': [], 'spill': 0, 'spill_into': ''}


# Two sessions: Opening 8:00–9:00, a break 9:00–9:15, Panel 9:15–10:00.
SEGMENTS = [seg(1, 480, 540, 'Opening Session'), seg(2, 540, 555, 'Break', is_break=True),
            seg(3, 555, 600, 'Panel')]


def mt_state(day):
    """Every Mic Tracker row of ``day``, pks and values: what "writes nothing" compares."""
    return (
        list(MicSession.objects.filter(day=day).order_by('pk').values_list(
            'pk', 'name', 'order', 'num_mics', 'start_time', 'end_time', 'rf_from_plan')),
        list(MicAssignment.objects.filter(session__day=day).order_by('pk').values_list(
            'pk', 'session_id', 'rf_number', 'notes', 'mic_type', 'is_micd')),
        list(PresenterSlot.objects.filter(assignment__session__day=day).order_by('pk').values_list(
            'pk', 'assignment_id', 'presenter_id', 'order', 'is_active', 'mic_type', 'notes', 'photo_data')),
        list(Presenter.objects.filter(project=day.project).order_by('pk').values_list('pk', 'name')),
    )


class PushBase(MicPlanBase):

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.n = 0

    def plan(self, people, packs=None, segments=SEGMENTS, flags=(), stale=False):
        """``people``: [(name, on, off, rf, kw)]; kw: hh, host (stage), backup
        (rf), person (ShowflowPerson). A stored plan, as planning._save writes one."""
        plan, _ = MicPlan.objects.update_or_create(day=self.day, defaults={
            'generated_at': timezone.now(), 'segments': segments, 'flags': list(flags), 'stale': stale,
            'settings': {'a2_count': 1}})
        plan.appearances.all().delete()
        plan.version += 1
        auto = {}
        for name, on, off, rf, kw in people:
            auto.setdefault(rf, 'HH' if kw.get('hh') else 'body')
            if kw.get('backup'):
                auto[kw['backup']] = 'HH'
        plan.packs = packs if packs is not None else [{'rf': rf, 'pool': pool, 'spare': False}
                                                      for rf, pool in sorted(auto.items())]
        plan.save()
        seen = {}
        for k, (name, on, off, rf, kw) in enumerate(people):
            n = seen[name] = seen.get(name, -1) + 1
            app = MicPlanAppearance.objects.create(
                plan=plan, key=k, person=kw.get('person'), person_name=name, on_min=on, off_min=off,
                mic_type='HH' if kw.get('hh') else 'body', is_host=bool(kw.get('host')),
                stage=[list(s) for s in kw.get('host') or ()], skey='{}|{}|{}'.format(name.lower(), on, n),
                source='host' if kw.get('host') else 'cue')
            MicPlanAssignment.objects.create(appearance=app, rf_number=rf, how='new')
            if kw.get('backup'):
                MicPlanAssignment.objects.create(appearance=app, rf_number=kw['backup'], how='backup', backup=True)
        return plan

    def url(self, day=None):
        return reverse('planner:mic_plan_push', args=[(day or self.day).pk])

    def send(self, keep=(), include_started=False, expect=302):
        p = push.preview(self.day)
        resp = self.client.post(self.url(), {'version': p.plan.version, 'digest': p.digest, 'keep': list(keep),
                                             **({'include_started': '1'} if include_started else {})})
        self.assertEqual(expect, resp.status_code)
        return p

    def sessions(self):
        return list(MicSession.objects.filter(day=self.day).order_by('order'))

    def table(self, session):
        """{rf: [(presenter name, order, mic_type, notes)]} and row notes."""
        out = {}
        for row in session.mic_assignments.order_by('rf_number'):
            out[row.rf_number] = [(s.presenter.name if s.presenter else None, s.order, s.mic_type, s.notes)
                                  for s in row.presenter_slots.order_by('order')]
        return out

    def row_notes(self, session):
        return {r.rf_number: r.notes for r in session.mic_assignments.all()}


class FirstPushTests(PushBase):

    def test_sessions_rows_and_slots_in_order_with_names(self):
        self.plan([('Avery Able', 490, 500, 1, {}), ('Blake Bond', 505, 520, 1, {}),
                   ('Casey Cole', 560, 580, 3, {'hh': True})])
        self.send()
        s1, s2 = self.sessions()
        self.assertEqual(['Opening Session (8:00–9:00)', 'Panel (9:15–10:00)'], [s1.name, s2.name])
        self.assertTrue(s1.rf_from_plan and s2.rf_from_plan)
        self.assertEqual((time(8, 0), time(9, 0)), (s1.start_time, s1.end_time))
        self.assertEqual({1: [('Avery Able', 0, '', ''), ('Blake Bond', 1, '', '')]}, self.table(s1))
        self.assertEqual({3: [('Casey Cole', 0, 'HH', '')]}, self.table(s2))
        self.assertEqual((1, 1), (s1.num_mics, s2.num_mics))
        first = s1.mic_assignments.get().presenter_slots.order_by('order')
        self.assertEqual([True, False], [s.is_active for s in first])

    def test_new_sessions_go_after_the_highest_order_even_after_a_delete(self):
        a = MicSession.objects.create(day=self.day, name='Hand made A', num_mics=2, order=0)
        MicSession.objects.create(day=self.day, name='Hand made B', num_mics=2, order=1)
        MicSession.objects.create(day=self.day, name='Hand made C', num_mics=2, order=2)
        a.delete()                       # two sessions left, highest order 2: count() would say 2
        self.plan([('Avery Able', 490, 500, 1, {}), ('Casey Cole', 560, 580, 2, {})])
        self.send()
        new = MicSession.objects.filter(day=self.day, rf_from_plan=True).order_by('order')
        self.assertEqual([3, 4], [s.order for s in new])

    def test_a_host_has_the_same_rf_only_in_sessions_they_are_on_stage(self):
        three = SEGMENTS + [seg(4, 600, 615, 'Lunch', is_break=True), seg(5, 615, 660, 'Closing')]
        self.plan([('Harper Host', 485, 655, 9, {'host': [(485, 490), (620, 655)]}),
                   ('Avery Able', 490, 500, 1, {}), ('Casey Cole', 560, 580, 2, {}),
                   ('Dana Dunn', 620, 640, 1, {})], segments=three)
        self.send()
        s1, s2, s3 = self.sessions()
        self.assertEqual([('Harper Host', 0, '', 'host')], self.table(s1)[9])
        self.assertNotIn(9, self.table(s2))
        self.assertEqual([('Harper Host', 0, '', 'host')], self.table(s3)[9])

    def test_a_host_newly_in_a_middle_session_never_takes_another_sessions_slot(self):
        three = SEGMENTS + [seg(4, 600, 615, 'Lunch', is_break=True), seg(5, 615, 660, 'Closing')]
        host = [('Avery Able', 490, 500, 1, {}), ('Casey Cole', 560, 580, 2, {}), ('Dana Dunn', 620, 640, 1, {})]
        self.plan([('Harper Host', 485, 655, 9, {'host': [(485, 490), (620, 655)]})] + host, segments=three)
        self.send()
        s1, s2, s3 = self.sessions()
        last = s3.mic_assignments.get(rf_number=9).presenter_slots.get()
        PresenterSlot.objects.filter(pk=last.pk).update(photo_data='data:image/png;base64,AAAA')
        # Now on stage in the Panel too.
        self.plan([('Harper Host', 485, 655, 9, {'host': [(485, 490), (570, 575), (620, 655)]})] + host,
                  segments=three)
        self.send()
        last.refresh_from_db()
        self.assertEqual(s3.pk, last.assignment.session_id)
        self.assertEqual([('Harper Host', 0, '', 'host')], self.table(s2)[9])

    def test_backup_row_and_spare_row(self):
        packs = [{'rf': 1, 'pool': 'body'}, {'rf': 2, 'pool': 'HH', 'backup_of': 1},
                 {'rf': 8, 'pool': 'HH', 'spare': True}]
        self.plan([('Avery Able', 490, 500, 1, {'backup': 2}), ('Casey Cole', 560, 580, 1, {})], packs=packs)
        self.send()
        s1, s2 = self.sessions()
        self.assertEqual({1: [('Avery Able', 0, '', '')], 2: [('Avery Able', 0, 'HH', 'backup for Avery Able')],
                          8: [(None, 0, 'HH', 'SPARE')]}, self.table(s1))
        self.assertEqual({1: [('Casey Cole', 0, '', '')], 8: [(None, 0, 'HH', 'SPARE')]},
                         self.table(s2))                                   # no backup where Avery is not on
        self.assertEqual({1: '', 2: '', 8: ''}, self.row_notes(s1))

    def test_new_presenters_created_listed_and_linked_back(self):
        person = ShowflowPerson.objects.create(day=self.day, display_name='Avery Able', name_key='avery able')
        self.plan([('Avery Able', 490, 500, 1, {'person': person})])
        p = push.preview(self.day)
        self.assertEqual(['Avery Able'], p.new_presenters)
        self.assertFalse(Presenter.objects.filter(project=self.project).exists())   # preview writes nothing
        self.send()
        made = Presenter.objects.get(project=self.project, name='Avery Able')
        person.refresh_from_db()
        self.assertEqual(made.pk, person.presenter_id)

    def test_linked_presenter_is_used_and_same_name_is_matched(self):
        linked = Presenter.objects.create(project=self.project, name='Stage Name A')
        same = Presenter.objects.create(project=self.project, name='blake BOND')
        a = ShowflowPerson.objects.create(day=self.day, display_name='Avery Able', name_key='avery able',
                                          presenter=linked)
        b = ShowflowPerson.objects.create(day=self.day, display_name='Blake Bond', name_key='blake bond')
        self.plan([('Avery Able', 490, 500, 1, {'person': a}), ('Blake Bond', 505, 520, 2, {'person': b})])
        p = push.preview(self.day)
        self.assertEqual([], p.new_presenters)
        self.assertEqual(['blake BOND'], p.matched_presenters)
        self.send()
        s1 = self.sessions()[0]
        self.assertEqual({1: [('Stage Name A', 0, '', '')], 2: [('blake BOND', 0, '', '')]}, self.table(s1))
        self.assertEqual(2, Presenter.objects.filter(project=self.project).count())
        linked.refresh_from_db()
        self.assertEqual('Stage Name A', linked.name)                       # never renamed

    def test_existing_session_matched_by_name_keeps_its_own_rows(self):
        hand = MicSession.objects.create(day=self.day, name='Opening Session (8:00–9:00)', num_mics=2, order=0)
        self.assertEqual([1, 2], sorted(hand.mic_assignments.values_list('rf_number', flat=True)))
        PresenterSlot.objects.create(assignment=hand.mic_assignments.get(rf_number=1), order=0, is_active=True)
        self.plan([('Avery Able', 490, 500, 1, {}), ('Blake Bond', 495, 520, 5, {})])
        self.send()
        hand.refresh_from_db()
        self.assertEqual(1, MicSession.objects.filter(day=self.day, name=hand.name).count())
        t = self.table(hand)
        self.assertEqual([('Avery Able', 0, '', '')], t[1])                 # the empty slot was filled
        self.assertEqual([], t[2])                                         # not the plan's: left alone
        self.assertEqual([('Blake Bond', 0, '', '')], t[5])
        self.assertTrue(hand.rf_from_plan)
        self.assertEqual(3, hand.num_mics)


class RePushTests(PushBase):

    def setUp(self):
        super().setUp()
        self.plan([('Avery Able', 490, 500, 1, {}), ('Blake Bond', 505, 520, 2, {}),
                   ('Casey Cole', 560, 580, 3, {})])
        self.send()
        self.s1, self.s2 = self.sessions()
        self.slot = {s.presenter.name: s for s in PresenterSlot.objects.filter(assignment__session__day=self.day)}

    def test_re_push_updates_in_place_and_keeps_a2_data(self):
        avery = self.slot['Avery Able']
        avery.photo_data = 'data:image/png;base64,AAAA'
        avery.notes = 'left ear, tape'
        avery.placement = 'LEFT_EAR'
        avery.save()
        # The plan moves Avery from RF 1 to RF 4.
        self.plan([('Avery Able', 490, 500, 4, {}), ('Blake Bond', 505, 520, 2, {}),
                   ('Casey Cole', 560, 580, 3, {})])
        p = push.preview(self.day)
        self.assertEqual(['slot_update'], [i['kind'] for i in p.group('update') if i['kind'] == 'slot_update'])
        self.send()
        avery.refresh_from_db()
        self.assertEqual(4, avery.assignment.rf_number)
        self.assertEqual(('data:image/png;base64,AAAA', 'left ear, tape', 'LEFT_EAR'),
                         (avery.photo_data, avery.notes, avery.placement))
        self.assertEqual({p.pk for p in self.slot.values()},
                         set(PresenterSlot.objects.filter(assignment__session__day=self.day).values_list('pk', flat=True)))
        self.assertEqual([2, 4], sorted(self.s1.mic_assignments.values_list('rf_number', flat=True)))  # RF 1 removed

    def test_nothing_to_send_when_mic_tracker_matches(self):
        p = push.preview(self.day)
        self.assertEqual([], p.changes)

    def test_a_second_push_with_nothing_changed_writes_nothing(self):
        before = mt_state(self.day)
        pushes = MicPlanPush.objects.count()
        p = push.preview(self.day)
        self.assertEqual([], p.changes)
        self.assertEqual(([], []), (p.labels, p.new_presenters))
        resp = self.client.get(self.url())
        self.assertContains(resp, 'already matches plan v{}'.format(p.plan.version))
        self.send()
        self.assertEqual(before, mt_state(self.day))
        self.assertEqual(pushes, MicPlanPush.objects.count())        # not even a push record

    def test_a_push_that_changes_one_slot_still_maps_every_slot(self):
        other = Presenter.objects.create(project=self.project, name='Someone Else')
        PresenterSlot.objects.filter(pk=self.slot['Blake Bond'].pk).update(presenter=other)
        self.send()
        self.assertEqual({s.pk for s in self.slot.values()}, set(push.last_push(self.day).slots.values()))
        self.assertEqual([], push.preview(self.day).changes)
        self.send()
        self.assertEqual(3, PresenterSlot.objects.filter(assignment__session__day=self.day).count())

    def test_edited_in_mic_tracker_is_replaced_by_default(self):
        other = Presenter.objects.create(project=self.project, name='Someone Else')
        PresenterSlot.objects.filter(pk=self.slot['Blake Bond'].pk).update(presenter=other)
        p = push.preview(self.day)
        self.assertEqual(['keep_slot_{}'.format(self.slot['Blake Bond'].pk)], [i['id'] for i in p.group('mt')])
        self.send()
        self.assertEqual('Blake Bond', PresenterSlot.objects.get(pk=self.slot['Blake Bond'].pk).presenter.name)

    def test_edited_in_mic_tracker_is_kept_when_toggled_and_asked_again_next_time(self):
        other = Presenter.objects.create(project=self.project, name='Someone Else')
        pk = self.slot['Blake Bond'].pk
        PresenterSlot.objects.filter(pk=pk).update(presenter=other)
        self.send(keep=['keep_slot_{}'.format(pk)])
        self.assertEqual('Someone Else', PresenterSlot.objects.get(pk=pk).presenter.name)
        self.assertEqual(['keep_slot_{}'.format(pk)], [i['id'] for i in push.preview(self.day).group('mt')])

    def test_kept_presenter_is_asked_again_even_when_the_plans_is_new(self):
        pk = self.slot['Blake Bond'].pk
        # Nobody is called Blake Bond any more, so the plan would make them anew.
        Presenter.objects.filter(pk=self.slot['Blake Bond'].presenter_id).update(name='Blake B.')
        other = Presenter.objects.create(project=self.project, name='Someone Else')
        PresenterSlot.objects.filter(pk=pk).update(presenter=other)
        self.send(keep=['keep_slot_{}'.format(pk)])
        self.assertEqual('Someone Else', PresenterSlot.objects.get(pk=pk).presenter.name)
        self.assertEqual(['keep_slot_{}'.format(pk)], [i['id'] for i in push.preview(self.day).group('mt')])

    def test_a2_mic_type_is_never_overwritten(self):
        PresenterSlot.objects.filter(pk=self.slot['Avery Able'].pk).update(mic_type='LAV')
        self.assertEqual([], push.preview(self.day).changes)

    def test_removal_keeps_slots_with_a2_data(self):
        PresenterSlot.objects.filter(pk=self.slot['Avery Able'].pk).update(notes='spare battery in pouch')
        self.plan([('Casey Cole', 560, 580, 3, {})])            # Avery and Blake gone, so is session 1
        p = push.preview(self.day)
        self.assertIn('Avery Able kept', ' '.join(i['text'] for i in p.group('kept')))
        self.send()
        self.assertTrue(PresenterSlot.objects.filter(pk=self.slot['Avery Able'].pk).exists())
        self.assertFalse(PresenterSlot.objects.filter(pk=self.slot['Blake Bond'].pk).exists())
        self.assertTrue(MicSession.objects.filter(pk=self.s1.pk).exists())     # it still holds Avery
        self.assertEqual([1], list(self.s1.mic_assignments.values_list('rf_number', flat=True)))

    def test_a_session_left_empty_is_removed(self):
        self.plan([('Casey Cole', 560, 580, 3, {})])
        self.send()
        self.assertFalse(MicSession.objects.filter(pk=self.s1.pk).exists())

    def test_started_session_is_skipped_unless_ticked(self):
        PresenterSlot.objects.filter(pk=self.slot['Avery Able'].pk).update(is_micd=True)
        self.plan([('Avery Able', 490, 500, 1, {}), ('Blake Bond', 505, 520, 6, {}),
                   ('Casey Cole', 560, 580, 7, {})])
        p = push.preview(self.day)
        self.assertEqual([self.s1.pk], [s['pk'] for s in p.started])
        self.send()
        self.assertEqual([1, 2], sorted(self.s1.mic_assignments.values_list('rf_number', flat=True)))
        self.assertEqual([7], list(self.s2.mic_assignments.values_list('rf_number', flat=True)))
        last = push.last_push(self.day)
        self.assertEqual([self.s1.name], last.summary['skipped'])
        self.assertIn(str(self.slot['Blake Bond'].pk), last.slot_snapshot)    # still known next time
        self.send(include_started=True)
        self.assertEqual([1, 6], sorted(self.s1.mic_assignments.values_list('rf_number', flat=True)))

    def test_labels_list_every_rf_whose_presenter_changes(self):
        self.plan([('Avery Able', 490, 500, 1, {}), ('Dana Dunn', 505, 520, 2, {}),
                   ('Casey Cole', 560, 580, 3, {})])
        self.assertEqual(['RF 2 (Opening Session (8:00–9:00))'], push.preview(self.day).labels)

    def test_before_snapshot_records_changed_rows(self):
        old_row = self.slot['Avery Able'].assignment_id
        self.plan([('Avery Able', 490, 500, 4, {}), ('Blake Bond', 505, 520, 2, {}),
                   ('Casey Cole', 560, 580, 3, {})])
        self.send()
        before = push.last_push(self.day).before
        self.assertIn(['presenterslot', self.slot['Avery Able'].pk, {'assignment_id': old_row}], before['updated'])
        self.assertIn(old_row, [d[1] for d in before['deleted'] if d[0] == 'micassignment'])
        self.assertTrue(any(c[0] == 'micassignment' for c in before['created']))


class RefusalAndAccessTests(PushBase):

    def test_stale_plan_is_refused(self):
        self.plan([('Avery Able', 490, 500, 1, {})], stale=True)
        resp = self.client.get(self.url())
        self.assertEqual(302, resp.status_code)
        with self.assertRaises(push.PushRefused):
            push.preview(self.day)
        self.assertFalse(MicSession.objects.filter(day=self.day).exists())

    def test_a_host_without_stage_times_is_refused(self):
        plan = self.plan([('Harper Host', 485, 655, 9, {'host': [(485, 490)]})])
        plan.appearances.update(stage=[])                 # as stored before PR 5
        with self.assertRaisesMessage(push.PushRefused, 'Re-generate'):
            push.preview(self.day)

    def test_conflict_plan_is_refused(self):
        self.plan([('Avery Able', 490, 500, 1, {})], flags=[{'kind': 'conflict', 'text': 'x', 'row': None}])
        with self.assertRaisesMessage(push.PushRefused, 'RF conflict'):
            push.preview(self.day)

    def test_a_preview_that_no_longer_matches_is_refused(self):
        self.plan([('Avery Able', 490, 500, 1, {})])
        p = push.preview(self.day)
        MicSession.objects.create(day=self.day, name='Opening Session (8:00–9:00)', num_mics=1)
        resp = self.client.post(self.url(), {'version': p.plan.version, 'digest': p.digest})
        self.assertRedirects(resp, self.url(), fetch_redirect_response=False)
        self.assertFalse(MicPlanPush.objects.exists())

    def test_viewer_403_and_other_project_404(self):
        self.plan([('Avery Able', 490, 500, 1, {})])
        self.use(self.viewer)
        self.assertEqual(403, self.client.get(self.url()).status_code)
        self.assertEqual(403, self.client.post(self.url(), {'version': 1, 'digest': 'x'}).status_code)
        self.use(self.editor)
        self.assertEqual(404, self.client.get(self.url(self.other_day)).status_code)
        self.assertFalse(MicSession.objects.exists())

    def test_an_error_rolls_everything_back(self):
        self.plan([('Avery Able', 490, 500, 1, {}), ('Casey Cole', 560, 580, 3, {})])
        p = push.preview(self.day)
        with mock.patch.object(push, '_record', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                push.apply(self.day, p.plan.version, p.digest, user=self.editor)
        self.assertFalse(MicSession.objects.filter(day=self.day).exists())
        self.assertFalse(PresenterSlot.objects.exists())
        self.assertFalse(Presenter.objects.filter(project=self.project).exists())


class FixedNumberTests(PushBase):
    """#171: a pushed session's RFs are the plan's packs and stay put."""

    def setUp(self):
        super().setUp()
        self.plan([('Avery Able', 490, 500, 3, {}), ('Blake Bond', 495, 520, 7, {}),
                   ('Dana Dunn', 500, 530, 21, {})])
        self.send()
        self.s1 = self.sessions()[0]

    def rfs(self):
        return sorted(self.s1.mic_assignments.values_list('rf_number', flat=True))

    def test_deleting_a_row_does_not_renumber(self):
        self.s1.mic_assignments.get(rf_number=7).delete()
        self.assertEqual([3, 21], self.rfs())

    def test_num_mics_change_adds_above_and_never_deletes(self):
        self.s1.refresh_from_db()
        self.s1.num_mics = 4
        self.s1.save()
        self.s1.create_mic_assignments()
        self.assertEqual([3, 7, 21, 22], self.rfs())
        self.s1.num_mics = 1
        self.s1.save()
        self.s1.create_mic_assignments()
        self.assertEqual([3, 7, 21, 22], self.rfs())

    def test_renumber_command_skips_it(self):
        from django.core.management import call_command
        call_command('renumber_mic_assignments', '--apply', stdout=open('/dev/null', 'w'))
        self.assertEqual([3, 7, 21], self.rfs())

    def test_hand_made_sessions_still_renumber(self):
        hand = MicSession.objects.create(day=self.day, name='Hand made', num_mics=3)
        hand.mic_assignments.get(rf_number=2).delete()
        self.assertEqual([1, 2], sorted(hand.mic_assignments.values_list('rf_number', flat=True)))


class EndToEndTests(EditBase):
    """The real fixture: generate, preview, send, and the Mic Plan header."""

    def push_now(self):
        p = push.preview(self.day)
        resp = self.client.post(reverse('planner:mic_plan_push', args=[self.day.pk]),
                                {'version': p.plan.version, 'digest': p.digest})
        self.assertEqual(302, resp.status_code)
        return p

    def test_regenerate_keeping_changes_then_push_writes_only_real_differences(self):
        self.push_now()
        before = mt_state(self.day)
        v = self.plan().version
        self.generate('keep')
        self.assertEqual(v + 1, self.plan().version)
        # Same showflow, same settings: nothing in Mic Tracker changes...
        self.assertEqual([], push.preview(self.day).changes)
        self.push_now()
        self.assertEqual(before, mt_state(self.day))
        # ...but the push is recorded, so the header no longer says "changed since".
        self.assertEqual(v + 1, push.last_push(self.day).plan_version)
        page = self.client.get(reverse('planner:mic_plan') + '?day={}'.format(self.day.pk))
        self.assertFalse(page.context['push_behind'])

        # One real move: only Kim's slot changes (and the rows it leaves and lands on).
        key = self.key('Kim Keynote')
        kim = PresenterSlot.objects.get(assignment__session__day=self.day, presenter__name='Kim Keynote')
        self.assertEqual(200, self.edit('move_rf', key, rf=7, pool='body').status_code)
        p = push.preview(self.day)
        slot_items = [i for i in p.changes if i['kind'].startswith('slot_')]
        self.assertEqual([('slot_update', kim.pk)], [(i['kind'], i['data'].get('pk')) for i in slot_items])
        self.assertEqual({'row'}, set(slot_items[0]['data']['set']))
        self.assertTrue({i['kind'] for i in p.changes} <= {'slot_update', 'row_create', 'row_remove'})
        self.push_now()
        kim.refresh_from_db()
        self.assertEqual(7, kim.assignment.rf_number)
        after = mt_state(self.day)
        self.assertEqual({s[0] for s in before[2]}, {s[0] for s in after[2]})     # same slot pks
        changed = {s[0] for s in after[2]} - {s[0] for s in after[2] if s in before[2]}
        self.assertEqual({kim.pk}, changed)

    def test_generate_preview_send_and_header(self):
        plan = self.plan()
        resp = self.client.get(reverse('planner:mic_plan_push', args=[self.day.pk]))
        self.assertEqual(200, resp.status_code)
        p = resp.context['preview']
        self.assertTrue(p.targets)
        self.assertFalse(MicSession.objects.filter(day=self.day).exists())
        resp = self.client.post(reverse('planner:mic_plan_push', args=[self.day.pk]),
                                {'version': plan.version, 'digest': p.digest})
        self.assertEqual(302, resp.status_code)
        sessions = MicSession.objects.filter(day=self.day).order_by('order')
        self.assertEqual([t['name'] for t in p.targets], [s.name for s in sessions])
        main = {(a.person_name, s.rf_number) for a in plan.appearances.prefetch_related('assignments')
                for s in a.assignments.all() if not s.backup}
        pushed = {(s.presenter.name, s.assignment.rf_number)
                  for s in PresenterSlot.objects.filter(assignment__session__day=self.day, presenter__isnull=False)}
        self.assertTrue({n for n, _ in main} <= {n for n, _ in pushed})
        page = self.client.get(reverse('planner:mic_plan') + '?day={}'.format(self.day.pk))
        self.assertContains(page, 'Sent to Mic Tracker: v{}'.format(plan.version))
        self.assertEqual([], push.preview(self.day).changes)
        # The Mic Tracker page renders the pushed sessions.
        self.assertEqual(200, self.client.get(reverse('planner:mic_tracker')).status_code)
