# Phase 6: Trusted Crew Rosters — Specification

**Created:** 2026-05-14
**Milestone:** v2.1 — Collaboration & User Management (Phase 1 of milestone)
**Ambiguity score:** 0.115 (gate: ≤ 0.20)
**Requirements:** 8 locked

## Goal

Project owners can define named "crew" rosters (e.g. "Concert team", "Corporate team") of trusted users and bulk-add an entire crew to any project as `ProjectMember` rows — without the email-acceptance round-trip currently required by `accounts.views.accept_invitation`. The existing single-email `Invitation` flow remains untouched for one-off non-crew collaborators.

## Background

**Current state in the codebase:**
- `planner.models.Invitation` (`planner/models.py:3809`) — per-project, per-email invitation row with UUID token, status (pending/accepted/declined/expired), and role (editor/viewer). Created by owner via `/projects/<id>/invite/`.
- `planner.models.ProjectMember` (`planner/models.py:692`) — the actual "user has access to project" row. Populated when an invitee clicks the email link and lands on `accept_invitation` (`accounts/views.py:181`).
- `planner.models.ProjectAccessRequest` (`planner/models.py:720`) — separate inbound-request flow using `Project.invite_token`. Not touched by this phase.
- `send_invitation_email` (`accounts/views.py`, Resend backend) — sends the "click here to accept" email.

**Friction this phase removes:**
Charlie works the same gigs with the same A2/touring crew every week. Every new project today requires (a) the owner typing each email, (b) the system sending an email per invitee, (c) every invitee clicking the link in their inbox before access is granted. For a trusted team of 3–6 engineers spinning up multiple projects per week, this is pure overhead.

**Gap to fill:**
- No "Crew" abstraction exists. The owner has no roster they can manage once and reuse across projects.
- No bulk-add path. Each `ProjectMember` row today goes through `Invitation` → click → accept.
- No pre-onboarding flow. If Charlie adds a new touring engineer's email before they've created a ShowStack account, the existing `Invitation.email` field captures the address but a `ProjectMember` row cannot be created (FK to `User` requires an existing account).

## Requirements

1. **Named crew rosters per owner**: Each owner can create, rename, and delete multiple named crews; a single user can appear in any number of an owner's crews.
   - Current: No `Crew` model exists. Owner can only list users one-at-a-time via the `Invitation` form.
   - Target: New `Crew(owner=User, name=CharField)` model plus a roster-membership model linking `Crew` to `User` (or to a pre-onboarding email placeholder — see Requirement 6). Owner sees `/accounts/crew/` index listing their crews and member counts; can CRUD crews and members from there.
   - Acceptance: An owner with no crews sees an empty state and a "Create crew" button. Creating "Concert team" and "Corporate team" yields two crew rows. The same `User` can be added to both. `unique_together = ('crew', 'user')` prevents duplicate memberships within one crew.

2. **Per-crew default role**: Each crew member has a default role (editor or viewer) used when bulk-adding to projects.
   - Current: `ProjectMember.role` is set from `Invitation.role` at acceptance time. There is no roster-level default.
   - Target: The roster-membership model carries `default_role` (CharField, choices `editor` / `viewer`, default `editor`) — settable when the owner adds the user to the crew and editable from the roster page.
   - Acceptance: Adding Mike to "Concert team" with `default_role='editor'` and to "Corporate team" with `default_role='viewer'` results in two distinct membership rows with the documented roles. Editing a member's default role from the roster page persists the change.

3. **Bulk-add crew to project (no acceptance click)**: Owner can add an entire crew's worth of `ProjectMember` rows to a project in one action, with no email-link click required from members.
   - Current: Every `ProjectMember` row today is created by `accept_invitation` after the invitee clicks the email link. There is no path to create one directly.
   - Target: On the project invite page (`/projects/<id>/invite/`) a new "Add your crew" panel lists the owner's crews. Clicking "Add Concert team" creates one `ProjectMember` row per crew member that does not already belong to the project, using the member's `default_role` from the roster. The view returns a confirmation message of the form "Added N members; M were already on this project."
   - Acceptance: Owner with a 3-member "Concert team" clicks "Add Concert team" on a project where none of the 3 are members → 3 `ProjectMember` rows created with the documented roles, response message shows "Added 3 members; 0 were already on this project." Repeating the click → 0 new rows, message shows "Added 0 members; 3 were already on this project." No `Invitation` rows are created in either case.

