"""Source Hardware options: one shared list -- owners and editors add to it,
only superusers rename, reorder or delete.

SourceHardwareOption has no project or owner: every account's Console page
offers the same list. Owning or editing ANY show used to grant every write
(in the admin and through the Console page's "+ Add new…"), so one customer
could rename or delete another's options. Now an owner or editor of the
CURRENT project may add (a new option goes to the end); renaming, reordering
and deleting are superuser-only. Inputs store the label as text, so editing
the list never changes an existing show. Per-account lists: issue #124.

Run with::

    python manage.py test planner.tests.test_source_hardware_options \\
        --settings=audiopatch.test_settings
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from planner.admin import ADDED_SOURCE_HARDWARE_ORDER
from planner.models import Console, ConsoleInput, Project, ProjectMember, SourceHardwareOption
from planner.tests.test_console_patch_picker import staff


class SourceHardwareOptionTests(TestCase):

    def setUp(self):
        self.owner = staff('owner')
        self.project = Project.objects.create(name='Show A', owner=self.owner)
        self.console = Console.objects.create(project=self.project, name='FOH')
        self.input = ConsoleInput.objects.create(console=self.console, input_ch='1', source='Kick',
                                                 source_hardware='Shure AD2')
        other = Project.objects.create(name='Show B', owner=staff('other'))
        self.editor = staff('editor')
        self.join(self.editor, self.project, 'editor')
        # A viewer here who edits another show: the role HERE decides.
        self.viewer = staff('viewer')
        self.join(self.viewer, self.project, 'viewer')
        self.join(self.viewer, other, 'editor')
        self.root = User.objects.create_superuser('root', 'root@example.com', 'pw')
        # Migration 0174 seeds 'Shure AD2' when the test database is built
        # from migrations; with --settings=audiopatch.test_settings it is not.
        self.option, _ = SourceHardwareOption.objects.get_or_create(
            label='Shure AD2', defaults={'sort_order': 1})

        self.changelist = reverse('admin:planner_sourcehardwareoption_changelist')
        self.add = reverse('admin:planner_sourcehardwareoption_add')
        self.change = reverse('admin:planner_sourcehardwareoption_change', args=[self.option.pk])
        self.delete = reverse('admin:planner_sourcehardwareoption_delete', args=[self.option.pk])
        self.quick_add = reverse('planner:add_source_hardware_option')

    def join(self, user, project, role):
        ProjectMember.objects.create(user=user, project=project, role=role,
                                     invited_by=project.owner)

    def use(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()

    def state(self):
        return list(SourceHardwareOption.objects.order_by('pk').values_list('label', 'sort_order'))

    # -- owner / editor: add yes, edit no -------------------------------------

    def test_owner_and_editor_can_add_in_the_admin_at_the_end_of_the_list(self):
        for user in (self.owner, self.editor):
            with self.subTest(user=user.username):
                self.use(user)
                page = self.client.get(self.changelist)
                self.assertContains(page, f'href="{self.add}"')
                form = self.client.get(self.add)
                self.assertEqual(form.status_code, 200)
                self.assertNotContains(form, 'name="sort_order"')   # no choosing a position
                label = f'{user.username} rack'
                r = self.client.post(self.add, {'label': label, 'sort_order': 0})
                self.assertEqual(r.status_code, 302)
                self.assertEqual(SourceHardwareOption.objects.get(label=label).sort_order,
                                 ADDED_SOURCE_HARDWARE_ORDER)

    def test_owner_and_editor_can_add_from_the_console_page(self):
        for user in (self.owner, self.editor):
            with self.subTest(user=user.username):
                self.use(user)
                r = self.client.post(self.quick_add, {'label': f'{user.username} IEM'})
                self.assertEqual(r.status_code, 200, r.content)
                self.assertEqual(SourceHardwareOption.objects.get(
                    label=f'{user.username} IEM').sort_order, 9999)
                page = self.client.get(reverse('admin:planner_console_change', args=[self.console.pk]))
                self.assertContains(page, 'value="__add_new__"')

    def test_owner_and_editor_cannot_rename_reorder_or_delete(self):
        for user in (self.owner, self.editor):
            with self.subTest(user=user.username):
                self.use(user)
                before = self.state()
                page = self.client.get(self.changelist)
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, 'name="form-0-sort_order"')   # no list_editable
                self.assertEqual(self.client.get(self.change).status_code, 200)   # view only
                self.assertEqual(self.client.post(
                    self.change, {'label': 'HACKED', 'sort_order': 5}).status_code, 403)
                self.assertEqual(self.client.post(self.changelist, {
                    'form-TOTAL_FORMS': 1, 'form-INITIAL_FORMS': 1, 'form-0-id': self.option.pk,
                    'form-0-sort_order': 99, '_save': 'Save'}).status_code, 403)
                self.assertEqual(self.client.post(self.delete, {'post': 'yes'}).status_code, 403)
                self.assertEqual(self.state(), before)

    # -- viewer: nothing -------------------------------------------------------

    def test_viewer_cannot_add_even_if_editor_elsewhere(self):
        self.use(self.viewer)
        before = self.state()
        self.assertEqual(self.client.get(self.changelist).status_code, 200)
        self.assertEqual(self.client.get(self.add).status_code, 403)
        self.assertEqual(self.client.post(self.add, {'label': 'Mine'}).status_code, 403)
        self.assertEqual(self.client.post(self.quick_add, {'label': 'Mine'}).status_code, 403)
        self.assertEqual(self.client.post(self.delete, {'post': 'yes'}).status_code, 403)
        self.assertEqual(self.state(), before)
        page = self.client.get(reverse('admin:planner_console_change', args=[self.console.pk]))
        self.assertNotContains(page, 'value="__add_new__"')

    # -- superuser: everything -------------------------------------------------

    def test_superuser_can_add_rename_reorder_and_delete(self):
        self.use(self.root)
        self.client.post(self.add, {'label': 'Sennheiser 6000', 'sort_order': 2})
        added = SourceHardwareOption.objects.get(label='Sennheiser 6000')
        self.assertEqual(added.sort_order, 2)
        self.client.post(self.change, {'label': 'Shure Axient', 'sort_order': 3})
        self.option.refresh_from_db()
        self.assertEqual((self.option.label, self.option.sort_order), ('Shure Axient', 3))
        self.client.post(self.delete, {'post': 'yes'})
        self.assertFalse(SourceHardwareOption.objects.filter(pk=self.option.pk).exists())
        self.assertTrue(SourceHardwareOption.objects.filter(pk=added.pk).exists())

    # -- existing shows --------------------------------------------------------

    def test_editing_the_list_never_changes_an_existing_show(self):
        """Inputs store the label as text: a rename or delete leaves them be,
        and the Console page still shows the old value."""
        self.use(self.root)
        self.client.post(self.change, {'label': 'Shure Axient', 'sort_order': 1})
        self.assertEqual(ConsoleInput.objects.get(pk=self.input.pk).source_hardware, 'Shure AD2')
        self.client.post(reverse('admin:planner_sourcehardwareoption_delete',
                                 args=[self.option.pk]), {'post': 'yes'})
        self.assertEqual(ConsoleInput.objects.get(pk=self.input.pk).source_hardware, 'Shure AD2')
        self.use(self.owner)
        page = self.client.get(reverse('admin:planner_console_change', args=[self.console.pk]))
        self.assertContains(page, '<option value="Shure AD2" selected>Shure AD2</option>')
