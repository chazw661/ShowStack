"""User-typed names on pages that build markup in the browser: each renders as
text. One test per fixed spot (#181): the name ``<img src=x onerror=alert(1)>``
(and, where it lands in an attribute or an onclick, a quote-breaking form of
it) must show as those characters, make no <img>, and raise no dialog.

Each test goes through the page's own code: the stored name, or the JSON the
page fetches (served by Playwright with the name in it).

Skipped unless asked for, because it needs Playwright and its browsers, which
the deploy does not install::

    SS_BROWSER_TESTS=1 python manage.py test planner.tests.test_xss_browser \\
        --settings=audiopatch.test_settings

(``pip install playwright && playwright install chromium`` once.) The
server-side fixes are tested without a browser in ``test_xss_server``.
"""

import json
import os
import unittest
from datetime import date

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from planner.models import AudioChecklist, MicSession, Project, ShowDay
from planner.tests.test_console_patch_picker import staff

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ENABLED = bool(os.environ.get('SS_BROWSER_TESTS')) and sync_playwright is not None

NAME = '<img src=x onerror=alert(1)>'
# For names that land in an attribute value or a quoted onclick argument.
QUOTED = '"\'><img src=x onerror=alert(1)>'


def answer(body):
    """A route handler serving ``body`` as JSON."""
    def handle(route):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(body))
    return handle


