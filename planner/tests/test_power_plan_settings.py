"""Power Distribution Calculator: Service Configuration round trip.

The Safety Margin menu compared the stored Decimal with float literals in the
template (Decimal('0.80') == 0.8 is False), so 70/80/90% were never marked
selected and the browser showed the first option, 70%, while Usable Amps/Leg
used the stored value. The next save of ANY setting then sent 0.7. These pin
the fix and check every other control on the panel holds a non-default value.

Run with::

    python manage.py test planner.tests.test_power_plan_settings \\
        --settings=audiopatch.test_settings
"""

import re
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from planner.models import AmplifierAssignment, PowerDistributionPlan, ProjectMember, UserProfile
from planner.tests.test_power_plan_tenancy import PowerPlanBase
from planner.views import HEADROOM_CHOICES, MARGIN_CHOICES


class PowerPlanSettingsBase(PowerPlanBase):

    def page(self):
        resp = self.client.get(reverse(
            'planner:power_distribution_calculator_detail', args=[self.plan_a.id]))
        self.assertEqual(200, resp.status_code)
        return resp.content.decode()

    def selected(self, html, select_id):
        """The values of the selected options in one <select>."""
        select = re.search(rf'<select id="{select_id}".*?</select>', html, re.S).group(0)
        return [v for v, sel in re.findall(r'<option value="([^"]*)"\s*(selected)?', select) if sel]

    def input_value(self, html, input_id):
        return re.search(rf'<input [^>]*id="{input_id}"[^>]*value="([^"]*)"', html).group(1)

    def usable(self, html):
        return re.search(r'Usable Amps/Leg</label>\s*<input type="text" value="([^"]+)"',
                         html).group(1)

    def save(self, payload, client=None):
        return self.post_json(client or self.client, 'update_plan_settings',
                              self.plan_a.id, payload)


class SafetyMarginTests(PowerPlanSettingsBase):

    def test_render_selects_the_stored_value_for_every_option(self):
        for value, _ in MARGIN_CHOICES:
            with self.subTest(value=value):
                PowerDistributionPlan.objects.filter(pk=self.plan_a.pk).update(
                    safety_margin=D(value))
                self.assertEqual([value], self.selected(self.page(), 'safety-margin'))

    def test_new_plan_shows_the_80_percent_default(self):
        self.assertEqual(['0.80'], self.selected(self.page(), 'safety-margin'))

    def test_value_off_the_list_is_shown_as_itself(self):
        PowerDistributionPlan.objects.filter(pk=self.plan_a.pk).update(safety_margin=D('0.75'))
        html = self.page()
        self.assertEqual(['0.75'], self.selected(html, 'safety-margin'))
        self.assertIn('<option value="0.75" selected>75%</option>', html)

    def test_post_each_option_persists_and_recalculates_usable(self):
        self.save({'available_amperage_per_leg': 437})
        for value, _ in MARGIN_CHOICES:
            with self.subTest(value=value):
                resp = self.save({'safety_margin': value})
                self.assertEqual(200, resp.status_code)
                expected = int(437 * D(value))  # 305, 393, 393, 437
                self.assertEqual(expected, resp.json()['usable_amperage'])
                self.plan_a.refresh_from_db()
                self.assertEqual(D(value), self.plan_a.safety_margin)
                html = self.page()
                self.assertEqual([value], self.selected(html, 'safety-margin'))
                self.assertEqual(f'{expected}A', self.usable(html))

    def test_usable_is_available_times_margin_without_float_truncation(self):
        # 100 x 0.29 is 28.999... in floats.
        PowerDistributionPlan.objects.filter(pk=self.plan_a.pk).update(
            available_amperage_per_leg=100, safety_margin=D('0.29'))
        self.plan_a.refresh_from_db()
        self.assertEqual(29, self.plan_a.get_usable_amperage())

    def test_out_of_range_margin_is_refused(self):
        for bad in ('0', '-0.5', '1.5'):
            with self.subTest(bad=bad):
                resp = self.save({'safety_margin': bad})
                self.assertEqual(400, resp.status_code)
                self.plan_a.refresh_from_db()
                self.assertEqual(D('0.80'), self.plan_a.safety_margin)


class OtherServiceSettingsTests(PowerPlanSettingsBase):
    """Every other control on the panel holds a non-default value."""

    def test_transient_headroom_round_trips_every_option(self):
        for value, _ in HEADROOM_CHOICES:
            with self.subTest(value=value):
                self.assertEqual(200, self.save({'transient_headroom': value}).status_code)
                self.assertEqual([value], self.selected(self.page(), 'transient-headroom'))

    def test_service_type_round_trips_every_option(self):
        for value, _ in PowerDistributionPlan.SERVICE_TYPES:
            with self.subTest(value=value):
                self.assertEqual(200, self.save({'service_type': value}).status_code)
                self.assertEqual([value], self.selected(self.page(), 'service-type'))

    def test_numeric_inputs_round_trip(self):
        resp = self.save({'available_amperage_per_leg': 1200, 'power_factor': '0.87',
                          'other_electronics_watts': 4500})
        self.assertEqual(200, resp.status_code)
        html = self.page()
        self.assertEqual('1200', self.input_value(html, 'available-amps'))
        self.assertEqual('0.87', self.input_value(html, 'power-factor'))
        self.assertEqual('4500', self.input_value(html, 'other-electronics'))

    def test_programme_round_trips_on_a_generated_plan(self):
        PowerDistributionPlan.objects.filter(pk=self.plan_a.pk).update(generated_at=timezone.now())
        for value, _ in AmplifierAssignment.PROGRAMME_CHOICES:
            with self.subTest(value=value):
                self.assertEqual(200, self.save({'programme': value}).status_code)
                self.assertEqual([value], self.selected(self.page(), 'plan-programme'))

    def test_saving_another_setting_keeps_the_margin(self):
        # What the page sends when any one control changes: every control's
        # displayed value. The margin must come back as what was stored.
        PowerDistributionPlan.objects.filter(pk=self.plan_a.pk).update(safety_margin=D('0.90'))
        shown = self.selected(self.page(), 'safety-margin')[0]
        self.save({'available_amperage_per_leg': 200, 'safety_margin': shown})
        self.plan_a.refresh_from_db()
        self.assertEqual(D('0.90'), self.plan_a.safety_margin)


class SafetyMarginViewerTests(PowerPlanSettingsBase):

    def test_viewer_cannot_change_the_margin(self):
        viewer = User.objects.create_user('pp_margin_viewer', 'mv@example.com', 'pw-mv',
                                          is_staff=True)
        UserProfile.objects.update_or_create(user=viewer, defaults={'account_type': 'paid'})
        ProjectMember.objects.create(user=viewer, project=self.project_a,
                                     role='viewer', invited_by=self.user_a)
        self.client.force_login(viewer)
        s = self.client.session
        s['current_project_id'] = self.project_a.id
        s.save()
        resp = self.save({'safety_margin': '0.90'})
        self.assertEqual(403, resp.status_code)
        self.plan_a.refresh_from_db()
        self.assertEqual(D('0.80'), self.plan_a.safety_margin)
