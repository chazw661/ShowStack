"""Mic Tracker Overview: the per-device Lock.

While locked, Type, Headset, Placement, Presenter and Notes show as the plain
text a viewer sees, so a tap while micing can't open a dropdown; Mic'd stays
live. Both forms are in the page and a class on #mto-root swaps them, set
before the page content is parsed from localStorage, so a locked reload never
paints editable controls. UI only: no server or permission change, and
viewers (already read-only) get no Lock button.

The browser tests are skipped unless SS_BROWSER_TESTS=1 (see test_xss_browser).
"""
import os
import unittest
from datetime import date

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, override_settings
from django.urls import reverse

from planner.models import (MicAssignment, MicSession, Presenter, PresenterSlot, Project, ProjectMember,
                            ShowDay, UserProfile)

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

BROWSER = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

NAME, NOTE = 'Alexandra Montgomery', 'Spare battery in pouch'
CONTROLS = '#mto-root .mto-edit-select, #mto-root .mto-pres-input, #mto-root .mto-notes-input'


def make_show(sessions=1):
    """An owner, a viewer and a day; the first session's RF 1 is filled in, RF 2 is empty."""
    owner = User.objects.create_user('lock_owner', password='pw', is_staff=True)
    viewer = User.objects.create_user('lock_viewer', password='pw', is_staff=True)
    for user in (owner, viewer):
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'paid'})
    project = Project.objects.create(name='Lock show', owner=owner)
    ProjectMember.objects.create(project=project, user=viewer, role='viewer', invited_by=owner)
    day = ShowDay.objects.create(project=project, date=date(2026, 3, 1))
    for i in range(sessions):
        MicSession.objects.create(day=day, name='Session {}'.format(i + 1), num_mics=2, order=i)
    slots = []
    for assignment in day.sessions.order_by('order').first().mic_assignments.order_by('rf_number'):
        slots.append(assignment.presenter_slots.first()
                     or PresenterSlot.objects.create(assignment=assignment, order=0, is_active=True))
    filled = slots[0]
    filled.presenter = Presenter.objects.create(project=project, name=NAME)
    filled.mic_type, filled.headset_color, filled.placement, filled.notes = 'LAV', 'BEIGE', 'TIE', NOTE
    filled.save()
    return owner, viewer, project, slots


