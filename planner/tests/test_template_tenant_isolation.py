"""Tenant isolation for the three template features.

Console Template Library import, Audio Checklist templates and COMM Config
templates each take a template id from the request body, and each had a way
across the tenant boundary:

* the console import looked the id up with nothing but ``is_template=True``;
* the library was routed by a bare lambda outside ``admin_view()``;
* COMM "save as template" deleted every tenant's template of the same name;
* loading a checklist template into the current project never checked the
  per-project edit role, so a viewer could wipe the checklist.

Run with::

    python manage.py test planner.tests.test_template_tenant_isolation \\
        --settings=audiopatch.test_settings
"""

import json

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from planner.models import (
    AudioChecklist, AudioChecklistTask, AudioChecklistTemplate,
    AudioChecklistTemplateTask, CommConfig, Console, ConsoleInput, Project,
    ProjectMember, UserProfile,
)
from planner.tests.test_tenant_isolation import TenantIsolationBase


class _TemplateBase(TenantIsolationBase):

    def setUp(self):
        super().setUp()
        # Project B's console doubles as B's library template.
        self.console_b.is_template = True
        self.console_b.save()

        # A viewer-role member of project A, who owns a project of their own
        # (so they DO have a template they are entitled to import elsewhere).
        self.viewer = User.objects.create_user(
            'viewer_a', 'v@example.com', 'pw', is_staff=True,
        )
        UserProfile.objects.update_or_create(
            user=self.viewer, defaults={'account_type': 'paid'},
        )
        ProjectMember.objects.create(
            project=self.project_a, user=self.viewer, role='viewer',
            invited_by=self.user_a,
        )
        self.viewer_project = Project.objects.create(
            name='Viewer Own', owner=self.viewer,
        )
        self.viewer_template = Console.objects.create(
            project=self.viewer_project, name='Viewer Tmpl', is_template=True,
        )
        self.viewer_client = self._client_for(self.viewer, self.project_a)

    def _client_for(self, user, project):
        c = Client()
        c.force_login(user)
        s = c.session
        s['current_project_id'] = project.id
        s.save()
        return c

    def post_json(self, client, name, payload):
        return client.post(
            reverse(f'planner:{name}'), data=json.dumps(payload),
            content_type='application/json',
        )


# ---------------------------------------------------------------------------
# Console Template Library
# ---------------------------------------------------------------------------

