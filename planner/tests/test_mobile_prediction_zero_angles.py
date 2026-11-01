"""Mobile prediction detail: a 0° azimuth or bumper angle is shown.

The tiles were guarded with ``{% if item.array.azimuth %}``, and Decimal 0.0
is falsy, so a centre array aimed straight ahead (0°) or a flat bumper lost
its tile. Unset (None) still shows no tile.

Run with::

    python manage.py test planner.tests.test_mobile_prediction_zero_angles \\
        --settings=audiopatch.test_settings
"""

from decimal import Decimal as D

from django.urls import reverse

from planner.models import SpeakerArray
from planner.tests.test_tenant_isolation import TenantIsolationBase


class MobileZeroAngleTests(TenantIsolationBase):

    def array(self, **fields):
        return SpeakerArray.objects.create(
            prediction=self.prediction_a, source_name='K2 C', array_base_name='K2 C',
            configuration='', bumper_type='K2-BUMP', **fields)

    def page(self):
        resp = self.client.get(reverse(
            'mobile:prediction_detail', args=[self.project_a.id, self.prediction_a.id]))
        self.assertEqual(200, resp.status_code)
        return resp.content.decode()

    def test_zero_azimuth_and_bumper_angle_are_shown(self):
        self.array(azimuth=D('0.0'), bumper_angle=D('0.0'))
        html = self.page()
        self.assertIn('<div class="stat-label">Azimuth</div>', html)
        self.assertIn('<div class="stat-label">Bumper</div>', html)
        self.assertEqual(2, html.count('<div class="stat-value">0.0°</div>'))

    def test_unset_angles_show_no_tile(self):
        self.array(azimuth=None, bumper_angle=None)
        html = self.page()
        self.assertNotIn('<div class="stat-label">Azimuth</div>', html)
        self.assertNotIn('<div class="stat-label">Bumper</div>', html)

    def test_non_zero_angles_still_shown(self):
        self.array(azimuth=D('-12.5'), bumper_angle=D('3.0'))
        html = self.page()
        self.assertIn('<div class="stat-value">-12.5°</div>', html)
        self.assertIn('<div class="stat-value">3.0°</div>', html)
