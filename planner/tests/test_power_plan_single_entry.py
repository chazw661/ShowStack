"""Power plan: one entry point.

The sidebar used to open the admin plan list, a page without Regenerate,
and from there the calculator. Now the sidebar, the dashboard and the admin
home card open the calculator, which shows the project's generated plan (or
how to make one). The admin list and add form are superuser-only; hand-built
plans stay in the database but are never picked by the calculator.

Run with::

    python manage.py test planner.tests.test_power_plan_single_entry \\
        --settings=audiopatch.test_settings
"""

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from planner.models import PowerDistributionPlan, ProjectMember, UserProfile
from planner.tests.test_power_plan_tenancy import PowerPlanBase

CALCULATOR = 'planner:power_distribution_calculator'


class SingleEntryBase(PowerPlanBase):

    def setUp(self):
        super().setUp()
        self.editor = self.member('pp_se_editor', 'editor')
        self.viewer = self.member('pp_se_viewer', 'viewer')
        self.superuser = User.objects.create_superuser('pp_se_su', 'su@example.com', 'pw')
        UserProfile.objects.update_or_create(user=self.superuser,
                                             defaults={'account_type': 'paid'})

    def member(self, username, role):
        user = User.objects.create_user(username, f'{username}@example.com', 'pw',
                                        is_staff=True)
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'paid'})
        ProjectMember.objects.create(user=user, project=self.project_a, role=role,
                                     invited_by=self.user_a)
        return user

    def use(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['current_project_id'] = self.project_a.id
        s.save()

    def generate_a(self):
        PowerDistributionPlan.objects.filter(pk=self.plan_a.pk).update(
            generated_at=timezone.now())
        self.plan_a.refresh_from_db()


class SidebarAndLinksTests(SingleEntryBase):

    def power_row(self, user):
        self.use(user)
        resp = self.client.get(reverse('admin:planner_console_changelist'))
        self.assertEqual(200, resp.status_code)
        planner = next(a for a in resp.context['available_apps'] if a['app_label'] == 'planner')
        return next(m for m in planner['models'] if m['object_name'] == 'PowerDistributionPlan')

    def test_sidebar_entry_opens_the_calculator_for_every_user(self):
        for user in (self.user_a, self.editor, self.viewer, self.superuser):
            with self.subTest(user=user.username):
                row = self.power_row(user)
                self.assertEqual(reverse(CALCULATOR), row['admin_url'])
                self.assertIsNone(row['add_url'])

    def test_sidebar_html_links_the_calculator(self):
        self.use(self.user_a)
        html = self.client.get(reverse('admin:planner_console_changelist')).content.decode()
        self.assertIn(f'href="{reverse(CALCULATOR)}"', html)
        self.assertNotIn('href="/admin/planner/powerdistributionplan/"', html)

    def test_dashboard_and_admin_home_link_the_calculator(self):
        self.use(self.user_a)
        for name in ('planner:system-dashboard', 'admin:index'):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn(f'href="{reverse(CALCULATOR)}"', html)
                self.assertNotIn('/admin/planner/powerdistributionplan/', html)


class AdminListAccessTests(SingleEntryBase):

    ADMIN_PAGES = ('admin:planner_powerdistributionplan_changelist',
                   'admin:planner_powerdistributionplan_add')

    def test_non_superusers_are_sent_to_the_calculator(self):
        for user in (self.user_a, self.editor, self.viewer):
            self.use(user)
            for name in self.ADMIN_PAGES:
                with self.subTest(user=user.username, page=name):
                    self.assertRedirects(self.client.get(reverse(name)), reverse(CALCULATOR),
                                         fetch_redirect_response=False)

    def test_non_superuser_post_to_add_is_refused_and_writes_nothing(self):
        for user in (self.user_a, self.editor, self.viewer):
            with self.subTest(user=user.username):
                self.use(user)
                before = PowerDistributionPlan.objects.count()
                resp = self.client.post(reverse('admin:planner_powerdistributionplan_add'),
                                        {'venue_name': 'Hand plan'})
                self.assertEqual(403, resp.status_code)
                self.assertEqual(before, PowerDistributionPlan.objects.count())

    def test_superuser_keeps_the_admin_list_and_add_form(self):
        self.use(self.superuser)
        for name in self.ADMIN_PAGES:
            with self.subTest(page=name):
                self.assertEqual(200, self.client.get(reverse(name)).status_code)

    def test_calculator_links_the_admin_list_for_superusers_only(self):
        self.generate_a()
        for user, shown in ((self.superuser, True), (self.user_a, False),
                            (self.editor, False), (self.viewer, False)):
            with self.subTest(user=user.username):
                self.use(user)
                html = self.client.get(reverse(CALCULATOR)).content.decode()
                self.assertEqual(shown, 'All plans (admin)' in html)
                self.assertNotIn('Back to Power Distribution Plans', html)


class CalculatorPlanChoiceTests(SingleEntryBase):

    def test_generated_plan_is_preferred_over_a_newer_hand_built_one(self):
        self.generate_a()
        PowerDistributionPlan.objects.create(project=self.project_a, venue_name='Hand, newer')
        resp = self.client.get(reverse(CALCULATOR))
        self.assertEqual(self.plan_a, resp.context['plan'])

    def test_hand_built_plan_alone_is_not_opened(self):
        resp = self.client.get(reverse(CALCULATOR))
        self.assertTemplateUsed(resp, 'planner/power_plan_empty.html')
        self.assertTrue(PowerDistributionPlan.objects.filter(pk=self.plan_a.pk).exists(),
                        'the hand-built plan stays in the database')


class EmptyStateTests(SingleEntryBase):

    def page(self, user):
        self.use(user)
        resp = self.client.get(reverse(CALCULATOR))
        self.assertEqual(200, resp.status_code)
        self.assertTemplateUsed(resp, 'planner/power_plan_empty.html')
        return resp.content.decode()

    def test_owner_and_editor_get_generate(self):
        for user in (self.user_a, self.editor):
            with self.subTest(user=user.username):
                html = self.page(user)
                self.assertIn('id="generate-power-plan"', html)
                self.assertIn(f'action="{reverse("planner:generate_power_plan")}"', html)

    def test_viewer_gets_an_explanation_not_generate(self):
        html = self.page(self.viewer)
        self.assertNotIn('id="generate-power-plan"', html)
        self.assertIn('id="power-plan-viewer-note"', html)

    def test_get_creates_nothing(self):
        before = PowerDistributionPlan.objects.count()
        for user in (self.user_a, self.editor, self.viewer):
            self.page(user)
        self.assertEqual(before, PowerDistributionPlan.objects.count())

    def test_viewer_cannot_generate(self):
        self.use(self.viewer)
        resp = self.client.post(reverse('planner:generate_power_plan'))
        self.assertEqual(403, resp.status_code)
        self.assertFalse(PowerDistributionPlan.objects.filter(
            project=self.project_a, generated_at__isnull=False).exists())

    def test_editor_generate_lands_on_the_new_plan(self):
        self.use(self.editor)
        resp = self.client.post(reverse('planner:generate_power_plan'))
        plan = PowerDistributionPlan.objects.get(project=self.project_a,
                                                 generated_at__isnull=False)
        self.assertRedirects(resp, reverse('planner:power_distribution_calculator_detail',
                                           args=[plan.pk]), fetch_redirect_response=False)
        self.assertEqual(plan, self.client.get(reverse(CALCULATOR)).context['plan'])


class VenueAndNotesTests(SingleEntryBase):

    def setUp(self):
        super().setUp()
        self.generate_a()

    def save(self, user, payload):
        self.use(user)
        return self.post_json(self.client, 'update_plan_settings', self.plan_a.id, payload)

    def test_editor_saves_venue_and_notes_and_the_page_shows_them(self):
        for user in (self.user_a, self.editor):
            with self.subTest(user=user.username):
                venue, notes = f'Hall {user.pk}', f'Distro by the dock {user.pk}'
                resp = self.save(user, {'venue_name': f'  {venue} ', 'notes': notes})
                self.assertEqual(200, resp.status_code)
                self.plan_a.refresh_from_db()
                self.assertEqual((venue, notes), (self.plan_a.venue_name, self.plan_a.notes))
                html = self.client.get(reverse(CALCULATOR)).content.decode()
                self.assertIn(f'id="venue-name" maxlength="200" value="{venue}"', html)
                self.assertIn(f'{notes}</textarea>', html)

    def test_venue_over_200_characters_is_refused(self):
        resp = self.save(self.user_a, {'venue_name': 'x' * 201})
        self.assertEqual(400, resp.status_code)
        self.plan_a.refresh_from_db()
        self.assertEqual('Venue AAA', self.plan_a.venue_name)

    def test_viewer_cannot_change_venue_or_notes(self):
        resp = self.save(self.viewer, {'venue_name': 'Viewer venue', 'notes': 'Viewer notes'})
        self.assertEqual(403, resp.status_code)
        self.plan_a.refresh_from_db()
        self.assertEqual(('Venue AAA', ''), (self.plan_a.venue_name, self.plan_a.notes))

    def test_viewer_sees_them_read_only(self):
        self.use(self.viewer)
        html = self.client.get(reverse(CALCULATOR)).content.decode()
        self.assertRegex(html, r'id="venue-name"[^>]*\sreadonly>')
        self.assertRegex(html, r'id="plan-notes"[^>]*\sreadonly>')
