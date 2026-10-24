"""Power Distribution Calculator: tenant isolation and edit rights.

Every power-plan endpoint used to look its plan or assignment up by id alone,
and the calculator with no id opened ``PowerDistributionPlan.objects.first()``
-- whichever tenant's plan sorted first. These pin the fix: another project's
plan or assignment is a 404 on every route, the no-id calculator only ever
opens the current project's plan, and a viewer cannot write.

Run with::

    python manage.py test planner.tests.test_power_plan_tenancy \\
        --settings=audiopatch.test_settings
"""

import json

from django.contrib.auth.models import User
from django.urls import reverse

from planner.models import (
    AmplifierAssignment, AmplifierProfile, PowerDistributionPlan, ProjectMember,
    UserProfile,
)
from planner.tests.test_tenant_isolation import TenantIsolationBase


class PowerPlanBase(TenantIsolationBase):

    def setUp(self):
        super().setUp()
        self.profile = AmplifierProfile.objects.create(
            manufacturer='L-Acoustics', model='LA12X',
            idle_power_watts=240, rated_power_watts=1500,
            peak_power_watts=3000, max_power_watts=12000,
        )
        for tag, project in (('a', self.project_a), ('b', self.project_b)):
            mark = self.MARKER_B if tag == 'b' else 'AAA'
            plan = PowerDistributionPlan.objects.create(
                project=project, show_day=getattr(self, f'show_day_{tag}'),
                venue_name=f'Venue {mark}',
            )
            setattr(self, f'plan_{tag}', plan)
            setattr(self, f'power_assignment_{tag}', AmplifierAssignment.objects.create(
                distribution_plan=plan, amplifier=self.profile,
                quantity=2, zone=f'Zone {mark}',
            ))

    def post_json(self, client, name, obj_id, payload):
        return client.post(
            reverse(f'planner:{name}', args=[obj_id]),
            data=json.dumps(payload), content_type='application/json',
        )


class PowerPlanCrossTenantTests(PowerPlanBase):
    """Project A's session asking for project B's plan gets a 404, everywhere."""

    def test_calculator_detail_404s_for_other_tenant(self):
        resp = self.client.get(reverse(
            'planner:power_distribution_calculator_detail', args=[self.plan_b.id],
        ))
        self.assertEqual(404, resp.status_code)
        self.assertNoLeak(resp, 'power calculator detail')

    def test_calculator_without_id_opens_only_current_project_plan(self):
        # plan_b is the older-created row in some orderings; either way the
        # no-id route must never reach it.
        resp = self.client.get(reverse('planner:power_distribution_calculator'))
        self.assertEqual(200, resp.status_code)
        self.assertEqual(self.plan_a, resp.context['plan'])
        self.assertNoLeak(resp, 'power calculator (no id)')

    def test_calculator_show_day_param_404s_for_other_tenant_day(self):
        resp = self.client.get(
            reverse('planner:power_distribution_calculator'),
            {'show_day': self.show_day_b.id},
        )
        self.assertEqual(404, resp.status_code)

    def test_calculator_without_plan_redirects_instead_of_borrowing_one(self):
        self.plan_a.delete()
        resp = self.client.get(reverse('planner:power_distribution_calculator'))
        self.assertRedirects(
            resp, reverse('admin:planner_powerdistributionplan_add'),
            fetch_redirect_response=False,
        )
        self.assertEqual(1, PowerDistributionPlan.objects.count(),
                         'a plan was created on a GET')

    def test_update_plan_settings_404s_for_other_tenant(self):
        resp = self.post_json(self.client, 'update_plan_settings', self.plan_b.id,
                              {'venue_name': 'PWNED'})
        self.assertEqual(404, resp.status_code)
        self.plan_b.refresh_from_db()
        self.assertNotEqual('PWNED', self.plan_b.venue_name)

    def test_add_amplifier_assignment_404s_for_other_tenant(self):
        before = self.plan_b.amplifier_assignments.count()
        resp = self.post_json(self.client, 'add_amplifier_assignment', self.plan_b.id,
                              {'amplifier_id': self.profile.id})
        self.assertEqual(404, resp.status_code)
        self.assertEqual(before, self.plan_b.amplifier_assignments.count())

    def test_get_assignment_404s_for_other_tenant(self):
        resp = self.client.get(reverse(
            'planner:get_amplifier_assignment', args=[self.power_assignment_b.id],
        ))
        self.assertEqual(404, resp.status_code)
        self.assertNoLeak(resp, 'get_amplifier_assignment')

    def test_update_assignment_404s_for_other_tenant(self):
        resp = self.post_json(self.client, 'update_amplifier_assignment',
                              self.power_assignment_b.id, {'zone': 'PWNED'})
        self.assertEqual(404, resp.status_code)
        self.power_assignment_b.refresh_from_db()
        self.assertNotEqual('PWNED', self.power_assignment_b.zone)

    def test_delete_assignment_404s_for_other_tenant(self):
        resp = self.client.delete(reverse(
            'planner:delete_amplifier_assignment', args=[self.power_assignment_b.id],
        ))
        self.assertEqual(404, resp.status_code)
        self.assertTrue(AmplifierAssignment.objects.filter(
            id=self.power_assignment_b.id).exists())

    def test_user_with_no_project_gets_404_not_someone_elses_plan(self):
        # The middleware falls back to the user's own first project when the
        # session names none, so "no project" means a user who has none.
        loner = User.objects.create_user('pp_loner', 'l@example.com', 'pw-l',
                                         is_staff=True)
        UserProfile.objects.update_or_create(user=loner,
                                             defaults={'account_type': 'paid'})
        self.client.force_login(loner)
        resp = self.client.get(reverse('planner:power_distribution_calculator'))
        self.assertEqual(404, resp.status_code)
        self.assertNoLeak(resp, 'power calculator (no project)')
        resp = self.client.get(reverse(
            'planner:get_amplifier_assignment', args=[self.power_assignment_b.id],
        ))
        self.assertEqual(404, resp.status_code)

    def test_anonymous_is_sent_to_login(self):
        resp = self.anon.get(reverse(
            'planner:power_distribution_calculator_detail', args=[self.plan_b.id],
        ))
        self.assertEqual(302, resp.status_code)
        self.assertNoLeak(resp, 'power calculator (anonymous)')


