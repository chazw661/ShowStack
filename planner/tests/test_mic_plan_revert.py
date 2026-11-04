"""Revert last push (mic_plan/revert.py), and pushed session names with a
plain hyphen. Made-up names.

Run with::

    python manage.py test planner.tests.test_mic_plan_revert --settings=audiopatch.test_settings
"""

from django.urls import reverse

from planner.mic_plan import mt_rows, push, revert
from planner.models import MicAssignment, MicPlanPush, MicSession, Presenter, PresenterSlot, ShowflowPerson
from planner.tests.test_mic_plan_edits import EditBase
from planner.tests.test_mic_plan_push import PushBase

PHOTO = 'data:image/png;base64,AAAA'


def everything(day):
    """Every column of every Mic Tracker row of ``day``, by pk, plus the
    project's presenters and the day's People links: what "exactly as it
    was" compares."""
    sessions = MicSession.objects.filter(day=day)
    return {
        'micsession': {s.pk: mt_rows.full(s) for s in sessions},
        'micassignment': {r.pk: mt_rows.full(r) for r in MicAssignment.objects.filter(session__day=day)},
        'presenterslot': {s.pk: mt_rows.full(s) for s in PresenterSlot.objects.filter(assignment__session__day=day)},
        'presenter': dict(Presenter.objects.filter(project=day.project).values_list('pk', 'name')),
        'people': dict(ShowflowPerson.objects.filter(day=day).values_list('pk', 'presenter_id')),
    }


class RevertBase(PushBase):

    def revert_url(self):
        return reverse('planner:mic_plan_revert', args=[self.day.pk])

    def do_revert(self, anyway=False, expect=302):
        p = revert.preview(self.day)
        resp = self.client.post(self.revert_url(), {'push': p.push.pk, 'digest': p.digest,
                                                    **({'anyway': '1'} if anyway else {})})
        self.assertEqual(expect, resp.status_code)
        return p, resp


class RevertRestoresExactlyTests(RevertBase):

    def setUp(self):
        super().setUp()
        # A hand-made session the first push matches by name (en dash, other
        # case: pushes before #174 wrote one), with an A2's slot in it.
        self.hand = MicSession.objects.create(day=self.day, name='opening session (8:00 – 9:00)', num_mics=2, order=0)
        self.hand_slot = PresenterSlot.objects.create(
            assignment=self.hand.mic_assignments.get(rf_number=2), order=0, is_active=True, notes='A2 note',
            presenter=Presenter.resolve('Pat Prior', self.project.pk))
        self.other = MicSession.objects.create(day=self.day, name='Hand made, untouched', num_mics=3, order=1)
        self.person = ShowflowPerson.objects.create(day=self.day, display_name='Avery Able', name_key='avery able')
        self.initial = everything(self.day)

    def first(self):
        self.plan([('Avery Able', 490, 500, 1, {'person': self.person}), ('Blake Bond', 505, 520, 3, {}),
                   ('Casey Cole', 560, 580, 3, {'hh': True})])
        self.send()

    def test_reverting_the_first_push_restores_mic_tracker_exactly(self):
        self.first()
        hand = MicSession.objects.get(pk=self.hand.pk)
        self.assertEqual('Opening Session (8:00-9:00)', hand.name)       # renamed, flagged, a row added
        self.assertTrue(hand.rf_from_plan)
        self.assertTrue(MicSession.objects.filter(day=self.day, name='Panel (9:15-10:00)').exists())
        self.assertIsNotNone(ShowflowPerson.objects.get(pk=self.person.pk).presenter_id)

        p, _ = self.do_revert()
        self.assertEqual([], p.changed)
        self.assertEqual(self.initial, everything(self.day))
        self.assertIsNone(push.last_push(self.day))
        self.assertIn('reverted', MicPlanPush.objects.get().summary)

    def test_reverting_a_re_push_restores_the_first_push_exactly(self):
        self.first()
        avery = PresenterSlot.objects.get(assignment__session__day=self.day, presenter__name='Avery Able')
        PresenterSlot.objects.filter(pk=avery.pk).update(photo_data=PHOTO, placement='LEFT_EAR')
        after_first = everything(self.day)
        # Avery moves RF 1 -> 4 (the slot moves, photo with it), Blake goes, Dana is new.
        self.plan([('Avery Able', 490, 500, 4, {'person': self.person}), ('Casey Cole', 560, 580, 3, {'hh': True}),
                   ('Dana Dunn', 565, 575, 5, {})])
        self.send()
        moved = PresenterSlot.objects.get(pk=avery.pk)
        self.assertEqual(4, moved.assignment.rf_number)
        self.assertFalse(PresenterSlot.objects.filter(presenter__name='Blake Bond').exists())

        # The photo was put on after the first push, so this push left it; no Mic Tracker change since.
        p, _ = self.do_revert()
        self.assertEqual([], p.changed)
        self.assertEqual(after_first, everything(self.day))              # pks, values, the photo, Blake's slot
        self.assertFalse(Presenter.objects.filter(project=self.project, name='Dana Dunn').exists())
        # The first push is the last one again, and Send matches through it.
        self.assertEqual(MicPlanPush.objects.order_by('pk').first(), push.last_push(self.day))
        # Reverting that one too: the photo and placement went on after it, so
        # they are a Mic Tracker change, listed, and need "Revert anyway".
        p = revert.preview(self.day)
        self.assertEqual(['RF 1 · Opening Session (8:00-9:00) · Avery Able: placement, photo changed'], p.changed)
        self.assertEqual(['RF 1 · Opening Session (8:00-9:00) · Avery Able: photo will be deleted'], p.a2)
        self.do_revert()
        self.assertEqual(after_first, everything(self.day))              # refused
        self.do_revert(anyway=True)
        self.assertEqual(self.initial, everything(self.day))


