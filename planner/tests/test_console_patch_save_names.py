"""A name typed on the Console page, used by a patch, then changed before saving.

The picker names the port after the row's Source as typed, saved or not
(test_console_patch_picker.UnnamedChannelTests). If the engineer then changes
the Source again -- back to the saved name, to blank, or to another name --
and saves the page, the port must end up with the channel's SAVED name and
the cell's "name not saved" flag must clear.

These tests save the real Console change form: every field the page renders,
posted back with one Source changed, as the browser would.

Run with::

    python manage.py test planner.tests.test_console_patch_save_names \\
        --settings=audiopatch.test_settings
"""

from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from django.db import connection
from django.test.utils import CaptureQueriesContext

from planner.models import ConsoleAuxOutput, ConsoleInput, DeviceInput, DeviceOutput
from planner.utils.device_patch import sync_port_names
from planner.tests.test_console_patch_picker import PickerFixture


class _FormFields(HTMLParser):
    """The fields of the page's main form, as a browser would submit them."""

    def __init__(self):
        super().__init__()
        self.data, self._select, self._options, self._textarea = {}, None, [], None
        self._in_form = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form' and a.get('id', '').endswith('_form'):
            self._in_form = True
        if not self._in_form or 'disabled' in a or not a.get('name') and tag != 'option':
            return
        if tag == 'input':
            kind = a.get('type', 'text')
            if kind in ('submit', 'button', 'file', 'image'):
                return
            if kind in ('checkbox', 'radio'):
                if 'checked' in a:
                    self.data.setdefault(a['name'], []).append(a.get('value', 'on'))
                return
            self.data[a['name']] = [a.get('value', '')]
        elif tag == 'select':
            self._select, self._options = a['name'], []
        elif tag == 'option' and self._select:
            self._options.append((a.get('value', ''), 'selected' in a))
        elif tag == 'textarea':
            self._textarea = a['name']
            self.data[a['name']] = ['']

    def handle_data(self, text):
        if self._textarea:
            self.data[self._textarea] = [self.data[self._textarea][0] + text]

    def handle_endtag(self, tag):
        if tag == 'form':
            self._in_form = False
        elif tag == 'textarea':
            self._textarea = None
        elif tag == 'select' and self._select:
            chosen = [v for v, sel in self._options if sel] or [v for v, _ in self._options[:1]]
            self.data[self._select] = chosen
            self._select = None


