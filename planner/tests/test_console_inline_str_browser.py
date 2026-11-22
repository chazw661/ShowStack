"""The Console page's inline rows still show no object label, in a real
browser.

The rows used to be label-free because the inlines blanked the models'
``__str__`` (test_console_inline_str). The label is now in the markup and
hidden by the ``td.original`` rule in templates/admin/base_site.html, so this
checks what the engineer sees: nothing of it, and rows exactly as tall and as
wide as they are with an empty label -- which is what the page had before.

Skipped unless asked for (needs Playwright and Chromium)::

    SS_BROWSER_TESTS=1 python manage.py test \\
        planner.tests.test_console_inline_str_browser \\
        --settings=audiopatch.test_settings

Add ``SS_BROWSER_SHOTS=<dir>`` to keep a screenshot of each page.
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from planner.tests.test_console_b_patch import PLAIN_STATIC
from planner.tests.test_console_inline_str import ChannelFixture

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ENABLED = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

GROUPS = {
    'consoleinput_set': ['Ch 1 · Kick', 'Ch 2 · Snare', 'Ch 5 · Vox'],
    'consoleauxoutput_set': ['Aux 3 · Drum Wedge'],
    'consolematrixoutput_set': ['Matrix 2 · Delay'],
    'consolestereooutput_set': ['Stereo Left · Main'],
}

# Every saved row of one inline: its label, whether any of it shows, and the
# row's box.
MEASURE = """(group) => [...document.querySelectorAll(`#${group}-group tr.has_original`)].map(tr => {
    const td = tr.querySelector('td.original'), p = td.querySelector('p');
    const box = e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; };
    const first = [...tr.children].find(c => c !== td && c.getBoundingClientRect().width > 0);
    return {
        label: p ? p.textContent.trim().replace(/\\s+/g, ' ') : null,
        tdDisplay: getComputedStyle(td).display,
        tdBox: box(td),
        pBox: p ? box(p) : null,
        rowBox: box(tr),
        rowVisible: tr.getBoundingClientRect().height > 0,
        firstCellLeft: first.getBoundingClientRect().left - tr.getBoundingClientRect().left,
        cells: [...tr.children].map(c => box(c)),
    };
})"""

BLANK = """() => document.querySelectorAll('.inline-group td.original p')
    .forEach(p => { p.textContent = ''; })"""


@unittest.skipUnless(ENABLED, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES=PLAIN_STATIC)
class InlineLabelBrowserTests(ChannelFixture, StaticLiveServerTestCase):

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

    def open_console(self, user, viewport=(1440, 900)):
        self.login(user)
        context = self.browser.new_context(
            viewport={'width': viewport[0], 'height': viewport[1]})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + self.url)
        page.wait_for_load_state('networkidle')
        # The inlines are collapsed by default: open every one.
        page.evaluate("document.querySelectorAll('.inline-group details')"
                      ".forEach(d => { d.open = true; })")
        return page

    def shot(self, page, name):
        where = os.environ.get('SS_BROWSER_SHOTS')
        if where:
            page.screenshot(path=os.path.join(where, f'inline_str_{name}.png'), full_page=True)

    def check(self, page, name):
        before = {group: page.evaluate(MEASURE, group) for group in GROUPS}
        self.shot(page, name)
        for group, labels in GROUPS.items():
            rows = before[group]
            # The label is there (not blanked at the source) ...
            self.assertEqual([r['label'] for r in rows], labels, group)
            for r in rows:
                self.assertTrue(r['rowVisible'], group)
                # ... and none of it is drawn.
                self.assertEqual(r['tdDisplay'], 'none', group)
                self.assertEqual(r['tdBox'], [0, 0], group)
                self.assertEqual(r['pBox'], [0, 0], group)
                # The first drawn cell starts at the row's edge: no gap left.
                self.assertLess(abs(r['firstCellLeft']), 1.5, group)
        # With the label emptied -- how the page was before -- nothing moves.
        page.evaluate(BLANK)
        for group in GROUPS:
            after = page.evaluate(MEASURE, group)
            for was, now in zip(before[group], after):
                self.assertEqual(now['label'], '')
                self.assertEqual(now['rowBox'], was['rowBox'], group)
                self.assertEqual(now['cells'], was['cells'], group)
        self.assertEqual(self.errors, [])

    def test_owner_sees_no_label_on_any_of_the_four_grids(self):
        self.check(self.open_console(self.owner), 'owner')

    def test_viewer_sees_no_label_either(self):
        self.check(self.open_console(self.viewer()), 'viewer')

    def test_tablet_width(self):
        self.check(self.open_console(self.owner, viewport=(1024, 768)), 'tablet')

    def test_the_label_text_is_nowhere_in_what_the_page_shows(self):
        page = self.open_console(self.owner)
        shown = page.evaluate("document.querySelector('#content').innerText")
        for labels in GROUPS.values():
            for label in labels:
                self.assertNotIn(label, shown)
