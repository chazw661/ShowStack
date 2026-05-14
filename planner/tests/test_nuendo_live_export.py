"""Tests for planner.utils.nuendo_live_export.

Phase 4 ships ONE automated assertion per CONTEXT.md D-09:
every ID attribute and every RuntimeID/ID int-value in the exported
.nlpr bytes is unique within the document. This directly verifies
NLP-06.

Bonus structural assertions (cheap, surface naturally) are added
under CONTEXT.md §"Test budget — one assertion":
  - output contains exactly `enabled_track_count` MAudioTrackEvent
    elements (NOT enabled + 1 — the seed must be removed per D-10).
  - every track has both name elements populated with the resolved
    label (outer MListNode/Name AND inner DeviceAttributes/Name/String,
    RESEARCH Pitfall 9 / NLP-03).

NLP-01 through NLP-05 (everything except uniqueness) ultimately
require opening the file in Nuendo Live 3 — that's HUMAN-UAT, not
a Python test.

Test uses a Python-generated minimal fake template at
`planner/tests/fixtures/nuendo_live_3_template_fake.nlpr` so the
suite is independent of Plan 04-03 (Charlie's hand-generated Nuendo
Live binary). The fake has every element shape build_nlpr's XPaths
need, just enough to exercise every helper.
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from lxml import etree

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
from planner.utils import nuendo_live_export as nle
from planner.utils.nuendo_live_export import build_nlpr

User = get_user_model()


FAKE_TEMPLATE = (
    Path(__file__).parent / 'fixtures'
    / 'nuendo_live_3_template_fake.nlpr'
)


class _SessionFixtureMixin:
    """Shared fixture builder. Not a TestCase (no test methods).

    Mirrors planner/tests/test_reaper_export.py:_SessionFixtureMixin but
    sets target_daw='nuendo_live' for semantic consistency. The exporter
    is target-agnostic (D-11) so the field value doesn't actually gate
    the build_nlpr call — it's just descriptive.
    """

    @classmethod
    def _build_user(cls):
        return User.objects.create_user(
            username='nuendo-tester',
            email='nuendo-tester@example.com',
            password='test-password-123',
        )

    @classmethod
    def _build_project(cls, user):
        return Project.objects.create(
            name='Nuendo Test Show', owner=user,
        )

    @classmethod
    def _build_console(cls, project):
        return Console.objects.create(
            project=project, name='Test CL5',
        )

    @classmethod
    def _build_session(cls, project, console, *, mode='console',
                       name='Main Mix'):
        return MultitrackSession.objects.create(
            project=project, console=console, name=name,
            target_daw='nuendo_live',
            feed_source='console_dante',
            track_order_mode=mode,
        )


class NuendoLiveExportIdUniquenessTests(_SessionFixtureMixin, TestCase):
    """D-09 / NLP-06: every ID and RuntimeID in the export is unique.

    Plus the two bonus structural checks declared in the module
    docstring.

    The session under test has 5 enabled tracks spanning every source
    type (input, aux, matrix, stereo, manual) so _ordered_enabled_tracks
    is exercised across all branches and the uniqueness check has a
    non-trivial population to scan.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = cls._build_user()
        cls.project = cls._build_project(cls.user)
        cls.console = cls._build_console(cls.project)
        cls.session = cls._build_session(
            cls.project, cls.console, name='Nuendo Smoke',
        )

        # Seed channel rows the multitrack tracks point at.
        # Field-type notes (verified against planner/models.py:807-934):
        #   ConsoleInput.dante_number       — CharField(max_length=3)
        #   ConsoleAuxOutput.dante_number   — IntegerField
        #   ConsoleAuxOutput.aux_number     — CharField(max_length=10)
        #   ConsoleMatrixOutput.dante_number — IntegerField
        #   ConsoleMatrixOutput.matrix_number — CharField(max_length=10)
        #   ConsoleStereoOutput.stereo_type — choices 'L'/'R'/'M' only
        cls.inp = ConsoleInput.objects.create(
            console=cls.console, input_ch='1', source='Vox',
            dante_number='1', color='Red',
        )
        cls.aux = ConsoleAuxOutput.objects.create(
            console=cls.console, aux_number='1', name='IEM Stage',
            dante_number=33, color='Blue',
        )
        cls.mtx = ConsoleMatrixOutput.objects.create(
            console=cls.console, matrix_number='1', name='Broadcast',
            dante_number=49, color='Off',
        )
        cls.stereo = ConsoleStereoOutput.objects.create(
            console=cls.console, stereo_type='L', name='Main L',
            dante_number=63, color='Green',
        )

        # Four enabled tracks — one per non-manual source type — plus a
        # manual track so all _ordered_enabled_tracks branches run.
        for n, (typ, src) in enumerate([
            ('input', cls.inp),
            ('aux', cls.aux),
            ('matrix', cls.mtx),
            ('stereo', cls.stereo),
        ], start=1):
            MultitrackTrack.objects.create(
                session=cls.session, track_number=n,
                source_type=typ, source_id=src.pk,
                enabled=True,
            )
        MultitrackTrack.objects.create(
            session=cls.session, track_number=5,
            source_type='manual', source_id=None,
            label_override='Click', color_override='#FF33AA',
            enabled=True,
        )
        cls.enabled_count = 5

    def setUp(self):
        # Point _TEMPLATE_PATH at the fake fixture and reset the
        # module-level cache so the swap takes effect for THIS test.
        # tearDown restores both so test isolation is preserved.
        self._orig_path = nle._TEMPLATE_PATH
        self._orig_tree = nle._TEMPLATE_TREE
        nle._TEMPLATE_PATH = FAKE_TEMPLATE
        nle._TEMPLATE_TREE = None

    def tearDown(self):
        nle._TEMPLATE_PATH = self._orig_path
        nle._TEMPLATE_TREE = self._orig_tree

    def test_ids_unique(self):
        """D-09 / NLP-06 — spec line 290: every `ID` attribute on
        actual `<obj class='...'>` bodies AND every `RuntimeID`/`ID`
        int-value must be unique within the document.

        Steinberg's serialization uses TWO reference-anchor patterns
        that intentionally mirror an object body's ID:
          - `<root name="..." ID="N"/>` — declaration-table anchor
          - `<obj name="..." ID="N"/>` (no @class) — member reference
        Both point to the actual `<obj class="..." ID="N">...</obj>`
        body elsewhere in the tree. They are NOT duplicates of the
        body's ID — they ARE the body's ID, used as a pointer. Our
        uniqueness assertion scopes to object bodies (`<obj>` with a
        `@class`) + `<int name='RuntimeID|ID'>` values, then asserts
        every anchor has a matching body (reference integrity).
        """
        body = build_nlpr(self.session)
        self.assertIsInstance(body, bytes)
        self.assertIn(b'<', body)  # smoke: looks like XML at all

        root = etree.fromstring(body)

        # Uniqueness: <obj class='...'> bodies + RuntimeID/ID values
        ids: list[str] = []
        for elem in root.xpath("//obj[@ID and @class]"):
            ids.append(elem.get('ID'))
        for elem in root.xpath(
            "//int[@name='RuntimeID' or @name='ID']"
        ):
            ids.append(elem.get('value'))
        duplicates = len(ids) - len(set(ids))
        self.assertEqual(
            duplicates, 0,
            f'Found {duplicates} duplicate IDs in export.\n'
            f'Total IDs scanned: {len(ids)}; unique: {len(set(ids))}.',
        )

        # Reference integrity: every <root @ID> and every class-less
        # <obj @ID> anchor must point to an <obj @ID @class> body.
        body_ids = {el.get('ID') for el in root.xpath("//obj[@ID and @class]")}
        anchor_ids = (
            {el.get('ID') for el in root.xpath("//root[@ID]")}
            | {el.get('ID') for el in root.xpath("//obj[@ID and not(@class)]")}
        )
        orphan_refs = anchor_ids - body_ids
        self.assertFalse(
            orphan_refs,
            f'Reference anchors without matching <obj class=...> body: '
            f'{sorted(orphan_refs)}',
        )

    def test_track_count_matches_enabled(self):
        """Bonus structural check (CONTEXT.md §Test budget): the
        output has exactly `enabled_count` MAudioTrackEvent elements
        inside the Audio folder — the seed was correctly removed
        (RESEARCH Pitfall 2 / D-10).
        """
        body = build_nlpr(self.session)
        root = etree.fromstring(body)
        audio = root.xpath(
            ".//obj[@class='MFolderTrack']"
            "[.//string[@name='Name' and @value='Audio']]"
        )[0]
        events = audio.xpath(".//obj[@class='MAudioTrackEvent']")
        self.assertEqual(
            len(events), self.enabled_count,
            f'Expected {self.enabled_count} MAudioTrackEvent '
            f'elements (seed dropped), got {len(events)}.',
        )

    def test_both_name_writes(self):
        """Bonus structural check (RESEARCH Pitfall 9 / NLP-03):
        every output track has BOTH the outer MListNode/Name and the
        inner DeviceAttributes/Name/String populated with the resolved
        label.
        """
        body = build_nlpr(self.session)
        root = etree.fromstring(body)
        audio = root.xpath(
            ".//obj[@class='MFolderTrack']"
            "[.//string[@name='Name' and @value='Audio']]"
        )[0]
        for event in audio.xpath(".//obj[@class='MAudioTrackEvent']"):
            outer = event.find(
                "./obj[@class='MListNode']/string[@name='Name']"
            )
            inner = event.find(
                ".//obj[@class='MAudioTrack']"
                "//member[@name='DeviceAttributes']"
                "/member[@name='Name']"
                "/string[@name='String']"
            )
            self.assertIsNotNone(outer, 'Outer Name missing')
            self.assertIsNotNone(inner, 'Inner Name/String missing')
            self.assertEqual(
                outer.get('value'), inner.get('value'),
                'Outer and inner names disagree — NLP-03 fails.',
            )
            self.assertTrue(
                outer.get('value'),
                'Track name empty after export.',
            )
