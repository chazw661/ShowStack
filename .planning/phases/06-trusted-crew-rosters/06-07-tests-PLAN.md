---
phase: 06-trusted-crew-rosters
plan: 07
type: execute
wave: 4
depends_on:
  - 06-01
  - 06-02
  - 06-03
  - 06-04
  - 06-05
  - 06-06
files_modified:
  - planner/tests/test_crew_rosters.py
autonomous: true
requirements:
  - SPEC-06-R01
  - SPEC-06-R02
  - SPEC-06-R03
  - SPEC-06-R04
  - SPEC-06-R05
  - SPEC-06-R06
  - SPEC-06-R07
  - SPEC-06-R08
user_setup: []
must_haves:
  truths:
    - "planner/tests/test_crew_rosters.py exists and follows the Phase 5 test_channel_record_defaults.py pattern (setUpTestData + Client + force_login)"
    - "Test class covers all 8 CI-gatable SPEC acceptance criteria (R1, R2, R3, R4, R5, R6, R7, R8)"
    - "send_crew_added_email is mocked via unittest.mock.patch so no real Resend API call is made during tests"
    - "Test for SPEC R5 verifies via git diff that Invitation model, accept_invitation, and send_invitation_email diffs are zero (or via grep that those identifiers are unchanged in the source files)"
    - "Test for SPEC R7 verifies a removed CrewMember row leaves the corresponding ProjectMember row intact"
    - "Test for SPEC R8 verifies a user in two of an owner's crews bulk-added to the same project produces exactly ONE ProjectMember row (no IntegrityError)"
    - "Test for SPEC R6 (auto-claim) materializes a ProjectMember row for a pending email when the matching user registers"
    - "Test for DB constraints from D-15: XOR check + partial unique constraints raise IntegrityError on violation"
    - "python manage.py test planner.tests.test_crew_rosters exits 0"
    - "python manage.py test planner accounts exits 0 — no regressions in existing test suite"
  artifacts:
    - path: "planner/tests/test_crew_rosters.py"
      provides: "Test class CrewRosterTests covering all 8 SPEC requirements + D-15 constraints"
      min_lines: 200
      contains: "class CrewRosterTests(TestCase)"
  key_links:
    - from: "planner/tests/test_crew_rosters.py"
      to: "accounts/views.py:bulk_add_crew"
      via: "self.client.post(reverse('bulk_add_crew', args=[...]))"
      pattern: "bulk_add_crew"
    - from: "planner/tests/test_crew_rosters.py"
      to: "planner/crew.py:claim_pending_crew_memberships"
      via: "Direct unit-test call + register() integration test"
      pattern: "claim_pending_crew_memberships"
    - from: "planner/tests/test_crew_rosters.py:test_emails_sent_per_new_row"
      to: "accounts/views.py:send_crew_added_email"
      via: "@patch('accounts.views.send_crew_added_email')"
      pattern: "@patch.*send_crew_added_email"
---