class ConsoleTemplateLibraryTests(_TemplateBase):

    url = '/admin/planner/console/template-library/'

    def _project_a_consoles_from_b(self):
        return Console.objects.filter(
            project=self.project_a, name__contains=self.MARKER_B,
        )

    def test_route_lives_on_the_showstack_admin_site(self):
        self.assertEqual(self.url, reverse('admin:console_template_library'))

    def test_old_root_path_redirects_to_admin_route(self):
        resp = self.client.get('/console-template-library/')
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)

    def test_non_staff_user_is_sent_to_admin_login(self):
        """admin_view() applies the staff gate the lambda route never had."""
        civilian = User.objects.create_user('civilian', 'c@example.com', 'pw')
        resp = self._client_for(civilian, self.project_a).get(self.url)
        self.assertEqual(302, resp.status_code)
        self.assertIn('/admin/login/', resp['Location'])

    def test_user_a_cannot_import_user_b_template(self):
        resp = self.client.post(self.url, {'template_id': self.console_b.id})
        self.assertEqual(302, resp.status_code)
        self.assertFalse(
            self._project_a_consoles_from_b().exists(),
            "project B's template console was copied into project A",
        )
        self.assertFalse(
            ConsoleInput.objects.filter(
                console__project=self.project_a,
                source__contains=self.MARKER_B,
            ).exists(),
        )

    def test_import_view_itself_rejects_user_b_template(self):
        """Same IDOR, called on the view directly so it cannot pass just
        because a URL failed to route to it (the admin's <object_id>/
        catch-all also answers a POST to this path with a 302)."""
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from planner.admin_site import showstack_admin_site

        request = RequestFactory().post(
            self.url, {'template_id': self.console_b.id})
        request.user = self.user_a
        request.current_project = self.project_a
        request.session = {}
        request._messages = FallbackStorage(request)
        showstack_admin_site._registry[Console].console_template_library_view(
            request)
        self.assertFalse(self._project_a_consoles_from_b().exists())

    def test_library_listing_does_not_show_user_b_template(self):
        resp = self.client.get(self.url)
        self.assertEqual(200, resp.status_code)
        self.assertNoLeak(resp, 'console template library')

    def test_owner_can_still_import_own_template_from_another_project(self):
        other = Project.objects.create(name='A Other', owner=self.user_a)
        tmpl = Console.objects.create(project=other, name='Mine', is_template=True)
        ConsoleInput.objects.create(console=tmpl, input_ch='1', source='Kick')
        resp = self.client.post(self.url, {'template_id': tmpl.id})
        self.assertEqual(302, resp.status_code)
        copy = Console.objects.get(project=self.project_a, name__startswith='Mine')
        self.assertEqual(['Kick'], list(
            copy.consoleinput_set.values_list('source', flat=True)))

    def test_viewer_cannot_import_into_project(self):
        before = Console.objects.filter(project=self.project_a).count()
        resp = self.viewer_client.post(
            self.url, {'template_id': self.viewer_template.id},
        )
        self.assertEqual(302, resp.status_code)
        self.assertEqual(
            before, Console.objects.filter(project=self.project_a).count(),
            'a viewer-role member imported a console into the project',
        )

    def test_superuser_is_exempt(self):
        su = self._client_for(self.superuser, self.project_a)
        su.post(self.url, {'template_id': self.console_b.id})
        self.assertTrue(self._project_a_consoles_from_b().exists())


# ---------------------------------------------------------------------------
# Audio Checklist templates
# ---------------------------------------------------------------------------

class AudioChecklistTemplateTests(_TemplateBase):

    def setUp(self):
        super().setUp()
        self.checklist_a = AudioChecklist.objects.create(
            project=self.project_a, name='FOH Check List',
        )
        self.task_a = AudioChecklistTask.objects.create(
            checklist=self.checklist_a, task='Line check AAA',
        )
        self.template_b = AudioChecklistTemplate.objects.create(
            project=self.project_b, name=f'Tmpl {self.MARKER_B}',
            created_by=self.user_b,
        )
        AudioChecklistTemplateTask.objects.create(
            template=self.template_b, task=f'Task {self.MARKER_B}',
        )
        self.viewer_own_template = AudioChecklistTemplate.objects.create(
            project=self.viewer_project, name='Viewer list', created_by=self.viewer,
        )
        AudioChecklistTemplateTask.objects.create(
            template=self.viewer_own_template, task='Viewer task',
        )

    def _a_tasks(self):
        return list(AudioChecklistTask.objects.filter(
            checklist__project=self.project_a,
        ).values_list('task', flat=True))

    def test_anonymous_requests_are_rejected(self):
        for name, payload in (
            ('audio_checklist_save_template', {'name': 'x'}),
            ('audio_checklist_load_template', {'template_id': self.template_b.id}),
            ('audio_checklist_delete_template', {'template_id': self.template_b.id}),
        ):
            resp = self.post_json(self.anon, name, payload)
            self.assertEqual(302, resp.status_code, name)
            self.assertIn('/login/', resp['Location'], name)
        self.assertTrue(
            AudioChecklistTemplate.objects.filter(pk=self.template_b.pk).exists())

    def test_user_a_cannot_load_user_b_template(self):
        resp = self.post_json(
            self.client, 'audio_checklist_load_template',
            {'template_id': self.template_b.id},
        )
        self.assertEqual(404, resp.status_code)
        self.assertEqual(['Line check AAA'], self._a_tasks())

    def test_user_a_cannot_delete_user_b_template(self):
        resp = self.post_json(
            self.client, 'audio_checklist_delete_template',
            {'template_id': self.template_b.id},
        )
        self.assertEqual(404, resp.status_code)
        self.assertTrue(
            AudioChecklistTemplate.objects.filter(pk=self.template_b.pk).exists())

    def test_viewer_cannot_load_template_over_project_checklist(self):
        resp = self.post_json(
            self.viewer_client, 'audio_checklist_load_template',
            {'template_id': self.viewer_own_template.id},
        )
        self.assertEqual(403, resp.status_code)
        self.assertEqual(
            ['Line check AAA'], self._a_tasks(),
            "a viewer replaced the project's checklist",
        )

    def test_owner_can_still_load_own_template(self):
        mine = AudioChecklistTemplate.objects.create(
            project=self.project_a, name='Mine', created_by=self.user_a,
        )
        AudioChecklistTemplateTask.objects.create(template=mine, task='Ring out')
        resp = self.post_json(
            self.client, 'audio_checklist_load_template', {'template_id': mine.id},
        )
        self.assertEqual(200, resp.status_code)
        self.assertEqual(['Ring out'], self._a_tasks())


