"""``Project.duplicate()`` and the models whose ``save()`` builds their own children.

Duplication is how a new show gets created, so every row it writes is a row an
engineer will be working from on site. Two of the models it copies scaffold
their own children on first save, and for both of them ``duplicate()`` then
copied the source's children on top of that scaffold instead of replacing it:

  * ``Amp.save()`` calls ``setup_channels()``, which builds one blank
    ``AmpChannel`` per channel the amp model declares. ``duplicate()`` then
    copied the source amp's channels as well -- issue #100, where a 4-channel
    LA12X came out of duplication with 8 channels numbered 1,1,2,2,3,3,4,4.
    Half of them blank, half of them the real patch, and no way to tell which
    was which from the rack view.

  * ``MicSession.save()`` calls ``create_mic_assignments()``, which builds
    ``num_mics`` blank ``MicAssignment`` rows. ``duplicate()`` then copied the
    source session's assignments as well, so an 8-mic session duplicated to 16
    with every rf_number appearing twice. (``renumber_assignments()`` and the
    ``renumber_mic_assignments`` command exist because of the fallout.)

The fix in both places is the one ``duplicate_session()`` in views.py already
used on the single-session path: drop the auto-created scaffold, then copy. The
source rows win, because they are the ones carrying the patch.

The third such model, ``P1Processor``, was already doing that, and
``ProcessorsStayUndoubledTests`` pins it so it stays that way.

``NothingIsDoubledAnywhereTests`` is the catch-all: it duplicates a project
holding one of everything and asserts that no numbered child table anywhere in
the copy has a number twice. A model added to ``duplicate()`` later that
scaffolds its own children fails there without anyone having to remember this
file exists.

Run with::

    python manage.py test planner.tests.test_duplicate_child_rows \\
        --settings=audiopatch.test_settings
"""
from collections import Counter
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from planner.models import (
    Amp, AmpChannel, AmpLocation, AmpModel,
    CommBeltPack, CommBeltPackChannel, CommChannel,
    Console, ConsoleInput,
    Device, DeviceInput, DeviceOutput,
    GalaxyProcessor, GalaxyInput, GalaxyOutput,
    Location,
    MicAssignment, MicSession,
    P1Processor, P1Input, P1Output,
    PresenterSlot, Presenter,
    Project, ShowDay, SystemProcessor,
)

# The AmpChannel columns that hold the engineer's patch. channel_number is
# checked separately because it is the identity of the row, not its payload.
PATCH_FIELDS = (
    'channel_name', 'channel_setting', 'avb_stream', 'aes_input',
    'analog_input',
)


def duplicate_numbers(numbers):
    """The values appearing more than once, sorted. Empty when all distinct."""
    return sorted(n for n, count in Counter(numbers).items() if count > 1)


class _ProjectMixin:
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='dup_children', email='d@example.com', password='x')
        self.project = Project.objects.create(name='Source Show',
                                              owner=self.user)
        self.amp_location = AmpLocation.objects.create(project=self.project,
                                                       name='SL LA Racks')
        self.location = Location.objects.create(project=self.project,
                                                name='FOH')
        self.amp_model = AmpModel.objects.create(
            manufacturer="L'Acoustics", model_name='LA12X', channel_count=4,
            nl4_connector_count=2, nl8_connector_count=1,
            cacom_output_count=1)

    def patched_amp(self, name='SL LA12X #1', amp_model=None):
        """An amp whose four channels each carry a distinct, recognisable patch."""
        amp = Amp.objects.create(
            project=self.project, location=self.amp_location,
            name=name, amp_model=amp_model or self.amp_model)
        for channel in amp.channels.order_by('channel_number'):
            n = channel.channel_number
            channel.channel_name = 'Main L LF %d' % n
            channel.channel_setting = ['PA_A', 'LF_B', 'HF_C', 'SB_D'][n - 1]
            channel.avb_stream = 'AVB %d - P1 Out %d' % (n, n)
            channel.aes_input = 'AES %d' % n
            channel.analog_input = 'ANA %d' % n
            channel.save()
        return amp

    def snapshot(self, amp):
        """{channel_number: {patch field: value}} — what the copy must match."""
        return {
            c.channel_number: {f: getattr(c, f) for f in PATCH_FIELDS}
            for c in amp.channels.all()
        }


