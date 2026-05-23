"""Phase 10 server-side test suite — label autocomplete, IDOR allowlist,
enrichment & equipment picker for Amp + SystemProcessor.

Covers the four Wave-1 server-side changes:

1. ``signal_flow_label_autocomplete`` view — 9 signal-name sources across Device,
   Console, Amp + Processor I/O models. Project-scoped, max 8 alphabetical
   results, blank/null filtered, source-tagged per D-02.
2. ``signal_flow_autosave`` IDOR allowlist extended for ``Amp`` and
   ``SystemProcessor`` (the most likely silent-failure bug if forgotten).
3. ``_enrich_nodes`` model allowlist extended so Amp/SystemProcessor cells
   resolve to ``isOrphan=False`` when the record exists, ``True`` when deleted.
4. ``signal_flow_autocomplete`` ``MODEL_MAP`` extended with ``processor`` and
   ``amp`` entries so the equipment picker can serve the new shape types.

Test pattern follows ``test_signal_flow_phase9._Phase9Base`` exactly:
force_login + session['current_project_id'] feeds CurrentProjectMiddleware.
"""

import json

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, Client
from django.urls import reverse

from planner.models import (
    Project, Console, ConsoleInput, ConsoleAuxOutput,
    Device, DeviceInput, DeviceOutput,
    Amp, AmpChannel, AmpModel, Location,
    SystemProcessor, P1Processor, P1Input, P1Output,
    GalaxyProcessor, GalaxyInput, GalaxyOutput,
    SignalFlowDiagram,
)


# ---------------------------------------------------------------------------
# Shared base — project + user + session wiring (mirrors Phase 9 pattern)
# ---------------------------------------------------------------------------