<objective>
Build a single regression test module `planner/tests/test_crew_rosters.py` that locks the CI gate for every CI-gatable SPEC requirement (R1–R8) plus the D-15 DB constraints. Pre-onboarding HUMAN-UAT (SPEC R6's manual smoke path) is the only criterion that remains a human-verified gate.

Purpose: Locks Phase 6 behavior against future regressions. Mirrors the Phase 5 `test_channel_record_defaults.py` style (Client + setUpTestData + force_login + @patch for Resend). Closes the last `requirements` slot for SPEC R5, R6, R7 coverage at the test level.
Output: One new test file, ≥200 lines, ≥10 test methods covering the 8 SPEC requirements + 3 D-15 DB constraints.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/phases/06-trusted-crew-rosters/06-SPEC.md
@.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md
@.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md
@planner/tests/test_channel_record_defaults.py

<interfaces>
<!-- Existing test patterns the executor MUST mirror. -->

From planner/tests/test_channel_record_defaults.py (the Phase 5 template — mirrored for Phase 6):

    import json
    from django.contrib.auth import get_user_model
    from django.test import Client, TestCase
    from django.urls import reverse

    from planner.models import (
        Console, ConsoleInput, MultitrackSession, MultitrackTrack, Project,
    )

    User = get_user_model()


    class ChannelRecordDefaultsSeedTests(TestCase):
        @classmethod
        def setUpTestData(cls):
            cls.user = User.objects.create_user(
                username='pol-tester', email='pol-tester@example.com',
                password='test-password-123', is_staff=True,
            )
            cls.project = Project.objects.create(name='POL Test Show', owner=cls.user)
            ...

        def setUp(self):
            self.client = Client()
            self.client.force_login(self.user)
            session = self.client.session
            session['current_project_id'] = self.project.id
            session.save()

URL names this plan exercises (verified in Plans 03 + 04 + 05):
- `crew_index`, `crew_create`, `crew_detail`, `crew_delete`
- `crew_member_add`, `crew_member_remove`
- `bulk_add_crew` (args: project_id, crew_id)
- `register` (test the registration flow's auto-claim hook)

Symbols this plan exercises:
- `planner.models.Crew`, `CrewMember`, `CrewProjectAdd`
- `planner.models.ProjectMember`, `Project` (existing)
- `planner.crew.claim_pending_crew_memberships(user)` — unit-testable directly
- `accounts.views.send_crew_added_email` — MOCK via `@patch('accounts.views.send_crew_added_email')` so no Resend call hits the network

The middleware-session pattern from test_channel_record_defaults.py is NOT needed for Phase 6 tests — `bulk_add_crew` uses URL-arg `project_id`, not session-scoped `current_project_id`. But session setup is harmless if copied.

D-15 DB constraint names (from Plan 01):
- `crewmember_user_xor_email` (XOR check)
- `uniq_crewmember_crew_user` (partial unique on `(crew, user)`)
- `uniq_crewmember_crew_email` (partial unique on `(crew, email)`)

`RegistrationForm` is at `accounts/forms.py:7`. POST fields it expects: typically `username`, `email`, `password1`, `password2`, `first_name`, `last_name`. Executor MUST read `accounts/forms.py` to confirm the exact field list before writing the register-flow integration test.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Create planner/tests/test_crew_rosters.py covering all 8 SPEC requirements</name>
  <files>planner/tests/test_crew_rosters.py</files>
  <read_first>
    - `planner/tests/test_channel_record_defaults.py` (full file — the recommended Phase 5 template)
    - `planner/tests/__init__.py` (to verify the tests package convention — if a `tests/` package exists with `__init__.py`)
    - `accounts/forms.py:1-100` (RegistrationForm — to learn the exact POST-field shape for the register-flow integration test)
    - `accounts/views.py` (post-Plan-05 state — to confirm `send_crew_added_email` is at module-level and importable as `accounts.views.send_crew_added_email`)
    - `.planning/phases/06-trusted-crew-rosters/06-SPEC.md` Acceptance Criteria
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` planner/tests/test_crew_rosters.py section
  </read_first>
  <action>
Create `planner/tests/test_crew_rosters.py`. The file must be ≥200 lines and contain at least these 10+ test methods (one per SPEC requirement + DB constraints). Use `unittest.mock.patch` to mock `accounts.views.send_crew_added_email` so no Resend API call is made.

Structure outline:

```
"""Regression tests for Phase 6 — Trusted Crew Rosters.

Covers every CI-gatable SPEC acceptance criterion (R1, R2, R3, R4, R5, R6, R7, R8)
plus the D-15 DB constraints (XOR check + two partial UniqueConstraints).

Pre-onboarding HUMAN-UAT (one item under R6) is NOT covered here; it remains
the only human-verified gate for Phase 6.

Mirrors the Phase 5 pattern in planner/tests/test_channel_record_defaults.py:
  - setUpTestData for owner / crew / project plumbing
  - Client + force_login per test
  - @patch for Resend so no real email goes out
"""
import subprocess
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from planner.crew import claim_pending_crew_memberships
from planner.models import (
    Crew,
    CrewMember,
    CrewProjectAdd,
    Invitation,
    Project,
    ProjectMember,
)

User = get_user_model()


class CrewRosterTests(TestCase):
    """SPEC R1, R2, R3, R4, R7, R8 + happy-path coverage."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='charlie', email='charlie@example.com',
            password='test-pw-123', is_staff=True,
        )
        cls.mike = User.objects.create_user(
            username='mike', email='mike@example.com', password='pw',
        )
        cls.sarah = User.objects.create_user(
            username='sarah', email='sarah@example.com', password='pw',
        )
        cls.jose = User.objects.create_user(
            username='jose', email='jose@example.com', password='pw',
        )
        cls.project = Project.objects.create(name='Test Show', owner=cls.owner)
        cls.crew = Crew.objects.create(owner=cls.owner, name='Concert team')
        CrewMember.objects.create(crew=cls.crew, user=cls.mike, default_role='editor')
        CrewMember.objects.create(crew=cls.crew, user=cls.sarah, default_role='editor')
        CrewMember.objects.create(crew=cls.crew, user=cls.jose, default_role='editor')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.owner)

    # --- SPEC R1: Named crew rosters per owner ---

    def test_crew_index_lists_owners_crews(self):
        # Owner sees their own crew on /crew/.
        response = self.client.get(reverse('crew_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Concert team')

    def test_crew_create_blocks_duplicate_name_per_owner(self):
        # SPEC R1 acceptance + D-02 unique_together on (owner, name).
        response = self.client.post(reverse('crew_create'), {'name': 'Concert team'})
        # Redirected back to index with error flash (not 500).
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Crew.objects.filter(owner=self.owner, name='Concert team').count(),
            1,
        )

    # --- SPEC R2: Per-crew default_role ---

    def test_crew_member_add_with_viewer_role(self):
        # Add a new user with default_role=viewer via the form.
        newbie = User.objects.create_user(
            username='newbie', email='newbie@example.com', password='pw',
        )
        response = self.client.post(
            reverse('crew_member_add', args=[self.crew.id]),
            {'user_or_email': 'newbie', 'default_role': 'viewer'},
        )
        self.assertEqual(response.status_code, 302)
        cm = CrewMember.objects.get(crew=self.crew, user=newbie)
        self.assertEqual(cm.default_role, 'viewer')

    # --- SPEC R3 + R4: Bulk-add creates ProjectMember rows + emails ---

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_creates_project_member_rows(self, mock_email):
        response = self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertEqual(response.status_code, 302)
        pms = ProjectMember.objects.filter(project=self.project)
        self.assertEqual(pms.count(), 3)
        for pm in pms:
            self.assertEqual(pm.role, 'editor')
            self.assertEqual(pm.invited_by_id, self.owner.id)
            self.assertIsNotNone(pm.invited_at)  # Pitfall 2 — auto_now_add fires
        # SPEC R4: one email per new ProjectMember row.
        self.assertEqual(mock_email.call_count, 3)
        # SPEC R3 — no Invitation rows.
        self.assertEqual(Invitation.objects.filter(project=self.project).count(), 0)

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_idempotent_when_all_already_members(self, mock_email):
        # First click adds all 3.
        url = reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        self.client.post(url)
        mock_email.reset_mock()
        # Second click adds 0, sends 0 emails.
        self.client.post(url)
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )
        self.assertEqual(mock_email.call_count, 0)

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_records_crew_project_add(self, mock_email):
        # D-09 — bulk-add writes CrewProjectAdd for auto-claim hook.
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertTrue(
            CrewProjectAdd.objects.filter(crew=self.crew, project=self.project).exists()
        )

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_rejects_non_project_owner(self, mock_email):
        # SPEC R3 — only project owner can bulk-add.
        outsider = User.objects.create_user(
            username='outsider', email='out@example.com', password='pw',
        )
        self.client.force_login(outsider)
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 0,
        )

    @patch('accounts.views.send_crew_added_email', side_effect=Exception('Resend down'))
    def test_bulk_add_survives_email_failure(self, mock_email):
        # D-10 — log + swallow; ProjectMember rows still committed.
        response = self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )

    # --- SPEC R5: Strictly additive — Invitation untouched ---

    def test_invitation_model_signature_preserved(self):
        # SPEC R5 — Invitation model fields are NOT modified by Phase 6.
        # This is a SUBSET check (existing fields still present); it cannot
        # detect ADDED fields or function-body edits. The behavioral test
        # below (`test_accept_invitation_flow_still_works_end_to_end`) is the
        # real behavioral gate; per-plan git-diff checks remain the file-level
        # gate.
        from planner.models import Invitation as Inv
        field_names = {f.name for f in Inv._meta.get_fields() if hasattr(f, 'name')}
        # Existing Invitation fields (verified in planner/models.py:3809-3849).
        # If Phase 6 has accidentally added a field, this assertion catches it.
        expected_required = {'project', 'email', 'role', 'status', 'token', 'invited_by', 'invited_at'}
        self.assertTrue(
            expected_required.issubset(field_names),
            f"Invitation missing expected fields: {expected_required - field_names}",
        )

    def test_accept_invitation_flow_still_works_end_to_end(self):
        """SPEC R5 — behavioral regression: legacy accept_invitation flow unchanged.

        Field-presence checks (above) and git-diff acceptance criteria gate
        the source files. This test gates the BEHAVIOR end-to-end: a pending
        Invitation row, POST to /invitations/accept/<token>/, must still
        materialize a ProjectMember row and flip status to 'accepted'.

        accounts/urls.py:13 confirms the route is
        path('invitations/accept/<uuid:token>/', views.accept_invitation,
             name='accept_invitation').
        """
        import uuid
        # The invitee must be a registered user — accept_invitation is the
        # post-login claim step.
        invitee = User.objects.create_user(
            username='r5-invitee', email='r5-invitee@example.com',
            password='pw',
        )
        # Create a pending Invitation row directly (mirrors what invite_user
        # writes via InviteUserForm.save()).
        invitation = Invitation.objects.create(
            project=self.project,
            email='r5-invitee@example.com',
            role='editor',
            status='pending',
            token=uuid.uuid4(),
            invited_by=self.owner,
        )
        # Log in as the invitee and accept.
        self.client.force_login(invitee)
        response = self.client.post(
            reverse('accept_invitation', args=[invitation.token])
        )
        # Redirect (Django's standard accept-then-redirect pattern).
        self.assertEqual(response.status_code, 302)
        # ProjectMember row materialized.
        self.assertTrue(
            ProjectMember.objects.filter(
                project=self.project, user=invitee,
            ).exists(),
            "accept_invitation regressed: no ProjectMember row created",
        )
        # Invitation status flipped to 'accepted'.
        invitation.refresh_from_db()
        self.assertEqual(
            invitation.status, 'accepted',
            f"accept_invitation regressed: status is {invitation.status!r}, expected 'accepted'",
        )

    # --- SPEC R7: No-cascade removal ---

    @patch('accounts.views.send_crew_added_email')
    def test_remove_crew_member_does_not_cascade_to_project_member(self, mock_email):
        # SPEC R7 — removing a CrewMember row leaves ProjectMember intact.
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )
        # Remove Mike from the crew.
        mike_cm = CrewMember.objects.get(crew=self.crew, user=self.mike)
        self.client.post(
            reverse('crew_member_remove', args=[self.crew.id, mike_cm.id])
        )
        # Crew row gone…
        self.assertFalse(
            CrewMember.objects.filter(crew=self.crew, user=self.mike).exists()
        )
        # …but ProjectMember row still there.
        self.assertTrue(
            ProjectMember.objects.filter(project=self.project, user=self.mike).exists()
        )

    @patch('accounts.views.send_crew_added_email')
    def test_delete_crew_does_not_cascade_to_project_member(self, mock_email):
        # Bulk-add, then delete entire crew, verify ProjectMember rows remain.
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.client.post(reverse('crew_delete', args=[self.crew.id]))
        self.assertFalse(Crew.objects.filter(id=self.crew.id).exists())
        # All 3 ProjectMember rows remain (SPEC R7 ethos extended to crew delete).
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )

    # --- SPEC R8: Dedupe across crews ---

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_dedupes_user_in_multiple_crews(self, mock_email):
        # Mike is in BOTH Concert team and Corporate team.
        corporate = Crew.objects.create(owner=self.owner, name='Corporate team')
        CrewMember.objects.create(crew=corporate, user=self.mike, default_role='editor')
        url_concert = reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        url_corp = reverse('bulk_add_crew', args=[self.project.id, corporate.id])
        self.client.post(url_concert)  # 3 rows
        self.client.post(url_corp)     # Mike already a member → 0 new
        # Exactly ONE ProjectMember row for Mike, no IntegrityError.
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project, user=self.mike).count(),
            1,
        )


class CrewMemberConstraintTests(TestCase):
    """D-15 DB constraints — XOR check + partial unique constraints."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='constraint-owner', email='c@x.com', password='pw',
        )
        cls.mike = User.objects.create_user(
            username='c-mike', email='c-mike@x.com', password='pw',
        )
        cls.crew = Crew.objects.create(owner=cls.owner, name='Constraint crew')

    def test_xor_blocks_both_user_and_email_set(self):
        # D-15 — crewmember_user_xor_email rejects rows with both non-null.
        with self.assertRaises(IntegrityError):
            CrewMember.objects.create(
                crew=self.crew, user=self.mike, email='c-mike@x.com',
            )

    def test_xor_blocks_neither_user_nor_email_set(self):
        # D-15 — XOR also rejects rows with both null.
        with self.assertRaises(IntegrityError):
            CrewMember.objects.create(crew=self.crew, user=None, email=None)

    def test_partial_unique_blocks_duplicate_user_in_crew(self):
        # D-15 — uniq_crewmember_crew_user.
        CrewMember.objects.create(crew=self.crew, user=self.mike, default_role='editor')
        with self.assertRaises(IntegrityError):
            CrewMember.objects.create(crew=self.crew, user=self.mike, default_role='viewer')

    def test_partial_unique_blocks_duplicate_pending_email_in_crew(self):
        # D-15 — uniq_crewmember_crew_email; Postgres NULL-not-distinct workaround.
        CrewMember.objects.create(crew=self.crew, email='pending@example.com')
        with self.assertRaises(IntegrityError):
            CrewMember.objects.create(crew=self.crew, email='pending@example.com')


class AutoClaimTests(TestCase):
    """SPEC R6 — pre-onboarding placeholder + auto-claim on register."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='claim-owner', email='claim-owner@x.com', password='pw',
        )
        cls.project = Project.objects.create(name='Claim Show', owner=cls.owner)
        cls.crew = Crew.objects.create(owner=cls.owner, name='Pending crew')
        CrewMember.objects.create(
            crew=cls.crew, email='newbie@example.com', default_role='editor',
        )
        CrewProjectAdd.objects.create(crew=cls.crew, project=cls.project)

    def test_claim_rebinds_pending_row_and_materializes_project_member(self):
        # SPEC R6 — register-equivalent: create the user, call the helper directly.
        newbie = User.objects.create_user(
            username='newbie', email='newbie@example.com', password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        # CrewMember row rebound in place (D-01).
        cm = CrewMember.objects.get(crew=self.crew, user=newbie)
        self.assertIsNone(cm.email)
        self.assertEqual(cm.default_role, 'editor')  # default_role preserved
        # ProjectMember row materialized.
        self.assertTrue(
            ProjectMember.objects.filter(project=self.project, user=newbie).exists()
        )
        # Helper returns the new rows for the caller's email loop.
        self.assertEqual(len(new_pms), 1)
        self.assertEqual(new_pms[0].project_id, self.project.id)
        self.assertEqual(new_pms[0].role, 'editor')
        self.assertEqual(new_pms[0].invited_by_id, self.owner.id)

    def test_claim_iexact_matches_uppercase_email(self):
        # D-08 — case-insensitive match.
        newbie = User.objects.create_user(
            username='newbie-upper', email='NEWBIE@example.com', password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        self.assertEqual(len(new_pms), 1)

    def test_claim_strips_whitespace(self):
        # D-08 — explicit .strip() on user-side value.
        # Owner stored email with no surrounding whitespace; new user's email
        # also has none — but the helper's .strip() guards against accidental
        # form-data whitespace.
        newbie = User.objects.create_user(
            username='nb-stripped', email='  newbie@example.com  ', password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        self.assertEqual(len(new_pms), 1)

    def test_claim_does_not_match_plus_alias(self):
        # D-08 — NO plus-alias collapsing. newbie+alias@example.com is NOT newbie@example.com.
        newbie = User.objects.create_user(
            username='nb-alias', email='newbie+alias@example.com', password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        self.assertEqual(len(new_pms), 0)
        # CrewMember row is still pending.
        self.assertTrue(
            CrewMember.objects.filter(crew=self.crew, email='newbie@example.com').exists()
        )

    def test_claim_idempotent_on_existing_project_member(self):
        # If the user is ALREADY a ProjectMember (e.g. added directly), claim
        # should NOT raise and should NOT create a duplicate.
        newbie = User.objects.create_user(
            username='nb-already', email='newbie@example.com', password='pw',
        )
        ProjectMember.objects.create(
            project=self.project, user=newbie, role='viewer', invited_by=self.owner,
        )
        new_pms = claim_pending_crew_memberships(newbie)
        # Helper returned 0 new rows because the existing one short-circuited.
        self.assertEqual(len(new_pms), 0)
        # The existing ProjectMember was NOT replaced — role still 'viewer'.
        pm = ProjectMember.objects.get(project=self.project, user=newbie)
        self.assertEqual(pm.role, 'viewer')


class RegisterIntegrationTests(TestCase):
    """SPEC R6 — full /register/ POST flow exercising auto-claim + atomic wrap (D-11)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='reg-owner', email='reg-owner@x.com', password='pw',
        )
        cls.project = Project.objects.create(name='Reg Show', owner=cls.owner)
        cls.crew = Crew.objects.create(owner=cls.owner, name='Reg crew')
        CrewMember.objects.create(
            crew=cls.crew, email='registrant@example.com', default_role='editor',
        )
        CrewProjectAdd.objects.create(crew=cls.crew, project=cls.project)

    @patch('accounts.views.send_crew_added_email')
    def test_register_triggers_auto_claim(self, mock_email):
        # Use the actual /register/ POST endpoint. The RegistrationForm field
        # names are the canonical Django UserCreationForm subset; executor
        # confirmed via accounts/forms.py before writing the field list.
        response = Client().post(reverse('register'), {
            'username': 'registrant',
            'email': 'registrant@example.com',
            'password1': 'a-very-strong-passw0rd!',
            'password2': 'a-very-strong-passw0rd!',
            'first_name': 'Reg',
            'last_name': 'Istrant',
        })
        # Successful registration redirects to login.
        self.assertEqual(response.status_code, 302)
        registrant = User.objects.get(username='registrant')
        # SPEC R6 — ProjectMember row materialized via auto-claim.
        self.assertTrue(
            ProjectMember.objects.filter(project=self.project, user=registrant).exists()
        )
        # SPEC R6 — pending CrewMember row rebound in place.
        cm = CrewMember.objects.get(crew=self.crew, user=registrant)
        self.assertIsNone(cm.email)
        # SPEC R4 — confirmation email attempted (post-atomic loop).
        self.assertEqual(mock_email.call_count, 1)
