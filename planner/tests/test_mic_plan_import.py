"""Mic Plan import: replace-or-add, what a re-import keeps, delete, and access.

Run with::

    python manage.py test planner.tests.test_mic_plan_import --settings=audiopatch.test_settings
"""

import os
from datetime import date
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from planner.admin_site import showstack_admin_site
from planner.mic_plan import importer, planning, solver
from planner.models import (
    MicPlan, MicPlanA2Action, MicPlanSettings, Presenter, Project, ProjectMember, ShowDay, ShowflowEvent, ShowflowImport,
    ShowflowPerson, ShowflowRow, UserProfile,
)
from planner.tests import showflow_fixture as F

PDFS = {}


def pdf(name):
    if name not in PDFS:
        PDFS[name] = F.build_pdf(getattr(F, name))
    return PDFS[name]


class MicPlanBase(TestCase):

    def setUp(self):
        self.owner = self.user('mp_owner')
        self.project = Project.objects.create(name='MP Show', owner=self.owner)
        self.day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 1))
        self.editor = self.user('mp_editor')
        self.viewer = self.user('mp_viewer')
        for user, role in ((self.editor, 'editor'), (self.viewer, 'viewer')):
            ProjectMember.objects.create(user=user, project=self.project, role=role,
                                         invited_by=self.owner)
        self.other_owner = self.user('mp_other')
        self.other = Project.objects.create(name='Other Show', owner=self.other_owner)
        self.other_day = ShowDay.objects.create(project=self.other, date=date(2026, 3, 1))

    def user(self, username):
        user = User.objects.create_user(username, f'{username}@example.com', 'pw', is_staff=True)
        UserProfile.objects.update_or_create(user=user, defaults={'account_type': 'paid'})
        return user

    def use(self, user, project=None):
        self.client.force_login(user)
        s = self.client.session
        s['current_project_id'] = (project or self.project).id
        s.save()

    def upload(self, name='MAIN_PAGES', filename='day1.pdf', day=None):
        return self.client.post(reverse('planner:mic_plan_upload'), {
            'day': (day or self.day).pk,
            'showflow': SimpleUploadedFile(filename, pdf(name), content_type='application/pdf'),
        })

    def parts(self):
        return list(ShowflowImport.objects.filter(day=self.day, status='active')
                    .order_by('part_order'))

    def person(self, name):
        return ShowflowPerson.objects.get(day=self.day, display_name=name)


class UploadTests(MicPlanBase):

    def test_first_upload_imports_straight_away(self):
        self.use(self.editor)
        resp = self.upload()
        part = ShowflowImport.objects.get(day=self.day)
        self.assertRedirects(resp, reverse('planner:mic_plan') + f'?day={self.day.pk}&part={part.pk}')
        self.assertEqual('active', part.status)
        self.assertEqual(19, part.rows.count())
        self.assertEqual({'Sam', 'Lee', 'Rio'}, set(part.crew_names))
        self.assertTrue(ShowflowEvent.objects.filter(row__showflow_import=part,
                                                     person__display_name='Robin Cole').exists())
        self.assertEqual(7 * 60, part.span_start)
        kinds = {w['kind'] for w in part.warnings}
        self.assertTrue({'caught_but_listed', 'never_caught', 'no_cue', 'bsm_only'} <= kinds)

    def test_every_import_logs_its_timing_without_the_file_name(self):
        self.use(self.editor)
        with self.assertLogs('planner.mic_plan.importer', level='INFO') as logs:
            self.upload(filename='secret-client.pdf')
        line = logs.output[0]
        self.assertRegex(line, r'Mic Plan import: 3 pages, 19 rows, extract \d+\.\d\ds, parse')
        self.assertNotIn('secret-client', line)

    def test_the_pdf_never_touches_disk(self):
        """In memory only: no temporary upload file, nothing under MEDIA_ROOT."""
        self.use(self.editor)
        media = settings.MEDIA_ROOT
        before = sorted(os.walk(media)) if os.path.isdir(media) else []
        with mock.patch('django.core.files.uploadhandler.TemporaryFileUploadHandler.new_file',
                        side_effect=AssertionError('wrote a temporary file')):
            with self.settings(FILE_UPLOAD_MAX_MEMORY_SIZE=10):  # would spill to disk by default
                self.upload()
        self.assertEqual(1, ShowflowImport.objects.count())
        after = sorted(os.walk(media)) if os.path.isdir(media) else []
        self.assertEqual(before, after)
        field_types = {f.get_internal_type() for m in (ShowflowImport, ShowflowRow)
                       for f in m._meta.get_fields() if hasattr(f, 'get_internal_type')}
        self.assertFalse(field_types & {'FileField', 'ImageField', 'BinaryField'})

    def test_unreadable_file_is_a_message_not_a_crash(self):
        self.use(self.editor)
        resp = self.client.post(reverse('planner:mic_plan_upload'), {
            'day': self.day.pk,
            'showflow': SimpleUploadedFile('x.pdf', F.build_pdf(F.NO_HEADER_PAGES)),
        }, follow=True)
        self.assertContains(resp, "Couldn&#x27;t find the column header")
        self.assertFalse(ShowflowImport.objects.exists())

    def test_overlapping_upload_defaults_to_replacing_that_part(self):
        self.use(self.editor)
        self.upload()
        old = self.parts()[0]
        self.upload('REVISED_PAGES', 'Actual day1.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        resp = self.client.get(reverse('planner:mic_plan_confirm', args=[pending.pk]))
        self.assertEqual(old, resp.context['target'])
        self.assertContains(resp, f'value="replace:{old.pk}" checked')

        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': f'replace:{old.pk}'})
        self.assertEqual([pending.pk], [p.pk for p in self.parts()])
        self.assertFalse(ShowflowImport.objects.filter(pk=old.pk).exists())

    def test_non_overlapping_upload_defaults_to_adding_a_part(self):
        self.use(self.editor)
        self.upload()
        self.upload('PM_PAGES', 'pm.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        resp = self.client.get(reverse('planner:mic_plan_confirm', args=[pending.pk]))
        self.assertIsNone(resp.context['target'])
        self.assertContains(resp, 'value="add" checked')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]), {'choice': 'add'})
        self.assertEqual(['day1.pdf', 'pm.pdf'], [p.source_filename for p in self.parts()])

    def test_the_default_can_be_switched(self):
        self.use(self.editor)
        self.upload()
        self.upload('REVISED_PAGES', 'Actual day1.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]), {'choice': 'add'})
        self.assertEqual(2, len(self.parts()))

    def test_cancel_discards_the_pending_import(self):
        self.use(self.editor)
        self.upload()
        self.upload('PM_PAGES', 'pm.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': 'add', 'cancel': '1'})
        self.assertFalse(ShowflowImport.objects.filter(pk=pending.pk).exists())
        self.assertEqual(1, len(self.parts()))

    def test_pending_imports_never_show_on_the_page(self):
        self.use(self.editor)
        self.upload()
        self.upload('PM_PAGES', 'pm.pdf')
        resp = self.client.get(reverse('planner:mic_plan') + f'?day={self.day.pk}')
        self.assertEqual(1, len(resp.context['parts']))
        self.assertNotContains(resp, 'pm.pdf')