class _Phase10Base(TestCase):
    """Shared setUp for all Phase 10 test classes.

    Creates:
      - self.user           — staff user, force-logged-in
      - self.other_user     — owner of self.other_project (cross-project IDOR)
      - self.project        — primary project (session-scoped)
      - self.other_project  — second project for cross-project IDOR tests
      - self.location       — Location in self.project (FK target for Amp/SystemProcessor)
      - self.client         — test client with session['current_project_id']
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='phase10_owner',
            email='phase10@example.com',
            password='test-pw-phase10',
            is_staff=True,
        )
        self.other_user = User.objects.create_user(
            username='phase10_other',
            email='phase10other@example.com',
            password='pw',
            is_staff=True,
        )
        self.project = Project.objects.create(
            name='phase10_test_project',
            owner=self.user,
        )
        self.other_project = Project.objects.create(
            name='phase10_other_project',
            owner=self.other_user,
        )
        self.location = Location.objects.create(
            project=self.project,
            name='HL LA Racks',
        )
        self.other_location = Location.objects.create(
            project=self.other_project,
            name='Other Racks',
        )

        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()


# ---------------------------------------------------------------------------
# Test class 1: signal_flow_label_autocomplete
# ---------------------------------------------------------------------------

class SignalFlowLabelAutocompleteTests(_Phase10Base):
    """Lock the Phase 10 LBL-01..LBL-03 contract for label autocomplete.

    Source list (D-05): 9 sources across Device, Console, Amp + 2 Processor
    families. SystemProcessor.name is intentionally NOT a source (D-05 — it's
    a device identifier, not a signal name).
    """

    def setUp(self):
        super().setUp()
        # ---- Device I/O ----
        self.device = Device.objects.create(
            project=self.project, name='Stage Rack 1',
            input_count=8, output_count=8,
        )
        DeviceInput.objects.create(
            device=self.device, input_number=1, signal_name='FOH Lead',
        )
        DeviceOutput.objects.create(
            device=self.device, output_number=1, signal_name='Stage Return',
        )
        # ---- Console I/O ----
        self.console = Console.objects.create(
            project=self.project, name='Main Console',
        )
        # null source — must be excluded
        ConsoleInput.objects.create(console=self.console, source=None)
        # blank source — must be excluded
        ConsoleInput.objects.create(console=self.console, source='')
        # populated — must appear
        ConsoleInput.objects.create(console=self.console, source='FOH Vocal')
        ConsoleAuxOutput.objects.create(
            console=self.console, aux_number='1', name='Aux 1',
        )
        # ---- Amp channel ----
        amp_model = AmpModel.objects.create(
            manufacturer='L\'Acoustics', model_name='LA12X', channel_count=4,
        )
        self.amp = Amp.objects.create(
            project=self.project, location=self.location,
            amp_model=amp_model, name='HL Amp 1',
        )
        # Amp.save() auto-creates 4 channels with channel_name=''.
        # Update channel 1 to a populated name; leave others blank to verify
        # blank-exclusion behaviour.
        self.amp.channels.filter(channel_number=1).update(channel_name='LA1 Out A')
        # ---- Processor I/O ----
        sp_p1 = SystemProcessor.objects.create(
            project=self.project, location=self.location,
            name='P1 Stage Left', device_type='P1',
        )
        p1 = P1Processor.objects.create(system_processor=sp_p1)
        # P1Processor.save() may auto-create channels; explicitly add one with
        # a label so the assertion below is deterministic.
        P1Input.objects.create(
            p1_processor=p1, input_type='ANALOG', channel_number=99,
            label='P1 Front Fill',
        )
        P1Output.objects.create(
            p1_processor=p1, output_type='ANALOG', channel_number=99,
            label='P1 Sub L',
        )
        sp_galaxy = SystemProcessor.objects.create(
            project=self.project, location=self.location,
            name='Galaxy Center', device_type='GALAXY',
        )
        galaxy = GalaxyProcessor.objects.create(system_processor=sp_galaxy)
        GalaxyInput.objects.create(
            galaxy_processor=galaxy, input_type='AVB', channel_number=1,
            label='Galaxy AVB 1',
        )
        GalaxyOutput.objects.create(
            galaxy_processor=galaxy, output_type='ANALOG', channel_number=1,
            label='Galaxy Out 1',
        )

    def _get(self, q=''):
        url = reverse('planner:signal_flow_label_autocomplete')
        if q:
            url += f'?q={q}'
        return self.client.get(url)

    def test_returns_200_with_results_key_and_label_source_shape(self):
        resp = self._get(q='FOH')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertIn('results', body)
        self.assertIsInstance(body['results'], list)
        self.assertGreater(len(body['results']), 0)
        # Every result must have D-02 shape: {label, source}
        for row in body['results']:
            self.assertIn('label', row)
            self.assertIn('source', row)

    def test_max_8_results_alphabetical_by_label(self):
        # Insert > 8 DeviceInputs with distinct labels to force truncation.
        for i in range(12):
            DeviceInput.objects.create(
                device=self.device, input_number=100 + i,
                signal_name=f'Sig {i:02d}',
            )
        resp = self._get(q='Sig')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertLessEqual(len(body['results']), 8)
        labels = [r['label'] for r in body['results']]
        self.assertEqual(labels, sorted(labels, key=str.lower))

    def test_source_tag_present_per_D02(self):
        resp = self._get(q='FOH Lead')
        body = json.loads(resp.content)
        # 'FOH Lead' is on DeviceInput.signal_name -> source tag 'Device Input'
        matched = [r for r in body['results'] if r['label'] == 'FOH Lead']
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]['source'], 'Device Input')

    def test_blank_amp_channel_excluded(self):
        # AmpChannel rows 2-4 have channel_name='' (default). They MUST NOT
        # surface as empty-string entries.
        resp = self._get()
        body = json.loads(resp.content)
        for row in body['results']:
            self.assertNotEqual(row['label'], '')
            self.assertIsNotNone(row['label'])

    def test_null_console_input_source_excluded(self):
        resp = self._get()
        body = json.loads(resp.content)
        # No row should have a None label, regardless of where it came from.
        for row in body['results']:
            self.assertIsNotNone(row['label'])

    def test_idor_cross_project_label_never_returned(self):
        # Same-named DeviceInput in self.other_project must NOT appear.
        other_device = Device.objects.create(
            project=self.other_project, name='Other Rack',
            input_count=1, output_count=1,
        )
        DeviceInput.objects.create(
            device=other_device, input_number=1,
            signal_name='Cross-Project Secret',
        )
        resp = self._get(q='Cross-Project')
        body = json.loads(resp.content)
        labels = [r['label'] for r in body['results']]
        self.assertNotIn('Cross-Project Secret', labels)

    def test_p1_and_galaxy_labels_returned_with_correct_source_tags(self):
        resp = self._get()
        body = json.loads(resp.content)
        # Build {label: source} map for the assertions
        by_label = {r['label']: r['source'] for r in body['results']}
        self.assertEqual(by_label.get('P1 Front Fill'), 'P1 Input')
        self.assertEqual(by_label.get('P1 Sub L'), 'P1 Output')
        self.assertEqual(by_label.get('Galaxy AVB 1'), 'Galaxy Input')
        self.assertEqual(by_label.get('Galaxy Out 1'), 'Galaxy Output')

    def test_no_active_project_returns_400(self):
        """Defensive guard: if request.current_project is None (user owns no
        projects and has no invitations), the view must return 400.

        We can't simply clear self.client.session['current_project_id'] —
        CurrentProjectMiddleware will auto-select the first project the user
        owns. So we log in as a third user with zero projects + zero
        memberships; the middleware leaves request.current_project = None.
        """
        loner = User.objects.create_user(
            username='phase10_loner',
            email='loner@example.com',
            password='pw',
            is_staff=True,
        )
        loner_client = Client()
        loner_client.force_login(loner)
        resp = loner_client.get(
            reverse('planner:signal_flow_label_autocomplete') + '?q=FOH'
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Test class 2: signal_flow_autosave IDOR allowlist extension
# ---------------------------------------------------------------------------

class SignalFlowAutosaveAllowlistTests(_Phase10Base):
    """Lock the Phase 10 IDOR allowlist extension for Amp + SystemProcessor.

    Without this extension, every autosave POST containing an Amp or
    SystemProcessor cell returns 422 — the most likely silent-failure mode
    of Phase 10 (research §Pitfall 1).
    """

    def setUp(self):
        super().setUp()
        amp_model = AmpModel.objects.create(
            manufacturer='L\'Acoustics', model_name='LA12X', channel_count=4,
        )
        self.amp = Amp.objects.create(
            project=self.project, location=self.location,
            amp_model=amp_model, name='HL Amp 1',
        )
        self.system_processor = SystemProcessor.objects.create(
            project=self.project, location=self.location,
            name='P1 Stage Left', device_type='P1',
        )

    def _build_canvas(self, model_instance, type_str):
        ct = ContentType.objects.get_for_model(type(model_instance))
        return {
            'cells': [{
                'id': f'cell-{type_str}',
                'type': f'showstack.{type_str}',
                'showstack': {
                    'contentTypeId': ct.id,
                    'objectId': model_instance.id,
                    'savedLabel': model_instance.name,
                },
                'attrs': {'label': {'text': model_instance.name}},
            }],
        }

    def _post_autosave(self, diagram, canvas_state, if_match=1):
        return self.client.post(
            reverse('planner:signal_flow_autosave', args=[diagram.id]),
            data=json.dumps({'canvas_state': canvas_state, 'viewport': {}}),
            content_type='application/json',
            HTTP_IF_MATCH=str(if_match),
        )

    def test_autosave_with_amp_cell_returns_200(self):
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='amp-cell',
            canvas_state={'cells': []}, viewport={}, version=1,
        )
        canvas = self._build_canvas(self.amp, 'Amp')
        resp = self._post_autosave(diagram, canvas, if_match=1)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = json.loads(resp.content)
        self.assertTrue(body['ok'])
        self.assertEqual(body['version'], 2)

    def test_autosave_with_system_processor_cell_returns_200(self):
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='sp-cell',
            canvas_state={'cells': []}, viewport={}, version=1,
        )
        canvas = self._build_canvas(self.system_processor, 'Processor')
        resp = self._post_autosave(diagram, canvas, if_match=1)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = json.loads(resp.content)
        self.assertTrue(body['ok'])
        self.assertEqual(body['version'], 2)

    def test_autosave_with_unallowed_model_still_returns_422(self):
        """Project itself is never a canvas GFK target — proves the
        allowlist still rejects unknown model_names."""
        ct = ContentType.objects.get_for_model(Project)
        canvas = {
            'cells': [{
                'id': 'cell-bogus',
                'type': 'showstack.Generic',
                'showstack': {
                    'contentTypeId': ct.id,
                    'objectId': self.project.id,
                    'savedLabel': self.project.name,
                },
                'attrs': {'label': {'text': self.project.name}},
            }],
        }
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='bogus-cell',
            canvas_state={'cells': []}, viewport={}, version=1,
        )
        resp = self._post_autosave(diagram, canvas, if_match=1)
        self.assertEqual(resp.status_code, 422)

    def test_amp_cross_project_returns_422(self):
        """Amp from another project must still be rejected with 422."""
        amp_model = AmpModel.objects.create(
            manufacturer='L\'Acoustics', model_name='LA12X', channel_count=4,
        )
        other_amp = Amp.objects.create(
            project=self.other_project, location=self.other_location,
            amp_model=amp_model, name='Other Amp',
        )
        canvas = self._build_canvas(other_amp, 'Amp')
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='cross-amp',
            canvas_state={'cells': []}, viewport={}, version=1,
        )
        resp = self._post_autosave(diagram, canvas, if_match=1)
        self.assertEqual(resp.status_code, 422)


# ---------------------------------------------------------------------------
# Test class 3: _enrich_nodes() extension for Amp + SystemProcessor
# ---------------------------------------------------------------------------

class SignalFlowStateEnrichAmpProcessorTests(_Phase10Base):
    """Lock the Phase 10 _enrich_nodes extension.

    Without this, Amp / SystemProcessor cells load as permanent orphans even
    when the equipment record exists (research §Pitfall 3).
    """

    def _build_canvas(self, model_instance, type_str):
        ct = ContentType.objects.get_for_model(type(model_instance))
        return {
            'cells': [{
                'id': f'cell-{type_str}',
                'type': f'showstack.{type_str}',
                'showstack': {
                    'contentTypeId': ct.id,
                    'objectId': model_instance.id,
                    'savedLabel': model_instance.name,
                },
                'attrs': {'label': {'text': model_instance.name}},
            }],
        }

    def setUp(self):
        super().setUp()
        amp_model = AmpModel.objects.create(
            manufacturer='L\'Acoustics', model_name='LA12X', channel_count=4,
        )
        self.amp = Amp.objects.create(
            project=self.project, location=self.location,
            amp_model=amp_model, name='HL Amp 1',
        )
        self.system_processor = SystemProcessor.objects.create(
            project=self.project, location=self.location,
            name='P1 Stage Left', device_type='P1',
        )

    def _state_get(self, diagram):
        return self.client.get(
            reverse('planner:signal_flow_state', args=[diagram.id])
        )

    def test_amp_cell_isOrphan_false_when_amp_exists(self):
        canvas = self._build_canvas(self.amp, 'Amp')
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='amp-live',
            canvas_state=canvas, viewport={}, version=1,
        )
        resp = self._state_get(diagram)
        self.assertEqual(resp.status_code, 200)
        cell = json.loads(resp.content)['canvas_state']['cells'][0]
        self.assertFalse(cell['showstack']['isOrphan'])
        self.assertEqual(cell['attrs']['label']['text'], 'HL Amp 1')

    def test_amp_cell_isOrphan_true_when_amp_deleted(self):
        canvas = self._build_canvas(self.amp, 'Amp')
        original_name = self.amp.name
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='amp-orphan',
            canvas_state=canvas, viewport={}, version=1,
        )
        self.amp.delete()
        resp = self._state_get(diagram)
        cell = json.loads(resp.content)['canvas_state']['cells'][0]
        self.assertTrue(cell['showstack']['isOrphan'])
        # D-14: savedLabel + attrs.label.text preserved
        self.assertEqual(cell['showstack']['savedLabel'], original_name)
        self.assertEqual(cell['attrs']['label']['text'], original_name)

    def test_system_processor_cell_isOrphan_false_when_sp_exists(self):
        canvas = self._build_canvas(self.system_processor, 'Processor')
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='sp-live',
            canvas_state=canvas, viewport={}, version=1,
        )
        resp = self._state_get(diagram)
        self.assertEqual(resp.status_code, 200)
        cell = json.loads(resp.content)['canvas_state']['cells'][0]
        self.assertFalse(cell['showstack']['isOrphan'])
        self.assertEqual(cell['attrs']['label']['text'], 'P1 Stage Left')

    def test_system_processor_cell_isOrphan_true_when_sp_deleted(self):
        canvas = self._build_canvas(self.system_processor, 'Processor')
        original_name = self.system_processor.name
        diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='sp-orphan',
            canvas_state=canvas, viewport={}, version=1,
        )
        self.system_processor.delete()
        resp = self._state_get(diagram)
        cell = json.loads(resp.content)['canvas_state']['cells'][0]
        self.assertTrue(cell['showstack']['isOrphan'])
        self.assertEqual(cell['showstack']['savedLabel'], original_name)
        self.assertEqual(cell['attrs']['label']['text'], original_name)


# ---------------------------------------------------------------------------
# Test class 4: signal_flow_autocomplete MODEL_MAP — processor + amp
# ---------------------------------------------------------------------------

class SignalFlowPickerProcessorAmpTests(_Phase10Base):
    """Lock the equipment picker MODEL_MAP extension for Processor + Amp."""

    def setUp(self):
        super().setUp()
        amp_model = AmpModel.objects.create(
            manufacturer='L\'Acoustics', model_name='LA12X', channel_count=4,
        )
        self.amp = Amp.objects.create(
            project=self.project, location=self.location,
            amp_model=amp_model, name='HL Amp Alpha',
        )
        self.system_processor = SystemProcessor.objects.create(
            project=self.project, location=self.location,
            name='P1 Stage Left', device_type='P1',
        )

    def _picker_get(self, type_str, q=''):
        url = reverse('planner:signal_flow_autocomplete') + f'?type={type_str}'
        if q:
            url += f'&q={q}'
        return self.client.get(url)

    def test_picker_returns_processor_results(self):
        resp = self._picker_get('processor')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        names = [r['name'] for r in body['results']]
        self.assertIn('P1 Stage Left', names)
        # ContentType id should resolve to SystemProcessor (not P1Processor).
        sp_ct = ContentType.objects.get_for_model(SystemProcessor)
        matched = [r for r in body['results'] if r['name'] == 'P1 Stage Left']
        self.assertEqual(matched[0]['contentTypeId'], sp_ct.id)

    def test_picker_returns_amp_results(self):
        resp = self._picker_get('amp')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        names = [r['name'] for r in body['results']]
        self.assertIn('HL Amp Alpha', names)
        amp_ct = ContentType.objects.get_for_model(Amp)
        matched = [r for r in body['results'] if r['name'] == 'HL Amp Alpha']
        self.assertEqual(matched[0]['contentTypeId'], amp_ct.id)

    def test_picker_processor_idor_cross_project_excluded(self):
        SystemProcessor.objects.create(
            project=self.other_project, location=self.other_location,
            name='Cross-Project Processor', device_type='P1',
        )
        resp = self._picker_get('processor')
        body = json.loads(resp.content)
        names = [r['name'] for r in body['results']]
        self.assertNotIn('Cross-Project Processor', names)

    def test_picker_amp_idor_cross_project_excluded(self):
        amp_model = AmpModel.objects.create(
            manufacturer='L\'Acoustics', model_name='LA12X', channel_count=4,
        )
        Amp.objects.create(
            project=self.other_project, location=self.other_location,
            amp_model=amp_model, name='Cross-Project Amp',
        )
        resp = self._picker_get('amp')
        body = json.loads(resp.content)
        names = [r['name'] for r in body['results']]
        self.assertNotIn('Cross-Project Amp', names)
