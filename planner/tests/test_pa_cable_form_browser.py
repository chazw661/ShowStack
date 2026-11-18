"""The one-mode PA cable form in a real browser (PR 2b-1).

No Entry mode; the linked-arrays panel follows Django's filter_horizontal
picker, which moves options between two lists without a change event.

Skipped unless asked for (needs Playwright and its browsers)::

    SS_BROWSER_TESTS=1 python manage.py test planner.tests.test_pa_cable_form_browser \\
        --settings=audiopatch.test_settings
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.tests.connection_fixtures import ConnectionFixtures

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

BROWSER = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None
SHOTS = os.environ.get('SS_SCREENSHOT_DIR')     # optional: where to save screenshots


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class PaCableFormBrowserTests(ConnectionFixtures, StaticLiveServerTestCase):

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
        self.amp_a = self.amp('SL LA12X #1', rack='SL Racks')
        pred = self.prediction()
        self.k2 = self.array(pred, 'K2 L')
        self.kara = self.array(pred, 'KARA Fill')

    def open(self, url, width=1280):
        context = self.browser.new_context(viewport={'width': width, 'height': 900})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + url)
        page.wait_for_load_state('networkidle')
        return page

    def shot(self, page, name):
        if SHOTS:
            page.screenshot(path=os.path.join(SHOTS, name), full_page=True)

    def test_no_entry_mode_and_the_panel_follows_the_picker(self):
        page = self.open(reverse('admin:planner_pacableschedule_add'))
        self.shot(page, 'pa_cable_add_desktop.png')
        self.assertEqual(page.locator('#id_entry_mode').count(), 0)
        self.assertEqual(page.locator('#id_speaker_array').count(), 0)
        page.wait_for_selector('#id_speaker_arrays_to', state='attached')
        self.assertIn('Link a speaker array', page.inner_text('#pa-array-ref'))

        page.select_option('#id_speaker_arrays_from', label='K2 L (show.pdf)')
        page.click('#id_speaker_arrays_add')
        page.wait_for_selector('#pa-array-ref .pa-array-ref__arrayname')
        page.select_option('#id_speaker_arrays_from', label='KARA Fill (show.pdf)')
        page.click('#id_speaker_arrays_add')
        page.wait_for_function(
            "document.querySelectorAll('#pa-array-ref .pa-array-ref__arrayname').length === 2")
        names = page.eval_on_selector_all('#pa-array-ref .pa-array-ref__arrayname',
                                          'els => els.map(e => e.textContent)')
        self.assertEqual(sorted(names), sorted([self.k2.display_name, self.kara.display_name]))
        self.shot(page, 'pa_cable_add.png')

        page.select_option('#id_speaker_arrays_to', label='K2 L (show.pdf)')
        page.click('#id_speaker_arrays_remove')
        page.wait_for_function(
            "document.querySelectorAll('#pa-array-ref .pa-array-ref__arrayname').length === 1")
        self.assertEqual(self.errors, [])

    def test_a_new_run_saves_from_the_form(self):
        page = self.open(reverse('admin:planner_pacableschedule_add'))
        page.select_option('#id_amp', label='SL Racks · SL LA12X #1')
        page.fill('#id_destination', 'KIVA DELAY 2 & 3')
        page.fill('#id_length', '100')
        page.click('input[name="_save"]')
        page.wait_for_load_state('networkidle')
        run = self.project.pacableschedule_set.get()
        self.assertEqual((run.amp, run.amp_location, run.destination),
                         (self.amp_a, self.amp_a.location, 'KIVA DELAY 2 & 3'))
        page = self.open(reverse('admin:planner_pacableschedule_changelist'))
        self.shot(page, 'pa_cable_list.png')
        self.assertEqual(self.errors, [])

    def test_the_form_fits_a_phone(self):
        page = self.open(reverse('admin:planner_pacableschedule_add'), width=390)
        page.wait_for_selector('#id_speaker_arrays_to', state='attached')
        self.shot(page, 'pa_cable_add_phone.png')
        self.assertEqual(self.errors, [])
