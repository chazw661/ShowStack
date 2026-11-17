"""The walkthrough in a browser (mic_plan_walkthrough.js): Enter confirms the
line and moves the cursor before the server answers, the answer is kept,
a line that changed under the user is redrawn and pointed to, and locked
lines are never confirmed by Enter.

Skipped unless asked for (Playwright and its browsers)::

    SS_BROWSER_TESTS=1 python manage.py test planner.tests.test_mic_planner_walkthrough_browser \\
        --settings=audiopatch.test_settings
"""

import os
import unittest
from datetime import date

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.mic_plan import importer, walkthrough
from planner.models import MicPlannerRowCheck, Project, ShowDay, ShowflowImport
from planner.tests import showflow_fixture as F
from planner.tests.test_console_patch_picker import staff

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
class WalkthroughBrowserTests(StaticLiveServerTestCase):

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
        self.owner = staff('walk_owner')
        self.project = Project.objects.create(name='Walk Show', owner=self.owner)
        self.day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 1))
        importer.confirm(importer.stage_upload(self.day, F.build_pdf(F.MAIN_PAGES), 'day.pdf', self.owner))
        self.part = ShowflowImport.objects.get(day=self.day)
        self.client.force_login(self.owner)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def open(self, slow=0):
        context = self.browser.new_context()
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        if slow:
            # Hold every walkthrough answer back: what shows before it is the page's own doing.
            page.route('**/walk/**', lambda route: (page.wait_for_timeout(slow), route.continue_()))
        page.goto(self.live_server_url + reverse('planner:mic_plan') + '?day={}#walk'.format(self.day.pk))
        page.wait_for_selector('#mp-walk-list .mp-wp.cursor')
        return page

    def cursor_line(self, page):
        return page.evaluate("document.querySelector('.mp-wp.cursor .line').textContent")

    def first_unlocked(self):
        walk = walkthrough.build(self.day)
        open_ = [p for p in walk['panels'] if p['state'] == 'open' and not (p['locks'] or p['person_locks'])]
        return walk, open_

    def go_to(self, page, panel):
        page.click('#wp-{} .mp-wp-head'.format(panel['id']))

    def test_enter_confirms_and_moves_on_before_the_answer_and_the_answer_sticks(self):
        walk, open_ = self.first_unlocked()
        first = open_[0]
        self.assertFalse(first['locks'] or first['person_locks'], first['line'])
        page = self.open(slow=1500)
        self.go_to(page, first)
        self.assertEqual(first['line'], self.cursor_line(page))
        page.keyboard.press('Enter')
        page.wait_for_timeout(100)                                 # far less than the held-back answer
        self.assertEqual('true', page.evaluate(
            "String(document.getElementById('wp-{}').classList.contains('s-confirmed'))".format(first['id'])))
        self.assertNotEqual(first['line'], self.cursor_line(page))
        page.wait_for_timeout(2500)
        self.assertTrue(MicPlannerRowCheck.objects.filter(part=self.part).exists())
        self.assertEqual('confirmed', next(p for p in walkthrough.build(self.day)['panels']
                                           if p['id'] == first['id'])['state'])
        self.assertIn('{} of'.format(walkthrough.progress(walkthrough.build(self.day))['confirmed']),
                      page.text_content('#mp-walk-progress'))
        self.assertEqual([], self.errors)

    def test_a_line_changed_under_the_user_is_redrawn_and_pointed_to(self):
        _, open_ = self.first_unlocked()
        first = open_[0]
        page = self.open()
        # Someone else edits the line after the page loaded.
        from planner.mic_plan import overrides
        row = self.part.rows.get(pk=first['id'])
        name = first['on'][0]['key'] if first['on'] else 'alex host'
        overrides.set_row(self.part, row, {'not_on': [name]}, None)
        self.go_to(page, first)
        page.keyboard.press('Enter')
        page.wait_for_selector('#wp-{}.changed'.format(first['id']))
        self.assertIn('changed', page.text_content('#mp-walk-progress'))
        self.assertFalse(MicPlannerRowCheck.objects.exists())
        self.assertEqual([], self.errors)

    def test_enter_on_a_locked_line_goes_to_its_decision_and_confirms_nothing(self):
        walk = walkthrough.build(self.day)
        locked = next(p for p in walk['panels'] if p['person_locks'] or p['locks'])
        page = self.open()
        page.click('#wp-{} .mp-wp-head'.format(locked['id']))
        page.keyboard.press('Enter')
        page.wait_for_timeout(300)
        focused = page.evaluate("document.activeElement.closest('.mp-wp-plock, .mp-wp-locks') !== null")
        self.assertTrue(focused)
        self.assertFalse(MicPlannerRowCheck.objects.exists())

    def test_arrows_move_without_confirming(self):
        page = self.open()
        start = self.cursor_line(page)
        page.keyboard.press('ArrowDown')
        self.assertNotEqual(start, self.cursor_line(page))
        page.keyboard.press('ArrowUp')
        self.assertEqual(start, self.cursor_line(page))
        self.assertFalse(MicPlannerRowCheck.objects.exists())
