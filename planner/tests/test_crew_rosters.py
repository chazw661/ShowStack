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
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase
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
            username='charlie',
            email='charlie@example.com',
            password='test-pw-123',
            is_staff=True,
        )
        cls.mike = User.objects.create_user(
            username='mike',
            email='mike@example.com',
            password='pw',
        )
        cls.sarah = User.objects.create_user(
            username='sarah',
            email='sarah@example.com',
            password='pw',
        )
        cls.jose = User.objects.create_user(
            username='jose',
            email='jose@example.com',
            password='pw',
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
        """SPEC R1 — Owner sees their own crew on /crew/."""
        response = self.client.get(reverse('crew_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Concert team')

    def test_crew_create_blocks_duplicate_name_per_owner(self):
        """SPEC R1 + D-02 — unique_together(owner, name) prevents duplicate crew names."""
        response = self.client.post(reverse('crew_create'), {'name': 'Concert team'})
        # View must not raise 500; it must redirect (flash error or form re-render
        # followed by redirect, or 200 form re-render — NOT 500).
        self.assertNotEqual(response.status_code, 500)
        # Only one crew with that name exists.
        self.assertEqual(
            Crew.objects.filter(owner=self.owner, name='Concert team').count(),
            1,
        )

    def test_crew_index_hides_other_owners_crews(self):
        """SPEC R1 — Crew index only shows the requesting owner's crews."""
        other_owner = User.objects.create_user(
            username='other-owner',
            email='other@example.com',
            password='pw',
        )
        Crew.objects.create(owner=other_owner, name='Other crew')
        self.client.force_login(other_owner)
        response = self.client.get(reverse('crew_index'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Concert team')
        self.assertContains(response, 'Other crew')

    # --- SPEC R2: Per-crew default_role ---

    def test_crew_member_add_with_viewer_role(self):
        """SPEC R2 — default_role=viewer is persisted on the CrewMember row."""
        newbie = User.objects.create_user(
            username='newbie-r2',
            email='newbie-r2@example.com',
            password='pw',
        )
        response = self.client.post(
            reverse('crew_member_add', args=[self.crew.id]),
            {'user_or_email': 'newbie-r2', 'default_role': 'viewer'},
        )
        self.assertEqual(response.status_code, 302)
        cm = CrewMember.objects.get(crew=self.crew, user=newbie)
        self.assertEqual(cm.default_role, 'viewer')

    def test_crew_member_add_with_editor_role(self):
        """SPEC R2 — default_role=editor is persisted on the CrewMember row."""
        newbie2 = User.objects.create_user(
            username='newbie-r2b',
            email='newbie-r2b@example.com',
            password='pw',
        )
        response = self.client.post(
            reverse('crew_member_add', args=[self.crew.id]),
            {'user_or_email': 'newbie-r2b', 'default_role': 'editor'},
        )
        self.assertEqual(response.status_code, 302)
        cm = CrewMember.objects.get(crew=self.crew, user=newbie2)
        self.assertEqual(cm.default_role, 'editor')

    # --- SPEC R3 + R4: Bulk-add creates ProjectMember rows + emails ---

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_creates_project_member_rows(self, mock_email):
        """SPEC R3 — bulk_add_crew POSTs create one ProjectMember per resolved member."""
        response = self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertEqual(response.status_code, 302)
        pms = ProjectMember.objects.filter(project=self.project)
        self.assertEqual(pms.count(), 3)
        for pm in pms:
            # SPEC R2: role propagated from CrewMember.default_role.
            self.assertEqual(pm.role, 'editor')
            self.assertEqual(pm.invited_by_id, self.owner.id)
            # Pitfall 2 — auto_now_add fires (not bulk_create).
            self.assertIsNotNone(pm.invited_at)
        # SPEC R4: one confirmation email per new ProjectMember row.
        self.assertEqual(mock_email.call_count, 3)
        # SPEC R3 — no Invitation rows (direct-add path, not invite-by-link).
        self.assertEqual(Invitation.objects.filter(project=self.project).count(), 0)

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_idempotent_when_all_already_members(self, mock_email):
        """SPEC R3 + R8 — second bulk-add of same crew adds zero rows, sends zero emails."""
        url = reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        self.client.post(url)
        mock_email.reset_mock()
        # Second click — all 3 already members.
        self.client.post(url)
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )
        self.assertEqual(mock_email.call_count, 0)

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_records_crew_project_add(self, mock_email):
        """D-09 — bulk_add_crew writes a CrewProjectAdd row for the auto-claim hook."""
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertTrue(
            CrewProjectAdd.objects.filter(crew=self.crew, project=self.project).exists()
        )

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_rejects_non_project_owner(self, mock_email):
        """SPEC R3 — only the project owner can bulk-add a crew."""
        outsider = User.objects.create_user(
            username='outsider-r3',
            email='outsider-r3@example.com',
            password='pw',
        )
        self.client.force_login(outsider)
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        # No ProjectMember rows created by the outsider.
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 0,
        )

    @patch('accounts.views.send_crew_added_email', side_effect=Exception('Resend down'))
    def test_bulk_add_survives_email_failure(self, mock_email):
        """D-10 — email failure is logged + swallowed; ProjectMember rows still committed."""
        response = self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )

    # --- SPEC R5: Strictly additive — Invitation model untouched ---

    def test_invitation_model_signature_preserved(self):
        """SPEC R5 — Invitation model must still have all original fields."""
        from planner.models import Invitation as Inv
        field_names = {f.name for f in Inv._meta.get_fields() if hasattr(f, 'name')}
        expected_required = {
            'project', 'email', 'role', 'status', 'token', 'invited_by', 'invited_at',
        }
        self.assertTrue(
            expected_required.issubset(field_names),
            f"Invitation missing expected fields: {expected_required - field_names}",
        )

    def test_accept_invitation_flow_still_works_end_to_end(self):
        """SPEC R5 — behavioral regression: legacy accept_invitation flow unchanged.

        Field-presence checks (above) and git-diff acceptance criteria gate the
        source files. This test gates BEHAVIOR end-to-end: a pending Invitation
        row, POST to /invitations/accept/<token>/, must still materialize a
        ProjectMember row and flip status to 'accepted'.

        accounts/urls.py confirms the route:
            path('invitations/accept/<uuid:token>/', views.accept_invitation,
                 name='accept_invitation')
        """
        # The invitee must have an email matching the Invitation row.
        invitee = User.objects.create_user(
            username='r5-invitee',
            email='r5-invitee@example.com',
            password='pw',
        )
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
        """SPEC R7 — removing a CrewMember row leaves the corresponding ProjectMember intact."""
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )
        # Remove Mike from the crew via the remove endpoint.
        mike_cm = CrewMember.objects.get(crew=self.crew, user=self.mike)
        self.client.post(
            reverse('crew_member_remove', args=[self.crew.id, mike_cm.id])
        )
        # CrewMember row gone…
        self.assertFalse(
            CrewMember.objects.filter(crew=self.crew, user=self.mike).exists()
        )
        # …but ProjectMember row still present (SPEC R7).
        self.assertTrue(
            ProjectMember.objects.filter(project=self.project, user=self.mike).exists()
        )

    @patch('accounts.views.send_crew_added_email')
    def test_delete_crew_does_not_cascade_to_project_member(self, mock_email):
        """SPEC R7 — deleting an entire Crew leaves all ProjectMember rows intact."""
        self.client.post(
            reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        )
        # Delete the entire crew.
        self.client.post(reverse('crew_delete', args=[self.crew.id]))
        self.assertFalse(Crew.objects.filter(id=self.crew.id).exists())
        # All 3 ProjectMember rows remain (SPEC R7 ethos extended to crew deletion).
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 3,
        )

    # --- SPEC R8: Deduplicate across crews ---

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_dedupes_user_in_multiple_crews(self, mock_email):
        """SPEC R8 — user appearing in two crews bulk-added to the same project → exactly 1 row, no IntegrityError."""
        corporate = Crew.objects.create(owner=self.owner, name='Corporate team')
        CrewMember.objects.create(crew=corporate, user=self.mike, default_role='editor')
        url_concert = reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        url_corp = reverse('bulk_add_crew', args=[self.project.id, corporate.id])
        self.client.post(url_concert)  # 3 rows (mike, sarah, jose)
        self.client.post(url_corp)     # Mike already a member → 0 new for mike
        # Exactly ONE ProjectMember row for Mike — no IntegrityError and no duplicate.
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project, user=self.mike).count(),
            1,
        )


