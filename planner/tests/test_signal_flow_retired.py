"""The Signal Flow Diagrammer is retired (step 1 of 2: hidden, data kept).

Its routes 404, nothing links to it, no code refers to the removed views,
templates or vendored JS, the rows survive, and the export command is the one
way left to read them.

Run with::

    python manage.py test planner.tests.test_signal_flow_retired \\
        --settings=audiopatch.test_settings
"""
import json
import re
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management import CommandError
from django.db import connection
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse

from planner.admin_site import showstack_admin_site
from planner.management.commands.export_signal_flow_diagrams import Command as ExportCommand
from planner.models import Project, SignalFlowDiagram

User = get_user_model()

FORMER_PATHS = (
    'signal-flow/', 'signal-flow/create/', 'signal-flow/autocomplete/',
    'signal-flow/label-autocomplete/', 'signal-flow/{id}/', 'signal-flow/{id}/state/',
    'signal-flow/{id}/save/', 'signal-flow/{id}/rename/', 'signal-flow/{id}/delete/',
    'signal-flow/{id}/export.png/',
)
FORMER_NAMES = ('signal_flow_list', 'signal_flow_create', 'signal_flow_autocomplete',
                'signal_flow_label_autocomplete', 'signal_flow_editor', 'signal_flow_state',
                'signal_flow_autosave', 'signal_flow_rename', 'signal_flow_delete',
                'signal_flow_export_png')


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='sfd_owner', email='o@example.com',
                                                  password='x')
        self.project = Project.objects.create(name='retired show', owner=self.user)
        self.diagram = SignalFlowDiagram.objects.create(
            project=self.project, name='Main flow',
            canvas_state={'cells': [{'id': 'a', 'type': 'standard.Rectangle'}]},
            viewport={'zoom': 1.5})
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['current_project_id'] = self.project.pk
        session.save()


