"""Mic Tracker Overview: per-user column choices.

Type, Headset, Placement and Notes can be hidden per
user; RF, Presenter and Mic'd always show. The choice lives in
UserProfile.ui_prefs, so it follows the user between devices, and the server
renders it as classes on #mto-root so hidden columns never flash on load.

The save endpoint never creates a UserProfile -- having one changes admin
access and the sidebar -- so a user without one gets an error and every
column.

The browser test at the bottom is skipped unless SS_BROWSER_TESTS=1 (see
test_xss_browser).
"""
import json
import os
import re
import unittest
from datetime import date

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, override_settings
from django.urls import reverse

from planner.models import MicSession, Project, ProjectMember, ShowDay, UserProfile

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

BROWSER = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

ALL = ('type', 'headset', 'placement', 'notes')


def make_show(name='Prefs show', sessions=1):
    owner = User.objects.create_user(name.lower().replace(' ', '_') + '_owner', password='pw', is_staff=True)
    UserProfile.objects.update_or_create(user=owner, defaults={'account_type': 'paid'})
    project = Project.objects.create(name=name, owner=owner)
    day = ShowDay.objects.create(project=project, date=date(2026, 3, 1))
    for i in range(sessions):
        MicSession.objects.create(day=day, name='Session {}'.format(i + 1), num_mics=1, order=i)
    return owner, project