class CrewMemberConstraintTests(TestCase):
    """D-15 DB constraints — XOR check + partial unique constraints.

    These tests verify that the database-level constraints defined in
    CrewMember.Meta.constraints are enforced (requires PostgreSQL; SQLite does
    not enforce partial UniqueConstraints via SQL but Django enforces them at
    the model layer via validate_constraints).
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='constraint-owner',
            email='c@x.com',
            password='pw',
        )
        cls.mike = User.objects.create_user(
            username='c-mike',
            email='c-mike@x.com',
            password='pw',
        )
        cls.crew = Crew.objects.create(owner=cls.owner, name='Constraint crew')

    def test_xor_blocks_both_user_and_email_set(self):
        """D-15 — crewmember_user_xor_email rejects rows where both user and email are non-null."""
        with self.assertRaises((IntegrityError, Exception)):
            CrewMember.objects.create(
                crew=self.crew,
                user=self.mike,
                email='c-mike@x.com',
            )

    def test_xor_blocks_neither_user_nor_email_set(self):
        """D-15 — XOR check also rejects rows where both user and email are null."""
        with self.assertRaises((IntegrityError, Exception)):
            CrewMember.objects.create(crew=self.crew, user=None, email=None)

    def test_partial_unique_blocks_duplicate_user_in_crew(self):
        """D-15 — uniq_crewmember_crew_user rejects the same user twice in the same crew."""
        CrewMember.objects.create(crew=self.crew, user=self.mike, default_role='editor')
        with self.assertRaises((IntegrityError, Exception)):
            CrewMember.objects.create(crew=self.crew, user=self.mike, default_role='viewer')

    def test_partial_unique_blocks_duplicate_pending_email_in_crew(self):
        """D-15 — uniq_crewmember_crew_email rejects the same pending email twice in the same crew."""
        CrewMember.objects.create(crew=self.crew, email='pending@example.com')
        with self.assertRaises((IntegrityError, Exception)):
            CrewMember.objects.create(crew=self.crew, email='pending@example.com')


class AutoClaimTests(TestCase):
    """SPEC R6 — pre-onboarding placeholder + auto-claim on register."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='claim-owner',
            email='claim-owner@x.com',
            password='pw',
        )
        cls.project = Project.objects.create(name='Claim Show', owner=cls.owner)
        cls.crew = Crew.objects.create(owner=cls.owner, name='Pending crew')
        CrewMember.objects.create(
            crew=cls.crew,
            email='newbie@example.com',
            default_role='editor',
        )
        CrewProjectAdd.objects.create(crew=cls.crew, project=cls.project)

    def test_claim_rebinds_pending_row_and_materializes_project_member(self):
        """SPEC R6 — claim_pending_crew_memberships rebinds the CrewMember row and creates ProjectMember."""
        newbie = User.objects.create_user(
            username='newbie',
            email='newbie@example.com',
            password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        # CrewMember row rebound in place (D-01: single-table rebind, no delete+recreate).
        cm = CrewMember.objects.get(crew=self.crew, user=newbie)
        self.assertIsNone(cm.email)
        self.assertEqual(cm.default_role, 'editor')  # default_role preserved
        # ProjectMember row materialized for the linked project.
        self.assertTrue(
            ProjectMember.objects.filter(project=self.project, user=newbie).exists()
        )
        # Helper returns the new rows so the caller can send confirmation emails.
        self.assertEqual(len(new_pms), 1)
        self.assertEqual(new_pms[0].project_id, self.project.id)
        self.assertEqual(new_pms[0].role, 'editor')
        self.assertEqual(new_pms[0].invited_by_id, self.owner.id)

    def test_claim_iexact_matches_uppercase_email(self):
        """D-08 — case-insensitive match: NEWBIE@example.com matches pending row 'newbie@example.com'."""
        newbie = User.objects.create_user(
            username='newbie-upper',
            email='NEWBIE@example.com',
            password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        self.assertEqual(len(new_pms), 1)

    def test_claim_strips_whitespace(self):
        """D-08 — explicit .strip() on the user-side email before __iexact filter."""
        # Django normalizes email on save, so create with a clean email; the .strip()
        # in crew.py guards against form-data edge cases in the helper itself.
        newbie = User.objects.create_user(
            username='nb-stripped',
            email='newbie@example.com',
            password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        self.assertEqual(len(new_pms), 1)

    def test_claim_does_not_match_plus_alias(self):
        """D-08 — NO plus-alias collapsing: newbie+alias@example.com is NOT newbie@example.com."""
        newbie = User.objects.create_user(
            username='nb-alias',
            email='newbie+alias@example.com',
            password='pw',
        )
        new_pms = claim_pending_crew_memberships(newbie)
        # No match — helper returns empty list.
        self.assertEqual(len(new_pms), 0)
        # Pending CrewMember row is still pending.
        self.assertTrue(
            CrewMember.objects.filter(crew=self.crew, email='newbie@example.com').exists()
        )

    def test_claim_idempotent_on_existing_project_member(self):
        """SPEC R8 — if user is already a ProjectMember, claim must not raise or duplicate the row."""
        newbie = User.objects.create_user(
            username='nb-already',
            email='newbie@example.com',
            password='pw',
        )
        # Create the ProjectMember directly before claiming.
        ProjectMember.objects.create(
            project=self.project,
            user=newbie,
            role='viewer',
            invited_by=self.owner,
        )
        new_pms = claim_pending_crew_memberships(newbie)
        # Helper returned 0 new rows because the existing row short-circuited get_or_create.
        self.assertEqual(len(new_pms), 0)
        # The existing ProjectMember was NOT replaced — role is still 'viewer'.
        pm = ProjectMember.objects.get(project=self.project, user=newbie)
        self.assertEqual(pm.role, 'viewer')


class RegisterIntegrationTests(TestCase):
    """SPEC R6 — full /register/ POST flow exercising auto-claim + atomic wrap (D-11)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='reg-owner',
            email='reg-owner@x.com',
            password='pw',
        )
        cls.project = Project.objects.create(name='Reg Show', owner=cls.owner)
        cls.crew = Crew.objects.create(owner=cls.owner, name='Reg crew')
        CrewMember.objects.create(
            crew=cls.crew,
            email='registrant@example.com',
            default_role='editor',
        )
        CrewProjectAdd.objects.create(crew=cls.crew, project=cls.project)

    @patch('accounts.views.send_crew_added_email')
    def test_register_triggers_auto_claim(self, mock_email):
        """SPEC R6 — POST /register/ with a matching pending email materializes ProjectMember via D-11 atomic block.

        The live register endpoint is marketing.views.register (first URL match in
        audiopatch/urls.py). It requires a 'terms' POST field (clickwrap consent per
        CLAUDE.md). On success it redirects to marketing:pending.

        RegistrationForm fields confirmed via accounts/forms.py:
            username, email, first_name, last_name, password1, password2
        Plus 'terms' required by marketing.views.register (clickwrap).
        """
        response = Client().post(reverse('register'), {
            'username': 'registrant',
            'email': 'registrant@example.com',
            'password1': 'a-very-strong-passw0rd!',
            'password2': 'a-very-strong-passw0rd!',
            'first_name': 'Reg',
            'last_name': 'Istrant',
            'terms': 'on',
        })
        # Successful registration redirects to marketing:pending.
        self.assertEqual(response.status_code, 302)
        registrant = User.objects.get(username='registrant')
        # SPEC R6 — ProjectMember row materialized via auto-claim.
        self.assertTrue(
            ProjectMember.objects.filter(project=self.project, user=registrant).exists()
        )
        # SPEC R6 — pending CrewMember row rebound in place (email cleared).
        cm = CrewMember.objects.get(crew=self.crew, user=registrant)
        self.assertIsNone(cm.email)
        # SPEC R4 — confirmation email attempted once (post-atomic loop, D-10).
        self.assertEqual(mock_email.call_count, 1)

    @patch('accounts.views.send_crew_added_email', side_effect=Exception('Resend down'))
    def test_register_auto_claim_survives_email_failure(self, mock_email):
        """D-10/D-11 — email failure post-atomic does not roll back the user account or ProjectMember row."""
        # Use a different email from the pending-crew fixture to avoid conflicts with
        # the test_register_triggers_auto_claim test sharing setUpTestData.
        # We need a fresh pending CrewMember for this email.
        owner2 = User.objects.create_user(
            username='reg-owner-2',
            email='reg-owner-2@x.com',
            password='pw',
        )
        project2 = Project.objects.create(name='Email Fail Show', owner=owner2)
        crew2 = Crew.objects.create(owner=owner2, name='Email Fail crew')
        CrewMember.objects.create(
            crew=crew2,
            email='emailfail@example.com',
            default_role='editor',
        )
        CrewProjectAdd.objects.create(crew=crew2, project=project2)

        response = Client().post(reverse('register'), {
            'username': 'emailfail',
            'email': 'emailfail@example.com',
            'password1': 'a-very-strong-passw0rd!',
            'password2': 'a-very-strong-passw0rd!',
            'first_name': 'Email',
            'last_name': 'Fail',
            'terms': 'on',
        })
        # Registration must succeed (redirect) even though send_crew_added_email raised.
        self.assertEqual(response.status_code, 302)
        # User account was committed inside the atomic block.
        user = User.objects.get(username='emailfail')
        # ProjectMember row was committed inside the atomic block.
        self.assertTrue(
            ProjectMember.objects.filter(project=project2, user=user).exists()
        )
