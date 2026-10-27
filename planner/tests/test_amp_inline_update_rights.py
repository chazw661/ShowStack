"""Who may change an Amp field from the rack page (amp_inline_update).

Owners and editors of the current project may; viewers get 403 on every
field; someone outside the project can't reach the amp at all.

Run with::

    python manage.py test planner.tests.test_amp_inline_update_rights \\
        --settings=audiopatch.test_settings
"""

from django.contrib.auth.models import User
from django.urls import reverse

from planner.models import Amp
from planner.tests.test_amp_output_cabinets import Fixture, staff
from planner.views import _INLINE_AMP_FIELDS


class AmpInlineUpdateRightsTests(Fixture):

    def post(self, field, value='X'):
        return self.client.post(reverse('planner:amp_inline_update', args=[self.la12x.pk]),
                                {'field': field, 'value': value})

    def amp_row(self):
        return Amp.objects.filter(pk=self.la12x.pk).values().get()

    def test_owner_may_edit(self):
        self.use(self.owner)
        self.assertEqual(200, self.post('name', 'Stage L').status_code)
        self.assertEqual('Stage L', self.amp_row()['name'])

    def test_editor_may_edit(self):
        editor = staff('editor')
        self.join(editor, self.project, 'editor')
        self.use(editor)
        self.assertEqual(200, self.post('ip_address', '10.0.0.5').status_code)
        self.assertEqual('10.0.0.5', self.amp_row()['ip_address'])

    def test_viewer_is_refused_on_every_field(self):
        # A viewer here who edits another show: the role HERE decides.
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.join(viewer, self.other, 'editor')
        self.use(viewer)
        before = self.amp_row()
        # 'leg' included by name: it joins the whitelist with generated power
        # plans, and must be refused whether or not it is there yet.
        for field in sorted(_INLINE_AMP_FIELDS | {'leg'}):
            response = self.post(field, '10.0.0.9' if field == 'ip_address' else 'L2')
            self.assertEqual(403, response.status_code, field)
            self.assertEqual({'success': False, 'error': 'Read-only access.'},
                             response.json(), field)
        self.assertEqual(before, self.amp_row())

    def test_non_member_cannot_reach_the_amp(self):
        # Owns another show, so that one is their current project.
        outsider = User.objects.create_user('outsider', password='pw', is_staff=True)
        self.other.owner = outsider
        self.other.save()
        self.use(outsider, self.project)
        before = self.amp_row()
        self.assertEqual(404, self.post('name', 'Hijack').status_code)
        self.assertEqual(404, self.post('leg', 'L1').status_code)
        self.assertEqual(before, self.amp_row())

    def test_non_member_with_no_project(self):
        self.use(staff('nobody'), self.project)
        before = self.amp_row()
        self.assertEqual(400, self.post('name', 'Hijack').status_code)
        self.assertEqual(before, self.amp_row())
