"""Plan tier and project role are separate questions (#147).

A free account can never create or own a project, by any path. Invited onto
someone else's project, it has that role's full rights; the global
Editor/Viewer groups decide nothing about either.

Run with::

    python manage.py test planner.tests.test_free_accounts \\
        --settings=audiopatch.test_settings
"""

import json

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth.models import Group, User
from django.test import RequestFactory, TestCase

from planner.admin import (
    CommBeltPackChannelInline, ConsoleInputInline, DeviceInputInline, ProjectAdmin,
)
from planner.admin_site import showstack_admin_site
from planner.models import (
    CommBeltPack, Console, Device, Project, ProjectMember, UserProfile,
)
from planner.plans import can_create_projects


def make_user(name, plan, groups=()):
    user = User.objects.create_user(name, password='pw', is_staff=True)
    UserProfile.objects.update_or_create(user=user, defaults={'account_type': plan})
    for group in groups:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    # Fresh: the profile signal cached user.userprofile as 'free'.
    return User.objects.get(pk=user.pk)


class Base(TestCase):

    def setUp(self):
        self.owner = make_user('premium_owner', 'paid')
        self.project = Project.objects.create(name='Show', owner=self.owner)
        # Registration leaves every sign-up in Viewer; a crew or member-admin
        # invite as editor never adds Editor.
        self.free_editor = make_user('free_editor', 'free', groups=('Viewer',))
        self.premium_editor = make_user('premium_editor', 'paid', groups=('Editor',))
        # Editor elsewhere, so in the Editor group, but a viewer here.
        self.viewer = make_user('viewer', 'free', groups=('Editor',))
        for user, role in ((self.free_editor, 'editor'), (self.premium_editor, 'editor'),
                           (self.viewer, 'viewer')):
            ProjectMember.objects.create(project=self.project, user=user, role=role,
                                         invited_by=self.owner)

    def login(self, user, project=None):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = (project or self.project).pk
        session.save()


class FreeAccountsCannotCreateProjects(Base):
    """Every path that makes a Project: the dashboard button, the admin add
    form (and its "+" popups, which open the same view), and duplicating."""

    def test_the_tier_check(self):
        self.assertFalse(can_create_projects(self.free_editor))
        self.assertFalse(can_create_projects(self.viewer))
        self.assertTrue(can_create_projects(self.owner))
        self.assertTrue(can_create_projects(self.premium_editor))
        for plan in ('beta', 'super_user'):
            UserProfile.objects.filter(user=self.owner).update(account_type=plan)
            self.assertTrue(can_create_projects(User.objects.get(pk=self.owner.pk)), plan)

    def test_dashboard_offers_creation_to_paid_only(self):
        self.login(self.free_editor)
        html = self.client.get('/dashboard/').content.decode()
        self.assertNotIn('href="/admin/planner/project/add/"', html)
        self.assertIn('Upgrade Required', html)
        self.login(self.owner)
        self.assertIn('href="/admin/planner/project/add/"',
                      self.client.get('/dashboard/').content.decode())

    def test_add_form_refuses_a_free_account(self):
        self.login(self.free_editor)
        self.assertEqual(403, self.client.get('/admin/planner/project/add/').status_code)
        resp = self.client.post('/admin/planner/project/add/', {'name': 'Mine'})
        self.assertEqual(403, resp.status_code)
        self.assertFalse(Project.objects.filter(owner=self.free_editor).exists())

    def test_add_form_works_for_a_paid_account(self):
        self.login(self.premium_editor)
        self.client.post('/admin/planner/project/add/', {'name': 'Mine', 'is_archived': ''})
        self.assertTrue(Project.objects.filter(owner=self.premium_editor, name='Mine').exists())

    def test_add_form_works_for_a_super_user_account(self):
        # The 'super_user' tier, not Django's is_superuser.
        account = make_user('tier_super_user', 'super_user')
        self.assertFalse(account.is_superuser)
        self.login(account)
        self.client.post('/admin/planner/project/add/', {'name': 'Mine', 'is_archived': ''})
        self.assertTrue(Project.objects.filter(owner=account, name='Mine').exists())

    def duplicate(self, user):
        self.login(user)
        return self.client.post('/admin/planner/project/', {
            'action': 'duplicate_project_action', ACTION_CHECKBOX_NAME: [self.project.pk],
            'confirm_duplicate': '1', 'new_name': f'Copy for {user.username}'})

    def test_duplicate_is_not_offered_to_a_free_editor(self):
        request = RequestFactory().get('/admin/planner/project/')
        request.user = self.free_editor
        admin = ProjectAdmin(Project, showstack_admin_site)
        self.assertNotIn('duplicate_project_action', admin.get_actions(request))
        request.user = self.premium_editor
        self.assertIn('duplicate_project_action', admin.get_actions(request))

    def test_duplicate_refuses_a_free_editor(self):
        self.duplicate(self.free_editor)
        self.assertFalse(Project.objects.filter(owner=self.free_editor).exists())
        self.assertEqual(1, Project.objects.count())

    def test_duplicate_works_for_a_paid_editor(self):
        self.duplicate(self.premium_editor)
        self.assertTrue(Project.objects.filter(owner=self.premium_editor,
                                               name='Copy for premium_editor').exists())


