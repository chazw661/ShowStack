"""The report and cleanup commands for issue #100's leftover AmpChannel rows.

``Project.duplicate()`` no longer writes duplicate channel rows (that fix and
its tests are in ``test_duplicate_child_rows.py``), but every project that was
duplicated before it still holds them. These two commands are how those rows
get found and then cleared:

  * ``report_duplicate_amp_channels`` — read-only,
  * ``cleanup_duplicate_amp_channels`` — dry-run unless given ``--apply``.

Both read their verdicts from ``planner/utils/amp_channel_dupes.py``, so the
tests here are mostly about that module's rules and about the two commands
agreeing with it. The rule that most needs pinning is the keep-rule for a
ONE-SIDED pair: the blank scaffold row is written *first* and therefore has the
**lower** id, so keeping the oldest row — the instinct that is right for most
duplicate cleanups, and what ``list_duplicate_presenters`` recommends for
presenters — would delete the engineer's patch and leave the blank.

The duplicates are built by hand here. Reproducing them through
``duplicate()`` is no longer possible, which is the point of the other file.

Run with::

    python manage.py test planner.tests.test_duplicate_amp_channel_cleanup \\
        --settings=audiopatch.test_settings
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from planner.models import Amp, AmpChannel, AmpLocation, AmpModel, Project
from planner.utils.amp_channel_dupes import (
    CONFLICTING, IDENTICAL, ONE_SIDED,
    classify, duplicate_groups, is_blank, judge, keeper_of, patch_of,
)

from planner.tests.legacy_duplicate_schema import (  # noqa: F401
    setUpModule, tearDownModule,
)


class _AmpMixin:
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='dupe_cleanup', email='c@example.com', password='x')
        self.project = Project.objects.create(name='Duplicated Show',
                                              owner=self.user)
        self.location = AmpLocation.objects.create(project=self.project,
                                                   name='SL LA Racks')
        self.amp_model = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA12X', channel_count=4,
            nl4_connector_count=2, nl8_connector_count=1,
            cacom_output_count=1)

    def clean_amp(self, name='SL LA12X #1'):
        """An amp as duplicate() now leaves it: four patched channels."""
        amp = Amp.objects.create(project=self.project, location=self.location,
                                 name=name, amp_model=self.amp_model)
        for channel in amp.channels.order_by('channel_number'):
            channel.channel_name = 'Main L LF %d' % channel.channel_number
            channel.avb_stream = 'AVB %d' % channel.channel_number
            channel.save()
        return amp

    def doubled_amp(self, name='SL LA12X #1'):
        """An amp as the *old* duplicate() left it: four blank scaffold rows
        written first (lower ids), then four patched copies on top."""
        amp = Amp.objects.create(project=self.project, location=self.location,
                                 name=name, amp_model=self.amp_model)
        # The scaffold Amp.save() just wrote is left exactly as it is: blank.
        for n in (1, 2, 3, 4):
            AmpChannel.objects.create(
                amp=amp, channel_number=n,
                channel_name='Main L LF %d' % n,
                channel_setting=['PA_A', 'LF_B', 'HF_C', 'SB_D'][n - 1],
                avb_stream='AVB %d' % n,
                aes_input='AES %d' % n,
                analog_input='ANA %d' % n)
        return amp

    def report(self, **kwargs):
        out = StringIO()
        call_command('report_duplicate_amp_channels', stdout=out,
                     no_color=True, **kwargs)
        return out.getvalue()

    def cleanup(self, **kwargs):
        out = StringIO()
        call_command('cleanup_duplicate_amp_channels', stdout=out,
                     no_color=True, **kwargs)
        return out.getvalue()


class VerdictTests(_AmpMixin, TestCase):
    """``planner/utils/amp_channel_dupes.py`` — the rules themselves."""

    def group(self, *patches):
        """Build one same-numbered group from (channel_name, avb_stream) pairs."""
        amp = Amp.objects.create(project=self.project, location=self.location,
                                 name='bench', amp_model=None)
        return [AmpChannel.objects.create(amp=amp, channel_number=1,
                                          channel_name=name, avb_stream=avb)
                for name, avb in patches]

    def test_same_values_are_identical(self):
        rows = self.group(('Main L', 'AVB 1'), ('Main L', 'AVB 1'))
        self.assertEqual(classify(rows), IDENTICAL)

    def test_two_blanks_are_identical(self):
        rows = self.group(('', ''), ('', ''))
        self.assertEqual(classify(rows), IDENTICAL)

    def test_one_patched_and_one_blank_is_one_sided(self):
        rows = self.group(('', ''), ('Main L', 'AVB 1'))
        self.assertEqual(classify(rows), ONE_SIDED)

    def test_two_different_patches_are_conflicting(self):
        rows = self.group(('Main L', 'AVB 1'), ('Main R', 'AVB 2'))
        self.assertEqual(classify(rows), CONFLICTING)

    def test_none_and_empty_string_do_not_count_as_a_disagreement(self):
        """``avb_stream`` is null=True and the rest are blank-only, so one row
        can read None where the other reads ''. Both mean "nothing patched"."""
        rows = self.group(('', None), ('', ''))
        self.assertEqual(classify(rows), IDENTICAL)
        self.assertTrue(all(is_blank(patch_of(r)) for r in rows))

    def test_whitespace_only_is_blank(self):
        rows = self.group(('   ', ''), ('', ''))
        self.assertEqual(classify(rows), IDENTICAL)

    def test_a_one_sided_pair_keeps_the_patched_row_not_the_older_one(self):
        """The rule this whole file exists for. The blank scaffold row has the
        LOWER id, so 'keep the oldest' would keep the blank."""
        rows = self.group(('', ''), ('Main L', 'AVB 1'))
        blank, patched = rows
        self.assertLess(blank.id, patched.id)
        keeper = keeper_of(rows, ONE_SIDED)
        self.assertEqual(keeper.id, patched.id)
        self.assertNotEqual(keeper.id, min(r.id for r in rows))

    def test_a_one_sided_pair_is_decided_the_same_way_round_the_other_way(self):
        """Row order within the group must not change the answer."""
        rows = self.group(('Main L', 'AVB 1'), ('', ''))
        patched, blank = rows
        self.assertEqual(keeper_of(rows, ONE_SIDED).id, patched.id)

    def test_an_identical_pair_keeps_the_lowest_id(self):
        rows = self.group(('Main L', 'AVB 1'), ('Main L', 'AVB 1'))
        self.assertEqual(keeper_of(rows, IDENTICAL).id,
                         min(r.id for r in rows))

    def test_a_conflicting_pair_keeps_nothing(self):
        rows = self.group(('Main L', 'AVB 1'), ('Main R', 'AVB 2'))
        self.assertIsNone(keeper_of(rows, CONFLICTING))

    def test_a_clean_amp_has_no_groups(self):
        groups, verdicts = judge(self.clean_amp())
        self.assertEqual(groups, {})
        self.assertEqual(verdicts, {})

    def test_a_doubled_amp_reports_every_number(self):
        groups, verdicts = judge(self.doubled_amp())
        self.assertEqual(sorted(groups), [1, 2, 3, 4])
        self.assertEqual(set(verdicts.values()), {ONE_SIDED})

    def test_groups_are_ordered_scaffold_first(self):
        amp = self.doubled_amp()
        for rows in duplicate_groups(amp).values():
            self.assertEqual([r.id for r in rows],
                             sorted(r.id for r in rows))


class ReportCommandTests(_AmpMixin, TestCase):
    """Requirement: amp id, name, channel count, duplicated numbers, and
    whether the pairs agree."""

    def test_a_clean_database_says_so(self):
        self.clean_amp()
        self.assertIn('No amps with duplicated channel numbers found',
                      self.report())

    def test_it_names_the_project_and_the_amp(self):
        amp = self.doubled_amp()
        out = self.report()
        self.assertIn('Project %d: Duplicated Show' % self.project.id, out)
        self.assertIn('amp id=%d' % amp.id, out)
        self.assertIn('SL LA12X #1', out)

    def test_it_prints_the_channel_count_against_the_model(self):
        self.doubled_amp()
        out = self.report()
        self.assertIn('channels=8', out)
        self.assertIn('model declares 4', out)

    def test_it_lists_the_duplicated_numbers(self):
        self.doubled_amp()
        self.assertIn('duplicated numbers=[1,2,3,4]', self.report())

    def test_it_counts_the_redundant_rows(self):
        self.doubled_amp()
        out = self.report()
        self.assertIn('redundant rows=4', out)
        self.assertIn('4 redundant AmpChannel row(s)', out)

    def test_it_says_whether_the_pairs_agree(self):
        self.doubled_amp()
        out = self.report()
        self.assertIn(ONE_SIDED, out)
        self.assertIn('ONE-SIDED=4', out)

    def test_it_flags_a_conflicting_pair_and_shows_both_sides(self):
        amp = self.doubled_amp()
        # Somebody patched the blank scaffold row for channel 2 as well.
        blank = amp.channels.filter(channel_number=2).order_by('id').first()
        blank.channel_name = 'Main R LF 2'
        blank.save()

        out = self.report()
        self.assertIn(CONFLICTING, out)
        self.assertIn('need a human', out)
        # Both values printed without having to ask for --show-values.
        self.assertIn('Main R LF 2', out)
        self.assertIn('Main L LF 2', out)

    def test_conflicting_only_hides_the_resolvable_amps(self):
        clean_dupes = self.doubled_amp(name='all one-sided')
        conflicted = self.doubled_amp(name='has a conflict')
        blank = conflicted.channels.filter(channel_number=1).order_by('id').first()
        blank.channel_name = 'Other'
        blank.save()

        out = self.report(conflicting_only=True)
        self.assertIn('has a conflict', out)
        self.assertNotIn('all one-sided', out)

    def test_show_values_prints_the_patch(self):
        self.doubled_amp()
        out = self.report(show_values=True)
        self.assertIn("channel_name='Main L LF 1'", out)
        self.assertIn('blank', out)
        self.assertIn('<- keep', out)

    def test_the_project_filter_restricts_it(self):
        self.doubled_amp()
        other = Project.objects.create(name='Other', owner=self.user)
        out = self.report(project=other.id)
        self.assertIn('No amps with duplicated channel numbers found', out)

    def test_it_splits_resolvable_from_manual(self):
        amp = self.doubled_amp()
        blank = amp.channels.filter(channel_number=3).order_by('id').first()
        blank.channel_name = 'Disagrees'
        blank.save()
        out = self.report()
        self.assertIn('3 of the 4 redundant row(s) are mechanically '
                      'resolvable; 1 sit', out)

    def test_it_writes_nothing(self):
        """Read-only is the whole contract of this command."""
        self.doubled_amp()
        before = list(AmpChannel.objects.order_by('id')
                      .values_list('id', 'channel_number', 'channel_name'))
        self.report(show_values=True)
        self.report(conflicting_only=True)
        self.assertEqual(
            list(AmpChannel.objects.order_by('id')
                 .values_list('id', 'channel_number', 'channel_name')),
            before)


class CleanupDryRunTests(_AmpMixin, TestCase):
    """Dry-run is the default, and it has to be a real one."""

    def test_the_default_run_writes_nothing(self):
        self.doubled_amp()
        before = set(AmpChannel.objects.values_list('id', flat=True))
        out = self.cleanup()
        self.assertIn('DRY RUN', out)
        self.assertEqual(set(AmpChannel.objects.values_list('id', flat=True)),
                         before)

    def test_it_says_which_rows_it_would_delete(self):
        amp = self.doubled_amp()
        out = self.cleanup()
        for number in (1, 2, 3, 4):
            rows = amp.channels.filter(channel_number=number).order_by('id')
            blank, patched = rows[0], rows[1]
            self.assertIn('keep id=%d' % patched.id, out)
            self.assertIn('id=%d' % blank.id, out)

    def test_the_dry_run_and_the_apply_agree_on_the_count(self):
        self.doubled_amp()
        dry = self.cleanup()
        self.assertIn('4 row(s) resolvable', dry)
        applied = self.cleanup(apply=True)
        self.assertIn('Deleted 4 redundant AmpChannel row(s)', applied)

    def test_a_clean_database_says_nothing_to_do(self):
        self.clean_amp()
        self.assertIn('Nothing to do', self.cleanup())


class CleanupApplyTests(_AmpMixin, TestCase):
    """What ``--apply`` actually leaves behind."""

    def test_it_leaves_one_row_per_channel_number(self):
        amp = self.doubled_amp()
        self.cleanup(apply=True)
        self.assertEqual(amp.channels.count(), 4)
        self.assertEqual(
            sorted(amp.channels.values_list('channel_number', flat=True)),
            [1, 2, 3, 4])

    def test_the_surviving_rows_are_the_patched_ones(self):
        amp = self.doubled_amp()
        expected = {
            c.channel_number: patch_of(c)
            for c in amp.channels.all() if not is_blank(patch_of(c))
        }
        self.cleanup(apply=True)
        self.assertEqual(
            {c.channel_number: patch_of(c) for c in amp.channels.all()},
            expected)

    def test_no_blank_row_survives(self):
        amp = self.doubled_amp()
        self.cleanup(apply=True)
        self.assertEqual(
            [c.id for c in amp.channels.all() if is_blank(patch_of(c))], [])

    def test_the_amp_then_reconciles_against_its_model_without_deleting(self):
        """The practical payoff: setup_channels() counted 8 against a target
        of 4 and started pruning. After cleanup the counts agree."""
        amp = self.doubled_amp()
        self.cleanup(apply=True)
        amp.refresh_from_db()
        amp.save()
        self.assertEqual(amp.channels.count(), 4)
        amp.amp_model = self.amp_model
        amp.save()
        self.assertEqual(amp.channels.count(), 4)

    def test_it_is_idempotent(self):
        self.doubled_amp()
        self.cleanup(apply=True)
        second = self.cleanup(apply=True)
        self.assertIn('Nothing to do', second)

    def test_it_leaves_a_clean_amp_alone(self):
        clean = self.clean_amp(name='already fine')
        self.doubled_amp(name='doubled')
        before = {c.id: patch_of(c) for c in clean.channels.all()}
        self.cleanup(apply=True)
        self.assertEqual({c.id: patch_of(c) for c in clean.channels.all()},
                         before)

    def test_it_skips_a_conflicting_group_and_clears_the_rest(self):
        amp = self.doubled_amp()
        blank = amp.channels.filter(channel_number=2).order_by('id').first()
        blank.channel_name = 'Main R LF 2'
        blank.save()

        out = self.cleanup(apply=True)
        self.assertIn('1 group(s) skipped as CONFLICTING', out)
        self.assertIn('Deleted 3 redundant', out)

        # Channel 2 still holds both rows; everything else is down to one.
        self.assertEqual(amp.channels.filter(channel_number=2).count(), 2)
        for number in (1, 3, 4):
            self.assertEqual(amp.channels.filter(channel_number=number).count(),
                             1)

    def test_a_conflicting_only_amp_loses_nothing(self):
        amp = self.doubled_amp()
        for channel in amp.channels.filter(channel_name=''):
            channel.channel_name = 'Disagrees %d' % channel.channel_number
            channel.save()
        before = set(AmpChannel.objects.values_list('id', flat=True))
        out = self.cleanup(apply=True)
        self.assertIn('Nothing deletable', out)
        self.assertEqual(set(AmpChannel.objects.values_list('id', flat=True)),
                         before)

    def test_the_project_filter_restricts_the_delete(self):
        self.doubled_amp(name='in scope')
        other = Project.objects.create(name='Other', owner=self.user)
        other_location = AmpLocation.objects.create(project=other,
                                                     name='Other racks')
        other_amp = Amp.objects.create(project=other, location=other_location,
                                       name='out of scope',
                                       amp_model=self.amp_model)
        for n in (1, 2, 3, 4):
            AmpChannel.objects.create(amp=other_amp, channel_number=n,
                                      channel_name='Keep %d' % n)
        self.assertEqual(other_amp.channels.count(), 8)

        self.cleanup(project=self.project.id, apply=True)
        self.assertEqual(other_amp.channels.count(), 8)
        self.assertEqual(
            Amp.objects.get(project=self.project, name='in scope')
            .channels.count(), 4)

    def test_the_amp_filter_restricts_the_delete(self):
        first = self.doubled_amp(name='amp one')
        second = self.doubled_amp(name='amp two')
        self.cleanup(amp=first.id, apply=True)
        self.assertEqual(first.channels.count(), 4)
        self.assertEqual(second.channels.count(), 8)

    def test_an_unknown_project_id_is_reported_not_ignored(self):
        self.doubled_amp()
        out = self.cleanup(project=999999, apply=True)
        self.assertIn('No project with id 999999', out)
        self.assertEqual(AmpChannel.objects.count(), 8)

    def test_a_triple_is_reduced_to_the_patched_row(self):
        """Duplicating a copy of a copy produced three rows per number."""
        amp = self.doubled_amp()
        for n in (1, 2, 3, 4):
            AmpChannel.objects.create(amp=amp, channel_number=n)
        self.assertEqual(amp.channels.count(), 12)
        self.cleanup(apply=True)
        self.assertEqual(amp.channels.count(), 4)
        self.assertEqual(
            [c.channel_name for c in amp.channels.order_by('channel_number')],
            ['Main L LF %d' % n for n in (1, 2, 3, 4)])

    def test_an_all_blank_pair_keeps_the_lowest_id(self):
        """IDENTICAL, not ONE-SIDED: nothing to prefer, so prefer the row
        other tables are likelier to already reference."""
        amp = Amp.objects.create(project=self.project, location=self.location,
                                 name='blank pair', amp_model=self.amp_model)
        for n in (1, 2, 3, 4):
            AmpChannel.objects.create(amp=amp, channel_number=n)
        keepers = {n: amp.channels.filter(channel_number=n)
                   .order_by('id').first().id for n in (1, 2, 3, 4)}
        out = self.cleanup(apply=True)
        self.assertIn(IDENTICAL, out)
        self.assertEqual(
            {c.channel_number: c.id for c in amp.channels.all()}, keepers)
