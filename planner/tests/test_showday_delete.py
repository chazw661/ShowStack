"""Deleting a ShowDay that has Mic Plan data, through the admin.

The admin's delete confirmation asks every registered model's admin about each
cascaded object, and ShowflowImportAdmin used to refuse flatly, so no owner or
editor could delete a day with an import. Made-up names.

Run with::

    python manage.py test planner.tests.test_showday_delete --settings=audiopatch.test_settings
"""

from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from planner.mic_plan import push
from planner.models import (
    MicAssignment, MicPlan, MicPlanA2Action, MicPlanAppearance, MicPlanAssignment, MicPlanEdit, MicPlanPush,
    MicSession, Presenter, PresenterSlot, ShowDay, ShowflowEvent, ShowflowImport, ShowflowPerson, ShowflowRow,
)
from planner.tests.test_mic_plan_edits import EditBase


def left(day_pk):
    """How many rows of each Mic Plan / Mic Tracker model still belong to the day."""
    return {
        'ShowflowImport': ShowflowImport.objects.filter(day_id=day_pk).count(),
        'ShowflowRow': ShowflowRow.objects.filter(showflow_import__day_id=day_pk).count(),
        'ShowflowPerson': ShowflowPerson.objects.filter(day_id=day_pk).count(),
        'ShowflowEvent': ShowflowEvent.objects.filter(person__day_id=day_pk).count(),
        'MicPlan': MicPlan.objects.filter(day_id=day_pk).count(),
        'MicPlanAppearance': MicPlanAppearance.objects.filter(plan__day_id=day_pk).count(),
        'MicPlanAssignment': MicPlanAssignment.objects.filter(appearance__plan__day_id=day_pk).count(),
        'MicPlanA2Action': MicPlanA2Action.objects.filter(plan__day_id=day_pk).count(),
        'MicPlanEdit': MicPlanEdit.objects.filter(plan__day_id=day_pk).count(),
        'MicPlanPush': MicPlanPush.objects.filter(day_id=day_pk).count(),
        'MicSession': MicSession.objects.filter(day_id=day_pk).count(),
        'MicAssignment': MicAssignment.objects.filter(session__day_id=day_pk).count(),
        'PresenterSlot': PresenterSlot.objects.filter(assignment__session__day_id=day_pk).count(),
    }


class ShowDayDeleteTests(EditBase):
    """The real fixture, generated, edited once and sent to Mic Tracker."""

    def setUp(self):
        super().setUp()                                   # editor: upload + generate
        key = self.key('Kim Keynote')
        self.assertEqual(200, self.edit('move_rf', key, rf=7, pool='body').status_code)
        p = push.preview(self.day)
        resp = self.client.post(reverse('planner:mic_plan_push', args=[self.day.pk]),
                                {'version': p.plan.version, 'digest': p.digest})
        self.assertEqual(302, resp.status_code)
        self.before = left(self.day.pk)
        self.assertTrue(all(self.before.values()), self.before)   # every kind is there to delete
        self.presenters = Presenter.objects.filter(project=self.project).count()

    def url(self, day=None):
        return reverse('admin:planner_showday_delete', args=[(day or self.day).pk])

    def assert_deletes(self, user):
        self.use(user)
        page = self.client.get(self.url())
        self.assertEqual(200, page.status_code)
        self.assertFalse(page.context['perms_lacking'])
        self.assertFalse(page.context['protected'])
        # The confirmation lists every kind it will delete, with the same
        # counts as are in the database (keys are verbose_name_plural).
        counts = {str(k): v for k, v in page.context['model_count']}
        for model in (ShowflowImport, ShowflowRow, ShowflowPerson, ShowflowEvent, MicPlan, MicPlanAppearance,
                      MicPlanAssignment, MicPlanA2Action, MicPlanEdit, MicPlanPush, MicSession, MicAssignment,
                      PresenterSlot):
            self.assertEqual(self.before[model.__name__], counts.get(str(model._meta.verbose_name_plural)),
                             model.__name__)
        self.assertContains(page, 'Mic Plan push: ')
        self.assertContains(page, 'Showflow import: ')

        pk = self.day.pk
        resp = self.client.post(self.url(), {'post': 'yes'})
        self.assertEqual(302, resp.status_code)
        self.assertFalse(ShowDay.objects.filter(pk=pk).exists())
        self.assertEqual({k: 0 for k in self.before}, left(pk))
        # Presenters belong to the project, not the day, and stay.
        self.assertEqual(self.presenters, Presenter.objects.filter(project=self.project).count())

    def test_owner_can_delete_a_day_with_mic_plan_data(self):
        self.assert_deletes(self.owner)

    def test_editor_can_delete_a_day_with_mic_plan_data(self):
        self.assert_deletes(self.editor)

    def test_viewer_cannot(self):
        self.use(self.viewer)
        self.assertEqual(403, self.client.get(self.url()).status_code)
        self.assertEqual(403, self.client.post(self.url(), {'post': 'yes'}).status_code)
        self.assertEqual(self.before, left(self.day.pk))

    def test_another_projects_day_is_not_found(self):
        self.use(self.other_owner, self.other)               # an owner, but of the other project
        resp = self.client.post(self.url(), {'post': 'yes'})
        # The admin answers an object outside its queryset with its "doesn't
        # exist" redirect, as for any other model; nothing is deleted.
        self.assertRedirects(resp, reverse('admin:index'), fetch_redirect_response=False)
        self.assertEqual(self.before, left(self.day.pk))

    def test_an_import_is_never_deleted_on_its_own_in_the_admin(self):
        self.use(self.owner)
        part = ShowflowImport.objects.filter(day=self.day).first()
        resp = self.client.post(reverse('admin:planner_showflowimport_delete', args=[part.pk]), {'post': 'yes'})
        self.assertRedirects(resp, reverse('planner:mic_plan'), fetch_redirect_response=False)
        self.assertTrue(ShowflowImport.objects.filter(pk=part.pk).exists())


class GroupPermissionTests(TestCase):
    """setup_user_groups covers every Mic Plan model and can run again."""

    MODELS = ['showflowimport', 'showflowrow', 'showflowperson', 'showflowevent', 'micplansettings', 'micplan',
              'micplanappearance', 'micplanassignment', 'micplanedit', 'micplana2action', 'micplanpush']

    def test_editor_gets_full_rights_and_viewer_view_only_and_a_rerun_changes_nothing(self):
        call_command('setup_user_groups', stdout=StringIO())
        first = {g: set(Group.objects.get(name=g).permissions.values_list('pk', flat=True))
                 for g in ('Editor', 'Viewer')}
        call_command('setup_user_groups', stdout=StringIO())
        for g, perms in first.items():
            self.assertEqual(perms, set(Group.objects.get(name=g).permissions.values_list('pk', flat=True)))
        editor = set(Group.objects.get(name='Editor').permissions.values_list('codename', flat=True))
        viewer = set(Group.objects.get(name='Viewer').permissions.values_list('codename', flat=True))
        for m in self.MODELS:
            self.assertLessEqual({f'{a}_{m}' for a in ('add', 'change', 'delete', 'view')}, editor, m)
            self.assertIn(f'view_{m}', viewer)
            self.assertNotIn(f'delete_{m}', viewer)
