"""Power plan page: links back to the amp module.

"← Amplifiers" next to the title (every plan) and "Open amps" in the
generated banner go to power_plan_amps, which opens the rack page for the
plan's own project -- not whichever project the session moved to since.

Run with::

    python manage.py test planner.tests.test_power_plan_amps_link \\
        --settings=audiopatch.test_settings
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.models import (
    Amp, AmpLocation, PowerDistributionPlan, Project, ProjectMember, UserProfile,
)


class PowerPlanAmpsLinkTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('owner', 'o@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=self.owner, defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='Show One', owner=self.owner)
        self.other = Project.objects.create(name='Show Two', owner=self.owner)
        for project, name in ((self.project, 'Alpha Amp'), (self.other, 'Bravo Amp')):
            location = AmpLocation.objects.create(project=project, name=f'{name} rack')
            Amp.objects.create(project=project, location=location, name=name)
        self.plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='Hall')
        self.amps_url = reverse('planner:power_plan_amps', args=[self.plan.id])
        self.client.force_login(self.owner)
        self.use_project(self.project)

    def use_project(self, project, client=None):
        session = (client or self.client).session
        session['current_project_id'] = project.id
        session.save()

    def page(self):
        return self.client.get(reverse('planner:power_distribution_calculator_detail',
                                       args=[self.plan.id]))

    def test_hand_built_plan_has_top_link_only(self):
        resp = self.page()
        self.assertContains(resp, f'href="{self.amps_url}" class="amps-link" id="amps-link"')
        self.assertContains(resp, '← Amplifiers')
        self.assertNotContains(resp, 'id="banner-amps-link"')

    def test_generated_plan_has_banner_link_too(self):
        from planner.utils import power_plan_generator as generator
        self.plan.delete()
        self.plan, _ = generator.generate(self.project, user=self.owner)
        resp = self.page()
        url = reverse('planner:power_plan_amps', args=[self.plan.id])
        self.assertContains(resp, f'href="{url}" class="amps-link" id="amps-link"')
        self.assertContains(resp, f'href="{url}" class="amps-link" id="banner-amps-link">Open amps</a>')

    def test_link_opens_the_plans_project_not_the_sessions(self):
        # Another tab switched the session to Show Two after the plan loaded.
        self.use_project(self.other)
        resp = self.client.get(self.amps_url)
        self.assertRedirects(resp, reverse('admin:planner_amp_changelist'),
                             fetch_redirect_response=False)
        self.assertEqual(self.client.session['current_project_id'], self.project.id)
        rack = self.client.get(resp.url)
        self.assertEqual(rack.status_code, 200)
        self.assertContains(rack, 'Alpha Amp')
        self.assertNotContains(rack, 'Bravo Amp')

    def test_viewer_member_gets_their_plans_project(self):
        viewer = User.objects.create_user('viewer', 'v@example.com', 'pw', is_staff=True)
        ProjectMember.objects.create(project=self.project, user=viewer, role='viewer',
                                     invited_by=self.owner)
        self.client.force_login(viewer)
        self.use_project(self.project)
        self.assertContains(self.page(), 'id="amps-link"')
        resp = self.client.get(self.amps_url)
        self.assertRedirects(resp, reverse('admin:planner_amp_changelist'),
                             fetch_redirect_response=False)
        self.assertEqual(self.client.session['current_project_id'], self.project.id)

    def test_user_without_access_gets_404_and_keeps_session(self):
        outsider = User.objects.create_user('outsider', 'x@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=outsider, defaults={'account_type': 'paid'})
        theirs = Project.objects.create(name='Theirs', owner=outsider)
        self.client.force_login(outsider)
        self.use_project(theirs)
        self.assertEqual(self.client.get(self.amps_url).status_code, 404)
        self.assertEqual(self.client.session['current_project_id'], theirs.id)

    def test_regenerate_stays_on_plan_page(self):
        from planner.utils import power_plan_generator as generator
        self.plan.delete()
        plan, _ = generator.generate(self.project, user=self.owner)
        resp = self.client.post(reverse('planner:regenerate_power_plan', args=[plan.id]))
        self.assertRedirects(resp, reverse('planner:power_distribution_calculator_detail',
                                           args=[plan.id]), fetch_redirect_response=False)