# ---------------------------------------------------------------------------
# COMM Config templates
# ---------------------------------------------------------------------------

class CommConfigTemplateTests(_TemplateBase):

    def setUp(self):
        super().setUp()
        self.comm_template_b = CommConfig.objects.create(
            project=self.project_b, name='Main', template_name='Main',
            is_template=True,
        )

    def test_anonymous_requests_are_rejected(self):
        for name, payload in (
            ('comm_config_save_as_template',
             {'config_id': self.comm_config_b.id, 'template_name': 'Main'}),
            ('comm_config_load_template',
             {'template_id': self.comm_template_b.id}),
        ):
            resp = self.post_json(self.anon, name, payload)
            self.assertEqual(302, resp.status_code, name)
            self.assertIn('/login/', resp['Location'], name)
        self.assertTrue(
            CommConfig.objects.filter(pk=self.comm_template_b.pk).exists())

    def test_save_as_template_does_not_delete_other_tenants_same_name(self):
        resp = self.post_json(
            self.client, 'comm_config_save_as_template',
            {'config_id': self.comm_config_a.id, 'template_name': 'Main'},
        )
        self.assertEqual(200, resp.status_code, resp.content)
        self.assertTrue(
            CommConfig.objects.filter(pk=self.comm_template_b.pk).exists(),
            "saving a template deleted another tenant's template of that name",
        )
        tmpl = CommConfig.objects.get(pk=resp.json()['template_id'])
        self.assertEqual(self.project_a, tmpl.project)
        self.assertEqual(
            ['PLAAA'], list(tmpl.partylines.values_list('label', flat=True)))

    def test_save_as_template_replaces_own_same_name(self):
        old = CommConfig.objects.create(
            project=self.project_a, name='Main', template_name='Main',
            is_template=True,
        )
        self.post_json(
            self.client, 'comm_config_save_as_template',
            {'config_id': self.comm_config_a.id, 'template_name': 'Main'},
        )
        self.assertFalse(CommConfig.objects.filter(pk=old.pk).exists())
        self.assertEqual(1, CommConfig.objects.filter(
            project=self.project_a, is_template=True, template_name='Main',
        ).count())

    def test_saved_template_shows_in_picker(self):
        self.post_json(
            self.client, 'comm_config_save_as_template',
            {'config_id': self.comm_config_a.id, 'template_name': 'Picker'},
        )
        resp = self.client.get(reverse('planner:comm_config_list_templates'))
        names = [t['template_name'] for t in resp.json()['templates']]
        self.assertEqual(['Picker'], names)

    def test_user_a_cannot_load_user_b_template(self):
        before = CommConfig.objects.filter(project=self.project_a).count()
        resp = self.post_json(
            self.client, 'comm_config_load_template',
            {'template_id': self.comm_template_b.id},
        )
        self.assertNotEqual(200, resp.status_code)
        self.assertEqual(
            before, CommConfig.objects.filter(project=self.project_a).count())
