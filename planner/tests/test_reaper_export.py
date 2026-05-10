"""Tests for planner.utils.reaper_export.

Covers every assertion in the Plan 01-02 <behavior> block:
  - hex_to_peakcol: PEAKCOL packing formula and fallback for malformed input
  - _sanitize_name: NAME-token sanitization (Pitfall 8)
  - build_rpp / build_rtracktemplate: full RPP / RTrackTemplate string output
  - track_order_mode dispatch (custom / console / dante)
  - enabled-only filtering

Combines pure-function unit tests (SimpleTestCase, no DB) with
integration tests against real ORM-backed MultitrackSession + Track rows
(TestCase, in-memory SQLite from `manage.py test`'s test database).

The session-fixture tests touch:
  - Project (planner.Project)
  - Console (planner.Console)
  - ConsoleInput / ConsoleAuxOutput / ConsoleMatrixOutput / ConsoleStereoOutput
  - MultitrackSession + MultitrackTrack (the discriminator-based source pattern from Plan 01-01)
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from planner.models import (
    Console,
    ConsoleAuxOutput,
    ConsoleInput,
    ConsoleMatrixOutput,
    ConsoleStereoOutput,
    MultitrackSession,
    MultitrackTrack,
    Project,
)
from planner.utils.reaper_export import (
    PEAKCOL_NO_COLOR,
    YAMAHA_TO_HEX,
    _ordered_enabled_tracks,
    _sanitize_name,
    build_rpp,
    build_rtracktemplate,
    hex_to_peakcol,
)


# ──────────────────────────────────────────────────────────────────
# Pure-function tests (no DB)
# ──────────────────────────────────────────────────────────────────

class HexToPeakcolTests(SimpleTestCase):
    """PEAKCOL packing per Reaper's verified formula:
    PEAKCOL = 0x01000000 | (B << 16) | (G << 8) | R
    """

    def test_pure_red(self):
        # R=255, G=0, B=0 -> 0x01000000 | 255 = 16777471
        self.assertEqual(hex_to_peakcol('#FF0000'), 0x010000FF)
        self.assertEqual(hex_to_peakcol('#FF0000'), 16777471)

    def test_pure_green(self):
        # R=0, G=255, B=0 -> 0x01000000 | (255<<8) = 0x0100FF00 = 16842496.
        # (Plan 01-02 <behavior> block lists 16842240 as the decimal — that is
        # an arithmetic typo; the bit layout 0x0100FF00 is the source of truth.
        # 0x01000000 = 16777216, plus 0xFF00 = 65280, equals 16842496.)
        self.assertEqual(hex_to_peakcol('#00FF00'), 0x0100FF00)
        self.assertEqual(hex_to_peakcol('#00FF00'), 16842496)

    def test_pure_blue(self):
        # R=0, G=0, B=255 -> 0x01000000 | (255<<16) = 33488896
        self.assertEqual(hex_to_peakcol('#0000FF'), 0x01FF0000)
        self.assertEqual(hex_to_peakcol('#0000FF'), 33488896)

    def test_empty_string_falls_back_to_sentinel(self):
        self.assertEqual(hex_to_peakcol(''), 16576)
        self.assertEqual(hex_to_peakcol(''), PEAKCOL_NO_COLOR)

    def test_none_falls_back_to_sentinel(self):
        self.assertEqual(hex_to_peakcol(None), 16576)

    def test_short_hex_falls_back_to_sentinel(self):
        # Reaper uses RRGGBB only; '#FFF' (3-digit shorthand) is unsupported here.
        self.assertEqual(hex_to_peakcol('#FFF'), 16576)

    def test_non_hex_chars_fall_back_to_sentinel(self):
        # 'XX'/'YY'/'ZZ' are non-hex — int() raises ValueError, caller returns sentinel.
        self.assertEqual(hex_to_peakcol('#XXYYZZ'), 16576)

    def test_missing_hash_still_works(self):
        # lstrip('#') makes the leading '#' optional.
        self.assertEqual(hex_to_peakcol('FF0000'), 0x010000FF)

    def test_high_bit_always_set(self):
        # Every non-fallback return value must have the 0x01000000 bit on
        # so Reaper treats it as "custom color enabled."
        for hex_color in ('#FF0000', '#00FF00', '#0000FF', '#33CC33', '#9933FF', '#FFFFFF'):
            with self.subTest(hex_color=hex_color):
                self.assertTrue(
                    hex_to_peakcol(hex_color) & 0x01000000,
                    f'High bit not set for {hex_color}',
                )

    def test_white_packs_correctly(self):
        # FFFFFF -> 0x01FFFFFF
        self.assertEqual(hex_to_peakcol('#FFFFFF'), 0x01FFFFFF)


class SanitizeNameTests(SimpleTestCase):
    """NAME-token sanitization (RESEARCH Pitfall 8):
    Reaper's NAME accepts an unquoted single word OR a "..."-wrapped string
    with NO internal `"`. Engineers commonly type `Lead Vox "Frank" L`.
    Replace `"` with `'` so the wrapping quotes stay valid.
    """

    def test_double_quote_replaced_with_single(self):
        self.assertEqual(
            _sanitize_name('Lead Vox "Frank" L'),
            "Lead Vox 'Frank' L",
        )

    def test_empty_string_returns_untitled(self):
        self.assertEqual(_sanitize_name(''), '(untitled)')

    def test_none_returns_untitled(self):
        self.assertEqual(_sanitize_name(None), '(untitled)')

    def test_whitespace_only_returns_untitled(self):
        # All-whitespace strips to empty -> sentinel.
        self.assertEqual(_sanitize_name('   '), '(untitled)')

    def test_normal_label_passes_through(self):
        self.assertEqual(_sanitize_name('Kick In'), 'Kick In')


class YamahaToHexTests(SimpleTestCase):
    """The Yamaha CL/QL palette table — dormant in Phase 1, used by Phase 2/5."""

    def test_table_present_with_known_keys(self):
        # The table MUST exist at module level so Phase 2/5 can import it.
        self.assertIn('Red', YAMAHA_TO_HEX)
        self.assertIn('Off', YAMAHA_TO_HEX)
        self.assertIn('White', YAMAHA_TO_HEX)
        self.assertEqual(YAMAHA_TO_HEX['Red'], '#FF0000')
        # 'Off' and 'White' map to None so Reaper writes the no-color sentinel.
        self.assertIsNone(YAMAHA_TO_HEX['Off'])
        self.assertIsNone(YAMAHA_TO_HEX['White'])

    def test_yamaha_off_resolves_to_no_color_sentinel(self):
        # End-to-end: 'Off' -> None -> hex_to_peakcol(None) -> 16576.
        self.assertEqual(hex_to_peakcol(YAMAHA_TO_HEX['Off']), PEAKCOL_NO_COLOR)


# ──────────────────────────────────────────────────────────────────
# Integration tests with real ORM fixtures
# ──────────────────────────────────────────────────────────────────

User = get_user_model()


class _SessionFixtureMixin:
    """Shared fixture builder. Not a TestCase itself (no test methods)."""

    @classmethod
    def _build_user(cls):
        return User.objects.create_user(
            username='reaper-tester',
            email='tester@example.com',
            password='test-password-123',
        )

    @classmethod
    def _build_project(cls, user):
        return Project.objects.create(name='Reaper Test Show', owner=user)

    @classmethod
    def _build_console(cls, project):
        return Console.objects.create(project=project, name='Test CL5')

    @classmethod
    def _build_session(cls, project, console, *, mode='console', name='Main Mix'):
        return MultitrackSession.objects.create(
            project=project,
            console=console,
            name=name,
            target_daw='reaper',
            feed_source='console_dante',
            track_order_mode=mode,
        )


class BuildRppEmptyTests(_SessionFixtureMixin, TestCase):
    """Behavior: build_rpp on a session with 0 enabled tracks."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console)

    def test_starts_with_reaper_project_header(self):
        out = build_rpp(self.session)
        self.assertTrue(out.startswith('<REAPER_PROJECT'))

    def test_ends_with_closing_angle_bracket(self):
        out = build_rpp(self.session)
        # Trailing newline after '>' is acceptable; the CLOSE token must be there.
        self.assertTrue(out.rstrip().endswith('>'))

    def test_zero_track_blocks(self):
        out = build_rpp(self.session)
        self.assertEqual(out.count('<TRACK '), 0)

    def test_contains_required_project_tokens(self):
        out = build_rpp(self.session)
        for token in ('RIPPLE', 'AUTOXFADE', 'TEMPO', 'SAMPLERATE'):
            with self.subTest(token=token):
                self.assertIn(token, out)


