"""The sidebar's folding groups, in a real browser.

The groups are paired by model name (``data-sidebar-parent`` + the row's
``model-<name>`` class), so this drives them with the labels deliberately
changed first: a group that still folds after its links are reworded is not
matching on link text.

Skipped unless asked for (needs Playwright and Chromium)::

    SS_BROWSER_TESTS=1 python manage.py test planner.tests.test_sidebar_browser \\
        --settings=audiopatch.test_settings

Add ``SS_BROWSER_SHOTS=<dir>`` to keep a screenshot of each role's sidebar.
"""
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.tests.test_console_b_patch import PLAIN_STATIC
from planner.tests.test_sidebar import SidebarFixture

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ENABLED = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None
SHOTS = os.environ.get('SS_BROWSER_SHOTS')

# Each parent row that has an arrow: its children and whether they show.
STATE = """() => Object.fromEntries(
    [...document.querySelectorAll('#nav-sidebar .menu-toggle-arrow')].map(arrow => {
        const row = arrow.closest('tr');
        const name = [...row.classList].find(c => c.startsWith('model-')).slice(6);
        const kids = [...document.querySelectorAll(
            `#nav-sidebar tr[data-sidebar-parent="${name}"]`)];
        return [name, kids.map(k => [
            [...k.classList].find(c => c.startsWith('model-')).slice(6),
            k.getBoundingClientRect().height > 0])];
    }))"""

# Reword every sidebar link before the page's own scripts run.
REWORD = """document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#nav-sidebar th a').forEach((a, i) => { a.textContent = 'Row ' + i; });
}, true);"""


@unittest.skipUnless(ENABLED, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES=PLAIN_STATIC)
class SidebarGroupsBrowserTests(SidebarFixture, StaticLiveServerTestCase):

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

    def open(self, role, reword=False):
        self.login(self.users[role])
        context = self.browser.new_context(viewport={'width': 1440, 'height': 1100})
        context.add_cookies([{'name': 'sessionid',
                              'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        if reword:
            context.add_init_script(REWORD)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + reverse('admin:planner_console_changelist'))
        page.wait_for_load_state('networkidle')
        return page

    def shot(self, page, name):
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            page.locator('#nav-sidebar').screenshot(path=os.path.join(SHOTS, name + '.png'))

    def test_groups_fold_open_and_stay_open(self):
        page = self.open('editor')
        closed = {'soundvisionprediction': [['speakerarray', False], ['speakercabinet', False]],
                  'powerdistributionplan': [['amplifierassignment', False]]}
        self.assertEqual(closed, page.evaluate(STATE))
        self.shot(page, 'editor-closed')

        page.click('#nav-sidebar tr.model-powerdistributionplan .menu-toggle-arrow')
        opened = dict(closed, powerdistributionplan=[['amplifierassignment', True]])
        self.assertEqual(opened, page.evaluate(STATE))
        self.shot(page, 'editor-open')

        page.reload()
        page.wait_for_load_state('networkidle')
        self.assertEqual(opened, page.evaluate(STATE))

        page.click('#nav-sidebar tr.model-powerdistributionplan .menu-toggle-arrow')
        self.assertEqual(closed, page.evaluate(STATE))
        self.assertEqual([], self.errors)

    def test_groups_do_not_depend_on_the_link_text(self):
        page = self.open('editor', reword=True)
        self.assertEqual('row 0', page.inner_text('#nav-sidebar th a >> nth=0').strip().lower())
        state = page.evaluate(STATE)
        self.assertEqual({'soundvisionprediction', 'powerdistributionplan'}, set(state))
        page.click('#nav-sidebar tr.model-soundvisionprediction .menu-toggle-arrow')
        self.assertEqual([['speakerarray', True], ['speakercabinet', True]],
                         page.evaluate(STATE)['soundvisionprediction'])
        self.assertEqual([], self.errors)

    def test_an_open_group_saved_under_the_old_label_stays_open(self):
        page = self.open('editor')
        page.evaluate("localStorage.setItem('sidebarState',"
                      " JSON.stringify({'Soundvision Predictions': false}))")
        page.reload()
        page.wait_for_load_state('networkidle')
        self.assertEqual([['speakerarray', True], ['speakercabinet', True]],
                         page.evaluate(STATE)['soundvisionprediction'])

    def test_a_viewer_and_a_superuser(self):
        viewer = self.open('viewer')
        self.assertEqual({}, viewer.evaluate(STATE))
        self.shot(viewer, 'viewer')
        boss = self.open('superuser')
        self.assertEqual({'soundvisionprediction', 'powerdistributionplan'},
                         set(boss.evaluate(STATE)))
        headings = boss.eval_on_selector_all(
            '#nav-sidebar caption', 'els => els.map(e => e.textContent.trim())')
        self.assertEqual(['Project', 'System', 'Comms', 'Mics', 'Show', 'Libraries', 'Admin'],
                         headings)
        self.shot(boss, 'superuser')
        self.assertEqual([], self.errors)
