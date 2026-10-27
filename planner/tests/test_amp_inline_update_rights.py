"""Who may change an Amp field from the rack page (amp_inline_update).

Owners and editors of the current project may; viewers get 403 on every
field, and the rack page shows them every field read-only; someone outside
the project can't reach the amp at all.

Run with::

    python manage.py test planner.tests.test_amp_inline_update_rights \\
        --settings=audiopatch.test_settings
"""

import re

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


class RackPageReadOnlyTests(Fixture):
    """What the rack page renders: every inline field (name, channel labels,
    IP, Preset, CH selects, output patch) is readonly/disabled for a viewer
    and editable for an owner or editor."""

    def fields(self, user):
        self.use(user)
        page = self.client.get(reverse('admin:planner_amp_changelist'))
        self.assertEqual(200, page.status_code)
        tags = re.findall(r'<(?:input|select)\b[^>]*class="amp-(?:cell|pill)-input[^>]*>',
                          page.content.decode(), re.S)
        return {re.search(r'data-field="([^"]+)"', t).group(1): t for t in tags}

    def assert_editable(self, fields):
        for name in ('name', 'ip_address', 'preset', 'channel_setting', 'avb_stream'):
            self.assertIn(name, fields)
        for name, tag in fields.items():
            self.assertNotRegex(tag, r'\b(readonly|disabled)\b', name)

    def test_owner_gets_editable_fields(self):
        self.assert_editable(self.fields(self.owner))

    def test_editor_gets_editable_fields(self):
        editor = staff('editor')
        self.join(editor, self.project, 'editor')
        self.assert_editable(self.fields(editor))

    def test_viewer_gets_read_only_fields(self):
        viewer = staff('viewer')
        self.join(viewer, self.project, 'viewer')
        self.join(viewer, self.other, 'editor')  # the role HERE decides
        fields = self.fields(viewer)
        for name in ('name', 'ip_address', 'preset', 'channel_setting', 'avb_stream',
                     'analog_input', 'aes_input'):
            self.assertIn(name, fields)
        for name, tag in fields.items():
            if tag.startswith('<select'):
                self.assertRegex(tag, r'\bdisabled\b', name)
            else:
                self.assertRegex(tag, r'\breadonly\b', name)
        self.assertNotIn('leg', fields)  # shown as text, not a select