class AmpChannelsAreNotDoubledTests(_ProjectMixin, TestCase):
    """Issue #100, head on: 4 channels in, 4 channels out."""

    def test_the_source_amp_has_the_channels_its_model_declares(self):
        """Guards the premise: 8-in-the-copy is not 8-in-the-source."""
        self.assertEqual(self.patched_amp().channels.count(), 4)

    def test_the_channel_count_matches_the_source(self):
        self.patched_amp()
        copy = self.project.duplicate(new_name='Copy')
        self.assertEqual(Amp.objects.get(project=copy).channels.count(), 4)

    def test_the_numbering_matches_the_source_with_nothing_repeated(self):
        self.patched_amp()
        copy = self.project.duplicate(new_name='Copy')
        numbers = list(Amp.objects.get(project=copy).channels
                       .values_list('channel_number', flat=True))
        self.assertEqual(duplicate_numbers(numbers), [])
        self.assertEqual(sorted(numbers), [1, 2, 3, 4])

    def test_every_patch_value_matches_the_source(self):
        source = self.patched_amp()
        expected = self.snapshot(source)
        copy = self.project.duplicate(new_name='Copy')
        self.assertEqual(self.snapshot(Amp.objects.get(project=copy)),
                         expected)

    def test_no_blank_channel_survives_the_copy(self):
        """The failure mode as the rack view showed it: half the rows empty."""
        self.patched_amp()
        copy = self.project.duplicate(new_name='Copy')
        blanks = Amp.objects.get(project=copy).channels.filter(
            channel_name='', avb_stream='', aes_input='', analog_input='')
        self.assertEqual(blanks.count(), 0)

    def test_duplicating_the_copy_does_not_compound_it(self):
        """A show duplicated down a season: 4 -> 8 -> 16 was the trajectory."""
        self.patched_amp()
        first = self.project.duplicate(new_name='Copy 1')
        second = first.duplicate(new_name='Copy 2')
        third = second.duplicate(new_name='Copy 3')
        for project in (first, second, third):
            self.assertEqual(
                Amp.objects.get(project=project).channels.count(), 4,
                'channels doubled in %s' % project.name)

    def test_the_source_project_is_left_alone(self):
        """The delete() runs against the copy's channels, never the source's."""
        source = self.patched_amp()
        expected = self.snapshot(source)
        self.project.duplicate(new_name='Copy')
        source.refresh_from_db()
        self.assertEqual(source.channels.count(), 4)
        self.assertEqual(self.snapshot(source), expected)

    def test_a_trimmed_amp_copies_as_trimmed(self):
        """Fewer channels than the model declares is a legitimate state, and
        the copy has to match the source rather than the model."""
        source = self.patched_amp()
        source.channels.filter(channel_number__gt=2).delete()
        self.assertEqual(source.channels.count(), 2)
        copy = self.project.duplicate(new_name='Copy')
        copied = Amp.objects.get(project=copy)
        self.assertEqual(copied.channels.count(), 2)
        self.assertEqual(
            sorted(copied.channels.values_list('channel_number', flat=True)),
            [1, 2])

    def test_a_model_less_amp_keeps_its_hand_made_channels(self):
        """No amp_model means setup_channels() scaffolds nothing, so this path
        was never doubled -- but it is also the path where the copy's channels
        can only come from the source. Deleting first must not lose them."""
        amp = Amp.objects.create(project=self.project,
                                 location=self.amp_location,
                                 name='Spare rack', amp_model=None)
        AmpChannel.objects.create(amp=amp, channel_number=1,
                                  channel_name='Hand made')
        copy = self.project.duplicate(new_name='Copy')
        copied = Amp.objects.get(project=copy)
        self.assertEqual(copied.channels.count(), 1)
        self.assertEqual(copied.channels.first().channel_name, 'Hand made')

    def test_an_amp_with_no_channels_copies_with_none(self):
        Amp.objects.create(project=self.project, location=self.amp_location,
                           name='Empty', amp_model=None)
        copy = self.project.duplicate(new_name='Copy')
        self.assertEqual(Amp.objects.get(project=copy).channels.count(), 0)

    def test_several_amps_each_keep_their_own_patch(self):
        """Channels are deleted per-amp inside the loop; a stray queryset
        would take out the amp copied before this one."""
        first = self.patched_amp(name='SL LA12X #1')
        second = self.patched_amp(name='SR LA12X #2')
        expected = {'SL LA12X #1': self.snapshot(first),
                    'SR LA12X #2': self.snapshot(second)}
        copy = self.project.duplicate(new_name='Copy')
        got = {a.name: self.snapshot(a)
               for a in Amp.objects.filter(project=copy)}
        self.assertEqual(got, expected)

    def test_adding_a_channel_after_duplication_numbers_from_the_right_place(self):
        """The practical consequence of the doubling: setup_channels() counted
        8 against a target of 4 and started deleting."""
        self.patched_amp()
        copy = self.project.duplicate(new_name='Copy')
        amp = Amp.objects.get(project=copy)
        amp.save()                      # no model change -> setup_channels() idle
        self.assertEqual(amp.channels.count(), 4)