4. **Confirmation email after bulk-add**: Each crew member added in a bulk operation receives a single informational email confirming the add — no action required.
   - Current: The email Resend sends today contains an `accept_url` that the invitee must click. There is no "you've been added" notification template.
   - Target: A new email template (subject roughly "You've been added to {project} on ShowStack") sent by the bulk-add view to each member that was actually added (skipped/already-member rows do not receive email). Email body contains owner display name, project name, assigned role, and a direct link into the project — no token, no acceptance step. Existing `send_invitation_email` is not modified.
   - Acceptance: Bulk-adding a 3-member crew triggers exactly 3 outgoing emails (one per new ProjectMember row). Re-running the bulk-add when all members are already on the project triggers 0 emails.

5. **Strictly additive — Invitation flow untouched**: This phase introduces new models, routes, views, and templates only. It does not modify `planner.models.Invitation`, `accept_invitation`, `send_invitation_email`, or any existing invite-form template.
   - Current: `Invitation` model, `accept_invitation` view at `accounts/views.py:181`, and the per-email invite form at `/projects/<id>/invite/` exist and work as documented.
   - Target: All four artifacts above continue to exist unchanged after this phase. Owners can still use the email-invite path for one-off non-crew collaborators (e.g. a client's PM, a freelance system engineer for one show).
   - Acceptance: `git diff` for this phase shows no edits to `planner.models.Invitation` (or its admin), no edits to `accounts.views.accept_invitation`, no edits to `accounts.views.send_invitation_email`, and no edits to the existing `accounts/templates/accounts/invite_user.html` aside from additive insertions for the new "Add your crew" panel (insertion-only — no rewrites of existing form markup).

6. **Pre-onboarding: pending member + auto-claim on register**: Owner can add an email to a crew before that email has a ShowStack account; the user auto-joins the crew (and materializes any pending project memberships) when they later register.
   - Current: There is no way to put an unregistered email into a relationship that resolves automatically at signup. The closest analog is `Invitation.email`, which requires the invitee to click a token link.
   - Target: The roster-membership model accepts EITHER a `user` FK (for existing users) OR an `email` placeholder (for pre-onboarding). When a new user completes registration, the registration view detects any roster-membership rows with `email == new_user.email` and `user__isnull=True`, links them to the new user, and creates `ProjectMember` rows for every project the crew has already been bulk-added to. The owner receives an in-app indicator (e.g. "Mike — pending signup") on the roster page for pre-onboarding rows.
   - Acceptance: Owner adds `newbie@example.com` to "Concert team" → roster shows the row with a "pending signup" badge. Owner clicks "Add Concert team" to a project → no `ProjectMember` row is created for `newbie@example.com` (no `User` yet) but the bulk-add still succeeds for the resolved members. When `newbie@example.com` registers, their account links into the crew automatically AND a `ProjectMember` row materializes for every project the crew has been bulk-added to since they joined.

7. **No-cascade removal**: Removing a user from a crew updates the roster only; it does not drop any existing `ProjectMember` rows.
   - Current: Not applicable — no Crew model exists.
   - Target: The roster page exposes a "Remove from crew" action per member that deletes only the roster-membership row. `ProjectMember` rows that were previously created via this crew remain untouched.
   - Acceptance: With 3 members on "Concert team" and all 3 on Project X, removing one member from "Concert team" → the member's `ProjectMember` row on Project X is unchanged (verified by direct query); only the roster-membership row is deleted. The remove action is gated behind a confirmation prompt that makes the no-cascade behavior explicit ("This removes them from the crew only. To remove them from active projects, manage each project's membership separately.").

8. **Dedupe on bulk-add when user is in multiple crews**: When a user appears in two crews being added to the same project (either via separate clicks or, future-extension, a multi-crew select), only one `ProjectMember` row is created.
   - Current: `ProjectMember` has `unique_together = ['project', 'user']` — duplicate creates already raise IntegrityError. There is no logic above this to skip-or-recover gracefully.
   - Target: The bulk-add view performs a single `Q(project=...) & Q(user__in=crew_member_ids)` query upfront, computes the set of `user_ids` not yet on the project, and creates only those `ProjectMember` rows. No raw IntegrityError can reach the user.
   - Acceptance: Mike is in both "Concert team" and "Corporate team". Bulk-add "Concert team" to Project X (3 rows created). Then bulk-add "Corporate team" to Project X (Mike already a member) → 0 new rows for Mike, view response message reads "Added N members; 1 was already on this project." No exception raised.

## Boundaries

**In scope:**
- New `Crew` model owner-scoped to a `User`, with a `name` CharField.
- New roster-membership model (working name `CrewMember` — final name decided in discuss-phase) linking `Crew` to either an existing `User` or a pending-email placeholder, with `default_role`.
- `/accounts/crew/` index page listing the owner's crews and member counts; create / rename / delete crew actions.
- `/accounts/crew/<crew_id>/` roster page listing members with per-member default role + remove-from-crew action.
- "Add your crew" panel on the existing project invite page (`/projects/<id>/invite/`) — additive markup only.
- Bulk-add view that creates `ProjectMember` rows (skipping already-members) and sends one confirmation email per new row.
- New "you've been added to {project}" email template sent via Resend (separate template from the existing acceptance-link template).
- Pre-onboarding placeholder rows + auto-claim hook in the registration view.
- Audit: `ProjectMember.invited_by` populated with the owner, `ProjectMember.invited_at` populated with `now()` on every bulk-add row (reuses existing fields).
- Migration: additive only (new tables for `Crew` and the roster-membership model; no edits to existing tables).

**Out of scope:**
- Per-project role override at bulk-add time — owner cannot override the crew default for a single project in this phase. (Adding it later is a clean migration: add `ProjectMember.crew_role_override` and tweak the bulk-add view. Out of scope to keep scope tight.)
- Removing crew membership cascading into `ProjectMember` deletion — explicit no-cascade by design (see Requirement 7).
- Cross-owner crew sharing — Crew is owner-scoped. Owner A cannot use owner B's crews. (Future feature; would require an org/workspace model that doesn't exist.)
- Editing existing `Invitation` model or `accept_invitation` view — strict additivity is a phase-level requirement (Requirement 5).
- Subsuming the `ProjectAccessRequest` invite-by-link flow at `planner/models.py:720` — separate feature.
- Bulk REMOVE crew from project — only bulk-ADD lands in this phase. (Bulk-remove can be done one click at a time via the existing project-members admin.)
- "Add multiple crews at once" / multi-select on the project page — single-crew bulk-add only this phase.
- Crew-level audit log / activity history — `invited_by` + `invited_at` per row is the audit shape; no separate event table.
- Mobile interface (`/m/`) parity — desktop / admin web UI only this phase.

