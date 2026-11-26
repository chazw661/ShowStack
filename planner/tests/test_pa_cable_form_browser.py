"""The one-mode PA cable form in a real browser (PR 2b-1).

No Entry mode; the linked-arrays panel follows Django's filter_horizontal
picker, which moves options between two lists without a change event.

Daisy-chain links: the chain-icon "Linked" toggle shows the Links rows
(pa_cable_links.js), a new link starts at the run's Count and cable type,
the arrows reorder, a jumper link has no length, and switching Linked off
removes the links on Save and not before.

Skipped unless asked for (needs Playwright and its browsers)::

    SS_BROWSER_TESTS=1 python manage.py test planner.tests.test_pa_cable_form_browser \\
        --settings=audiopatch.test_settings
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.models import PACableLink, ProjectMember
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
        groups = page.eval_on_selector_all(
            '#id_source optgroup',
            'gs => gs.map(g => [g.label, [...g.children].map(o => o.textContent)])')
        self.assertEqual(groups, [['SL Racks', ['SL Racks \u2014 whole rack', 'SL LA12X #1 \u00b7 TEST4']]])
        page.select_option('#id_source', label='SL LA12X #1 \u00b7 TEST4')
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

    def test_the_whole_rack_saves_from_the_form(self):
        page = self.open(reverse('admin:planner_pacableschedule_add'))
        page.select_option('#id_source', label='SL Racks \u2014 whole rack')
        page.fill('#id_destination', 'KIVA DELAY 2 & 3')
        page.fill('#id_length', '100')
        page.click('input[name="_save"]')
        page.wait_for_load_state('networkidle')
        run = self.project.pacableschedule_set.get()
        self.assertEqual((run.amp, run.amp_location), (None, self.amp_a.location))
        self.assertEqual(page.input_value('#id_source'), f'rack:{self.amp_a.location_id}')
        self.assertEqual(self.errors, [])

    def test_the_form_fits_a_phone(self):
        page = self.open(reverse('admin:planner_pacableschedule_add'), width=390)
        page.wait_for_selector('#id_speaker_arrays_to', state='attached')
        self.shot(page, 'pa_cable_add_phone.png')
        self.assertEqual(self.errors, [])

    # -- daisy-chain links ----------------------------------------------------

    ROWS = '#links-group tbody tr.form-row:not(.empty-form)'

    def linked_run(self, *lengths):
        run = self.text_cable(destination='K2 Left', amp=self.amp_a, cable='NL_8',
                              count=2, length=75)
        for n, length in enumerate(lengths, start=1):
            PACableLink.objects.create(cable_schedule=run, order=n, cable='NL_4',
                                       length=length, quantity=2, note=f'link {length}')
        return run

    def positions(self, page):
        return page.eval_on_selector_all(self.ROWS + ' .pa-link-pos',
                                         'els => els.map(e => e.textContent)')

    def test_linked_off_by_default_then_add_reorder_and_save(self):
        page = self.open(reverse('admin:planner_pacableschedule_add'))
        toggle = page.locator('#pa-linked-toggle')
        self.assertEqual(toggle.get_attribute('aria-pressed'), 'false')
        self.assertFalse(page.locator('#links-group').is_visible())
        # The Links section sits right under the fieldset the toggle is in.
        self.assertTrue(page.evaluate(
            "document.getElementById('pa-linked-toggle').closest('fieldset')"
            ".nextElementSibling.id === 'links-group'"))

        page.select_option('#id_source', label='SL LA12X #1 \u00b7 TEST4')
        page.fill('#id_destination', 'K2 Left')
        page.fill('#id_count', '3')
        page.select_option('#id_cable', 'NL_8')
        page.fill('#id_length', '75')

        toggle.click()
        self.assertEqual(toggle.get_attribute('aria-pressed'), 'true')
        page.wait_for_selector(self.ROWS)
        self.assertTrue(page.locator('#links-group').is_visible())
        # A new link starts at the run's Count and the run's cable type.
        self.assertEqual(page.input_value('[name="links-0-quantity"]'), '3')
        self.assertEqual(page.input_value('[name="links-0-cable"]'), 'NL_8')
        page.fill('[name="links-0-length"]', '25')
        page.fill('[name="links-0-note"]', 'first')

        page.click('#links-group tr.add-row a')
        page.wait_for_function(f"document.querySelectorAll('{self.ROWS}').length === 2")
        page.select_option('[name="links-1-cable"]', 'NL_4')
        page.fill('[name="links-1-length"]', '50')
        page.fill('[name="links-1-quantity"]', '1')
        page.fill('[name="links-1-note"]', 'second')
        self.assertEqual(self.positions(page), ['Spk 1 \u2192 2', 'Spk 2 \u2192 3'])
        self.shot(page, 'pa_cable_links_on.png')

        # Move the second link earlier: the two rows' values swap.
        page.locator(self.ROWS).nth(1).locator('.pa-link-move').first.click()
        self.assertEqual(page.input_value('[name="links-0-note"]'), 'second')
        self.assertEqual(page.input_value('[name="links-1-note"]'), 'first')
        self.assertTrue(page.locator(self.ROWS).nth(0).locator('.pa-link-move').first.is_disabled())

        # A jumper link has no length.
        page.click('#links-group tr.add-row a')
        page.wait_for_function(f"document.querySelectorAll('{self.ROWS}').length === 3")
        page.select_option('[name="links-2-cable"]', 'NL4_JUMPER')
        self.assertFalse(page.locator('[name="links-2-length"]').is_visible())
        self.assertEqual(page.locator(self.ROWS).nth(2).locator('.pa-length-na').inner_text(),
                         '\u2014')

        page.click('input[name="_save"]')
        page.wait_for_load_state('networkidle')
        run = self.project.pacableschedule_set.get()
        self.assertEqual(
            list(run.links.values_list('order', 'quantity', 'cable', 'length', 'note')),
            [(1, 1, 'NL_4', 50, 'second'), (2, 3, 'NL_8', 25, 'first'),
             (3, 3, 'NL4_JUMPER', None, '')])
        page = self.open(reverse('admin:planner_pacableschedule_changelist'))
        self.assertEqual(page.eval_on_selector_all(
            '#result_list td.field-links_col .cb-link', 'els => els.map(e => e.textContent)'),
            ["1\u00d7 NL 4 50'", "3\u00d7 NL 8 25'", '3\u00d7 NL4 Jumper'])
        self.shot(page, 'pa_cable_links_list.png')
        self.assertEqual(self.errors, [])

    def test_a_linked_run_opens_on_and_off_removes_its_links_only_on_save(self):
        run = self.linked_run(25, 50)
        url = reverse('admin:planner_pacableschedule_change', args=[run.pk])
        page = self.open(url)
        toggle = page.locator('#pa-linked-toggle')
        self.assertEqual(toggle.get_attribute('aria-pressed'), 'true')
        self.assertEqual(page.locator(self.ROWS).count(), 2)

        toggle.click()
        self.assertEqual(toggle.get_attribute('aria-pressed'), 'false')
        self.assertIn('These 2 links will be removed when you save',
                      page.inner_text('.pa-links-off-note'))
        self.assertTrue(page.locator('#links-group').is_visible())
        self.shot(page, 'pa_cable_links_off.png')
        self.assertEqual(run.links.count(), 2)          # nothing is deleted yet

        # On again takes it back: saving now keeps both.
        toggle.click()
        self.assertFalse(page.locator('.pa-links-off-note').is_visible())
        page.click('input[name="_save"]')
        page.wait_for_load_state('networkidle')
        self.assertEqual(list(run.links.values_list('length', flat=True)), [25, 50])

        page = self.open(url)
        page.locator('#pa-linked-toggle').click()
        page.click('input[name="_save"]')
        page.wait_for_load_state('networkidle')
        self.assertEqual(run.links.count(), 0)
        self.assertTrue(self.project.pacableschedule_set.filter(pk=run.pk).exists())
        self.assertEqual(self.errors, [])

    def test_off_drops_a_link_that_was_never_saved(self):
        page = self.open(reverse('admin:planner_pacableschedule_add'))
        page.select_option('#id_source', label='SL LA12X #1 \u00b7 TEST4')
        page.fill('#id_destination', 'K2 Left')
        page.fill('#id_length', '75')
        toggle = page.locator('#pa-linked-toggle')
        toggle.click()
        page.wait_for_selector(self.ROWS)
        toggle.click()
        self.assertEqual(page.locator(self.ROWS).count(), 0)
        self.assertFalse(page.locator('#links-group').is_visible())
        page.click('input[name="_save"]')
        page.wait_for_load_state('networkidle')
        self.assertEqual(self.project.pacableschedule_set.get().links.count(), 0)
        self.assertEqual(self.errors, [])

    def test_a_viewer_sees_the_links_and_a_toggle_that_does_nothing(self):
        from django.contrib.auth import get_user_model
        run = self.linked_run(25)
        viewer = get_user_model().objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=self.project, role='viewer',
                                     invited_by=self.user)
        self.client.force_login(viewer)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        page = self.open(reverse('admin:planner_pacableschedule_change', args=[run.pk]))
        toggle = page.locator('#pa-linked-toggle')
        self.assertTrue(toggle.is_disabled())
        self.assertEqual(toggle.get_attribute('aria-pressed'), 'true')
        self.assertIn('link 25', page.inner_text('#links-group'))
        self.assertEqual(page.locator('#links-group .pa-link-move').count(), 0)
        self.assertEqual(page.locator('#links-group input:not([type=hidden])').count(), 0)
        self.assertEqual(self.errors, [])

    def test_the_links_fit_a_phone(self):
        run = self.linked_run(25, 50)
        page = self.open(reverse('admin:planner_pacableschedule_change', args=[run.pk]),
                         width=390)
        self.assertEqual(page.locator(self.ROWS).count(), 2)
        self.assertTrue(page.locator('#pa-linked-toggle').is_visible())
        self.shot(page, 'pa_cable_links_phone.png')
        self.assertEqual(self.errors, [])
