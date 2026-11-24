"""The admin sidebar: what each role sees, section by section.

The sections live in ``planner/admin_ordering.py``. These pin the whole
sidebar for a superuser, an owner, an editor and a viewer of the current
project, so a change to a permission or to the sections shows up here as a
diff of names rather than as a row somebody notices is missing.

Run with::

    python manage.py test planner.tests.test_sidebar \\
        --settings=audiopatch.test_settings
"""
import re
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner import admin_ordering
from planner.admin_site import showstack_admin_site
from planner.models import Project, ProjectMember
from planner.tests.test_free_accounts import make_user

SYSTEM = ['Console', 'Device', 'IPAddressManager', 'SystemProcessor',
          'SoundvisionPrediction', 'SpeakerArray', 'SpeakerCabinet',
          'Amp', 'PACableSchedule',
          'PowerDistributionPlan', 'AmplifierAssignment', 'WiringDiagram']
COMMS = ['CommBeltPack', 'CommConfig']
MICS = ['ShowflowImport', 'ShowDay']
SHOW = ['AudioChecklist', 'MultitrackSession']

EXPECTED = {
    'superuser': [
        ('Project', ['Project', 'Location', 'ProjectMember', 'Invitation', 'Crew']),
        ('System', SYSTEM),
        ('Comms', COMMS),
        ('Mics', MICS),
        ('Show', SHOW),
        ('Libraries', ['SourceHardwareOption', 'CabinetModel', 'AmplifierProfile',
                       'CommDeviceModel']),
        ('Admin', ['User', 'Group', 'UserProfile']),
    ],
    'owner': [
        ('Project', ['Project', 'Location', 'ProjectMember', 'Invitation']),
        ('System', SYSTEM),
        ('Comms', COMMS),
        ('Mics', MICS),
        ('Show', SHOW),
        ('Libraries', ['SourceHardwareOption']),
    ],
    'editor': [
        ('Project', ['Project', 'Location']),
        ('System', SYSTEM),
        ('Comms', COMMS),
        ('Mics', MICS),
        ('Show', SHOW),
        ('Libraries', ['SourceHardwareOption']),
    ],
    'viewer': [
        ('Project', ['Project', 'Location']),
        ('System', [name for name in SYSTEM
                    if name not in ('SpeakerArray', 'SpeakerCabinet', 'AmplifierAssignment')]),
        ('Comms', COMMS),
        ('Mics', MICS),
        ('Show', SHOW),
        ('Libraries', ['SourceHardwareOption']),
    ],
}


class SidebarFixture:
    """One project and a user in each role. A mixin, not a TestCase, so the
    browser tests can put it on a live-server case."""

    def setUp(self):
        super().setUp()
        owner = make_user('premium_owner', 'paid')
        self.project = Project.objects.create(name='Show', owner=owner)
        # Registration leaves every sign-up in Viewer; an invite as editor
        # never adds Editor. The viewer is an editor elsewhere, so in Editor.
        self.users = {
            'superuser': User.objects.create_superuser('boss', 'boss@example.com', 'pw'),
            'owner': owner,
            'editor': make_user('free_editor', 'free', groups=('Viewer',)),
            'viewer': make_user('viewer', 'free', groups=('Editor',)),
        }
        for role in ('editor', 'viewer'):
            ProjectMember.objects.create(project=self.project, user=self.users[role],
                                         role=role, invited_by=owner)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def page(self, role, url=None):
        self.login(self.users[role])
        response = self.client.get(url or reverse('admin:planner_console_changelist'))
        self.assertEqual(200, response.status_code, role)
        return response

    def sidebar(self, role):
        return [(str(section['name']), [m['object_name'] for m in section['models']])
                for section in self.page(role).context['available_apps']]

    def labels(self, role):
        return {m['object_name']: str(m['name'])
                for section in self.page(role).context['available_apps']
                for m in section['models']}


class SidebarBase(SidebarFixture, TestCase):
    pass


class SidebarContentsByRole(SidebarBase):

    def test_superuser(self):
        self.assertEqual(EXPECTED['superuser'], self.sidebar('superuser'))

    def test_owner(self):
        self.assertEqual(EXPECTED['owner'], self.sidebar('owner'))

    def test_editor(self):
        self.assertEqual(EXPECTED['editor'], self.sidebar('editor'))

    def test_viewer(self):
        self.assertEqual(EXPECTED['viewer'], self.sidebar('viewer'))

    def test_the_dashboard_and_an_app_index_show_the_same_sidebar(self):
        for role, expected in EXPECTED.items():
            with self.subTest(role=role):
                self.assertEqual(expected, [
                    (str(s['name']), [m['object_name'] for m in s['models']])
                    for s in self.page(role, reverse('admin:index')).context['available_apps']])

    def test_the_names_people_read(self):
        labels = self.labels('superuser')
        self.assertEqual('Amplifiers', labels['Amp'])
        self.assertEqual('Power Plan Amps', labels['AmplifierAssignment'])
        self.assertEqual('Comm Configurations', labels['CommConfig'])
        self.assertEqual('Mic Planner', labels['ShowflowImport'])
        self.assertEqual('IP Address Manager', labels['IPAddressManager'])
        self.assertNotIn('ShowTemplate', labels)