class LockMarkupTests(TestCase):

    def setUp(self):
        self.owner, self.viewer, self.project, _ = make_show()

    def overview(self, user):
        self.client.force_login(user)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()
        return self.client.get(reverse('planner:mic_tracker_overview')).content.decode()

    def test_editor_gets_the_button_the_early_script_and_the_plain_text(self):
        html = self.overview(self.owner)
        self.assertIn('id="mto-lock-btn"', html)
        # The class is set by the first thing inside #mto-root, before any row.
        root = html.index('<div id="mto-root"')
        early = html.index("localStorage.getItem('mto-locked')", root)
        self.assertLess(early, html.index('class="mto-session"'))
        for shown in ('<span class="mto-type-badge">LAV</span>', '<span class="mto-dim">Beige</span>',
                      '<span class="mto-dim">Tie</span>', '<span class="mto-presenter">{}</span>'.format(NAME),
                      '<span class="mto-notes-text" tabindex="0">{}</span>'.format(NOTE),
                      '<span class="mto-unassigned">— Unassigned —</span>'):
            self.assertIn('<span class="mto-lock-text">' + shown, html)
        self.assertIn('class="mto-pres-input"', html)        # unlocked by default: controls too
        self.assertNotIn('mto-locked', html[root:html.index('>', root)])

    def test_viewer_gets_no_lock(self):
        html = self.overview(self.viewer)
        self.assertNotIn('id="mto-lock-btn"', html)
        self.assertNotIn("getItem('mto-locked')", html)
        self.assertNotIn('class="mto-lock-text"', html)
        self.assertNotIn('class="mto-pres-input"', html)


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LockBrowserTests(StaticLiveServerTestCase):

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

    def show(self, sessions=1):
        self.owner, self.viewer, self.project, self.slots = make_show(sessions)

    def open(self, user=None, init_script=None, width=820, height=1180):
        """A new browser (its own localStorage) on the Overview, as ``user``."""
        self.client.force_login(user or self.owner)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()
        context = self.browser.new_context(viewport={'width': width, 'height': height}, has_touch=True)
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        if init_script:
            context.add_init_script(init_script)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.on('dialog', lambda d: (self.errors.append('dialog: ' + d.message), d.dismiss()))
        page.goto(self.live_server_url + reverse('planner:mic_tracker_overview'))
        page.wait_for_load_state('networkidle')
        return page

    @staticmethod
    def visible_controls(page):
        return page.evaluate('(sel) => [...document.querySelectorAll(sel)].filter(e => e.offsetParent).length',
                             CONTROLS)

    @staticmethod
    def first_row_text(page):
        return page.evaluate("""() => [...document.querySelector('.mto-row').querySelectorAll('.mto-lock-text')]
                                    .map(e => e.offsetParent ? e.textContent.trim() : null)""")

    def lock(self, page):
        page.click('#mto-lock-btn')
        page.wait_for_function("() => document.getElementById('mto-root').classList.contains('mto-locked')")

    def test_lock_leaves_only_micd_and_micd_still_saves(self):
        self.show()
        page = self.open()
        self.assertEqual(10, self.visible_controls(page))         # 2 rows x 5
        self.assertEqual('🔓 Lock', page.inner_text('#mto-lock-btn'))
        self.lock(page)
        self.assertEqual(0, self.visible_controls(page))
        self.assertEqual(['LAV', 'Beige', 'Tie', NAME, NOTE], self.first_row_text(page))
        self.assertEqual(['—', '—', '—', '— Unassigned —', '—'], page.evaluate(
            "() => [...document.querySelectorAll('.mto-row')[1].querySelectorAll('.mto-lock-text')]"
            ".map(e => e.textContent.trim())"))
        btn = page.locator('#mto-lock-btn')
        self.assertEqual('🔒 Locked — tap to edit', btn.inner_text())
        self.assertEqual('true', btn.get_attribute('aria-pressed'))
        self.assertGreaterEqual(btn.bounding_box()['height'], 44)
        # Filled amber with dark text, and an amber stripe over the header.
        self.assertEqual(['rgb(255, 171, 0)', 'rgb(22, 23, 26)'], btn.evaluate(
            'b => [getComputedStyle(b).backgroundColor, getComputedStyle(b).color]'))
        self.assertIn('rgb(255, 171, 0)', page.evaluate(
            "getComputedStyle(document.querySelector('.mto-header')).boxShadow"))

        micd = page.locator('.mto-micd-btn').first
        self.assertTrue(micd.is_visible())
        with page.expect_response('**/api/mic/update/'):
            micd.click()
        self.assertEqual('ON', micd.inner_text())
        self.assertTrue(MicAssignment.objects.get(pk=self.slots[0].assignment_id).is_micd)
        self.assertEqual([], self.errors)

    def test_lock_survives_a_reload_without_painting_controls(self):
        self.show()
        # Note any control the parser adds while #mto-root is not yet locked.
        watch = """(() => { window.__controls = 0; window.__flash = 0;
            new MutationObserver(records => { for (const r of records) for (const n of r.addedNodes) {
                if (n.nodeType !== 1 || !n.matches('.mto-edit-select, .mto-pres-input, .mto-notes-input')) continue;
                window.__controls++;
                if (!document.getElementById('mto-root').classList.contains('mto-locked')) window.__flash++;
            } }).observe(document, {childList: true, subtree: true}); })()"""
        page = self.open(init_script=watch)
        self.assertEqual(0, page.evaluate('window.__controls - window.__flash'))   # unlocked: every one "flashes"
        self.lock(page)
        page.reload()
        page.wait_for_load_state('networkidle')
        self.assertEqual((10, 0), (page.evaluate('window.__controls'), page.evaluate('window.__flash')))
        self.assertEqual(0, self.visible_controls(page))
        self.assertEqual('true', page.get_attribute('#mto-lock-btn', 'aria-pressed'))
        self.assertEqual(['LAV', 'Beige', 'Tie', NAME, NOTE], self.first_row_text(page))

        page.click('#mto-lock-btn')                                  # unlock, and it stays unlocked
        page.reload()
        page.wait_for_load_state('networkidle')
        self.assertEqual(10, self.visible_controls(page))
        self.assertEqual('false', page.get_attribute('#mto-lock-btn', 'aria-pressed'))
        self.assertEqual([], self.errors)

    def test_viewer_sees_no_button_even_with_a_locked_device(self):
        self.show()
        page = self.open(self.viewer, init_script="localStorage.setItem('mto-locked', '1')")
        self.assertEqual(0, page.locator('#mto-lock-btn').count())
        self.assertFalse(page.evaluate("document.getElementById('mto-root').classList.contains('mto-locked')"))
        self.assertTrue(page.locator('.mto-presenter').first.is_visible())
        self.assertEqual([], self.errors)

    def test_locking_mid_edit_saves_what_was_typed(self):
        self.show()
        page = self.open()
        empty = self.slots[1]
        # Tapping Lock while a name is typed but not committed.
        page.locator('.mto-pres-input').nth(1).fill('Sam Lee')
        with page.expect_response('**/api/mic/slot/update/'):
            self.lock(page)
        page.click('#mto-lock-btn')                                       # unlock to type a note
        # Locking with focus still in the box (no tap to move it): the lock blurs it.
        page.locator('.mto-notes-input').nth(1).fill('Wears glasses')
        with page.expect_response('**/api/mic/slot/update/'):
            page.evaluate('mtoToggleLock()')
        empty.refresh_from_db()
        self.assertEqual(('Sam Lee', 'Wears glasses'), (empty.presenter.name, empty.notes))
        row = page.evaluate("() => [...document.querySelectorAll('.mto-row')[1].querySelectorAll('.mto-lock-text')]"
                            ".map(e => e.textContent.trim())")
        self.assertEqual(['Sam Lee', 'Wears glasses'], row[3:])
        self.assertEqual([], self.errors)

    def test_a_notes_conflict_stays_up_while_locked_and_keeps_both_texts(self):
        self.show()
        page = self.open()
        filled = self.slots[0]
        PresenterSlot.objects.filter(pk=filled.pk).update(notes='Changed by the A1')   # after this page loaded
        page.locator('.mto-notes-input').first.fill('Mine: tape the pack')
        with page.expect_response('**/api/mic/slot/update/'):
            self.lock(page)
        box = page.locator('.mto-notes-conflict')
        box.wait_for()
        self.assertTrue(box.is_visible())                                   # locked, and still up
        self.assertIn('Changed by the A1', box.inner_text())
        self.assertEqual('Mine: tape the pack', self.first_row_text(page)[4])
        filled.refresh_from_db()
        self.assertEqual('Changed by the A1', filled.notes)                  # nothing overwritten yet
        with page.expect_response('**/api/mic/slot/update/'):
            box.locator('.mto-notes-keep-mine').click()
        filled.refresh_from_db()
        self.assertEqual('Mine: tape the pack', filled.notes)
        self.assertEqual(0, page.locator('.mto-notes-conflict').count())
        self.assertEqual('Mine: tape the pack', self.first_row_text(page)[4])
        self.assertEqual(0, self.visible_controls(page))
        self.assertEqual([], self.errors)

    def test_presets_session_nav_and_card_widths_work_locked(self):
        self.show(sessions=3)
        page = self.open()
        layout = """() => { const c = document.querySelector('.mto-session');
            return [Math.round(c.getBoundingClientRect().width), Math.round(parseFloat(getComputedStyle(c).minWidth)),
                    document.querySelector('.mto-sess-pos').textContent]; }"""
        before = page.evaluate(layout)
        self.lock(page)
        self.assertEqual(before, page.evaluate(layout))
        page.click('#mto-cols-btn')
        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('.mto-cols-preset[data-hide="headset notes"]')
        self.assertFalse(page.locator('th.mto-col-headset').first.is_visible())
        self.assertEqual(457, page.evaluate(layout)[1])
        self.assertEqual(['LAV', 'Tie', NAME], [t for t in self.first_row_text(page) if t is not None])
        page.locator('.mto-title').click()
        page.click('.mto-sess-next')
        page.wait_for_function('() => document.querySelector(".mto-sess-pos").textContent.startsWith("Session 2")')
        self.assertEqual(0, self.visible_controls(page))
        self.assertEqual([], self.errors)