class ColumnPrefsTests(TestCase):

    def setUp(self):
        self.owner, self.project = make_show()
        self.viewer = User.objects.create_user('prefs_viewer', password='pw', is_staff=True)
        UserProfile.objects.update_or_create(user=self.viewer, defaults={'account_type': 'paid'})
        ProjectMember.objects.create(project=self.project, user=self.viewer, role='viewer',
                                     invited_by=self.owner)
        self.login(self.owner)

    def login(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()

    def save(self, hidden):
        return self.client.post(reverse('planner:save_mic_overview_prefs'),
                                json.dumps({'hidden': hidden}), content_type='application/json')

    def overview(self):
        resp = self.client.get(reverse('planner:mic_tracker_overview'))
        self.assertEqual(200, resp.status_code)
        return resp.content.decode()

    def hidden_on_page(self, html):
        root = re.search(r'<div id="mto-root" class="([^"]*)">', html)
        self.assertIsNotNone(root, '#mto-root not rendered')
        return sorted(c[len('mto-hide-'):] for c in root.group(1).split() if c.startswith('mto-hide-'))

    def badge_hidden(self, html):
        tag = re.search(r'<button type="button" id="mto-hidden-badge"[^>]*>', html, re.S).group(0)
        return bool(re.search(r'\shidden(\s|>)', tag))

    def pressed_preset(self, html):
        names = re.findall(r'aria-pressed="true"[^>]*>\s*<span class="mto-cols-preset-name">([^<]+)<', html)
        return names[0] if len(names) == 1 else names or None

    def test_presets_render_with_the_matching_one_pressed(self):
        html = self.overview()
        self.assertIn('data-hide="headset notes"', html)                 # A1 setup
        self.assertIn('data-hide=""', html)                              # A2 entry
        self.save(['notes', 'headset'])
        self.assertEqual('A1 setup', self.pressed_preset(self.overview()))
        self.save(['type'])
        self.assertIsNone(self.pressed_preset(self.overview()))          # a custom set

    def prefs(self, user):
        return UserProfile.objects.get(user=user).ui_prefs

    # -- defaults ------------------------------------------------------------

    def test_default_is_every_column(self):
        html = self.overview()
        self.assertEqual([], self.hidden_on_page(html))
        self.assertTrue(self.badge_hidden(html))
        for col in ALL:
            self.assertIn('mto-col-{}'.format(col), html)
        self.assertEqual('A2 entry', self.pressed_preset(html))

    # -- save and load -------------------------------------------------------

    def test_saved_choice_renders_on_load(self):
        resp = self.save(['type', 'notes'])
        self.assertEqual({'success': True, 'hidden': ['type', 'notes']}, resp.json())
        self.assertEqual({'mic_overview': {'hidden': ['type', 'notes']}}, self.prefs(self.owner))
        html = self.overview()
        self.assertEqual(['notes', 'type'], self.hidden_on_page(html))
        self.assertFalse(self.badge_hidden(html))
        self.assertIn('<span id="mto-hidden-count">2</span> hidden · Show all', html)
        self.assertRegex(html, r'data-col="type"\s+onchange')       # unchecked
        self.assertRegex(html, r'data-col="headset" checked\s+onchange')

    def test_show_all_is_an_empty_list(self):
        self.save(list(ALL))
        self.assertEqual(sorted(ALL), self.hidden_on_page(self.overview()))
        self.assertTrue(self.save([]).json()['success'])
        html = self.overview()
        self.assertEqual([], self.hidden_on_page(html))
        self.assertTrue(self.badge_hidden(html))

    def test_locked_and_unknown_columns_are_dropped(self):
        resp = self.save(['rf', 'presenter', 'micd', 'bogus', 'notes', 'type', 'type', 7, [1], {'a': 1}])
        self.assertEqual(['type', 'notes'], resp.json()['hidden'])
        self.assertEqual(['notes', 'type'], self.hidden_on_page(self.overview()))

    def test_other_prefs_on_the_profile_are_kept(self):
        profile = UserProfile.objects.get(user=self.owner)
        profile.ui_prefs = {'something_else': {'x': 1}}
        profile.save()
        self.save(['notes'])
        self.assertEqual({'something_else': {'x': 1}, 'mic_overview': {'hidden': ['notes']}},
                         self.prefs(self.owner))

    def test_malformed_body_is_refused(self):
        url = reverse('planner:save_mic_overview_prefs')
        for body in ('not json', json.dumps({'hidden': 'type'}), json.dumps(['type'])):
            with self.subTest(body=body):
                resp = self.client.post(url, body, content_type='application/json')
                self.assertEqual(400, resp.status_code)
        self.assertEqual({}, self.prefs(self.owner))

    def test_corrupt_stored_prefs_fall_back_to_every_column(self):
        UserProfile.objects.filter(user=self.owner).update(ui_prefs={'mic_overview': {'hidden': 'type'}})
        self.assertEqual([], self.hidden_on_page(self.overview()))

    # -- per user ------------------------------------------------------------

    def test_choices_are_per_user(self):
        self.save(['type'])
        self.login(self.viewer)
        self.assertEqual([], self.hidden_on_page(self.overview()))
        self.assertTrue(self.save(['notes']).json()['success'])     # viewers set their own
        self.assertEqual(['notes'], self.hidden_on_page(self.overview()))
        self.login(self.owner)
        self.assertEqual(['type'], self.hidden_on_page(self.overview()))

    def test_choices_follow_the_user_to_another_project(self):
        self.save(['placement'])
        other = Project.objects.create(name='Second show', owner=self.owner)
        ShowDay.objects.create(project=other, date=date(2026, 4, 1))
        s = self.client.session
        s['current_project_id'] = other.pk
        s.save()
        self.assertEqual(['placement'], self.hidden_on_page(self.overview()))

    def test_signed_out_is_refused(self):
        self.client.logout()
        # The login middleware redirects first; either way nothing is saved.
        self.assertIn(self.save(['type']).status_code, (302, 403))
        self.assertEqual({}, self.prefs(self.owner))

    # -- no profile ----------------------------------------------------------

    def test_no_profile_is_not_created_and_shows_every_column(self):
        # A superuser can reach the Overview without a profile. Delete it
        # after signing in: a login saves the user, and a signal on that save
        # creates a missing profile.
        su = User.objects.create_superuser('prefs_su', 'su@example.com', 'pw')
        self.project.owner = su
        self.project.save()
        self.login(su)
        UserProfile.objects.filter(user=su).delete()

        resp = self.save(['type'])
        self.assertEqual(409, resp.status_code)
        self.assertIs(False, resp.json()['success'])
        self.assertFalse(UserProfile.objects.filter(user=su).exists())

        html = self.overview()
        self.assertEqual([], self.hidden_on_page(html))
        self.assertTrue(self.badge_hidden(html))
        self.assertFalse(UserProfile.objects.filter(user=su).exists())


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ColumnPrefsBrowserTests(StaticLiveServerTestCase):

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

    def test_presets_columns_cards_per_row_and_show_all(self):
        owner, project = make_show('Browser prefs', sessions=3)
        self.client.force_login(owner)
        s = self.client.session
        s['current_project_id'] = project.pk
        s.save()
        context = self.browser.new_context(viewport={'width': 1180, 'height': 820})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        url = self.live_server_url + reverse('planner:mic_tracker_overview')
        page.goto(url)
        visible = lambda sel: page.locator(sel).first.is_visible()
        pressed = lambda: page.evaluate("""() => [...document.querySelectorAll('.mto-cols-preset[aria-pressed="true"]')]
                                            .map(b => b.querySelector('.mto-cols-preset-name').textContent)""")
        m = lambda: page.evaluate("""() => { const g = document.querySelector('.mto-session-grid'),
                c = g.querySelector('.mto-session'), cs = getComputedStyle(g);
            return {min: Math.round(parseFloat(getComputedStyle(c).minWidth)),
                    card: c.getBoundingClientRect().width,
                    row: g.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
                    pres: c.querySelector('.mto-th-pres').getBoundingClientRect().width,
                    pos: document.querySelector('.mto-sess-pos').textContent}; }""")

        start = m()
        self.assertEqual((652, 'Session 1 of 3'), (start['min'], start['pos']))
        self.assertEqual(['A2 entry'], pressed())
        self.assertFalse(visible('#mto-hidden-badge'))

        # One column off: still one card per row of three, so the row
        # scrolls and the card keeps filling it; Notes' width goes to Presenter.
        page.click('#mto-cols-btn')
        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.locator('input[data-col="notes"]').uncheck()
        after = m()
        self.assertFalse(visible('th.mto-col-notes'))
        self.assertEqual(547, after['min'])
        self.assertAlmostEqual(start['card'], after['card'], delta=1)
        self.assertGreater(after['pres'], start['pres'] + 100)
        self.assertEqual('1', page.text_content('#mto-hidden-count'))
        self.assertEqual([], pressed())

        # A1 setup: Headset and Notes off, cards narrow and two fit.
        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('.mto-cols-preset[data-hide="headset notes"]')
        a1 = m()
        self.assertEqual(457, a1['min'])
        self.assertAlmostEqual((a1['row'] - 18) / 2, a1['card'], delta=1)
        self.assertEqual('Sessions 1–2 of 3', a1['pos'])
        self.assertEqual(['A1 setup'], pressed())
        for col, shown in (('type', True), ('headset', False), ('placement', True), ('notes', False)):
            self.assertEqual(shown, visible('th.mto-col-' + col), col)
        for always in ('th.mto-th-rf', 'th.mto-th-pres', 'th.mto-th-micd'):
            self.assertTrue(visible(always), always)
        self.assertEqual('2', page.text_content('#mto-hidden-count'))

        page.goto(url)                                                # follows the user
        self.assertEqual((457, 'Sessions 1–2 of 3'), (m()['min'], m()['pos']))
        self.assertEqual(['A1 setup'], pressed())
        self.assertTrue(visible('#mto-hidden-badge'))

        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('#mto-hidden-badge')                           # Show all, one tap
        self.assertFalse(visible('#mto-hidden-badge'))
        for col in ALL:
            self.assertTrue(visible('th.mto-col-' + col), col)
        self.assertEqual((652, 'Session 1 of 3'), (m()['min'], m()['pos']))
        self.assertEqual(['A2 entry'], pressed())
        self.assertEqual({'mic_overview': {'hidden': []}}, UserProfile.objects.get(user=owner).ui_prefs)

    def open(self, owner, project, width, height=900):
        self.client.force_login(owner)
        s = self.client.session
        s['current_project_id'] = project.pk
        s.save()
        context = self.browser.new_context(viewport={'width': width, 'height': height})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.live_server_url + reverse('planner:mic_tracker_overview'))
        return page

    @staticmethod
    def across(page):
        """How many session cards of the first day are wholly on screen."""
        return page.evaluate("""() => { const g = document.querySelector('.mto-session-grid'),
                box = g.getBoundingClientRect();
            return [...g.querySelectorAll('.mto-session')].filter(c => {
                const r = c.getBoundingClientRect();
                return r.left >= box.left - 1 && r.right <= box.right + 1; }).length; }""")

    def test_a1_setup_shows_more_sessions_across_at_1440(self):
        owner, project = make_show('Laptop prefs', sessions=4)
        page = self.open(owner, project, 1440)
        a2 = self.across(page)
        page.click('#mto-cols-btn')
        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('.mto-cols-preset[data-hide="headset notes"]')
        a1 = self.across(page)
        self.assertEqual((1, 2), (a2, a1))
        self.assertGreater(a1, a2)

    def test_session_nav_hidden_while_every_session_fits(self):
        owner, project = make_show('Nav prefs', sessions=2)
        nav = lambda page: page.locator('.mto-sess-nav').is_visible()
        # A2 entry at 1180: one card across, so the nav shows ...
        page = self.open(owner, project, 1180, 820)
        self.assertEqual(1, self.across(page))
        self.assertTrue(nav(page))
        # ... A1 setup fits both, so it goes; back to A2 entry, it returns.
        page.click('#mto-cols-btn')
        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('.mto-cols-preset[data-hide="headset notes"]')
        self.assertEqual(2, self.across(page))
        self.assertFalse(nav(page))
        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('.mto-cols-preset[data-hide=""]')
        self.assertTrue(nav(page))
        # A wide screen fits both with every column: no nav from the first paint.
        wide = self.open(owner, project, 1920, 1080)
        self.assertEqual(2, self.across(wide))
        self.assertTrue(wide.locator('.mto-sess-nav').is_hidden())

    def test_failed_save_is_one_quiet_note(self):
        su = User.objects.create_superuser('prefs_browser_su', 'su@example.com', 'pw')
        owner, project = make_show('Quiet prefs', sessions=1)
        project.owner = su
        project.save()
        page = self.open(su, project, 1180, 820)
        UserProfile.objects.filter(user=su).delete()                 # no profile: saves refused
        dialogs = []
        page.on('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))
        page.click('#mto-cols-btn')
        note = page.locator('.mto-cols-error')
        self.assertFalse(note.is_visible())
        for col in ('notes', 'headset'):
            with page.expect_response('**/api/ui-prefs/mic-overview/') as r:
                page.locator('input[data-col="{}"]'.format(col)).uncheck()
            self.assertEqual(409, r.value.status)
            page.wait_for_function("() => !document.getElementById('mto-cols-error').hidden")
        self.assertEqual(1, note.count())
        self.assertTrue(note.is_visible())
        self.assertIn("won't be remembered", note.text_content())
        self.assertEqual([], dialogs)
        self.assertFalse(page.locator('th.mto-col-notes').is_visible())   # the page still follows the choice
        self.assertFalse(UserProfile.objects.filter(user=su).exists())