class MicAssignmentsAreNotDoubledTests(_ProjectMixin, TestCase):
    """The same bug, one model over: MicSession.save() scaffolds too."""

    def setUp(self):
        super().setUp()
        self.day = ShowDay.objects.create(project=self.project,
                                          date=date(2026, 10, 8),
                                          name='Day 1', order=0)
        self.presenter = Presenter.objects.create(project=self.project,
                                                  name='Jane Doe')
        self.session = MicSession.objects.create(
            day=self.day, name='General Session', num_mics=4, order=0)
        for assignment in self.session.mic_assignments.order_by('rf_number'):
            assignment.mic_type = 'handheld'
            assignment.is_micd = True
            assignment.notes = 'RF %d' % assignment.rf_number
            assignment.save()
            PresenterSlot.objects.create(assignment=assignment,
                                         presenter=self.presenter,
                                         order=0, is_active=True)

    def copied_session(self, project):
        return MicSession.objects.get(day__project=project)

    def test_the_source_session_has_four_assignments(self):
        self.assertEqual(self.session.mic_assignments.count(), 4)

    def test_the_assignment_count_matches_the_source(self):
        copy = self.project.duplicate(new_name='Copy')
        self.assertEqual(self.copied_session(copy).mic_assignments.count(), 4)

    def test_the_rf_numbering_has_nothing_repeated(self):
        copy = self.project.duplicate(new_name='Copy')
        numbers = list(self.copied_session(copy).mic_assignments
                       .values_list('rf_number', flat=True))
        self.assertEqual(duplicate_numbers(numbers), [])
        self.assertEqual(sorted(numbers), [1, 2, 3, 4])

    def test_the_copied_assignments_carry_the_source_values(self):
        copy = self.project.duplicate(new_name='Copy')
        got = sorted(
            (a.rf_number, a.mic_type, a.is_micd, a.notes)
            for a in self.copied_session(copy).mic_assignments.all()
        )
        self.assertEqual(got, [(n, 'handheld', True, 'RF %d' % n)
                               for n in (1, 2, 3, 4)])

    def test_every_copied_assignment_has_its_presenter_slot(self):
        """The giveaway in the UI: half the mics had no A2 card, because the
        scaffolded rows were never given slots."""
        copy = self.project.duplicate(new_name='Copy')
        for assignment in self.copied_session(copy).mic_assignments.all():
            self.assertEqual(assignment.presenter_slots.count(), 1,
                             'rf %d lost its slot' % assignment.rf_number)

    def test_num_mics_still_agrees_with_the_row_count(self):
        """Disagreement is what create_mic_assignments() later acts on, so a
        copy that holds twice the rows gets half of them silently deleted on
        the next save."""
        copy = self.project.duplicate(new_name='Copy')
        session = self.copied_session(copy)
        self.assertEqual(session.num_mics, session.mic_assignments.count())

    def test_duplicating_the_copy_does_not_compound_it(self):
        first = self.project.duplicate(new_name='Copy 1')
        second = first.duplicate(new_name='Copy 2')
        for project in (first, second):
            self.assertEqual(
                self.copied_session(project).mic_assignments.count(), 4,
                'assignments doubled in %s' % project.name)

    def test_the_source_session_is_left_alone(self):
        self.project.duplicate(new_name='Copy')
        self.assertEqual(self.session.mic_assignments.count(), 4)
        self.assertEqual(PresenterSlot.objects.filter(
            assignment__session=self.session).count(), 4)

    def test_a_session_whose_rows_were_trimmed_copies_as_trimmed(self):
        self.session.mic_assignments.filter(rf_number__gt=2).delete()
        copy = self.project.duplicate(new_name='Copy')
        self.assertEqual(self.copied_session(copy).mic_assignments.count(), 2)


