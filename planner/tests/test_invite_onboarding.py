"""Invited signup is the onboarding path for free accounts.

An invitation link carries its token through the preview page's "Create Free
Account" into signup. A signup with the invited address is accepted on the
spot: logged in, on the invited project, with the invited role, and still a
free account. Everything else -- no token, a stale one, another address -- is
a plain signup with no projects. Only a project's owner invites.

Run with::

    python manage.py test planner.tests.test_invite_onboarding \\
        --settings=audiopatch.test_settings
"""

import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from planner.admin import ConsoleInputInline, DeviceInputInline
from planner.admin_site import showstack_admin_site
from planner.models import (
    Console, Crew, CrewMember, CrewProjectAdd, Device, Invitation, Project,
    ProjectMember, UserProfile,
)
from planner.plans import account_type, can_create_projects

INVITED = 'invitee@example.com'


def make_user(name, plan='free', email=None, staff=False):
    user = User.objects.create_user(name, email=email or f'{name}@example.com',
                                    password='pw', is_staff=staff)
    UserProfile.objects.update_or_create(user=user, defaults={'account_type': plan})
    return User.objects.get(pk=user.pk)


def group_names(user):
    return sorted(user.groups.values_list('name', flat=True))


class Base(TestCase):

    def setUp(self):
        self.owner = make_user('owner', 'paid', staff=True)
        self.project = Project.objects.create(name='Main Show', owner=self.owner)

    def invite(self, project=None, email=INVITED, role='editor', days_ago=0, status='pending'):
        invitation = Invitation.objects.create(
            project=project or self.project, email=email, role=role,
            invited_by=self.owner, status=status)
        if days_ago:
            Invitation.objects.filter(pk=invitation.pk).update(
                invited_at=timezone.now() - timedelta(days=days_ago))
            invitation.refresh_from_db()
        return invitation

    def signup(self, invitation=None, email=INVITED, username='invitee', client=None):
        data = {
            'first_name': 'In', 'last_name': 'Vitee', 'email': email,
            'username': username, 'password1': 'a-very-strong-passw0rd!',
            'password2': 'a-very-strong-passw0rd!', 'terms': 'on',
        }
        if invitation is not None:
            data['invite'] = str(invitation.token)
        return (client or self.client).post(reverse('marketing:register'), data)

    def assert_plain_signup(self, resp, username='invitee'):
        self.assertRedirects(resp, reverse('marketing:pending'), fetch_redirect_response=False)
        user = User.objects.get(username=username)
        self.assertFalse(ProjectMember.objects.filter(user=user).exists())
        self.assertNotIn('_auth_user_id', self.client.session)
        return user

    def membership(self, user, project=None):
        return ProjectMember.objects.get(user=user, project=project or self.project)


class EndToEnd(Base):
    """Owner invites -> preview page -> Register -> signup -> in the project."""

    @patch('accounts.views.send_invitation_email')
    def run_flow(self, role, mock_send):
        self.client.force_login(self.owner)
        resp = self.client.post(reverse('invite_user', args=[self.project.pk]),
                                {'email': INVITED, 'role': role})
        self.assertEqual(302, resp.status_code)
        invitation = mock_send.call_args.args[0]
        self.client.logout()

        preview = self.client.get(reverse('accept_invitation', args=[invitation.token]))
        self.assertEqual(200, preview.status_code)
        register_href = re.search(r'href="(/register/\?invite=[^"]+)"',
                                  preview.content.decode()).group(1)

        page = self.client.get(register_href)
        html = page.content.decode()
        self.assertIn(f'value="{INVITED}"', html)  # email prefilled
        self.assertIn(f'name="invite" value="{invitation.token}"', html)
        self.assertIn('Main Show', html)

        resp = self.signup(invitation)
        self.assertRedirects(resp, '/admin/', fetch_redirect_response=False)
        self.assertNotEqual(reverse('marketing:pending'), resp['Location'])

        user = User.objects.get(username='invitee')
        self.assertEqual(str(user.pk), self.client.session['_auth_user_id'])
        self.assertEqual(self.project.pk, self.client.session['current_project_id'])
        self.assertEqual(role, self.membership(user).role)
        invitation.refresh_from_db()
        self.assertEqual('accepted', invitation.status)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertEqual('free', account_type(user))
        self.assertFalse(can_create_projects(user))
        self.assertEqual(200, self.client.get('/admin/').status_code)
        return user

    def test_editor(self):
        user = self.run_flow('editor')
        self.assertEqual(['Editor'], group_names(user))

    def test_viewer(self):
        user = self.run_flow('viewer')
        self.assertEqual(['Viewer'], group_names(user))


