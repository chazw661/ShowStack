"""The pages test_write_endpoint_guard found crashing, and the views.py
functions that were defined twice.

- consoles/<id>/ raised FieldError on every request; it now sends the user
  to the console's admin change page.
- The COMM matrix and COMM export read belt pack fields (channel_a..d) that
  were replaced by CommBeltPackChannel rows, and read every project's packs.
- The mobile COMM list read the same fields; its channel badges never showed.
- Five views.py functions had two definitions; the second one is what ran.
  For dmic_and_rotate and get_assignment_details the first, never-run copy
  was the newer, working one. Methods defined twice in admin.py classes
  lost their dead copies too (the live, last ones are kept).
- /audiopatch/checklist/ rendered a template that does not exist; the
  route is gone (its URL name already pointed at audiochecklist/).
- admin.py's module level had a dead PAFanOutInline copy and three unused
  has_module_permission functions.
- A power plan made in the admin now records created_by, as a generated
  one already did.

Run with::

    python manage.py test planner.tests.test_crash_fixes \\
        --settings=audiopatch.test_settings
"""

import ast
import csv
import io
import json
from pathlib import Path

from django.contrib.auth.models import User
from django.urls import reverse

from planner.models import (
    CommBeltPack, CommBeltPackChannel, CommChannel, Console, MicAssignment,
    MicSession, Presenter, PresenterSlot, ProjectMember, ShowDay,
)
from planner.tests.test_write_endpoint_guard import WriteGuardBase


class ConsoleDetailTests(WriteGuardBase):

    def test_redirects_to_the_admin_editor(self):
        console = Console.objects.create(project=self.project, name='FOH')
        editor = self.outsider
        ProjectMember.objects.create(project=self.project, user=editor, role='editor',
                                     invited_by=self.owner)
        change = reverse('admin:planner_console_change', args=[console.pk])
        for user in (self.owner, editor, self.viewer):
            self.login(user, self.project)
            resp = self.client.get(f'/audiopatch/consoles/{console.pk}/')
            self.assertRedirects(resp, change, fetch_redirect_response=False)
            self.assertEqual(200, self.client.get(change).status_code)

    def test_other_project_is_404(self):
        console = Console.objects.create(project=self.project, name='FOH')
        self.login(self.outsider, self.theirs)
        self.assertEqual(404, self.client.get(f'/audiopatch/consoles/{console.pk}/').status_code)


class CommPagesBase(WriteGuardBase):

    def setUp(self):
        super().setUp()
        CommBeltPack.objects.all().delete()
        CommChannel.objects.all().delete()
        self.pl = CommChannel.objects.create(project=self.project, channel_number='1',
                                             name='Production', abbreviation='PROD', order=1)
        self.audio = CommChannel.objects.create(project=self.project, channel_number='2',
                                                name='Audio', abbreviation='AUD', order=2)
        self.bp = CommBeltPack.objects.create(project=self.project, bp_number=7,
                                              system_type='WIRELESS')
        self.bp.channels.all().delete()
        CommBeltPackChannel.objects.create(beltpack=self.bp, channel_number=1, channel=self.pl)
        CommBeltPackChannel.objects.create(beltpack=self.bp, channel_number=3, channel=self.audio)
        theirs = CommBeltPack.objects.create(project=self.theirs, bp_number=99,
                                             system_type='WIRELESS')
        theirs.channels.all().delete()


class CommExportTests(CommPagesBase):

    def test_current_project_with_its_channels(self):
        self.login(self.viewer, self.project)
        resp = self.client.get(reverse('planner:export_comm_assignments'))
        self.assertEqual(200, resp.status_code)
        rows = list(csv.reader(io.StringIO(resp.content.decode())))
        header = rows[0]
        self.assertEqual(['CH 1', 'CH 2', 'CH 3'],
                         header[header.index('CH 1'):header.index('Audio PGM')])
        self.assertEqual(2, len(rows))  # the header and this project's one pack
        row = dict(zip(header, rows[1]))
        self.assertEqual('7', row['BP #'])
        self.assertEqual(str(self.pl), row['CH 1'])
        self.assertEqual('', row['CH 2'])
        self.assertEqual(str(self.audio), row['CH 3'])


class CommMatrixTests(CommPagesBase):

    def test_renders_the_key_each_channel_is_on(self):
        self.login(self.viewer, self.project)
        resp = self.client.get(reverse('planner:comm_channel_matrix'))
        self.assertEqual(200, resp.status_code)
        matrix = resp.context['matrix']
        self.assertEqual([self.bp], [row['bp'] for row in matrix])
        self.assertEqual(['1', '3'], matrix[0]['channels'])
        self.assertEqual([self.pl, self.audio], list(resp.context['channels']))
        self.assertContains(resp, '<td class="on">3</td>', html=False)

    def test_empty_project(self):
        self.login(self.outsider, self.theirs)
        resp = self.client.get(reverse('planner:comm_channel_matrix'))
        self.assertEqual(200, resp.status_code)
        self.assertEqual([], [row['bp'].project for row in resp.context['matrix']
                              if row['bp'].project != self.theirs])


class MobileCommListTests(CommPagesBase):

    def test_channel_badges(self):
        self.login(self.viewer, self.project)
        resp = self.client.get(f'/m/project/{self.project.pk}/comm/')
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, '<span class="channel-badge">PROD</span>')
        self.assertContains(resp, '<span class="channel-badge">AUD</span>')


