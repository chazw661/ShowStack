"""Per-module templates, PR 1: ShowTemplate + console.

Covers:

* tenant isolation of "My templates" -- user A cannot list, load, rename or
  delete user B's template; a superuser can (the support exception);
* saving a console copies EVERY field, including the ones the old library
  import dropped (source_b, source_hardware(_b), color, default_record,
  stereo outputs, location);
* loading always adds: collisions are previewed with suggested renames,
  applied in one transaction, and never delete or overwrite;
* the migrate_console_templates command: dry-run by default, never removes
  a console from its project;
* the field-mirror guard: a Console* field with no Template* twin fails here.

Run with::

    python manage.py test planner.tests.test_show_templates \\
        --settings=audiopatch.test_settings
"""

from io import StringIO

from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from planner.models import (
    Console, ConsoleAuxOutput, ConsoleInput, ConsoleMatrixOutput,
    ConsoleStereoOutput, Location, Project, ProjectMember, ShowTemplate,
    TemplateConsole, UserProfile,
)
from planner.show_templates import (
    CONSOLE_CHILDREN, LoadConflict, apply_load, console_fields, copied_fields,
    preview_load, save_console_template,
)
from planner.tenancy import owned_templates
from planner.tests.test_tenant_isolation import TenantIsolationBase

LIBRARY_URL = '/admin/planner/console/template-library/'


def _client_for(user, project):
    c = Client()
    c.force_login(user)
    s = c.session
    s['current_project_id'] = project.id
    s.save()
    return c


def _full_console(project, name='FOH Desk', location=None):
    """A console with a non-default value in every field of every child."""
    console = Console.objects.create(
        project=project, name=name, location=location,
        primary_ip_address='10.0.0.10', secondary_ip_address='10.0.1.10',
    )
    ConsoleInput.objects.create(
        console=console, dante_number='1', input_ch='1', source='Kick In',
        source_b='Kick Spare', source_hardware='Shure - B91',
        source_hardware_b='Shure - B52', color='Red', default_record=False,
        group='Drums', dca='1', mute='M1', direct_out='DO1', omni_in='OMNI 1',
    )
    ConsoleInput.objects.create(console=console, input_ch='2', source='Snare')
    ConsoleAuxOutput.objects.create(
        console=console, dante_number=33, aux_number='1', name='Wedge 1',
        mono_stereo='Mono', bus_type='Fixed', omni_in='OI1', omni_out='OO1',
        color='Yellow', default_record=False,
    )
    ConsoleMatrixOutput.objects.create(
        console=console, dante_number=49, matrix_number='1', name='Delay',
        mono_stereo='Stereo', destination='Delay Tower', omni_out='OO9',
        color='Green', default_record=False,
    )
    ConsoleStereoOutput.objects.create(
        console=console, stereo_type='L', name='Main L', dante_number=60,
        omni_out='OO15', color='Purple', default_record=False,
    )
    return console


def _rows(console):
    """Every copied value of a live console, children in id order."""
    out = {'console': {f: getattr(console, f) for f in console_fields()},
           'location': console.location.name if console.location_id else ''}
    for live, _, accessor, _, _ in CONSOLE_CHILDREN:
        fields = copied_fields(live)
        out[accessor] = [
            {f: getattr(r, f) for f in fields}
            for r in getattr(console, accessor).order_by('id')
        ]
    return out


# ---------------------------------------------------------------------------
# The mirror guard
# ---------------------------------------------------------------------------

class FieldMirrorTests(TestCase):

    def test_every_console_child_field_has_a_template_mirror(self):
        for live, mirror, *_ in CONSOLE_CHILDREN:
            mirror_fields = {f.name for f in mirror._meta.concrete_fields}
            missing = set(copied_fields(live)) - mirror_fields
            self.assertEqual(
                set(), missing,
                f"{live.__name__} has field(s) {sorted(missing)} with no twin on "
                f"{mirror.__name__}; templates would silently drop them. Add "
                "the field to the mirror model (and a migration).",
            )

    def test_every_console_field_has_a_template_mirror(self):
        mirror_fields = {f.name for f in TemplateConsole._meta.concrete_fields}
        self.assertEqual(set(), set(console_fields()) - mirror_fields)


