"""COMM Config write endpoints need edit rights on the CURRENT project.

They scoped every lookup to the current project, so another tenant's rows
404, but never asked about the role on it: a viewer could add, rename and
delete partylines, roles, ports and whole configs with a fetch(). The LAN
endpoint did not even scope -- it fetched the network port by id alone, so
anyone signed in could rewrite another tenant's base-station IP settings.

Same two cases as test_project_roles (#18): viewer on A + editor on B can't
write on A; editor on A isn't blocked by viewer on B.

Run with::

    python manage.py test planner.tests.test_comm_config_roles \\
        --settings=audiopatch.test_settings
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.models import (
    CommConfig, CommConfigNetworkPort, CommConfigPartyline, CommCrewName,
    Project, ProjectMember,
)
from planner.views import _seed_factory_defaults


def make_config(project, name):
    config = CommConfig.objects.create(project=project, name=name)
    _seed_factory_defaults(config)
    CommConfigNetworkPort.objects.create(config=config, port_number=1,
                                         traffic_type='admin')
    return config


class CommConfigRoleTests(TestCase):

    def setUp(self):
        owner_a = User.objects.create_user('owner_a', 'oa@example.com', 'pw')
        owner_b = User.objects.create_user('owner_b', 'ob@example.com', 'pw')
        self.project_a = Project.objects.create(name='A', owner=owner_a)
        self.project_b = Project.objects.create(name='B', owner=owner_b)
        self.config_a = make_config(self.project_a, 'Comms A')
        self.config_b = make_config(self.project_b, 'Comms B')
        CommCrewName.objects.create(project=self.project_a, name='Stage Left')

        self.user = User.objects.create_user('crew', 'crew@example.com', 'pw',
                                             is_staff=True)
        self.client.force_login(self.user)

    def member(self, project, role):
        ProjectMember.objects.create(user=self.user, project=project, role=role,
                                     invited_by=project.owner)

    def use(self, project):
        session = self.client.session
        session['current_project_id'] = project.pk
        session.save()

    def post(self, name, payload):
        return self.client.post(reverse(f'planner:{name}'), json.dumps(payload),
                                content_type='application/json')

    def write_calls(self, config):
        """Every COMM Config write endpoint, with a payload that would succeed."""
        pl = config.partylines.order_by('channel_number').first()
        port = config.port_assignments.first()
        lan = config.network_ports.first()
        crew = CommCrewName.objects.filter(project=config.project).first()
        calls = [
            ('comm_config_create', {'name': 'New', 'device_type': 'arcadia'}),
            ('comm_config_update_partyline', {'partyline_id': pl.id, 'label': 'HACKED'}),
            ('comm_config_add_partyline', {'config_id': config.id}),
            ('comm_config_assign_port', {'port_id': port.id, 'port_label': 'HACKED'}),
            ('comm_config_update_setting', {'config_id': config.id,
                                            'field': 'name', 'value': 'HACKED'}),
            ('comm_config_update_lan', {'lan_id': lan.id, 'static_ip': '6.6.6.6'}),
            ('comm_config_add_role', {'config_id': config.id, 'device_type': 'FSII-BP',
                                      'label': 'HACKED'}),
            ('comm_config_add_dante', {'config_id': config.id, 'label': 'HACKED'}),
            ('comm_config_add_session', {'config_id': config.id, 'session_type': 'B.FSII'}),
            ('comm_config_add_roleset', {'config_id': config.id}),
            ('comm_config_save_as_template', {'config_id': config.id,
                                              'template_name': 'HACKED'}),
            ('comm_config_delete_partyline', {'partyline_id': pl.id}),
            ('comm_config_delete', {'config_id': config.id}),
        ]
        if crew:
            calls.append(('comm_config_delete_crew_name', {'crew_name_id': crew.id}))
        calls.append(('comm_config_add_crew_name', {'name': 'HACKED'}))
        return calls

    def snapshot(self, project):
        configs = CommConfig.objects.filter(project=project)
        return {
            'configs': sorted(configs.values_list('name', flat=True)),
            'partylines': sorted(CommConfigPartyline.objects.filter(
                config__project=project).values_list('channel_number', 'label')),
            'ports': sorted(configs.values_list('port_assignments__port_label', flat=True),
                            key=str),
            'roles': configs.values_list('roles__id', flat=True).count(),
            'dante': configs.values_list('dante_channels__id', flat=True).count(),
            'sessions': configs.values_list('sessions__id', flat=True).count(),
            'rolesets': configs.values_list('rolesets__id', flat=True).count(),
            'lan': sorted(CommConfigNetworkPort.objects.filter(
                config__project=project).values_list('static_ip', flat=True), key=str),
            'crew': sorted(CommCrewName.objects.filter(project=project)
                           .values_list('name', flat=True)),
        }

    def assert_read_only(self, project, config):
        before = self.snapshot(project)
        for name, payload in self.write_calls(config):
            response = self.post(name, payload)
            self.assertEqual(response.status_code, 403, name)
            self.assertEqual(response.json(), {'error': 'Read-only access.'}, name)
        self.assertEqual(self.snapshot(project), before)

    # -- viewer on A + editor on B ------------------------------------------

    def test_viewer_on_a_cannot_write_on_a_though_editor_on_b(self):
        self.member(self.project_a, 'viewer')
        self.member(self.project_b, 'editor')
        self.use(self.project_a)
        self.assert_read_only(self.project_a, self.config_a)

    def test_the_viewer_can_still_read_and_export(self):
        self.member(self.project_a, 'viewer')
        self.use(self.project_a)
        self.assertEqual(self.client.get(
            reverse('planner:comm_config_editor', args=[self.config_a.pk])).status_code, 200)
        role = self.config_a.roles.first()
        if role:
            self.assertEqual(self.client.get(reverse('planner:comm_config_role_chips'),
                                             {'role_id': role.id}).status_code, 200)

    # -- editor on A + viewer on B ------------------------------------------

    def test_editor_on_a_is_not_blocked_by_viewer_on_b(self):
        self.member(self.project_a, 'editor')
        self.member(self.project_b, 'viewer')
        self.use(self.project_a)
        pl = self.config_a.partylines.order_by('channel_number').first()
        response = self.post('comm_config_update_partyline',
                             {'partyline_id': pl.id, 'label': 'Director'})
        self.assertEqual(response.status_code, 200)
        pl.refresh_from_db()
        self.assertEqual(pl.label, 'Director')
        self.assertEqual(self.post('comm_config_add_partyline',
                                   {'config_id': self.config_a.id}).status_code, 200)

        self.use(self.project_b)
        self.assert_read_only(self.project_b, self.config_b)

    def test_every_comm_config_url_but_the_reads_refuses_a_viewer(self):
        # Catches the next endpoint added without the guard: anything named
        # comm_config_* that is not a page, a read or an export must 403 a
        # viewer before it looks at the body.
        from django.urls import get_resolver
        reads = {'comm_config', 'comm_config_editor', 'comm_config_role_chips',
                 'comm_config_list_templates', 'comm_config_export',
                 'comm_config_export_freespeak'}
        names = {getattr(p, 'name', None) for p in get_resolver('planner.urls').url_patterns}
        names = {n for n in names if n and n.startswith('comm_config')} - reads
        self.assertGreaterEqual(len(names), 25)
        self.member(self.project_a, 'viewer')
        self.use(self.project_a)
        for name in sorted(names):
            response = self.post(name, {})
            self.assertEqual(response.status_code, 403, name)

    def test_owner_can_write(self):
        self.client.force_login(self.project_a.owner)
        self.use(self.project_a)
        self.assertEqual(self.post('comm_config_create',
                                   {'name': 'Second', 'device_type': 'arcadia'}).status_code, 200)

    # -- LAN: scoped now --------------------------------------------------------

    def test_lan_settings_of_another_tenant_cannot_be_written(self):
        self.member(self.project_a, 'editor')
        self.use(self.project_a)
        lan_b = self.config_b.network_ports.first()
        response = self.post('comm_config_update_lan',
                             {'lan_id': lan_b.id, 'static_ip': '6.6.6.6'})
        self.assertEqual(response.status_code, 404)
        lan_b.refresh_from_db()
        self.assertNotEqual(lan_b.static_ip, '6.6.6.6')

    def test_own_lan_settings_still_save(self):
        self.member(self.project_a, 'editor')
        self.use(self.project_a)
        lan = self.config_a.network_ports.first()
        self.assertEqual(self.post('comm_config_update_lan',
                                   {'lan_id': lan.id, 'static_ip': '10.0.0.5'}).status_code, 200)
        lan.refresh_from_db()
        self.assertEqual(lan.static_ip, '10.0.0.5')


class CommConfigPageRenderingTests(CommConfigRoleTests):
    """The page offers a viewer no edit controls: the panels are one disabled
    fieldset (values shown, nothing changeable, add/delete buttons hidden),
    and New / Templates / Save as Template / Delete are not rendered. Export
    stays. Editors and owners see the page as before."""

    def page(self, config=None):
        url = (reverse('planner:comm_config_editor', args=[config.pk]) if config
               else reverse('planner:comm_config'))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    EDIT_ONLY = ('onclick="deleteConfig(', 'onclick="openSaveTemplateModal(')
    LIST_EDIT_ONLY = ('onclick="createConfig(\'arcadia\')"', 'onclick="openLoadTemplateModal()"')

    def assert_editable(self):
        page = self.page(self.config_a)
        self.assertIn('<fieldset class="cc-panels">', page)
        self.assertNotIn('<p class="cc-readonly-note"', page)
        for control in self.EDIT_ONLY:
            self.assertIn(control, page)
        self.assertIn('onclick="exportCca(', page)
        listing = self.page()
        for control in self.LIST_EDIT_ONLY:
            self.assertIn(control, listing)

    def test_viewer_sees_it_read_only_with_export(self):
        self.member(self.project_a, 'viewer')
        self.member(self.project_b, 'editor')   # editor elsewhere changes nothing here
        self.use(self.project_a)
        page = self.page(self.config_a)
        self.assertIn('<fieldset class="cc-panels" disabled>', page)
        self.assertIn('<p class="cc-readonly-note"', page)
        for control in self.EDIT_ONLY:
            self.assertNotIn(control, page)
        self.assertIn('onclick="exportCca(', page)
        # The panels' controls are all inside the disabled fieldset.
        start, end = page.index('<fieldset class="cc-panels"'), page.index('</fieldset>')
        self.assertIn('class="cc-pl-name"', page[start:end])
        self.assertNotIn('class="cc-pl-name"', page[:start] + page[end:])
        listing = self.page()
        for control in self.LIST_EDIT_ONLY:
            self.assertNotIn(control, listing)
        self.assertIn('Comms A', listing)

    def test_viewer_can_export_a_freespeak_config(self):
        config = make_config(self.project_a, 'FSII')
        config.device_type = 'freespeak'
        config.save()
        self.member(self.project_a, 'viewer')
        self.use(self.project_a)
        page = self.page(config)
        self.assertIn(reverse('planner:comm_config_export_freespeak', args=[config.pk]), page)
        self.assertIn('<fieldset class="cc-panels" disabled>', page)

    def test_editor_sees_the_edit_controls(self):
        self.member(self.project_a, 'editor')
        self.member(self.project_b, 'viewer')   # viewer elsewhere changes nothing here
        self.use(self.project_a)
        self.assert_editable()

    def test_owner_sees_the_edit_controls(self):
        self.client.force_login(self.project_a.owner)
        self.project_a.owner.is_staff = True
        self.project_a.owner.save()
        self.use(self.project_a)
        self.assert_editable()
