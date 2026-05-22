"""Phase 9 server-side test suite — autosave optimistic locking + enrichment.

Covers DGM-07 (If-Match / 409 conflict), SHP-06 (label propagation), and
SHP-07 (orphan flagging). All 12 tests must pass before Wave 2 JS work begins.

Test class 1 — SignalFlowAutosaveVersionConflictTests:
    Exercises the Phase 9 If-Match / atomic-UPDATE path in signal_flow_autosave.

Test class 2 — SignalFlowStateEnrichmentTests:
    Exercises _enrich_nodes() via the signal_flow_state GET endpoint.
"""
import json

from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, Client
from django.urls import reverse

from planner.models import Project, Console, SignalFlowDiagram
from planner.views import _enrich_nodes


# ---------------------------------------------------------------------------
# Shared base — project + user + session wiring
# ---------------------------------------------------------------------------

class _Phase9Base(TestCase):
    """Shared setUp for both test classes.

    Creates:
      - self.user       — staff user (not in Viewer group)
      - self.project    — primary project
      - self.other_project — second project for cross-project IDOR tests
      - self.console    — Console in self.project
      - self.client     — test client, force-logged-in + session set
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='phase9_owner',
            email='phase9@example.com',
            password='test-pw-phase9',
            is_staff=True,
        )
        self.other_user = User.objects.create_user(
            username='phase9_other',
            email='phase9other@example.com',
            password='pw',
            is_staff=True,
        )
        self.project = Project.objects.create(
            name='phase9_test_project',
            owner=self.user,
        )
        self.other_project = Project.objects.create(
            name='phase9_other_project',
            owner=self.other_user,
        )
        self.console = Console.objects.create(
            project=self.project,
            name='Main Console',
        )

        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def _build_canvas_state_with_console(self, console):
        """Return a canvas_state dict with one cell linked to the given Console."""
        ct = ContentType.objects.get_for_model(type(console))
        return {
            'cells': [{
                'id': 'cell-1',
                'type': 'showstack.Console',
                'showstack': {
                    'contentTypeId': ct.id,
                    'objectId': console.id,
                    'savedLabel': console.name,
                },
                'attrs': {'label': {'text': console.name}},
            }],
        }

    def _post_autosave(self, diagram, payload, if_match=None, viewport_only=False):
        """Helper: POST to signal_flow_autosave with optional If-Match header."""
        url = reverse('planner:signal_flow_autosave', args=[diagram.id])
        if viewport_only:
            url += '?viewport_only=1'
        kwargs = dict(
            data=json.dumps(payload),
            content_type='application/json',
        )
        if if_match is not None:
            kwargs['HTTP_IF_MATCH'] = str(if_match)
        return self.client.post(url, **kwargs)


# ---------------------------------------------------------------------------
# Test class 1: If-Match / optimistic-locking behaviour
# ---------------------------------------------------------------------------

class SignalFlowAutosaveVersionConflictTests(_Phase9Base):
    """Lock the Phase 9 DGM-07 contract for signal_flow_autosave."""

    def test_missing_if_match_returns_409_version_required(self):
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='conflict-1',
            canvas_state={'cells': []}, viewport={}, version=1,
        )
        resp = self.client.post(
            reverse('planner:signal_flow_autosave', args=[diagram.id]),
            data=json.dumps({'canvas_state': {'cells': []}, 'viewport': {}}),
            content_type='application/json',
            # NOTE: no If-Match header
        )
        self.assertEqual(resp.status_code, 409)
        body = json.loads(resp.content)
        self.assertEqual(body, {'error': 'version_required'})
        # DB row must be untouched
        diagram.refresh_from_db()
        self.assertEqual(diagram.version, 1)

    def test_non_integer_if_match_returns_409_version_required(self):
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='conflict-2',
            canvas_state={'cells': []}, viewport={}, version=1,
        )
        resp = self._post_autosave(
            diagram,
            {'canvas_state': {'cells': []}, 'viewport': {}},
            if_match='not-a-number',
        )
        self.assertEqual(resp.status_code, 409)
        body = json.loads(resp.content)
        self.assertEqual(body['error'], 'version_required')
        diagram.refresh_from_db()
        self.assertEqual(diagram.version, 1)

    def test_stale_if_match_returns_409_version_conflict_with_current_version(self):
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='conflict-3',
            canvas_state={'cells': []}, viewport={}, version=5,
        )
        # Send version=1 but current DB version is 5 — stale
        resp = self._post_autosave(
            diagram,
            {'canvas_state': {'cells': []}, 'viewport': {}},
            if_match=1,
        )
        self.assertEqual(resp.status_code, 409)
        body = json.loads(resp.content)
        self.assertEqual(body['error'], 'version_conflict')
        self.assertEqual(body['current_version'], 5)
        # DB row must be untouched
        diagram.refresh_from_db()
        self.assertEqual(diagram.version, 5)

    def test_matching_if_match_returns_200_with_bumped_version(self):
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='conflict-4',
            canvas_state={'cells': []}, viewport={}, version=3,
        )
        resp = self._post_autosave(
            diagram,
            {'canvas_state': {'cells': []}, 'viewport': {}},
            if_match=3,
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body['ok'])
        self.assertEqual(body['version'], 4)
        diagram.refresh_from_db()
        self.assertEqual(diagram.version, 4)

    def test_concurrent_saves_one_wins_one_409(self):
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='race',
            canvas_state={'cells': []}, viewport={}, version=5,
        )
        payload = json.dumps({'canvas_state': {'cells': []}, 'viewport': {}})
        url = reverse('planner:signal_flow_autosave', args=[diagram.id])

        # First save with version=5 wins
        r1 = self.client.post(
            url, data=payload, content_type='application/json', HTTP_IF_MATCH='5',
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(json.loads(r1.content)['version'], 6)

        # Second save still using version=5 — now stale (DB is at 6)
        r2 = self.client.post(
            url, data=payload, content_type='application/json', HTTP_IF_MATCH='5',
        )
        self.assertEqual(r2.status_code, 409)
        body = json.loads(r2.content)
        self.assertEqual(body['error'], 'version_conflict')
        self.assertEqual(body['current_version'], 6)

    def test_viewport_only_does_not_require_if_match(self):
        """Regression: viewport-only path stays last-write-wins (D-05)."""
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='vp-only',
            canvas_state={'cells': []}, viewport={}, version=2,
        )
        resp = self._post_autosave(
            diagram,
            {'viewport': {'x': 10, 'y': 20, 'scale': 1.0}},
            # NO If-Match header
            viewport_only=True,
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body['ok'])
        self.assertTrue(body.get('viewport_only'))
        # Version must NOT change on a viewport-only write
        diagram.refresh_from_db()
        self.assertEqual(diagram.version, 2)

    def test_idor_walk_still_rejects_cross_project_equipment_with_422(self):
        """Regression: IDOR walk runs after If-Match check, returns 422 (T-09-01)."""
        # Canvas stamped with a Console from self.other_project
        other_console = Console.objects.create(
            project=self.other_project,
            name='Cross-project console',
        )
        ct = ContentType.objects.get_for_model(Console)
        cross_canvas = {
            'cells': [{
                'id': 'cell-x',
                'type': 'showstack.Console',
                'showstack': {
                    'contentTypeId': ct.id,
                    'objectId': other_console.id,
                    'savedLabel': other_console.name,
                },
                'attrs': {'label': {'text': other_console.name}},
            }],
        }
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='idor-test',
            canvas_state={'cells': []}, viewport={}, version=1,
        )
        # If-Match is CORRECT (passes the version check); IDOR walk should reject
        resp = self._post_autosave(
            diagram,
            {'canvas_state': cross_canvas, 'viewport': {}},
            if_match=1,
        )
        self.assertEqual(resp.status_code, 422)
        body = json.loads(resp.content)
        self.assertIn('error', body)


# ---------------------------------------------------------------------------
# Test class 2: _enrich_nodes() via the signal_flow_state GET endpoint
# ---------------------------------------------------------------------------

class SignalFlowStateEnrichmentTests(_Phase9Base):
    """Lock the Phase 9 SHP-06 + SHP-07 server-side contract."""

    def test_live_console_label_refreshes_on_state_get(self):
        """SHP-06: rename a linked Console → next GET reflects new name."""
        canvas = self._build_canvas_state_with_console(self.console)
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='enrich-live',
            canvas_state=canvas, viewport={}, version=1,
        )
        # Rename the Console
        self.console.name = 'Renamed Console'
        self.console.save(update_fields=['name'])

        resp = self.client.get(
            reverse('planner:signal_flow_state', args=[diagram.id])
        )
        self.assertEqual(resp.status_code, 200)
        state = json.loads(resp.content)
        cell = state['canvas_state']['cells'][0]
        self.assertEqual(cell['attrs']['label']['text'], 'Renamed Console')
        self.assertEqual(cell['showstack']['savedLabel'], 'Renamed Console')
        self.assertFalse(cell['showstack']['isOrphan'])

    def test_deleted_console_returns_orphan_with_savedLabel_preserved(self):
        """SHP-07: delete a linked Console → GET shows isOrphan=True + original label."""
        canvas = self._build_canvas_state_with_console(self.console)
        original_name = self.console.name
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='enrich-orphan',
            canvas_state=canvas, viewport={}, version=1,
        )
        self.console.delete()

        resp = self.client.get(
            reverse('planner:signal_flow_state', args=[diagram.id])
        )
        self.assertEqual(resp.status_code, 200)
        state = json.loads(resp.content)
        cell = state['canvas_state']['cells'][0]
        self.assertTrue(cell['showstack']['isOrphan'])
        # savedLabel PRESERVED (D-14)
        self.assertEqual(cell['showstack']['savedLabel'], original_name)
        # attrs.label.text PRESERVED (D-14)
        self.assertEqual(cell['attrs']['label']['text'], original_name)

    def test_cross_project_reference_is_orphan(self):
        """T-09-03: canvas stamped with a Console from another project → isOrphan=True."""
        other_console = Console.objects.create(
            project=self.other_project,
            name='Other Project Console',
        )
        ct = ContentType.objects.get_for_model(Console)
        canvas = {
            'cells': [{
                'id': 'cell-cross',
                'type': 'showstack.Console',
                'showstack': {
                    'contentTypeId': ct.id,
                    'objectId': other_console.id,
                    'savedLabel': 'Other Project Console',
                },
                'attrs': {'label': {'text': 'Other Project Console'}},
            }],
        }
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='cross-project-enrich',
            canvas_state=canvas, viewport={}, version=1,
        )

        resp = self.client.get(
            reverse('planner:signal_flow_state', args=[diagram.id])
        )
        self.assertEqual(resp.status_code, 200)
        state = json.loads(resp.content)
        cell = state['canvas_state']['cells'][0]
        self.assertTrue(cell['showstack']['isOrphan'])
        # savedLabel and label text must be PRESERVED (D-14)
        self.assertEqual(cell['showstack']['savedLabel'], 'Other Project Console')
        self.assertEqual(cell['attrs']['label']['text'], 'Other Project Console')

    def test_generic_shape_untouched(self):
        """Non-linked cell (no contentTypeId) must not get an isOrphan flag."""
        canvas = {
            'cells': [{
                'id': 'cell-generic',
                'type': 'showstack.Generic',
                'showstack': {
                    # contentTypeId and objectId absent — generic shape
                    'savedLabel': 'Stage Monitor',
                },
                'attrs': {'label': {'text': 'Stage Monitor'}},
            }],
        }
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='generic-shape',
            canvas_state=canvas, viewport={}, version=1,
        )

        resp = self.client.get(
            reverse('planner:signal_flow_state', args=[diagram.id])
        )
        self.assertEqual(resp.status_code, 200)
        state = json.loads(resp.content)
        cell = state['canvas_state']['cells'][0]
        # isOrphan must NOT have been added
        self.assertNotIn('isOrphan', cell.get('showstack', {}))
        # Other fields preserved
        self.assertEqual(cell['showstack']['savedLabel'], 'Stage Monitor')
        self.assertEqual(cell['attrs']['label']['text'], 'Stage Monitor')

    def test_persisted_blob_is_not_mutated(self):
        """D-12: _enrich_nodes() must deep-copy; DB blob must remain unchanged."""
        canvas = self._build_canvas_state_with_console(self.console)
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='deepcopy',
            canvas_state=canvas, viewport={}, version=1,
        )

        # Rename Console so live name differs from the stored savedLabel
        self.console.name = 'Mutated Name'
        self.console.save(update_fields=['name'])

        # Call the helper directly — not via the HTTP endpoint
        enriched = _enrich_nodes(diagram.canvas_state, self.project)

        diagram.refresh_from_db()
        # The DB blob still has the OLD name
        self.assertEqual(
            diagram.canvas_state['cells'][0]['attrs']['label']['text'],
            'Main Console',
        )
        # The enriched copy has the new name
        self.assertEqual(
            enriched['cells'][0]['attrs']['label']['text'],
            'Mutated Name',
        )
        # Confirm they differ (belt-and-suspenders)
        self.assertNotEqual(
            diagram.canvas_state['cells'][0]['attrs']['label']['text'],
            enriched['cells'][0]['attrs']['label']['text'],
        )
