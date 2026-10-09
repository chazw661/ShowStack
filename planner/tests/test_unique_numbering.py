"""``unique_amp_channel_number`` / ``unique_session_rf_number``, and every
write path that could trip over them.

Issue #100 let ``Project.duplicate()`` double the child rows that a parent's
``save()`` had already scaffolded, so a 4-channel amp came out with 8
``AmpChannel`` rows numbered 1,1,2,2,3,3,4,4 and a mic session came out with
every ``rf_number`` twice. That is fixed at the source and the production data
is clean, but nothing in the schema stopped the next bug writing the same
shape. Migration 0198 adds the two constraints that do.

A uniqueness constraint on a number that software renumbers is only safe if no
write path passes through a colliding intermediate state. The constraints are
deliberately **immediate, not DEFERRABLE INITIALLY DEFERRED** -- see the
migration's module docstring for the full reasoning, the short version being
that Django emits *no SQL at all* for a deferrable unique constraint on
SQLite, which is where this suite runs, so a deferred constraint would be
tested against nothing.

That makes the audit of the renumbering paths load-bearing rather than
advisory, so each one has a test here:

  * ``MicSession.renumber_assignments()`` -- the one in-place renumberer.
    Reached from the issue #36 ``post_delete`` receiver (delete a middle RF),
    from ``MicSessionAdmin.save_formset``, and from the
    ``renumber_mic_assignments`` command.
  * ``Amp.setup_channels()`` and ``MicSession.create_mic_assignments()`` --
    gap fillers. Both used to derive the numbers to create from a *row count*,
    which produced a second copy of an existing number whenever the surviving
    numbers had a hole.
  * ``Project.duplicate()`` and ``MicSession.duplicate_to_session()`` --
    scaffold-then-copy.
  * ``mic_assignment_reorder`` and ``amp_reorder`` -- drag-to-reorder, which
    must be shown *not* to touch these columns.
  * The migration's own pre-flight check, which has to abort with the cleanup
    commands named rather than let ``AddConstraint`` raise a bare
    ``UniqueViolation``.

Run with::

    python manage.py test planner.tests.test_unique_numbering \\
        --settings=audiopatch.test_settings
"""
import json
from datetime import date

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from planner.models import (
    Amp, AmpChannel, AmpLocation, AmpModel,
    MicAssignment, MicSession, Presenter, PresenterSlot, Project,
    ProjectMember, ShowDay,
)
from planner.tests.legacy_duplicate_schema import legacy_duplicate_schema
from planner.utils.mic_assignment_dupes import numbering_held

MIGRATION = 'planner.migrations.0198_unique_amp_channel_and_rf_number'


def numbers(queryset, field):
    return sorted(queryset.values_list(field, flat=True))


def guard_module():
    return __import__(MIGRATION, fromlist=['check_for_duplicates'])