class InlineRightsFollowTheProjectRole(Base):
    """Inline rows used Django's model permissions, i.e. the global groups."""

    def rights(self, inline_class, parent, user):
        request = RequestFactory().get('/')
        request.user = user
        request.current_project = self.project
        inline = inline_class(type(parent), showstack_admin_site)
        return tuple(getattr(inline, f'has_{p}_permission')(request, parent)
                     for p in ('view', 'add', 'change', 'delete'))

    def test_each_role(self):
        parents = (
            (ConsoleInputInline, Console.objects.create(project=self.project, name='FOH')),
            (DeviceInputInline, Device.objects.create(project=self.project, name='Stage rack')),
            (CommBeltPackChannelInline, CommBeltPack.objects.create(project=self.project, bp_number=1)),
        )
        expected = ((self.owner, (True,) * 4), (self.free_editor, (True,) * 4),
                    (self.premium_editor, (True,) * 4),
                    (self.viewer, (True, False, False, False)))
        outsider = make_user('outsider', 'paid', groups=('Editor',))
        for inline_class, parent in parents:
            for user, rights in expected + ((outsider, (False,) * 4),):
                with self.subTest(inline=inline_class.__name__, user=user.username):
                    self.assertEqual(rights, self.rights(inline_class, parent, user))


class HeaderRoleIsTheCurrentProjects(Base):

    def test_editor_here_viewer_elsewhere(self):
        elsewhere = Project.objects.create(name='Earlier show', owner=self.premium_editor)
        ProjectMember.objects.filter(user=self.free_editor).delete()
        ProjectMember.objects.create(project=elsewhere, user=self.free_editor, role='viewer',
                                     invited_by=self.premium_editor)
        ProjectMember.objects.create(project=self.project, user=self.free_editor, role='editor',
                                     invited_by=self.owner)
        self.login(self.free_editor)
        resp = self.client.get('/audiopatch/audiochecklist/')
        self.assertEqual('editor', resp.context['user_role'])
        self.login(self.free_editor, elsewhere)
        self.assertEqual('viewer', self.client.get('/audiopatch/audiochecklist/').context['user_role'])


class FreeOwnersKeepTheirProjects(Base):
    """Interim rule: a free account that already owns a project (from before
    the rule) keeps an owner's full rights on it; it just can't make another."""

    def setUp(self):
        super().setUp()
        self.free_owner = make_user('free_owner', 'free', groups=('Viewer',))
        Project.objects.filter(pk=self.project.pk).update(owner=self.free_owner)
        self.project.refresh_from_db()

    def test_full_rights_on_the_owned_project(self):
        from planner.models import AudioChecklist, AudioChecklistTask
        checklist = AudioChecklist.objects.create(project=self.project, name='Show Check List')
        task = AudioChecklistTask.objects.create(checklist=checklist, task='Line check',
                                                 task_type='setup', sort_order=0)
        self.login(self.free_owner)
        html = self.client.get('/audiopatch/audiochecklist/').content.decode()
        self.assertIn('const CAN_EDIT = true;', html)
        resp = self.client.post('/audiopatch/audiochecklist/update-task/', json.dumps(
            {'task_id': task.pk, 'field': 'task', 'value': 'by the owner'}),
            content_type='application/json')
        self.assertEqual(200, resp.status_code, resp.content)
        task.refresh_from_db()
        self.assertEqual('by the owner', task.task)
        console = Console.objects.create(project=self.project, name='FOH')
        self.assertEqual((True,) * 4,
                         InlineRightsFollowTheProjectRole.rights(self, ConsoleInputInline,
                                                                 console, self.free_owner))
        self.assertEqual('owner', self.client.get('/audiopatch/audiochecklist/')
                         .context['user_role'])

    def test_but_cannot_create_another(self):
        self.assertFalse(can_create_projects(self.free_owner))
        self.login(self.free_owner)
        self.assertEqual(403, self.client.get('/admin/planner/project/add/').status_code)
        self.client.post('/admin/planner/project/', {
            'action': 'duplicate_project_action', ACTION_CHECKBOX_NAME: [self.project.pk],
            'confirm_duplicate': '1', 'new_name': 'Second show'})
        self.assertEqual(1, Project.objects.filter(owner=self.free_owner).count())


class SidebarFollowsTheCurrentProjectsRole(Base):
    """Child models are hidden for a viewer of the current project, not for
    anyone who is "a viewer somewhere and an editor nowhere"."""

    def sidebar(self, user, project):
        self.login(user, project)
        app_list = self.client.get('/admin/').context['app_list']
        return {m['object_name'].lower() for app in app_list for m in app['models']}

    def test_role_on_the_current_project_decides(self):
        elsewhere = Project.objects.create(name='Other show', owner=self.premium_editor)
        # Editor here, viewer elsewhere; viewer here, editor elsewhere.
        ProjectMember.objects.create(project=elsewhere, user=self.free_editor, role='viewer',
                                     invited_by=self.premium_editor)
        ProjectMember.objects.create(project=elsewhere, user=self.viewer, role='editor',
                                     invited_by=self.premium_editor)
        self.assertIn('speakerarray', self.sidebar(self.free_editor, self.project))
        self.assertNotIn('speakerarray', self.sidebar(self.free_editor, elsewhere))
        self.assertNotIn('speakerarray', self.sidebar(self.viewer, self.project))
        self.assertIn('speakerarray', self.sidebar(self.viewer, elsewhere))