class RevertRefusalTests(RevertBase):

    def setUp(self):
        super().setUp()
        self.plan([('Avery Able', 490, 500, 1, {}), ('Blake Bond', 505, 520, 2, {})])
        self.send()
        self.session = MicSession.objects.get(day=self.day)
        self.slot = {s.presenter.name: s for s in PresenterSlot.objects.filter(assignment__session__day=self.day)}

    def test_a_mic_tracker_edit_since_the_push_is_refused_unless_ticked(self):
        PresenterSlot.objects.filter(pk=self.slot['Blake Bond'].pk).update(
            presenter=Presenter.resolve('Sam Standin', self.project.pk))
        MicAssignment.objects.filter(session=self.session, rf_number=1).update(input_channel=12)
        p = revert.preview(self.day)
        text = ' '.join(p.changed)
        self.assertIn('RF 2 · Opening Session (8:00-9:00) · Sam Standin: presenter changed', text)
        self.assertIn('RF 1 · Opening Session (8:00-9:00): input channel changed', text)
        page = self.client.get(self.revert_url())
        self.assertContains(page, 'Revert anyway')
        self.assertContains(page, 'presenter changed')

        before = everything(self.day)
        _, resp = self.do_revert()
        self.assertRedirects(resp, self.revert_url(), fetch_redirect_response=False)
        self.assertEqual(before, everything(self.day))                    # nothing written
        self.assertIsNotNone(push.last_push(self.day))

        self.do_revert(anyway=True)
        self.assertFalse(MicSession.objects.filter(day=self.day).exists())
        self.assertTrue(MicPlanPush.objects.get().summary['reverted']['anyway'])

    def test_a2_data_on_what_the_push_created_is_listed_never_deleted_silently(self):
        PresenterSlot.objects.filter(pk=self.slot['Avery Able'].pk).update(photo_data=PHOTO)
        PresenterSlot.objects.filter(pk=self.slot['Blake Bond'].pk).update(is_micd=True)
        added = PresenterSlot.objects.create(assignment=self.slot['Avery Able'].assignment, order=1, notes='swap at 9')
        p = revert.preview(self.day)
        a2 = ' | '.join(p.a2)
        self.assertIn('RF 1 · Opening Session (8:00-9:00) · Avery Able: photo will be deleted', a2)
        self.assertIn("Blake Bond: MIC'D will be deleted", a2)
        self.assertIn('no presenter: notes will be deleted', a2)
        self.assertTrue(p.changed)                                       # so it needs "Revert anyway" too
        page = self.client.get(self.revert_url())
        self.assertContains(page, 'A2 data that will be deleted')
        self.do_revert()                                                 # refused
        self.assertTrue(PresenterSlot.objects.filter(pk=added.pk).exists())
        self.do_revert(anyway=True)
        self.assertFalse(PresenterSlot.objects.filter(pk__in=[added.pk, self.slot['Avery Able'].pk]).exists())

    def test_push_notes_are_not_a2_notes(self):
        self.plan([('Harper Host', 485, 520, 9, {'host': [(485, 490)]}), ('Avery Able', 490, 500, 1, {})])
        self.send()
        self.assertEqual([], revert.preview(self.day).a2)

    def test_a_preview_that_no_longer_matches_is_refused(self):
        p = revert.preview(self.day)
        MicAssignment.objects.filter(session=self.session, rf_number=1).update(notes='changed')
        resp = self.client.post(self.revert_url(), {'push': p.push.pk, 'digest': p.digest, 'anyway': '1'})
        self.assertRedirects(resp, self.revert_url(), fetch_redirect_response=False)
        self.assertTrue(MicSession.objects.filter(pk=self.session.pk).exists())

    def test_an_older_push_without_after_data_needs_revert_anyway(self):
        last = push.last_push(self.day)
        b = dict(last.before)
        b.pop('after')
        b.pop('scope')
        MicPlanPush.objects.filter(pk=last.pk).update(before=b)
        p = revert.preview(self.day)
        self.assertEqual([revert.LEGACY], p.changed)
        self.do_revert()
        self.assertTrue(MicSession.objects.filter(pk=self.session.pk).exists())
        self.do_revert(anyway=True)
        self.assertFalse(MicSession.objects.filter(pk=self.session.pk).exists())

    def test_nothing_to_revert(self):
        self.do_revert(anyway=True)
        resp = self.client.get(self.revert_url())
        self.assertRedirects(resp, reverse('planner:mic_plan') + '?day={}'.format(self.day.pk),
                             fetch_redirect_response=False)

    def test_viewer_403_and_other_project_404(self):
        self.use(self.viewer)
        self.assertEqual(403, self.client.get(self.revert_url()).status_code)
        p = revert.preview(self.day)
        self.assertEqual(403, self.client.post(self.revert_url(), {'push': p.push.pk, 'digest': p.digest}).status_code)
        self.assertTrue(MicSession.objects.filter(pk=self.session.pk).exists())
        self.use(self.other_owner, self.other)
        self.assertEqual(404, self.client.get(self.revert_url()).status_code)
        self.assertEqual(404, self.client.post(self.revert_url(), {'push': p.push.pk, 'digest': p.digest}).status_code)