class HiddenRowsKeepTheirPages(SidebarBase):
    """The sidebar narrows what is listed, never what may be opened."""

    def test_catalogues_and_templates_still_open_for_an_editor(self):
        for name in ('admin:planner_cabinetmodel_changelist',
                     'admin:planner_amplifierprofile_changelist',
                     'admin:planner_showtemplate_changelist'):
            with self.subTest(page=name):
                self.page('editor', reverse(name))

    def test_manage_templates_is_on_the_consoles_list_and_the_load_page(self):
        link = 'href="%s"' % reverse('admin:planner_showtemplate_changelist')
        for name in ('admin:planner_console_changelist', 'admin:console_template_library'):
            with self.subTest(page=name):
                html = self.page('editor', reverse(name)).content.decode()
                self.assertIn('Manage templates', html)
                # Once in the page body; never in the sidebar.
                self.assertEqual(1, html.count(link))


class GroupsFollowTheModel(SidebarBase):
    """Folding rows are paired by model name in the markup, so the wording of
    a link has no say in it (the old script matched on link text, and a
    rename silently unfolded the group)."""

    def parents(self, role):
        html = self.page(role).content.decode()
        return dict(re.findall(
            r'<tr class="model-(\w+)[^"]*" data-sidebar-parent="(\w+)">', html)), html

    def test_children_name_their_parent(self):
        parents, html = self.parents('editor')
        self.assertEqual({'speakerarray': 'soundvisionprediction',
                          'speakercabinet': 'soundvisionprediction',
                          'amplifierassignment': 'powerdistributionplan'}, parents)
        for parent in set(parents.values()):
            self.assertIn('<tr class="model-%s' % parent, html)

    def test_a_viewer_has_no_folding_rows(self):
        self.assertEqual({}, self.parents('viewer')[0])

    def test_the_script_reads_no_link_text(self):
        html = self.page('editor').content.decode()
        script = html[html.index('<!-- Collapsible Sidebar Menu -->'):]
        script = script[:script.index('</script>')]
        self.assertIn('data-sidebar-parent', script)
        self.assertNotIn('textContent.trim()', script)
        for label in ('Soundvision Predictions', 'Power Plan Amps', 'Amplifier Profiles'):
            # Old localStorage keys are the one place a label may appear.
            self.assertLessEqual(script.count("'%s'" % label), 1, label)

    def test_section_headings_are_text_not_links(self):
        html = self.page('superuser').content.decode()
        for heading in ('Project', 'System', 'Comms', 'Mics', 'Show', 'Libraries', 'Admin'):
            self.assertIn('<span class="section">%s</span>' % heading, html)
        self.assertNotIn('class="section" title=', html)


class EveryRegisteredModelIsPlaced(SidebarBase):

    def test_each_model_is_in_a_section_or_deliberately_left_out(self):
        in_sections = {name for _key, _heading, names in admin_ordering.SECTIONS
                       for name in names}
        registered = {model._meta.model_name for model in showstack_admin_site._registry
                      if model._meta.app_label in ('planner', 'accounts', 'auth')}
        pages = {page['object_name'].lower() for page in admin_ordering._pages()}
        self.assertEqual(set(), in_sections & admin_ordering.NOT_IN_SIDEBAR)
        self.assertEqual(
            set(), registered - in_sections - admin_ordering.NOT_IN_SIDEBAR,
            'Add these to a section in planner/admin_ordering.py, or to NOT_IN_SIDEBAR')
        self.assertEqual(set(), in_sections - registered - pages,
                         'A section names something that is not registered')

    def test_groups_only_name_listed_rows(self):
        in_sections = {name for _key, _heading, names in admin_ordering.SECTIONS
                       for name in names}
        for parent, children in admin_ordering.GROUPS.items():
            self.assertLessEqual({parent, *children}, in_sections)


class WiringDiagramOnTheDashboards(SidebarBase):
    url = reverse('planner:wiring_diagram') + '?view=overview'

    def no_graph(self):
        """Fail if anything builds the connection graph."""
        return mock.patch('planner.connections.graph.project_graph',
                          side_effect=AssertionError('project_graph() was called'))

    def test_admin_dashboard_card_follows_mic_tracker(self):
        for role in EXPECTED:
            with self.subTest(role=role), self.no_graph(), \
                    mock.patch('planner.views_wiring.project_graph',
                               side_effect=AssertionError('project_graph() was called')):
                html = self.page(role, reverse('admin:index')).content.decode()
                card = html.index('class="ss-card wiring" href="%s"' % self.url)
                self.assertLess(html.index('class="ss-card mic"'), card)
                self.assertLess(card, html.index('class="ss-card power"'))
                self.assertEqual(
                    200, self.client.get(reverse('planner:dashboard_stats')).status_code)

    def test_system_dashboard_quick_action_follows_pa_cables(self):
        # The page with the quick actions is the System Dashboard,
        # /audiopatch/dashboard/. (/dashboard/ is the project list.)
        with self.no_graph():
            html = self.page('editor', reverse('planner:system-dashboard')).content.decode()
        action = html.index('<a href="%s" class="quick-action">' % self.url)
        self.assertLess(html.index('PA Cables'), action)
        self.assertLess(action, html.index('<a href="/admin/planner/commbeltpack/" class="quick-action">'))

    def test_the_card_opens_the_overview(self):
        response = self.page('viewer', self.url)
        self.assertEqual('overview', response.context['tab'])