class PowerPlanOwnProjectTests(PowerPlanBase):
    """The scoping must not lock an owner out of their own plan."""

    def test_owner_can_open_their_plan(self):
        resp = self.client.get(reverse(
            'planner:power_distribution_calculator_detail', args=[self.plan_a.id],
        ))
        self.assertEqual(200, resp.status_code)

    def test_owner_can_read_update_and_delete_their_assignment(self):
        resp = self.client.get(reverse(
            'planner:get_amplifier_assignment', args=[self.power_assignment_a.id],
        ))
        self.assertEqual(200, resp.status_code)

        resp = self.post_json(self.client, 'update_amplifier_assignment',
                              self.power_assignment_a.id, {'quantity': 3})
        self.assertEqual(200, resp.status_code)
        self.power_assignment_a.refresh_from_db()
        self.assertEqual(3, self.power_assignment_a.quantity)

        resp = self.client.delete(reverse(
            'planner:delete_amplifier_assignment', args=[self.power_assignment_a.id],
        ))
        self.assertEqual(200, resp.status_code)

    def test_owner_can_add_and_change_settings(self):
        resp = self.post_json(self.client, 'add_amplifier_assignment', self.plan_a.id,
                              {'amplifier_id': self.profile.id, 'quantity': 1})
        self.assertEqual(200, resp.status_code)
        resp = self.post_json(self.client, 'update_plan_settings', self.plan_a.id,
                              {'venue_name': 'Renamed'})
        self.assertEqual(200, resp.status_code)
        self.plan_a.refresh_from_db()
        self.assertEqual('Renamed', self.plan_a.venue_name)


class PowerPlanViewerTests(PowerPlanBase):
    """A viewer on the project can read the plan but every write is a 403."""

    def setUp(self):
        super().setUp()
        self.viewer = User.objects.create_user('pp_viewer', 'v@example.com', 'pw-v',
                                               is_staff=True)
        UserProfile.objects.update_or_create(user=self.viewer,
                                             defaults={'account_type': 'paid'})
        ProjectMember.objects.create(user=self.viewer, project=self.project_a,
                                     role='viewer', invited_by=self.user_a)
        self.client.force_login(self.viewer)
        s = self.client.session
        s['current_project_id'] = self.project_a.id
        s.save()

    def test_viewer_can_read(self):
        resp = self.client.get(reverse(
            'planner:power_distribution_calculator_detail', args=[self.plan_a.id],
        ))
        self.assertEqual(200, resp.status_code)

    def test_viewer_writes_are_refused(self):
        resp = self.post_json(self.client, 'update_plan_settings', self.plan_a.id,
                              {'venue_name': 'PWNED'})
        self.assertEqual(403, resp.status_code)
        resp = self.post_json(self.client, 'add_amplifier_assignment', self.plan_a.id,
                              {'amplifier_id': self.profile.id})
        self.assertEqual(403, resp.status_code)
        resp = self.post_json(self.client, 'update_amplifier_assignment',
                              self.power_assignment_a.id, {'zone': 'PWNED'})
        self.assertEqual(403, resp.status_code)
        resp = self.client.delete(reverse(
            'planner:delete_amplifier_assignment', args=[self.power_assignment_a.id],
        ))
        self.assertEqual(403, resp.status_code)

        self.plan_a.refresh_from_db()
        self.power_assignment_a.refresh_from_db()
        self.assertNotEqual('PWNED', self.plan_a.venue_name)
        self.assertNotEqual('PWNED', self.power_assignment_a.zone)
        self.assertEqual(1, self.plan_a.amplifier_assignments.count())