class EdgeCases(Base):

    def test_expired_invite_is_a_plain_signup(self):
        invitation = self.invite(days_ago=8)
        page = self.client.get(f"{reverse('marketing:register')}?invite={invitation.token}")
        html = page.content.decode()
        self.assertIn('expired or has already been used', html)
        self.assertNotIn('name="invite"', html)
        self.assert_plain_signup(self.signup(invitation))
        invitation.refresh_from_db()
        self.assertEqual('expired', invitation.status)

    def test_expiring_a_second_stale_invite_does_not_crash(self):
        # The old unique (project, email, status) turned the second expiry
        # write into an IntegrityError.
        self.invite(status='expired')
        stale = self.invite(days_ago=8)
        self.assertFalse(stale.is_valid())
        self.assertEqual(2, Invitation.objects.filter(status='expired').count())

    def test_used_invite_is_a_plain_signup(self):
        invitation = self.invite(status='accepted')
        self.assert_plain_signup(self.signup(invitation))

    def test_garbage_token_is_a_plain_signup(self):
        self.assertEqual(200, self.client.get('/register/?invite=not-a-uuid').status_code)
        resp = self.client.post(reverse('marketing:register'), {
            'first_name': 'A', 'last_name': 'B', 'email': 'other@example.com',
            'username': 'other', 'password1': 'a-very-strong-passw0rd!',
            'password2': 'a-very-strong-passw0rd!', 'terms': 'on', 'invite': 'nope'})
        self.assertRedirects(resp, reverse('marketing:pending'), fetch_redirect_response=False)

    def test_changed_email_is_a_plain_signup_with_a_message(self):
        invitation = self.invite()
        resp = self.signup(invitation, email='someone-else@example.com')
        user = self.assert_plain_signup(resp)
        page = self.client.get(resp['Location'])
        self.assertIn('different email address', page.content.decode())
        self.assertIn('Main Show', page.content.decode())
        invitation.refresh_from_db()
        self.assertEqual('pending', invitation.status)
        self.assertEqual('free', account_type(user))

    def test_email_match_ignores_case(self):
        invitation = self.invite()
        resp = self.signup(invitation, email='InVitee@Example.COM')
        self.assertRedirects(resp, '/admin/', fetch_redirect_response=False)
        self.assertEqual('editor', self.membership(User.objects.get(username='invitee')).role)

    def test_already_registered_address_is_sent_to_log_in(self):
        existing = make_user('existing', email=INVITED)
        invitation = self.invite()
        resp = self.signup(invitation, username='second')
        self.assertEqual(200, resp.status_code)
        html = resp.content.decode()
        self.assertIn('already exists', html)
        accept_url = reverse('accept_invitation', args=[invitation.token])
        self.assertIn(f'/login/?next={accept_url}', html)
        self.assertFalse(User.objects.filter(username='second').exists())

        # Logging in through that link accepts the invitation.
        resp = self.client.post(f'/login/?next={accept_url}',
                                {'username': 'existing', 'password': 'pw'})
        self.assertRedirects(resp, accept_url, fetch_redirect_response=False)
        self.client.get(accept_url)
        self.assertEqual('editor', self.membership(existing).role)
        self.assertEqual('free', account_type(User.objects.get(pk=existing.pk)))

    def test_plain_signup_refuses_a_registered_address_too(self):
        make_user('existing', email=INVITED)
        resp = self.signup()
        self.assertEqual(200, resp.status_code)
        self.assertFalse(User.objects.filter(username='invitee').exists())

    def test_multiple_invites_accept_only_the_one_used_then_the_dashboard(self):
        other = Project.objects.create(name='Second Show', owner=self.owner)
        first = self.invite(role='editor')
        second = self.invite(project=other, role='viewer')
        self.signup(first)
        user = User.objects.get(username='invitee')
        self.assertEqual(['Main Show'], [pm.project.name for pm in ProjectMember.objects.filter(user=user)])
        second.refresh_from_db()
        self.assertEqual('pending', second.status)

        dashboard = self.client.get('/dashboard/').content.decode()
        accept_url = reverse('accept_invitation', args=[second.token])
        self.assertIn(accept_url, dashboard)
        self.client.get(accept_url)
        self.assertEqual('viewer', self.membership(user, other).role)
        self.assertEqual('editor', self.membership(user).role)
        # Editor somewhere is what the global groups record.
        self.assertEqual(['Editor'], group_names(user))

    def test_existing_member_keeps_their_role(self):
        user = make_user('invitee', email=INVITED)
        ProjectMember.objects.create(project=self.project, user=user, role='viewer',
                                     invited_by=self.owner)
        invitation = self.invite(role='editor')
        self.assertTrue(invitation.accept(user))
        self.assertEqual('viewer', self.membership(user).role)
        invitation.refresh_from_db()
        self.assertEqual('accepted', invitation.status)

    def test_accept_creates_membership_despite_an_older_accepted_invite(self):
        # The bug B hit: the new invite deleted itself as a "duplicate" and
        # returned True with no ProjectMember.
        self.invite(status='accepted')
        invitation = self.invite()
        user = make_user('invitee', email=INVITED)
        self.assertTrue(invitation.accept(user))
        self.assertEqual('editor', self.membership(user).role)

    @patch('accounts.views.send_invitation_email')
    def test_deleted_then_reinvited(self, _send):
        first = self.invite(role='viewer')
        self.signup(first)
        user = User.objects.get(username='invitee')
        self.client.logout()

        user.delete()
        first.refresh_from_db()
        self.assertEqual('revoked', first.status)

        self.client.force_login(self.owner)
        resp = self.client.post(reverse('invite_user', args=[self.project.pk]),
                                {'email': INVITED, 'role': 'editor'})
        self.assertEqual(302, resp.status_code)
        second = Invitation.objects.get(status='pending')
        self.client.logout()

        self.assertRedirects(self.signup(second, username='invitee2'), '/admin/',
                             fetch_redirect_response=False)
        self.assertEqual('editor', self.membership(User.objects.get(username='invitee2')).role)