# ---------------------------------------------------------------------------
# owned_templates()
# ---------------------------------------------------------------------------

class OwnedTemplatesTests(TestCase):

    def setUp(self):
        self.a = User.objects.create_user('ot_a', password='pw')
        self.b = User.objects.create_user('ot_b', password='pw')
        self.su = User.objects.create_superuser('ot_su', 'su@x.com', 'pw')
        self.ta = ShowTemplate.objects.create(owner=self.a, kind='console', name='A')
        self.tb = ShowTemplate.objects.create(owner=self.b, kind='console', name='B')

    def _ids(self, user):
        request = RequestFactory().get('/')
        request.user = user
        return set(owned_templates(request, ShowTemplate.objects.all())
                   .values_list('id', flat=True))

    def test_anonymous_sees_nothing(self):
        self.assertEqual(set(), self._ids(AnonymousUser()))

    def test_user_sees_only_own(self):
        self.assertEqual({self.ta.id}, self._ids(self.a))

    def test_superuser_sees_all(self):
        self.assertEqual({self.ta.id, self.tb.id}, self._ids(self.su))


# ---------------------------------------------------------------------------
# Isolation of "My templates"
# ---------------------------------------------------------------------------

class MyTemplatesIsolationTests(TenantIsolationBase):

    def setUp(self):
        super().setUp()
        self.template_a = save_console_template(self.console_a, self.user_a, 'A Tmpl')
        self.template_b = save_console_template(
            self.console_b, self.user_b, f'B Tmpl {self.MARKER_B}')
        self.changelist = reverse('admin:planner_showtemplate_changelist')

    def change_url(self, t):
        return reverse('admin:planner_showtemplate_change', args=[t.pk])

    def delete_url(self, t):
        return reverse('admin:planner_showtemplate_delete', args=[t.pk])

    # list
    def test_user_a_cannot_list_user_b_template(self):
        resp = self.client.get(self.changelist)
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, 'A Tmpl')
        self.assertNoLeak(resp, 'My templates changelist')

    def test_user_a_library_does_not_list_user_b_template(self):
        resp = self.client.get(LIBRARY_URL)
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, 'A Tmpl')
        self.assertNoLeak(resp, 'console template library')

    # load
    def test_user_a_cannot_load_user_b_template(self):
        before = Console.objects.filter(project=self.project_a).count()
        for action in ('preview', 'apply'):
            resp = self.client.post(
                LIBRARY_URL, {'template_id': self.template_b.id, 'action': action})
            self.assertEqual(302, resp.status_code, action)
        self.assertEqual(before, Console.objects.filter(project=self.project_a).count())

    # rename
    def test_user_a_cannot_view_or_rename_user_b_template(self):
        resp = self.client.get(self.change_url(self.template_b))
        self.assertNotEqual(200, resp.status_code)
        resp = self.client.post(self.change_url(self.template_b), {'name': 'pwned', 'notes': ''})
        self.assertNotEqual(200, resp.status_code)
        self.template_b.refresh_from_db()
        self.assertEqual(f'B Tmpl {self.MARKER_B}', self.template_b.name)

    # delete
    def test_user_a_cannot_delete_user_b_template(self):
        self.client.post(self.delete_url(self.template_b), {'post': 'yes'})
        self.assertTrue(ShowTemplate.objects.filter(pk=self.template_b.pk).exists())

    # the owner can do all of it to their own
    def test_owner_can_rename_and_delete_own(self):
        resp = self.client.get(self.change_url(self.template_a))
        self.assertContains(resp, '1 console · 1 in · 0 aux · 0 mtx · 0 st')
        resp = self.client.post(self.change_url(self.template_a), {'name': 'Renamed', 'notes': 'n'})
        self.assertEqual(302, resp.status_code)
        self.template_a.refresh_from_db()
        self.assertEqual('Renamed', self.template_a.name)
        self.client.post(self.delete_url(self.template_a), {'post': 'yes'})
        self.assertFalse(ShowTemplate.objects.filter(pk=self.template_a.pk).exists())

    def test_rename_onto_own_existing_name_is_a_form_error_not_a_500(self):
        other = save_console_template(self.console_a, self.user_a, 'Other')
        resp = self.client.post(self.change_url(other), {'name': 'A Tmpl', 'notes': ''})
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, 'already have a console template')
        other.refresh_from_db()
        self.assertEqual('Other', other.name)

    def test_cannot_add_an_empty_template_from_the_admin(self):
        resp = self.client.get(reverse('admin:planner_showtemplate_add'))
        self.assertEqual(403, resp.status_code)

    # superuser exception
    def test_superuser_can_list_load_rename_and_delete_any_template(self):
        su = _client_for(self.superuser, self.project_a)
        self.assertContains(su.get(self.changelist), self.MARKER_B)
        self.assertContains(su.get(LIBRARY_URL), self.MARKER_B)

        su.post(LIBRARY_URL, {'template_id': self.template_b.id, 'action': 'apply'})
        self.assertTrue(Console.objects.filter(
            project=self.project_a, name__contains=self.MARKER_B).exists())

        su.post(self.change_url(self.template_b), {'name': 'Support rename', 'notes': ''})
        self.template_b.refresh_from_db()
        self.assertEqual('Support rename', self.template_b.name)

        su.post(self.delete_url(self.template_b), {'post': 'yes'})
        self.assertFalse(ShowTemplate.objects.filter(pk=self.template_b.pk).exists())


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

class SaveActionTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('save_owner', password='pw', is_staff=True)
        UserProfile.objects.update_or_create(user=self.owner, defaults={'account_type': 'paid'})
        self.project = Project.objects.create(name='Tour', owner=self.owner)
        self.loc = Location.objects.create(project=self.project, name='FOH')
        self.console = _full_console(self.project, location=self.loc)
        self.client = _client_for(self.owner, self.project)
        self.url = reverse('admin:planner_console_changelist')

    def _run(self, ids):
        return self.client.post(self.url, {
            'action': 'save_as_template', '_selected_action': ids,
        })

    def test_saves_full_field_set_and_leaves_console_alone(self):
        before = _rows(self.console)
        self._run([self.console.id])
        tmpl = ShowTemplate.objects.get(owner=self.owner)
        self.assertEqual(('console', 'FOH Desk', self.project.id, 1),
                         (tmpl.kind, tmpl.name, tmpl.source_project_id, tmpl.payload_version))

        tc = tmpl.consoles.get()
        self.assertEqual('FOH', tc.location_name)
        self.assertEqual(before['console'], {f: getattr(tc, f) for f in console_fields()})
        for live, _, accessor, related, _ in CONSOLE_CHILDREN:
            fields = copied_fields(live)
            self.assertEqual(
                before[accessor],
                [{f: getattr(r, f) for f in fields} for r in getattr(tc, related).all()],
                related,
            )
        self.console.refresh_from_db()
        self.assertEqual(before, _rows(self.console))

    def test_requires_exactly_one_console(self):
        second = Console.objects.create(project=self.project, name='MON')
        self._run([self.console.id, second.id])
        self.assertFalse(ShowTemplate.objects.exists())

    def test_name_clash_gets_project_suffix_then_number(self):
        self._run([self.console.id])
        self._run([self.console.id])
        self._run([self.console.id])
        self.assertEqual(
            ['FOH Desk', 'FOH Desk (Tour)', 'FOH Desk (Tour) (2)'],
            sorted(ShowTemplate.objects.values_list('name', flat=True)),
        )

    def test_template_is_owned_by_the_saver_not_the_project_owner(self):
        editor = User.objects.create_user('save_editor', password='pw', is_staff=True)
        ProjectMember.objects.create(project=self.project, user=editor, role='editor',
                                     invited_by=self.owner)
        c = _client_for(editor, self.project)
        c.post(self.url, {'action': 'save_as_template',
                          '_selected_action': [self.console.id]})
        self.assertEqual(editor, ShowTemplate.objects.get().owner)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

class LoadTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('load_owner', password='pw', is_staff=True)
        UserProfile.objects.update_or_create(user=self.owner, defaults={'account_type': 'paid'})
        src_project = Project.objects.create(name='Source', owner=self.owner)
        self.src = _full_console(
            src_project, location=Location.objects.create(project=src_project, name='FOH'))
        self.template = save_console_template(self.src, self.owner, 'Corporate')
        self.tc = self.template.consoles.get()
        self.target = Project.objects.create(name='Target', owner=self.owner)
        self.client = _client_for(self.owner, self.target)

    def test_load_copies_full_field_set_and_creates_location(self):
        [console] = apply_load(self.template, self.target)
        src, copy = _rows(self.src), _rows(console)
        self.assertEqual(src, copy)
        self.assertEqual(self.target, console.location.project)
        self.assertFalse(console.is_template)

    def test_load_reuses_existing_location_by_name(self):
        loc = Location.objects.create(project=self.target, name='FOH')
        [console] = apply_load(self.template, self.target)
        self.assertEqual(loc, console.location)
        self.assertEqual(1, Location.objects.filter(project=self.target).count())

    def test_load_tolerates_duplicate_location_names(self):
        Location.objects.create(project=self.target, name='FOH', sort_order=2)
        first = Location.objects.create(project=self.target, name='FOH', sort_order=1)
        [console] = apply_load(self.template, self.target)
        self.assertEqual(first, console.location)

    def test_preview_reports_collision_with_suggestion(self):
        Console.objects.create(project=self.target, name='FOH Desk')
        Console.objects.create(project=self.target, name='FOH Desk (2)')
        [item] = preview_load(self.template, self.target)
        self.assertTrue(item['collides'])
        self.assertEqual('FOH Desk (3)', item['suggested'])
        self.assertEqual({'inputs': 2, 'auxes': 1, 'matrices': 1, 'stereos': 1},
                         item['counts'])
        self.assertFalse(item['location_exists'])

    def test_suggestions_avoid_each_other(self):
        TemplateConsole.objects.create(template=self.template, name='FOH Desk')
        Console.objects.create(project=self.target, name='FOH Desk')
        plan = preview_load(self.template, self.target)
        self.assertEqual(['FOH Desk (2)', 'FOH Desk (3)'], [p['suggested'] for p in plan])
        created = apply_load(self.template, self.target,
                             {p['id']: p['suggested'] for p in plan})
        self.assertEqual(['FOH Desk (2)', 'FOH Desk (3)'], [c.name for c in created])

    def test_apply_refuses_a_colliding_name_and_writes_nothing(self):
        existing = Console.objects.create(project=self.target, name='FOH Desk')
        ConsoleInput.objects.create(console=existing, input_ch='1', source='Keep me')
        with self.assertRaises(LoadConflict) as ctx:
            apply_load(self.template, self.target)
        self.assertIn(self.tc.id, ctx.exception.errors)
        self.assertEqual(1, Console.objects.filter(project=self.target).count())
        self.assertEqual(0, Location.objects.filter(project=self.target).count())
        self.assertEqual(['Keep me'], list(
            existing.consoleinput_set.values_list('source', flat=True)))

    def test_apply_with_rename_adds_and_never_touches_existing(self):
        existing = Console.objects.create(project=self.target, name='FOH Desk')
        ConsoleInput.objects.create(console=existing, input_ch='1', source='Keep me')
        [new] = apply_load(self.template, self.target, {self.tc.id: 'FOH Desk B'})
        self.assertEqual('FOH Desk B', new.name)
        self.assertEqual(2, Console.objects.filter(project=self.target).count())
        self.assertEqual(['Keep me'], list(
            existing.consoleinput_set.values_list('source', flat=True)))

    def test_loading_twice_adds_twice(self):
        apply_load(self.template, self.target)
        apply_load(self.template, self.target, {self.tc.id: 'FOH Desk 2'})
        self.assertEqual(2, Console.objects.filter(project=self.target).count())
        self.assertEqual(4, ConsoleInput.objects.filter(console__project=self.target).count())

    # through the view
    def test_view_preview_then_apply(self):
        Console.objects.create(project=self.target, name='FOH Desk')
        resp = self.client.post(LIBRARY_URL, {'template_id': self.template.id,
                                              'action': 'preview'})
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, 'value="FOH Desk (2)"')
        self.assertEqual(1, Console.objects.filter(project=self.target).count())

        resp = self.client.post(LIBRARY_URL, {
            'template_id': self.template.id, 'action': 'apply',
            f'name_{self.tc.id}': 'FOH Desk (2)',
        })
        new = Console.objects.get(project=self.target, name='FOH Desk (2)')
        self.assertRedirects(resp, reverse('admin:planner_console_change', args=[new.pk]),
                             fetch_redirect_response=False)

    def test_view_apply_with_collision_reshows_preview(self):
        Console.objects.create(project=self.target, name='FOH Desk')
        resp = self.client.post(LIBRARY_URL, {
            'template_id': self.template.id, 'action': 'apply',
            f'name_{self.tc.id}': 'FOH Desk',
        })
        self.assertEqual(200, resp.status_code)
        self.assertContains(resp, 'already exists in this project')
        self.assertEqual(1, Console.objects.filter(project=self.target).count())


