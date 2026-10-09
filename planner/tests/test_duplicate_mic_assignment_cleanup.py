"""The report and cleanup commands for the duplicated MicAssignment rows.

``Project.duplicate()`` no longer writes duplicate assignments (that fix and
its tests are in ``test_duplicate_child_rows.py``), but every project
duplicated before it still holds them — an 8-mic session as 16 rows with every
``rf_number`` twice, only half of them holding a ``PresenterSlot``.

Two things here matter more than the plumbing:

  * **The keep-rule.** The blank scaffold row is written *first* and so has the
    **lower** id. "Keep the oldest" would keep the blank and delete the
    engineer's work, so the keeper is chosen from row contents.

  * **The protection veto.** A ``MicAssignment`` is a parent row: its
    presenters and half its notes live in ``PresenterSlot`` children, and
    deleting the parent cascades to them. A row holding the group's only
    presenter, only note or only mic'd flag is never deleted, whatever the
    field-level verdict says. ``ProtectionVetoTests`` builds the cases where
    the verdict and the veto disagree and pins that the veto wins.

``NumberingIsNotTouchedTests`` covers the subtler hazard: the issue #36
``post_delete`` receiver renumbers a session's surviving rf_numbers after any
assignment delete, which on a session with a *skipped* group would pull that
pair apart and leave the session looking clean while two rows still mean the
same mic. The cleanup suspends that receiver; these tests prove it.

Run with::

    python manage.py test planner.tests.test_duplicate_mic_assignment_cleanup \\
        --settings=audiopatch.test_settings
"""
from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from planner.models import (
    MicAssignment, MicGroup, MicSession, Presenter, PresenterSlot, Project,
    ShowDay,
)
from planner.utils.dupe_verdicts import decide, losses_from_keeping
from planner.utils.mic_assignment_dupes import (
    CONFLICTING, IDENTICAL, ONE_SIDED, PROTECTIONS,
    decide_group, describe, duplicate_groups, has_micd_state, has_notes,
    has_presenter, is_blank, judge, numbering_held, payload_of,
)


class _SessionMixin:
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='mic_dupes', email='m@example.com', password='x')
        self.project = Project.objects.create(name='Duplicated Show',
                                              owner=self.user)
        self.day = ShowDay.objects.create(project=self.project,
                                          date=date(2026, 10, 8),
                                          name='Day 1', order=0)
        self.presenter = Presenter.objects.create(project=self.project,
                                                  name='Jane Doe')

    def blank_session(self, num_mics=4, name='General Session'):
        """A session as MicSession.save() leaves it: num_mics blank rows."""
        return MicSession.objects.create(day=self.day, name=name,
                                         num_mics=num_mics, order=0)

    def patched_session(self, num_mics=4, name='General Session'):
        """A session as duplicate() now leaves it: num_mics patched rows."""
        session = self.blank_session(num_mics=num_mics, name=name)
        for assignment in session.mic_assignments.order_by('rf_number'):
            self.patch(assignment)
        return session

    def patch(self, assignment, presenter=True):
        """Give one assignment a recognisable payload plus a presenter slot."""
        n = assignment.rf_number
        assignment.mic_type = 'handheld'
        assignment.is_micd = True
        assignment.placement = ''
        assignment.notes = 'RF %d' % n
        assignment.save()
        PresenterSlot.objects.create(
            assignment=assignment,
            presenter=self.presenter if presenter else None,
            order=0, is_active=True, notes='slot %d' % n)
        return assignment

    def doubled_session(self, num_mics=4, name='General Session'):
        """A session as the *old* duplicate() left it: num_mics blank scaffold
        rows written first (lower ids), then the patched copies on top."""
        session = self.blank_session(num_mics=num_mics, name=name)
        for n in range(1, num_mics + 1):
            copied = MicAssignment.objects.create(session=session, rf_number=n)
            self.patch(copied)
        return session

    def report(self, **kwargs):
        out = StringIO()
        call_command('report_duplicate_mic_assignments', stdout=out,
                     no_color=True, **kwargs)
        return out.getvalue()

    def cleanup(self, **kwargs):
        out = StringIO()
        call_command('cleanup_duplicate_mic_assignments', stdout=out,
                     no_color=True, **kwargs)
        return out.getvalue()

    def rows(self, session, rf_number):
        return list(session.mic_assignments.filter(rf_number=rf_number)
                    .order_by('id'))


