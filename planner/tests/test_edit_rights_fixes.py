"""The fixes test_write_endpoint_guard found, beyond the role check itself:
tenant scoping the guard can't see with an empty body, and what each page
shows a viewer.

Run with::

    python manage.py test planner.tests.test_edit_rights_fixes \\
        --settings=audiopatch.test_settings
"""

import json

from django.urls import reverse

from planner.models import (
    AmpDivider, AmpLocation, CommBeltPack, CommCrewName, CommPosition, Location,
    MicAssignment, Project, ProjectMember,
)
from planner.tests.test_write_endpoint_guard import WriteGuardBase


class TenantScopingTests(WriteGuardBase):

    def test_divider_project_comes_from_the_location(self):
        location = AmpLocation.objects.create(project=self.project, name='SL')
        self.login(self.owner, self.project)
        resp = self.client.post('/audiopatch/api/amp/divider/add/', {
            'location_id': location.pk, 'project_id': self.theirs.pk, 'label': 'x'})
        self.assertEqual(200, resp.status_code)
        divider = AmpDivider.objects.get(pk=resp.json()['divider_id'])
        self.assertEqual(self.project, divider.project)

    def test_divider_sync_ignores_a_project_in_the_body(self):
        location = AmpLocation.objects.create(project=self.project, name='SR')
        self.login(self.owner, self.project)
        self.client.post('/audiopatch/api/amp/divider/sync/', {
            'location_id': location.pk, 'project_id': self.theirs.pk,
            'dividers': json.dumps([{'label': 'new', 'after': 0}])})
        self.assertFalse(AmpDivider.objects.filter(project=self.theirs).exists())
        self.assertTrue(AmpDivider.objects.filter(location=location, project=self.project,
                                                  label='new').exists())

    def test_divider_in_another_project_is_404(self):
        divider = self.factory.get(AmpDivider)
        self.login(self.outsider, self.theirs)
        for action in ('update', 'delete', 'reorder'):
            resp = self.client.post(f'/audiopatch/api/amp/divider/{divider.pk}/{action}/',
                                    {'direction': 'up', 'label': 'x'})
            self.assertEqual(404, resp.status_code, action)
        self.assertTrue(AmpDivider.objects.filter(pk=divider.pk).exists())

    def test_location_pdf_of_another_project_is_404(self):
        location = Location.objects.create(project=self.project, name='Stage')
        self.login(self.outsider, self.theirs)
        self.assertEqual(404, self.client.get(
            reverse('planner:location_pdf_export', args=[location.pk])).status_code)
        self.login(self.viewer, self.project)
        self.assertEqual(200, self.client.get(
            reverse('planner:location_pdf_export', args=[location.pk])).status_code)

    def test_comm_imports_write_to_the_current_project(self):
        CommPosition.objects.create(project=self.theirs, name='FOH', order=1)
        self.login(self.owner, self.project)
        self.client.post('/audiopatch/admin/planner/commposition/import/', {'positions': 'FOH'})
        self.client.post('/audiopatch/admin/planner/commcrewname/import/', {'names': 'Sam'})
        self.assertTrue(CommPosition.objects.filter(project=self.project, name='FOH').exists())
        self.assertTrue(CommCrewName.objects.filter(project=self.project, name='Sam').exists())

    def test_next_beltpack_number_counts_this_project_only(self):
        mine = self.factory.get(CommBeltPack)
        CommBeltPack.objects.filter(pk=mine.pk).update(bp_number=3, system_type='WIRELESS')
        theirs = CommBeltPack.objects.get(pk=mine.pk)
        theirs.pk, theirs.project, theirs.bp_number = None, self.theirs, 40
        theirs.save()
        self.login(self.owner, self.project)
        resp = self.client.get('/audiopatch/admin/planner/commbeltpack/get_next_bp_number/',
                               {'system_type': 'WIRELESS'})
        self.assertEqual(4, resp.json()['next_bp_number'])


class MobileToggleTests(WriteGuardBase):

    def post(self, user, project, url):
        self.login(user, project)
        return self.client.post(url)

    def test_viewer_403_member_editor_200_non_member_404(self):
        bp = self.factory.get(CommBeltPack)
        url = f'/m/api/comm/toggle-checkout/{bp.pk}/'
        self.assertEqual(403, self.post(self.viewer, self.project, url).status_code)
        self.assertEqual(404, self.post(self.outsider, self.theirs, url).status_code)
        before = CommBeltPack.objects.get(pk=bp.pk).checked_out
        self.assertEqual(before, CommBeltPack.objects.get(pk=bp.pk).checked_out)
        self.assertEqual(200, self.post(self.owner, self.project, url).status_code)
        self.assertNotEqual(before, CommBeltPack.objects.get(pk=bp.pk).checked_out)

    def test_micd_toggle(self):
        mic = self.factory.get(MicAssignment)
        url = f'/m/api/mic/toggle-micd/{mic.pk}/'
        self.assertEqual(403, self.post(self.viewer, self.project, url).status_code)
        self.assertEqual(404, self.post(self.outsider, self.theirs, url).status_code)
        editor = self.outsider
        ProjectMember.objects.create(project=self.project, user=editor, role='editor',
                                     invited_by=self.owner)
        self.assertEqual(200, self.post(editor, self.project, url).status_code)


class ViewerPagesTests(WriteGuardBase):

    def page(self, user, url):
        self.login(user, self.project)
        resp = self.client.get(url)
        self.assertEqual(200, resp.status_code, url)
        return resp.content.decode()

    def test_rack_page_hides_add_and_divider_controls(self):
        AmpDivider.objects.all().delete()
        location = AmpLocation.objects.create(project=self.project, name='Rack A')
        AmpDivider.objects.create(project=self.project, location=location, label='Top')
        url = reverse('admin:planner_amp_changelist')
        viewer, owner = self.page(self.viewer, url), self.page(self.owner, url)
        for marker in ('class="add-amp-row"', 'onclick="addDivider(', 'class="rack-divider-actions"'):
            self.assertIn(marker, owner)
            self.assertNotIn(marker, viewer)
        self.assertRegex(viewer, r'class="rack-divider-label"[^>]*readonly')

    def test_checklist_is_read_only_for_a_viewer(self):
        url = reverse('planner:audio_checklist')
        viewer, owner = self.page(self.viewer, url), self.page(self.owner, url)
        self.assertIn('const CAN_EDIT = false;', viewer)
        self.assertIn('const CAN_EDIT = true;', owner)
        self.assertNotIn('resetAll()">', viewer)
        self.assertIn('resetAll()">', owner)

    def test_monitor_agent_key_only_for_editors(self):
        key = str(self.project.agent_api_key)
        url = reverse('planner:network_monitor')
        self.assertNotIn(key, self.page(self.viewer, url))
        self.assertIn(key, self.page(self.owner, url))

    def test_multitrack_new_session_hidden_for_a_viewer(self):
        url = reverse('planner:multitrack_dashboard')
        create = reverse('planner:multitrack_create')
        self.assertNotIn(f'href="{create}"', self.page(self.viewer, url))
        self.assertIn(f'href="{create}"', self.page(self.owner, url))

    def test_populate_positions_is_not_run_for_a_viewer(self):
        CommPosition.objects.all().delete()
        self.login(self.viewer, self.project)
        self.client.post('/admin/planner/commposition/', {'action': 'populate_common_positions'})
        self.assertFalse(CommPosition.objects.filter(project=self.project).exists())
        self.login(self.owner, self.project)
        self.client.post('/admin/planner/commposition/', {'action': 'populate_common_positions'})
        self.assertTrue(CommPosition.objects.filter(project=self.project).exists())
