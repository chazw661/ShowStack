"""User-typed names that the server writes into markup or a script: each must
come out as text (#181). The browser-side fixes are in ``test_xss_browser``.

Run with::

    python manage.py test planner.tests.test_xss_server --settings=audiopatch.test_settings
"""

import json
import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from planner.models import (
    CommBeltPack, CommBeltPackChannel, CommChannel, CommCrewName, CommConfig, Console, ConsoleInput, Crew,
    DiscoveredDevice, MultitrackSession, Project,
)
from planner.tests.test_console_b_patch import PLAIN_STATIC
from planner.tests.test_console_inline_str import ChannelFixture
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


@override_settings(STORAGES=PLAIN_STATIC)
class ConsoleChannelNameTests(ChannelFixture, TestCase):
    """A channel or bus name is printed by the admin on the Console's delete
    confirmation and in its history (``str(channel)``, which used to be
    blank after any Console page load -- test_console_inline_str)."""

    ESCAPED = '&lt;img src=x onerror=alert(1)&gt;'

    def setUp(self):
        super().setUp()
        self.load_console_page()

    def test_delete_confirmation_prints_the_names_as_text(self):
        ConsoleInput.objects.filter(pk=self.kick.pk).update(source=NAME)
        for row in (self.aux, self.matrix, self.stereo):
            type(row).objects.filter(pk=row.pk).update(name=NAME)
        html = self.client.get(
            reverse('admin:planner_console_delete', args=[self.foh.pk])).content.decode()
        self.assertNotIn(NAME, html)
        for line in ('Console input: FOH · Ch 1 · ', 'Console aux output: FOH · Aux 3 · ',
                     'Console matrix output: FOH · Matrix 2 · ',
                     'Console stereo output: FOH · Stereo Left · '):
            self.assertIn(line + self.ESCAPED, html)

    def test_a_console_name_with_markup_is_text_in_its_channels_lines(self):
        Console.objects.filter(pk=self.foh.pk).update(name=NAME)
        html = self.client.get(
            reverse('admin:planner_console_delete', args=[self.foh.pk])).content.decode()
        self.assertNotIn(NAME, html)
        self.assertIn(f'Console input: {self.ESCAPED} · Ch 1 · Kick', html)

    def test_admin_history_prints_the_names_as_text(self):
        i = self.row('consoleinput_set', self.kick.pk)
        j = self.row('consoleauxoutput_set', self.aux.pk)
        r = self.console_post({f'consoleinput_set-{i}-source': NAME,
                               f'consoleauxoutput_set-{j}-name': NAME})
        self.assertEqual(r.status_code, 302)
        self.assertIn(NAME, self.last_log().get_change_message())     # stored as typed
        html = self.client.get(
            reverse('admin:planner_console_history', args=[self.foh.pk])).content.decode()
        self.assertNotIn(NAME, html)
        self.assertIn(f'Ch 1 · {self.ESCAPED}', html)
        self.assertIn(f'Aux 3 · {self.ESCAPED}', html)


from planner.tests.test_comm_devices import CommFixture   # noqa: E402
from planner.models import Device, DeviceOutput   # noqa: E402


@override_settings(STORAGES=PLAIN_STATIC)
class CommDeviceNameTests(CommFixture, TestCase):
    """The comm device page prints other devices' names, port names and
    Dante networks in its lists, boxes, warnings and a JSON block; the other
    device's page and the Wiring Diagram print the comm device's."""

    SCRIPT = '</script><script>alert(1)</script>'

    def assert_clean(self, html):
        self.assertNotIn(NAME, html)
        self.assertNotIn(self.SCRIPT, html)
        self.assertNotIn('<script>alert(1)', html)

    def test_names_networks_and_destinations_are_text_everywhere(self):
        Device.objects.filter(pk=self.mk88.pk).update(name=NAME)
        Device.objects.filter(pk=self.rio.pk).update(dante_network=self.SCRIPT[:40])
        DeviceOutput.objects.filter(pk=self.out(self.rio, 2).pk).update(signal_name=NAME)
        entry = f'{NAME} · Rio SL Out 2 [{self.SCRIPT[:40]}]'
        r = self.post(dout1=f'{NAME} Out 3', dout2=entry, din1=f'{NAME} In 1',
                      **{'4w1_send': f'{NAME} In 2', '2w1_dest': NAME, '2w1_cable': NAME[:40]})
        self.assertEqual(r.status_code, 302)
        Device.objects.filter(pk=self.arc.pk).update(name=NAME + ' comm')

        page = self.client.get(self.url()).content.decode()
        self.assert_clean(page)
        escaped = '&lt;img src=x onerror=alert(1)&gt;'
        self.assertIn(f'value="{escaped} Out 3"', page)             # a row's box
        self.assertIn(f'<option value="{escaped} Out 4"></option>', page)   # a list
        self.assertIn(f'value="{escaped}" aria-label="2W 1 destination"', page)
        self.assertIn('\\u003C/script\\u003E', page)                # the JSON block
        self.assertIn('class="comm-warning">Rio SL is on Dante network', page)

        self.assert_clean(self.client.get(self.url(self.mk88)).content.decode())
        self.assert_clean(self.client.get(self.url(self.rio)).content.decode())
        note = self.client.get(self.url(self.mk88)).content.decode()
        self.assertIn(f'← {escaped} comm Dante Out 1</a>', note)
        for view in ('', '?view=dante', '?view=analog'):
            wiring = self.client.get(reverse('planner:wiring_diagram') + view).content.decode()
            self.assert_clean(wiring)
        overview = self.client.get(reverse('planner:wiring_diagram')).content.decode()
        self.assertIn(f'<td>{escaped} comm · Dante Out 1</td><td>{escaped} · Out 3</td>', overview)

    def test_an_error_row_prints_what_was_typed_as_text(self):
        r = self.post(dout1=NAME, dout2='MK88 Out 1', dout3='MK88 Out 1')
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assert_clean(html)
        self.assertIn('value="&lt;img src=x onerror=alert(1)&gt;"', html)
        self.assertIn('MK88 Out 1 is already picked on Dante Out 2.', html)
