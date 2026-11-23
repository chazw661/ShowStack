"""The comm device page in a real browser: add one from the device list,
patch it by picking from the lists, see the other-network warning while
typing, and follow the read-only link back from the other device.

Skipped unless asked for (needs Playwright and Chromium)::

    SS_BROWSER_TESTS=1 python manage.py test \\
        planner.tests.test_comm_devices_browser \\
        --settings=audiopatch.test_settings

Add ``SS_BROWSER_SHOTS=<dir>`` to keep a screenshot of each page.
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.models import Device
from planner.tests.test_comm_devices import PLAIN_STATIC, CommFixture

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ENABLED = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

NAME = '<img src=x onerror="window.__xss = 1">'


@unittest.skipUnless(ENABLED, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES=PLAIN_STATIC)
class CommDeviceBrowserTests(CommFixture, StaticLiveServerTestCase):

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

    def open(self, path, user=None, viewport=(1440, 900)):
        self.login(user or self.owner)
        context = self.browser.new_context(
            viewport={'width': viewport[0], 'height': viewport[1]})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + path)
        page.wait_for_load_state('networkidle')
        return page

    def shot(self, page, name):
        where = os.environ.get('SS_BROWSER_SHOTS')
        if where:
            page.screenshot(path=os.path.join(where, f'comm_device_{name}.png'), full_page=True)

    def box(self, page, label):
        return page.locator(f'#comm-patch input[aria-label="{label}"]')

    def save(self, page):
        page.click('input[name="_continue"]')
        page.wait_for_load_state('networkidle')

    def test_add_a_comm_device_from_the_list_and_patch_it(self):
        page = self.open(reverse('admin:planner_device_changelist'))
        self.assertEqual([t.strip() for t in
                          page.locator('.object-tools a.addlink').all_text_contents()],
                         ['Add I/O device', 'Add comm device'])
        self.shot(page, 'list')
        page.click('#add-comm-device')
        page.wait_for_load_state('networkidle')
        page.fill('#id_name', 'Arcadia B')
        page.fill('#id_input_count', '2')
        page.fill('#id_output_count', '2')
        page.fill('#id_four_wire_count', '1')
        page.fill('#id_two_wire_count', '1')
        page.fill('#id_dante_network', 'Comms 48k')
        page.click('input[name="_save"]')
        page.wait_for_load_state('networkidle')
        device = Device.objects.get(name='Arcadia B')
        self.assertTrue(page.url.endswith(self.url(device)))
        self.assertEqual(page.locator('#comm-patch td.port').all_inner_texts(),
                         ['Dante In 1', 'Dante In 2', 'Dante Out 1', 'Dante Out 2', '4W 1', '2W 1'])

        # Each box offers its own list, this network's devices first.
        options = page.evaluate(
            "id => [...document.getElementById(id).options].map(o => o.value)", 'comm-list-dout')
        self.assertEqual(options[:5], ['Arcadia Dante In 1', 'Arcadia Dante In 2',
                                       'Arcadia Dante In 3', 'Arcadia Dante In 4',
                                       'DVS FOH Out 1'])
        self.assertLess(options.index('MK88 Out 8'), options.index('Rio SL Out 1 [Main 96k]'))
        self.assertEqual(self.box(page, 'Dante Out 1').get_attribute('list'), 'comm-list-dout')
        self.assertEqual(self.box(page, '4W 1 receive').get_attribute('list'), 'comm-list-recv')

        self.box(page, 'Dante In 1').fill('MK88 In 3')
        self.box(page, 'Dante Out 1').fill('MK88 Out 3')
        self.box(page, '4W 1 send').fill('Rio SL In 3')
        self.box(page, '4W 1 receive').fill('Rio SL Out 5')
        self.box(page, '2W 1 destination').fill('Wired BP chain SL')
        self.assertEqual(self.box(page, '4W 1 cable type').input_value(), '4W adapter')
        self.save(page)
        self.shot(page, 'patched')
        self.assertEqual(self.box(page, 'Dante Out 1').input_value(), 'MK88 Out 3')
        self.assertEqual(self.box(page, '2W 1 destination').input_value(), 'Wired BP chain SL')
        self.assertEqual(len(self.links()), 4)
        self.assertEqual(page.locator('.comm-error').count(), 0)
        self.assertEqual(self.errors, [])

    def test_another_network_warns_while_typing_and_after_saving(self):
        page = self.open(self.url())
        box = self.box(page, 'Dante Out 1')
        live = box.locator('xpath=..').locator('.comm-live-warning')
        self.assertFalse(live.is_visible())
        box.fill('Rio SL Out 2 [Main 96k]')
        self.assertTrue(live.is_visible())
        self.assertIn('Dante network “Main 96k”', live.inner_text())
        box.fill('MK88 Out 2')
        self.assertFalse(live.is_visible())
        box.fill('Rio SL Out 2 [Main 96k]')
        self.save(page)
        self.shot(page, 'other_network')
        stored = page.locator('#comm-patch .comm-warning:not(.comm-live-warning)')
        self.assertEqual(stored.count(), 1)
        self.assertTrue(stored.first.is_visible())
        self.assertIn('Rio SL is on Dante network “Main 96k”', stored.first.inner_text())
        self.assertTrue(page.locator('.messagelist .warning').first.is_visible())
        self.assertEqual(self.errors, [])

    def test_text_that_is_no_entry_is_marked_and_kept(self):
        page = self.open(self.url())
        self.box(page, 'Dante Out 2').fill('the truck')
        self.save(page)
        error = page.locator('#comm-patch .comm-error')
        self.assertEqual(error.all_inner_texts(), ['Pick an entry from the list, or leave it blank.'])
        self.assertEqual(self.box(page, 'Dante Out 2').input_value(), 'the truck')
        self.assertEqual(self.links(), [])

    def test_the_other_device_links_back_and_a_viewer_reads_only(self):
        self.post(dout2='MK88 Out 3')
        page = self.open(self.url(self.mk88))
        note = page.locator('.ss-comm-note a')
        self.assertEqual(note.all_inner_texts(), ['← Arcadia Dante Out 2'])
        self.assertTrue(note.first.is_visible())
        self.shot(page, 'other_device')
        note.first.click()
        page.wait_for_load_state('networkidle')
        self.assertTrue(page.url.endswith(self.url() + '#comm-patch'))
        self.assertEqual(self.errors, [])

        page = self.open(self.url(), user=self.viewer(), viewport=(820, 1180))
        self.shot(page, 'viewer_tablet')
        boxes = page.locator('#comm-patch input[type="text"]')
        self.assertGreater(boxes.count(), 8)
        self.assertTrue(all(boxes.nth(i).is_disabled() for i in range(boxes.count())))
        self.assertEqual(self.box(page, 'Dante Out 2').input_value(), 'MK88 Out 3')
        # nothing runs off the side of a tablet
        self.assertLessEqual(page.evaluate(
            "document.getElementById('comm-patch').getBoundingClientRect().right"), 820)
        self.assertEqual(self.errors, [])

    def test_names_with_markup_run_nothing(self):
        Device.objects.filter(pk=self.mk88.pk).update(name=NAME)
        self.post(dout1=f'{NAME} Out 1', **{'2w1_dest': NAME})
        Device.objects.filter(pk=self.rio.pk).update(dante_network='</script><svg onload=1>')
        for path in (self.url(), self.url(self.mk88), reverse('planner:wiring_diagram')):
            page = self.open(path)
            self.assertIsNone(page.evaluate('window.__xss || null'), path)
            self.assertEqual(page.locator('img[src="x"]').count(), 0, path)
            self.assertEqual(self.errors, [], path)
        page = self.open(self.url())
        self.assertEqual(self.box(page, 'Dante Out 1').input_value(), f'{NAME} Out 1')
        self.assertEqual(self.box(page, '2W 1 destination').input_value(), NAME)

    def test_the_comms_tab_draws_the_patch_left_to_right(self):
        Device.objects.filter(pk=self.rio.pk).update(console_connection='dante')
        self.post(din1='MK88 In 3', dout1='MK88 Out 3', dout2='DVS FOH Out 1',
                  **{'4w1_send': 'Rio SL In 3', '4w1_recv': 'Rio SL Out 5',
                     '2w1_dest': 'Wired BP chain SL', '2w1_cable': 'XLR3'})
        page = self.open(reverse('planner:wiring_diagram') + '?view=comms')
        self.shot(page, 'comms_tab')
        self.assertEqual(page.locator('.wd-tabs a[aria-current="page"]').inner_text(), 'Comms')
        self.assertEqual(page.locator('svg.wd-svg text.wd-col').all_text_contents(),
                         ['To comms', 'Comm devices', 'From comms'])
        self.assertEqual(page.locator('svg.wd-svg .wd-link').count(), 6)
        # Every row's text stays inside its own box, and the 4W row has a
        # line on each side at one height.
        outside = page.evaluate("""() => [...document.querySelectorAll('svg.wd-svg .wd-box')].flatMap(g => {
            const box = g.querySelector('rect').getBoundingClientRect();
            return [...g.querySelectorAll('text')].filter(t => {
                if (!t.textContent.trim()) return false;        // a blank second line
                const r = t.getBoundingClientRect();
                return r.left < box.left - 1 || r.right > box.right + 1
                    || r.top < box.top - 1 || r.bottom > box.bottom + 1;
            }).map(t => [t.textContent, t.getBoundingClientRect().toJSON(), box.toJSON()]);
        })""")
        self.assertEqual(outside, [])
        ends = page.evaluate("""() => [...document.querySelectorAll('svg.wd-svg .wd-link')].map(g => {
            const d = g.querySelector('path.wd-edge').getAttribute('d').match(/-?[\\d.]+/g).map(Number);
            return [d[0], d[1], d[d.length - 2], d[d.length - 1]];
        })""")
        for x0, _, x1, _ in ends:
            self.assertLess(x0, x1)
        row = page.locator('svg.wd-svg text[data-slot="4W 1"]')
        self.assertEqual(row.count(), 1)
        self.assertEqual(self.errors, [])

        Device.objects.filter(pk=self.rio.pk).update(dante_network='')
        page = self.open(reverse('planner:wiring_diagram') + '?view=dante')
        self.shot(page, 'dante_networks')
        self.assertEqual(sorted(set(page.locator('svg.wd-svg text.wd-group').all_text_contents())),
                         ['Comms 48k', 'No network set'])
        self.assertEqual(self.errors, [])
