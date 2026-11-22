"""B input patches in a real browser, reached the way an engineer gets there:
the sidebar, not typed URLs.

Skipped unless asked for (needs Playwright and Chromium)::

    SS_BROWSER_TESTS=1 python manage.py test \\
        planner.tests.test_console_b_patch_browser \\
        --settings=audiopatch.test_settings

As ``paidtest`` -- a paid owner, not a superuser:

  * sidebar -> Consoles -> the console -> "B Inputs": the Patch (B) column is
    blank though A is patched, the A name shows read-only; tap Patch (B) ->
    device -> port: B is stored, A untouched; the own-A port warns first
  * sidebar -> I/O Devices -> the device: the narrow B picker sets a B, which
    the Console page's B view then shows

and as a viewer, the same route: no picker on Patch (B), the B select is
disabled.

Add ``SS_BROWSER_SHOTS=<dir>`` to keep a screenshot of each page.
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from planner.models import DeviceInput, ProjectMember
from planner.tests.test_console_b_patch import BFixture, make_user

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ENABLED = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None


@unittest.skipUnless(ENABLED, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class BPatchBrowserTests(BFixture, StaticLiveServerTestCase):

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

    def open_dashboard(self, user):
        self.login(user)
        context = self.browser.new_context(viewport={'width': 1440, 'height': 900})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + '/admin/')
        page.wait_for_load_state('networkidle')
        return page

    def shot(self, page, name):
        where = os.environ.get('SS_BROWSER_SHOTS')
        if where:
            page.screenshot(path=os.path.join(where, f'b_patch_{name}.png'), full_page=True)

    def sidebar(self, page, model):
        link = page.locator(f'#nav-sidebar a[href$="/planner/{model}/"]').first
        link.click()
        page.wait_for_load_state('networkidle')

    def to_console(self, page):
        self.sidebar(page, 'console')
        page.click(f'a[href$="/planner/console/{self.foh.pk}/change/"]')
        page.wait_for_load_state('networkidle')
        page.click('.ab-input-toggle__btn:has-text("B Inputs")')

    def visible_texts(self, page, selector):
        return page.evaluate('(s) => [...document.querySelectorAll(s)]'
                             '.filter(e => e.offsetParent !== null).map(e => e.textContent.trim())',
                             selector)

    def test_paid_owner_patches_b_from_the_console_page_via_the_sidebar(self):
        self.set_a(self.inport(1), self.kick)
        page = self.open_dashboard(self.owner)
        self.to_console(page)
        # Inputs inline is collapsed by default.
        toggle = page.locator('#consoleinput_set-group summary, #consoleinput_set-group .collapse-toggle')
        if toggle.count():
            toggle.first.click()
        self.assertFalse(page.locator('#consoleinput_set-group th.column-patch').first.is_visible())
        self.assertTrue(page.locator('#consoleinput_set-group th.column-patch_b').first.is_visible())
        names = self.visible_texts(page, '#consoleinput_set-group td.field-a_name')
        self.assertEqual(names[:3], ['Kick', 'Snare', 'Vox'])
        b_cells = self.visible_texts(page, '#consoleinput_set-group td.field-patch_b')
        self.assertEqual(b_cells[:3], ['+ Patch'] * 3)       # blank though Ch 1 has an A

        # Patch (B) on Ch 1 -> Stage Box A -> In 1, its own A port: warns first.
        page.locator('#consoleinput_set-group td.field-patch_b .ss-patch-edit').first.click()
        page.wait_for_selector('.ss-pp-device')
        self.assertIn('(B)', page.text_content('#ss-pp-title'))
        page.click('.ss-pp-device:has-text("Stage Box A")')
        port1 = page.locator('.ss-pp-port').first
        self.assertIn('same port as A', port1.text_content())
        port1.click()
        page.wait_for_selector('.ss-pp-choice')
        self.assertIn('same port as A', page.text_content('.ss-pp-choice'))
        page.click('.ss-pp-choice .ss-pp-primary')
        page.wait_for_function("document.querySelector('.ss-pp-backdrop').hidden")
        p = self.inport(1)
        self.assertEqual((p.console_input_id, p.console_input_b_id), (self.kick.pk, self.kick.pk))
        cell = page.locator('#consoleinput_set-group td.field-patch_b').first.text_content()
        self.shot(page, 'console_b_view')
        self.assertIn('Stage Box A', cell)
        self.assertIn('same port as A', cell)

        # Replace it with In 5 (B only); there is no Add for B.
        page.locator('#consoleinput_set-group td.field-patch_b .ss-patch-edit').first.click()
        page.wait_for_selector('.ss-pp-device')
        page.click('.ss-pp-device:has-text("Stage Box A")')
        page.locator('.ss-pp-port.is-free').nth(3).click()     # In 5 (In 1 is "here")
        page.wait_for_selector('.ss-pp-choice')
        self.assertEqual(page.locator('.ss-pp-choice .ss-pp-warn').count(), 0)
        page.click('.ss-pp-choice .ss-pp-primary')
        page.wait_for_function("document.querySelector('.ss-pp-backdrop').hidden")
        self.assertIsNone(self.inport(1).console_input_b_id)
        self.assertEqual(self.inport(1).console_input_id, self.kick.pk)
        self.assertEqual(self.inport(5).console_input_b_id, self.kick.pk)
        self.assertEqual(self.errors, [])

    def test_paid_owner_sets_b_on_the_device_page_via_the_sidebar(self):
        page = self.open_dashboard(self.owner)
        self.sidebar(page, 'device')
        page.click(f'a[href$="/planner/device/{self.box.pk}/change/"]')
        page.wait_for_load_state('networkidle')
        select = page.locator('select[name="inputs-2-b_ref"]')
        self.assertTrue(select.is_visible())
        width = select.evaluate('e => e.getBoundingClientRect().width')
        cell = select.evaluate('e => e.closest("td").getBoundingClientRect().width')
        self.assertLessEqual(width, cell)                      # narrow: inside its port's cell
        select.select_option(str(self.vox.pk))
        self.shot(page, 'device_page')
        page.click('input[name="_continue"]')
        page.wait_for_load_state('networkidle')
        self.assertEqual(self.inport(3).console_input_b_id, self.vox.pk)
        self.assertIsNone(self.inport(3).console_input_id)
        self.assertEqual(self.inport(3).signal_name, '')
        # The Console page's B view now shows it, on Ch 5 only.
        self.to_console(page)
        b_cells = page.evaluate("[...document.querySelectorAll('#consoleinput_set-group "
                                "td.field-patch_b')].map(e => e.textContent.trim())")
        self.assertIn('Stage Box A · In 3', b_cells[2])
        self.assertNotIn('Stage Box', b_cells[0])
        self.assertEqual(self.errors, [])

    def test_viewer_gets_no_b_picker_and_a_disabled_b_select(self):
        viewer = make_user('viewer1', 'free', 'Viewer')
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.owner)
        DeviceInput.objects.filter(pk=self.inport(2).pk).update(console_input_b=self.kick)
        page = self.open_dashboard(viewer)
        self.to_console(page)
        self.assertEqual(page.locator('#consoleinput_set-group td.field-patch_b .ss-patch-edit')
                         .count(), 0)
        self.assertIn('Stage Box A',
                      page.locator('#consoleinput_set-group td.field-patch_b').first.text_content())
        self.sidebar(page, 'device')
        page.click(f'a[href$="/planner/device/{self.box.pk}/change/"]')
        page.wait_for_load_state('networkidle')
        self.assertTrue(page.locator('select[name="inputs-1-b_ref"]').is_disabled())
        self.assertEqual(self.errors, [])
