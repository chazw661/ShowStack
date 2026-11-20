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

from planner.models import AudioChecklist, MicSession, PresenterSlot, Project, ShowDay
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

    def test_overview_notes_and_the_conflict_box(self):
        # mic_tracker_overview.html: the stored note in the Notes box, and the
        # note someone else saved, which mtoShowNotesConflict puts beside it.
        day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 1))
        session = MicSession.objects.create(day=day, name='Keynote', num_mics=1, order=0)
        assignment = session.mic_assignments.first()
        slot = (assignment.presenter_slots.first()
                or PresenterSlot.objects.create(assignment=assignment, order=0, is_active=True))
        slot.notes = QUOTED
        slot.save()
        conflict = {'success': False, 'conflict': True, 'current': NAME}
        page = self.open(reverse('planner:mic_tracker_overview'),
                         [('**/api/mic/slot/update/**', conflict)])
        self.assert_text(page, '.mto-notes-input', QUOTED, 'overview note')
        box = page.locator('.mto-notes-input').first
        box.fill('mine')
        box.blur()                                     # change -> save -> conflict
        page.wait_for_selector('.mto-notes-conflict-text')
        self.assert_text(page, '.mto-notes-conflict-text', NAME, 'conflicting note')
        self.assertEqual('mine', box.input_value())

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

    # -- PA Cable Entries --------------------------------------------------------

    def test_names_on_a_pa_cable_run_and_its_linked_arrays_panel(self):
        # pa_cable_array_speakers.js builds the arrays panel from JSON; the
        # change form and the list are server-rendered.
        from planner.models import (Amp, AmpLocation, AmpModel, PACableSchedule, PAZone,
                                    SoundvisionPrediction, SpeakerArray)
        rack = AmpLocation.objects.create(project=self.project, name=QUOTED)
        amp = Amp.objects.create(project=self.project, name=NAME, location=rack,
                                 amp_model=AmpModel.objects.get_or_create(
                                     manufacturer="L'Acoustics", model_name='XSS4',
                                     defaults={'channel_count': 4})[0])
        pred = SoundvisionPrediction.objects.create(project=self.project, file_name='x.pdf')
        array = SpeakerArray.objects.create(prediction=pred, source_name=NAME,
                                            array_base_name=NAME,
                                            configuration='vertical_flown', bumper_type='K2-BUMP')
        run = PACableSchedule.objects.create(
            project=self.project, amp=amp, destination=QUOTED[:50],
            label=PAZone.objects.create(project=self.project, name='<b>HL'))
        run.speaker_arrays.add(array)
        page = self.open(reverse('admin:planner_pacableschedule_change', args=[run.pk]))
        page.wait_for_selector('#pa-array-ref .pa-array-ref__arrayname')
        self.assert_text(page, '#pa-array-ref .pa-array-ref__arrayname', array.display_name,
                         'arrays panel')
        self.assert_text(page, '#id_source option', NAME, 'From picker: amp')
        self.assert_text(page, '#id_source option', QUOTED, 'From picker: whole rack')
        self.assertEqual(page.eval_on_selector_all('#id_source optgroup', 'gs => gs.map(g => g.label)'),
                         [QUOTED], 'From picker: rack group label')
        self.assert_text(page, '#id_speaker_arrays_to option', NAME, 'linked arrays picker')
        self.assertEqual(page.input_value('#id_destination'), QUOTED[:50])
        page = self.open(reverse('admin:planner_pacableschedule_changelist'))
        self.assert_text(page, '#result_list td.field-from_col', NAME, 'From column')
        self.assert_text(page, '#result_list td.field-to_col', QUOTED[:50], 'To column')
        self.assert_text(page, '#result_list td.field-arrays_col .cb-array', NAME, 'Arrays column')
        self.assert_text(page, '#result_list .field-cable_label_col', '<b>HL', 'Cable Label')

    # -- Amp input pickers ------------------------------------------------------

    def test_names_in_the_amp_input_pickers_and_link_tooltip(self):
        # The datalists are filled from JSON with .value; the link button's
        # tooltip is server-rendered, then set by script after a save.
        from planner.models import (Amp, AmpLocation, AmpModel, Device, DeviceOutput,
                                    P1Output, P1Processor, SystemProcessor)
        from planner.models import Location
        proc = SystemProcessor.objects.create(project=self.project, name=NAME, device_type='P1',
                                              location=Location.objects.create(
                                                  project=self.project, name='Racks'))
        P1Processor.objects.create(system_processor=proc)
        P1Output.objects.filter(p1_processor__system_processor=proc, output_type='AVB',
                                channel_number=1).update(label=QUOTED)
        box = Device.objects.create(project=self.project, name=QUOTED)
        DeviceOutput.objects.create(device=box, output_number=1, signal_name=NAME)
        amp = Amp.objects.create(project=self.project, name='Amp 1',
                                 location=AmpLocation.objects.create(project=self.project, name='L'),
                                 amp_model=AmpModel.objects.get_or_create(
                                     manufacturer="L'Acoustics", model_name='XSS4',
                                     defaults={'channel_count': 4, 'has_avb_inputs': True})[0])
        avb = f'AVB 1 - {QUOTED} ({NAME})'
        io = f'{NAME} · {QUOTED} Out 1'
        page = self.open(reverse('admin:planner_amp_changelist'))
        values = page.eval_on_selector_all('#amp-avb-input-options option', 'os => os.map(o => o.value)')
        self.assertIn(avb, values)
        values = page.eval_on_selector_all('#amp-analog-input-options option', 'os => os.map(o => o.value)')
        self.assertIn(io, values)
        cell = f'input.amp-cell-input[data-channel-id="{amp.channels.get(channel_number=1).pk}"]'
        page.click('.amp-avb-toggle')                     # empty AVB rows are folded away
        page.fill(cell + '[data-field="avb_stream"]', avb)
        page.press(cell + '[data-field="avb_stream"]', 'Tab')
        page.wait_for_selector('td.amp-input-cell.linked .amp-link-btn.linked')
        title = page.get_attribute('td.amp-input-cell.linked .amp-link-btn', 'title')
        self.assertEqual(title, f'Linked to {avb}')
        page.reload()
        page.wait_for_load_state('networkidle')
        self.assertEqual(page.get_attribute('td.amp-input-cell.linked .amp-link-btn', 'title'),
                         f'Linked to {avb}')
        self.assert_text(page, cell + '[data-field="avb_stream"]', avb, 'linked input text')

    # -- Wiring Diagram ----------------------------------------------------------

    def test_names_in_the_wiring_diagram_svg_and_warnings(self):
        # connections/svg.py draws names server-side; the page's only script
        # is the fit/100% toggle, which must leave the text as it is.
        from planner.models import (Device, DeviceOutput, Location, P1Input, P1Processor,
                                    SystemProcessor)
        rack = Location.objects.create(project=self.project, name='Racks')
        box = Device.objects.create(project=self.project, name=NAME)
        DeviceOutput.objects.create(device=box, output_number=1, signal_name=QUOTED)
        for name in ('SL', 'SR'):
            proc = SystemProcessor.objects.create(project=self.project, name=name, device_type='P1',
                                                  location=rack)
            P1Processor.objects.create(system_processor=proc)
            P1Input.objects.filter(p1_processor__system_processor=proc, input_type='AES',
                                   channel_number=1).update(label=QUOTED)
        # An amp input naming no output: an "Unlinked feeds" box of its text.
        from planner.models import Amp, AmpChannel, AmpLocation
        amp = Amp.objects.create(project=self.project, name='Amp 1', location=AmpLocation.objects.create(
            project=self.project, name='Amp Racks'))
        AmpChannel.objects.update_or_create(amp=amp, channel_number=1,
                                            defaults={'aes_input': NAME})
        page = self.open(reverse('planner:wiring_diagram'))
        page.wait_for_selector('svg.wd-svg')
        self.assert_text(page, 'svg.wd-svg .wd-box title', NAME, 'device box')
        self.assert_text(page, 'svg.wd-svg .wd-label', QUOTED, 'ambiguous edge label')
        self.assert_text(page, '.wd-warnings li', QUOTED, 'warnings panel')
        self.assert_text(page, 'svg.wd-svg .wd-box.unlinked title', f'AES: {NAME}', 'unlinked feed box')
        self.assert_text(page, 'svg.wd-svg .wd-col', 'Unlinked feeds', 'feeds column')
        page.click('#wd-toggle')
        self.assert_text(page, 'svg.wd-svg .wd-box title', NAME, 'after the toggle')
        self.assertFalse(page.evaluate("document.getElementById('wd-scroll').classList.contains('fit')"))

    # -- Dashboard -------------------------------------------------------------

    # -- Mic Planner walkthrough ----------------------------------------------

    def test_walkthrough_row_text_names_leftovers_and_day_strip(self):
        from planner.mic_plan import importer
        from planner.models import ShowflowImport, ShowflowPerson
        from planner.tests import showflow_fixture as F

        day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 1))
        # Hostile text in a description, a Speaker cell (left over: not a
        # name) and a BSM cue, on a cue-free page so every name is locked.
        pages = [[F.HEADER_E,
                  F._row14('300', '8:00 AM', '8:45 AM', '0:45:00', 'Opening ' + QUOTED),
                  F._row14('301', desc='Max enters ' + NAME, speaker='Max Pine'),
                  F._row14('302', desc='Ola enters', speaker='Ola Brand ' + NAME, bsm=QUOTED),
                  F._row14('303', desc='Ned joins', speaker='Ned Quill'),
                  # A company after "Name," and an upper-case note: grey marks.
                  F._row14('304', desc='Ola returns', speaker='Ola Brand, Acme Health <b>x</b>'),
                  F._row14('305', desc='Doors', speaker='ROOM AND FOYER')]]
        pending = importer.stage_upload(day, F.build_pdf(pages), NAME + '.pdf', self.owner)
        importer.confirm(pending)
        ShowflowPerson.objects.filter(day=day, display_name='Max Pine').update(display_name=NAME)
        ShowflowPerson.objects.filter(day=day, display_name='Ned Quill').update(display_name=QUOTED)
        importer.reject_phrase(day, QUOTED + ' hall', self.owner)
        self.assertTrue(ShowflowImport.objects.filter(day=day, status='active').exists())
        page = self.open(reverse('planner:mic_plan') + '?day={}#walk'.format(day.pk))
        page.wait_for_selector('#mp-walk-list .mp-wp')
        # The PDF wraps a long cell, so the row text is matched up to its first break.
        self.assert_text(page, '#mp-walk-list .mp-wp-body', 'enters <img src=x', 'row text')
        self.assert_text(page, '#mp-walk-list .mp-wp-body', '"\'><img src=x', 'row text in quotes')
        self.assert_text(page, '#mp-walk-list .mp-wchip b', NAME, 'name on a chip')
        self.assert_text(page, '#mp-walk-list .mp-wp-plock .q', QUOTED, 'person lock question')
        self.assert_text(page, '#mp-walk-list .mp-wp-same option', NAME, 'Same as list')
        self.assert_text(page, '#mp-walk-strip', QUOTED + ' hall', 'rejected phrase on the strip')
        page.click('#wp-{} .mp-wp-edit summary'.format(
            ShowflowImport.objects.get(day=day).rows.get(line_no='301').pk))
        self.assert_text(page, '#mp-walk-list .mp-wp-editor', NAME, 'row editor')
        self.assertEqual(0, page.evaluate("document.querySelectorAll('#mp-walk-list mark img, #mp-walk-list b img').length"))
        self.assert_text(page, '#mp-walk-list mark.company', 'Acme Health <b>x<', 'company mark')   # "/" ends the company
        self.assert_text(page, '#mp-walk-list mark.note', 'ROOM AND FOYER', 'note mark')
        self.assertEqual(0, page.evaluate("document.querySelectorAll('#mp-walk-list mark b').length"))

    def test_day_and_project_names_on_the_dashboard(self):
        day = {'date': '2026-03-01', 'name': NAME, 'mic_count': 3, 'planned': True}
        stats = {'project_name': NAME, 'show_days': [day],
                 'mic_planner': [{'day': 1, 'state': 'imported', 'date': '2026-03-01', 'name': NAME}]}
        page = self.open(reverse('admin:index'), [('**/dashboard/stats/**', stats)])
        page.wait_for_selector('#mic-planner-list .ss-mp-day')
        self.assert_text(page, '#ss-project-name', NAME, 'project name')
        self.assert_text(page, '#mic-days-list', NAME, 'Mic Tracker card')
        self.assert_text(page, '#mic-planner-list', NAME, 'Mic Planner card')
