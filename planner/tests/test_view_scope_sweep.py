"""Endpoints found by the get_object_or_404 / objects.get-by-id sweep.

Each of these looked a row up by a client-supplied id with no project filter
and then read or wrote it. One test per endpoint: project A's session names
project B's row, and project B's row must come out unchanged (or unserved).

Run with::

    python manage.py test planner.tests.test_view_scope_sweep \\
        --settings=audiopatch.test_settings
"""

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from planner.models import (
    CommConfigDanteChannel, CommConfigRoleset, CommConfigSession, MicSession,
    SoundvisionPrediction,
)
from planner.tests.test_tenant_isolation import TenantIsolationBase


class ViewScopeSweepTests(TenantIsolationBase):

    def post_json(self, name, payload):
        return self.client.post(
            reverse(f'planner:{name}'), data=json.dumps(payload),
            content_type='application/json',
        )

    # -- Mic Tracker -----------------------------------------------------

    def test_toggle_day_collapse_ignores_other_tenant_day(self):
        before = self.show_day_b.is_collapsed
        self.client.post(reverse('planner:toggle_day_collapse'),
                         {'day_id': self.show_day_b.id})
        self.show_day_b.refresh_from_db()
        self.assertEqual(before, self.show_day_b.is_collapsed)

    def test_create_session_refuses_other_tenant_day(self):
        before = MicSession.objects.filter(day=self.show_day_b).count()
        resp = self.post_json('create_session', {
            'day_id': self.show_day_b.id, 'name': 'PWNED', 'num_mics': 2,
        })
        self.assertNotIn(b'"success": true', resp.content)
        self.assertEqual(before, MicSession.objects.filter(day=self.show_day_b).count())

    def test_add_shared_presenter_refuses_other_tenant_assignment(self):
        self.post_json('add_shared_presenter', {
            'assignment_id': self.mic_assignment_b.id, 'presenter_name': 'PWNED',
        })
        self.assertFalse(self.mic_assignment_b.shared_presenters.exists())

    def test_remove_shared_presenter_refuses_other_tenant_assignment(self):
        resp = self.post_json('remove_shared_presenter', {
            'assignment_id': self.mic_assignment_b.id, 'presenter_name': 'x',
        })
        self.assertNotIn(b'"success": true', resp.content)

    def test_dmic_and_rotate_refuses_other_tenant_assignment(self):
        before = self.mic_assignment_b.is_d_mic
        self.post_json('dmic_and_rotate', {'assignment_id': self.mic_assignment_b.id})
        self.mic_assignment_b.refresh_from_db()
        self.assertEqual(before, self.mic_assignment_b.is_d_mic)

    def test_reset_presenter_rotation_refuses_other_tenant_assignment(self):
        resp = self.post_json('reset_presenter_rotation',
                              {'assignment_id': self.mic_assignment_b.id})
        self.assertNotIn(b'"success": true', resp.content)

    # -- Soundvision -----------------------------------------------------

    def test_upload_prediction_refuses_other_tenant_day(self):
        before = SoundvisionPrediction.objects.filter(project=self.project_b).count()
        resp = self.client.post(reverse('planner:upload_prediction'), {
            'show_day': self.show_day_b.id,
            'pdf_file': SimpleUploadedFile('x.pdf', b'%PDF-1.4', 'application/pdf'),
        })
        self.assertEqual(404, resp.status_code)
        self.assertEqual(
            before, SoundvisionPrediction.objects.filter(project=self.project_b).count())

    # -- COMM Config -----------------------------------------------------

    def _comm_rows_b(self):
        dante = CommConfigDanteChannel.objects.create(
            config=self.comm_config_b, channel_number=1, label='DanteB')
        roleset = CommConfigRoleset.objects.create(
            config=self.comm_config_b, roleset_number=1, label='RolesetB')
        return dante, roleset

    def test_comm_dante_update_and_delete_refuse_other_tenant(self):
        dante, _ = self._comm_rows_b()
        resp = self.post_json('comm_config_update_dante',
                              {'channel_id': dante.id, 'label': 'PWNED'})
        self.assertEqual(404, resp.status_code)
        resp = self.post_json('comm_config_delete_dante', {'channel_id': dante.id})
        self.assertEqual(404, resp.status_code)
        dante.refresh_from_db()
        self.assertEqual('DanteB', dante.label)

    def test_comm_roleset_update_and_delete_refuse_other_tenant(self):
        _, roleset = self._comm_rows_b()
        resp = self.post_json('comm_config_update_roleset',
                              {'roleset_id': roleset.id, 'label': 'PWNED'})
        self.assertEqual(404, resp.status_code)
        resp = self.post_json('comm_config_delete_roleset', {'roleset_id': roleset.id})
        self.assertEqual(404, resp.status_code)
        roleset.refresh_from_db()
        self.assertEqual('RolesetB', roleset.label)

    def test_comm_session_cannot_point_at_other_tenant_roleset(self):
        _, roleset_b = self._comm_rows_b()
        session_type = CommConfigSession._meta.get_field('session_type').choices[0][0]
        session_a = CommConfigSession.objects.create(
            config=self.comm_config_a, session_type=session_type, label='SessA')
        resp = self.post_json('comm_config_update_session', {
            'session_id': session_a.id, 'roleset': roleset_b.id,
        })
        self.assertEqual(404, resp.status_code)
        session_a.refresh_from_db()
        self.assertIsNone(session_a.roleset_id)

    # -- IP addresses ----------------------------------------------------

    def test_save_ip_address_refuses_other_tenant_object(self):
        resp = self.post_json('save_ip_address', {
            'model_name': 'amp', 'object_id': self.amp_b.id,
            'field_name': 'ip_address', 'ip_value': '10.9.9.9',
        })
        self.assertEqual(404, resp.status_code)
        self.amp_b.refresh_from_db()
        self.assertNotEqual('10.9.9.9', self.amp_b.ip_address)

    def test_save_ip_address_only_writes_ip_fields(self):
        resp = self.post_json('save_ip_address', {
            'model_name': 'amp', 'object_id': self.amp_a.id,
            'field_name': 'name', 'ip_value': 'PWNED',
        })
        self.assertEqual(400, resp.status_code)
        self.amp_a.refresh_from_db()
        self.assertNotEqual('PWNED', self.amp_a.name)

    def test_save_ip_address_still_saves_own_amp(self):
        resp = self.post_json('save_ip_address', {
            'model_name': 'amp', 'object_id': self.amp_a.id,
            'field_name': 'ip_address', 'ip_value': '10.1.1.1',
        })
        self.assertEqual(200, resp.status_code)
        self.amp_a.refresh_from_db()
        self.assertEqual('10.1.1.1', self.amp_a.ip_address)

    # -- Admin custom views ----------------------------------------------

    def test_yamaha_export_refuses_other_tenant_console(self):
        resp = self.client.get(reverse('admin:console-export-yamaha',
                                       args=[self.console_b.id]))
        self.assertEqual(404, resp.status_code)

    def test_processor_add_view_does_not_name_other_tenant_processor(self):
        for name in ('admin:planner_p1processor_add', 'admin:planner_galaxyprocessor_add'):
            resp = self.client.get(reverse(name),
                                   {'system_processor': self.processor_b.id})
            self.assertNoLeak(resp, name)

    def test_amp_colour_action_cannot_recolour_other_tenant_amp(self):
        before = self.amp_b.color
        self.client.post(reverse('admin:planner_amp_changelist'), {
            'action': 'assign_color_to_amps', 'apply': '1', 'color': '#123456',
            '_selected_action': [self.amp_b.id],
        })
        self.amp_b.refresh_from_db()
        self.assertEqual(before, self.amp_b.color)