class BuildRppThreeTrackTests(_SessionFixtureMixin, TestCase):
    """Behavior: build_rpp on a session with 3 enabled tracks."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console, mode='custom')

        # Three enabled input-sourced tracks with explicit color overrides.
        cls.inp1 = ConsoleInput.objects.create(
            console=console, dante_number='1', input_ch='1', source='Kick In',
        )
        cls.inp2 = ConsoleInput.objects.create(
            console=console, dante_number='2', input_ch='2', source='Kick Out',
        )
        cls.inp3 = ConsoleInput.objects.create(
            console=console, dante_number='3', input_ch='3', source='Snare',
        )

        MultitrackTrack.objects.create(
            session=cls.session, track_number=1,
            source_type='input', source_id=cls.inp1.id,
            color_override='#FF0000', enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=2,
            source_type='input', source_id=cls.inp2.id,
            color_override='#00FF00', enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=3,
            source_type='input', source_id=cls.inp3.id,
            enabled=True,  # no color override -> sentinel
        )

    def test_exactly_three_track_blocks(self):
        out = build_rpp(self.session)
        self.assertEqual(out.count('<TRACK '), 3)

    def test_exactly_three_name_tokens(self):
        out = build_rpp(self.session)
        self.assertEqual(out.count('NAME "'), 3)

    def test_exactly_three_mainsend_tokens(self):
        # Pitfall 6: missing MAINSEND silently mutes the track.
        out = build_rpp(self.session)
        self.assertEqual(out.count('MAINSEND 1 0'), 3)

    def test_exactly_three_trackid_tokens(self):
        out = build_rpp(self.session)
        self.assertEqual(out.count('TRACKID {'), 3)

    def test_track_names_present_in_output(self):
        out = build_rpp(self.session)
        for label in ('Kick In', 'Kick Out', 'Snare'):
            with self.subTest(label=label):
                self.assertIn(f'NAME "{label}"', out)

    def test_color_override_packs_into_peakcol(self):
        out = build_rpp(self.session)
        # Red track -> 0x010000FF = 16777471
        self.assertIn(f'PEAKCOL {0x010000FF}', out)
        # Green track -> 0x0100FF00 = 16842240
        self.assertIn(f'PEAKCOL {0x0100FF00}', out)
        # Uncolored track -> sentinel 16576
        self.assertIn(f'PEAKCOL {PEAKCOL_NO_COLOR}', out)

    def test_required_track_tokens_appear_per_block(self):
        out = build_rpp(self.session)
        for token in ('PEAKCOL', 'TRACKHEIGHT', 'NCHAN', 'MAINSEND'):
            with self.subTest(token=token):
                # Each token must appear at least once per track.
                self.assertGreaterEqual(out.count(token), 3)


class BuildRtracktemplateTests(_SessionFixtureMixin, TestCase):
    """Behavior: .RTrackTemplate is the per-track output without the
    <REAPER_PROJECT> wrapper."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console, mode='custom')

        inp = ConsoleInput.objects.create(
            console=console, dante_number='1', input_ch='1', source='Kick',
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=1,
            source_type='input', source_id=inp.id, enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=2,
            source_type='manual', source_id=None, label_override='Click',
            enabled=True,
        )

    def test_no_reaper_project_wrapper(self):
        out = build_rtracktemplate(self.session)
        self.assertNotIn('<REAPER_PROJECT', out)

    def test_starts_with_track_at_zero_indent(self):
        out = build_rtracktemplate(self.session)
        self.assertTrue(out.startswith('<TRACK '))

    def test_includes_each_track_block(self):
        out = build_rtracktemplate(self.session)
        self.assertEqual(out.count('<TRACK '), 2)
        self.assertIn('NAME "Kick"', out)
        self.assertIn('NAME "Click"', out)