class VerdictTests(_SessionMixin, TestCase):
    """The content classification, before any protection is considered."""

    def test_a_scaffold_row_is_blank(self):
        session = self.blank_session()
        for assignment in session.mic_assignments.all():
            self.assertTrue(is_blank(assignment))

    def test_a_patched_row_is_not_blank(self):
        session = self.patched_session()
        for assignment in session.mic_assignments.all():
            self.assertFalse(is_blank(assignment))

    def test_a_positional_only_slot_does_not_count_as_content(self):
        """An empty slot carrying only order/is_active must not make a row look
        patched -- it would turn routine pairs into CONFLICTING ones that
        nothing could ever clean up."""
        session = self.blank_session(num_mics=1)
        assignment = session.mic_assignments.get()
        PresenterSlot.objects.create(assignment=assignment, order=0,
                                     is_active=True)
        self.assertTrue(is_blank(assignment))

    def test_the_doubled_session_is_all_one_sided(self):
        session = self.doubled_session()
        groups, decisions = judge(session)
        self.assertEqual(sorted(groups), [1, 2, 3, 4])
        self.assertEqual({v for v, _, _ in decisions.values()}, {ONE_SIDED})

    def test_two_blank_rows_are_identical(self):
        session = self.blank_session(num_mics=1)
        MicAssignment.objects.create(session=session, rf_number=1)
        verdict, keeper, lost = decide_group(self.rows(session, 1))
        self.assertEqual(verdict, IDENTICAL)
        self.assertEqual(lost, [])

    def test_two_differently_patched_rows_conflict(self):
        session = self.blank_session(num_mics=1)
        first = session.mic_assignments.get()
        first.notes = 'one'
        first.save()
        second = MicAssignment.objects.create(session=session, rf_number=1,
                                              notes='two')
        verdict, keeper, lost = decide_group(self.rows(session, 1))
        self.assertEqual(verdict, CONFLICTING)
        self.assertIsNone(keeper)

    def test_a_clean_session_has_no_groups(self):
        groups, decisions = judge(self.patched_session())
        self.assertEqual(groups, {})
        self.assertEqual(decisions, {})

    def test_groups_read_scaffold_first(self):
        session = self.doubled_session()
        for rows in duplicate_groups(session).values():
            self.assertEqual([r.id for r in rows],
                             sorted(r.id for r in rows))


class KeepRuleTests(_SessionMixin, TestCase):
    """The rule this file exists for: contents, not id order."""

    def test_the_keeper_is_the_patched_row_not_the_older_one(self):
        session = self.doubled_session()
        for number in (1, 2, 3, 4):
            rows = self.rows(session, number)
            scaffold, copied = rows
            self.assertLess(scaffold.id, copied.id)
            verdict, keeper, lost = decide_group(rows)
            self.assertEqual(verdict, ONE_SIDED)
            self.assertEqual(keeper.id, copied.id)
            self.assertNotEqual(keeper.id, min(r.id for r in rows))

    def test_an_identical_pair_keeps_the_lowest_id(self):
        session = self.blank_session(num_mics=1)
        MicAssignment.objects.create(session=session, rf_number=1)
        rows = self.rows(session, 1)
        verdict, keeper, lost = decide_group(rows)
        self.assertEqual(keeper.id, min(r.id for r in rows))

    def test_the_order_rows_come_back_in_does_not_change_the_answer(self):
        session = self.doubled_session(num_mics=1)
        rows = self.rows(session, 1)
        forwards = decide_group(rows)[1]
        backwards = decide_group(list(reversed(rows)))[1]
        self.assertEqual(forwards.id, backwards.id)


