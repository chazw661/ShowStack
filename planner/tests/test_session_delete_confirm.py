"""Typed-name delete confirmations: one Mic Session (admin delete page), and
all of a Show Day's sessions (ShowDayAdmin.delete_sessions_view). Made-up names.

Run with::

    python manage.py test planner.tests.test_session_delete_confirm --settings=audiopatch.test_settings
"""

from datetime import date

from django.test import SimpleTestCase
from django.urls import reverse

from planner.models import MicAssignment, MicSession, PresenterSlot, ShowDay
from planner.tests.test_mic_plan_import import MicPlanBase
from planner.utils.typed_names import loose, same_name


class SameNameTests(SimpleTestCase):

    def test_case_dashes_and_spaces_do_not_count(self):
        name = 'Opening Session (8:00–8:45)'
        for typed in ('Opening Session (8:00-8:45)', 'opening session (8:00 - 8:45)', '  OPENING  session (8:00—8:45) ',
                      'Opening Session (8:00 –8:45)', 'Opening\tSession (8:00-8:45)'):
            self.assertTrue(same_name(typed, name), typed)

    def test_anything_else_does(self):
        name = 'Opening Session (8:00-8:45)'
        for typed in ('Opening Session (8:00-8:46)', 'Opening Session', 'OpeningSession (8:00-8:45)', ''):
            self.assertFalse(same_name(typed, name), typed)
        self.assertFalse(same_name('', ''))                    # an empty name never matches

    def test_loose(self):
        self.assertEqual('gs 1-2', loose(' GS  1 – 2 '))


class SessionDeleteTests(MicPlanBase):

    def setUp(self):
        super().setUp()
        self.session = MicSession.objects.create(day=self.day, name='Opening Session (8:00–8:45)', num_mics=2)
        self.url = reverse('admin:planner_micsession_delete', args=[self.session.pk])

    def post(self, typed):
        return self.client.post(self.url, {'post': 'yes', 'confirm_name': typed})

    def test_the_name_typed_loosely_deletes(self):
        self.use(self.editor)
        page = self.client.get(self.url)
        self.assertContains(page, 'confirm_name')
        self.assertContains(page, 'mtt-copy')
        self.assertEqual(302, self.post('opening session (8:00 - 8:45)').status_code)
        self.assertFalse(MicSession.objects.filter(pk=self.session.pk).exists())

    def test_a_wrong_or_missing_name_deletes_nothing(self):
        self.use(self.editor)
        for typed in ('Opening Session', ''):
            resp = self.post(typed)
            self.assertRedirects(resp, self.url, fetch_redirect_response=False)
            self.assertTrue(MicSession.objects.filter(pk=self.session.pk).exists())
        resp = self.client.post(self.url, {'post': 'yes'})
        self.assertTrue(MicSession.objects.filter(pk=self.session.pk).exists())

    def test_viewer_403(self):
        self.use(self.viewer)
        self.assertEqual(403, self.post(self.session.name).status_code)
        self.assertTrue(MicSession.objects.filter(pk=self.session.pk).exists())


class DeleteAllSessionsTests(MicPlanBase):

    def setUp(self):
        super().setUp()
        self.a = MicSession.objects.create(day=self.day, name='Morning', num_mics=2, order=0)
        self.b = MicSession.objects.create(day=self.day, name='Afternoon', num_mics=3, order=1)
        PresenterSlot.objects.filter(assignment__session=self.a).update(photo_data='data:image/png;base64,AAAA')
        PresenterSlot.objects.create(assignment=self.a.mic_assignments.first(), order=1, is_micd=True)
        self.second = ShowDay.objects.create(project=self.project, date=date(2026, 3, 2))
        self.keep = MicSession.objects.create(day=self.second, name='Morning', num_mics=2)
        self.elsewhere = MicSession.objects.create(day=self.other_day, name='Morning', num_mics=2)
        self.url = reverse('admin:planner_showday_delete_sessions', args=[self.day.pk])

    def test_the_show_day_page_links_to_it(self):
        self.use(self.editor)
        page = self.client.get(reverse('admin:planner_showday_change', args=[self.day.pk]))
        self.assertContains(page, self.url)
        self.assertContains(page, 'Delete all sessions for this day')

    def test_the_page_lists_what_will_go(self):
        self.use(self.editor)
        page = self.client.get(self.url)
        self.assertEqual(200, page.status_code)
        self.assertContains(page, 'Morning')
        self.assertContains(page, 'Afternoon')
        self.assertContains(page, '2026-03-01')
        self.assertContains(page, 'Delete 2 sessions')
        rows = {r['session'].name: r for r in page.context['rows']}
        self.assertEqual((2, 3), (rows['Morning']['rfs'], rows['Afternoon']['rfs']))
        self.assertEqual(1, rows['Morning']['micd'])

    def test_date_or_delete_removes_only_that_days_sessions(self):
        for user, typed in ((self.editor, '2026-03-01'), (self.owner, 'delete')):
            self.a = MicSession.objects.get_or_create(day=self.day, name='Morning', defaults={'num_mics': 1})[0]
            self.use(user)
            resp = self.client.post(self.url, {'confirm': typed})
            self.assertRedirects(resp, reverse('admin:planner_showday_change', args=[self.day.pk]),
                                 fetch_redirect_response=False)
            self.assertFalse(MicSession.objects.filter(day=self.day).exists())
            self.assertFalse(MicAssignment.objects.filter(session__day=self.day).exists())
            self.assertTrue(ShowDay.objects.filter(pk=self.day.pk).exists())
            self.assertTrue(MicSession.objects.filter(pk=self.keep.pk).exists())          # another day
            self.assertTrue(MicSession.objects.filter(pk=self.elsewhere.pk).exists())     # another project

    def test_a_wrong_confirmation_deletes_nothing(self):
        self.use(self.editor)
        for typed in ('', '2026-03-02', 'yes'):
            self.assertEqual(200, self.client.post(self.url, {'confirm': typed}).status_code)
        self.assertEqual(2, MicSession.objects.filter(day=self.day).count())

    def test_viewer_403_and_another_project_not_found(self):
        self.use(self.viewer)
        self.assertEqual(403, self.client.get(self.url).status_code)
        self.assertEqual(403, self.client.post(self.url, {'confirm': 'DELETE'}).status_code)
        page = self.client.get(reverse('admin:planner_showday_change', args=[self.day.pk]))
        self.assertNotContains(page, self.url)
        self.use(self.editor)
        other = reverse('admin:planner_showday_delete_sessions', args=[self.other_day.pk])
        self.assertRedirects(self.client.post(other, {'confirm': 'DELETE'}), reverse('admin:index'),
                             fetch_redirect_response=False)
        self.assertTrue(MicSession.objects.filter(pk=self.elsewhere.pk).exists())
        self.assertEqual(2, MicSession.objects.filter(day=self.day).count())
