"""User-typed names that the server writes into markup or a script: each must
come out as text (#181). The browser-side fixes are in ``test_xss_browser``.

Run with::

    python manage.py test planner.tests.test_xss_server --settings=audiopatch.test_settings
"""

import json
import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.models import (
    CommBeltPack, CommBeltPackChannel, CommChannel, CommCrewName, CommConfig, Console, ConsoleInput, Crew,
    DiscoveredDevice, MultitrackSession, Project,
)
from planner.utils.script_json import script_json

NAME = '<img src=x onerror=alert(1)>'
CLOSES = '</script><img src=x onerror=alert(1)>'
# Ends a quoted JS string in an onclick once the browser decodes &#x27;.
BREAKS = "x');alert(1);//"


class Base(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('xss_srv', is_staff=True, is_superuser=True)
        self.project = Project.objects.create(name='Show X', owner=self.owner)
        self.client.force_login(self.owner)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def script_values(self, html, prefix):
        """The JSON after ``prefix`` in an inline script, parsed."""
        m = re.search(re.escape(prefix) + r'\s*(.*?);?\s*$', html, re.M)
        return json.loads(m.group(1).rstrip(';'))


class ScriptJsonTests(TestCase):

    def test_nothing_in_it_can_close_the_script(self):
        out = script_json({'label': CLOSES, 'note': 'a & b'})
        self.assertNotIn('<', out)
        self.assertNotIn('>', out)
        self.assertEqual({'label': CLOSES, 'note': 'a & b'}, json.loads(out))


class NetworkMonitorTests(Base):

    def test_a_device_label_cannot_end_the_script(self):
        # views_monitor.network_monitor_view: devices_json / recent_events_json
        DiscoveredDevice.objects.create(project=self.project, label=CLOSES, ip_address='10.0.0.9', domain='dante')
        html = self.client.get(reverse('planner:network_monitor')).content.decode()
        self.assertNotIn(CLOSES, html)
        devices = self.script_values(html, 'const NHM_DEVICES =')
        self.assertEqual(CLOSES, devices[0]['label'])


class MultitrackPickerTests(Base):

    def test_a_channel_name_cannot_end_the_picker_json(self):
        # views.multitrack_editor: picker_data_json in <script type="application/json">
        console = Console.objects.create(project=self.project, name='FOH')
        ConsoleInput.objects.create(console=console, input_ch='1', source=CLOSES, default_record=True)
        session = MultitrackSession.objects.create(project=self.project, console=console, name='Rec',
                                                   target_daw='reaper', feed_source='console_dante',
                                                   track_order_mode='console')
        html = self.client.get(reverse('planner:multitrack_editor', args=[session.pk])).content.decode()
        self.assertNotIn(CLOSES, html)
        data = json.loads(re.search(r'<script id="mts-picker-data" type="application/json">(.*?)</script>',
                                    html, re.S).group(1))
        self.assertIn(CLOSES, json.dumps(data, ensure_ascii=False))


class BeltpackChannelBadgeTests(Base):

    def test_a_channel_abbreviation_is_text(self):
        # admin.CommBeltPackAdmin.channel_summary (mark_safe'd badges)
        channel = CommChannel.objects.create(project=self.project, channel_type='4W', channel_number='1',
                                             name='Prod', abbreviation=NAME)
        pack = CommBeltPack.objects.create(project=self.project, bp_number=1)
        CommBeltPackChannel.objects.create(beltpack=pack, channel_number=1, channel=channel)
        html = self.client.get(reverse('admin:planner_commbeltpack_changelist')).content.decode()
        self.assertNotIn(NAME, html)
        self.assertIn('1: &lt;img src=x onerror=alert(1)&gt;', html)


class CrewDeleteConfirmTests(Base):

    def test_a_crew_name_cannot_end_the_confirm_string(self):
        # accounts/crew_index.html: the Delete button's confirm()
        Crew.objects.create(owner=self.owner, name=BREAKS)
        html = self.client.get(reverse('crew_index')).content.decode()
        onclick = re.search(r'onclick="return confirm\(([^"]*)\)"', html).group(1)
        self.assertNotIn("x');alert", onclick)
        self.assertNotIn('x&#x27;);alert', onclick)
        self.assertIn('x\\u0027)', onclick)               # the quote stays inside the string


class CommCrewNamesTests(Base):

    def test_crew_names_stay_inside_their_strings(self):
        # comm_config.html: const allCrewNames = [...]. A name ending in a
        # backslash used to swallow the closing quote, so the next name ran.
        CommConfig.objects.create(project=self.project, name='FS2')
        CommCrewName.objects.create(project=self.project, name='A1\\')
        CommCrewName.objects.create(project=self.project, name=');alert(1)//')
        html = self.client.get(reverse('planner:comm_config')).content.decode()
        line = re.search(r'const allCrewNames = (\[.*?\]);', html).group(1)
        self.assertEqual(sorted(['A1\\', ');alert(1)//']), sorted(json.loads(line)))