class NothingProtectedIsEverDeletedTests(_SessionMixin, TestCase):
    """The requirement: a row holding the group's only presenter, note or
    mic'd state is never deleted.

    In every shape below the protected row also makes itself non-empty, so the
    group classifies as CONFLICTING and the cleanup skips it -- the protection
    is delivered by the verdict, and the veto never has to fire. That is the
    reassuring outcome, not a loophole: the rows survive either way. The veto
    is tested as a mechanism in ``ProtectionVetoMechanismTests`` below, and
    ``test_no_keeper_ever_loses_a_protected_thing`` asserts the guarantee over
    the whole corpus rather than trusting either path.
    """

    def pair(self):
        """Two rows at rf 1: returns (session, lower_id, higher_id)."""
        session = self.blank_session(num_mics=1)
        first = session.mic_assignments.get()
        second = MicAssignment.objects.create(session=session, rf_number=1)
        return session, first, second

    def contested(self, give_to_low):
        """A pair where the higher-id row holds the field payload and the
        lower-id row holds whatever ``give_to_low`` puts on it."""
        session, low, high = self.pair()
        high.mic_type = 'handheld'
        high.save()
        give_to_low(low)
        return session, low, high

    def assert_nothing_deleted(self, session, holder, protection):
        before = set(session.mic_assignments.values_list('id', flat=True))
        slots_before = PresenterSlot.objects.count()

        verdict, keeper, lost = decide_group(self.rows(session, 1))
        self.assertIsNone(
            keeper,
            'a group whose only %s sits on a non-keeper must not be given a '
            'keeper' % protection)

        self.cleanup(apply=True)
        self.assertEqual(
            set(session.mic_assignments.values_list('id', flat=True)), before,
            'the cleanup deleted a row holding the only %s' % protection)
        self.assertEqual(PresenterSlot.objects.count(), slots_before)
        holder.refresh_from_db()

    def test_a_presenter_held_only_by_the_lower_row_survives(self):
        def give(row):
            PresenterSlot.objects.create(assignment=row, order=0,
                                         is_active=True,
                                         presenter=self.presenter)
        session, low, high = self.contested(give)
        self.assertTrue(has_presenter(low))
        self.assert_nothing_deleted(session, low, 'presenter')
        self.assertTrue(has_presenter(
            session.mic_assignments.get(id=low.id)))

    def test_a_note_held_only_by_the_lower_row_survives(self):
        def give(row):
            row.notes = 'cue from SM'
            row.save()
        session, low, high = self.contested(give)
        self.assert_nothing_deleted(session, low, 'note')
        self.assertEqual(
            session.mic_assignments.get(id=low.id).notes, 'cue from SM')

    def test_a_micd_flag_held_only_by_the_lower_row_survives(self):
        def give(row):
            row.is_micd = True
            row.save()
        session, low, high = self.contested(give)
        self.assert_nothing_deleted(session, low, "mic'd state")
        self.assertTrue(session.mic_assignments.get(id=low.id).is_micd)

    def test_a_slot_note_held_only_by_the_lower_row_survives(self):
        def give(row):
            PresenterSlot.objects.create(assignment=row, order=0,
                                         notes='tape the pack down')
        session, low, high = self.contested(give)
        self.assertTrue(has_notes(low))
        self.assert_nothing_deleted(session, low, 'slot note')

    def test_a_slot_micd_flag_held_only_by_the_lower_row_survives(self):
        def give(row):
            PresenterSlot.objects.create(assignment=row, order=0,
                                         is_micd=True)
        session, low, high = self.contested(give)
        self.assertTrue(has_micd_state(low))
        self.assert_nothing_deleted(session, low, "slot mic'd state")

    def test_a_presenter_the_property_cannot_see_is_protected_too(self):
        """``MicAssignment.presenter`` returns the *active* slot, falling back
        to the first by order. So a row holding an active slot with nobody on
        it plus an inactive slot with a real presenter reads as having no
        presenter through the property, while the person is right there in the
        second slot. ``has_presenter`` checks every slot for exactly this
        reason -- going through the property would make that presenter
        silently deletable.
        """
        second = Presenter.objects.create(project=self.project,
                                          name='Sam Okonjo')

        def give(row):
            PresenterSlot.objects.create(assignment=row, order=0,
                                         is_active=True, presenter=None)
            PresenterSlot.objects.create(assignment=row, order=1,
                                         is_active=False, presenter=second)

        session, low, high = self.contested(give)
        low.refresh_from_db()
        self.assertIsNone(low.presenter)          # the property sees nobody
        self.assertTrue(has_presenter(low))       # the protection sees Sam
        self.assert_nothing_deleted(session, low, 'inactive-slot presenter')
        self.assertTrue(
            PresenterSlot.objects.filter(assignment_id=low.id,
                                         presenter=second).exists())

    def test_a_lone_inactive_slot_is_still_seen_by_the_property(self):
        """Guards the premise of the test above: ``active_slot`` falls back to
        the first slot by order, so a single inactive slot is NOT invisible.
        The gap only opens when an empty active slot shadows a populated one."""
        session, low, high = self.pair()
        PresenterSlot.objects.create(assignment=low, order=1, is_active=False,
                                     presenter=self.presenter)
        low.refresh_from_db()
        self.assertEqual(low.presenter, self.presenter)

    def test_presenter_is_a_property_over_the_slots_not_a_column(self):
        """``MicAssignment`` declares ``presenter = models.ForeignKey(...)``,
        but a read-only ``@property`` of the same name later in the class body
        shadows it, so Django never registers the field -- there is no
        ``presenter_id`` column and the slots are the only place a presenter
        lives. Reading the FK was the first thing this module got wrong, so pin
        the shape of it."""
        from django.core.exceptions import FieldDoesNotExist

        with self.assertRaises(FieldDoesNotExist):
            MicAssignment._meta.get_field('presenter')
        self.assertIsInstance(
            MicAssignment.__dict__.get('presenter'), property)

        session, low, high = self.pair()
        self.assertIsNone(low.presenter)
        PresenterSlot.objects.create(assignment=low, order=0, is_active=True,
                                     presenter=self.presenter)
        low.refresh_from_db()
        self.assertEqual(low.presenter, self.presenter)
        self.assertTrue(has_presenter(low))

    def test_no_veto_when_the_keeper_holds_everything(self):
        """The normal case must stay decidable, or the cleanup clears nothing."""
        session = self.doubled_session()
        for number in (1, 2, 3, 4):
            verdict, keeper, lost = decide_group(self.rows(session, number))
            self.assertEqual(lost, [])
            self.assertIsNotNone(keeper)

    def test_no_veto_when_both_rows_hold_the_same_presenter(self):
        session, low, high = self.pair()
        for row in (low, high):
            PresenterSlot.objects.create(assignment=row, order=0,
                                         presenter=self.presenter)
        verdict, keeper, lost = decide_group(self.rows(session, 1))
        self.assertEqual(verdict, IDENTICAL)
        self.assertEqual(lost, [])
        self.assertEqual(keeper.id, low.id)

    def test_no_keeper_ever_loses_a_protected_thing(self):
        """The guarantee itself, over every shape this file builds: whenever a
        keeper IS chosen, it holds every protected thing present in its group.

        This is the assertion that would catch a future change to the payload,
        the verdicts or the protections, whichever of the two mechanisms is
        doing the protecting at the time.
        """
        shapes = []

        shapes.append(self.doubled_session(num_mics=3, name='all one-sided'))

        blanks = self.blank_session(num_mics=2, name='blank pairs')
        for n in (1, 2):
            MicAssignment.objects.create(session=blanks, rf_number=n)
        shapes.append(blanks)

        mixed = self.blank_session(num_mics=2, name='mixed')
        for n in (1, 2):
            self.patch(MicAssignment.objects.create(session=mixed,
                                                    rf_number=n))
        stray = self.rows(mixed, 1)[0]
        stray.notes = 'disagrees'
        stray.save()
        shapes.append(mixed)

        checked = 0
        for session in shapes:
            groups, decisions = judge(session)
            for number, rows in groups.items():
                verdict, keeper, lost = decisions[number]
                if keeper is None:
                    continue
                checked += 1
                for name, test in PROTECTIONS.items():
                    if any(test(row) for row in rows):
                        self.assertTrue(
                            test(keeper),
                            'keeping id=%d in rf %d of %r would lose the '
                            "group's only %s"
                            % (keeper.id, number, session.name, name))
        self.assertGreater(checked, 0, 'the corpus decided nothing, so the '
                                       'guarantee was never exercised')


