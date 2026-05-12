"""End-to-end integration tests for Phase 2 Console CSV Import.

Covers CSV-01..CSV-05 + the security envelope (auth, viewer 403, IDOR).
Depends on Plans 01 (models), 02 (parser + fixtures), 03 (views + URLs).
"""
import pathlib

from django.contrib.auth.models import Group, User
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from planner.models import (
    ConsoleImport,
    ConsoleInput,
    Project,
    Console,
)

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'csv_import'


def _load_fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class CsvImportTestBase(TestCase):
    """Shared setup: a project, a console, a staff user, a viewer user.

    Setup quirks discovered during test authoring:
    - Project.objects.create requires an ``owner`` FK (User), unlike the plan
      spec which showed only ``name`` and ``client``.
    - Console requires only ``name``; ``project`` is nullable.
    - Session key for CurrentProjectMiddleware is ``current_project_id``
      (confirmed in planner/middleware.py:36).
    """

    def setUp(self):
        super().setUp()
        # Owner user must exist before Project can be created
        self.owner_user = User.objects.create_user(
            'owner', 'owner@example.com', 'pw', is_staff=True,
        )
        self.project = Project.objects.create(
            name='Test Show',
            client='Acme',
            owner=self.owner_user,
        )
        self.console = Console.objects.create(
            project=self.project,
            name='CL5 Main',
        )

        self.staff_user = self.owner_user  # owner is staff; reuse to avoid extra user

        self.viewer_user = User.objects.create_user(
            'viewer', 'viewer@example.com', 'pw', is_staff=True,
        )
        viewer_group, _ = Group.objects.get_or_create(name='Viewer')
        self.viewer_user.groups.add(viewer_group)

        self.client = Client()

    def _login_staff(self):
        """Log in as the staff/owner user and set the current_project session key."""
        self.client.force_login(self.staff_user)
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def _login_viewer(self):
        """Log in as the viewer user and set the current_project session key."""
        self.client.force_login(self.viewer_user)
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()

    def _upload_payload(self, fixture_name: str):
        content = _load_fixture_bytes(fixture_name)
        return SimpleUploadedFile(fixture_name, content, content_type='text/csv')


# ---------------------------------------------------------------------------
# Anonymous access
# ---------------------------------------------------------------------------

class AnonymousAccessTest(CsvImportTestBase):
    def test_anon_redirected_to_login_on_upload_get(self):
        """Anonymous GET on upload page → redirect to login (not 403, not 200)."""
        response = self.client.get(reverse('planner:console_import_upload'))
        # @staff_member_required redirects unauthenticated users to /admin/login/
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.url)


# ---------------------------------------------------------------------------
# Viewer gate (D-09 / Blocker 3)
# ---------------------------------------------------------------------------

