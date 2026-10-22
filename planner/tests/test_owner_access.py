"""A plain project owner reaches their own show's admin pages.

"Plain" means what a real paid or beta customer is: made with create_user,
not staff, in no Django group, never invited to anyone else's project. Until
now such an owner was turned away from the admin entirely (is_staff was only
set by accepting an invitation), got a 403 from the Admin Panel button
(ProjectAdmin used the global groups' model permissions), never saw the team
sections (they asked for an account type, 'premium', that does not exist)
and could not read Amplifier Profiles or pick an amp in a power plan.

Run with::

    python manage.py test planner.tests.test_owner_access \\
        --settings=audiopatch.test_settings
"""

import importlib

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.models import AmplifierProfile, Project, ProjectMember, UserProfile

migration_0202 = importlib.import_module(
    'planner.migrations.0202_staff_for_owners_and_paid_accounts')


def plain_user(username, account_type='paid'):
    user = User.objects.create_user(username, f'{username}@example.com', 'pw')
    UserProfile.objects.update_or_create(user=user,
                                         defaults={'account_type': account_type})
    user.refresh_from_db()
    return user


class PlainOwnerTests(TestCase):

    def setUp(self):
        self.owner = plain_user('owner')
        self.project = Project.objects.create(name='Show', owner=self.owner)
        self.owner.refresh_from_db()
        self.profile = AmplifierProfile.objects.create(
            manufacturer='L-Acoustics', model='LA12X', idle_power_watts=240,
            rated_power_watts=1500, peak_power_watts=3000, max_power_watts=12000)
        self.client.force_login(self.owner)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def get(self, name, *args, **query):
        return self.client.get(reverse(name, args=args), query)

    def test_the_owner_is_in_no_group(self):
        self.assertFalse(self.owner.groups.exists())
        self.assertFalse(self.owner.is_superuser)

    def test_reaches_the_admin_and_can_create_a_project(self):
        self.assertTrue(self.owner.is_staff)
        self.assertEqual(self.get('admin:index').status_code, 200)
        self.assertEqual(self.get('admin:planner_project_add').status_code, 200)

    def test_admin_panel_button_opens_the_project(self):
        detail = self.get('project_detail', self.project.pk)
        change_url = f'/admin/planner/project/{self.project.pk}/change/'
        self.assertContains(detail, change_url)
        self.assertEqual(self.client.get(change_url).status_code, 200)
        self.assertEqual(self.get('admin:planner_project_changelist').status_code, 200)

    def test_manage_team_pages(self):
        self.assertEqual(self.get('project_detail', self.project.pk).status_code, 200)
        self.assertEqual(self.get('admin:planner_projectmember_changelist').status_code, 200)
        self.assertEqual(self.get('admin:planner_invitation_changelist').status_code, 200)

    def test_reads_amplifier_profiles_but_cannot_rewrite_the_shared_catalogue(self):
        self.assertContains(self.get('admin:planner_amplifierprofile_changelist'), 'LA12X')
        self.assertEqual(
            self.get('admin:planner_amplifierprofile_change', self.profile.pk).status_code, 200)
        self.assertEqual(self.get('admin:planner_amplifierprofile_add').status_code, 403)
        self.client.post(
            reverse('admin:planner_amplifierprofile_change', args=[self.profile.pk]),
            {'manufacturer': 'L-Acoustics', 'model': 'LA12X', 'idle_power_watts': 1,
             'rated_power_watts': 1, 'peak_power_watts': 1, 'max_power_watts': 1,
             'nominal_voltage': 208, 'power_factor': '0.95', 'efficiency': '0.90',
             'channels': 4, 'rack_units': 2})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.idle_power_watts, 240)

    def test_can_pick_an_amp_in_a_power_plan(self):
        # The power plan's amplifier field is an autocomplete, which asks
        # AmplifierProfileAdmin for view permission.
        response = self.get('admin:autocomplete', app_label='planner',
                            model_name='amplifierassignment',
                            field_name='amplifier', term='LA12')
        self.assertEqual(response.status_code, 200)
        self.assertIn('LA12X', response.content.decode())

    def test_a_free_account_given_a_project_gets_access_too(self):
        free = plain_user('free', 'free')
        self.assertFalse(free.is_staff)
        Project.objects.create(name='Gifted', owner=free)
        free.refresh_from_db()
        self.assertTrue(free.is_staff)

    def test_upgrading_to_beta_grants_access(self):
        user = plain_user('later', 'free')
        self.assertFalse(user.is_staff)
        profile = UserProfile.objects.get(user=user)
        profile.account_type = 'beta'
        profile.save()
        user.refresh_from_db()
        self.assertTrue(user.is_staff)


class TeamPagesAreTheOwnersTests(TestCase):
    """An editor on the show can edit equipment, but not who is on the team."""

    def setUp(self):
        owner = plain_user('owner')
        self.project = Project.objects.create(name='Show', owner=owner)
        self.editor = plain_user('editor', 'free')
        ProjectMember.objects.create(user=self.editor, project=self.project,
                                     role='editor', invited_by=owner)
        User.objects.filter(pk=self.editor.pk).update(is_staff=True)  # as accepting does
        self.client.force_login(self.editor)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def test_editor_cannot_open_the_team_admin(self):
        self.assertEqual(self.client.get(
            reverse('admin:planner_projectmember_changelist')).status_code, 403)

    def test_editor_cannot_rewrite_amplifier_profiles(self):
        self.assertEqual(self.client.get(
            reverse('admin:planner_amplifierprofile_add')).status_code, 403)
        self.assertEqual(self.client.get(
            reverse('admin:planner_amplifierprofile_changelist')).status_code, 200)


class ExistingAccountsMigrationTests(TestCase):

    def test_0202_staffs_owners_and_paid_beta_only(self):
        owner = plain_user('owner', 'free')
        paid = plain_user('paid', 'free')
        free = plain_user('free', 'free')
        gone = plain_user('gone', 'free')
        Project.objects.create(name='Show', owner=owner)
        # Undo what the signals did, to stand for accounts made before them.
        User.objects.update(is_staff=False)
        UserProfile.objects.filter(user__in=[paid, gone]).update(account_type='beta')
        User.objects.filter(pk=gone.pk).update(is_active=False)

        migration_0202.grant(django_apps, None)

        staff = set(User.objects.filter(is_staff=True).values_list('username', flat=True))
        self.assertEqual(staff, {'owner', 'paid'})