class TrackOrderCustomTests(_SessionFixtureMixin, TestCase):
    """track_order_mode='custom' produces tracks in track_number 1..N order."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console, mode='custom')

        # Insert in scrambled order; the exporter must reorder by track_number.
        for tn, label in [(3, 'Charlie'), (1, 'Alpha'), (2, 'Bravo')]:
            MultitrackTrack.objects.create(
                session=cls.session, track_number=tn,
                source_type='manual', source_id=None,
                label_override=label, enabled=True,
            )

    def test_ordered_by_track_number_ascending(self):
        ordered = _ordered_enabled_tracks(self.session)
        self.assertEqual([t.track_number for t in ordered], [1, 2, 3])

    def test_build_rpp_outputs_in_custom_order(self):
        out = build_rpp(self.session)
        # The labels must appear in 1, 2, 3 order in the file.
        a = out.index('NAME "Alpha"')
        b = out.index('NAME "Bravo"')
        c = out.index('NAME "Charlie"')
        self.assertLess(a, b)
        self.assertLess(b, c)


class TrackOrderConsoleTests(_SessionFixtureMixin, TestCase):
    """track_order_mode='console' orders tracks by source-type priority
    (input < aux < matrix < stereo < manual), then by source channel
    number ascending. Manual tracks sort last."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console, mode='console')

        cls.inp_5 = ConsoleInput.objects.create(
            console=console, dante_number='5', input_ch='5', source='In5',
        )
        cls.inp_2 = ConsoleInput.objects.create(
            console=console, dante_number='2', input_ch='2', source='In2',
        )
        cls.aux_3 = ConsoleAuxOutput.objects.create(
            console=console, dante_number=33, aux_number='3', name='Aux3',
        )
        cls.mtx_1 = ConsoleMatrixOutput.objects.create(
            console=console, dante_number=41, matrix_number='1', name='Mtx1',
        )
        cls.st = ConsoleStereoOutput.objects.create(
            console=console, dante_number=51, stereo_type='L', name='Main L',
        )

        # Insert in deliberately scrambled order — exporter must apply the
        # console-mode ordering.
        MultitrackTrack.objects.create(
            session=cls.session, track_number=10,
            source_type='manual', source_id=None,
            label_override='Talkback', enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=11,
            source_type='stereo', source_id=cls.st.id, enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=12,
            source_type='matrix', source_id=cls.mtx_1.id, enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=13,
            source_type='aux', source_id=cls.aux_3.id, enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=14,
            source_type='input', source_id=cls.inp_5.id, enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=15,
            source_type='input', source_id=cls.inp_2.id, enabled=True,
        )

    def test_ordered_by_source_type_then_channel_number(self):
        ordered = _ordered_enabled_tracks(self.session)
        types_in_order = [t.source_type for t in ordered]
        # Expected: input, input, aux, matrix, stereo, manual.
        self.assertEqual(
            types_in_order,
            ['input', 'input', 'aux', 'matrix', 'stereo', 'manual'],
        )

    def test_inputs_sorted_by_channel_number_ascending(self):
        ordered = _ordered_enabled_tracks(self.session)
        # First input should be ch 2 (In2), then ch 5 (In5).
        input_tracks = [t for t in ordered if t.source_type == 'input']
        self.assertEqual([t.source_id for t in input_tracks], [self.inp_2.id, self.inp_5.id])

    def test_manual_tracks_sort_last(self):
        ordered = _ordered_enabled_tracks(self.session)
        self.assertEqual(ordered[-1].source_type, 'manual')