class FormerDuplicateViewTests(WriteGuardBase):

    def setUp(self):
        super().setUp()
        day = ShowDay.objects.create(project=self.project, date='2027-06-01')
        session = MicSession.objects.create(day=day, name='Main', num_mics=1)
        self.mic = MicAssignment.objects.filter(session=session).first()
        # The primary presenter is the active slot's (MicAssignment.presenter).
        PresenterSlot.objects.create(
            assignment=self.mic, order=0, is_active=True,
            presenter=Presenter.objects.create(project=self.project, name='Ada'))
        self.mic.shared_presenters.add(Presenter.objects.create(project=self.project, name='Bo'))
        self.login(self.owner, self.project)

    def test_get_assignment_details_answers(self):
        # The copy that ran read assignment.presenter_name, which doesn't
        # exist: every call was a 400 and the shared-presenter dialog failed.
        resp = self.client.get(f'/audiopatch/api/mic/get-assignment/{self.mic.pk}/')
        self.assertEqual(200, resp.status_code)
        data = resp.json()['assignment']
        self.assertEqual('Ada', data['presenter'])
        self.assertEqual(['Bo'], data['shared_presenters'])

    def test_dmic_rotates_to_the_next_presenter(self):
        # The copy that ran rotated when D-MIC was turned OFF and reported
        # rotate_to_next_presenter()'s True/False as the presenter's name.
        resp = self.client.post('/audiopatch/api/mic/dmic-and-rotate/',
                                data=json.dumps({'assignment_id': self.mic.pk}),
                                content_type='application/json')
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_d_mic'])
        self.assertEqual('Ada', data['previous_presenter'])
        self.assertEqual('Bo', data['current_presenter'])
        self.assertEqual('Ada D-MIC → Bo is now active', data['message'])
        self.mic.refresh_from_db()
        self.assertEqual(1, self.mic.active_presenter_index)

    def test_viewer_still_refused(self):
        self.login(self.viewer, self.project)
        resp = self.client.post('/audiopatch/api/mic/dmic-and-rotate/',
                                data=json.dumps({'assignment_id': self.mic.pk}),
                                content_type='application/json')
        self.assertEqual(403, resp.status_code)


class NoDuplicateDefinitionsTests(WriteGuardBase):

    def test_modules_define_each_name_once(self):
        # A second top-level def silently replaces the first; the first one's
        # fixes then never run (dmic_and_rotate, get_assignment_details).
        planner = Path(__file__).resolve().parents[1]
        twice = []
        for name in ('admin.py', 'views.py'):
            seen = set()
            for node in ast.parse((planner / name).read_text()).body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name in seen:
                        twice.append(f'{name} {node.name} (line {node.lineno})')
                    seen.add(node.name)
        self.assertEqual([], twice)

    def test_classes_define_each_method_once(self):
        # Same in a class body: the last def wins. AudioChecklistAdmin's
        # "return False" add/delete never ran, nor did three of
        # PowerDistributionPlanAdmin's four save_models.
        planner = Path(__file__).resolve().parents[1]
        twice = []
        for name in ('admin.py', 'views.py'):
            for cls in ast.walk(ast.parse((planner / name).read_text())):
                if not isinstance(cls, ast.ClassDef):
                    continue
                seen = set()
                for node in cls.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name in seen:
                            twice.append(f'{name} {cls.name}.{node.name} (line {node.lineno})')
                        seen.add(node.name)
        self.assertEqual([], twice)


class DeadChecklistRouteTests(WriteGuardBase):

    def test_only_the_working_checklist_is_routed(self):
        # checklist/ rendered a template that does not exist (a 500). The
        # name it shared already reversed to audiochecklist/.
        self.assertEqual('/audiopatch/audiochecklist/', reverse('planner:audio_checklist'))
        self.assertEqual(404, self.client.get('/audiopatch/checklist/').status_code)


class PowerPlanCreatedByTests(WriteGuardBase):
    """A new plan records who made it, by either path; editing keeps it."""

    def test_admin_create_sets_it_and_an_edit_keeps_it(self):
        from django.test import RequestFactory
        from planner.admin import PowerDistributionPlanAdmin
        from planner.admin_site import showstack_admin_site
        from planner.models import PowerDistributionPlan
        admin = PowerDistributionPlanAdmin(PowerDistributionPlan, showstack_admin_site)
        request = RequestFactory().post('/')
        request.user, request.current_project = self.owner, self.project
        plan = PowerDistributionPlan(venue_name='Hall')
        admin.save_model(request, plan, form=None, change=False)
        plan.refresh_from_db()
        self.assertEqual((self.owner, self.project), (plan.created_by, plan.project))
        editor = User.objects.create_user('pp_editor', is_staff=True)
        request.user = editor
        admin.save_model(request, plan, form=None, change=True)
        plan.refresh_from_db()
        self.assertEqual(self.owner, plan.created_by)

    def test_generate_from_amps_sets_it(self):
        from planner.models import PowerDistributionPlan
        self.login(self.owner, self.project)
        self.client.post(reverse('planner:generate_power_plan'))
        plan = PowerDistributionPlan.objects.get(project=self.project, generated_at__isnull=False)
        self.assertEqual(self.owner, plan.created_by)