# ---------------------------------------------------------------------------
# migrate_console_templates
# ---------------------------------------------------------------------------

class MigrateConsoleTemplatesTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user('mig_owner', password='pw')
        self.p1 = Project.objects.create(name='Tour 2025', owner=self.owner)
        self.p2 = Project.objects.create(name='Gala', owner=self.owner)
        self.live = _full_console(
            self.p1, name='PM10',
            location=Location.objects.create(project=self.p1, name='FOH'))
        self.live.is_template = True
        self.live.save()
        self.other = Console.objects.create(project=self.p2, name='PM10', is_template=True)
        self.plain = Console.objects.create(project=self.p2, name='Not a template')

    def run_cmd(self, *args):
        out = StringIO()
        call_command('migrate_console_templates', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        out = self.run_cmd()
        self.assertIn('DRY RUN', out)
        self.assertIn("template 'PM10 (Gala)'", out)
        self.assertFalse(ShowTemplate.objects.exists())
        self.assertEqual(2, Console.objects.filter(is_template=True).count())

    def test_apply_copies_and_clears_flag_but_keeps_consoles(self):
        before = _rows(self.live)
        self.run_cmd('--apply')

        self.assertEqual(
            ['PM10', 'PM10 (Gala)'],
            sorted(ShowTemplate.objects.filter(owner=self.owner).values_list('name', flat=True)),
        )
        # Never removed from the project, and otherwise untouched.
        self.live.refresh_from_db()
        self.assertEqual(self.p1, self.live.project)
        self.assertFalse(self.live.is_template)
        self.assertEqual(before, _rows(self.live))
        self.assertEqual(3, Console.objects.count())

        tmpl = ShowTemplate.objects.get(name='PM10')
        self.assertEqual(self.p1, tmpl.source_project)
        [copy] = apply_load(tmpl, Project.objects.create(name='New', owner=self.owner))
        self.assertEqual(before, _rows(copy))

    def test_existing_template_name_gets_project_suffix(self):
        ShowTemplate.objects.create(owner=self.owner, kind='console', name='PM10')
        self.run_cmd('--apply')
        self.assertEqual(
            ['PM10', 'PM10 (Gala)', 'PM10 (Tour 2025)'],
            sorted(ShowTemplate.objects.values_list('name', flat=True)),
        )

    def test_rerun_is_a_no_op(self):
        self.run_cmd('--apply')
        self.run_cmd('--apply')
        self.assertEqual(2, ShowTemplate.objects.count())

    def test_console_without_project_is_skipped(self):
        orphan = Console.objects.create(project=None, name='Orphan', is_template=True)
        out = self.run_cmd('--apply')
        self.assertIn('SKIP', out)
        orphan.refresh_from_db()
        self.assertTrue(orphan.is_template)