class PeopleAcrossPartsTests(MicPlanBase):

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload()
        self.part = self.parts()[0]
        self.presenter = Presenter.objects.create(project=self.project, name='Kim K. (keynote)')

    def test_merge_presenter_and_hint_survive_a_re_import(self):
        kk, kim = self.person('KK'), self.person('Kim Keynote')
        self.client.post(reverse('planner:mic_plan_merge', args=[kk.pk]), {'into': kim.pk})
        self.client.post(reverse('planner:mic_plan_person', args=[kim.pk]),
                         {'presenter': self.presenter.pk, 'mic_hint': 'HH'})
        kim.refresh_from_db()
        self.assertEqual(['KK'], kim.aliases)
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='KK').exists())
        self.assertTrue(ShowflowEvent.objects.filter(person=kim, row__line_no='117').exists())

        self.upload('REVISED_PAGES', 'Actual day1.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': f'replace:{self.part.pk}'})
        kim.refresh_from_db()
        self.assertEqual(['KK'], kim.aliases)
        self.assertEqual(self.presenter, kim.presenter)
        self.assertEqual(('HH', True), (kim.mic_hint, kim.mic_hint_locked))
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='KK').exists())

    def test_events_from_every_part_point_at_the_days_person(self):
        self.upload('PM_PAGES', 'pm.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]), {'choice': 'add'})
        alex = ShowflowPerson.objects.filter(day=self.day, display_name='Alex Host')
        self.assertEqual(1, alex.count())
        parts = set(ShowflowEvent.objects.filter(person=alex.get())
                    .values_list('row__showflow_import', flat=True))
        self.assertEqual({self.part.pk, pending.pk}, parts)

    def test_delete_removes_people_no_part_mentions_any_more(self):
        self.upload('PM_PAGES', 'pm.pdf')
        pm = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pm.pk]), {'choice': 'add'})
        self.client.post(reverse('planner:mic_plan_delete', args=[self.part.pk]))
        self.assertFalse(ShowflowImport.objects.filter(pk=self.part.pk).exists())
        self.assertFalse(ShowflowRow.objects.filter(showflow_import_id=self.part.pk).exists())
        names = set(ShowflowPerson.objects.filter(day=self.day).values_list('display_name', flat=True))
        self.assertEqual({'Alex Host', 'Jo Emcee'}, names)   # both in the PM part

    def test_crew_edit_re_reads_cues(self):
        self.client.post(reverse('planner:mic_plan_crew', args=[self.part.pk]),
                         {'crew': ['Sam', 'Rio'], 'add': ''})
        self.part.refresh_from_db()
        self.assertEqual(['Sam', 'Rio'], self.part.crew_names)
        self.assertFalse(ShowflowEvent.objects.filter(row__line_no='110').exists())
        self.assertTrue(any(w['kind'] == 'unknown_crew' for w in self.part.warnings))

    def test_removing_an_alias_splits_the_person_out_again(self):
        kk, kim = self.person('KK'), self.person('Kim Keynote')
        self.client.post(reverse('planner:mic_plan_merge', args=[kk.pk]), {'into': kim.pk})
        self.client.post(reverse('planner:mic_plan_unalias', args=[kim.pk]), {'alias': 'KK'})
        self.assertTrue(ShowflowPerson.objects.filter(day=self.day, display_name='KK').exists())

    def test_a_presenter_with_the_same_name_is_linked_on_creation(self):
        Presenter.objects.create(project=self.project, name='Pat Guest')
        Presenter.objects.create(project=self.other, name='Jo Emcee')   # another tenant's
        ShowflowPerson.objects.filter(day=self.day).delete()
        importer.rebuild_day(self.day)
        self.assertEqual('Pat Guest', self.person('Pat Guest').presenter.name)
        self.assertIsNone(self.person('Jo Emcee').presenter)

    def test_settings_save(self):
        resp = self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 2, 'mic_min': 4, 'demic_min': 2, 'premic_lead_min': 45, 'margin_min': 10,
            'wireless_channels': '24', 'handheld_channels': '4', 'spare_handhelds': '1'})
        self.assertEqual(302, resp.status_code)
        s = MicPlanSettings.objects.get(project=self.project)
        self.assertEqual((2, 4, 2, 45, 10, 24, 4, 1),
                         (s.a2_count, s.mic_min, s.demic_min, s.premic_lead_min, s.margin_min,
                          s.wireless_channels, s.handheld_channels, s.spare_handhelds))
        self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 0, 'mic_min': 4, 'demic_min': 2, 'premic_lead_min': 45, 'margin_min': 10})
        self.assertEqual(2, MicPlanSettings.objects.get(project=self.project).a2_count)