class RevertHeaderTests(EditBase):
    """The real fixture: generate, send, revert, and the Mic Plan header."""

    def test_header_after_revert(self):
        p = push.preview(self.day)
        self.client.post(reverse('planner:mic_plan_push', args=[self.day.pk]),
                         {'version': p.plan.version, 'digest': p.digest})
        url = reverse('planner:mic_plan') + '?day={}'.format(self.day.pk)
        revert_url = reverse('planner:mic_plan_revert', args=[self.day.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Sent to Mic Tracker: v')
        self.assertContains(page, revert_url)
        r = revert.preview(self.day)
        self.assertEqual([], r.changed)
        self.client.post(revert_url, {'push': r.push.pk, 'digest': r.digest})
        self.assertFalse(MicSession.objects.filter(day=self.day).exists())
        page = self.client.get(url)
        self.assertNotContains(page, 'Sent to Mic Tracker: v')
        self.assertNotContains(page, revert_url)
        self.assertContains(page, 'was reverted by mp_editor')
        self.assertIsNone(push.preview(self.day).last)                 # the next push is a first push again


class HyphenNameTests(PushBase):

    def test_sessions_pushed_with_an_en_dash_are_renamed_on_the_next_push(self):
        self.plan([('Avery Able', 490, 500, 1, {})])
        self.send()
        s = MicSession.objects.get(day=self.day)
        self.assertEqual('Opening Session (8:00-9:00)', s.name)
        # As a push before this change left it.
        old = 'Opening Session (8:00–9:00)'
        MicSession.objects.filter(pk=s.pk).update(name=old)
        last = push.last_push(self.day)
        last.session_snapshot[str(s.pk)]['name'] = old
        last.save()
        p = push.preview(self.day)
        self.assertEqual(['session_update'], [i['kind'] for i in p.changes])
        self.send()
        s.refresh_from_db()
        self.assertEqual('Opening Session (8:00-9:00)', s.name)