class _Fixture:
    """One project, one 4-channel amp, one 5-mic session."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='unique_numbering', email='u@example.com', password='x')
        self.project = Project.objects.create(name='Numbering Show',
                                              owner=self.user)
        self.amp_location = AmpLocation.objects.create(
            project=self.project, name='SL LA Racks')
        self.amp_model = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA12X', channel_count=4,
            nl4_connector_count=2, nl8_connector_count=1,
            cacom_output_count=1)
        self.other_model = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA4X', channel_count=4,
            nl4_connector_count=2, nl8_connector_count=1,
            cacom_output_count=1)
        self.amp = Amp.objects.create(
            project=self.project, location=self.amp_location,
            name='SL LA12X #1', amp_model=self.amp_model)
        self.day = ShowDay.objects.create(
            project=self.project, date=date(2026, 10, 8), name='Day 1',
            order=0)
        self.session = MicSession.objects.create(
            day=self.day, name='General Session', num_mics=5, order=0)

    def rf_numbers(self, session=None):
        return numbers((session or self.session).mic_assignments, 'rf_number')

    def channel_numbers(self, amp=None):
        return numbers((amp or self.amp).channels, 'channel_number')

    def hole_in_rf(self, *rf_numbers):
        """Delete assignments without letting the receiver heal the gap."""
        with numbering_held():
            self.session.mic_assignments.filter(
                rf_number__in=rf_numbers).delete()

    def keep_only_rf(self, keep):
        with numbering_held():
            self.session.mic_assignments.exclude(
                rf_number__in=keep).delete()


# ---------------------------------------------------------------------------
# 1. The constraints exist, and they bite
# ---------------------------------------------------------------------------

class ConstraintsAreEnforcedTests(_Fixture, TestCase):
    """The premise. Every other test here is worthless if these fail."""

    def test_a_second_channel_with_the_same_number_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AmpChannel.objects.create(amp=self.amp, channel_number=1)

    def test_the_same_channel_number_on_another_amp_is_fine(self):
        """The constraint is per-amp, not global. Every LA12X in a 20-amp
        rack has a channel 1."""
        other = Amp.objects.create(
            project=self.project, location=self.amp_location,
            name='SL LA12X #2', amp_model=self.amp_model)
        self.assertEqual(self.channel_numbers(other), [1, 2, 3, 4])

    def test_a_second_assignment_with_the_same_rf_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MicAssignment.objects.create(session=self.session, rf_number=1)

    def test_the_same_rf_number_in_another_session_is_fine(self):
        """RF 1 in the keynote and RF 1 after lunch are different mics on the
        same frequency, which is normal."""
        other = MicSession.objects.create(
            day=self.day, name='Afternoon', num_mics=5, order=1)
        self.assertEqual(self.rf_numbers(other), [1, 2, 3, 4, 5])


class ConstraintsAreImmediateTests(_Fixture, TestCase):
    """Pins the deferrable decision so a later edit has to argue with it.

    If someone sets ``deferrable=Deferrable.DEFERRED`` on either constraint,
    Django's SQLite backend emits no SQL for it at all -- the constraint
    quietly stops existing locally and in CI, and
    ``ConstraintsAreEnforcedTests`` above starts passing against nothing.
    Read the migration docstring before changing this.
    """

    EXPECTED = {
        AmpChannel: 'unique_amp_channel_number',
        MicAssignment: 'unique_session_rf_number',
    }

    def test_neither_constraint_is_deferrable(self):
        for model, name in self.EXPECTED.items():
            with self.subTest(model=model.__name__):
                constraint = next(
                    c for c in model._meta.constraints if c.name == name)
                self.assertIsNone(
                    constraint.deferrable,
                    'a deferrable unique constraint is dropped silently on '
                    'SQLite, so this suite would stop testing anything')

    def test_the_database_really_has_both_constraints(self):
        """Model state is not evidence; ask the database."""
        for model, name in self.EXPECTED.items():
            with self.subTest(model=model.__name__):
                with connection.cursor() as cursor:
                    found = connection.introspection.get_constraints(
                        cursor, model._meta.db_table)
                self.assertIn(name, found)
                self.assertTrue(found[name]['unique'])


# ---------------------------------------------------------------------------
# 2. renumber_assignments() -- the one path that renumbers in place
# ---------------------------------------------------------------------------

class RenumberAfterDeleteTests(_Fixture, TestCase):
    """The issue #36 ``post_delete`` receiver, which is the path that actually
    runs when an engineer deletes a row in the Mic Tracker."""

    def test_deleting_a_middle_rf_renumbers_the_survivors(self):
        """Deleting RF 3 of 1..5 leaves 1..4, not 1,2,4,5.

        The explicit risk case: the receiver has to pull RF 4 down onto 3 and
        RF 5 down onto 4, so it writes numbers that rows held moments before.
        """
        self.session.mic_assignments.get(rf_number=3).delete()
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4])

    def test_deleting_the_first_rf_renumbers_the_survivors(self):
        """Every surviving row moves, so every write lands on ground another
        row occupied a moment earlier."""
        self.session.mic_assignments.get(rf_number=1).delete()
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4])

    def test_deleting_the_last_rf_needs_no_renumbering(self):
        self.session.mic_assignments.get(rf_number=5).delete()
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4])

    def test_num_mics_follows_the_delete(self):
        """Otherwise the next create_mic_assignments() re-adds the row."""
        self.session.mic_assignments.get(rf_number=3).delete()
        self.session.refresh_from_db()
        self.assertEqual(self.session.num_mics, 4)

    def test_deleting_middle_rows_repeatedly(self):
        """Four renumbering passes in a row, each starting from the result of
        the last. A collision on any of them raises."""
        for _ in range(4):
            assignments = list(
                self.session.mic_assignments.order_by('rf_number'))
            assignments[len(assignments) // 2].delete()
        self.assertEqual(self.rf_numbers(), [1])

    def test_the_patch_follows_the_row_through_a_delete(self):
        """Renumbering must move numbers, never payloads: the mic that was
        RF 5 keeps its own notes when it becomes RF 4."""
        for assignment in self.session.mic_assignments.all():
            assignment.notes = 'was RF %d' % assignment.rf_number
            assignment.save(update_fields=['notes'])

        self.session.mic_assignments.get(rf_number=3).delete()

        self.assertEqual(
            [(a.rf_number, a.notes) for a in
             self.session.mic_assignments.order_by('rf_number')],
            [(1, 'was RF 1'), (2, 'was RF 2'), (3, 'was RF 4'),
             (4, 'was RF 5')])

    def test_deleting_the_session_cascades_without_renumbering(self):
        """The receiver has to no-op when the parent is already gone --
        ``filter().first()`` rather than ``get()``."""
        session_id = self.session.id
        self.session.delete()
        self.assertFalse(
            MicAssignment.objects.filter(session_id=session_id).exists())

    def test_the_delete_endpoint_renumbers_too(self):
        """``mic_assignment_delete`` is the button in the admin inline; it
        goes through the same receiver."""
        client = Client()
        client.force_login(self.user)
        s = client.session
        s['current_project_id'] = self.project.id
        s.save()

        target = self.session.mic_assignments.get(rf_number=3)
        response = client.post(
            reverse('planner:mic_assignment_delete', args=[target.id]))
        self.assertTrue(response.json().get('success'), response.json())
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4])


class RenumberCollapsesGapsTests(_Fixture, TestCase):
    """``renumber_assignments()`` called directly, on gapped input."""

    def test_a_gapped_run_collapses_to_1_to_n(self):
        self.keep_only_rf([2, 4, 5])
        self.assertEqual(self.rf_numbers(), [2, 4, 5])  # premise
        self.assertTrue(self.session.renumber_assignments())
        self.assertEqual(self.rf_numbers(), [1, 2, 3])

    def test_a_run_starting_above_one_collapses_down(self):
        """[4, 5] -> [1, 2]: every target is below the value its own row
        holds, so nothing is written onto occupied ground."""
        self.keep_only_rf([4, 5])
        self.assertTrue(self.session.renumber_assignments())
        self.assertEqual(self.rf_numbers(), [1, 2])

    def test_a_single_row_high_up_collapses_to_one(self):
        self.keep_only_rf([5])
        self.assertTrue(self.session.renumber_assignments())
        self.assertEqual(self.rf_numbers(), [1])

    def test_an_already_consecutive_run_writes_nothing(self):
        self.assertFalse(self.session.renumber_assignments())
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    def test_it_is_idempotent(self):
        self.keep_only_rf([2, 4, 5])
        self.session.renumber_assignments()
        self.assertFalse(self.session.renumber_assignments())
        self.assertEqual(self.rf_numbers(), [1, 2, 3])

    def test_an_empty_session_is_a_no_op(self):
        with numbering_held():
            self.session.mic_assignments.all().delete()
        self.assertFalse(self.session.renumber_assignments())

    def test_the_patch_follows_the_row_not_the_number(self):
        self.keep_only_rf([2, 4, 5])
        for assignment in self.session.mic_assignments.all():
            assignment.notes = 'was RF %d' % assignment.rf_number
            assignment.save(update_fields=['notes'])
        self.session.renumber_assignments()
        self.assertEqual(
            [(a.rf_number, a.notes) for a in
             self.session.mic_assignments.order_by('rf_number')],
            [(1, 'was RF 2'), (2, 'was RF 4'), (3, 'was RF 5')])

    def test_every_gapped_subset_collapses_without_colliding(self):
        """Exhaustive over the 31 non-empty subsets of RF 1..5.

        This is the property the constraint actually depends on, so it is
        proved rather than sampled. An IntegrityError on any subset means
        some ordering of the writes passed through a state where two rows
        held the same number.
        """
        from itertools import combinations

        for size in range(1, 6):
            for keep in combinations(range(1, 6), size):
                with self.subTest(keep=keep):
                    with transaction.atomic():
                        session = MicSession.objects.create(
                            day=self.day, name='Subset %s' % (keep,),
                            num_mics=5, order=1)
                        with numbering_held():
                            session.mic_assignments.exclude(
                                rf_number__in=keep).delete()
                        self.assertEqual(
                            numbers(session.mic_assignments, 'rf_number'),
                            list(keep))

                        session.renumber_assignments()
                        self.assertEqual(
                            numbers(session.mic_assignments, 'rf_number'),
                            list(range(1, size + 1)))
                        transaction.set_rollback(True)

    def test_renumbering_does_not_depend_on_insertion_order(self):
        """id order and rf order can disagree, and the result must not.

        Only the two-pass-over-negatives form survives this: a single pass
        that iterated by ``id`` instead of ``rf_number`` would take the
        RF 3 row first and write 1 onto it while the RF 1 row still held 1.
        """
        with numbering_held():
            self.session.mic_assignments.all().delete()
            later_id = MicAssignment.objects.create(
                session=self.session, rf_number=3, notes='inserted first')
            earlier_rf = MicAssignment.objects.create(
                session=self.session, rf_number=1, notes='inserted second')
        self.assertGreater(earlier_rf.id, later_id.id)  # premise

        self.assertTrue(self.session.renumber_assignments())

        self.assertEqual(
            [(a.rf_number, a.notes) for a in
             self.session.mic_assignments.order_by('rf_number')],
            [(1, 'inserted second'), (2, 'inserted first')])


class RenumberRepairsLegacyDuplicatesTests(TransactionTestCase):
    """The pre-migration repair path: renumbering data the constraint forbids.

    This is the input that breaks the collision-free argument above --
    [1, 1, 2, 2] -> [1, 2, 3, 4] writes 2 onto the second row while two
    others still hold it -- and it is the state issues #36 and #100 left
    behind. Repairing it is what ``renumber_assignments()`` and the
    ``renumber_mic_assignments`` command are for, on a database that has not
    had migration 0198 applied yet, which is why the constraints come off for
    the duration.

    Note what this does *not* claim: with the constraints dropped a single
    ascending pass would reach the same answer here without raising, so this
    is coverage of the repair, not a proof that the negative scratch pass is
    required. The case that genuinely needs it is
    ``test_renumbering_does_not_depend_on_insertion_order`` above.

    ``TransactionTestCase`` because dropping a table constraint on SQLite
    means rebuilding the table, which is not something to do inside the
    class-level atomic block ``TestCase`` holds open.
    """

    def test_two_passes_repair_a_duplicated_session(self):
        user = get_user_model().objects.create_superuser(
            username='legacy_renumber', email='l@example.com', password='x')
        project = Project.objects.create(name='Legacy Show', owner=user)
        day = ShowDay.objects.create(project=project, date=date(2026, 10, 8),
                                     name='Day 1', order=0)

        with legacy_duplicate_schema():
            session = MicSession.objects.create(day=day, name='Keynote',
                                                num_mics=2, order=0)
            # Exactly what duplicate() used to write.
            for assignment in list(session.mic_assignments.all()):
                MicAssignment.objects.create(
                    session=session, rf_number=assignment.rf_number)
            self.assertEqual(
                numbers(session.mic_assignments, 'rf_number'), [1, 1, 2, 2])

            self.assertTrue(session.renumber_assignments())
            self.assertEqual(
                numbers(session.mic_assignments, 'rf_number'), [1, 2, 3, 4])

        # The constraints go back on when the block exits. That the re-add
        # succeeds at all is the proof the repair left the data unique.
        self.assertEqual(
            numbers(session.mic_assignments, 'rf_number'), [1, 2, 3, 4])


class RenumberCommandTests(_Fixture, TestCase):
    """``manage.py renumber_mic_assignments`` -- the operator-facing path."""

    def test_the_dry_run_writes_nothing(self):
        self.keep_only_rf([2, 4, 5])
        call_command('renumber_mic_assignments', session=self.session.id,
                     verbosity=0)
        self.assertEqual(self.rf_numbers(), [2, 4, 5])

    def test_apply_collapses_the_numbering(self):
        self.keep_only_rf([2, 4, 5])
        call_command('renumber_mic_assignments', session=self.session.id,
                     apply=True, verbosity=0)
        self.assertEqual(self.rf_numbers(), [1, 2, 3])

    def test_apply_on_a_clean_session_is_a_no_op(self):
        call_command('renumber_mic_assignments', session=self.session.id,
                     apply=True, verbosity=0)
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    def test_apply_across_every_session_at_once(self):
        """No --session, so the command sweeps the table. Two sessions
        renumbered in one run, each independently."""
        second = MicSession.objects.create(
            day=self.day, name='Afternoon', num_mics=5, order=1)
        self.keep_only_rf([2, 5])
        with numbering_held():
            second.mic_assignments.exclude(rf_number__in=[3, 4]).delete()

        call_command('renumber_mic_assignments', apply=True, verbosity=0)

        self.assertEqual(self.rf_numbers(), [1, 2])
        self.assertEqual(self.rf_numbers(second), [1, 2])


class AdminInlineRenumberTests(_Fixture, TestCase):
    """The admin path. ``MicAssignmentInlineFormSet.clean()`` stamps
    ``max(rf_number) + 1`` onto rows added with "Add another", then
    ``MicSessionAdmin.save_formset`` collapses the session to 1..N. Two writes
    to the same column in one request, which is where an immediate constraint
    shows up if the order is wrong."""

    def test_new_inline_rows_get_numbers_above_the_existing_ones(self):
        from planner.admin import MicAssignmentInlineFormSet

        FormSet = self._formset_class()
        formset = FormSet(data=self._payload(extra=2), instance=self.session,
                          prefix='mic_assignments')
        self.assertIsInstance(formset, MicAssignmentInlineFormSet)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

        # max + 1 twice: 6 and 7, both free, so no collision on insert.
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5, 6, 7])

    def test_save_formset_renumbers_after_the_inline_saved(self):
        FormSet = self._formset_class()
        formset = FormSet(data=self._payload(extra=2), instance=self.session,
                          prefix='mic_assignments')
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

        self._model_admin().save_formset(
            self._request(), _ParentForm(self.session),
            _SavedFormSet(MicAssignment), change=True)

        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5, 6, 7])
        self.session.refresh_from_db()
        self.assertEqual(self.session.num_mics, 7)

    def test_save_formset_collapses_a_gap_left_by_an_inline_delete(self):
        """A formset that deleted RF 3 leaves 1,2,4,5 behind; save_formset is
        what pulls them back to 1..4. The receiver is suspended for the delete
        so the gap is still there when save_formset runs."""
        self.hole_in_rf(3)
        self.assertEqual(self.rf_numbers(), [1, 2, 4, 5])

        self._model_admin().save_formset(
            self._request(), _ParentForm(self.session),
            _SavedFormSet(MicAssignment), change=True)

        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4])

    def test_adding_a_row_over_a_gap_does_not_collide(self):
        """The nastiest admin shape: a session sitting on 1,2,4,5 gaining a
        new row. ``max + 1`` is 6, which is free, and the collapse afterwards
        has to land on 1..5."""
        self.hole_in_rf(3)

        FormSet = self._formset_class()
        formset = FormSet(data=self._payload(extra=1), instance=self.session,
                          prefix='mic_assignments')
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.rf_numbers(), [1, 2, 4, 5, 6])

        self._model_admin().save_formset(
            self._request(), _ParentForm(self.session),
            _SavedFormSet(MicAssignment), change=True)

        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    # -- helpers ----------------------------------------------------------

    def _model_admin(self):
        from planner.admin import MicSessionAdmin
        from planner.admin_site import showstack_admin_site
        return MicSessionAdmin(MicSession, showstack_admin_site)

    def _formset_class(self):
        inline = next(
            i for i in self._model_admin().get_inline_instances(
                self._request(), self.session)
            if i.model is MicAssignment)
        return inline.get_formset(self._request(), self.session)

    def _request(self):
        from django.test import RequestFactory
        request = RequestFactory().post('/admin/')
        request.user = self.user
        request.current_project = self.project
        request.session = {}
        return request

    def _payload(self, extra):
        """Management-form data resubmitting every existing row unchanged,
        plus ``extra`` blank rows (what "Add another" posts)."""
        existing = list(self.session.mic_assignments.order_by('rf_number'))
        prefix = 'mic_assignments'
        data = {
            '%s-TOTAL_FORMS' % prefix: str(len(existing) + extra),
            '%s-INITIAL_FORMS' % prefix: str(len(existing)),
            '%s-MIN_NUM_FORMS' % prefix: '0',
            '%s-MAX_NUM_FORMS' % prefix: '1000',
        }
        for i, assignment in enumerate(existing):
            data['%s-%d-id' % (prefix, i)] = str(assignment.id)
            data['%s-%d-session' % (prefix, i)] = str(self.session.id)
        for i in range(len(existing), len(existing) + extra):
            data['%s-%d-id' % (prefix, i)] = ''
            data['%s-%d-session' % (prefix, i)] = str(self.session.id)
        return data


class _ParentForm:
    """Stands in for the admin's parent ModelForm; ``save_formset`` reads only
    ``form.instance``."""

    def __init__(self, instance):
        self.instance = instance


class _SavedFormSet:
    """Stands in for an inline formset that has already saved; ``save_formset``
    reads only ``formset.model`` after delegating to ``super()``."""

    def __init__(self, model):
        self.model = model

    def save(self, commit=True):
        return []


# ---------------------------------------------------------------------------
# 3. The gap fillers -- the paths that used to manufacture a duplicate
# ---------------------------------------------------------------------------

class SetupChannelsFillsGapsTests(_Fixture, TestCase):
    """``Amp.setup_channels()`` derived the numbers to create from a row
    count: ``current_count + 1 .. target_count``. With a hole in the existing
    numbers that range starts past a number already taken, so the "missing"
    channel it created was a second copy of an existing one -- silently before
    ``unique_amp_channel_number``, an IntegrityError after it."""

    def _hole(self, *channel_numbers):
        self.amp.channels.filter(
            channel_number__in=channel_numbers).delete()

    def test_switching_amp_model_over_a_hole_does_not_duplicate(self):
        """The live path: delete channel 2, then change the amp's model. Both
        models have 4 channels, so the old count-based range was 4..4 -- and
        channel 4 already existed."""
        self._hole(2)
        self.assertEqual(self.channel_numbers(), [1, 3, 4])

        self.amp.amp_model = self.other_model
        self.amp.save()

        self.assertEqual(self.channel_numbers(), [1, 2, 3, 4])

    def test_setup_channels_fills_the_hole_itself(self):
        self._hole(3)
        self.amp.setup_channels()
        self.assertEqual(self.channel_numbers(), [1, 2, 3, 4])

    def test_two_holes_are_both_filled(self):
        self._hole(1, 3)
        self.amp.setup_channels()
        self.assertEqual(self.channel_numbers(), [1, 2, 3, 4])

    def test_a_full_channel_list_is_left_alone(self):
        before = {c.id: c.channel_number for c in self.amp.channels.all()}
        self.amp.setup_channels()
        after = {c.id: c.channel_number for c in self.amp.channels.all()}
        self.assertEqual(before, after, 'existing rows must not be replaced')

    def test_the_existing_patch_survives_a_gap_fill(self):
        channel = self.amp.channels.get(channel_number=4)
        channel.channel_name = 'Main L LF'
        channel.save(update_fields=['channel_name'])
        self._hole(2)
        self.amp.setup_channels()
        self.assertEqual(
            self.amp.channels.get(channel_number=4).channel_name,
            'Main L LF')

    def test_channels_above_a_smaller_model_are_trimmed(self):
        self.amp.amp_model = self._small_model()
        self.amp.save()
        self.assertEqual(self.channel_numbers(), [1, 2])

    def test_trimming_then_growing_again_does_not_duplicate(self):
        """4 -> 2 -> 4. The trim leaves 1,2; growing back has to add 3 and 4
        and must not re-add 1 and 2."""
        self.amp.amp_model = self._small_model()
        self.amp.save()
        self.amp.amp_model = self.amp_model
        self.amp.save()
        self.assertEqual(self.channel_numbers(), [1, 2, 3, 4])

    def test_trimming_over_a_hole_fills_it_and_trims(self):
        """1,2,4 down to a 2-channel model: 3 is created, 4 removed."""
        self._hole(3)
        self.amp.amp_model = self._small_model()
        self.amp.save()
        self.assertEqual(self.channel_numbers(), [1, 2])

    def test_an_amp_with_no_model_keeps_its_channels(self):
        self.amp.amp_model = None
        self.amp.save()
        self.assertEqual(self.channel_numbers(), [1, 2, 3, 4])

    def _small_model(self):
        return AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA2Xi', channel_count=2,
            nl4_connector_count=1, nl8_connector_count=0,
            cacom_output_count=0)


class CreateMicAssignmentsFillsGapsTests(_Fixture, TestCase):
    """``MicSession.create_mic_assignments()`` had the same count-based bug as
    ``setup_channels``, reached from ``MicSessionAdmin.save_model`` whenever
    ``num_mics`` changes."""

    def test_raising_num_mics_over_a_hole_does_not_duplicate(self):
        self.hole_in_rf(2)
        self.assertEqual(self.rf_numbers(), [1, 3, 4, 5])

        self.session.num_mics = 6
        self.session.save(update_fields=['num_mics'])
        self.session.create_mic_assignments()

        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5, 6])

    def test_create_fills_the_hole_without_growing(self):
        self.hole_in_rf(3)
        self.session.create_mic_assignments()
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    def test_lowering_num_mics_trims_from_the_top(self):
        self.session.num_mics = 3
        self.session.save(update_fields=['num_mics'])
        self.session.create_mic_assignments()
        self.assertEqual(self.rf_numbers(), [1, 2, 3])

    def test_a_full_session_is_left_alone(self):
        before = {a.id: a.rf_number
                  for a in self.session.mic_assignments.all()}
        self.session.create_mic_assignments()
        after = {a.id: a.rf_number
                 for a in self.session.mic_assignments.all()}
        self.assertEqual(before, after)

    def test_trimming_then_growing_again_does_not_duplicate(self):
        for num_mics in (3, 5):
            self.session.num_mics = num_mics
            self.session.save(update_fields=['num_mics'])
            self.session.create_mic_assignments()
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    def test_the_admin_save_model_path_does_not_duplicate(self):
        """``MicSessionAdmin.save_model`` calls create_mic_assignments on any
        num_mics change. Over a hole, that used to write a duplicate."""
        self.hole_in_rf(2)

        from planner.admin import MicSessionAdmin
        from planner.admin_site import showstack_admin_site
        from django.test import RequestFactory

        request = RequestFactory().post('/admin/')
        request.user = self.user
        request.current_project = self.project
        request.session = {}

        self.session.num_mics = 6
        MicSessionAdmin(MicSession, showstack_admin_site).save_model(
            request, self.session, _ChangedForm(['num_mics']), change=True)

        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5, 6])


class _ChangedForm:
    """Stands in for the admin's ModelForm; ``save_model`` reads only
    ``form.changed_data``."""

    def __init__(self, changed_data):
        self.changed_data = changed_data


# ---------------------------------------------------------------------------
# 4. Duplication -- scaffold, then copy
# ---------------------------------------------------------------------------

class DuplicationStaysUniqueTests(_Fixture, TestCase):
    """Both copy paths delete the children the parent's ``save()`` scaffolded
    before copying the source's rows in. ``test_duplicate_child_rows`` pins
    the counts; these pin that the constraints hold while it happens, which is
    the part that now fails loudly instead of silently."""

    def test_project_duplicate_leaves_unique_channel_numbers(self):
        copy = self.project.duplicate(new_name='Copy')
        copied_amp = Amp.objects.get(project=copy)
        self.assertEqual(self.channel_numbers(copied_amp), [1, 2, 3, 4])

    def test_project_duplicate_leaves_unique_rf_numbers(self):
        copy = self.project.duplicate(new_name='Copy')
        copied = MicSession.objects.get(day__project=copy)
        self.assertEqual(self.rf_numbers(copied), [1, 2, 3, 4, 5])

    def test_project_duplicate_twice_over_stays_unique(self):
        """A copy of a copy. If the first one came out doubled, the second
        would double again -- the shape issue #100 produced."""
        first = self.project.duplicate(new_name='Copy')
        second = first.duplicate(new_name='Copy of Copy')
        self.assertEqual(
            self.channel_numbers(Amp.objects.get(project=second)),
            [1, 2, 3, 4])
        self.assertEqual(
            self.rf_numbers(MicSession.objects.get(day__project=second)),
            [1, 2, 3, 4, 5])

    def test_duplicate_to_session_leaves_unique_rf_numbers(self):
        target = MicSession.objects.create(
            day=self.day, name='Afternoon', num_mics=5, order=1)
        with numbering_held():
            target.mic_assignments.all().delete()
        self.session.duplicate_to_session(target)
        self.assertEqual(self.rf_numbers(target), [1, 2, 3, 4, 5])

    def test_the_duplicate_session_endpoint_leaves_unique_rf_numbers(self):
        """The view an engineer actually clicks, scaffold-delete included."""
        client = Client()
        client.force_login(self.user)
        s = client.session
        s['current_project_id'] = self.project.id
        s.save()

        response = client.post(
            reverse('planner:duplicate_session'),
            data=json.dumps({'source_session_id': self.session.id,
                             'target_session_name': 'Afternoon'}),
            content_type='application/json')
        payload = response.json()
        self.assertTrue(payload.get('success'), payload)

        copied = MicSession.objects.get(id=payload['session_id'])
        self.assertEqual(self.rf_numbers(copied), [1, 2, 3, 4, 5])

    def test_duplicating_a_gapped_session_still_lands_unique(self):
        """The source need not be tidy. A session sitting on 2,4,5 copies to
        2,4,5 -- distinct, which is all the constraint asks."""
        self.keep_only_rf([2, 4, 5])

        target = MicSession.objects.create(
            day=self.day, name='Afternoon', num_mics=5, order=1)
        with numbering_held():
            target.mic_assignments.all().delete()
        self.session.duplicate_to_session(target)
        self.assertEqual(self.rf_numbers(target), [2, 4, 5])


