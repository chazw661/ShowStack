"""Console page picker in a real browser: touch, iPad sizes, Chromium + WebKit.

Skipped unless asked for, because it needs Playwright and its browsers, which
the deploy does not install::

    SS_BROWSER_TESTS=1 python manage.py test \\
        planner.tests.test_console_patch_picker_browser \\
        --settings=audiopatch.test_settings

(``pip install playwright && playwright install chromium webkit`` once.)
Add ``SS_BROWSER_SHOTS=<dir>`` to keep a screenshot of each step.

For each browser and each iPad viewport, with touch on (coarse pointer),
logged in as an editor of the show:

  * the panel fits the window -- no page scroll sideways, nothing off-screen
  * every control in it is a 44px target, and so is the Patch cell
  * tap a cell -> device -> free port: the port is linked (in the database),
    that cell and the free-ports block change, and NOTHING else does: an
    unsaved edit typed into another row is still there, the page was not
    reloaded and the console form was not submitted
  * a patched channel asks Replace or Add; Replace swaps the ports
  * a stale page (the patch changed behind it) gets the fresh cell and a
    message, and writes nothing
  * Unpatch frees the port

and an unnamed channel: the panel says so (a note, not an error), a name
typed in the row and not saved names the port (the cell says "name not
saved", and leaving the page asks first), and saving the page after leaves
port and channel agreeing;

and, as a viewer, the cells are read-only links with no picker.
"""

import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.models import ConsoleInput, DeviceInput
from planner.tests.test_console_patch_picker import PickerFixture

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ENABLED = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

# The four iPad sizes the console grids were measured at (#111), both ways up.
VIEWPORTS = [(768, 1024), (820, 1180), (1024, 768), (1180, 820)]
BROWSERS = ['chromium', 'webkit']
TAP = 44