@unittest.skipUnless(ENABLED, 'set SS_BROWSER_TESTS=1 (needs playwright + browsers)')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class NamesRenderAsTextTests(StaticLiveServerTestCase):

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
        self.owner = staff('xss_owner')
        self.project = Project.objects.create(name='Show X', owner=self.owner)
        self.client.force_login(self.owner)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    # -- helpers -------------------------------------------------------------

    def open(self, url, routes=()):
        """``routes``: (glob, json body) answered by the browser itself."""
        context = self.browser.new_context()
        context.add_cookies([{'name': 'sessionid', 'value': self.client.cookies['sessionid'].value,
                              'url': self.live_server_url}])
        self.addCleanup(context.close)
        page = context.new_page()
        self.dialogs = []
        page.on('dialog', lambda d: (self.dialogs.append(d.message), d.dismiss()))
        for glob, body in routes:
            page.route(glob, answer(body))
        page.goto(self.live_server_url + url)
        page.wait_for_load_state('networkidle')
        return page

    def assert_text(self, page, selector, expected, what):
        page.wait_for_timeout(300)                     # an <img src=x> errors at once
        self.assertEqual([], self.dialogs, '{}: a dialog was raised'.format(what))
        self.assertEqual(0, page.evaluate("document.querySelectorAll('img[src=\"x\"]').length"),
                         '{}: the name became an <img>'.format(what))
        shown = page.evaluate('(s) => [...document.querySelectorAll(s)].map(e => e.value !== undefined && '
                              'e.tagName === "INPUT" ? e.value : e.textContent)', selector)
        self.assertTrue(any(expected in t for t in shown), '{}: {!r} not shown in {}'.format(what, expected, shown))

    # -- Mic Tracker -----------------------------------------------------------

    def mic_tracker(self, routes=()):
        day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 1))
        self.session = MicSession.objects.create(day=day, name='Keynote', num_mics=1, order=0)
        return self.open(reverse('planner:mic_tracker') + '?day={}'.format(day.pk), routes)

    def test_mic_group_names_in_the_group_manager_and_picker(self):
        groups = {'success': True, 'groups': [{'id': 7, 'name': NAME, 'color': 'blue'}]}
        page = self.mic_tracker([('**/api/mic-groups/**', groups)])
        # mic_tracker_v5.js refreshGroupManagerList
        page.evaluate('(s) => refreshGroupManagerList(s)', self.session.pk)
        page.wait_for_selector('#group-manage-list .group-manage-name', state='attached')
        self.assert_text(page, '#group-manage-list .group-manage-name', NAME, 'group manager')
        # mic_tracker.html openSlotGroupPicker
        page.evaluate("""(s) => { const p = document.createElement('div'); p.id = 'slot-group-picker-9001';
                                  const dot = document.createElement('span'); document.body.append(p, dot);
                                  openSlotGroupPicker(9001, s, dot); }""", self.session.pk)
        page.wait_for_selector('#slot-group-picker-9001 .group-picker-item', state='attached')
        self.assert_text(page, '#slot-group-picker-9001 .group-picker-item', NAME, 'group picker')

    def test_shared_presenter_names(self):
        # mic_tracker_v5.js updateSharedPresentersList (its list element is not
        # on today's page; made here so the code still runs).
        page = self.mic_tracker()
        page.evaluate("""(n) => { const l = document.createElement('div'); l.id = 'sharedPresentersList';
                                  document.body.append(l); currentSharedPresenters = [n];
                                  updateSharedPresentersList(); }""", NAME)
        self.assert_text(page, '#sharedPresentersList .shared-presenter-item span', NAME, 'shared presenter')

    def test_mic_type_badge(self):
        # mic_tracker_render.js setTypeBadge, through MTTSlots.patch
        page = self.mic_tracker()
        row = page.locator('[data-assignment-id]').first
        aid, sid = row.get_attribute('data-assignment-id'), row.get_attribute('data-slot-id') or ''
        page.evaluate('([a, s, n]) => MTTSlots.patch(a, s, {micType: n})', [aid, sid, NAME])
        self.assert_text(page, '.mic-type-badge', NAME, 'mic type badge')

    # -- Network monitor -------------------------------------------------------

    def test_device_label_on_a_dante_card(self):
        # network_monitor.html createDanteCard: label in text, attributes and
        # the Remove button (which used to be an onclick string).
        page = self.open(reverse('planner:network_monitor'))
        page.evaluate("""(n) => document.body.append(createDanteCard(
            {device_id: 42, label: n, ip: '10.0.0.9', status: 'online'}, {clock_role: 'master'}))""", QUOTED)
        self.assert_text(page, '#nhm-device-42 .nhm-card-name', QUOTED, 'card name')
        label = page.evaluate("document.querySelector('#nhm-device-42 .nhm-dot').getAttribute('aria-label')")
        self.assertEqual(QUOTED + ': online', label)
        if page.locator('#nhm-device-42 .nhm-card-remove').count():
            page.evaluate("document.querySelector('#nhm-device-42 .nhm-card-remove').click()")
            self.assert_text(page, 'body', 'Remove ' + QUOTED + '?', 'remove dialog')

    # -- Audio checklist -------------------------------------------------------

    def test_checklist_task_text_and_template_names(self):
        AudioChecklist.create_default_checklists(self.project)
        for checklist in AudioChecklist.objects.filter(project=self.project):
            checklist.tasks.update(task=QUOTED)
        templates = {'templates': [{'id': 3, 'name': QUOTED}]}
        page = self.open(reverse('planner:audio_checklist'),
                         [('**/audiochecklist/template/list/**', templates)])
        page.wait_for_selector('.task-input')
        # audio_checklist.html createSetupRow / createDailyRow: the value attribute
        self.assert_text(page, '.task-input', QUOTED, 'task text')
        # day labels (kept in this browser): the value attribute
        page.evaluate("(n) => { setDayLabel(activeTab, 1, n); renderChecklists(); }", QUOTED)
        self.assert_text(page, '.day-label-input', QUOTED, 'day label')
        # loadTemplateList: the name in text and in the Load button
        page.evaluate('openLoadTemplateModal()')
        page.wait_for_timeout(300)
        self.assert_text(page, 'body', QUOTED, 'template name')
        load = page.locator('button[data-name]').first
        self.assertEqual(QUOTED, load.get_attribute('data-name'))
        load.click()                                   # confirm() shows the name
        self.assertEqual(['Load "{}"? This will replace ALL current checklist tasks.'.format(QUOTED)], self.dialogs)

    # -- COMM config -----------------------------------------------------------

    def test_comm_template_crew_and_key_label_names(self):
        templates = {'templates': [{'id': 5, 'template_name': QUOTED}]}
        chips = {'chips': [{'letter': 'A', 'label': NAME, 'assigned': True}]}
        page = self.open(reverse('planner:comm_config'),
                         [('**/comm-config/template/list/**', templates),
                          ('**/comm-config/role/chips/**', chips),
                          ('**/comm-config/crew-name/add/**', {'ok': True, 'id': 77})])
        # comm_config.html loadTemplateDropdown / openLoadTemplateModal
        page.evaluate("""() => { if (!document.getElementById('template-dropdown-items')) {
                                   const d = document.createElement('div'); d.id = 'template-dropdown-items';
                                   document.body.append(d); }
                                 loadTemplateDropdown(); }""")
        page.wait_for_selector('#template-dropdown-items .cc-dropdown-item')
        self.assert_text(page, '#template-dropdown-items .cc-dropdown-item', QUOTED, 'template dropdown')
        self.assertEqual(QUOTED, page.locator('#template-dropdown-items .cc-dropdown-item').get_attribute('data-name'))
        page.evaluate('openLoadTemplateModal()')
        page.wait_for_selector('#ccTemplateListContainer button[data-name]')
        self.assert_text(page, '#ccTemplateListContainer span', QUOTED, 'template list')
        # refreshRoleChips: a partyline label on a key chip
        page.evaluate("""() => { const c = document.createElement('div'); c.id = 'role-chips-31';
                                 document.body.append(c); refreshRoleChips(31); }""")
        page.wait_for_selector('#role-chips-31 .cc-key-chip')
        self.assert_text(page, '#role-chips-31 .cc-key-chip', NAME, 'key chip')
        # addCrewName: the name just typed, added to the list
        page.evaluate("""(n) => { for (const id of ['newCrewNameInput', 'crewNamesList_modal']) {
                                    if (!document.getElementById(id)) {
                                      const e = document.createElement(id.startsWith('new') ? 'input' : 'div');
                                      e.id = id; document.body.append(e); } }
                                  document.getElementById('newCrewNameInput').value = n; addCrewName(); }""", NAME)
        page.wait_for_selector('#crew-name-77')
        self.assert_text(page, '#crew-name-77 .cc-crew-name-text', NAME, 'crew name')

    # -- Dashboard -------------------------------------------------------------

    def test_day_and_project_names_on_the_dashboard(self):
        day = {'date': '2026-03-01', 'name': NAME, 'mic_count': 3, 'planned': True}
        stats = {'project_name': NAME, 'show_days': [day],
                 'mic_planner': [{'day': 1, 'state': 'imported', 'date': '2026-03-01', 'name': NAME}]}
        page = self.open(reverse('admin:index'), [('**/dashboard/stats/**', stats)])
        page.wait_for_selector('#mic-planner-list .ss-mp-day')
        self.assert_text(page, '#ss-project-name', NAME, 'project name')
        self.assert_text(page, '#mic-days-list', NAME, 'Mic Tracker card')
        self.assert_text(page, '#mic-planner-list', NAME, 'Mic Planner card')