class SaveAfterTypedPatchTests(PickerFixture, TestCase):

    def page_url(self):
        return reverse('admin:planner_console_change', args=[self.foh.pk])

    def save_page(self, channel, source):
        """Save the Console page with ``channel``'s Source (a bus: its Name)
        set to ``source``."""
        page = self.client.get(self.page_url())
        self.assertEqual(page.status_code, 200)
        parser = _FormFields()
        parser.feed(page.content.decode())
        data = parser.data
        prefix = next(k[:-len('-id')] for k, v in data.items()
                      if k.endswith('-id') and v == [str(channel.pk)]
                      and k.startswith(type(channel).__name__.lower()))
        field = 'source' if isinstance(channel, ConsoleInput) else 'name'
        data[f'{prefix}-{field}'] = [source]
        data['_continue'] = ['Save and continue editing']
        response = self.client.post(self.page_url(), data)
        self.assertEqual(response.status_code, 302,
                         response.context and [f.errors for f in response.context.get('inline_admin_formsets', [])])

    def flagged(self, channel):
        return 'name not saved' in self.picker(channel)['cell_html']

    def test_saved_page_with_the_typed_name_agrees(self):
        """The case that already worked: type, patch, save."""
        self.post(self.kick, self.inport(1), name='Kick In')
        self.save_page(self.kick, 'Kick In')
        self.assertEqual(ConsoleInput.objects.get(pk=self.kick.pk).source, 'Kick In')
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.kick, 'Kick In'))
        self.assertFalse(self.flagged(self.kick))

    def test_typed_back_to_the_saved_name_then_saved(self):
        self.post(self.kick, self.inport(1), name='Kick In')
        self.save_page(self.kick, 'Kick')
        self.assertEqual(ConsoleInput.objects.get(pk=self.kick.pk).source, 'Kick')
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.kick, 'Kick'))
        self.assertFalse(self.flagged(self.kick))

    def test_unnamed_channel_typed_then_cleared_then_saved(self):
        self.post(self.blank, self.inport(1), name='Spare Vox')
        self.save_page(self.blank, '')
        self.assertEqual(ConsoleInput.objects.get(pk=self.blank.pk).source, '')
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.blank, ''))
        self.assertFalse(self.flagged(self.blank))

    def test_typed_another_name_then_saved(self):
        self.post(self.kick, self.inport(1), name='Kick In')
        self.save_page(self.kick, 'Kick Drum')
        self.assertEqual(ConsoleInput.objects.get(pk=self.kick.pk).source, 'Kick Drum')
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.kick, 'Kick Drum'))
        self.assertFalse(self.flagged(self.kick))

    def test_buses_typed_back_then_saved(self):
        for n, bus in ((1, self.aux), (2, self.mtx), (3, self.st_l)):
            with self.subTest(bus=type(bus).__name__):
                self.post(bus, self.out(n), name='Typed')
                self.assertTrue(self.flagged(bus))
                self.save_page(bus, bus.name)
                self.assertEqual((self.out(n).console_output, self.out(n).signal_name),
                                 (bus, bus.name))
                self.assertFalse(self.flagged(bus))

    def test_unnamed_bus_typed_then_cleared_then_saved(self):
        blank_aux = ConsoleAuxOutput.objects.create(console=self.foh, aux_number='2', name='')
        self.post(blank_aux, self.out(1), name='Sidefill')
        self.save_page(blank_aux, '')
        self.assertEqual((self.out(1).console_output, self.out(1).signal_name), (blank_aux, ''))

    def test_clearing_a_name_on_the_page_clears_its_linked_port(self):
        """A behaviour change: the page now leaves every linked port carrying
        its channel's saved name, so a channel renamed to blank there leaves
        a blank, still-linked port (the device page says "linked to … (unnamed)")
        rather than its last name, which would be flagged "name not saved"
        for good. (A rename to blank by any other path still keeps the last
        name: test_device_patch_link.)"""
        self.post(self.kick, self.inport(1))
        self.save_page(self.kick, '')
        self.assertEqual((self.inport(1).console_input, self.inport(1).signal_name),
                         (self.kick, ''))
        self.assertFalse(self.flagged(self.kick))

    def test_other_consoles_and_agreeing_ports_are_left_alone(self):
        self.post(self.kick, self.inport(1))
        DeviceInput.objects.filter(pk=self.inport(2).pk).update(
            console_input=self.snare, signal_name='SNARE ')      # case / space only
        DeviceInput.objects.filter(pk=self.inport(1, self.other_box).pk).update(
            console_input=self.other_kick, signal_name='Typed')  # another show
        self.assertEqual(sync_port_names(self.foh), 0)
        self.assertEqual(self.inport(2).signal_name, 'SNARE ')
        self.assertEqual(self.inport(1, self.other_box).signal_name, 'Typed')

    def test_sync_query_count_does_not_grow_with_ports(self):
        def count():
            DeviceInput.objects.filter(console_input__console=self.foh).update(signal_name='Typed')
            DeviceOutput.objects.filter(device__project=self.project).exclude(
                object_id=None).update(signal_name='Typed')
            with CaptureQueriesContext(connection) as q:
                sync_port_names(self.foh)
            return len(q)
        self.post(self.kick, self.inport(1))
        self.post(self.aux, self.out(1))
        few = count()
        for n in range(2, 9):
            DeviceInput.objects.filter(pk=self.inport(n).pk).update(console_input=self.kick)
        for n in range(2, 5):
            self.post(self.aux, self.out(n), mode='add')
        self.assertEqual(count(), few)
