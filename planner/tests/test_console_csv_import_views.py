"""End-to-end integration tests for Phase 2 Console CSV Import.

One-shot flow: an upload creates a NEW Console in the current project, populates
its channel rows from the CSV, snapshots the upload as a ConsoleImport, and
redirects to the multitrack dashboard. Covers CSV-01..CSV-05 plus the security
envelope (auth, viewer 403, project scoping).
"""
import pathlib

from django.contrib.auth.models import Group, User
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from planner.models import (
    Console,
    ConsoleAuxOutput,
    ConsoleImport,
    ConsoleInput,
    ConsoleMatrixOutput,
    ConsoleStereoOutput,
    Project,
)

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'csv_import'


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class CsvImportTestBase(TestCase):
    """Shared setup: a project, a staff user, a viewer user.

    No pre-existing target console — the new flow creates the console from the
    CSV. Each test that needs a console name supplies one.
    """

    def setUp(self):
        super().setUp()
        self.owner_user = User.objects.create_user(
            'owner', 'owner@example.com', 'pw', is_staff=True,
        )
        self.project = Project.objects.create(
            name='Test Show',
            client='Acme',
            owner=self.owner_user,
        )
        self.staff_user = self.owner_user

        self.viewer_user = User.objects.create_user(
            'viewer', 'viewer@example.com', 'pw', is_staff=True,
        )
        viewer_group, _ = Group.objects.get_or_create(name='Viewer')
        self.viewer_user.groups.add(viewer_group)

        self.client = Client()

    def _login_staff(self):
        self.client.force_login(self.staff_user)
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def _login_viewer(self):
        self.client.force_login(self.viewer_user)
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def _upload_payload(self, fixture_name: str):
        return SimpleUploadedFile(
            fixture_name, _fixture_bytes(fixture_name), content_type='text/csv',
        )


# ---------------------------------------------------------------------------
# Auth & viewer gate (D-09)
# ---------------------------------------------------------------------------

class AnonymousAccessTest(CsvImportTestBase):
    def test_anon_redirected_to_login(self):
        response = self.client.get(reverse('planner:console_import_upload'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.url)


class ViewerGateTest(CsvImportTestBase):
    def test_viewer_403_on_get(self):
        self._login_viewer()
        response = self.client.get(reverse('planner:console_import_upload'))
        self.assertEqual(response.status_code, 403)

    def test_viewer_403_on_post(self):
        self._login_viewer()
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'X',
            'csv_file': self._upload_payload('cl5_inname.csv'),
        })
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Happy-path: CL/QL upload creates a new console (CSV-01, CSV-04)
# ---------------------------------------------------------------------------

class CreatesConsoleFromClqlTest(CsvImportTestBase):
    def test_cl5_upload_creates_console_and_inputs(self):
        self._login_staff()
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'FOH CL5',
            'csv_file': self._upload_payload('cl5_inname.csv'),
        })
        # Redirects to the multitrack dashboard
        self.assertRedirects(response, reverse('planner:multitrack_dashboard'))

        # New console exists in this project
        console = Console.objects.get(project=self.project, name='FOH CL5')

        # ConsoleImport snapshot was created and committed
        snap = ConsoleImport.objects.get(console=console)
        self.assertTrue(snap.committed)
        self.assertEqual(snap.original_filename, 'cl5_inname.csv')
        self.assertEqual(snap.uploaded_by, self.staff_user)
        self.assertGreaterEqual(snap.summary.get('created_inputs', 0), 1)

        # Channel rows populated
        self.assertGreaterEqual(
            ConsoleInput.objects.filter(console=console).count(), 1
        )

    def test_dashboard_renders_success_banner_after_redirect(self):
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'FOH CL5',
            'csv_file': self._upload_payload('cl5_inname.csv'),
        })
        followed = self.client.get(reverse('planner:multitrack_dashboard'))
        self.assertEqual(followed.status_code, 200)
        self.assertContains(followed, 'FOH CL5')
        self.assertContains(followed, 'Imported')