class ViewerGateTest(CsvImportTestBase):
    def test_viewer_403_on_upload_get(self):
        """Blocker 3 / D-09: viewers see no upload UI at all — GET upload returns 403."""
        self._login_viewer()
        response = self.client.get(reverse('planner:console_import_upload'))
        self.assertEqual(response.status_code, 403)

    def test_viewer_403_on_preview_get(self):
        """Blocker 3 / D-09: viewers see no preview UI — GET preview returns 403.

        Set up the draft as staff so the row exists; then attack from the viewer session.
        """
        # Create a draft as staff first
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        snap = ConsoleImport.objects.get(console=self.console)

        self.client.logout()
        self._login_viewer()
        response = self.client.get(
            reverse('planner:console_import_preview', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_403_on_upload_post(self):
        """Viewer POSTs upload form → 403 (D-09)."""
        self._login_viewer()
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        self.assertEqual(response.status_code, 403)

    def test_viewer_403_on_commit_post(self):
        """Viewer POSTs commit → 403 (D-09)."""
        # Create a draft as staff first so viewer has something to try committing
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        snap = ConsoleImport.objects.get(console=self.console)

        self.client.logout()
        self._login_viewer()
        response = self.client.post(
            reverse('planner:console_import_commit', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Upload flow (CSV-01, CSV-02)
# ---------------------------------------------------------------------------

class UploadFlowTest(CsvImportTestBase):
    def test_valid_csv_creates_draft_and_redirects_to_preview(self):
        """Valid CL5 InName CSV → 1 draft ConsoleImport created → redirect to preview."""
        self._login_staff()
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        self.assertEqual(ConsoleImport.objects.count(), 1)
        snap = ConsoleImport.objects.get()
        self.assertFalse(snap.committed)
        self.assertEqual(snap.console, self.console)
        self.assertRedirects(
            response,
            reverse('planner:console_import_preview', kwargs={'import_id': snap.id}),
            fetch_redirect_response=False,
        )

    def test_junk_upload_no_import_row_created(self):
        """Uploading a non-Yamaha file renders the upload page with an error; no ConsoleImport created."""
        self._login_staff()
        junk = SimpleUploadedFile('junk.csv', b'not a yamaha file\n', content_type='text/csv')
        response = self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': junk,
        })
        self.assertEqual(ConsoleImport.objects.count(), 0)
        # Form re-renders (200) with error messaging
        self.assertEqual(response.status_code, 200)

    def test_cannot_preview_other_project_import(self):
        """Previewing an import_id from a different project returns 404 (IDOR guard)."""
        other_owner = User.objects.create_user('other_owner', 'o@example.com', 'pw')
        other_project = Project.objects.create(
            name='Other Show', client='Other', owner=other_owner,
        )
        other_console = Console.objects.create(project=other_project, name='Other Console')
        snap = ConsoleImport.objects.create(
            console=other_console,
            original_filename='x.csv',
            parsed_sections={'sections': [], 'family': 'cl_ql', 'is_zip': False},
        )

        self._login_staff()  # logged into self.project, NOT other_project
        response = self.client.get(
            reverse('planner:console_import_preview', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Preview page (CSV-03)
# ---------------------------------------------------------------------------

class PreviewTest(CsvImportTestBase):
    def _create_draft(self):
        """Helper: upload customized CL5 fixture and return the ConsoleImport."""
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        return ConsoleImport.objects.get()

    def test_preview_context_keys(self):
        """Preview page exposes all required context keys."""
        snap = self._create_draft()
        response = self.client.get(
            reverse('planner:console_import_preview', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 200)
        for key in (
            'import', 'stats', 'diff_rows', 'errors',
            'detected_family', 'current_count', 'new_count', 'family_mismatch_warning',
        ):
            self.assertIn(key, response.context, f'missing context key {key!r}')

    def test_preview_recomputes_diff(self):
        """Diff is recomputed on every GET; mutating a channel between upload and
        preview GET changes the diff result.

        (This verifies the 'no drift detection' stance in RESEARCH: just recompute.)
        """
        snap = self._create_draft()

        # Manually add a ConsoleInput that didn't exist at upload time
        ConsoleInput.objects.create(
            console=self.console, input_ch='10', source='Pre-existing', color='Blue',
        )

        response = self.client.get(
            reverse('planner:console_import_preview', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 200)
        # current_count should now reflect the manually-added row
        self.assertGreaterEqual(response.context['current_count'], 1)


# ---------------------------------------------------------------------------
# Commit flow (CSV-03, CSV-04)
# ---------------------------------------------------------------------------

class CommitTest(CsvImportTestBase):
    def test_commit_creates_channels_and_redirects(self):
        """Committing a customized CL5 InName CSV creates ConsoleInput rows and
        redirects to the multitrack dashboard (D-06)."""
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        snap = ConsoleImport.objects.get()

        response = self.client.post(
            reverse('planner:console_import_commit', kwargs={'import_id': snap.id})
        )
        self.assertRedirects(
            response,
            reverse('planner:multitrack_dashboard'),
            fetch_redirect_response=False,
        )

        snap.refresh_from_db()
        self.assertTrue(snap.committed)
        self.assertGreaterEqual(snap.summary.get('created', 0), 2)

        # The two customized rows must have landed correctly
        kick = ConsoleInput.objects.get(console=self.console, input_ch='1')
        self.assertEqual(kick.source, 'Kick')
        self.assertEqual(kick.color, 'Red')

        snare = ConsoleInput.objects.get(console=self.console, input_ch='2')
        self.assertEqual(snare.source, 'Snare')
        self.assertEqual(snare.color, 'Orange')

    def test_double_commit_returns_400(self):
        """POSTing commit a second time on an already-committed import returns 400."""
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        snap = ConsoleImport.objects.get()
        # First commit
        self.client.post(
            reverse('planner:console_import_commit', kwargs={'import_id': snap.id})
        )
        # Second commit — must return 400
        response = self.client.post(
            reverse('planner:console_import_commit', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 400)

    def test_smart_skip_preserves_user_custom_label(self):
        """D-01: a default-row CSV must NOT overwrite an engineer's custom label.

        Pre-populate input_ch=5 with a custom label, then upload a CSV where
        _05 is the factory default ``ch 5,Blue,Dynamic,``. After commit the
        custom label must still be intact.
        """
        # Pre-populate input_ch=5 with a custom label
        ConsoleInput.objects.create(
            console=self.console, input_ch='5', source='UserCustomLabel', color='Green',
        )
        self._login_staff()

        # Build a minimal CSV where _05 is the factory default
        content = (
            "[Information]\r\nCL5\r\nV4.1\r\n[InName]\r\nIN,NAME,COLOR,ICON,\r\n"
            "_05,ch 5,Blue,Dynamic,\r\n"
        )
        payload = SimpleUploadedFile(
            'mini.csv', content.encode('utf-8'), content_type='text/csv'
        )
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': payload,
        })
        snap = ConsoleImport.objects.get()
        self.client.post(
            reverse('planner:console_import_commit', kwargs={'import_id': snap.id})
        )

        preserved = ConsoleInput.objects.get(console=self.console, input_ch='5')
        self.assertEqual(preserved.source, 'UserCustomLabel')
        self.assertEqual(preserved.color, 'Green')


# ---------------------------------------------------------------------------
# CSV-05 hand-off: Phase 1 picker query sees imported channels
# ---------------------------------------------------------------------------

class CommitToPickerTest(CsvImportTestBase):
    """CSV-05 — after commit, Phase 1's picker exposes the new channels.

    Phase 1's picker uses the query:
        ConsoleInput.objects.filter(console=console).exclude(id__in=used_ids['input'])
    This test re-runs the same base query without the exclude clause (no used
    tracks yet) and asserts the imported channels are present.

    No Phase 1 code is modified. The same ConsoleInput table entries that the
    import created are the ones the picker reads.
    """

    def test_imported_channels_appear_in_phase_one_queries(self):
        """CSV-05: after commit, ConsoleInput.objects.filter(console=...) returns
        the imported channels — satisfying Phase 1's picker query without any
        Phase 1 code changes."""
        self._login_staff()
        # Console starts with zero ConsoleInput rows
        self.assertEqual(ConsoleInput.objects.filter(console=self.console).count(), 0)

        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        snap = ConsoleImport.objects.get()
        self.client.post(
            reverse('planner:console_import_commit', kwargs={'import_id': snap.id})
        )

        # This is the exact query Phase 1's picker (_build_picker_data) uses.
        # Re-running it here must now return the imported channels.
        imported = list(
            ConsoleInput.objects.filter(console=self.console).order_by('input_ch')
        )
        sources = [c.source for c in imported]
        self.assertIn('Kick', sources)
        self.assertIn('Snare', sources)
        self.assertGreaterEqual(len(imported), 2)  # at least the 2 non-default rows


# ---------------------------------------------------------------------------
# Family-mismatch warning (Blocker 2 / R-02)
# ---------------------------------------------------------------------------

class FamilyMismatchWarningTest(CsvImportTestBase):
    """Blocker 2 / R-02: family-mismatch warning surfaces as a red banner +
    second confirmation checkbox + disabled commit button when the heuristic
    trips.

    Two heuristics trigger the warning (either is sufficient):
    1. Count gap: new_count > current_count + 16
    2. Name mismatch: detected family tokens don't appear in the console name
    """

    def test_warning_set_when_name_mismatch(self):
        """Uploading a Rivage InName.csv (detected_family='rivage_pm') against a
        console named 'CL5 Main' (no 'rivage'/'PM' tokens) trips the name-mismatch
        heuristic — family_mismatch_warning must be True.

        The console has zero existing channels (current_count=0).
        The Rivage InName fixture is all-default rows so new_count=0; the gap
        heuristic does NOT trip. The name-mismatch heuristic does trip because
        'CL5 Main' contains no 'rivage' or 'PM' tokens.
        """
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('rivage_inname.csv'),
        })
        snap = ConsoleImport.objects.get()
        response = self.client.get(
            reverse('planner:console_import_preview', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 200)
        # Name mismatch must trip the warning (rivage_pm CSV into 'CL5 Main')
        self.assertTrue(
            response.context.get('family_mismatch_warning'),
            f"warning not set: detected_family={response.context.get('detected_family')} "
            f"new={response.context.get('new_count')} current={response.context.get('current_count')}",
        )
        # Template renders the warning banner div, confirm checkbox, and disabled commit button.
        # Check for the rendered div element (not just the CSS class name, which is always
        # present in the <style> block regardless of warning state).
        self.assertContains(response, 'class="mts-banner mts-banner-warning"')
        self.assertContains(response, 'name="confirm_family"')
        self.assertIn(b'disabled', response.content)

    def test_warning_unset_when_match_clean(self):
        """Customized CL5 InName upload into a fresh console named 'CL5 Main'
        produces new_count=2 (well within the +16 gap) AND 'CL5' appears in the
        console name — warning must NOT trip."""
        self._login_staff()
        self.client.post(reverse('planner:console_import_upload'), {
            'console': self.console.id,
            'csv_file': self._upload_payload('cl5_inname_customized.csv'),
        })
        snap = ConsoleImport.objects.get()
        response = self.client.get(
            reverse('planner:console_import_preview', kwargs={'import_id': snap.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get('family_mismatch_warning'))
        # Check that the warning div element is NOT in the response body.
        # (The CSS class name itself appears in the <style> block on every render,
        # so we check for the rendered div markup instead.)
        self.assertNotContains(response, 'class="mts-banner mts-banner-warning"')