class TrackOrderDanteTests(_SessionFixtureMixin, TestCase):
    """track_order_mode='dante' orders by resolved_dante_number ascending;
    tracks with no Dante number sort after numbered tracks (by track_number);
    manual tracks always sort last."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console, mode='dante')

        # Three inputs with Dante numbers 7, 3, 11.
        cls.inp_7 = ConsoleInput.objects.create(
            console=console, dante_number='7', input_ch='1', source='D7',
        )
        cls.inp_3 = ConsoleInput.objects.create(
            console=console, dante_number='3', input_ch='2', source='D3',
        )
        cls.inp_11 = ConsoleInput.objects.create(
            console=console, dante_number='11', input_ch='3', source='D11',
        )
        # One input with NO Dante number.
        cls.inp_no_dante = ConsoleInput.objects.create(
            console=console, dante_number='', input_ch='99', source='NoDante',
        )

        for tn, src in [
            (1, cls.inp_7),
            (2, cls.inp_3),
            (3, cls.inp_11),
            (4, cls.inp_no_dante),
        ]:
            MultitrackTrack.objects.create(
                session=cls.session, track_number=tn,
                source_type='input', source_id=src.id, enabled=True,
            )
        # Manual track — must sort dead last.
        MultitrackTrack.objects.create(
            session=cls.session, track_number=5,
            source_type='manual', source_id=None,
            label_override='Click', enabled=True,
        )

    def test_dante_ordering_ascending_with_no_dante_then_manual_last(self):
        ordered = _ordered_enabled_tracks(self.session)
        labels_in_order = [t.resolved_label for t in ordered]
        # Expected: D3, D7, D11, NoDante, Click (manual last).
        self.assertEqual(labels_in_order, ['D3', 'D7', 'D11', 'NoDante', 'Click'])

    def test_manual_track_is_last(self):
        ordered = _ordered_enabled_tracks(self.session)
        self.assertEqual(ordered[-1].source_type, 'manual')


class DisabledTracksFilteredTests(_SessionFixtureMixin, TestCase):
    """Pitfall 8: disabled tracks must NOT appear in the output."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console, mode='custom')

        inp = ConsoleInput.objects.create(
            console=console, dante_number='1', input_ch='1', source='Used',
        )
        inp_disabled = ConsoleInput.objects.create(
            console=console, dante_number='2', input_ch='2', source='Skipped',
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=1,
            source_type='input', source_id=inp.id, enabled=True,
        )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=2,
            source_type='input', source_id=inp_disabled.id, enabled=False,
        )

    def test_only_enabled_track_in_ordered_list(self):
        ordered = _ordered_enabled_tracks(self.session)
        self.assertEqual(len(ordered), 1)
        self.assertEqual(ordered[0].resolved_label, 'Used')

    def test_disabled_track_label_not_in_rpp(self):
        out = build_rpp(self.session)
        self.assertIn('NAME "Used"', out)
        self.assertNotIn('NAME "Skipped"', out)

    def test_disabled_track_label_not_in_rtracktemplate(self):
        out = build_rtracktemplate(self.session)
        self.assertIn('NAME "Used"', out)
        self.assertNotIn('NAME "Skipped"', out)


class QuoteSanitizationInRppTests(_SessionFixtureMixin, TestCase):
    """End-to-end: a label containing `"` must reach the file as `'`,
    so the NAME token's wrapping quotes stay valid."""

    @classmethod
    def setUpTestData(cls):
        user = cls._build_user()
        project = cls._build_project(user)
        console = cls._build_console(project)
        cls.session = cls._build_session(project, console, mode='custom')
        MultitrackTrack.objects.create(
            session=cls.session, track_number=1,
            source_type='manual', source_id=None,
            label_override='Lead Vox "Frank" L',
            enabled=True,
        )

    def test_double_quotes_replaced(self):
        out = build_rpp(self.session)
        self.assertIn("NAME \"Lead Vox 'Frank' L\"", out)
        # And the raw double-quoted label MUST NOT appear (would break parser).
        self.assertNotIn('Lead Vox "Frank" L', out)
