"""Amp and processor input pickers in a real browser (PR 2b-2, 2b-3).

The datalist is the picker: an entry typed or picked links the input, other
text unlinks it, and the in-cell button's "Unlink (keep text)" drops the link
and leaves the text. The button sits inside the cell, so no row gets wider.

Skipped unless asked for (needs Playwright and its browsers)::

    SS_BROWSER_TESTS=1 python manage.py test planner.tests.test_amp_input_links_browser \\
        --settings=audiopatch.test_settings
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.models import Connection
from planner.tests.connection_fixtures import ConnectionFixtures

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

BROWSER = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None
SHOTS = os.environ.get('SS_SCREENSHOT_DIR')

AVB = 'AVB 3 - L Main (SL P1)'
AES = 'CENTER · Stage Box Out 1'


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class AmpInputPickerBrowserTests(ConnectionFixtures, StaticLiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')  # sync Playwright
        super().setUpClass()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        self.sl = self.p1('SL P1')
        self.p1_out(self.sl, 'AVB', 3, 'L Main')
        self.box = self.device('Stage Box')
        self.out1 = self.device_output(self.box, 1, 'CENTER')
        self.amp4 = self.amp('SL Amp 1')
        self.amp16 = self.amp('SL Amp 16', channels=16)
        self.ch1 = self.amp4.channels.get(channel_number=1)
        # Every AVB row shown: an empty one is folded away until revealed.
        for amp in (self.amp4, self.amp16):
            amp.channels.update(analog_input='x')

    def open(self, width=1280):
        context = self.browser.new_context(viewport={'width': width, 'height': 900})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + reverse('admin:planner_amp_changelist'))
        page.wait_for_load_state('networkidle')
        return page

    def cell(self, channel, field):
        return f'td.amp-input-cell:has(input[data-channel-id="{channel.pk}"][data-field="{field}"])'

    def enter(self, page, channel, field, text):
        selector = f'input.amp-cell-input[data-channel-id="{channel.pk}"][data-field="{field}"]'
        page.fill(selector, text)
        with page.expect_response(lambda r: 'inline-update' in r.url):
            page.press(selector, 'Tab')

    def linked(self, page, channel, field):
        return page.eval_on_selector(self.cell(channel, field), 'td => td.classList.contains("linked")')

    def test_the_datalists_list_every_source(self):
        page = self.open()
        avb = page.eval_on_selector_all('#amp-avb-input-options option', 'os => os.map(o => o.value)')
        aes = page.eval_on_selector_all('#amp-aes-input-options option', 'os => os.map(o => o.value)')
        self.assertIn(AVB, avb)
        self.assertIn(AES, aes)
        self.assertNotIn(AES, avb)
        self.assertEqual(self.errors, [])

    def test_selecting_an_entry_links_and_editing_away_unlinks(self):
        page = self.open()
        self.enter(page, self.ch1, 'avb_stream', AVB)
        self.assertTrue(self.linked(page, self.ch1, 'avb_stream'))
        self.assertEqual(page.get_attribute(self.cell(self.ch1, 'avb_stream') + ' .amp-link-btn', 'title'),
                         f'Linked to {AVB}')
        self.assertEqual(Connection.objects.get().to_id, self.ch1.pk)
        self.shot(page, 'amp_inputs_linked.png')
        self.enter(page, self.ch1, 'avb_stream', 'AVB 3')
        self.assertFalse(self.linked(page, self.ch1, 'avb_stream'))
        self.assertFalse(Connection.objects.exists())
        self.assertEqual(self.errors, [])

    def test_unlink_keeps_the_text(self):
        page = self.open()
        self.enter(page, self.ch1, 'aes_input', AES)
        page.click(self.cell(self.ch1, 'aes_input') + ' .amp-link-btn')
        page.wait_for_selector('#amp-link-menu:not([hidden])')
        with page.expect_response(lambda r: 'inline-update' in r.url):
            page.click('#amp-link-unlink')
        self.assertFalse(self.linked(page, self.ch1, 'aes_input'))
        self.assertFalse(Connection.objects.exists())
        self.assertEqual(page.input_value(
            f'input[data-channel-id="{self.ch1.pk}"][data-field="aes_input"]'), AES)
        self.ch1.refresh_from_db()
        self.assertEqual(self.ch1.aes_input, AES)
        self.assertEqual(self.errors, [])

    def test_no_row_gets_wider(self):
        for amp in (self.amp4, self.amp16):
            for n, ch in enumerate(amp.channels.order_by('channel_number')[:2], start=1):
                Connection.objects.create(project=self.project, from_ct_id=_ct('deviceoutput'),
                                          from_id=self.out1.pk, to_ct_id=_ct('ampchannel'),
                                          to_id=ch.pk, transport='aes')
        for width in (1280, 1024, 810):
            with self.subTest(width=width):
                page = self.open(width)
                report = page.evaluate("""() => {
                    const out = {overflow: [], outside: [], rows: []};
                    document.querySelectorAll('.amp-input-table').forEach(t => {
                        const box = t.parentElement.getBoundingClientRect();
                        const r = t.getBoundingClientRect();
                        if (r.right > box.right + 0.5) out.overflow.push(r.right - box.right);
                        const linked = [...t.querySelectorAll('td.amp-input-cell.linked')]
                                        .map(td => td.parentElement.getBoundingClientRect().height);
                        const plain = [...t.querySelectorAll('td.amp-input-cell:not(.linked)')]
                                        .map(td => td.parentElement.getBoundingClientRect().height);
                        if (linked.length) out.rows.push([Math.max(...linked), Math.min(...plain)]);
                    });
                    document.querySelectorAll('.amp-link-btn').forEach(b => {
                        const r = b.getBoundingClientRect(), c = b.closest('td').getBoundingClientRect();
                        if (r.left < c.left - 0.5 || r.right > c.right + 0.5 ||
                            r.top < c.top - 0.5 || r.bottom > c.bottom + 0.5) out.outside.push(b.dataset.field);
                    });
                    return out;
                }""")
                self.assertEqual(report['overflow'], [])
                self.assertEqual(report['outside'], [])
                self.assertEqual(len(report['rows']), 2)          # both amps have linked rows
                for linked, plain in report['rows']:
                    self.assertAlmostEqual(linked, plain, delta=0.5)
                self.shot(page, f'amp_inputs_{width}.png')
                self.assertEqual(self.errors, [])

    def shot(self, page, name):
        if SHOTS:
            page.screenshot(path=os.path.join(SHOTS, name), full_page=True)


def _ct(model):
    from django.contrib.contenttypes.models import ContentType
    return ContentType.objects.get(app_label='planner', model=model).pk


PROC = 'Left · Y001 Out 1'


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ProcessorInputPickerBrowserTests(ConnectionFixtures, StaticLiveServerTestCase):
    """PR 2b-3: the P1 page's AES / Analog inputs pick a source and save it."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')  # sync Playwright
        super().setUpClass()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        self.sl = self.p1('SL P1')
        self.box = self.device('Y001')
        self.left = self.device_output(self.box, 1, 'Left')
        self.matrix(self.console('FOH PM5'), 3, name='Lobby')
        from planner.models import P1Input
        self.aes1 = P1Input.objects.get(p1_processor__system_processor=self.sl,
                                        input_type='AES', channel_number=1)

    def open(self):
        context = self.browser.new_context(viewport={'width': 1280, 'height': 900})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + reverse('admin:planner_p1processor_change',
                                                 args=[self.sl.p1_config.pk]))
        page.wait_for_load_state('networkidle')
        return page

    def cell(self):
        return f'td.proc-input-cell:has(.proc-link-btn[data-input-id="{self.aes1.pk}"])'

    def save(self, page):
        with page.expect_navigation():
            page.click('input[name="_continue"]')
        page.wait_for_load_state('networkidle')

    def test_picking_from_the_grouped_list_links_on_save(self):
        page = self.open()
        page.click(self.cell() + ' .label-field input')
        page.wait_for_selector('.combobox-opt-group')
        headers = page.eval_on_selector_all('.combobox-opt-group', 'hs => hs.map(h => h.textContent)')
        self.assertEqual(headers, ['Y001', 'FOH PM5'])
        page.click(f'.combobox-opt:text-is("{PROC}")')
        self.assertEqual(page.input_value(self.cell() + ' .label-field input'), PROC)
        self.save(page)
        self.assertEqual(Connection.objects.get().from_id, self.left.pk)
        self.assertTrue(page.eval_on_selector(self.cell(), 'td => td.classList.contains("linked")'))
        self.assertEqual(page.get_attribute(self.cell() + ' .proc-link-btn', 'title'),
                         f'Linked to {PROC}')
        self.shot(page, 'p1_inputs_linked.png')
        self.assertEqual(self.errors, [])

    def test_typing_away_warns_then_saving_unlinks(self):
        self.aes1.label = PROC
        self.aes1.save()
        from planner.connections import processor_sources
        processor_sources.link_from_text(self.aes1)
        page = self.open()
        page.fill(self.cell() + ' .label-field input', 'Left')
        self.assertIn('Saving this text will unlink it',
                      page.get_attribute(self.cell() + ' .proc-link-btn', 'title'))
        self.save(page)
        self.assertFalse(Connection.objects.exists())
        self.assertEqual(self.errors, [])

    def test_unlink_keeps_the_text(self):
        self.aes1.label = PROC
        self.aes1.save()
        from planner.connections import processor_sources
        processor_sources.link_from_text(self.aes1)
        page = self.open()
        page.click(self.cell() + ' .proc-link-btn')
        page.wait_for_selector('#proc-link-menu:not([hidden])')
        with page.expect_response(lambda r: '/unlink/' in r.url):
            page.click('#proc-link-unlink')
        self.assertFalse(page.eval_on_selector(self.cell(), 'td => td.classList.contains("linked")'))
        self.assertFalse(Connection.objects.exists())
        self.assertEqual(page.input_value(self.cell() + ' .label-field input'), PROC)
        self.aes1.refresh_from_db()
        self.assertEqual(self.aes1.label, PROC)
        self.assertEqual(self.errors, [])

    shot = AmpInputPickerBrowserTests.shot