class AccessTests(MicPlanBase):

    def setUp(self):
        super().setUp()
        self.use(self.owner)
        self.upload()
        self.part = self.parts()[0]
        self.kk = self.person('KK')
        self.kim = self.person('Kim Keynote')

    def writes(self, part=None, person=None, into=None):
        part, person, into = part or self.part, person or self.kk, into or self.kim
        return [
            (reverse('planner:mic_plan_upload'), {'day': self.day.pk}),
            (reverse('planner:mic_plan_delete', args=[part.pk]), {}),
            (reverse('planner:mic_plan_crew', args=[part.pk]), {'crew': ['X']}),
            (reverse('planner:mic_plan_break', args=[part.pk]), {'row': part.rows.first().pk, 'is_break': '1'}),
            (reverse('planner:mic_plan_helpers', args=[part.pk]), {'row': part.rows.first().pk, 'helpers': '1'}),
            (reverse('planner:mic_plan_person', args=[person.pk]), {'mic_hint': 'HH'}),
            (reverse('planner:mic_plan_merge', args=[person.pk]), {'into': into.pk}),
            (reverse('planner:mic_plan_unalias', args=[person.pk]), {'alias': 'x'}),
            (reverse('planner:mic_plan_settings'), {'a2_count': 3}),
            (reverse('planner:mic_plan_generate', args=[self.day.pk]), {}),
        ]

    def test_viewer_reads_the_page_without_controls(self):
        self.use(self.viewer)
        resp = self.client.get(reverse('planner:mic_plan'))
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, 'Kim Keynote')
        self.assertNotContains(resp, reverse('planner:mic_plan_upload'))
        self.assertNotContains(resp, 'Merge into')

    def test_viewer_is_refused_every_write(self):
        self.use(self.viewer)
        for url, data in self.writes():
            with self.subTest(url=url):
                self.assertEqual(403, self.client.post(url, data).status_code)
        self.assertTrue(ShowflowImport.objects.filter(pk=self.part.pk).exists())
        self.assertTrue(ShowflowPerson.objects.filter(pk=self.kk.pk).exists())

    def test_another_projects_ids_are_404(self):
        self.use(self.other_owner, self.other)
        settings_url = reverse('planner:mic_plan_settings')    # the session's own project
        for url, data in [w for w in self.writes()[1:] if w[0] != settings_url]:
            with self.subTest(url=url):
                self.assertEqual(404, self.client.post(url, data).status_code)
        resp = self.client.post(reverse('planner:mic_plan_upload'), {
            'day': self.day.pk, 'showflow': SimpleUploadedFile('a.pdf', pdf('MAIN_PAGES'))})
        self.assertEqual(404, resp.status_code)
        self.assertEqual(1, ShowflowImport.objects.filter(day=self.day).count())

    def test_presenter_from_another_project_cannot_be_linked(self):
        foreign = Presenter.objects.create(project=self.other, name='Elsewhere')
        resp = self.client.post(reverse('planner:mic_plan_person', args=[self.kim.pk]),
                                {'presenter': foreign.pk})
        self.assertEqual(404, resp.status_code)

    def test_merge_target_must_be_the_same_day(self):
        other_day = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        stranger = ShowflowPerson.objects.create(day=other_day, display_name='Z', name_key='z')
        resp = self.client.post(reverse('planner:mic_plan_merge', args=[self.kk.pk]),
                                {'into': stranger.pk})
        self.assertEqual(404, resp.status_code)

    def test_another_projects_page_shows_none_of_this(self):
        self.use(self.other_owner, self.other)
        resp = self.client.get(reverse('planner:mic_plan') + f'?day={self.day.pk}')
        self.assertEqual(200, resp.status_code)
        self.assertNotContains(resp, 'Kim Keynote')
        self.assertEqual(self.other_day, resp.context['day'])


