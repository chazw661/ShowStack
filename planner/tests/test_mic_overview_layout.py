"""Mic Tracker Overview layout: as many session cards per row as fit at the
card minimum, every day split alike, cards no wider than the card maximum
and left-aligned, Presenter and Notes sharing the spare width, and the day
header's ◀ Session N of M ▶ buttons.

The browser tests are skipped unless SS_BROWSER_TESTS=1 (see test_xss_browser).
"""
import json
import os
import unittest
from datetime import date

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from planner.models import MicSession, Presenter, PresenterSlot, Project, ShowDay, UserProfile

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

BROWSER = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

CARD_MIN, CARD_MAX = 728, 977           # every column showing
A1_MIN, A1_MAX = 533, 627               # A1 setup: no Headset, no Notes
FIXED = [40, 90, 90, 104, 68]           # RF, Type, Headset, Placement, Mic'd
TYPE_W, PRES_MIN, NOTES_MIN = 90, 226, 105
NAME20 = 'Alexandra Montgomery'


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
        self.owner = owner
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
                    min: parseFloat(getComputedStyle(s).minWidth),
                    pageOverflow: document.documentElement.scrollWidth - innerWidth,
                    pos: document.querySelector('.mto-sess-pos').textContent}; }""")

    def assert_spare_shared(self, m, capped=True):
        """Presenter and Notes have their minimums; Presenter gets 60% of the
        rest, up to 320px on a row that fits, Notes the remainder (up to
        260px on a row that fits). A row that scrolls has no maximum."""
        self.assertEqual(TYPE_W, round(m['type']))                       # fixed columns stay fixed
        spare = m['card'] - m['min']
        pres = PRES_MIN + (min(320 - PRES_MIN, spare * 0.6) if capped else spare * 0.6)
        self.assertAlmostEqual(pres, m['pres'], delta=1.5)
        self.assertAlmostEqual(NOTES_MIN + spare - (pres - PRES_MIN), m['notes'], delta=1.5)
        if capped:
            self.assertLessEqual(m['pres'], 320 + 0.5)
            self.assertLessEqual(m['notes'], 260 + 0.5)

    def test_one_card_per_row_where_two_do_not_fit(self):
        # Every column showing, one card across up to a (2 x minimum + gap)
        # row. Three sessions don't fit, so the row scrolls and the card
        # fills it exactly, past the maximum.
        for width, height in ((820, 1180), (1180, 820), (1400, 900)):
            with self.subTest(width=width):
                m = self.layout(self.open(width, height))
                self.assertEqual(CARD_MIN, round(m['min']))
                self.assertAlmostEqual(m['row'], m['card'], delta=1)
                self.assertEqual(0, m['pageOverflow'])
                self.assert_spare_shared(m, capped=False)
                self.assertEqual('Session 1 of 3', m['pos'])

    def test_as_many_cards_as_fit_at_the_minimum(self):
        m = self.layout(self.open(1920, 1080))
        self.assertAlmostEqual((m['row'] - 18) / 2, m['card'], delta=1)
        self.assert_spare_shared(m, capped=False)
        self.assertEqual('Sessions 1–2 of 3', m['pos'])

    def test_zeroed_column_variables_fit_more_cards(self):
        # What hiding columns does: Headset and Notes off takes the minimum
        # to 533px, so a 1440 laptop row fits two.
        page = self.open(1440, 900)
        page.evaluate("""() => { const r = document.getElementById('mto-root');
            r.style.setProperty('--mto-w-headset', '0px'); r.style.setProperty('--mto-min-notes', '0px');
            mtoLayoutRows(); }""")
        m = self.layout(page)
        self.assertEqual(A1_MIN, round(m['min']))
        self.assertAlmostEqual((m['row'] - 18) / 2, m['card'], delta=1)
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

    def test_wide_monitor_two_sessions_left_aligned_capped_and_names_fit(self):
        # A wide monitor with two sessions: the cards sit at the left of the
        # row at their maximum (the rest of the row stays empty, rather than
        # spreading Mic'd far from the name), Presenter is at its 320px, and a
        # 20-character name shows whole. (The old fixed-width cards cut the
        # same name to ~14 characters.)
        name = 'Alexandra Montgomery'
        self.assertEqual(20, len(name))
        project = Project.objects.create(name='Wide show', owner=self.owner)
        day = ShowDay.objects.create(project=project, date=date(2026, 11, 16))
        for i in range(2):
            session = MicSession.objects.create(day=day, name='Session {}'.format(i + 1), num_mics=1, order=i)
            assignment = session.mic_assignments.first()
            slot = (assignment.presenter_slots.first()
                    or PresenterSlot.objects.create(assignment=assignment, order=0, is_active=True))
            slot.presenter = Presenter.objects.create(project=project, name=name)
            slot.save()
        s = self.client.session
        s['current_project_id'] = project.pk
        s.save()
        page = self.open(2500, 1200)
        m = page.evaluate("""() => {
            const g = document.querySelector('.mto-session-grid'), cs = getComputedStyle(g);
            const cards = [...g.querySelectorAll('.mto-session')];
            const left = g.getBoundingClientRect().left + parseFloat(cs.paddingLeft);
            const w = (c, sel) => c.querySelector(sel).getBoundingClientRect().width;
            return {
                cards: cards.length,
                lefts: cards.map(c => Math.round(c.getBoundingClientRect().left - left)),
                widths: cards.map(c => c.getBoundingClientRect().width),
                fixed: ['.mto-th-rf', '.mto-th-type', '.mto-th-hc', '.mto-th-pl', '.mto-th-micd'].map(sel => Math.round(w(cards[0], sel))),
                pres: w(cards[0], '.mto-th-pres'), notes: w(cards[0], '.mto-th-notes'),
                names: cards.map(c => { const i = c.querySelector('.mto-pres-input');
                                        return [i.value, i.scrollWidth, i.clientWidth]; }),
            }; }""")
        self.assertEqual(2, m['cards'])
        self.assertEqual([0, round(m['widths'][0]) + 18], m['lefts'])        # left-aligned, side by side
        for width in m['widths']:
            self.assertLessEqual(width, CARD_MAX + 0.5)
        self.assertEqual(FIXED, m['fixed'])
        self.assertAlmostEqual(320, m['pres'], delta=0.5)
        self.assertGreater(m['pres'], m['notes'])
        for value, needed, shown in m['names']:
            self.assertEqual(name, value)
            self.assertLessEqual(needed, shown, '{!r} is cut off ({} px needed, {} shown)'.format(value, needed, shown))


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class CardMaximumBrowserTests(StaticLiveServerTestCase):
    """A day with fewer sessions than fit across (one, say) gets cards as
    wide as the other days', never one stretched card, and hiding columns
    visibly shrinks it."""

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

    def show(self, sessions_per_day):
        self.owner, project, _ = make_show(sessions_per_day)
        self.client.force_login(self.owner)
        s = self.client.session
        s['current_project_id'] = project.pk
        s.save()

    def open(self, width, hidden=()):
        UserProfile.objects.filter(user=self.owner).update(ui_prefs={'mic_overview': {'hidden': list(hidden)}})
        context = self.browser.new_context(viewport={'width': width, 'height': 900})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.live_server_url + reverse('planner:mic_tracker_overview'))
        page.wait_for_load_state('networkidle')
        return page

    @staticmethod
    def days(page):
        """Per day, per card: [left offset in the row, width], and cards wholly on screen."""
        return page.evaluate("""() => [...document.querySelectorAll('.mto-session-grid')].map(g => {
            const box = g.getBoundingClientRect(), left = box.left + parseFloat(getComputedStyle(g).paddingLeft);
            const cards = [...g.querySelectorAll('.mto-session')];
            return {cards: cards.map(c => { const r = c.getBoundingClientRect(); return [r.left - left, r.width]; }),
                    across: cards.filter(c => { const r = c.getBoundingClientRect();
                                                return r.left >= box.left - 1 && r.right <= box.right + 1; }).length}; })""")

    def test_lone_card_on_a_wide_monitor_is_capped_and_left_aligned(self):
        self.show([1])
        for hidden, cap in (((), CARD_MAX), (('headset', 'notes'), A1_MAX)):
            with self.subTest(hidden=hidden):
                ((left, width),) = self.days(self.open(2500, hidden))[0]['cards']
                self.assertAlmostEqual(0, left, delta=0.5)
                self.assertAlmostEqual(cap, width, delta=0.5)

    def test_a1_setup_narrows_a_lone_card(self):
        self.show([1])
        for width in (1440, 2500):
            with self.subTest(width=width):
                a2 = self.days(self.open(width))[0]['cards'][0][1]
                a1 = self.days(self.open(width, ('headset', 'notes')))[0]['cards'][0][1]
                self.assertLess(a1, a2 - 300)

    def test_every_day_has_the_same_card_width(self):
        # Mon 2 sessions, Tue 1. Under A1 setup at 1440 two fit across: Tue's
        # card is as wide as Mon's, not the whole row.
        self.show([2, 1])
        mon, tue = self.days(self.open(1440, ('headset', 'notes')))
        self.assertEqual(2, mon['across'])
        self.assertAlmostEqual(mon['cards'][0][1], tue['cards'][0][1], delta=0.5)
        self.assertAlmostEqual(0, tue['cards'][0][0], delta=0.5)

    def test_multi_session_days_fit_as_many_across_as_before(self):
        # The count across still comes from the card minimum.
        self.show([5])
        for width, hidden, across in ((820, (), 1), (1440, (), 1), (1440, ('headset', 'notes'), 2),
                                      (1920, (), 2), (2500, (), 3), (2500, ('headset', 'notes'), 4)):
            with self.subTest(width=width, hidden=hidden):
                day = self.days(self.open(width, hidden))[0]
                self.assertEqual(across, day['across'])
                self.assertEqual(0, round(day['cards'][0][0]))

    def test_laptop_widths_one_across_or_two_under_a1_setup(self):
        # Every column: one across through a 1512 MacBook Pro window, the card
        # filling the row. A1 setup: two across from 1480 down to 1242.
        self.show([2])
        day = self.days(self.open(1512))[0]
        self.assertEqual(1, day['across'])
        self.assertAlmostEqual(1512 - 158, day['cards'][0][1], delta=1)
        for width in (1242, 1480, 1512):
            with self.subTest(width=width):
                self.assertEqual(2, self.days(self.open(width, ('headset', 'notes')))[0]['across'])
        self.assertEqual(1, self.days(self.open(1222, ('headset', 'notes')))[0]['across'])

    def test_every_dropdown_choice_fits_its_column(self):
        # A select sized to one choice (width: auto) is as wide as that
        # choice needs, arrow and padding included; it must fit the cell.
        self.show([1])
        session = MicSession.objects.get(day__project__owner=self.owner)
        assignment = session.mic_assignments.first()
        assignment.presenter_slots.first() or PresenterSlot.objects.create(
            assignment=assignment, order=0, is_active=True)
        page = self.open(1440)
        short = page.evaluate("""() => [...document.querySelectorAll('.mto-row')[0].querySelectorAll('select')].flatMap(sel => {
            const td = sel.closest('td'), cs = getComputedStyle(td);
            const have = td.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            return [...sel.options].map(o => {
                const t = document.createElement('select');
                t.className = sel.className; t.style.width = 'auto'; t.style.position = 'absolute';
                t.append(new Option(o.text)); document.body.append(t);
                const need = t.getBoundingClientRect().width; t.remove();
                return need > have ? `${td.className}: "${o.text}" needs ${need}px, has ${have}px` : null;
            }).filter(Boolean); })""")
        self.assertEqual(3, page.locator('.mto-row').first.locator('select').count())
        self.assertEqual([], short)

    def test_presenter_at_ipad_portrait_width(self):
        # A day that fits (capped) and one that scrolls (uncapped).
        self.show([1, 3])
        page = self.open(820)
        widths = page.evaluate("[...document.querySelectorAll('.mto-th-pres')].map(e => e.getBoundingClientRect().width)")
        self.assertEqual(4, len(widths))
        for width in widths:
            self.assertGreaterEqual(width, 182)

    def test_no_card_is_ever_cut_off_and_names_always_fit(self):
        # iPad and laptop / desktop widths, a 2-session and a 5-session day,
        # every column and A1 setup: at the start of each row and at every
        # session it can snap to, each card on screen is wholly inside the
        # row (a card maximum on a row that scrolled used to stop the card
        # short and show part of the next one), and a 20-character name is
        # never truncated.
        self.show([2, 5])
        project = Project.objects.get(owner=self.owner)
        for session in MicSession.objects.filter(day__project=project):
            for assignment in session.mic_assignments.all():
                slot = (assignment.presenter_slots.first()
                        or PresenterSlot.objects.create(assignment=assignment, order=0, is_active=True))
                slot.presenter = Presenter.objects.create(project=project, name=NAME20)
                slot.save()
        cut, short = [], []
        for hidden in ((), ('headset', 'notes')):
            page = self.open(1200, hidden)
            for width in [820, 1180] + list(range(1200, 1701, 20)):
                page.set_viewport_size({'width': width, 'height': 900})
                page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
                found = page.evaluate("""() => [...document.querySelectorAll('.mto-session-grid')].flatMap((g, day) => {
                    const cs = getComputedStyle(g), pad = parseFloat(cs.paddingLeft);
                    const cards = [...g.querySelectorAll('.mto-session')], out = [];
                    for (const at of cards) {
                        g.scrollTo({left: at.offsetLeft - pad, behavior: 'instant'});
                        const box = g.getBoundingClientRect();
                        const left = box.left + pad, right = box.right - parseFloat(cs.paddingRight);
                        cards.forEach((c, i) => { const r = c.getBoundingClientRect();
                            const seen = r.right > box.left + 0.5 && r.left < box.right - 0.5;
                            if (seen && (r.left < left - 1 || r.right > right + 1))
                                out.push(`day ${day + 1} at session ${cards.indexOf(at) + 1}: session ${i + 1} cut`); });
                    }
                    g.scrollTo({left: 0, behavior: 'instant'});
                    return out; })""")
                cut += ['{} {}px: {}'.format(hidden or 'all columns', width, f) for f in found]
                names = page.evaluate("""() => [...document.querySelectorAll('.mto-pres-input')]
                    .filter(i => i.value).map(i => [i.value, i.scrollWidth, i.clientWidth])""")
                self.assertEqual(2 * (2 + 5), len(names))                    # 2 RFs a session, 7 sessions
                short += ['{} {}px: {} needs {}, has {}'.format(hidden or 'all columns', width, *n)
                          for n in names if n[1] > n[2]][:1]
        self.assertEqual([], cut[:12], '{} cut-off views'.format(len(cut)))
        self.assertEqual([], short[:12], '{} widths truncate a 20-character name'.format(len(short)))



@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SingleSessionDayBrowserTests(StaticLiveServerTestCase):
    """A one-session day between two busier days. It has no session nav, and
    neither it nor a layout error on any one row may stop the other days'
    layout, the column presets, or the "show was updated" poll."""

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
        self.owner, self.project, self.days = make_show([2, 1, 3])
        self.client.force_login(self.owner)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()
        assignment = self.days[0].sessions.first().mic_assignments.first()
        self.slot = (assignment.presenter_slots.first()
                     or PresenterSlot.objects.create(assignment=assignment, order=0, is_active=True))

    def open(self, init_script=None):
        context = self.browser.new_context(viewport={'width': 1440, 'height': 900})
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors, self.logged, self.checks = [], [], []
        page.on('requestfinished', lambda r: '/api/mic-tracker-checksum/' in r.url and self.checks.append(r))
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.on('console', lambda m: m.type == 'error' and self.logged.append(m.text))
        if init_script:
            page.add_init_script(init_script)
        page.clock.install()                       # the poll's timers run when the test says
        page.goto(self.live_server_url + reverse('planner:mic_tracker_overview'))
        page.wait_for_load_state('networkidle')
        return page

    def days_state(self, page):
        """Per day: cards, visible Headset / Notes headers, nav shown, cards per row."""
        return page.evaluate("""() => [...document.querySelectorAll('.mto-day')].map(d => {
            const g = d.querySelector('.mto-session-grid'), nav = d.querySelector('.mto-sess-nav');
            const shown = sel => [...d.querySelectorAll(sel)].filter(e => e.offsetParent).length;
            return {cards: d.querySelectorAll('.mto-session').length,
                    headset: shown('th.mto-col-headset'), notes: shown('th.mto-col-notes'),
                    nav: !!nav && !nav.hidden, perRow: g.style.getPropertyValue('--mto-per-row')}; })""")

    def assert_poll_running(self, page):
        """A change saved from another browser session raises the banner."""
        def tick(checks):
            # Wait for the check to finish: the live server shares the test's
            # in-memory SQLite connection, so its query must not overlap ours.
            done = len(self.checks) + checks
            page.clock.run_for(5100)
            while len(self.checks) < done:
                page.wait_for_timeout(50)
        tick(1)                                    # the first check sets the baseline
        other = Client()
        other.force_login(self.owner)
        s = other.session
        s['current_project_id'] = self.project.pk
        s.save()
        resp = other.post(reverse('planner:update_slot_field'),
                          json.dumps({'slot_id': self.slot.pk, 'field': 'notes', 'value': 'Changed elsewhere'}),
                          content_type='application/json')
        self.assertTrue(resp.json()['success'])
        self.assertFalse(page.locator('#mto-update-banner').is_visible())
        tick(1)
        self.assertTrue(page.locator('#mto-update-banner').is_visible())

    def test_single_session_day_loads_clean_and_presets_reach_every_day(self):
        page = self.open()
        self.assertEqual([], self.errors)
        self.assertEqual([], self.logged)
        state = self.days_state(page)
        self.assertEqual([2, 1, 3], [d['cards'] for d in state])
        self.assertEqual([True, False, True], [d['nav'] for d in state])   # A2 entry: one card across
        self.assertEqual([2, 1, 3], [d['headset'] for d in state])

        page.click('#mto-cols-btn')
        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('.mto-cols-preset[data-hide="headset notes"]')
        state = self.days_state(page)
        self.assertEqual([(0, 0)] * 3, [(d['headset'], d['notes']) for d in state])
        # A1 setup fits two across: the two-session day loses its nav, the
        # three-session day keeps it, the one-session day never has one.
        self.assertEqual([False, False, True], [d['nav'] for d in state])
        self.assertEqual('Sessions 1–2 of 3', page.locator('.mto-sess-pos').nth(1).text_content())

        with page.expect_response('**/api/ui-prefs/mic-overview/'):
            page.click('.mto-cols-preset[data-hide=""]')
        state = self.days_state(page)
        self.assertEqual([(2, 2), (1, 1), (3, 3)], [(d['headset'], d['notes']) for d in state])
        self.assertEqual([], self.errors)
        self.assertEqual([], self.logged)
        self.assert_poll_running(page)

    def test_an_error_on_one_row_stops_neither_the_others_nor_the_poll(self):
        # Saved A1 setup, so the later three-session day lays out two across.
        profile = UserProfile.objects.get(user=self.owner)
        profile.ui_prefs = {'mic_overview': {'hidden': ['headset', 'notes']}}
        profile.save()
        # Make laying out the one-session day throw.
        page = self.open("""(() => { const real = window.getComputedStyle;
            window.getComputedStyle = function(el) {
                if (el && el.id === 'mto-grid-%d') throw new Error('layout broke');
                return real.apply(this, arguments); }; })()""" % self.days[1].pk)
        self.assertEqual([], self.errors)                                  # caught, not thrown
        self.assertTrue(any('mto-grid-{}'.format(self.days[1].pk) in m for m in self.logged), self.logged)
        state = self.days_state(page)
        self.assertEqual('2', state[2]['perRow'])                          # the day after it still laid out
        self.assertEqual('Sessions 1–2 of 3', page.locator('.mto-sess-pos').nth(1).text_content())
        self.assert_poll_running(page)