class ProtectionVetoMechanismTests(_SessionMixin, TestCase):
    """``losses_from_keeping`` itself, and why it is kept despite being
    unreachable through the current payload.

    As ``NothingProtectedIsEverDeletedTests`` shows, a protected row is also a
    non-empty row, so such groups classify as CONFLICTING and never get a
    keeper -- the veto never fires in production as the payload stands today.
    It is kept as the backstop for the payload *changing*: narrow
    ``SLOT_FIELDS`` or ``ASSIGNMENT_FIELDS`` and a protected row can start
    looking empty, at which point the verdict alone would delete a presenter.
    These tests drive it with a deliberately narrowed payload to prove the
    backstop is live rather than decorative.
    """

    def pair(self):
        session = self.blank_session(num_mics=1)
        first = session.mic_assignments.get()
        second = MicAssignment.objects.create(session=session, rf_number=1)
        return session, first, second

    def rows_at_one(self, session):
        return list(session.mic_assignments.filter(rf_number=1)
                    .order_by('id'))

    def test_losses_from_keeping_names_what_a_keeper_would_destroy(self):
        session, low, high = self.pair()
        PresenterSlot.objects.create(assignment=low, order=0,
                                     presenter=self.presenter)
        rows = self.rows_at_one(session)
        self.assertEqual(
            losses_from_keeping(rows, high, PROTECTIONS), ['presenter'])
        self.assertEqual(losses_from_keeping(rows, low, PROTECTIONS), [])

    def test_losses_from_keeping_is_empty_when_there_is_no_keeper(self):
        session, low, high = self.pair()
        PresenterSlot.objects.create(assignment=low, order=0,
                                     presenter=self.presenter)
        self.assertEqual(
            losses_from_keeping(self.rows_at_one(session), None, PROTECTIONS),
            [])

    def test_it_reports_every_protected_thing_that_would_go(self):
        session, low, high = self.pair()
        low.notes = 'cue'
        low.is_micd = True
        low.save()
        PresenterSlot.objects.create(assignment=low, order=0,
                                     presenter=self.presenter)
        lost = losses_from_keeping(self.rows_at_one(session), high,
                                   PROTECTIONS)
        self.assertEqual(sorted(lost), sorted(PROTECTIONS))

    def test_a_narrowed_payload_would_delete_a_presenter_without_the_veto(self):
        """The failure the veto exists to stop. With a payload that ignores the
        slots, the presenter-holding row looks empty, so the verdict is
        ONE-SIDED and points at the *other* row."""
        session, low, high = self.pair()
        high.mic_type = 'handheld'
        high.save()
        PresenterSlot.objects.create(assignment=low, order=0,
                                     presenter=self.presenter)
        rows = self.rows_at_one(session)

        def narrow_payload(assignment):
            return (assignment.mic_type,)

        verdict, keeper, lost = decide(rows, narrow_payload)     # no veto
        self.assertEqual(verdict, ONE_SIDED)
        self.assertEqual(keeper.id, high.id)
        self.assertFalse(has_presenter(keeper))

    def test_the_veto_stops_it(self):
        session, low, high = self.pair()
        high.mic_type = 'handheld'
        high.save()
        PresenterSlot.objects.create(assignment=low, order=0,
                                     presenter=self.presenter)
        rows = self.rows_at_one(session)

        def narrow_payload(assignment):
            return (assignment.mic_type,)

        verdict, keeper, lost = decide(rows, narrow_payload, PROTECTIONS)
        self.assertEqual(verdict, ONE_SIDED)
        self.assertIsNone(keeper, 'the veto must withdraw the keeper')
        self.assertEqual(lost, ['presenter'])

    def test_the_full_payload_catches_it_as_conflicting_instead(self):
        """Why the veto is unreachable today: the real payload already sees the
        slot, so the group never becomes decidable in the first place."""
        session, low, high = self.pair()
        high.mic_type = 'handheld'
        high.save()
        PresenterSlot.objects.create(assignment=low, order=0,
                                     presenter=self.presenter)
        verdict, keeper, lost = decide_group(self.rows_at_one(session))
        self.assertEqual(verdict, CONFLICTING)
        self.assertIsNone(keeper)
        self.assertEqual(lost, [])