class DeletingAUserRevokesTheirInvitations(Base):

    def test_accepted_invites_for_the_address_are_revoked(self):
        user = make_user('invitee', email=INVITED)
        accepted = self.invite(status='accepted')
        pending = self.invite(project=Project.objects.create(name='Other', owner=self.owner))
        unrelated = self.invite(email='else@example.com', status='accepted')
        user.delete()
        for invitation, status in ((accepted, 'revoked'), (pending, 'pending'),
                                   (unrelated, 'accepted')):
            invitation.refresh_from_db()
            self.assertEqual(status, invitation.status)

    def test_left_alone_while_another_account_has_the_address(self):
        user = make_user('invitee', email=INVITED)
        make_user('twin', email=INVITED.upper())
        accepted = self.invite(status='accepted')
        user.delete()
        accepted.refresh_from_db()
        self.assertEqual('accepted', accepted.status)


class FreeInviteeRules(Base):
    """What a free account invited onto a project may and may not do."""

    def setUp(self):
        super().setUp()
        self.editor_invite = self.invite(role='editor')
        self.signup(self.editor_invite)
        self.editor = User.objects.get(username='invitee')
        self.viewer_client = self.client_class()
        self.signup(self.invite(email='viewer@example.com', role='viewer'),
                    email='viewer@example.com', username='viewer', client=self.viewer_client)
        self.viewer = User.objects.get(username='viewer')

    def rights(self, inline_class, parent, user):
        request = RequestFactory().get('/')
        request.user = user
        request.current_project = self.project
        inline = inline_class(type(parent), showstack_admin_site)
        return tuple(getattr(inline, f'has_{p}_permission')(request, parent)
                     for p in ('view', 'add', 'change', 'delete'))

    def test_view_and_edit_follow_the_invited_role(self):
        parents = ((ConsoleInputInline, Console.objects.create(project=self.project, name='FOH')),
                   (DeviceInputInline, Device.objects.create(project=self.project, name='Rack')))
        for inline_class, parent in parents:
            with self.subTest(inline=inline_class.__name__):
                self.assertEqual((True,) * 4, self.rights(inline_class, parent, self.editor))
                self.assertEqual((True, False, False, False),
                                 self.rights(inline_class, parent, self.viewer))
        for client in (self.client, self.viewer_client):
            self.assertEqual(200, client.get('/admin/').status_code)
            self.assertEqual(200, client.get(
                f'/admin/planner/project/{self.project.pk}/change/').status_code)

    def test_cannot_create_or_duplicate_projects(self):
        from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
        for user in (self.editor, self.viewer):
            self.assertFalse(can_create_projects(user))
        self.assertEqual(403, self.client.get('/admin/planner/project/add/').status_code)
        self.client.post('/admin/planner/project/add/', {'name': 'Mine'})
        self.client.post('/admin/planner/project/', {
            'action': 'duplicate_project_action', ACTION_CHECKBOX_NAME: [self.project.pk],
            'confirm_duplicate': '1', 'new_name': 'Copy'})
        self.assertEqual(['Main Show'], list(Project.objects.values_list('name', flat=True)))

    def test_an_invite_never_grants_a_creator_plan(self):
        for user in (self.editor, self.viewer):
            self.assertEqual('free', account_type(User.objects.get(pk=user.pk)))
        other = Project.objects.create(name='Second Show', owner=self.owner)
        self.client.get(reverse('accept_invitation', args=[self.invite(project=other).token]))
        self.assertEqual('free', account_type(User.objects.get(pk=self.editor.pk)))
        self.assertFalse(can_create_projects(User.objects.get(pk=self.editor.pk)))

    def test_leave_a_project(self):
        self.client.get(reverse('leave_project', args=[self.project.pk]))
        self.assertFalse(ProjectMember.objects.filter(user=self.editor).exists())
        self.assertEqual([], group_names(self.editor))
        # Nothing left to open in the admin: login lands on the dashboard.
        self.client.logout()
        resp = self.client.post('/login/', {'username': 'invitee',
                                            'password': 'a-very-strong-passw0rd!'})
        self.assertRedirects(resp, '/dashboard/', fetch_redirect_response=False)