class SidebarTests(MicPlanBase):

    def test_sidebar_entry_opens_the_review_page_for_every_role(self):
        for user in (self.owner, self.editor, self.viewer):
            with self.subTest(user=user.username):
                self.use(user)
                resp = self.client.get(reverse('admin:planner_console_changelist'))
                planner = next(a for a in resp.context['available_apps']
                               if a['app_label'] == 'planner')
                row = next(m for m in planner['models'] if m['object_name'] == 'ShowflowImport')
                self.assertEqual('Mic Planner', str(row['name']))
                self.assertEqual(reverse('planner:mic_plan'), row['admin_url'])
                self.assertIsNone(row['add_url'])

    def test_admin_list_redirects_to_the_page(self):
        self.use(self.owner)
        resp = self.client.get(reverse('admin:planner_showflowimport_changelist'))
        self.assertRedirects(resp, reverse('planner:mic_plan'), fetch_redirect_response=False)
        self.assertIn(ShowflowImport, showstack_admin_site._registry)


class ReviewPageTests(MicPlanBase):
    """The page before and after a plan: showflow, Review cards, crew only with cues."""

    def setUp(self):
        super().setUp()
        self.use(self.owner)

    def page(self, **query):
        url = reverse('planner:mic_plan')
        if query:
            url += '?' + '&'.join('{}={}'.format(k, v) for k, v in query.items())
        return self.client.get(url)

    def test_before_a_plan_the_showflow_and_generate_are_shown(self):
        self.upload()
        resp = self.page()
        self.assertContains(resp, 'Showflow + plan')
        self.assertContains(resp, 'Generate plan')
        self.assertContains(resp, 'No plan yet.')
        self.assertContains(resp, 'id="mp-crew"')             # this file has cues
        self.assertIsNone(resp.context['plan'])
        self.assertIsNone(resp.context['chart'])

    def test_a_cue_free_file_has_no_crew_panel(self):
        self.upload()                                          # the project now has crew names
        day2 = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        self.upload('CLIENT_E_PAGES', day=day2)
        self.assertTrue(ShowflowImport.objects.get(day=day2).crew_names)   # copied, yet no cues
        resp = self.page(day=day2.pk)
        self.assertNotContains(resp, 'id="mp-crew"')
        self.assertContains(resp, "intro'd line 304")

    def test_review_cards_carry_parser_flags_with_their_line(self):
        self.upload('CLIENT_E_PAGES')
        cards = self.page().context['cards']
        texts = {(c['line'], c['text']) for c in cards}
        self.assertIn(('311', 'Line 311: description names people not in the Speaker column — check '
                              'who goes on'), texts)
        self.assertTrue(any(line == '319' and text.startswith('Line 319: which Vic?')
                            for line, text in texts))
        part = self.parts()[0]
        self.assertContains(self.page(), '?day={}&amp;part={}#showflow:row-'.format(self.day.pk, part.pk))

    def test_intro_rows_are_stored_per_part(self):
        self.upload('CLIENT_E_PAGES')
        part = self.parts()[0]
        row = ShowflowRow.objects.get(showflow_import=part,
                                      order=self.person('Dr. Una Reyes').flags['intro'][str(part.pk)])
        self.assertEqual('306', row.line_no)

    def test_settings_are_in_the_drawer(self):
        self.upload()
        resp = self.page()
        self.assertContains(resp, reverse('planner:mic_plan_settings'))
        self.assertContains(resp, 'name="wireless_channels"')
        self.assertContains(resp, 'name="spare_handhelds"')

    def test_one_editor_for_the_selected_person_not_controls_on_every_row(self):
        self.upload()
        resp = self.page()
        self.assertContains(resp, 'id="mp-editor"', count=1)
        self.assertContains(resp, 'name="presenter"', count=1)
        self.assertContains(resp, 'name="into"', count=1)

    def test_fonts_are_self_hosted(self):
        resp = self.page()
        self.assertNotContains(resp, 'fonts.googleapis')
        css = open(os.path.join(settings.BASE_DIR, 'planner', 'static', 'css', 'mic_plan.css')).read()
        self.assertNotIn('googleapis', css)
        for family in ('barlow-condensed', 'ibm-plex-sans', 'ibm-plex-mono'):
            folder = os.path.join(settings.BASE_DIR, 'planner', 'static', 'fonts', family)
            self.assertTrue(os.path.exists(os.path.join(folder, 'OFL.txt')))
            for name in os.listdir(folder):
                if name.endswith('.woff2'):
                    self.assertIn('../fonts/{}/{}'.format(family, name), css)

    def test_page_cap_is_sixty(self):
        self.assertEqual(60, importer.MAX_PAGES)
        self.assertContains(self.page(), 'up to 60 pages')

    def test_viewer_gets_no_editor(self):
        self.upload()
        self.use(self.viewer)
        resp = self.page()
        self.assertNotContains(resp, 'id="mp-editor"')
        self.assertNotContains(resp, 'id="mp-import"')