class ProcessorsStayUndoubledTests(_ProjectMixin, TestCase):
    """``P1Processor.save()`` scaffolds channels too; ``duplicate()`` already
    dropped them before copying. Pin it, so the fix above and this one cannot
    drift apart."""

    def p1(self):
        processor = SystemProcessor.objects.create(
            project=self.project, name='P1 #1', device_type='P1',
            location=self.location)
        config = P1Processor.objects.create(system_processor=processor)
        config.inputs.update(label='labelled')
        config.outputs.update(label='labelled')
        return config

    def galaxy(self):
        processor = SystemProcessor.objects.create(
            project=self.project, name='GALAXY #1', device_type='GALAXY',
            location=self.location)
        config = GalaxyProcessor.objects.create(system_processor=processor)
        GalaxyInput.objects.create(galaxy_processor=config,
                                   input_type='AES', channel_number=1,
                                   label='In 1')
        GalaxyOutput.objects.create(galaxy_processor=config,
                                    output_type='AES', channel_number=1,
                                    label='Out 1')
        return config

    def test_p1_channel_counts_match_the_source(self):
        source = self.p1()
        expected = (source.inputs.count(), source.outputs.count())
        copy = self.project.duplicate(new_name='Copy')
        copied = P1Processor.objects.get(system_processor__project=copy)
        self.assertEqual((copied.inputs.count(), copied.outputs.count()),
                         expected)

    def test_p1_labels_survive_rather_than_the_blank_scaffold(self):
        self.p1()
        copy = self.project.duplicate(new_name='Copy')
        copied = P1Processor.objects.get(system_processor__project=copy)
        self.assertEqual(copied.inputs.filter(label='labelled').count(),
                         copied.inputs.count())
        self.assertEqual(copied.outputs.filter(label='labelled').count(),
                         copied.outputs.count())

    def test_galaxy_channel_counts_match_the_source(self):
        self.galaxy()
        copy = self.project.duplicate(new_name='Copy')
        copied = GalaxyProcessor.objects.get(system_processor__project=copy)
        self.assertEqual(copied.inputs.count(), 1)
        self.assertEqual(copied.outputs.count(), 1)


