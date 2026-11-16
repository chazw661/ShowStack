"""Mic Tracker Overview layout: cards that fill the row, Presenter and Notes
sharing the width, and the day header's ◀ Session N of M ▶ buttons.

The browser tests are skipped unless SS_BROWSER_TESTS=1 (see test_xss_browser).
"""
import os
import unittest
from datetime import date

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, override_settings
from django.urls import reverse

from planner.models import MicSession, Project, ShowDay, UserProfile

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

BROWSER = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None


def make_show(sessions_per_day):
    """An owner and a project with one day per entry in ``sessions_per_day``."""
    owner = User.objects.create_user('layout_owner', password='pw', is_staff=True)
    UserProfile.objects.update_or_create(user=owner, defaults={'account_type': 'paid'})
    project = Project.objects.create(name='Layout show', owner=owner)
    days = []
    for n, count in enumerate(sessions_per_day):
        day = ShowDay.objects.create(project=project, date=date(2026, 3, 1 + n))
        for i in range(count):
            MicSession.objects.create(day=day, name='Session {}'.format(i + 1), num_mics=2, order=i)
        days.append(day)
    return owner, project, days


class SessionNavMarkupTests(TestCase):

    def test_nav_only_on_days_with_more_than_one_session(self):
        owner, project, (busy, quiet) = make_show([3, 1])
        self.client.force_login(owner)
        s = self.client.session
        s['current_project_id'] = project.pk
        s.save()
        html = self.client.get(reverse('planner:mic_tracker_overview')).content.decode()
        self.assertIn('<div class="mto-session-grid" id="mto-grid-{}">'.format(busy.pk), html)
        self.assertIn('<nav class="mto-sess-nav" data-grid="mto-grid-{}"'.format(busy.pk), html)
        self.assertNotIn('data-grid="mto-grid-{}"'.format(quiet.pk), html)
        self.assertEqual(1, html.count('class="mto-sess-nav"'))


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class OverviewLayoutBrowserTests(StaticLiveServerTestCase):

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
        owner, project, _ = make_show([3])
        self.client.force_login(owner)
        s = self.client.session
        s['current_project_id'] = project.pk
        s.save()

    def open(self, width, height):
        context = self.browser.new_context(viewport={'width': width, 'height': height})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.live_server_url + reverse('planner:mic_tracker_overview'))
        page.wait_for_load_state('networkidle')
        return page

    def wait_until_still(self, page):
        """Until the row's smooth scroll has stopped (same position 200ms apart)."""
        page.evaluate("""() => new Promise(done => {
            const g = document.querySelector('.mto-session-grid');
            let last = -1;
            const tick = () => { if (g.scrollLeft === last) return done(); last = g.scrollLeft; setTimeout(tick, 200); };
            tick(); })""")

    def layout(self, page):
        return page.evaluate("""() => {
            const g = document.querySelector('.mto-session-grid'), s = g.querySelector('.mto-session');
            const w = sel => s.querySelector(sel).getBoundingClientRect().width;
            const cs = getComputedStyle(g);
            return {card: s.getBoundingClientRect().width,
                    row: g.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
                    pres: w('.mto-th-pres'), notes: w('.mto-th-notes'), type: w('.mto-th-type'),
                    pageOverflow: document.documentElement.scrollWidth - innerWidth,
                    pos: document.querySelector('.mto-sess-pos').textContent}; }""")

    def test_card_fills_the_row_and_presenter_gets_more_than_notes(self):
        for width, height in ((820, 1180), (1180, 820), (1440, 900)):
            with self.subTest(width=width):
                m = self.layout(self.open(width, height))
                self.assertAlmostEqual(m['row'], m['card'], delta=1)
                self.assertEqual(0, m['pageOverflow'])
                self.assertEqual(108, round(m['type']))                  # fixed columns stay fixed
                self.assertGreaterEqual(m['notes'], 105)
                self.assertAlmostEqual(1.5, m['pres'] / m['notes'], delta=0.05)

    def test_two_sessions_side_by_side_where_both_fit(self):
        m = self.layout(self.open(1920, 1080))
        self.assertAlmostEqual((m['row'] - 18) / 2, m['card'], delta=1)
        self.assertGreaterEqual(m['card'], 700)
        self.assertEqual('Sessions 1–2 of 3', m['pos'])

    def test_session_buttons_step_through_the_row(self):
        page = self.open(820, 1180)
        prev, nxt = page.locator('.mto-sess-prev'), page.locator('.mto-sess-next')
        self.assertTrue(prev.is_disabled())
        self.assertEqual('Session 1 of 3', page.text_content('.mto-sess-pos'))
        for expected in ('Session 2 of 3', 'Session 3 of 3'):
            nxt.click()
            page.wait_for_function('(t) => document.querySelector(".mto-sess-pos").textContent === t', arg=expected)
        self.assertTrue(nxt.is_disabled())
        self.assertGreaterEqual(nxt.bounding_box()['height'], 44)
        prev.click()
        page.wait_for_function('() => document.querySelector(".mto-sess-pos").textContent === "Session 2 of 3"')
        # A loose scroll comes to rest on a whole session.
        self.wait_until_still(page)
        page.evaluate("(g => g.scrollBy({left: 200}))(document.querySelector('.mto-session-grid'))")
        self.wait_until_still(page)
        offset = page.evaluate("""() => { const g = document.querySelector('.mto-session-grid');
            const pad = parseFloat(getComputedStyle(g).paddingLeft);
            return Math.min(...[...g.querySelectorAll('.mto-session')]
                .map(c => Math.abs(c.offsetLeft - pad - g.scrollLeft))); }""")
        self.assertLess(offset, 2)