class ProvenanceTests(MicPlanBase):
    """A re-import or re-read keeps only what the user set; the parser's own
    earlier output is rebuilt, so a parser fix is never undone by old state."""

    # What the #160 parser made of CLIENT_E_PAGES: a title + surname person, and
    # no Vic Stone. Fed back as known names, "Vic" on 304 went to Vic Dahl.
    OLD_PARSE = ['Ann Pike', 'Dr Reyes', 'Dr. Lou Penn', 'Max Pine', 'Ned Quill', 'Ola Brand',
                 'Vic Dahl', 'Zed Moss']

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload('CLIENT_E_PAGES')
        self.part = self.parts()[0]

    def seed_old_parse(self):
        from planner.mic_plan.parser import name_key
        ShowflowPerson.objects.filter(day=self.day).delete()
        for name in self.OLD_PARSE:
            ShowflowPerson.objects.create(day=self.day, display_name=name, name_key=name_key(name))

    def reread(self, part=None):
        return self.client.post(reverse('planner:mic_plan_reread', args=[(part or self.part).pk]))

    def lines(self, name, part=None):
        part = part or self.part
        orders = self.person(name).flags['rows'].get(str(part.pk), [])
        return [r.line_no for r in ShowflowRow.objects.filter(showflow_import=part, order__in=orders)
                .order_by('order')]

    def flags(self, part=None):
        part = part or self.parts()[0]
        return [w for w in part.warnings if w['kind'] != 'parse']

    def assert_current_rules(self, part=None):
        part = part or self.parts()[0]
        part.refresh_from_db()
        self.assertEqual(['304', '305', '315', '318'], self.lines('Vic Stone', part))
        self.assertEqual(['316', '317', '318'], self.lines('Vic Dahl', part))
        names = set(ShowflowPerson.objects.filter(day=self.day).values_list('display_name', flat=True))
        self.assertNotIn('Dr Reyes', names)
        self.assertIn('Dr. Una Reyes', names)
        self.assertEqual(['description_names', 'which_first'],
                         sorted(w['kind'] for w in self.flags(part)))

    def test_stale_parser_people_do_not_survive_a_replace(self):
        self.seed_old_parse()
        self.upload('CLIENT_E_PAGES', 'again.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': f'replace:{self.part.pk}'})
        self.assert_current_rules(pending)

    def test_re_read_applies_the_current_rules(self):
        self.seed_old_parse()
        resp = self.reread()
        self.assertEqual(302, resp.status_code)
        self.assert_current_rules()

    def test_re_read_recomputes_stored_times(self):
        row = ShowflowRow.objects.get(showflow_import=self.part, line_no='304')
        good = row.est_time
        ShowflowRow.objects.filter(pk=row.pk).update(est_time=1, is_segment=not row.is_segment)
        self.part.span_start = None
        self.part.save()
        self.reread()
        row.refresh_from_db()
        self.part.refresh_from_db()
        self.assertEqual(good, row.est_time)
        self.assertIsNotNone(self.part.span_start)

    def test_a_user_merge_survives_a_re_read_and_still_wins(self):
        stone, dahl = self.person('Vic Stone'), self.person('Vic Dahl')
        self.client.post(reverse('planner:mic_plan_merge', args=[stone.pk]), {'into': dahl.pk})
        self.reread()
        dahl.refresh_from_db()
        self.assertEqual(['Vic Stone'], dahl.aliases)
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='Vic Stone').exists())
        self.assertIn('304', self.lines('Vic Dahl'))

    def test_a_user_presenter_link_survives_even_with_another_name(self):
        presenter = Presenter.objects.create(project=self.project, name='Someone Else')
        stone = self.person('Vic Stone')
        self.client.post(reverse('planner:mic_plan_person', args=[stone.pk]),
                         {'presenter': presenter.pk, 'mic_hint': ''})
        self.seed_old_parse()        # the old parse never had Vic Stone...
        ShowflowPerson.objects.filter(pk=stone.pk).delete()
        stone = ShowflowPerson.objects.create(
            day=self.day, display_name='Vic Stone', name_key='vic stone', presenter=presenter,
            flags={'presenter_by': 'user'})                  # ...but the user linked them
        self.reread()
        stone.refresh_from_db()
        self.assertEqual(presenter, stone.presenter)
        self.assertEqual('user', stone.flags['presenter_by'])
        self.assertEqual(['304', '305', '315', '318'], self.lines('Vic Stone'))

    def test_an_automatic_presenter_link_is_matched_afresh(self):
        presenter = Presenter.objects.create(project=self.project, name='Someone Else')
        ShowflowPerson.objects.filter(day=self.day, display_name='Vic Stone').update(
            presenter=presenter)                             # e.g. a link from before PR 1.2
        Presenter.objects.create(project=self.project, name='Vic Dahl')
        self.reread()
        self.assertIsNone(self.person('Vic Stone').presenter)
        self.assertEqual('Vic Dahl', self.person('Vic Dahl').presenter.name)

    def test_saving_only_a_hint_does_not_lock_the_presenter(self):
        stone = self.person('Vic Stone')
        self.client.post(reverse('planner:mic_plan_person', args=[stone.pk]),
                         {'presenter': '', 'mic_hint': 'HH'})
        stone.refresh_from_db()
        self.assertNotIn('presenter_by', stone.flags)
        self.reread()
        stone.refresh_from_db()
        self.assertEqual(('HH', True), (stone.mic_hint, stone.mic_hint_locked))

    def test_a_stale_person_without_user_state_is_deleted(self):
        ShowflowPerson.objects.create(day=self.day, display_name='Dr Reyes', name_key='dr. reyes')
        self.reread()
        self.assertFalse(ShowflowPerson.objects.filter(day=self.day, display_name='Dr Reyes').exists())

    def test_a_stale_person_with_user_state_is_kept_flagged_and_removable(self):
        gone = ShowflowPerson.objects.create(day=self.day, display_name='Dr Reyes',
                                             name_key='dr. reyes', mic_hint='HH',
                                             mic_hint_locked=True)
        self.reread()
        gone.refresh_from_db()
        self.assertTrue(gone.flags['gone'])
        resp = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(resp, 'no longer in this showflow')
        self.assertContains(resp, reverse('planner:mic_plan_remove', args=[gone.pk]))
        self.assertTrue(any(c['kind'] == 'gone' and c['person'] == gone.pk
                            for c in resp.context['cards']))

        self.client.post(reverse('planner:mic_plan_remove', args=[gone.pk]))
        self.assertFalse(ShowflowPerson.objects.filter(pk=gone.pk).exists())
        resp = self.client.get(reverse('planner:mic_plan'))
        self.assertFalse(any(c['kind'] == 'gone' for c in resp.context['cards']))

    def test_remove_refuses_someone_still_in_the_showflow(self):
        stone = self.person('Vic Stone')
        self.client.post(reverse('planner:mic_plan_remove', args=[stone.pk]))
        self.assertTrue(ShowflowPerson.objects.filter(pk=stone.pk).exists())

    def test_re_read_and_remove_are_editor_only_and_project_scoped(self):
        gone = ShowflowPerson.objects.create(day=self.day, display_name='Gone', name_key='gone',
                                             flags={'gone': True}, mic_hint_locked=True)
        urls = [reverse('planner:mic_plan_reread', args=[self.part.pk]),
                reverse('planner:mic_plan_remove', args=[gone.pk])]
        self.use(self.viewer)
        self.assertNotContains(self.client.get(reverse('planner:mic_plan')), urls[0])
        for url in urls:
            with self.subTest(url=url, who='viewer'):
                self.assertEqual(403, self.client.post(url).status_code)
        self.use(self.other_owner, self.other)
        for url in urls:
            with self.subTest(url=url, who='other project'):
                self.assertEqual(404, self.client.post(url).status_code)
        self.assertTrue(ShowflowPerson.objects.filter(pk=gone.pk).exists())
        self.use(self.editor)
        self.assertContains(self.client.get(reverse('planner:mic_plan')), urls[0])


