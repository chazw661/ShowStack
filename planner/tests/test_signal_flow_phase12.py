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
# Shared base — mirrors _Phase9Base setUp.
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
