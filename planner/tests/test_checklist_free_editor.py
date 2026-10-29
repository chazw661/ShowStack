"""Checklist rights by project role, whatever the plan tier (#147).

A free account can't own a project but can be invited onto one; an editor
then edits like any editor. Role and plan are separate questions, and the
global Viewer/Editor groups answer neither.

Run with::

    python manage.py test planner.tests.test_checklist_free_editor \\
        --settings=audiopatch.test_settings
"""

import json

from django.contrib.auth.models import Group, User
from django.test import TestCase

from planner.models import (
    AudioChecklist, AudioChecklistTask, Project, ProjectMember, UserProfile,
)


def make_user(name, plan, groups=()):
    user = User.objects.create_user(name, password='pw', is_staff=True)
    UserProfile.objects.update_or_create(user=user, defaults={'account_type': plan})
    for group in groups:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    # Fresh: the profile signal cached user.userprofile as 'free'.
    return User.objects.get(pk=user.pk)


class ChecklistRightsByRoleTests(TestCase):

    def setUp(self):
        self.owner = make_user('premium_owner', 'paid')
        self.project = Project.objects.create(name='Show', owner=self.owner)
        # Registration puts every new account in the global Viewer group, so a
        # free user invited as editor is in both groups.
        self.free_editor = make_user('free_editor', 'free', groups=('Viewer', 'Editor'))
        self.premium_editor = make_user('premium_editor', 'paid', groups=('Editor',))
        self.viewer = make_user('viewer', 'free', groups=('Viewer',))
        for user, role in ((self.free_editor, 'editor'), (self.premium_editor, 'editor'),
                           (self.viewer, 'viewer')):
            ProjectMember.objects.create(project=self.project, user=user, role=role,
                                         invited_by=self.owner)
        checklist = AudioChecklist.objects.create(project=self.project, name='Show Check List')
        self.task = AudioChecklistTask.objects.create(
            checklist=checklist, task='Line check', task_type='setup', sort_order=0)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def page_can_edit(self, user):
        self.login(user)
        html = self.client.get('/audiopatch/audiochecklist/').content.decode()
        return 'const CAN_EDIT = true;' in html

    def endpoint_can_edit(self, user):
        self.login(user)
        resp = self.client.post('/audiopatch/audiochecklist/update-task/', json.dumps(
            {'task_id': self.task.pk, 'field': 'task', 'value': f'by {user.username}'}),
            content_type='application/json')
        self.task.refresh_from_db()
        wrote = self.task.task == f'by {user.username}'
        self.assertEqual(wrote, resp.status_code == 200, resp.content)
        return wrote

    def test_page_and_endpoints_agree_on_each_role(self):
        expected = [(self.owner, True), (self.free_editor, True),
                    (self.premium_editor, True), (self.viewer, False)]
        for user, enabled in expected:
            with self.subTest(user=user.username):
                self.assertEqual(enabled, self.page_can_edit(user), 'page')
                self.assertEqual(enabled, self.endpoint_can_edit(user), 'endpoint')

    def test_free_account_that_accepts_an_editor_invite_can_edit(self):
        """The real path: a free sign-up (not staff, in the global Viewer
        group, as registration leaves it) accepts an editor invitation."""
        from planner.models import Invitation
        newcomer = User.objects.create_user('newcomer', email='new@example.com', password='pw')
        UserProfile.objects.update_or_create(user=newcomer, defaults={'account_type': 'free'})
        newcomer.groups.add(Group.objects.get_or_create(name='Viewer')[0])
        invitation = Invitation.objects.create(project=self.project, email='new@example.com',
                                               role='editor', invited_by=self.owner)
        self.client.force_login(newcomer)
        self.client.get(f'/invitations/accept/{invitation.token}/')
        self.assertTrue(ProjectMember.objects.filter(
            project=self.project, user=newcomer, role='editor').exists())
        self.assertTrue(self.page_can_edit(newcomer))
        self.assertTrue(self.endpoint_can_edit(newcomer))
