"""Tests for the I/O device signal-name combobox suggestions.

The device input/output inlines render one free-text ``signal_name`` field
backed by a datalist of the current project's console channels. A bare source
name is ambiguous on a two-console show, so each suggestion now carries where
it came from ("FOH PM7 · Ch 3 · Kick") while still inserting only the name.

Under test: planner.forms._device_input_suggestions and
planner.forms._device_output_suggestions.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from planner.forms import (
    _device_input_suggestions,
    _device_output_suggestions,
)
from planner.models import (
    Console,
    ConsoleAuxOutput,
    ConsoleInput,
    ConsoleMatrixOutput,
    ConsoleStereoOutput,
    Project,
)

User = get_user_model()


class DeviceInputSuggestionTests(TestCase):
    """Input suggestions: labelled, console/channel ordered, name-only value."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='io-suggest-tester',
            email='io-suggest@example.com',
            password='test-password-123',
            is_staff=True,
        )
        cls.project = Project.objects.create(name='Suggest Show', owner=cls.user)
        cls.other_project = Project.objects.create(
            name='Other Show', owner=cls.user,
        )
        cls.foh = Console.objects.create(project=cls.project, name='FOH PM7')
        cls.mons = Console.objects.create(project=cls.project, name='Mons PM5')

    def test_label_carries_console_channel_and_source(self):
        ConsoleInput.objects.create(
            console=self.foh, input_ch='3', source='Kick',
        )
        self.assertEqual(
            _device_input_suggestions(self.project.id),
            [{'value': 'Kick', 'meta': 'FOH PM7 · Ch 3',
              'label': 'FOH PM7 · Ch 3 · Kick'}],
        )

    def test_same_source_on_two_consoles_is_listed_twice(self):
        ConsoleInput.objects.create(console=self.foh, input_ch='3', source='Kick')
        ConsoleInput.objects.create(console=self.mons, input_ch='7', source='Kick')
        labels = [s['label'] for s in _device_input_suggestions(self.project.id)]
        self.assertEqual(
            labels, ['FOH PM7 · Ch 3 · Kick', 'Mons PM5 · Ch 7 · Kick'],
        )
        # Either one still writes the bare name into signal_name.
        self.assertEqual(
            {s['value'] for s in _device_input_suggestions(self.project.id)},
            {'Kick'},
        )

    def test_identical_console_channel_and_source_collapses(self):
        ConsoleInput.objects.create(console=self.foh, input_ch='3', source='Kick')
        ConsoleInput.objects.create(console=self.foh, input_ch='3', source=' Kick ')
        self.assertEqual(len(_device_input_suggestions(self.project.id)), 1)

    def test_sorted_by_console_then_numeric_channel(self):
        ConsoleInput.objects.create(console=self.mons, input_ch='2', source='Snare')
        ConsoleInput.objects.create(console=self.foh, input_ch='10', source='Hat')
        ConsoleInput.objects.create(console=self.foh, input_ch='2', source='Tom')
        self.assertEqual(
            [s['label'] for s in _device_input_suggestions(self.project.id)],
            [
                'FOH PM7 · Ch 2 · Tom',      # 2 before 10, not "10" before "2"
                'FOH PM7 · Ch 10 · Hat',
                'Mons PM5 · Ch 2 · Snare',
            ],
        )

    def test_non_numeric_channel_sorts_last_without_crashing(self):
        """Issue #56: a typo'd input_ch must not break the whole datalist."""
        ConsoleInput.objects.create(console=self.foh, input_ch='oops', source='Spare')
        ConsoleInput.objects.create(console=self.foh, input_ch='1', source='Kick')
        self.assertEqual(
            [s['label'] for s in _device_input_suggestions(self.project.id)],
            ['FOH PM7 · Ch 1 · Kick', 'FOH PM7 · Ch oops · Spare'],
        )

    def test_missing_channel_drops_that_part_of_the_label(self):
        ConsoleInput.objects.create(console=self.foh, input_ch='', source='Kick')
        self.assertEqual(
            _device_input_suggestions(self.project.id),
            [{'value': 'Kick', 'meta': 'FOH PM7', 'label': 'FOH PM7 · Kick'}],
        )

    def test_scoped_to_project(self):
        other_console = Console.objects.create(
            project=self.other_project, name='Elsewhere',
        )
        ConsoleInput.objects.create(
            console=other_console, input_ch='1', source='Leaked',
        )
        ConsoleInput.objects.create(console=self.foh, input_ch='1', source='Kick')
        self.assertEqual(
            [s['value'] for s in _device_input_suggestions(self.project.id)],
            ['Kick'],
        )

    def test_no_project_returns_empty(self):
        self.assertEqual(_device_input_suggestions(None), [])


class DeviceOutputSuggestionTests(TestCase):
    """Output suggestions: Aux / Mtx / St labels in console-inline order."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='io-out-tester',
            email='io-out@example.com',
            password='test-password-123',
            is_staff=True,
        )
        cls.project = Project.objects.create(name='Output Show', owner=cls.user)
        cls.foh = Console.objects.create(project=cls.project, name='FOH PM7')

    def test_aux_matrix_stereo_labels_and_order(self):
        ConsoleMatrixOutput.objects.create(
            console=self.foh, matrix_number='2', name='Lobby',
        )
        ConsoleStereoOutput.objects.create(
            console=self.foh, stereo_type='L', name='PA Left',
        )
        ConsoleAuxOutput.objects.create(
            console=self.foh, aux_number='6', name='Drum Fill',
        )
        self.assertEqual(
            [s['label'] for s in _device_output_suggestions(self.project.id)],
            [
                'FOH PM7 · Aux 6 · Drum Fill',
                'FOH PM7 · Mtx 2 · Lobby',
                'FOH PM7 · St L · PA Left',
            ],
        )

    def test_value_is_the_bare_output_name(self):
        ConsoleAuxOutput.objects.create(
            console=self.foh, aux_number='6', name='Drum Fill',
        )
        self.assertEqual(
            _device_output_suggestions(self.project.id),
            [{'value': 'Drum Fill', 'meta': 'FOH PM7 · Aux 6',
              'label': 'FOH PM7 · Aux 6 · Drum Fill'}],
        )

    def test_same_name_on_aux_and_matrix_is_listed_twice(self):
        ConsoleAuxOutput.objects.create(
            console=self.foh, aux_number='1', name='Broadcast',
        )
        ConsoleMatrixOutput.objects.create(
            console=self.foh, matrix_number='1', name='Broadcast',
        )
        self.assertEqual(
            [s['label'] for s in _device_output_suggestions(self.project.id)],
            ['FOH PM7 · Aux 1 · Broadcast', 'FOH PM7 · Mtx 1 · Broadcast'],
        )

    def test_numeric_aux_order(self):
        for number in ('10', '2'):
            ConsoleAuxOutput.objects.create(
                console=self.foh, aux_number=number, name='Mix %s' % number,
            )
        self.assertEqual(
            [s['value'] for s in _device_output_suggestions(self.project.id)],
            ['Mix 2', 'Mix 10'],
        )

    def test_no_project_returns_empty(self):
        self.assertEqual(_device_output_suggestions(None), [])