## Constraints

- **No new external dependencies.** All work uses Django 5.x + Resend (already in `requirements.txt`). No new email-template engine, no Celery, no async workers — bulk-add is synchronous in-request (acceptable because crews are small — order 1–10 members).
- **Migration must be additive.** Per Requirement 5, no edits to existing tables. New tables only.
- **Confirmation emails must respect Resend rate limits.** For a typical 3–6 member bulk-add this is a non-issue. For a hypothetical 50+ member crew, a single bulk-add issues N emails synchronously; if that becomes a problem in practice, future phase can move email sends to a queue (out of scope here).
- **Pre-onboarding email lookup is case-insensitive.** Standard Django `iexact` matching when auto-claiming on register (mirrors the case-insensitive lookup already in `accept_invitation` at `accounts/views.py:207`).
- **Crew is owner-scoped.** Only the project owner can add a crew to their own project. Editor/viewer collaborators cannot use the bulk-add UI even if they have admin permission elsewhere. Mirrors the existing `if project.owner != request.user` gate at `accounts/views.py:129`.

## Acceptance Criteria

- [ ] An owner can create at least 2 named crews from `/accounts/crew/`, add 3 existing users to one of them with `default_role='editor'`, and see both rosters listed correctly with member counts.
- [ ] On a project page with no existing members, clicking "Add Concert team" creates exactly 3 `ProjectMember` rows with `role='editor'`, `invited_by=owner`, `invited_at≈now()`. Zero `Invitation` rows are created.
- [ ] Each of the 3 added members receives exactly one informational email (subject contains the project name; body has no `accept_url` token link).
- [ ] Re-clicking "Add Concert team" on the same project creates 0 new `ProjectMember` rows; response message reads "Added 0 members; 3 were already on this project." Zero new outgoing emails.
- [ ] Removing one user from "Concert team" via the roster page deletes only the roster-membership row; the `ProjectMember` row on the previously-bulk-added project is unchanged (verified by `ProjectMember.objects.filter(project=..., user=...).exists() == True` after the remove).
- [ ] `git diff phase-start..HEAD -- planner/models.py | grep -E "^[+-].*Invitation"` shows zero matches — `Invitation` model untouched.
- [ ] `git diff phase-start..HEAD -- accounts/views.py` shows no edits to the `accept_invitation` function body.
- [ ] A user added to two of the owner's crews (e.g. Mike in both "Concert team" and "Corporate team") who is bulk-added via both crews to the same project results in exactly ONE `ProjectMember` row (no IntegrityError raised, no duplicate).
- [ ] Pre-onboarding HUMAN-UAT (acceptable as manual smoke, not automated CI gate for this phase): owner adds `unregistered@example.com` to a crew → roster shows "pending signup" badge → owner bulk-adds the crew to a project → unregistered email registers → on first login, the new user has a `ProjectMember` row for that project.
- [ ] `python manage.py check` exits 0.
- [ ] `python manage.py test planner accounts` exits 0 with no regressions in the existing test suite.

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                    |
|--------------------|-------|------|--------|----------------------------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | Bulk-add behavior, role source, notification all locked |
| Boundary Clarity   | 0.92  | 0.70 | ✓      | Strictly-additive perimeter + explicit out-of-scope list |
| Constraint Clarity | 0.85  | 0.65 | ✓      | Additive migration, sync sends, owner-scoped, no deps    |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 11 pass/fail criteria; pre-onboarding is HUMAN-UAT       |
| **Ambiguity**      | 0.115 | ≤0.20| ✓      | All dimensions over minimum                              |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption).

