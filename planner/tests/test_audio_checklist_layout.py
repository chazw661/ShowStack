"""Audio Checklist layout (FOH and A2 tabs): task names are always readable.

A task name is a one-row textarea that grows with its text, so a long name
wraps instead of being cut off, and is never narrower than a typical
30-character name. Setup and Daily sit side by side only while both fit at
their minimum widths, otherwise Daily stacks under Setup; Daily's day columns
that still don't fit scroll sideways under a sticky TASK column.

Skipped unless SS_BROWSER_TESTS=1 (see test_xss_browser).
"""
import json
import os
import unittest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.models import AudioChecklist, AudioChecklistTask, Project, ProjectMember
from planner.tests.test_console_patch_picker import staff

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

BROWSER = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

NAME30 = 'Label Tops of Amp Racks w/ Loc'
LONG = 'Pack all Prep cables in cube case-including Network, Analogue, and Ethercon (Dante Network)'
WIDTHS = (820, 1180, 1512, 1920)
TABS = ('FOH', 'A2')


@unittest.skipUnless(BROWSER, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ChecklistLayoutBrowserTests(StaticLiveServerTestCase):

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
        self.assertEqual(30, len(NAME30))
        self.owner = staff('checklist_owner')
        self.project = Project.objects.create(name='Checklist show', owner=self.owner)
        AudioChecklist.create_default_checklists(self.project)
        # The first setup and daily task of each tab gets the 30-character
        # name, the second a long one that has to wrap.
        for checklist in AudioChecklist.objects.filter(project=self.project, name__in=['FOH Check List', 'A2 Check List']):
            for task_type in ('setup', 'daily'):
                first, second = checklist.tasks.filter(task_type=task_type).order_by('sort_order', 'pk')[:2]
                AudioChecklistTask.objects.filter(pk=first.pk).update(task=NAME30)
                AudioChecklistTask.objects.filter(pk=second.pk).update(task=LONG)

    def days(self, n):
        AudioChecklist.objects.filter(project=self.project).update(num_days=n)

    def open(self, width, user=None, height=1000):
        self.client.force_login(user or self.owner)
        s = self.client.session
        s['current_project_id'] = self.project.pk
        s.save()
        context = self.browser.new_context(viewport={'width': width, 'height': height})
        # The page sends the csrftoken cookie a browser gets at login.
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url},
                             {'name': 'csrftoken', 'value': 'c' * 32, 'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.errors = []
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.goto(self.live_server_url + reverse('planner:audio_checklist'))
        page.wait_for_selector('.task-input')
        page.wait_for_load_state('networkidle')
        return page

    def tab(self, page, name):
        page.locator('.checklist-tab', has_text=name).click()
        page.wait_for_selector('.task-input')

    @staticmethod
    def measure(page):
        """Per table (setup, daily): every task name's fit, the 30-character
        name's line count, and each panel's box."""
        return page.evaluate("""([name30]) => [...document.querySelectorAll('.checklist-panel')].map(panel => {
            const fields = [...panel.querySelectorAll('tbody textarea.task-input')];
            const line = parseFloat(getComputedStyle(fields[0]).lineHeight);
            const lines = el => Math.round((el.clientHeight - parseFloat(getComputedStyle(el).paddingTop)
                                            - parseFloat(getComputedStyle(el).paddingBottom)) / line);
            const cut = fields.filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)
                              .map(e => e.value);
            const n30 = fields.find(e => e.value === name30), long = fields.find(e => e.value.length > 60);
            const narrowSelects = [...panel.querySelectorAll('tbody select')].filter(s =>
                s.getBoundingClientRect().width < (s.classList.contains('stage-select') ? 136 : 112) - 0.5).length;
            const r = panel.getBoundingClientRect();
            return {cut, lines30: lines(n30), longLines: lines(long), narrowSelects,
                    top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left)}; })""", [NAME30])

    def test_task_names_are_never_cut_off(self):
        problems = []
        for days in (4, 7):
            self.days(days)
            for width in WIDTHS:
                page = self.open(width)
                for tab in TABS:
                    self.tab(page, tab)
                    panels = self.measure(page)
                    self.assertEqual(2, len(panels))
                    for kind, p in zip(('setup', 'daily'), panels):
                        where = '{} days, {}px, {} {}'.format(days, width, tab, kind)
                        if p['cut']:
                            problems.append('{}: cut {}'.format(where, p['cut']))
                        if p['lines30'] != 1:
                            problems.append('{}: the 30-character name takes {} lines'.format(where, p['lines30']))
                        # Where the column is narrower than the 91-character name, it wraps.
                        if width == 820 and p['longLines'] < 2:
                            problems.append('{}: the long name did not wrap'.format(where))
                        if p['narrowSelects']:
                            problems.append('{}: {} dropdowns narrower than their text'.format(where, p['narrowSelects']))
                self.assertEqual([], self.errors)
        self.assertEqual([], problems)

    def test_panels_stack_when_they_dont_both_fit(self):
        self.days(4)
        setup, daily = self.measure(self.open(820))
        self.assertGreaterEqual(daily['top'], setup['bottom'])            # Daily under Setup
        self.assertEqual(setup['left'], daily['left'])
        setup, daily = self.measure(self.open(1920))
        self.assertEqual(setup['top'], daily['top'])                      # side by side
        self.assertGreater(daily['left'], setup['left'])

    def test_task_column_stays_put_while_the_days_scroll(self):
        self.days(7)
        page = self.open(820)
        for tab in TABS:
            self.tab(page, tab)
            page.locator('.daily-scroll').scroll_into_view_if_needed()
            state = page.evaluate("""() => {
                const sc = document.querySelector('.daily-scroll'), box = sc.getBoundingClientRect();
                const before = sc.scrollWidth > sc.clientWidth;
                sc.scrollLeft = sc.scrollWidth;
                const lastDay = [...sc.querySelectorAll('thead th')].slice(-2)[0].getBoundingClientRect();
                const rows = [...sc.querySelectorAll('tbody tr')].map(tr => {
                    const td = tr.querySelector('td'), r = td.getBoundingClientRect();
                    const hit = document.elementFromPoint(r.left + 20, r.top + r.height / 2);
                    return Math.abs(r.left - box.left) < 1 && td.contains(hit); });
                return {scrolls: before, scrolled: sc.scrollLeft > 0, lastDayShown: lastDay.right <= box.right + 1,
                        taskOnTop: rows.filter(Boolean).length, rows: rows.length}; }""")
            self.assertTrue(state['scrolls'] and state['scrolled'], (tab, state))
            self.assertTrue(state['lastDayShown'], (tab, state))
            self.assertEqual(state['rows'], state['taskOnTop'], (tab, state))

    def test_editing_a_task_name_still_saves_and_stays_one_line(self):
        self.days(4)
        page = self.open(1180)
        field = page.locator('.checklist-panel').nth(1).locator('textarea.task-input').first
        task_id = int(field.evaluate("e => e.closest('tr').dataset.taskId"))
        field.fill('')
        field.type('Line check')
        page.evaluate("(e) => { e.value += '\\nall wedges'; e.dispatchEvent(new Event('input')); }", field.element_handle())
        with page.expect_response('**/audiochecklist/update-task/**') as resp:
            field.press('Enter')                                          # saves, adds no line
        self.assertTrue(resp.value.json()['success'])
        self.assertEqual('Line check all wedges', AudioChecklistTask.objects.get(pk=task_id).task)
        self.assertEqual('Line check all wedges', field.input_value())
        self.assertEqual([], self.errors)

    def test_viewer_sees_whole_names_but_cannot_edit(self):
        viewer = staff('checklist_viewer')
        ProjectMember.objects.create(project=self.project, user=viewer, role='viewer', invited_by=self.owner)
        self.days(4)
        page = self.open(820, viewer)
        p = self.measure(page)
        self.assertEqual([[], []], [x['cut'] for x in p])
        self.assertEqual(0, page.evaluate(
            "[...document.querySelectorAll('textarea.task-input')].filter(e => !e.disabled).length"))