class PlanTests(MicPlanBase):
    """Generate, re-generate, stale marking and plan.json."""

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload()
        self.part = self.parts()[0]

    def generate(self, replace=False):
        return self.client.post(reverse('planner:mic_plan_generate', args=[self.day.pk]),
                                {'replace': '1'} if replace else {})

    def plan(self):
        return MicPlan.objects.get(day=self.day)

    def test_generate_saves_the_plan_and_the_page_shows_it(self):
        resp = self.generate()
        self.assertEqual(302, resp.status_code)
        plan = self.plan()
        self.assertEqual((1, False, 'cues'), (plan.version, plan.stale, plan.cue_mode))
        self.assertTrue(plan.packs)
        self.assertTrue(MicPlanA2Action.objects.filter(plan=plan, kind='mic').exists())
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'Re-generate')
        self.assertContains(page, 'Replace the draft (v1)?')
        self.assertIsNotNone(page.context['chart'])
        self.assertContains(page, 'class="verb mic"')
        self.assertContains(page, 'A2 busy')
        self.assertEqual(len(plan.packs), len(page.context['chart']['lanes']))

    def test_re_generate_needs_confirming_and_bumps_the_version(self):
        self.generate()
        self.generate()                                  # not confirmed
        self.assertEqual(1, self.plan().version)
        self.generate(replace=True)
        self.assertEqual(2, self.plan().version)
        self.assertEqual(1, MicPlan.objects.filter(day=self.day).count())

    def test_backup_hint_adds_a_counted_pack_and_settings_are_snapshot(self):
        jo = self.person('Jo Emcee')
        self.client.post(reverse('planner:mic_plan_person', args=[jo.pk]),
                         {'mic_hint': 'backup', 'backup_mic_type': 'body'})
        self.generate()
        plan = self.plan()
        backups = [p for p in plan.packs if p['backup_of'] == jo.pk]
        self.assertEqual(1, len(backups))
        self.assertEqual(('body', 'Jo Emcee backup'), (backups[0]['pool'], backups[0]['label']))
        stats = self.client.get(reverse('planner:mic_plan')).context['stats']
        self.assertEqual(len([p for p in plan.packs if p['pool'] == 'body']), stats['body'])
        self.assertEqual(1, plan.settings['a2_count'])

    def test_changes_after_generating_mark_the_plan_stale(self):
        kk, kim = self.person('KK'), self.person('Kim Keynote')
        for change in (
                lambda: self.client.post(reverse('planner:mic_plan_reread', args=[self.part.pk])),
                lambda: self.client.post(reverse('planner:mic_plan_merge', args=[kk.pk]), {'into': kim.pk}),
                lambda: self.client.post(reverse('planner:mic_plan_person', args=[kim.pk]),
                                         {'mic_hint': 'HH'})):
            with self.subTest(change=change):
                self.generate(replace=True)
                self.assertFalse(self.plan().stale)
                change()
                self.assertTrue(self.plan().stale)
        self.assertContains(self.client.get(reverse('planner:mic_plan')), 'Re-generate to update it.')

    def test_a_presenter_change_alone_does_not_make_it_stale(self):
        self.generate()
        presenter = Presenter.objects.create(project=self.project, name='Someone')
        kim = self.person('Kim Keynote')
        self.client.post(reverse('planner:mic_plan_person', args=[kim.pk]),
                         {'presenter': presenter.pk, 'mic_hint': kim.mic_hint})
        self.assertFalse(self.plan().stale)

    def test_changed_settings_are_bannered(self):
        self.generate()
        self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 2, 'mic_min': 3, 'demic_min': 3, 'premic_lead_min': 30, 'margin_min': 5})
        self.assertContains(self.client.get(reverse('planner:mic_plan')),
                            'Plan settings changed after this plan was made')

    def test_plan_json_is_the_stored_plan(self):
        self.generate()
        url = reverse('planner:mic_plan_json', args=[self.day.pk])
        self.use(self.viewer)
        resp = self.client.get(url)
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        plan = self.plan()
        self.assertEqual(plan.version, data['version'])
        self.assertEqual(plan.actions.count(), len(data['actions']))
        self.assertEqual(plan.appearances.count(), len(data['appearances']))
        first = data['actions'][0]
        self.assertEqual({'time', 'verb', 'name', 'rf', 'reason', 'a2', 'text', 'start_min', 'rf_number'},
                         {'time', 'verb', 'name', 'rf', 'reason', 'a2', 'text', 'start_min', 'rf_number'} & set(first))
        self.assertEqual(plan.segments, data['segments'])

    def test_plan_json_is_scoped_and_needs_a_plan(self):
        url = reverse('planner:mic_plan_json', args=[self.day.pk])
        self.assertEqual(404, self.client.get(url).status_code)          # no plan yet
        self.generate()
        self.use(self.other_owner, self.other)
        self.assertEqual(404, self.client.get(url).status_code)

    def test_viewers_cannot_generate_and_see_no_generate_button(self):
        self.use(self.viewer)
        self.assertEqual(403, self.generate().status_code)
        self.assertFalse(MicPlan.objects.filter(day=self.day).exists())
        self.assertNotContains(self.client.get(reverse('planner:mic_plan')), 'Generate plan')

    def test_another_project_cannot_generate_this_day(self):
        self.use(self.other_owner, self.other)
        self.assertEqual(404, self.generate().status_code)

    def test_cue_free_day_is_built_from_line_estimates(self):
        day2 = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        self.upload('CLIENT_E_PAGES', day=day2)
        self.client.post(reverse('planner:mic_plan_generate', args=[day2.pk]))
        plan = MicPlan.objects.get(day=day2)
        self.assertEqual('line estimates', plan.cue_mode)
        self.assertContains(self.client.get(reverse('planner:mic_plan') + '?day={}'.format(day2.pk)),
                            'Built from line estimates')


