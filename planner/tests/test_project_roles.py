"""Edit rights come from the CURRENT project's role, never from another one's.

BaseEquipmentAdmin's add/change-list/bulk-delete checks and the Mic Tracker's
``is_viewer`` used to ask about the account ("is it paid?") or about every
project the user belonged to ("an editor anywhere?", "owns anything?"). So a
viewer on project A who was an editor on B -- or who simply had a paid account
-- got the Add button and the edit controls on A. These pin the per-project
rule from both sides, with the same user switching between the two projects.

Run with::

    python manage.py test planner.tests.test_project_roles \\
        --settings=audiopatch.test_settings
"""

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from planner.admin import ConsoleAdmin
from planner.admin_site import showstack_admin_site
from planner.models import Console, Project, ProjectMember, UserProfile


class CurrentProjectRoleTests(TestCase):

    def setUp(self):
        owner_a = User.objects.create_user('owner_a', 'oa@example.com', 'pw')
        owner_b = User.objects.create_user('owner_b', 'ob@example.com', 'pw')
        self.project_a = Project.objects.create(name='A', owner=owner_a)
        self.project_b = Project.objects.create(name='B', owner=owner_b)
        Console.objects.create(project=self.project_a, name='FOH A')
        Console.objects.create(project=self.project_b, name='FOH B')

        # A paid account, so the old "premium owner" shortcut would have
        # waved it through everywhere.
        self.user = User.objects.create_user('crew', 'crew@example.com', 'pw',
                                             is_staff=True)
        UserProfile.objects.update_or_create(user=self.user,
                                             defaults={'account_type': 'paid'})
        self.client.force_login(self.user)

    def member(self, project, role):
        ProjectMember.objects.create(user=self.user, project=project, role=role,
                                     invited_by=project.owner)

    def use(self, project):
        session = self.client.session
        session['current_project_id'] = project.pk
        session.save()

    def can_add(self, project):
        request = RequestFactory().get('/')
        request.user = self.user
        request.current_project = project
        return ConsoleAdmin(Console, showstack_admin_site).has_add_permission(request)

    def mic_tracker_is_viewer(self, project):
        self.use(project)
        context = self.client.get(reverse('planner:mic_tracker')).context
        return context['is_viewer']

    # -- viewer on A + editor on B ------------------------------------------

    def test_viewer_on_a_cannot_add_on_a_though_editor_on_b(self):
        self.member(self.project_a, 'viewer')
        self.member(self.project_b, 'editor')
        self.assertFalse(self.can_add(self.project_a))
        self.assertTrue(self.can_add(self.project_b))

        self.use(self.project_a)
        self.assertEqual(
            self.client.get(reverse('admin:planner_console_add')).status_code, 403)
        changelist = self.client.get(reverse('admin:planner_console_changelist'))
        self.assertEqual(changelist.status_code, 200)
        self.assertNotContains(changelist, reverse('admin:planner_console_add'))

        self.use(self.project_b)
        self.assertEqual(
            self.client.get(reverse('admin:planner_console_add')).status_code, 200)

    def test_viewer_on_a_gets_a_read_only_mic_tracker_though_editor_on_b(self):
        self.member(self.project_a, 'viewer')
        self.member(self.project_b, 'editor')
        self.assertTrue(self.mic_tracker_is_viewer(self.project_a))
        self.assertFalse(self.mic_tracker_is_viewer(self.project_b))

    def test_viewer_on_a_cannot_bulk_delete_on_a(self):
        self.member(self.project_a, 'viewer')
        self.member(self.project_b, 'editor')
        self.use(self.project_a)
        changelist = self.client.get(reverse('admin:planner_console_changelist'))
        self.assertNotIn('delete_selected', changelist.context['cl'].model_admin
                         .get_actions(changelist.wsgi_request))

    def test_owning_another_project_does_not_unlock_a_viewed_one(self):
        # The Mic Tracker treated "owns any project" as edit rights everywhere.
        Project.objects.create(name='Mine', owner=self.user)
        self.member(self.project_a, 'viewer')
        self.assertFalse(self.can_add(self.project_a))
        self.assertTrue(self.mic_tracker_is_viewer(self.project_a))

    # -- editor on A + viewer on B ------------------------------------------

    def test_editor_on_a_is_not_blocked_by_viewer_on_b(self):
        self.member(self.project_a, 'editor')
        self.member(self.project_b, 'viewer')
        self.assertTrue(self.can_add(self.project_a))
        self.assertFalse(self.can_add(self.project_b))
        self.assertFalse(self.mic_tracker_is_viewer(self.project_a))
        self.assertTrue(self.mic_tracker_is_viewer(self.project_b))

        self.use(self.project_a)
        self.assertEqual(
            self.client.get(reverse('admin:planner_console_add')).status_code, 200)

    def test_free_account_editor_can_add(self):
        # The old rule needed a paid account OR an editor role somewhere; the
        # role on this project is enough on its own.
        UserProfile.objects.filter(user=self.user).update(account_type='free')
        self.member(self.project_a, 'editor')
        self.assertTrue(self.can_add(self.project_a))

    def test_no_current_project_means_no_add(self):
        self.member(self.project_a, 'editor')
        self.assertFalse(self.can_add(None))
