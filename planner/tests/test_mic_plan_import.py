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
from planner.mic_plan import importer
from planner.models import (
    MicPlanSettings, Presenter, Project, ProjectMember, ShowDay, ShowflowEvent, ShowflowImport,
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
            'a2_count': 2, 'mic_min': 4, 'demic_min': 2, 'premic_lead_min': 45, 'margin_min': 10})
        self.assertEqual(302, resp.status_code)
        s = MicPlanSettings.objects.get(project=self.project)
        self.assertEqual((2, 4, 2, 45, 10), (s.a2_count, s.mic_min, s.demic_min, s.premic_lead_min,
                                             s.margin_min))
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
            (reverse('planner:mic_plan_person', args=[person.pk]), {'mic_hint': 'HH'}),
            (reverse('planner:mic_plan_merge', args=[person.pk]), {'into': into.pk}),
            (reverse('planner:mic_plan_unalias', args=[person.pk]), {'alias': 'x'}),
            (reverse('planner:mic_plan_settings'), {'a2_count': 3}),
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
        for url, data in self.writes()[1:-1]:
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
                self.assertEqual('Mic Plan', str(row['name']))
                self.assertEqual(reverse('planner:mic_plan'), row['admin_url'])
                self.assertIsNone(row['add_url'])

    def test_admin_list_redirects_to_the_page(self):
        self.use(self.owner)
        resp = self.client.get(reverse('admin:planner_showflowimport_changelist'))
        self.assertRedirects(resp, reverse('planner:mic_plan'), fetch_redirect_response=False)
        self.assertIn(ShowflowImport, showstack_admin_site._registry)


class ReviewPageTests(MicPlanBase):
    """The review page: who's on stage, people, crew only with cues."""

    def setUp(self):
        super().setUp()
        self.use(self.owner)

    def page(self):
        return self.client.get(reverse('planner:mic_plan'))

    def test_who_is_on_stage_lists_segments_with_their_people_and_cues(self):
        self.upload()
        resp = self.page()
        self.assertContains(resp, "Who's on stage")
        segments = resp.context['segments']
        names = [s.name for s in segments]
        self.assertIn('Keynote Conversation', names)
        keynote = next(s for s in segments if s.name == 'Keynote')
        on = {a.person.display_name: a for a in keynote.people}
        self.assertTrue(on['Kim Keynote'].by_cue)             # sent 113, caught 115
        self.assertEqual(('113', '115'), (on['Kim Keynote'].on_line, on['Kim Keynote'].off_line))
        self.assertContains(resp, 'id="mp-crew"')             # this file has cues
        opening = next(s for s in segments if s.name == 'Opening')
        on = {a.person.display_name: a for a in opening.people}
        # Sent and caught on line 106, inside Opening: shown there, not in the next segment.
        self.assertEqual(('106', '106', True), (on['Pat Guest'].on_line, on['Pat Guest'].off_line,
                                                on['Pat Guest'].by_cue))
        self.assertNotIn('Chris Baker', on)                    # sent on 108 for the next segment
        nxt = next(s for s in segments if s.name == 'Building the Future')
        self.assertNotIn('Pat Guest', [a.person.display_name for a in nxt.people])

    def test_a_cue_free_file_says_so_and_has_no_crew_panel(self):
        self.upload()                                          # the project now has crew names
        day2 = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        self.upload('CLIENT_E_PAGES', day=day2)
        self.assertTrue(ShowflowImport.objects.get(day=day2).crew_names)   # copied, yet no cues
        resp = self.client.get(reverse('planner:mic_plan') + '?day={}'.format(day2.pk))
        self.assertContains(resp, 'No send/catch cues in this showflow — on/off times come from '
                                  'segment times.')
        self.assertNotContains(resp, 'id="mp-crew"')
        opening = resp.context['segments'][0]
        self.assertEqual('Opening Session', opening.name)
        vic = next(a for a in opening.people if a.person.display_name == 'Vic Stone')
        self.assertFalse(vic.by_cue)
        self.assertEqual(('304', '305', '8:00a', '8:45a'),
                         (vic.on_line, vic.off_line, vic.on_time, vic.off_time))
        self.assertContains(resp, "intro'd line 304")
        self.assertEqual(['BREAK'], [s.name for s in resp.context['segments'] if s.is_break])

    def test_flags_sit_at_their_line_in_plain_language(self):
        self.upload('CLIENT_E_PAGES')
        segments = self.page().context['segments']
        flags = [(s.name, i.line, i.text) for s in segments for i in s.items if not hasattr(i, 'person')]
        self.assertIn(('Opening Session', '311', 'Line 311: description names people not in the '
                       'Speaker column — check who goes on'), flags)
        self.assertTrue(any(line == '319' and text.startswith('Line 319: which Vic?')
                            for _, line, text in flags))

    def test_intro_rows_are_stored_per_part(self):
        self.upload('CLIENT_E_PAGES')
        part = self.parts()[0]
        row = ShowflowRow.objects.get(showflow_import=part,
                                      order=self.person('Dr. Una Reyes').flags['intro'][str(part.pk)])
        self.assertEqual('306', row.line_no)

    def test_settings_are_not_on_this_page(self):
        self.upload()
        resp = self.page()
        self.assertNotContains(resp, reverse('planner:mic_plan_settings'))
        self.assertNotContains(resp, 'premic_lead_min')

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