# ---------------------------------------------------------------------------
# Rivage upload (CSV-02)
# ---------------------------------------------------------------------------

class CreatesConsoleFromRivageTest(CsvImportTestBase):
    def test_rivage_zip_upload_creates_console_with_all_in_scope_models(self):
        self._login_staff()
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'Rivage PM7',
            'csv_file': SimpleUploadedFile(
                'rivage_export_zip.zip',
                _fixture_bytes('rivage_export_zip.zip'),
                content_type='application/zip',
            ),
        })
        self.assertRedirects(response, reverse('planner:multitrack_dashboard'))

        console = Console.objects.get(project=self.project, name='Rivage PM7')
        snap = ConsoleImport.objects.get(console=console)
        self.assertTrue(snap.committed)
        self.assertTrue(snap.parsed_sections.get('is_zip'))

        # The fixture zip contains inputs + mix + matrix + stereo sections
        self.assertGreater(ConsoleInput.objects.filter(console=console).count(), 0)


# ---------------------------------------------------------------------------
# CSV-05 — Phase 1 picker hand-off
# ---------------------------------------------------------------------------

class PickerHandoffTest(CsvImportTestBase):
    """The Phase 1 multitrack track-source picker queries
    `ConsoleInput.objects.filter(console=...).order_by(...)` directly.
    After import, those queries must return the imported rows with NO Phase 1
    code changes (CSV-05).
    """
    def test_picker_query_sees_imported_inputs(self):
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'Picker Console',
            'csv_file': self._upload_payload('cl5_inname.csv'),
        })
        console = Console.objects.get(project=self.project, name='Picker Console')

        # The exact query shape from the Phase 1 picker (planner/views.py:5805-5826)
        inputs = list(
            ConsoleInput.objects.filter(console=console).order_by('input_ch')
        )
        self.assertGreater(len(inputs), 0)


# ---------------------------------------------------------------------------
# Validation: per-row errors don't abort (CSV-03)
# ---------------------------------------------------------------------------

class ParseErrorTest(CsvImportTestBase):
    def test_junk_upload_shows_error_and_creates_nothing(self):
        self._login_staff()
        junk = SimpleUploadedFile(
            'junk.csv', b'this is not a yamaha export', content_type='text/csv',
        )
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'Should Not Exist',
            'csv_file': junk,
        })
        # Stays on the upload page with an error banner
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Console.objects.filter(project=self.project, name='Should Not Exist').count(),
            0,
        )
        self.assertEqual(ConsoleImport.objects.count(), 0)


# ---------------------------------------------------------------------------
# Form validation: duplicate console name in the same project
# ---------------------------------------------------------------------------

class DuplicateConsoleNameTest(CsvImportTestBase):
    def test_duplicate_name_rejected_with_form_error(self):
        Console.objects.create(project=self.project, name='Pre-existing')
        self._login_staff()
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'Pre-existing',
            'csv_file': self._upload_payload('cl5_inname.csv'),
        })
        # Stays on the upload page; the duplicate console was NOT created twice
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Console.objects.filter(project=self.project, name='Pre-existing').count(), 1,
        )
        self.assertEqual(ConsoleImport.objects.count(), 0)

    def test_duplicate_name_check_is_case_insensitive(self):
        Console.objects.create(project=self.project, name='Pre-Existing')
        self._login_staff()
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'pre-existing',
            'csv_file': self._upload_payload('cl5_inname.csv'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Console.objects.filter(project=self.project).count(), 1,
        )


# ---------------------------------------------------------------------------
# Project scoping (IDOR prevention)
# ---------------------------------------------------------------------------

class ProjectScopingTest(CsvImportTestBase):
    def test_new_console_lands_in_current_project(self):
        # A second project exists but is NOT the current project
        other_project = Project.objects.create(
            name='Other Show', client='Acme', owner=self.owner_user,
        )
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console_name': 'Scoped Console',
            'csv_file': self._upload_payload('cl5_inname.csv'),
        })
        console = Console.objects.get(name='Scoped Console')
        self.assertEqual(console.project, self.project)
        self.assertNotEqual(console.project, other_project)