## Interview Log

| Round | Perspective       | Question summary                                          | Decision locked                                                                 |
|-------|-------------------|-----------------------------------------------------------|--------------------------------------------------------------------------------|
| 0     | (positioning)     | v2.0 closed — where does Trusted Crew live?              | Start v2.1 milestone (Collaboration & User Management); this is Phase 1 of v2.1 |
| 1     | Researcher        | Notification model after bulk-add?                        | Confirmation email after add (informational; no `accept_url`)                  |
| 1     | Researcher        | Role assignment at bulk-add time?                         | Default role from the crew roster (set per-member when added to crew)          |
| 1     | Researcher        | Existing Invitation flow touched by this phase?           | Strictly additive — Invitation model + accept_invitation view untouched        |
| 2     | Simplifier        | Pre-onboarding: email not yet a ShowStack user?           | Pending-member placeholder + auto-claim on register                            |
| 2     | Failure Analyst   | Bulk-add hits user already on project?                    | Skip silently, show "Added N; M already on project" count                      |
| 2     | Failure Analyst   | Audit trail on crew-added ProjectMember rows?             | Reuse existing `invited_by` + `invited_at` fields (no new audit table)         |
| 3     | Boundary Keeper   | Remove from crew — cascade into project memberships?      | No cascade — roster delete only; existing ProjectMember rows untouched         |
| 3     | Boundary Keeper   | Same user in multiple crews — allowed?                    | Yes, allowed; bulk-add dedupes via upfront user_id set query                   |
| 3     | Boundary Keeper   | Minimum demo path that proves the phase is shipped?       | Bulk-add existing users (pre-onboarding ships but is HUMAN-UAT, not CI gate)  |

---

*Phase: 06-trusted-crew-rosters*
*Spec created: 2026-05-14*
*Next step: /gsd-discuss-phase 6 — implementation decisions (model names, model relationship shape, email template wording, UI panel layout, registration auto-claim hook location)*