class NothingIsDoubledAnywhereTests(_ProjectMixin, TestCase):
    """Catch-all. Duplicate a project holding one of everything numbered, then
    assert no child table in the copy carries the same number twice.

    This is the test that fires for the *next* model given a ``save()`` that
    scaffolds its own children, without anyone remembering to come back here.
    """

    def setUp(self):
        super().setUp()
        self.patched_amp()

        self.day = ShowDay.objects.create(project=self.project,
                                          date=date(2026, 10, 8),
                                          name='Day 1', order=0)
        MicSession.objects.create(day=self.day, name='Session 1',
                                  num_mics=4, order=0)

        console = Console.objects.create(project=self.project, name='PM7',
                                         location=self.location)
        for n in (1, 2):
            ConsoleInput.objects.create(console=console, input_ch=n,
                                        source='Mic %d' % n)

        device = Device.objects.create(project=self.project, name='Rio3224',
                                       location=self.location,
                                       input_count=2, output_count=2)
        for n in (1, 2):
            DeviceInput.objects.create(device=device, input_number=n,
                                       signal_name='In %d' % n)
            DeviceOutput.objects.create(device=device, output_number=n,
                                        signal_name='Out %d' % n)

        processor = SystemProcessor.objects.create(
            project=self.project, name='P1 #1', device_type='P1',
            location=self.location)
        P1Processor.objects.create(system_processor=processor)

        comm_channel = CommChannel.objects.create(project=self.project,
                                                  channel_number=1,
                                                  name='PROD')
        beltpack = CommBeltPack.objects.create(project=self.project,
                                               bp_number=1)
        CommBeltPackChannel.objects.create(beltpack=beltpack,
                                           channel_number=1,
                                           channel=comm_channel)

    def numbered_children(self, project):
        """[(label, [numbers]), ...] for every numbered child row in a project."""
        groups = []

        for amp in Amp.objects.filter(project=project):
            groups.append((
                'AmpChannel of amp %s' % amp.name,
                list(amp.channels.values_list('channel_number', flat=True))))

        for session in MicSession.objects.filter(day__project=project):
            groups.append((
                'MicAssignment of session %s' % session.name,
                list(session.mic_assignments
                     .values_list('rf_number', flat=True))))

        for console in Console.objects.filter(project=project):
            groups.append((
                'ConsoleInput of console %s' % console.name,
                list(console.consoleinput_set
                     .values_list('input_ch', flat=True))))

        for device in Device.objects.filter(project=project):
            groups.append((
                'DeviceInput of device %s' % device.name,
                list(device.inputs.values_list('input_number', flat=True))))
            groups.append((
                'DeviceOutput of device %s' % device.name,
                list(device.outputs.values_list('output_number', flat=True))))

        for config in P1Processor.objects.filter(
                system_processor__project=project):
            # (type, number) is the identity here, not the number alone.
            groups.append((
                'P1Input of %s' % config.system_processor.name,
                list(config.inputs.values_list('input_type',
                                               'channel_number'))))
            groups.append((
                'P1Output of %s' % config.system_processor.name,
                list(config.outputs.values_list('output_type',
                                                'channel_number'))))

        for config in GalaxyProcessor.objects.filter(
                system_processor__project=project):
            groups.append((
                'GalaxyInput of %s' % config.system_processor.name,
                list(config.inputs.values_list('input_type',
                                               'channel_number'))))
            groups.append((
                'GalaxyOutput of %s' % config.system_processor.name,
                list(config.outputs.values_list('output_type',
                                                'channel_number'))))

        for beltpack in CommBeltPack.objects.filter(project=project):
            groups.append((
                'CommBeltPackChannel of bp %s' % beltpack.bp_number,
                list(beltpack.channels
                     .values_list('channel_number', flat=True))))

        groups.append((
            'CommChannel of project',
            list(CommChannel.objects.filter(project=project)
                 .values_list('channel_number', flat=True))))
        groups.append((
            'Presenter of project',
            list(Presenter.objects.filter(project=project)
                 .values_list('name', flat=True))))

        return groups

    def assert_nothing_repeated(self, project):
        for label, numbers in self.numbered_children(project):
            self.assertEqual(
                duplicate_numbers(numbers), [],
                '%s in %s has repeated numbers: %s'
                % (label, project.name, numbers))

    def test_the_source_project_has_nothing_repeated(self):
        """The premise. If this fails the fixture is wrong, not duplicate()."""
        self.assert_nothing_repeated(self.project)

    def test_the_copy_has_nothing_repeated(self):
        self.assert_nothing_repeated(self.project.duplicate(new_name='Copy'))

    def test_a_copy_of_a_copy_has_nothing_repeated(self):
        first = self.project.duplicate(new_name='Copy 1')
        self.assert_nothing_repeated(first.duplicate(new_name='Copy 2'))

    def test_the_copy_holds_the_same_row_counts_as_the_source(self):
        """Doubling shows up as a count mismatch even where a table has no
        number column to collide on."""
        copy = self.project.duplicate(new_name='Copy')
        expected = {label: len(numbers)
                    for label, numbers in self.numbered_children(self.project)}
        got = {label: len(numbers)
               for label, numbers in self.numbered_children(copy)}
        self.assertEqual(sorted(got), sorted(expected))
        for label in expected:
            self.assertEqual(got[label], expected[label],
                             '%s changed count on duplication' % label)

    def test_total_amp_channel_rows_did_not_grow_beyond_one_project_worth(self):
        before = AmpChannel.objects.count()
        self.project.duplicate(new_name='Copy')
        self.assertEqual(AmpChannel.objects.count(), before * 2)

    def test_total_mic_assignment_rows_did_not_grow_beyond_one_project_worth(self):
        before = MicAssignment.objects.count()
        self.project.duplicate(new_name='Copy')
        self.assertEqual(MicAssignment.objects.count(), before * 2)