class PackPolicyPageTests(MicPlanBase):
    """The pack policy setting, both-policy counts, and the Break toggle."""

    def setUp(self):
        super().setUp()
        self.use(self.editor)
        self.upload()
        self.part = self.parts()[0]

    def generate(self):
        return self.client.post(reverse('planner:mic_plan_generate', args=[self.day.pk]), {'replace': '1'})

    def save_settings(self, **extra):
        return self.client.post(reverse('planner:mic_plan_settings'), {
            'a2_count': 1, 'mic_min': 3, 'demic_min': 3, 'premic_lead_min': 30, 'margin_min': 5, **extra})

    def heading(self):
        """The first segment heading and its detected break value."""
        rows = list(self.part.rows.order_by('order'))
        seg = planning.part_segments(self.part, rows, planning.named_orders(self.day, self.part))[0]
        return seg['row'], seg['detected']

    def test_the_policy_is_saved_shown_and_changing_it_banners_the_plan(self):
        self.assertEqual('recycle_at_breaks', planning.project_settings(self.project).pack_policy)
        self.generate()
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'Pack use: <b>Recycle at breaks</b>')
        self.assertContains(page, 'Recycle at breaks · 1 A2')
        self.assertNotContains(page, 'Plan settings changed after this plan was made')
        self.save_settings(pack_policy='fewest_packs')
        self.assertEqual('fewest_packs', planning.project_settings(self.project).pack_policy)
        self.assertContains(self.client.get(reverse('planner:mic_plan')),
                            'Plan settings changed after this plan was made')
        self.generate()
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'Pack use: <b>Fewest packs</b>')
        self.assertNotContains(page, 'Plan settings changed after this plan was made')

    def test_an_unknown_policy_is_refused(self):
        resp = self.save_settings(pack_policy='whatever')
        self.assertEqual(302, resp.status_code)
        self.assertEqual('recycle_at_breaks', planning.project_settings(self.project).pack_policy)

    def test_a_plan_from_before_the_policy_counts_as_fewest_packs(self):
        self.generate()
        plan = MicPlan.objects.get(day=self.day)
        plan.settings = {k: v for k, v in plan.settings.items() if k != 'pack_policy'}
        plan.save()
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, 'Pack use: <b>Fewest packs</b>')
        self.assertContains(page, 'Plan settings changed after this plan was made')

    def test_both_policy_counts_match_two_separate_solves(self):
        self.save_settings(wireless_channels=2)
        self.generate()
        plan = MicPlan.objects.get(day=self.day)
        data, _, _ = planning.build_day(self.day)
        values = planning.settings_dict(planning.project_settings(self.project))
        for policy in ('recycle_at_breaks', 'fewest_packs'):
            with self.subTest(policy=policy):
                s = solver.summary(solver.solve(data, planning.solver_settings(
                    {**values, 'pack_policy': policy, 'wireless_channels': None})))
                self.assertEqual({'body': s['body'], 'hh': s['hh'], 'mid_session': s['mid_session']},
                                 plan.policy_counts[policy])
        counts = plan.policy_counts
        text = 'Recycle at breaks: {} body'.format(counts['recycle_at_breaks']['body'])
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, text)
        self.assertContains(page, 'Fewest packs: {} body'.format(counts['fewest_packs']['body']))

    def test_the_break_toggle_overrides_detection_marks_the_plan_stale_and_goes_back(self):
        self.generate()
        row, detected = self.heading()
        url = reverse('planner:mic_plan_break', args=[self.part.pk])
        resp = self.client.post(url, {'row': row.pk, 'is_break': '0' if detected else '1'})
        self.assertRedirects(resp, reverse('planner:mic_plan') + '?day={}&part={}#showflow:row-{}'.format(
            self.day.pk, self.part.pk, row.order), fetch_redirect_response=False)
        self.part.refresh_from_db()
        saved = self.part.break_overrides[row.line_no]
        self.assertEqual((not detected, self.editor.pk), (saved['is_break'], saved['by']))
        self.assertTrue(MicPlan.objects.get(day=self.day).stale)
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertContains(page, '{} · set by you'.format('not a break' if detected else 'break'))
        data, _, _ = planning.build_day(self.day)
        self.assertEqual(not detected, next(s for s in data.segments if s.key == row.pk).is_break)
        # Back to the detected value: the override goes.
        self.client.post(url, {'row': row.pk, 'is_break': '1' if detected else '0'})
        self.part.refresh_from_db()
        self.assertEqual({}, self.part.break_overrides)

    def test_another_editor_sees_who_set_it(self):
        row, detected = self.heading()
        self.client.post(reverse('planner:mic_plan_break', args=[self.part.pk]),
                         {'row': row.pk, 'is_break': '0' if detected else '1'})
        self.use(self.owner)
        self.assertContains(self.client.get(reverse('planner:mic_plan')), 'set by mp_editor')

    def test_a_row_that_is_not_a_segment_heading_is_refused(self):
        row = self.part.rows.filter(is_segment=False).first()
        self.client.post(reverse('planner:mic_plan_break', args=[self.part.pk]), {'row': row.pk, 'is_break': '1'})
        self.part.refresh_from_db()
        self.assertEqual({}, self.part.break_overrides)

    def test_a_break_set_by_hand_survives_re_read_and_replace(self):
        row, detected = self.heading()
        self.client.post(reverse('planner:mic_plan_break', args=[self.part.pk]),
                         {'row': row.pk, 'is_break': '0' if detected else '1'})
        self.client.post(reverse('planner:mic_plan_reread', args=[self.part.pk]))
        self.part.refresh_from_db()
        self.assertIn(row.line_no, self.part.break_overrides)
        self.upload('REVISED_PAGES', 'Actual day1.pdf')
        pending = ShowflowImport.objects.get(status='pending')
        self.client.post(reverse('planner:mic_plan_confirm', args=[pending.pk]),
                         {'choice': f'replace:{self.part.pk}'})
        new = self.parts()[0]
        self.assertEqual(pending.pk, new.pk)
        head = new.rows.get(line_no=row.line_no, is_segment=True)
        seg = next(s for s in planning.part_segments(new, list(new.rows.order_by('order')),
                                                     planning.named_orders(self.day, new))
                   if s['row'].pk == head.pk)
        self.assertEqual((not detected, True), (seg['is_break'], bool(seg['override'])))

    def test_viewers_see_a_hand_set_break_but_no_toggle(self):
        row, detected = self.heading()
        self.client.post(reverse('planner:mic_plan_break', args=[self.part.pk]),
                         {'row': row.pk, 'is_break': '0' if detected else '1'})
        self.use(self.viewer)
        page = self.client.get(reverse('planner:mic_plan'))
        self.assertNotContains(page, reverse('planner:mic_plan_break', args=[self.part.pk]))
        self.assertContains(page, 'set by mp_editor')