```

Note on RegistrationForm field names: executor must confirm against `accounts/forms.py` before finalizing the test. If the form requires additional fields (e.g. `terms_accepted` for the clickwrap consent mentioned in CLAUDE.md), add them.

Note on test location: file lives at `planner/tests/test_crew_rosters.py` per D-13 ("models live in planner; tests live next to models"). Mirrors Phase 5's `planner/tests/test_channel_record_defaults.py`.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && test -f planner/tests/test_crew_rosters.py && test "$(wc -l < planner/tests/test_crew_rosters.py)" -ge 200 && grep -q "class CrewRosterTests(TestCase)" planner/tests/test_crew_rosters.py && grep -q "class CrewMemberConstraintTests" planner/tests/test_crew_rosters.py && grep -q "class AutoClaimTests" planner/tests/test_crew_rosters.py && grep -q "class RegisterIntegrationTests" planner/tests/test_crew_rosters.py && grep -q "@patch('accounts.views.send_crew_added_email')" planner/tests/test_crew_rosters.py && grep -q "test_bulk_add_creates_project_member_rows" planner/tests/test_crew_rosters.py && grep -q "test_bulk_add_dedupes_user_in_multiple_crews" planner/tests/test_crew_rosters.py && grep -q "test_remove_crew_member_does_not_cascade_to_project_member" planner/tests/test_crew_rosters.py && grep -q "test_xor_blocks_both_user_and_email_set" planner/tests/test_crew_rosters.py && grep -q "test_partial_unique_blocks_duplicate_pending_email_in_crew" planner/tests/test_crew_rosters.py && grep -q "test_claim_rebinds_pending_row_and_materializes_project_member" planner/tests/test_crew_rosters.py && grep -q "test_register_triggers_auto_claim" planner/tests/test_crew_rosters.py && python manage.py test planner.tests.test_crew_rosters -v 2 2>&1 | tee /tmp/test_crew.out | tail -5 | grep -q "OK$" && python manage.py test planner accounts -v 0 2>&1 | tee /tmp/test_full.out | tail -3 | grep -q "^OK$"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f planner/tests/test_crew_rosters.py` exits 0
    - `wc -l < planner/tests/test_crew_rosters.py` outputs >= 200
    - `grep -c "^class " planner/tests/test_crew_rosters.py` outputs >= 4 (CrewRosterTests, CrewMemberConstraintTests, AutoClaimTests, RegisterIntegrationTests)
    - `grep -c "    def test_" planner/tests/test_crew_rosters.py` outputs >= 15
    - `grep -q "@patch('accounts.views.send_crew_added_email')" planner/tests/test_crew_rosters.py` exits 0 (Resend mocked — no network)
    - `grep -q "from planner.crew import claim_pending_crew_memberships" planner/tests/test_crew_rosters.py` exits 0
    - `grep -q "test_bulk_add_dedupes_user_in_multiple_crews" planner/tests/test_crew_rosters.py` exits 0 (SPEC R8)
    - `grep -q "test_remove_crew_member_does_not_cascade_to_project_member" planner/tests/test_crew_rosters.py` exits 0 (SPEC R7)
    - `grep -q "test_xor_blocks_both_user_and_email_set" planner/tests/test_crew_rosters.py` exits 0 (D-15)
    - `grep -q "test_partial_unique_blocks_duplicate_pending_email_in_crew" planner/tests/test_crew_rosters.py` exits 0 (D-15 / Pitfall 1)
    - `grep -q "test_claim_rebinds_pending_row_and_materializes_project_member" planner/tests/test_crew_rosters.py` exits 0 (SPEC R6)
    - `grep -q "test_register_triggers_auto_claim" planner/tests/test_crew_rosters.py` exits 0 (SPEC R6 integration)
    - `grep -q "test_accept_invitation_flow_still_works_end_to_end" planner/tests/test_crew_rosters.py` exits 0 (SPEC R5 behavioral regression — legacy flow unchanged)
    - `python manage.py test planner.tests.test_crew_rosters -v 2` exits 0 with all tests OK
    - `python manage.py test planner accounts -v 0` exits 0 — no regressions in existing suite
  </acceptance_criteria>
  <done>