# ---------------------------------------------------------------------------
# 5. Drag-to-reorder -- must not touch these columns at all
# ---------------------------------------------------------------------------

class ReorderDoesNotRenumberTests(_Fixture, TestCase):
    """``mic_assignment_reorder`` moves presenters between rows and
    ``amp_reorder`` moves ``Amp.sort_order``. Neither may write the numbers
    the constraints cover -- an RF number is a transmitter and a channel
    number is the amp's own output. Pinned here because "drag to reorder" is
    exactly the feature someone would later implement by swapping numbers."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        s = self.client.session
        s['current_project_id'] = self.project.id
        s.save()

        self.presenters = {}
        for assignment in self.session.mic_assignments.order_by('rf_number'):
            presenter = Presenter.objects.create(
                project=self.project,
                name='Presenter %d' % assignment.rf_number)
            PresenterSlot.objects.create(
                assignment=assignment, presenter=presenter, order=0,
                is_active=True)
            self.presenters[assignment.rf_number] = presenter.name

    def _reorder(self, **payload):
        response = self.client.post(
            reverse('planner:mic_assignment_reorder'),
            data=json.dumps(payload), content_type='application/json')
        body = response.json()
        self.assertTrue(body.get('success'), body)
        return body

    def _assignment(self, rf_number):
        return self.session.mic_assignments.get(rf_number=rf_number)

    def _presenter_at(self, rf_number):
        slot = self._assignment(rf_number).presenter_slots.get()
        return slot.presenter.name if slot.presenter else None

    def test_a_swap_leaves_every_rf_number_where_it_was(self):
        self._reorder(action='swap', source_id=self._assignment(1).id,
                      target_id=self._assignment(4).id)
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    def test_a_swap_moves_the_presenters_instead(self):
        self._reorder(action='swap', source_id=self._assignment(1).id,
                      target_id=self._assignment(4).id)
        self.assertEqual(self._presenter_at(1), self.presenters[4])
        self.assertEqual(self._presenter_at(4), self.presenters[1])

    def test_a_move_leaves_every_rf_number_where_it_was(self):
        self._reorder(action='move', source_id=self._assignment(5).id,
                      target_id=self._assignment(1).id, position='above')
        self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    def test_a_move_rotates_the_presenters_instead(self):
        self._reorder(action='move', source_id=self._assignment(5).id,
                      target_id=self._assignment(1).id, position='above')
        self.assertEqual(self._presenter_at(1), self.presenters[5])

    def test_repeated_reorders_never_touch_the_numbering(self):
        for rf in (2, 3, 4, 5):
            self._reorder(action='swap', source_id=self._assignment(1).id,
                          target_id=self._assignment(rf).id)
            self.assertEqual(self.rf_numbers(), [1, 2, 3, 4, 5])

    def test_amp_reorder_leaves_every_channel_number_where_it_was(self):
        """``amp_reorder`` calls a full ``Amp.save()``, which re-enters
        ``setup_channels()`` if the model looks changed. It must not."""
        second = Amp.objects.create(
            project=self.project, location=self.amp_location,
            name='SL LA12X #2', amp_model=self.amp_model)

        response = self.client.post(
            reverse('planner:amp_reorder'),
            data=json.dumps({'amp_id': second.id, 'direction': 'up'}),
            content_type='application/json')
        self.assertTrue(response.json().get('success'), response.json())

        self.assertEqual(self.channel_numbers(self.amp), [1, 2, 3, 4])
        self.assertEqual(self.channel_numbers(second), [1, 2, 3, 4])

    def test_amp_reorder_moves_sort_order_not_channel_numbers(self):
        second = Amp.objects.create(
            project=self.project, location=self.amp_location,
            name='SL LA12X #2', amp_model=self.amp_model)
        before = (self.amp.sort_order, second.sort_order)

        self.client.post(
            reverse('planner:amp_reorder'),
            data=json.dumps({'amp_id': second.id, 'direction': 'up'}),
            content_type='application/json')

        self.amp.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((self.amp.sort_order, second.sort_order),
                         (before[1], before[0]))


class InlineChannelUpdateCannotRenumberTests(_Fixture, TestCase):
    """``amp_channel_inline_update`` is the rack page's per-cell save.
    ``channel_number`` is deliberately absent from its allowlist; if it were
    added, an engineer typing into the rack view could collide two channels."""

    def test_channel_number_is_not_inline_editable(self):
        from planner.views import _INLINE_CHANNEL_FIELDS
        self.assertNotIn('channel_number', _INLINE_CHANNEL_FIELDS)

    def test_the_endpoint_refuses_a_channel_number_write(self):
        client = Client()
        client.force_login(self.user)
        s = client.session
        s['current_project_id'] = self.project.id
        s.save()

        channel = self.amp.channels.get(channel_number=4)
        response = client.post(
            reverse('planner:amp_channel_inline_update', args=[channel.id]),
            data={'field': 'channel_number', 'value': '1'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.channel_numbers(), [1, 2, 3, 4])


# ---------------------------------------------------------------------------
# 6. The migration's pre-flight check
# ---------------------------------------------------------------------------

class MigrationGuardTests(_Fixture, TestCase):
    """``AddConstraint`` over a duplicate raises a bare ``UniqueViolation``
    naming an index, which tells an operator nothing. The guard has to abort
    with the cleanup commands spelled out instead.

    ``global_apps`` stands in for the migration's historical registry: the
    guard only calls ``apps.get_model``, and the real models are a superset.
    The suite runs with ``MIGRATION_MODULES`` disabled, so the migration never
    executes here -- this is the only coverage it gets.
    """

    def setUp(self):
        super().setUp()
        module = guard_module()
        self.check = module.check_for_duplicates
        self.reverse = module.noop_reverse

    def test_a_clean_database_passes(self):
        self.check(global_apps, None)  # must not raise

    def test_an_empty_database_passes(self):
        Project.objects.all().delete()
        self.check(global_apps, None)

    def test_the_reverse_is_a_no_op(self):
        self.assertIsNone(self.reverse(global_apps, None))

    def test_the_guard_runs_before_the_constraints_are_added(self):
        """Operation order is the whole point -- a RunPython that ran after
        AddConstraint would never be reached on a dirty database."""
        operations = guard_module().Migration.operations
        self.assertEqual(type(operations[0]).__name__, 'RunPython')
        self.assertEqual(
            [type(op).__name__ for op in operations[1:]],
            ['AddConstraint', 'AddConstraint'])

    def test_the_migration_adds_exactly_the_constraints_the_models_declare(self):
        """A rename on one side and not the other would leave the constraint
        unenforced in production while the suite kept passing, because the
        test database is built from model state, not from migrations."""
        from_migration = {
            op.constraint.name
            for op in guard_module().Migration.operations
            if type(op).__name__ == 'AddConstraint'
        }
        self.assertEqual(
            from_migration,
            {'unique_amp_channel_number', 'unique_session_rf_number'})


class MigrationGuardOnDirtyDataTests(TransactionTestCase):
    """The guard's message, against the data it exists for.

    The constraints come off for the fixture because a database still holding
    issue #100's duplicates is by definition one where they were never added.
    ``TransactionTestCase`` for the same reason as
    ``RenumberRepairsLegacyDuplicatesTests``: the drop rebuilds the table on
    SQLite.
    """

    def setUp(self):
        self.check = guard_module().check_for_duplicates
        self.user = get_user_model().objects.create_superuser(
            username='dirty_guard', email='d@example.com', password='x')
        self.project = Project.objects.create(name='Dirty Show',
                                              owner=self.user)

    def _duplicated_amp(self):
        location = AmpLocation.objects.create(project=self.project, name='SL')
        amp_model = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA12X', channel_count=4,
            nl4_connector_count=2, nl8_connector_count=1,
            cacom_output_count=1)
        amp = Amp.objects.create(project=self.project, location=location,
                                 name='SL LA12X #1', amp_model=amp_model)
        for channel in list(amp.channels.all()):
            AmpChannel.objects.create(amp=amp,
                                      channel_number=channel.channel_number)
        return amp

    def _duplicated_session(self):
        day = ShowDay.objects.create(project=self.project,
                                     date=date(2026, 10, 8), name='Day 1',
                                     order=0)
        session = MicSession.objects.create(day=day, name='Keynote',
                                            num_mics=3, order=0)
        for assignment in list(session.mic_assignments.all()):
            MicAssignment.objects.create(session=session,
                                         rf_number=assignment.rf_number)
        return session

    def _message_for(self, build):
        """Build dirty data, capture the guard's complaint, clean up again.

        The rows have to go before the constraints come back on, or the
        re-add at the end of the block fails -- which is itself the point
        being made, just not in this test.
        """
        with legacy_duplicate_schema():
            built = build()
            with self.assertRaises(RuntimeError) as caught:
                self.check(global_apps, None)
            message = str(caught.exception)
            self.project.delete()
        return built, message

    def test_duplicate_amp_channels_abort_the_migration(self):
        _, message = self._message_for(self._duplicated_amp)
        self.assertIn('AmpChannel rows share a channel_number', message)
        self.assertIn('report_duplicate_amp_channels', message)
        self.assertIn('cleanup_duplicate_amp_channels', message)
        self.assertIn('--apply', message)

    def test_duplicate_rf_numbers_abort_the_migration(self):
        _, message = self._message_for(self._duplicated_session)
        self.assertIn('MicAssignment rows share an rf_number', message)
        self.assertIn('report_duplicate_mic_assignments', message)
        self.assertIn('cleanup_duplicate_mic_assignments', message)

    def test_the_message_names_the_offending_rows(self):
        """An operator has to be able to find them without writing SQL."""
        session, message = self._message_for(self._duplicated_session)
        self.assertIn('session=%d' % session.id, message)
        self.assertIn('rf_number=1', message)
        self.assertIn('(2 rows)', message)

    def test_the_message_mentions_issue_100_and_the_backup(self):
        _, message = self._message_for(self._duplicated_session)
        self.assertIn('issue #100', message)
        self.assertIn('backup', message)

    def test_both_problems_are_reported_together(self):
        """Not one, a cleanup, and then the other on the next attempt."""
        def build():
            self._duplicated_amp()
            return self._duplicated_session()

        _, message = self._message_for(build)
        self.assertIn('AmpChannel rows share a channel_number', message)
        self.assertIn('MicAssignment rows share an rf_number', message)

    def test_the_cleanup_commands_make_the_guard_pass(self):
        """End to end: the exact remedy the message prescribes clears it, and
        the constraints can then be added -- which is what exiting the block
        does, so a leftover duplicate would fail this test."""
        with legacy_duplicate_schema():
            self._duplicated_amp()
            self._duplicated_session()
            with self.assertRaises(RuntimeError):
                self.check(global_apps, None)

            call_command('cleanup_duplicate_amp_channels', apply=True,
                         verbosity=0)
            call_command('cleanup_duplicate_mic_assignments', apply=True,
                         verbosity=0)

            self.check(global_apps, None)  # must not raise