@unittest.skipUnless(ENABLED, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class PickerBrowserTests(PickerFixture, StaticLiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')  # sync Playwright
        super().setUpClass()
        cls.pw = sync_playwright().start()
        cls.browsers = {name: getattr(cls.pw, name).launch() for name in BROWSERS}

    @classmethod
    def tearDownClass(cls):
        for b in cls.browsers.values():
            b.close()
        cls.pw.stop()
        super().tearDownClass()

    # -- helpers -------------------------------------------------------------

    def open_page(self, browser, size, user):
        self.as_user(user, self.project)
        context = self.browsers[browser].new_context(
            viewport={'width': size[0], 'height': size[1]},
            has_touch=True, is_mobile=browser == 'chromium', device_scale_factor=2)
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        # Patch view on, so the column shows at every width (#111's switch).
        context.add_init_script("try{localStorage.setItem('ss.consolePatchView','patch')}catch(e){}")
        page = context.new_page()
        page.goto(self.live_server_url + reverse('admin:planner_console_change', args=[self.foh.pk]))
        page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        page.evaluate('window.__ssMarker = 1')   # gone if the page reloads
        self.addCleanup(context.close)
        return page

    def cell(self, page, channel):
        return page.locator(f'.ss-patch-edit[data-patch-url="{self.url(channel)}"]')

    def assert_fits(self, page, what):
        overflow = page.evaluate(
            'document.documentElement.scrollWidth - document.documentElement.clientWidth')
        self.assertLessEqual(overflow, 0, f'{what}: page scrolls sideways by {overflow}px')
        box = page.locator('.ss-pp').bounding_box()
        vw, vh = page.viewport_size['width'], page.viewport_size['height']
        self.assertGreaterEqual(box['x'], 0, what)
        self.assertGreaterEqual(box['y'], 0, what)
        self.assertLessEqual(box['x'] + box['width'], vw, what)
        self.assertLessEqual(box['y'] + box['height'], vh, what)
        small = page.evaluate(f"""
            [...document.querySelectorAll('.ss-pp button')]
              .filter(b => b.offsetParent)
              .map(b => [b.textContent.trim(), b.getBoundingClientRect().height,
                         b.getBoundingClientRect().width])
              .filter(([t, h, w]) => h < {TAP} || w < {TAP})""")
        self.assertEqual(small, [], f'{what}: controls under {TAP}px')

    def shot(self, page, what, step):
        folder = os.environ.get('SS_BROWSER_SHOTS')
        if folder:
            os.makedirs(folder, exist_ok=True)
            page.screenshot(path=os.path.join(folder, f"{what.replace(' ', '_')}_{step}.png"))

    def wait_closed(self, page):
        page.wait_for_selector('.ss-pp-backdrop', state='hidden')

    # -- the run ---------------------------------------------------------------

    def test_editor_patches_by_touch_at_every_ipad_size(self):
        for browser in BROWSERS:
            for size in VIEWPORTS:
                with self.subTest(browser=browser, size=size):
                    self.run_editor(browser, size)

    def run_editor(self, browser, size):
        DeviceInput.objects.filter(device__project=self.project).update(
            signal_name='', console_input=None)
        what = f'{browser} {size[0]}x{size[1]}'
        page = self.open_page(browser, size, self.owner)

        # An unsaved edit somewhere else on the page.
        other = page.locator('input[name$="-source"]').nth(1)
        other.fill('Snare (unsaved)')

        kick = self.cell(page, self.kick)
        kick.scroll_into_view_if_needed()
        cell_box = page.locator(f'td.field-patch:has([data-patch-url="{self.url(self.kick)}"])').bounding_box()
        self.assertGreaterEqual(cell_box['height'], TAP - 1, f'{what}: cell target')

        # Patch: cell -> device -> free port 1.
        kick.tap()
        page.wait_for_selector('.ss-pp-device')
        self.shot(page, what, '1_devices')
        self.assert_fits(page, what)
        page.locator('.ss-pp-device', has_text='Stage Box A').tap()
        page.wait_for_selector('.ss-pp-port.is-free')
        self.shot(page, what, '2_ports')
        self.assert_fits(page, what)
        page.locator('.ss-pp-port.is-free', has_text='1').first.tap()
        self.wait_closed(page)
        self.shot(page, what, '3_patched')
        self.assertEqual(self.inport(1).console_input_id, self.kick.pk, what)
        self.assertIn('Stage Box A', kick.inner_text())
        self.assertIn('7 free inputs', page.locator('.ss-patch-free').inner_text())

        # Nothing else moved: same page, edit kept, form not submitted.
        self.assertEqual(page.evaluate('window.__ssMarker'), 1, f'{what}: page reloaded')
        self.assertEqual(other.input_value(), 'Snare (unsaved)', what)
        self.assertEqual(self.snare.__class__.objects.get(pk=self.snare.pk).source, 'Snare')

        # Replace needs an explicit choice.
        self.cell(page, self.kick).tap()
        page.locator('.ss-pp-device', has_text='Stage Box A').tap()
        page.locator('.ss-pp-port.is-free', has_text='2').first.tap()
        page.wait_for_selector('.ss-pp-choice')
        self.shot(page, what, '4_choice')
        self.assert_fits(page, what)
        self.assertEqual(self.inport(2).console_input_id, None, f'{what}: sent before choosing')
        page.locator('.ss-pp-primary', has_text='Replace').tap()
        self.wait_closed(page)
        self.assertEqual((self.inport(1).console_input_id, self.inport(2).console_input_id),
                         (None, self.kick.pk), what)

        # Stale: patched behind the page's back while the picker is open.
        self.cell(page, self.kick).tap()
        page.locator('.ss-pp-device', has_text='Stage Box B').tap()
        page.wait_for_selector('.ss-pp-port.is-free')
        self.link(self.inport(5), self.kick)
        page.locator('.ss-pp-port.is-free', has_text='3').first.tap()
        page.wait_for_selector('.ss-pp-choice')
        page.locator('.ss-pp-primary').tap()
        page.wait_for_selector('.ss-pp-msg.is-warn')
        self.shot(page, what, '5_stale')
        self.assertIsNone(self.inport(3, self.box_b).console_input_id, what)
        self.assertIn('In 5', self.cell(page, self.kick).inner_text())

        # Unpatch, from the same (now fresh) panel.
        page.locator('.ss-pp-unpatch').first.tap()
        page.wait_for_selector('.ss-pp-msg.is-ok')
        self.assertEqual(DeviceInput.objects.filter(console_input=self.kick).count(), 1, what)
        page.locator('.ss-pp-close').tap()
        self.wait_closed(page)
        self.assertEqual(other.input_value(), 'Snare (unsaved)', what)
        self.assertEqual(page.evaluate('window.__ssMarker'), 1, what)

    def test_viewer_gets_read_only_cells(self):
        viewer = self.member('viewer', 'viewer')
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                self.link(self.inport(1), self.kick)
                page = self.open_page(browser, (820, 1180), viewer)
                self.assertEqual(page.locator('.ss-patch-edit').count(), 0)
                self.assertGreater(page.locator('td.field-patch a').count(), 0)
                page.locator('td.field-patch a').first.tap()
                page.wait_for_url('**/device/**')

    def test_unnamed_channel_typed_name_patch_then_save(self):
        """Ch 3 has no saved name. The panel says so (informational); typing a
        name and patching names the port without saving the page; saving the
        page afterwards leaves port and channel agreeing, still linked."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                ConsoleInput.objects.filter(pk=self.blank.pk).update(source='')
                DeviceInput.objects.filter(device__project=self.project).update(
                    signal_name='', console_input=None)
                page = self.open_page(browser, (1180, 820), self.owner)
                cell = self.cell(page, self.blank)
                source = page.locator('tr', has=cell).locator('input[name$="-source"]')

                cell.tap()
                page.wait_for_selector('.ss-pp-device')
                self.assertIn('Ch 3 is unnamed — the port will take its name when you save.',
                              page.locator('.ss-pp-info').inner_text())
                self.assertEqual(page.locator('.ss-pp-msg.is-error:visible').count(), 0)
                page.locator('.ss-pp-close').tap()
                self.wait_closed(page)

                source.fill('Spare Vox')
                cell.tap()
                page.wait_for_selector('.ss-pp-device')
                self.assertIn('not saved yet', page.locator('.ss-pp-info').inner_text())
                page.locator('.ss-pp-device', has_text='Stage Box A').tap()
                page.locator('.ss-pp-port.is-free', has_text='1').first.tap()
                self.wait_closed(page)
                port = self.inport(1)
                self.assertEqual((port.console_input_id, port.signal_name),
                                 (self.blank.pk, 'Spare Vox'))
                self.assertEqual(ConsoleInput.objects.get(pk=self.blank.pk).source, '')
                self.assertEqual(source.input_value(), 'Spare Vox')
                self.assertIn('name not saved', cell.inner_text())

                # Leaving now asks first (and staying keeps everything).
                dialogs = []
                page.on('dialog', lambda d: (dialogs.append(d.type), d.dismiss()))
                url = page.url
                self.try_to_leave(page)
                self.assertEqual(dialogs, ['beforeunload'])
                self.assertEqual(page.url, url)
                self.assertEqual(source.input_value(), 'Spare Vox')

                # Saving does not ask, and leaves port and channel agreeing.
                with page.expect_navigation():
                    page.locator('input[name="_continue"]').click()
                self.assertEqual(dialogs, ['beforeunload'])
                port = self.inport(1)
                self.assertEqual(ConsoleInput.objects.get(pk=self.blank.pk).source, 'Spare Vox')
                self.assertEqual((port.console_input_id, port.signal_name),
                                 (self.blank.pk, 'Spare Vox'))
                page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                self.assertNotIn('name not saved', self.cell(page, self.blank).inner_text())

    def try_to_leave(self, page):
        page.evaluate("setTimeout(() => { location.href = '/admin/'; }, 0)")
        page.wait_for_timeout(1500)

    def test_leaving_asks_only_while_a_patched_name_is_unsaved(self):
        """Typed, patched, then typed back to the saved name: nothing is
        unsaved, so leaving does not ask."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                DeviceInput.objects.filter(device__project=self.project).update(
                    signal_name='', console_input=None)
                page = self.open_page(browser, (1180, 820), self.owner)
                cell = self.cell(page, self.kick)
                source = page.locator('tr', has=cell).locator('input[name$="-source"]')
                source.fill('Kick In')
                cell.tap()
                page.locator('.ss-pp-device', has_text='Stage Box A').tap()
                page.locator('.ss-pp-port.is-free', has_text='1').first.tap()
                self.wait_closed(page)
                self.assertEqual(self.inport(1).signal_name, 'Kick In')
                source.fill('Kick')
                dialogs = []
                page.on('dialog', lambda d: (dialogs.append(d.type), d.dismiss()))
                self.try_to_leave(page)
                self.assertEqual(dialogs, [])
                self.assertTrue(page.url.endswith('/admin/'), page.url)