class ReportCommandTests(_SessionMixin, TestCase):
    """Per project/session: duplicated rf_numbers, who holds what, verdict."""

    def test_a_clean_database_says_so(self):
        self.patched_session()
        self.assertIn('No sessions with duplicated rf_numbers found',
                      self.report())

    def test_it_names_the_project_and_the_session(self):
        session = self.doubled_session()
        out = self.report()
        self.assertIn('Project %d: Duplicated Show' % self.project.id, out)
        self.assertIn('session id=%d' % session.id, out)
        self.assertIn('General Session', out)

    def test_it_lists_the_duplicated_rf_numbers_and_counts(self):
        self.doubled_session()
        out = self.report()
        self.assertIn('assignments=8 (num_mics=4)', out)
        self.assertIn('duplicated rf_numbers=[1,2,3,4]', out)
        self.assertIn('redundant rows=4', out)
        self.assertIn('4 redundant MicAssignment row(s)', out)

    def test_it_gives_a_verdict_per_rf_number(self):
        self.doubled_session()
        out = self.report()
        self.assertIn(ONE_SIDED, out)
        self.assertIn('ONE-SIDED=4', out)

    def test_it_says_which_row_holds_the_presenter_notes_and_micd_state(self):
        """The explicit ask: the report has to show which row carries what."""
        session = self.doubled_session(num_mics=1)
        scaffold, copied = self.rows(session, 1)
        out = self.report(show_values=True)
        self.assertIn('id=%-7d' % copied.id, out)
        self.assertIn('Jane Doe', out)
        self.assertIn("holds presenter, notes, mic'd", out)
        self.assertIn('blank', out)                  # the scaffold row
        self.assertIn('<- keep', out)

    def test_it_flags_a_contested_pair_and_says_who_holds_the_presenter(self):
        """The row carrying the presenter is named, and the group is left for a
        human -- the report's half of "never delete the only presenter"."""
        session = self.blank_session(num_mics=1)
        low = session.mic_assignments.get()
        MicAssignment.objects.create(session=session, rf_number=1,
                                     mic_type='handheld')
        PresenterSlot.objects.create(assignment=low, order=0,
                                     presenter=self.presenter)
        out = self.report()
        self.assertIn(CONFLICTING, out)
        self.assertIn('id=%-7d' % low.id, out)
        self.assertIn('Jane Doe', out)
        self.assertIn('[holds presenter]', out)
        self.assertIn('need a human', out)
        self.assertIn('the cleanup will skip', out)

    def test_conflicting_only_hides_the_decidable_sessions(self):
        self.doubled_session(num_mics=2, name='all one-sided')
        session = self.blank_session(num_mics=1, name='needs a human')
        first = session.mic_assignments.get()
        first.notes = 'one'
        first.save()
        MicAssignment.objects.create(session=session, rf_number=1, notes='two')

        out = self.report(conflicting_only=True)
        self.assertIn('needs a human', out)
        self.assertNotIn('all one-sided', out)

    def test_the_project_filter_restricts_it(self):
        self.doubled_session()
        other = Project.objects.create(name='Other', owner=self.user)
        self.assertIn('No sessions with duplicated rf_numbers found',
                      self.report(project=other.id))

    def test_the_session_filter_restricts_it(self):
        first = self.doubled_session(num_mics=2, name='session one')
        second = self.doubled_session(num_mics=2, name='session two')
        out = self.report(session=first.id)
        self.assertIn('session one', out)
        self.assertNotIn('session two', out)

    def test_it_writes_nothing(self):
        self.doubled_session()
        before = list(MicAssignment.objects.order_by('id')
                      .values_list('id', 'rf_number', 'notes'))
        slots_before = PresenterSlot.objects.count()
        self.report(show_values=True)
        self.report(conflicting_only=True)
        self.assertEqual(
            list(MicAssignment.objects.order_by('id')
                 .values_list('id', 'rf_number', 'notes')), before)
        self.assertEqual(PresenterSlot.objects.count(), slots_before)


