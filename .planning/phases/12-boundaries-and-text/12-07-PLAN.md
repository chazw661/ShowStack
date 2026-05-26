---
phase: 12
plan_number: 07
wave: 1
depends_on: []
files_modified:
  - planner/tests/test_signal_flow_phase12.py
autonomous: true
requirements_addressed: [DRAW-02, TXT-02]
must_haves:
  truths:
    - "planner/tests/test_signal_flow_phase12.py exists with _Phase12Base setUp following the _Phase9Base pattern (User + Project + ProjectMember not required — Phase 9 uses owner-only; mirror that)"
    - "test_boundary_only_canvas_state_round_trips POSTs a canvas_state containing only a BoundaryLine cell with no equipment GFK and asserts HTTP 200, ok=True, version=2 — regression-locks the planner/views.py:7693 'continue' branch (R-04)"
    - "test_text_only_canvas_state_round_trips POSTs a canvas_state containing only a TextLabel cell and asserts HTTP 200"
    - "test_mixed_boundary_text_equipment_round_trip POSTs a canvas_state containing BoundaryLine + TextLabel + a Console with valid project-scoped contentTypeId/objectId and asserts HTTP 200 — proves the allowlist walk skips decorative cells AND runs IDOR on the Console"
    - "test_boundary_with_invalid_color_still_saves POSTs a BoundaryLine with color='not-a-real-hex' and asserts HTTP 200 — locks the 'server is opaque to canvas_state JSON' contract"
    - "Full Phase 12 backend suite runs in under 5 seconds via `python manage.py test planner.tests.test_signal_flow_phase12 -v 2`"
  artifacts:
    - path: "planner/tests/test_signal_flow_phase12.py"
      provides: "Regression suite for IDOR pass-through + canvas_state opacity (R-04, R-13, R-14)"
      contains: "class _Phase12Base(TestCase):"
      contains_also: "class SignalFlowPhase12AutosaveTests(_Phase12Base):"
  key_links:
    - from: "BoundaryLine cell with no contentTypeId/objectId"
      to: "planner/views.py:7693 `continue` branch"
      via: "_post_autosave returns 200"
      pattern: "test_boundary_only_canvas_state_round_trips"
    - from: "Mixed canvas (decorative + equipment)"
      to: "Allowlist walks runs IDOR on Console only"
      via: "_post_autosave returns 200 with valid project-scoped GFK"
      pattern: "test_mixed_boundary_text_equipment_round_trip"
---

