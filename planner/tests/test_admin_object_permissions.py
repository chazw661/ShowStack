"""Admin object permissions reach the project through the model's real
relation.

`BaseEquipmentAdmin`'s view and change checks read `obj.project`, but several
admin models reach their project through a parent -- an AmplifierAssignment
through its `distribution_plan` -- so their change views 500ed with
"'AmplifierAssignment' object has no attribute 'project'". The delete check
guarded with hasattr and so denied the owner instead, and the inline viewer
check swallowed the error and let viewers edit a MicSession's assignments.

Run with::

    python manage.py test planner.tests.test_admin_object_permissions \\
        --settings=audiopatch.test_settings
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from planner.admin import (
    CHILD_PROJECT_PATHS, OWNER_SCOPED_PATHS, BaseEquipmentAdmin, MicAssignmentInline,
    project_of,
)
from planner.admin_site import showstack_admin_site
from planner.models import (
    AmplifierAssignment, AmplifierProfile, MicSession, PowerDistributionPlan, Project,
    ProjectMember, ShowDay,
)


class AmplifierAssignmentChangeViewTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pw', is_staff=True)
        self.project = Project.objects.create(name='Show', owner=self.owner)
        profile = AmplifierProfile.objects.create(
            manufacturer='L-Acoustics', model='LA12X', idle_power_watts=240,
            rated_power_watts=1500, peak_power_watts=3000, max_power_watts=12000)
        plan = PowerDistributionPlan.objects.create(project=self.project, venue_name='Hall')
        self.row = AmplifierAssignment.objects.create(
            distribution_plan=plan, amplifier=profile, quantity=2, zone='FOH')
        self.admin = showstack_admin_site._registry[AmplifierAssignment]

    def member(self, name, role):
        user = User.objects.create_user(name, password='pw', is_staff=True)
        ProjectMember.objects.create(user=user, project=self.project, role=role,
                                     invited_by=self.owner)
        return user

    def outsider(self):
        user = User.objects.create_user('out', password='pw', is_staff=True)
        Project.objects.create(name='Theirs', owner=user)
        return user

    def get(self, user, view='change'):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()
        return self.client.get(reverse(f'admin:planner_amplifierassignment_{view}',
                                       args=[self.row.pk]))

    def can(self, user):
        request = RequestFactory().get('/')
        request.user = user
        return (self.admin.has_view_permission(request, self.row),
                self.admin.has_change_permission(request, self.row),
                self.admin.has_delete_permission(request, self.row))

    def test_superuser(self):
        boss = User.objects.create_superuser('boss', 'boss@example.com', 'pw')
        self.assertEqual(200, self.get(boss).status_code)

    def test_owner(self):
        self.assertEqual(200, self.get(self.owner).status_code)
        self.assertEqual(200, self.get(self.owner, 'delete').status_code)
        self.assertEqual((True, True, True), self.can(self.owner))

    def test_editor(self):
        editor = self.member('ed', 'editor')
        self.assertEqual(200, self.get(editor).status_code)
        self.assertEqual((True, True, True), self.can(editor))

    def test_viewer_reads_only(self):
        viewer = self.member('vi', 'viewer')
        self.assertEqual(200, self.get(viewer).status_code)
        self.assertEqual((True, False, False), self.can(viewer))
        self.assertEqual(403, self.get(viewer, 'delete').status_code)

    def test_non_member(self):
        # The middleware will not set another tenant's project as current,
        # so the row is outside the changelist queryset and the admin answers
        # as for a missing object (redirect to the index) -- it does not
        # confirm the row exists. The object check itself also says no.
        outsider = self.outsider()
        response = self.get(outsider)
        self.assertRedirects(response, reverse('admin:index'))
        self.assertEqual((False, False, False), self.can(outsider))


class InlineViewerTests(TestCase):

    def test_viewer_of_a_mic_session_is_a_viewer(self):
        owner = User.objects.create_user('owner', password='pw', is_staff=True)
        project = Project.objects.create(name='Show', owner=owner)
        day = ShowDay.objects.create(project=project, date=date(2026, 10, 8), name='Day 1',
                                     order=0)
        session = MicSession.objects.create(day=day, name='Session', num_mics=2, order=0)
        viewer = User.objects.create_user('vi', password='pw', is_staff=True)
        ProjectMember.objects.create(user=viewer, project=project, role='viewer',
                                     invited_by=owner)
        inline = MicAssignmentInline(MicSession, showstack_admin_site)
        request = RequestFactory().get('/')
        request.user = viewer
        self.assertTrue(inline._user_is_viewer(request, session))
        self.assertFalse(inline.has_change_permission(request, session))
        request.user = owner
        self.assertFalse(inline._user_is_viewer(request, session))


class EveryAdminModelReachesAProjectTests(TestCase):
    """Each model behind BaseEquipmentAdmin has a `project` field, a path in
    CHILD_PROJECT_PATHS that resolves through real relations, or an owner."""

    def test_paths(self):
        for model, model_admin in showstack_admin_site._registry.items():
            if not isinstance(model_admin, BaseEquipmentAdmin):
                continue
            name = model.__name__
            with self.subTest(model=name):
                if name in OWNER_SCOPED_PATHS:
                    model._meta.get_field(OWNER_SCOPED_PATHS[name])
                    continue
                path = CHILD_PROJECT_PATHS.get(name, 'project')
                target = model
                for attr in path.split('__'):
                    target = target._meta.get_field(attr).related_model
                self.assertIs(Project, target, f'{name}: {path}')

    def test_project_of(self):
        owner = User.objects.create_user('owner')
        project = Project.objects.create(name='Show', owner=owner)
        plan = PowerDistributionPlan.objects.create(project=project, venue_name='Hall')
        self.assertEqual(project, project_of(project))
        self.assertEqual(project, project_of(plan))
        self.assertEqual(project, project_of(AmplifierAssignment(distribution_plan=plan)))
        self.assertIsNone(project_of(owner))