class CleanupDryRunTests(_SessionMixin, TestCase):
    def test_the_default_run_writes_nothing(self):
        session = self.doubled_session()
        before = set(MicAssignment.objects.values_list('id', flat=True))
        out = self.cleanup()
        self.assertIn('DRY RUN', out)
        self.assertEqual(set(MicAssignment.objects.values_list('id', flat=True)),
                         before)

    def test_it_names_the_rows_it_would_delete(self):
        session = self.doubled_session()
        out = self.cleanup()
        for number in (1, 2, 3, 4):
            scaffold, copied = self.rows(session, number)
            self.assertIn('keep id=%d' % copied.id, out)
            self.assertIn('id=%d' % scaffold.id, out)

    def test_the_dry_run_and_the_apply_agree(self):
        self.doubled_session()
        self.assertIn('4 row(s) resolvable', self.cleanup())
        self.assertIn('Deleted 4 redundant MicAssignment row(s)',
                      self.cleanup(apply=True))

    def test_a_clean_database_says_nothing_to_do(self):
        self.patched_session()
        self.assertIn('Nothing to do', self.cleanup())


class CleanupApplyTests(_SessionMixin, TestCase):
    def test_it_leaves_one_row_per_rf_number(self):
        session = self.doubled_session()
        self.cleanup(apply=True)
        self.assertEqual(session.mic_assignments.count(), 4)
        self.assertEqual(
            sorted(session.mic_assignments.values_list('rf_number', flat=True)),
            [1, 2, 3, 4])

    def test_the_survivors_are_the_patched_rows_with_their_slots(self):
        session = self.doubled_session()
        expected = {a.rf_number: a.id
                    for a in session.mic_assignments.all()
                    if not is_blank(a)}
        self.cleanup(apply=True)
        self.assertEqual(
            {a.rf_number: a.id for a in session.mic_assignments.all()},
            expected)
        for assignment in session.mic_assignments.all():
            self.assertEqual(assignment.presenter_slots.count(), 1)
            self.assertTrue(has_presenter(assignment))
            self.assertTrue(has_notes(assignment))
            self.assertTrue(has_micd_state(assignment))

    def test_no_blank_row_survives(self):
        session = self.doubled_session()
        self.cleanup(apply=True)
        self.assertEqual(
            [a.id for a in session.mic_assignments.all() if is_blank(a)], [])

    def test_the_victims_slots_go_with_them_and_no_others(self):
        session = self.doubled_session()
        self.assertEqual(PresenterSlot.objects.count(), 4)   # only copies have slots
        self.cleanup(apply=True)
        self.assertEqual(PresenterSlot.objects.count(), 4)

    def test_it_is_idempotent(self):
        self.doubled_session()
        self.cleanup(apply=True)
        self.assertIn('Nothing to do', self.cleanup(apply=True))

    def test_it_leaves_a_clean_session_alone(self):
        clean = self.patched_session(name='already fine')
        self.doubled_session(name='doubled')
        before = {a.id: payload_of(a) for a in clean.mic_assignments.all()}
        self.cleanup(apply=True)
        self.assertEqual(
            {a.id: payload_of(a) for a in clean.mic_assignments.all()}, before)

    def test_it_skips_one_group_and_clears_the_rest(self):
        session = self.doubled_session()
        scaffold = self.rows(session, 2)[0]
        scaffold.notes = 'disagrees'
        scaffold.save()

        out = self.cleanup(apply=True)
        self.assertIn('1 group(s) skipped', out)
        self.assertIn('Deleted 3 redundant', out)
        self.assertEqual(session.mic_assignments.filter(rf_number=2).count(), 2)
        for number in (1, 3, 4):
            self.assertEqual(
                session.mic_assignments.filter(rf_number=number).count(), 1)

    def test_a_session_where_nothing_is_decidable_loses_nothing(self):
        session = self.blank_session(num_mics=2)
        for assignment in session.mic_assignments.all():
            assignment.notes = 'original %d' % assignment.rf_number
            assignment.save()
        for n in (1, 2):
            MicAssignment.objects.create(session=session, rf_number=n,
                                         notes='copy %d' % n)
        before = set(MicAssignment.objects.values_list('id', flat=True))
        out = self.cleanup(apply=True)
        self.assertIn('Nothing deletable', out)
        self.assertEqual(set(MicAssignment.objects.values_list('id', flat=True)),
                         before)

    def test_the_project_filter_restricts_the_delete(self):
        in_scope = self.doubled_session(num_mics=2, name='in scope')
        other = Project.objects.create(name='Other', owner=self.user)
        other_day = ShowDay.objects.create(project=other,
                                           date=date(2026, 10, 9),
                                           name='Other day', order=0)
        out_of_scope = MicSession.objects.create(day=other_day, name='out',
                                                 num_mics=2, order=0)
        for n in (1, 2):
            MicAssignment.objects.create(session=out_of_scope, rf_number=n,
                                         notes='keep %d' % n)
        self.assertEqual(out_of_scope.mic_assignments.count(), 4)

        self.cleanup(project=self.project.id, apply=True)
        self.assertEqual(out_of_scope.mic_assignments.count(), 4)
        self.assertEqual(in_scope.mic_assignments.count(), 2)

    def test_the_session_filter_restricts_the_delete(self):
        first = self.doubled_session(num_mics=2, name='one')
        second = self.doubled_session(num_mics=2, name='two')
        self.cleanup(session=first.id, apply=True)
        self.assertEqual(first.mic_assignments.count(), 2)
        self.assertEqual(second.mic_assignments.count(), 4)

    def test_an_unknown_project_id_is_reported_not_ignored(self):
        self.doubled_session()
        out = self.cleanup(project=999999, apply=True)
        self.assertIn('No project with id 999999', out)
        self.assertEqual(MicAssignment.objects.count(), 8)

    def test_a_triple_reduces_to_the_patched_row(self):
        session = self.doubled_session(num_mics=2)
        for n in (1, 2):
            MicAssignment.objects.create(session=session, rf_number=n)
        self.assertEqual(session.mic_assignments.count(), 6)
        self.cleanup(apply=True)
        self.assertEqual(session.mic_assignments.count(), 2)
        self.assertEqual(
            sorted(a.notes for a in session.mic_assignments.all()),
            ['RF 1', 'RF 2'])