class RoutesAreGoneTests(_Base):
    def test_every_former_path_is_404_on_get_and_post(self):
        for path in FORMER_PATHS:
            url = '/audiopatch/' + path.format(id=self.diagram.pk)
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url, method=method.__name__):
                    self.assertEqual(method(url).status_code, 404)

    def test_url_names_no_longer_reverse(self):
        for name in FORMER_NAMES:
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(f'planner:{name}')

    def test_admin_pages_are_gone(self):
        self.assertNotIn(SignalFlowDiagram, showstack_admin_site._registry)
        for url in ('/admin/planner/signalflowdiagram/',
                    f'/admin/planner/signalflowdiagram/{self.diagram.pk}/change/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class NothingLinksToItTests(_Base):
    def test_admin_sidebar_has_no_entry(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        models = [m['object_name'] for app in response.context['app_list']
                  for m in app['models']]
        self.assertNotIn('SignalFlowDiagram', models)
        html = response.content.decode()
        self.assertNotIn('signalflowdiagram', html)
        self.assertNotIn('/audiopatch/signal-flow/', html)
        self.assertNotIn('Diagrammer', html)

    def test_dashboard_has_no_quick_action(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('/audiopatch/signal-flow/', response.content.decode())


class NoCodeRefersToItTests(TestCase):
    """No module, template or script names the removed views, routes,
    templates or vendored libraries. The model stays, so its name may."""

    PATTERN = re.compile(
        r'signal_flow_(list|create|editor|state|autosave|rename|delete|export_png|'
        r'autocomplete|label_autocomplete|viewer_block|instance_port_labels)'
        r'|_get_diagram_for_request|_enrich_nodes|planner/signal_flow/|signal_flow\.css'
        r'|/signal-flow/|joint\.min\.js|html-to-image|jspdf|signalflow-(start|ports-export)',
        re.IGNORECASE)
    ROOTS = ('planner', 'templates', 'accounts', 'marketing', 'audiopatch')
    SUFFIXES = {'.py', '.html', '.js', '.css', '.txt'}

    def test_no_references_remain(self):
        base = Path(settings.BASE_DIR)
        this = Path(__file__).resolve()
        hits = []
        for root in self.ROOTS:
            for path in (base / root).rglob('*'):
                if (path.suffix not in self.SUFFIXES or 'migrations' in path.parts
                        or '__pycache__' in path.parts or path.resolve() == this):
                    continue
                for n, line in enumerate(path.read_text(errors='ignore').splitlines(), 1):
                    if self.PATTERN.search(line):
                        hits.append(f'{path.relative_to(base)}:{n}: {line.strip()[:100]}')
        self.assertEqual(hits, [])

    def test_removed_templates_and_static_files_are_gone(self):
        for name in ('planner/signal_flow/editor.html', 'planner/signal_flow/list.html',
                     'planner/signal_flow/_equipment_picker_modal.html',
                     'help/topics/signalflow-start.html',
                     'help/topics/signalflow-ports-export.html'):
            with self.subTest(template=name):
                with self.assertRaises(TemplateDoesNotExist):
                    get_template(name)
        for name in ('planner/js/signal_flow_editor.js', 'planner/css/signal_flow.css',
                     'planner/js/vendor/joint.min.js', 'planner/js/vendor/html-to-image.min.js',
                     'planner/js/vendor/jspdf.umd.min.js'):
            with self.subTest(static=name):
                self.assertIsNone(finders.find(name))
        self.assertIsNotNone(finders.find('planner/js/vendor/Sortable.min.js'))  # Multitrack's


class DataIsKeptTests(_Base):
    def test_rows_survive_and_still_cascade_with_their_project(self):
        diagram = SignalFlowDiagram.objects.get(pk=self.diagram.pk)
        self.assertEqual(diagram.canvas_state['cells'][0]['id'], 'a')
        self.project.delete()
        self.assertFalse(SignalFlowDiagram.objects.filter(pk=self.diagram.pk).exists())


class ExportCommandTests(_Base):
    def setUp(self):
        super().setUp()
        other_owner = User.objects.create_user(username='other_owner', password='x')
        self.other = Project.objects.create(name='other show', owner=other_owner)
        # Same name in another project; names that slugify alike or to nothing.
        self.twin = SignalFlowDiagram.objects.create(project=self.other, name='Main flow')
        self.slash = SignalFlowDiagram.objects.create(project=self.other, name='Main/flow')
        self.cjk = SignalFlowDiagram.objects.create(project=self.other, name='音響 系統')
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / 'export'

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def run_command(self, *args):
        """Parse ``args`` exactly as ``manage.py`` would. call_command can't be
        used: its own ``stdout=`` keyword is mapped onto the ``--stdout`` flag."""
        out, err = StringIO(), StringIO()
        command = ExportCommand(stdout=out, stderr=err)
        options = command.create_parser('manage.py', 'export_signal_flow_diagrams').parse_args(args)
        command.execute(**vars(options))
        return out.getvalue(), err.getvalue()

    def test_dry_run_counts_per_project_and_owner_and_writes_nothing(self):
        with CaptureQueriesContext(connection) as ctx:
            out, _ = self.run_command('--out-dir', str(self.out))
        self.assertFalse(self.out.exists())
        self.assertRegex(out, rf"project {self.project.pk}\s+'retired show'\s+owner=sfd_owner\s+"
                              r"diagrams=1 ")
        self.assertRegex(out, rf"project {self.other.pk}\s+'other show'\s+owner=other_owner\s+"
                              r"diagrams=3 ")
        self.assertIn('4 diagram(s) in 2 project(s), 2 owner(s).', out)
        self.assertIn('Dry run: nothing written', out)
        self._assert_no_db_writes(ctx)

    def test_apply_writes_one_file_per_diagram_with_every_field(self):
        with CaptureQueriesContext(connection) as ctx:
            self.run_command('--apply', '--out-dir', str(self.out))
        files = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob('*.json'))
        self.assertEqual(files, sorted([
            f'{self.project.pk}/{self.diagram.pk}-main-flow.json',
            f'{self.other.pk}/{self.twin.pk}-main-flow.json',
            f'{self.other.pk}/{self.slash.pk}-mainflow.json',
            f'{self.other.pk}/{self.cjk.pk}-diagram.json',
        ]))
        data = json.loads((self.out / str(self.project.pk) /
                           f'{self.diagram.pk}-main-flow.json').read_text(encoding='utf-8'))
        self.assertEqual(set(data), {'project_id', 'project_name', 'owner', 'diagram_id', 'name',
                                     'created_at', 'updated_at', 'version', 'canvas_state',
                                     'viewport'})
        self.assertEqual((data['project_id'], data['name'], data['owner'], data['viewport']),
                         (self.project.pk, 'Main flow', 'sfd_owner', {'zoom': 1.5}))
        self.assertEqual(data['canvas_state'], self.diagram.canvas_state)
        self.assertEqual(data['updated_at'], self.diagram.updated_at.isoformat())
        cjk = json.loads((self.out / str(self.other.pk) /
                          f'{self.cjk.pk}-diagram.json').read_text(encoding='utf-8'))
        self.assertEqual(cjk['name'], '音響 系統')
        self._assert_no_db_writes(ctx)

    def test_apply_refuses_to_overwrite_without_force(self):
        self.run_command('--apply', '--out-dir', str(self.out))
        with self.assertRaises(CommandError):
            self.run_command('--apply', '--out-dir', str(self.out))
        self.run_command('--apply', '--out-dir', str(self.out), '--force')

    def test_stdout_is_one_json_bundle_and_writes_no_files(self):
        with CaptureQueriesContext(connection) as ctx:
            out, err = self.run_command('--apply', '--stdout', '--out-dir', str(self.out))
        bundle = json.loads(out)
        self.assertEqual(bundle['count'], 4)
        self.assertEqual({d['diagram_id'] for d in bundle['diagrams']},
                         {self.diagram.pk, self.twin.pk, self.slash.pk, self.cjk.pk})
        self.assertIn('4 diagram(s) in 2 project(s)', err)   # the summary is on stderr
        self.assertFalse(self.out.exists())
        self._assert_no_db_writes(ctx)

    def test_stdout_needs_apply(self):
        with self.assertRaises(CommandError):
            self.run_command('--stdout')

    def test_project_narrows_the_export(self):
        out, _ = self.run_command('--apply', '--stdout', '--project', str(self.project.pk))
        self.assertEqual([d['diagram_id'] for d in json.loads(out)['diagrams']],
                         [self.diagram.pk])

    def _assert_no_db_writes(self, ctx):
        writes = [q['sql'] for q in ctx.captured_queries
                  if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writes, [])