`planner/tests/test_crew_rosters.py` exists with 4+ test classes and 15+ test methods covering every CI-gatable SPEC requirement. `python manage.py test planner accounts` exits 0 — full suite green, no regressions introduced by Phase 6.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test runner → Resend SDK | Mocked via `@patch` so no test ever hits the real Resend API |
| Test runner → DB | Standard Django test isolation (per-test transaction rollback for TestCase) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-07-01 | Information Disclosure | Tests accidentally trigger real Resend send | mitigate | Every test that touches bulk_add_crew is decorated `@patch('accounts.views.send_crew_added_email')` |
| T-06-07-02 | Tampering | Test pollutes prod DB | accept | Django TestCase wraps each test in a transaction rollback — standard Django guarantee |
| T-06-07-03 | Repudiation | Future Phase 6 regression slips into prod undetected | mitigate | This plan ships 15+ assertions covering all 8 SPEC R's; CI runs `python manage.py test planner accounts` on every deploy attempt (Railway's startCommand does not run tests, so CI gate is the developer running tests locally — same as Phase 5) |
| T-06-07-04 | Information Disclosure | Test fixture leaks real user emails | accept | Test users use synthetic emails (`@example.com`) per RFC 2606 — no real-user collision possible |
</threat_model>

<verification>
- `python manage.py test planner.tests.test_crew_rosters` exits 0
- `python manage.py test planner accounts` exits 0 (full suite green)
- All grep acceptance criteria pass
- No tests touch the real Resend API (verified by `@patch` decorator on every bulk-add test)
</verification>

<success_criteria>
- 15+ test methods, all passing
- One test per CI-gatable SPEC requirement (R1–R8 inclusive)
- Three tests for D-15 DB constraints (XOR check + 2 partial uniques)
- One integration test exercising the full /register/ POST flow end-to-end (auto-claim materializes ProjectMember through the atomic wrap per D-11)
- `python manage.py test planner accounts` returns OK with no regressions in existing tests
- HUMAN-UAT (SPEC R6 manual smoke) is the ONLY remaining gate before /gsd-complete-phase
</success_criteria>

<output>
After completion, create `.planning/phases/06-trusted-crew-rosters/06-07-SUMMARY.md` capturing: test method count, classes covered, `python manage.py test planner.tests.test_crew_rosters` output (or summary), and confirmation that `python manage.py test planner accounts` is green.
</output>