class NumberingIsNotTouchedTests(_SessionMixin, TestCase):
    """The issue #36 post_delete receiver renumbers survivors to 1..N. Letting
    it run during the cleanup would pull a *skipped* pair apart and hide the
    duplication for good."""

    def test_a_skipped_pair_keeps_its_shared_rf_number(self):
        session = self.doubled_session()
        scaffold = self.rows(session, 2)[0]
        scaffold.notes = 'disagrees'
        scaffold.save()

        self.cleanup(apply=True)

        still_paired = session.mic_assignments.filter(rf_number=2)
        self.assertEqual(still_paired.count(), 2,
                         'the skipped pair was renumbered apart, which would '
                         'hide the duplication from the report')

    def test_the_report_still_sees_the_skipped_pair_afterwards(self):
        session = self.doubled_session()
        scaffold = self.rows(session, 2)[0]
        scaffold.notes = 'disagrees'
        scaffold.save()
        self.cleanup(apply=True)

        out = self.report()
        self.assertIn('duplicated rf_numbers=[2]', out)
        self.assertIn(CONFLICTING, out)

    def test_the_survivors_keep_the_source_numbering(self):
        session = self.doubled_session()
        self.cleanup(apply=True)
        self.assertEqual(
            sorted(session.mic_assignments.values_list('rf_number', flat=True)),
            [1, 2, 3, 4])

    def test_num_mics_is_left_alone(self):
        """The cleanup deletes rows; renumber_mic_assignments is the tool for
        numbering and num_mics, and is only safe once the report is clean."""
        session = self.doubled_session()
        self.cleanup(apply=True)
        session.refresh_from_db()
        self.assertEqual(session.num_mics, 4)

    def test_the_receiver_is_reconnected_afterwards(self):
        """Suspending it must not leak: the Mic Tracker's own delete still
        renumbers."""
        session = self.doubled_session()
        self.cleanup(apply=True)

        # A normal delete, outside the command, must renumber again.
        session.mic_assignments.filter(rf_number=1).delete()
        session.refresh_from_db()
        self.assertEqual(
            sorted(session.mic_assignments.values_list('rf_number', flat=True)),
            [1, 2, 3])

    def test_the_context_manager_restores_the_receiver_after_an_error(self):
        session = self.doubled_session(num_mics=1)
        try:
            with numbering_held():
                raise RuntimeError('boom')
        except RuntimeError:
            pass
        session.mic_assignments.filter(rf_number=1).order_by('id').first().delete()
        session.refresh_from_db()
        self.assertEqual(
            list(session.mic_assignments.values_list('rf_number', flat=True)),
            [1])

    def test_nesting_the_guard_does_not_lose_the_receiver(self):
        with numbering_held():
            with numbering_held():
                pass
        session = self.doubled_session(num_mics=2)
        session.mic_assignments.filter(rf_number=1).order_by('id').first().delete()
        session.refresh_from_db()
        self.assertEqual(
            sorted(session.mic_assignments.values_list('rf_number', flat=True)),
            [1, 2, 3])


class DescribeTests(_SessionMixin, TestCase):
    """Both commands print rows through describe(), so it has to be readable."""

    def test_a_blank_row_reads_blank(self):
        session = self.blank_session(num_mics=1)
        self.assertEqual(describe(session.mic_assignments.get()), 'blank')

    def test_a_patched_row_names_its_presenter_and_flags(self):
        session = self.doubled_session(num_mics=1)
        copied = self.rows(session, 1)[1]
        text = describe(copied)
        self.assertIn('presenter=Jane Doe', text)
        self.assertIn('slots=1', text)
        self.assertIn("MIC'D", text)
        self.assertIn('RF 1', text)
        self.assertIn('mic_type=handheld', text)