class PostLoginLanding(Base):

    def log_in(self, username, next_url=None):
        url = '/login/' + (f'?next={next_url}' if next_url else '')
        return self.client.post(url, {'username': username, 'password': 'pw'})

    def test_free_account_with_no_project_goes_to_the_dashboard(self):
        make_user('loner')
        self.assertRedirects(self.log_in('loner'), '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(200, self.client.get('/dashboard/').status_code)

    def test_member_goes_to_the_admin(self):
        member = make_user('member', staff=True)
        ProjectMember.objects.create(project=self.project, user=member, role='viewer',
                                     invited_by=self.owner)
        self.assertRedirects(self.log_in('member'), '/admin/', fetch_redirect_response=False)

    def test_creator_plan_goes_to_the_admin(self):
        make_user('creator', 'paid', staff=True)
        self.assertRedirects(self.log_in('creator'), '/admin/', fetch_redirect_response=False)

    def test_next_is_honoured_but_not_off_site(self):
        make_user('loner')
        self.assertRedirects(self.log_in('loner', '/dashboard/?x=1'), '/dashboard/?x=1',
                             fetch_redirect_response=False)
        self.client.logout()
        self.assertRedirects(self.log_in('loner', 'https://evil.example/'), '/dashboard/',
                             fetch_redirect_response=False)

    def test_signed_in_visitor_to_login_or_register_is_sent_on(self):
        self.client.force_login(make_user('loner'))
        for url in ('/login/', '/register/'):
            self.assertRedirects(self.client.get(url), '/dashboard/', fetch_redirect_response=False)


class PlainSignup(Base):

    def test_lands_on_the_registered_page_without_approval_wording(self):
        resp = self.signup()
        user = self.assert_plain_signup(resp)
        self.assertTrue(user.is_active)
        self.assertEqual('free', account_type(user))
        html = self.client.get(resp['Location']).content.decode()
        self.assertIn("You're registered!", html)
        self.assertIn('ask its owner to send you an invitation', html)
        for word in ('approval', 'pending', 'review'):
            self.assertNotIn(word, html.lower().split('<body')[-1], word)

    def test_dead_accounts_register_is_gone(self):
        import accounts.views
        self.assertFalse(hasattr(accounts.views, 'register'))
        self.assertEqual('marketing.views', resolve('/register/').func.__module__)


class OnlyOwnersInvite(Base):

    def setUp(self):
        super().setUp()
        self.editor = make_user('editor', staff=True)
        self.viewer = make_user('viewer', staff=True)
        for user, role in ((self.editor, 'editor'), (self.viewer, 'viewer')):
            ProjectMember.objects.create(project=self.project, user=user, role=role,
                                         invited_by=self.owner)

    def as_(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    @patch('accounts.views.send_invitation_email')
    def test_endpoints_refuse_editors_and_viewers(self, mock_send):
        crew = Crew.objects.create(owner=self.editor, name='My crew')
        for user in (self.editor, self.viewer):
            with self.subTest(user=user.username):
                self.as_(user)
                invite_url = reverse('invite_user', args=[self.project.pk])
                self.assertRedirects(self.client.get(invite_url), '/dashboard/',
                                     fetch_redirect_response=False)
                self.client.post(invite_url, {'email': 'x@example.com', 'role': 'editor'})
                self.assertRedirects(
                    self.client.get(reverse('project_invitations', args=[self.project.pk])),
                    '/dashboard/', fetch_redirect_response=False)
                self.client.post(reverse('bulk_add_crew', args=[self.project.pk, crew.pk]))
                self.assertEqual(403, self.client.get('/admin/planner/invitation/').status_code)
        self.assertFalse(Invitation.objects.exists())
        mock_send.assert_not_called()

    @patch('accounts.views.send_invitation_email')
    def test_owner_can(self, mock_send):
        self.as_(self.owner)
        self.client.post(reverse('invite_user', args=[self.project.pk]),
                         {'email': 'x@example.com', 'role': 'viewer'})
        self.assertTrue(Invitation.objects.filter(email='x@example.com').exists())
        mock_send.assert_called_once()

    def test_ui_offers_inviting_to_the_owner_only(self):
        invitations_url = reverse('project_invitations', args=[self.project.pk])
        change_url = f'/admin/planner/project/{self.project.pk}/change/'
        for user, offered in ((self.owner, True), (self.editor, False), (self.viewer, False)):
            with self.subTest(user=user.username):
                self.as_(user)
                for page in (reverse('project_detail', args=[self.project.pk]), '/dashboard/'):
                    html = self.client.get(page).content.decode()
                    self.assertEqual(offered, invitations_url in html, page)
                html = self.client.get(change_url).content.decode()
                self.assertEqual(offered, 'Shareable Access Request Link' in html)


class CrewRosterClaim(Base):
    """A pending email on an owner's crew roster, after that crew was added
    to the owner's project, becomes a member when the address signs up."""

    def setUp(self):
        super().setUp()
        self.crew = Crew.objects.create(owner=self.owner, name='A team')

    def roster(self, crew=None, email=INVITED, role='viewer'):
        return CrewMember.objects.create(crew=crew or self.crew, email=email, default_role=role)

    @patch('accounts.views.send_crew_added_email')
    def test_signup_gets_the_rosters_role_and_nothing_more(self, _send):
        self.roster(role='editor')
        CrewProjectAdd.objects.create(crew=self.crew, project=self.project)
        resp = self.signup()
        self.assertRedirects(resp, reverse('marketing:pending'), fetch_redirect_response=False)
        user = User.objects.get(username='invitee')
        pm = self.membership(user)
        self.assertEqual(('editor', self.owner), (pm.role, pm.invited_by))
        self.assertEqual('free', account_type(user))
        self.assertFalse(can_create_projects(user))
        self.assertTrue(user.is_staff)
        self.assertEqual(['Editor'], group_names(user))
        page = self.client.get(reverse('marketing:pending')).content.decode()
        self.assertIn("added to Main Show", page)
        resp = self.client.post('/login/', {'username': 'invitee',
                                            'password': 'a-very-strong-passw0rd!'})
        self.assertRedirects(resp, '/admin/', fetch_redirect_response=False)
        self.assertEqual(200, self.client.get('/admin/').status_code)

    @patch('accounts.views.send_crew_added_email')
    def test_viewer_roster_role(self, _send):
        self.roster(role='viewer')
        CrewProjectAdd.objects.create(crew=self.crew, project=self.project)
        self.signup()
        user = User.objects.get(username='invitee')
        self.assertEqual('viewer', self.membership(user).role)
        self.assertEqual(['Viewer'], group_names(user))

    def test_a_roster_alone_grants_no_project(self):
        self.roster()
        self.signup()
        self.assertFalse(ProjectMember.objects.filter(user__username='invitee').exists())

    @patch('accounts.views.send_crew_invite_to_signup_email')
    @patch('accounts.views.send_crew_added_email')
    def test_only_owners_control_the_roster_and_where_it_goes(self, _added, _signup):
        member = make_user('member', staff=True)
        ProjectMember.objects.create(project=self.project, user=member, role='editor',
                                     invited_by=self.owner)
        self.client.force_login(member)
        # Someone else's crew: no reading, adding or removing.
        listed = self.roster(email='listed@example.com')
        self.assertRedirects(self.client.get(reverse('crew_detail', args=[self.crew.pk])),
                             reverse('crew_index'), fetch_redirect_response=False)
        self.client.post(reverse('crew_member_add', args=[self.crew.pk]),
                         {'user_or_email': INVITED, 'default_role': 'editor'})
        self.client.post(reverse('crew_member_remove', args=[self.crew.pk, listed.pk]))
        self.assertEqual(['listed@example.com'],
                         list(self.crew.crewmember_set.values_list('email', flat=True)))
        # Their own crew can't be attached to a project they don't own.
        own = Crew.objects.create(owner=member, name='Mine')
        self.roster(crew=own, role='editor')
        self.client.post(reverse('bulk_add_crew', args=[self.project.pk, own.pk]))
        self.assertFalse(CrewProjectAdd.objects.exists())
        self.client.logout()
        self.signup()
        self.assertFalse(ProjectMember.objects.filter(user__username='invitee').exists())

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_of_a_registered_free_account(self, _send):
        user = make_user('invitee', email=INVITED)
        self.assertFalse(user.is_staff)
        CrewMember.objects.create(crew=self.crew, user=user, default_role='editor')
        self.client.force_login(self.owner)
        self.client.post(reverse('bulk_add_crew', args=[self.project.pk, self.crew.pk]))
        user.refresh_from_db()
        self.assertEqual('editor', self.membership(user).role)
        self.assertTrue(user.is_staff)
        self.assertEqual(['Editor'], group_names(user))
        self.assertEqual('free', account_type(user))

    def test_any_new_membership_grants_staff(self):
        user = make_user('member')
        ProjectMember.objects.create(project=self.project, user=user, role='viewer',
                                     invited_by=self.owner)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        inactive = make_user('inactive')
        User.objects.filter(pk=inactive.pk).update(is_active=False)
        ProjectMember.objects.create(project=self.project, user=User.objects.get(pk=inactive.pk),
                                     role='viewer', invited_by=self.owner)
        self.assertFalse(User.objects.get(pk=inactive.pk).is_staff)


class LocalInvitationEmail(Base):

    def test_debug_without_a_resend_key_prints_the_link(self):
        import io
        import os
        from contextlib import redirect_stdout
        from django.test import override_settings
        self.client.force_login(self.owner)
        out = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != 'RESEND_API_KEY'}
        with override_settings(DEBUG=True), patch.dict(os.environ, env, clear=True), \
                redirect_stdout(out):
            resp = self.client.post(reverse('invite_user', args=[self.project.pk]),
                                    {'email': INVITED, 'role': 'viewer'})
        self.assertEqual(302, resp.status_code)
        invitation = Invitation.objects.get()
        self.assertIn(f'/invitations/accept/{invitation.token}/', out.getvalue())