<objective>
Create `planner/tests/test_signal_flow_phase12.py` with four backend autosave round-trip tests that regression-lock two server-side contracts: (a) the existing IDOR allowlist at `planner/views.py:7693` passes through cells without `showstack.contentTypeId/objectId` via its `continue` statement (R-04 finding — the bug does NOT exist today, but a future refactor of the allowlist could re-introduce it without a regression test), and (b) the server treats `canvas_state` as opaque JSON — invalid colors and unknown cell types still round-trip. This plan is INDEPENDENT of all frontend work (Plans 01-06) and can run in Wave 1 parallel with the JS / CSS / HTML work. The phase Goal's "BoundaryLine cells persist through autosave → POST → GET round-trip" claim is locked here.
</objective>

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Future refactor of the IDOR allowlist promotes the pass-through to a strict-enum check, silently rejecting Phase 12 cells (Risk #2) | high | This entire test file IS the mitigation. test_boundary_only + test_text_only POST a payload that exercises the `continue` branch; if a future refactor breaks it, these tests turn red. |
| Test creates equipment with `is_staff=False` user and the project-scoping middleware rejects the save | medium | Test base mirrors `_Phase9Base` setUp exactly: User with `is_staff=True`, Project owned by that user, session has `current_project_id` set. Verified by reading `planner/tests/test_signal_flow_phase9.py` lines 38-68. |
| Mixed-canvas test uses a Console with a contentTypeId/objectId that points to a project the user doesn't own → IDOR rejects the entire save | medium | Mixed test creates the Console in self.project (the current_project_id project), not in self.other_project. Acceptance criterion: the Console row in the mixed test is created via `Console.objects.create(project=self.project, name=...)`. |
| Test pollutes other phase test runs by leaving DB state | low | `TestCase` (NOT `TransactionTestCase`) auto-rolls back at end of each test. No cleanup code needed. |
| New endpoint OR new view code accidentally introduced | low | This plan ONLY creates a new test file. No changes to planner/views.py, models.py, urls.py. Acceptance criterion: `files_modified` in the frontmatter contains ONLY `planner/tests/test_signal_flow_phase12.py`. |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Create planner/tests/test_signal_flow_phase12.py with _Phase12Base + 4 tests</name>
  <files>planner/tests/test_signal_flow_phase12.py</files>
  <read_first>
    - planner/tests/test_signal_flow_phase9.py lines 1-97 (entire `_Phase9Base` class — the setUp pattern + `_post_autosave` helper to clone)
    - planner/tests/test_signal_flow_phase9.py lines 160-180 (test_matching_if_match_returns_200_with_bumped_version — the version=1 → 2 bump pattern to mirror)
    - planner/views.py lines 7686-7726 (the IDOR allowlist walk — confirms the `continue` branch on line 7693 is the regression target)
    - planner/models.py lines 1-30 (SignalFlowDiagram + Console imports — confirm class names)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-04 (lines 451-472 — verbatim quote of the IDOR allowlist code being regression-locked)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-13 (lines 967-1033 — test surface specification)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-14 (lines 1037-1100 — per-cell JSON shape for DRAW + TXT)
  </read_first>
  <action>
    Create a new file at `planner/tests/test_signal_flow_phase12.py` with the following content VERBATIM. The setUp pattern matches `_Phase9Base` exactly — User + Project + Console + force_login + session current_project_id.

    ```python
    """Phase 12 server-side test suite — boundary + text cell autosave round-trip.

    Locks two contracts that Phase 12 inherits from the server but does not modify:

    1. The IDOR allowlist at planner/views.py:7686-7693 PASSES THROUGH cells without
       `showstack.contentTypeId/objectId` via its `continue` statement. BoundaryLine
       and TextLabel cells have no equipment GFK; they MUST round-trip with HTTP 200.
       Research R-04 verified this works today; these tests lock it against future
       refactors (Risk #2).

    2. `canvas_state` is opaque JSON to the server. Invalid colors, unknown line
       styles, or future cell types still round-trip — the server does not parse
       the cell content beyond the IDOR walk.

    No views or models change for Phase 12. This test file is the ONLY backend
    artifact in the phase.
    """
    import json

    from django.contrib.auth.models import User
    from django.contrib.contenttypes.models import ContentType
    from django.test import TestCase, Client
    from django.urls import reverse

    from planner.models import Project, Console, SignalFlowDiagram


    # ---------------------------------------------------------------------------
    # Shared base — mirrors _Phase9Base setUp exactly.
    # ---------------------------------------------------------------------------

    class _Phase12Base(TestCase):
        """Shared setUp for Phase 12 backend tests.

        Creates:
          - self.user     — staff user owning self.project
          - self.project  — primary project, set as current_project_id in session
          - self.console  — Console in self.project (used by mixed-canvas test)
          - self.client   — Django test client, force-logged-in
        """

        def setUp(self):
            self.user = User.objects.create_user(
                username='phase12_owner',
                email='phase12@example.com',
                password='test-pw-phase12',
                is_staff=True,
            )
            self.project = Project.objects.create(
                name='phase12_test_project',
                owner=self.user,
            )
            self.console = Console.objects.create(
                project=self.project,
                name='Phase 12 Console',
            )

            self.client = Client()
            self.client.force_login(self.user)
            session = self.client.session
            session['current_project_id'] = self.project.id
            session.save()

        def _post_autosave(self, diagram, payload, if_match=None):
            """POST to signal_flow_autosave; mirrors _Phase9Base._post_autosave."""
            url = reverse('planner:signal_flow_autosave', args=[diagram.id])
            kwargs = dict(
                data=json.dumps(payload),
                content_type='application/json',
            )
            if if_match is not None:
                kwargs['HTTP_IF_MATCH'] = str(if_match)
            return self.client.post(url, **kwargs)


    # ---------------------------------------------------------------------------
    # Phase 12 autosave round-trip tests — R-04 + R-13 + R-14.
    # ---------------------------------------------------------------------------

    class SignalFlowPhase12AutosaveTests(_Phase12Base):
        """Lock Phase 12's R-04 finding: cells WITHOUT showstack.contentTypeId
        bypass the IDOR allowlist via the `continue` at planner/views.py:7693.

        Regression test against a future refactor that re-introduces the bug.
        """

        def test_boundary_only_canvas_state_round_trips(self):
            """Canvas with only a BoundaryLine cell (no equipment GFK) autosaves OK."""
            diagram = SignalFlowDiagram.objects.create(
                project=self.project, name='boundary-only',
                canvas_state={'cells': []}, viewport={}, version=1,
            )
            payload = {
                'canvas_state': {
                    'cells': [{
                        'id': 'b1',
                        'type': 'showstack.BoundaryLine',
                        'position': {'x': 0, 'y': 0},
                        'size': {'width': 0, 'height': 0},
                        'attrs': {
                            'linePrimary': {'points': '100,100 200,100 200,200'},
                            'lineSecondary': {'display': 'none'},
                        },
                        'vertices': [
                            {'x': 100, 'y': 100},
                            {'x': 200, 'y': 100},
                            {'x': 200, 'y': 200},
                        ],
                        'color': '#dc2626',
                        'lineStyle': 'dashed',
                        'z': 0,
                    }],
                },
                'viewport': {'x': 0, 'y': 0, 'scale': 1.0, 'snapEnabled': True},
            }
            resp = self._post_autosave(diagram, payload, if_match=1)
            self.assertEqual(resp.status_code, 200, resp.content)
            body = json.loads(resp.content)
            self.assertTrue(body['ok'])
            self.assertEqual(body['version'], 2)
            diagram.refresh_from_db()
            self.assertEqual(diagram.version, 2)
            # Verify the boundary cell round-tripped into the stored canvas_state.
            cells = (diagram.canvas_state or {}).get('cells') or []
            self.assertEqual(len(cells), 1)
            self.assertEqual(cells[0]['type'], 'showstack.BoundaryLine')
            self.assertEqual(cells[0]['color'], '#dc2626')
            self.assertEqual(cells[0]['lineStyle'], 'dashed')
            self.assertEqual(len(cells[0]['vertices']), 3)

        def test_text_only_canvas_state_round_trips(self):
            """Canvas with only a TextLabel cell (no equipment GFK) autosaves OK."""
            diagram = SignalFlowDiagram.objects.create(
                project=self.project, name='text-only',
                canvas_state={'cells': []}, viewport={}, version=1,
            )
            payload = {
                'canvas_state': {
                    'cells': [{
                        'id': 't1',
                        'type': 'showstack.TextLabel',
                        'position': {'x': 240, 'y': 80},
                        'size': {'width': 60, 'height': 22},
                        'attrs': {
                            'label': {
                                'text': 'FOH',
                                'fontSize': 24,
                                'fill': '#ffffff',
                            },
                        },
                        'fontSize': 24,
                        'color': '#ffffff',
                        'z': 999,
                    }],
                },
                'viewport': {'x': 0, 'y': 0, 'scale': 1.0, 'snapEnabled': True},
            }
            resp = self._post_autosave(diagram, payload, if_match=1)
            self.assertEqual(resp.status_code, 200, resp.content)
            body = json.loads(resp.content)
            self.assertTrue(body['ok'])
            self.assertEqual(body['version'], 2)
            diagram.refresh_from_db()
            cells = (diagram.canvas_state or {}).get('cells') or []
            self.assertEqual(len(cells), 1)
            self.assertEqual(cells[0]['type'], 'showstack.TextLabel')
            self.assertEqual(cells[0]['attrs']['label']['text'], 'FOH')
            self.assertEqual(cells[0]['fontSize'], 24)
            self.assertEqual(cells[0]['color'], '#ffffff')

        def test_mixed_boundary_text_equipment_round_trip(self):
            """Mixed canvas — BoundaryLine + TextLabel + Console (with valid project-scoped GFK).

            Proves the IDOR allowlist walk skips the decorative cells (no
            showstack.contentTypeId) and runs the IDOR check ONLY on the Console.
            This is the realistic save shape — engineers will routinely combine
            decorative annotations with linked equipment in one diagram.
            """
            diagram = SignalFlowDiagram.objects.create(
                project=self.project, name='mixed',
                canvas_state={'cells': []}, viewport={}, version=1,
            )
            console_ct = ContentType.objects.get_for_model(Console)
            payload = {
                'canvas_state': {
                    'cells': [
                        {
                            'id': 'b1',
                            'type': 'showstack.BoundaryLine',
                            'position': {'x': 0, 'y': 0},
                            'vertices': [{'x': 50, 'y': 50}, {'x': 250, 'y': 50}],
                            'color': '#000000',
                            'lineStyle': 'solid',
                            'z': 0,
                        },
                        {
                            'id': 'c1',
                            'type': 'showstack.Console',
                            'position': {'x': 100, 'y': 100},
                            'size': {'width': 180, 'height': 60},
                            'attrs': {'label': {'text': self.console.name}},
                            'showstack': {
                                'contentTypeId': console_ct.id,
                                'objectId': self.console.id,
                                'savedLabel': self.console.name,
                            },
                            'z': 1,
                        },
                        {
                            'id': 't1',
                            'type': 'showstack.TextLabel',
                            'position': {'x': 240, 'y': 30},
                            'attrs': {'label': {'text': 'Stage Left', 'fontSize': 16, 'fill': '#000000'}},
                            'fontSize': 16,
                            'color': '#000000',
                            'z': 999,
                        },
                    ],
                },
                'viewport': {'x': 0, 'y': 0, 'scale': 1.0, 'snapEnabled': True},
            }
            resp = self._post_autosave(diagram, payload, if_match=1)
            self.assertEqual(resp.status_code, 200, resp.content)
            body = json.loads(resp.content)
            self.assertTrue(body['ok'])
            self.assertEqual(body['version'], 2)
            diagram.refresh_from_db()
            cells = (diagram.canvas_state or {}).get('cells') or []
            self.assertEqual(len(cells), 3)
            types = sorted(c['type'] for c in cells)
            self.assertEqual(
                types,
                ['showstack.BoundaryLine', 'showstack.Console', 'showstack.TextLabel'],
            )

        def test_boundary_with_invalid_color_still_saves(self):
            """Phase 12 cells are opaque to the server — palette validation is client-side.

            The server does not parse `cell.color` or `cell.lineStyle`; it just
            stores the canvas_state JSON blob. A garbage color value still
            round-trips with HTTP 200. This locks in the 'server is opaque to
            canvas_state JSON' contract — if a future change adds server-side
            palette validation, this test will turn red and force a decision.
            """
            diagram = SignalFlowDiagram.objects.create(
                project=self.project, name='garbage-color',
                canvas_state={'cells': []}, viewport={}, version=1,
            )
            payload = {
                'canvas_state': {
                    'cells': [{
                        'id': 'b-junk',
                        'type': 'showstack.BoundaryLine',
                        'position': {'x': 0, 'y': 0},
                        'vertices': [{'x': 0, 'y': 0}, {'x': 10, 'y': 10}],
                        'color': 'not-a-real-hex',
                        'lineStyle': 'plaid',
                        'z': 0,
                    }],
                },
                'viewport': {},
            }
            resp = self._post_autosave(diagram, payload, if_match=1)
            self.assertEqual(resp.status_code, 200, resp.content)
            body = json.loads(resp.content)
            self.assertTrue(body['ok'])
            self.assertEqual(body['version'], 2)
            diagram.refresh_from_db()
            cells = (diagram.canvas_state or {}).get('cells') or []
            self.assertEqual(cells[0]['color'], 'not-a-real-hex')
            self.assertEqual(cells[0]['lineStyle'], 'plaid')
    ```

    Do NOT touch any other test file. Do NOT modify planner/views.py or any other view file — the IDOR allowlist's `continue` branch is the regression target and MUST remain unchanged. Do NOT register on `admin.site` (irrelevant). Do NOT create model migrations.

    Verify the test base aligns with the actual Phase 9 base by reading `planner/tests/test_signal_flow_phase9.py` lines 38-97 BEFORE writing the file. If the actual `_Phase9Base.setUp` includes additional setup steps not reflected above (e.g., a Group assignment for `superuser` / `premium owner`), adopt the same steps in `_Phase12Base` — the goal is functional equivalence with the Phase 9 / Phase 10 test base, not a fresh design.
  </action>
  <verify>
    <automated>test -f planner/tests/test_signal_flow_phase12.py && grep -n "class _Phase12Base(TestCase):" planner/tests/test_signal_flow_phase12.py && grep -n "class SignalFlowPhase12AutosaveTests(_Phase12Base):" planner/tests/test_signal_flow_phase12.py && grep -n "def test_boundary_only_canvas_state_round_trips" planner/tests/test_signal_flow_phase12.py && grep -n "def test_text_only_canvas_state_round_trips" planner/tests/test_signal_flow_phase12.py && grep -n "def test_mixed_boundary_text_equipment_round_trip" planner/tests/test_signal_flow_phase12.py && grep -n "def test_boundary_with_invalid_color_still_saves" planner/tests/test_signal_flow_phase12.py && python manage.py test planner.tests.test_signal_flow_phase12 -v 2</automated>
  </verify>
  <acceptance_criteria>
    - `test -f planner/tests/test_signal_flow_phase12.py` succeeds (file exists).
    - `grep -c "class _Phase12Base(TestCase):" planner/tests/test_signal_flow_phase12.py` returns exactly `1`.
    - `grep -c "class SignalFlowPhase12AutosaveTests(_Phase12Base):" planner/tests/test_signal_flow_phase12.py` returns exactly `1`.
    - The file declares EXACTLY 4 test methods: `test_boundary_only_canvas_state_round_trips`, `test_text_only_canvas_state_round_trips`, `test_mixed_boundary_text_equipment_round_trip`, `test_boundary_with_invalid_color_still_saves` — verified by `grep -c "    def test_" planner/tests/test_signal_flow_phase12.py` returning exactly `4`.
    - The test base contains `User.objects.create_user(...)` + `Project.objects.create(...)` + `Console.objects.create(...)` + `self.client.force_login(self.user)` + session `current_project_id` set — verified by reading the setUp.
    - `python manage.py test planner.tests.test_signal_flow_phase12 -v 2` exits with status 0 (all 4 tests pass).
    - The test suite completes in under 5 seconds (Phase 12 has no slow operations — no PNG render, no JS execution).
    - No imports from `planner.views` (no `_enrich_nodes` references — this plan is opacity-locking; the GET endpoint enrichment path is out of scope).
    - No changes to `planner/views.py` — verified by `git diff --name-only HEAD planner/views.py` returning empty (or a no-op if executor stages the test only).
    - No model migrations created — verified by `ls planner/migrations/` showing no new file with a date in the current session window.
    - The mixed test creates the Console row in `self.project` (the session's current_project_id) — verified by reading the setUp: the Console is created in the Base, and the mixed test reuses `self.console` (which is in `self.project`).
    - The boundary-only test asserts `body['version'] == 2` (initial version=1 bumped to 2 on successful save) — verified by reading the assertion.
    - The mixed test asserts `len(cells) == 3` and that the sorted type tuple is `['showstack.BoundaryLine', 'showstack.Console', 'showstack.TextLabel']` — verified by reading the assertion.
    - The invalid-color test asserts the garbage color round-trips unchanged — confirms server opacity.
  </acceptance_criteria>
  <done>planner/tests/test_signal_flow_phase12.py exists with _Phase12Base + 4 round-trip tests; `python manage.py test planner.tests.test_signal_flow_phase12 -v 2` exits clean.</done>
</task>

</tasks>

<verification>
- `python manage.py test planner.tests.test_signal_flow_phase12 -v 2` — expect 4 tests, all pass, total runtime under 5 seconds.
- `python manage.py test planner.tests.test_signal_flow_phase9 planner.tests.test_signal_flow_phase10 planner.tests.test_signal_flow_phase12 -v 2` — expect ALL existing Phase 9 + Phase 10 tests still pass alongside the new Phase 12 tests (no cross-phase regression).
- `git diff --stat planner/` after the plan: ONLY `planner/tests/test_signal_flow_phase12.py` should appear; no other planner/ files modified.
</verification>

<must_haves>
- planner/tests/test_signal_flow_phase12.py exists.
- _Phase12Base setUp mirrors _Phase9Base: User + Project + Console + force_login + session current_project_id.
- _post_autosave helper mirrors _Phase9Base._post_autosave signature: `(diagram, payload, if_match=None)`.
- test_boundary_only_canvas_state_round_trips locks the IDOR `continue` branch for BoundaryLine cells without GFK (R-04).
- test_text_only_canvas_state_round_trips locks the IDOR `continue` branch for TextLabel cells without GFK.
- test_mixed_boundary_text_equipment_round_trip proves the allowlist walk skips decorative cells AND validates the Console's GFK in one save.
- test_boundary_with_invalid_color_still_saves locks the "server is opaque to canvas_state JSON" contract.
- All 4 tests pass on `python manage.py test planner.tests.test_signal_flow_phase12 -v 2`.
- No changes to planner/views.py, planner/models.py, planner/urls.py, or any migration.
</must_haves>
