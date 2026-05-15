# Phase 6: Trusted Crew Rosters - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Owner-defined named crew rosters and one-click bulk-add of an entire crew to a project as `ProjectMember` rows — bypassing the existing email-acceptance round-trip for repeat collaborators. The existing single-email `Invitation` flow stays intact and untouched for one-off non-crew invites.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**8 requirements are locked.** See `06-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `06-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- New `Crew` model (owner-scoped, `name` CharField) and `CrewMember` (roster-membership) model
- `/accounts/crew/` index page + `/accounts/crew/<crew_id>/` roster page (CRUD)
- "Add your crew" panel on `/projects/<id>/invite/` — additive markup only
- Bulk-add view creating `ProjectMember` rows (skip-existing) + one confirmation email per new row
- New "you've been added to {project}" email template (separate from existing acceptance-link email)
- Pre-onboarding placeholder rows + auto-claim hook in registration view
- Audit: `ProjectMember.invited_by` + `invited_at` populated on every bulk-add row
- Migration: additive only (new tables, no edits to existing)

**Out of scope (from SPEC.md):**
- Per-project role override at bulk-add time
- Cascade removal from crew → ProjectMember (explicit no-cascade by design)
- Cross-owner crew sharing
- Edits to `Invitation` model or `accept_invitation` view (strict additivity)
- Subsuming `ProjectAccessRequest` invite-by-link flow
- Bulk REMOVE crew from project (only bulk-ADD lands this phase)
- "Add multiple crews at once" / multi-select picker
- Crew-level audit log / activity history
- Mobile interface (`/m/`) parity

</spec_lock>

<decisions>
## Implementation Decisions

### Model Shape

- **D-01: Single `CrewMember` table with nullable user + nullable email.**
  One table accepts both existing-user rows and pending-email rows.
  - `user` is a nullable FK to `auth.User`
  - `email` is a nullable `EmailField`
  - DB CHECK constraint: exactly one of `user` or `email` is non-null per row (researcher will pick the cleanest Postgres-compatible syntax — Django `CheckConstraint` with `Q` expression)
  - On auto-claim (Requirement 6 from SPEC), the row UPDATES IN PLACE: `email` → `NULL`, `user` → new User FK. No row delete + recreate (preserves `default_role` and any future audit fields).
  - Roster reads use a single query: `crew.crewmember_set.select_related('user').all()` — pending members surface alongside existing-user members.

- **D-02: Crew model is minimal: `owner` FK + `name` CharField + standard timestamps.**
  - Per-member default role lives on `CrewMember.default_role` (CharField, choices `editor`/`viewer`, default `editor`).
  - Crew has no crew-level default role and no color/icon — Future enhancement out of scope this phase.
  - `unique_together = ('owner', 'name')` so an owner can't have two crews with the same name.
  - `CrewMember.unique_together = ('crew', 'user')` for existing-user rows AND `('crew', 'email')` for pending rows (researcher: confirm Django can express both `unique_together` constraints simultaneously, or use a partial unique index).

### UI Placement & Navigation

- **D-03: `/accounts/crew/` is the index URL — new top-level route under the accounts app.**
  - Auth-gated via `@login_required`. Owner-only views check `request.user == project.owner` for any project-touching action.
  - Templates live in the existing pattern: `accounts/templates/accounts/crew_index.html`, `crew_detail.html` (matches `register.html`, `invite_user.html` neighbors).
  - NOT under Django admin — this is a first-class user-facing feature, not a power-user backstage tool.
  - Routes: `/accounts/crew/` (index), `/accounts/crew/new/` (create), `/accounts/crew/<crew_id>/` (detail/edit/delete), `/accounts/crew/<crew_id>/members/add/` (add member), `/accounts/crew/<crew_id>/members/<member_id>/remove/` (remove). Final URL names finalized in planning.

- **D-04: Nav surface is the top-right user menu, next to logout.**
  - Add a "My Crew" link to whatever template renders the top-right user dropdown (researcher: locate that template — likely a header partial in `templates/` or `accounts/templates/accounts/`).
  - NO dashboard card alongside the audio modules — keeps the dashboard focused on audio production surfaces.

### "Add your crew" Panel Layout

- **D-05: Stacked layout on `/projects/<id>/invite/`. Existing email form stays at top; new panel below.**
  - Below the existing form, render one card per crew the owner has.
  - Each card displays: crew name, total member count, full member list (e.g. "Mike, Sarah, Jose, +newbie@example.com (pending)"), and an "Add this crew" button.
  - Members already on the project are visually greyed/struck (planner: pick the exact visual treatment) so the owner sees what the click will and won't add.
  - Pending-email members (no User FK yet) are tagged with a "pending signup" pill on the crew detail page AND on the invite page card.
  - Markup is additive — no rewrites of the existing invite-form markup (SPEC Requirement 5).

- **D-06: Single-click bulk-add. No confirmation modal. Result is a confirmation banner.**
  - Clicking "Add this crew" POSTs to the new bulk-add endpoint (URL TBD by planner — likely `/projects/<id>/invite/add-crew/<crew_id>/` or similar) → redirect back to the invite page → flash message: `"Added {N} members from {crew_name}; {M} were already on this project."`
  - Per-member email confirmation sent server-side as part of the same request, synchronously (SPEC Constraint: no Celery, crews are small, ~1–10 members).
  - Eligible-member computation happens server-side BEFORE the POST so the button on the card is disabled / hidden when N would be 0.

### Auto-Claim Hook

- **D-07: Inline call in `register()` view body at `accounts/views.py:27` (after `form.save()` returns the new User).**
  - Implementation: a dedicated helper (working name `claim_pending_crew_memberships(user)`) in a new module (researcher: likely `planner/crew.py` or `accounts/crew_claim.py` — pick based on which app owns Crew/CrewMember).
  - Helper does:
    1. Look up all `CrewMember.objects.filter(user__isnull=True, email__iexact=user.email.strip())` (case-insensitive, whitespace-stripped per D-08).
    2. For each match, set `user=user`, `email=None`, save.
    3. For every project the crew has been bulk-added to, create a `ProjectMember` row for the new user if one doesn't already exist (`get_or_create` against `(project, user)` to avoid IntegrityError).
    4. Fire confirmation emails for the newly-materialized `ProjectMember` rows (same template as Requirement 4).
  - NO Django signals — register() is the single, visible, testable entry point.
  - Helper is unit-testable directly without an HTTP request (just instantiate a User + pending CrewMember + bulk-added Project, call helper, assert).

- **D-08: Email match strictness — case-insensitive + whitespace strip, no provider-specific normalization.**
  - `user.email.strip().lower() == pending.email.strip().lower()`
  - Implemented via Django `__iexact` lookup (which already lowercases) plus an explicit `.strip()` on the user-side value before passing to `filter()`.
  - Pending-email rows have their `email` field stored as the owner typed it; the helper trims at compare-time.
  - No gmail dot-stripping, no `+alias` collapsing — too surprising for users who legitimately use plus addressing.

### Post-Research Locks (added 2026-05-14 after RESEARCH.md surfaced open questions)

- **D-09: Add a `CrewProjectAdd` link table to track which projects each crew has been bulk-added to.**
  - 3 fields: `crew` FK, `project` FK, `added_at` (auto_now_add).
  - `unique_together = ('crew', 'project')` — re-clicking "Add this crew" updates nothing in this table (idempotent).
  - Populated by the bulk-add view as part of the same atomic write that creates `ProjectMember` rows.
  - Auto-claim helper reads this table to find every project to materialize `ProjectMember` rows for.
  - Lives in `planner/models.py` alongside `Crew` and `CrewMember`.

- **D-10: Email-send failure during bulk-add is logged and swallowed.**
  - Contract is "ProjectMember rows exist." Resend dashboard surfaces per-recipient failures.
  - Wrap each `send_crew_added_email(...)` call in try/except Exception with a `logger.exception(...)` and continue.
  - Bulk-add returns success even if 0 of N emails actually sent.
  - Diverges from `send_invitation_email`'s re-raise behavior — but that path is interactive (user clicks "Send invite", expects feedback); bulk-add is bulk and durable.

- **D-11: `register()` wraps `form.save()` + `claim_pending_crew_memberships(user)` in a single `transaction.atomic()`.**
  - All-or-nothing — if the claim helper raises, the new User row is rolled back too.
  - Avoids the confusing "account exists but no crew claim happened" half-state.
  - Confirmation email sends from the helper happen INSIDE the atomic block but per D-10 are wrapped in try/except so an email hiccup never rolls back the user account.

- **D-12: "My Crew" link in the top-right user menu is always visible for logged-in users.**
  - The `/accounts/crew/` index page handles the empty state with a "Create your first crew" CTA.
  - Mirrors the existing dashboard "free-account" gating pattern.
  - Two insertion surfaces per RESEARCH.md: `templates/admin/base_site.html` (admin chrome `userlinks` block) AND `templates/accounts/dashboard.html` (`.header-right` div). Both edits are additive.

- **D-13: Models live in `planner/models.py`, not `accounts/models.py`.**
  - Matches the existing pattern: `ProjectMember`, `Invitation`, `ProjectAccessRequest` all live in `planner/models.py` despite views in `accounts/`.
  - `accounts/models.py` is a 3-line empty stub — leave it alone.
  - Auto-claim helper lives at `planner/crew.py` (alongside the models).

- **D-14: Templates live in project-level `templates/accounts/`, NOT `accounts/templates/accounts/`.**
  - RESEARCH.md confirms the latter does not exist on disk.
  - Phase 6's new templates land in `templates/accounts/crew_index.html` and `templates/accounts/crew_detail.html`.
  - The invite-page additive panel edits `templates/accounts/invite_user.html` (insertion point ~line 220 per RESEARCH.md).

- **D-15: Use Django 5.2 `condition=` (not deprecated `check=`) on CheckConstraint, and partial `UniqueConstraint(condition=Q(...))` (not `unique_together`) where any column is nullable.**
  - `CrewMember` Meta.constraints contains:
    - `CheckConstraint(condition=Q(user__isnull=False, email__isnull=True) | Q(user__isnull=True, email__isnull=False), name="crewmember_user_xor_email")`
    - `UniqueConstraint(fields=["crew", "user"], condition=Q(user__isnull=False), name="uniq_crewmember_crew_user")`
    - `UniqueConstraint(fields=["crew", "email"], condition=Q(email__isnull=False), name="uniq_crewmember_crew_email")`
  - `Crew` keeps `unique_together = (("owner", "name"),)` — fine because both fields are non-nullable.

### Stale Reference Corrections (from RESEARCH.md — supersedes earlier line numbers in this file)

- `accounts/views.py` line numbers in this CONTEXT.md predate the current file. Use the corrected positions: `register()` at line **16**, `invite_user` owner-check at line **129**, `accept_invitation` at line **181**, `send_invitation_email` at line **241** (NOT 252), `set_project` at line **359**.
- Template directory: project-level `templates/accounts/` is canonical; `accounts/templates/accounts/` does NOT exist. Pattern-mapper and planner must use the project-level path.

### Claude's Discretion

- **Confirmation email HTML/template:** Model after the existing inline-HTML pattern in `accounts/views.py:send_invitation_email` (line 241). One short template, no `accept_url` token, brand-consistent. Researcher/planner picks final wording. Subject line: "{owner.first_name} added you to {project.name} on ShowStack" or similar — owner-friendly.
- **Admin registration:** Register `Crew` + `CrewMember` on `showstack_admin_site` per CLAUDE.md convention so superuser can audit. Update `admin_ordering.py` for the new models (per CLAUDE.md). User-facing UI is the custom `/accounts/crew/` pages — admin is for power use only.
- **Exact button labels, microcopy, CSS:** Match existing project visual language (dark theme, `ss-card` styling pattern seen in `templates/admin/index.html`). Planner picks.
- **Bulk-add URL shape:** `POST /projects/<id>/invite/add-crew/<crew_id>/` is the suggested shape but planner finalizes per existing accounts URL conventions.
- **Test fixture shape:** Mirror `accounts/test_*.py` patterns (if any exist) or follow `planner/tests/test_channel_record_defaults.py` Phase 5 style: `setUpTestData` for owner/crew/project plumbing, per-test variations.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 6 Spec
- `.planning/phases/06-trusted-crew-rosters/06-SPEC.md` — Locked requirements (8), boundaries, acceptance criteria. MUST read before planning.

### Project-Level
- `CLAUDE.md` — Project instructions; especially the rules:
  - "Always register models on `showstack_admin_site`, NOT `admin.site`"
  - "Update `admin_ordering.py` whenever a new admin-registered model is added"
  - Email is via Resend; secrets in `.env` (gitignored)
  - "Solo dev typically goes straight to main; use feature branches only when work is risky or spans multiple sessions"
- `.planning/PROJECT.md` — Project vision and core value
- `.planning/REQUIREMENTS.md` — Project-wide requirements

### Existing Code Patterns to Mirror
- `accounts/views.py:181` — `accept_invitation` view (DO NOT MODIFY — strict additivity per SPEC Requirement 5). Pattern reference for permission gating and message-framework usage.
- `accounts/views.py:252` — `send_invitation_email` inline-HTML template pattern (model the new "you've been added" email after this).
- `accounts/views.py:16` — `register()` view (the auto-claim hook insertion point per D-07).
- `accounts/views.py:129` — `if project.owner != request.user` pattern (mirror this guard on bulk-add view).
- `planner/models.py:3809` — `Invitation` model (reference shape for token, status, role choices — but DO NOT MODIFY).
- `planner/models.py:692` — `ProjectMember` model (the row created by bulk-add; already has `invited_by` + `invited_at` we reuse per SPEC Requirement 3).
- `planner/admin_ordering.py` — Update with new admin-registered models per CLAUDE.md.
- `planner/admin_site.py` — `showstack_admin_site` registration target.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`@login_required` + owner-check pattern** at `accounts/views.py:128-131` — copy verbatim for the bulk-add view.
- **Resend email backend** is already wired (env-configured). New email template is a new function alongside `send_invitation_email`, not a new infrastructure.
- **Message framework** (`messages.success`, `messages.error`) is already used in `accounts/views.py` for flash messages — reuse for the bulk-add confirmation banner.
- **`RegistrationForm`** at `accounts/forms.py:7` — auto-claim hook fires AFTER `form.save()` in the view body, doesn't need to touch the form class.
- **`ProjectMember.unique_together = ('project', 'user')`** — DB-level safety net for the dedupe logic; bulk-add view computes the diff upfront but the constraint protects against any race.

### Established Patterns
- **Single email per Invitation row** (no batch sends) — bulk-add mimics this synchronously, N emails per N new ProjectMember rows.
- **Inline HTML in email body** — `send_invitation_email` does not use a Django template engine. Mirror that for the new confirmation email.
- **Auth gating via `request.user` checks in the view body** — no decorators for ownership, just explicit if-checks (matches `invite_user` at line 129).
- **Template dirs:** `accounts/templates/accounts/` is where existing accounts pages live (`register.html`, `invite_user.html`, `invitation_preview.html`). Crew templates land here.

### Integration Points
- **`accounts/urls.py`** gets new routes for the crew index + detail + member CRUD.
- **`accounts/views.py`** gets new views for the same routes + the bulk-add endpoint.
- **`accounts/views.py:register()`** body gets a single new line (call to `claim_pending_crew_memberships(user)`).
- **`accounts/templates/accounts/invite_user.html`** gets the new "Add your crew" panel appended below the existing form (additive insert).
- **`planner/admin_ordering.py`** gets entries for `Crew` and `CrewMember` (under a new "Account / Collaboration" grouping or similar — planner picks).
- **Top-right user menu template** (researcher locates) gets a "My Crew" link.

</code_context>

<specifics>
## Specific Ideas

- Charlie has a touring/A2 team he works the same gigs with weekly — Concert team and Corporate team are concrete example crews (matches the SPEC).
- The "you've been added to {project} by {owner}" framing was specifically endorsed in the SPEC interview — emphasizes the owner-as-actor and removes the click-to-accept cognitive load.
- Mobile parity is explicitly out of scope this phase (SPEC Boundary). The `/m/` interface gets no crew UI for now.

</specifics>

<deferred>
## Deferred Ideas

- **Per-project role override at bulk-add time** — explicit out of scope per SPEC. Clean migration when wanted: add `ProjectMember.crew_role_override` plus an "override role" picker on the crew card.
- **Bulk REMOVE crew from project** — only bulk-ADD lands here. Bulk-remove deferred to a later phase.
- **"Add multiple crews at once" multi-select** — deferred. Single-crew bulk-add is sufficient for the SPEC.
- **Cascade options on crew remove** — explicit no-cascade design; deferred any cascade UX work.
- **Cross-owner crew sharing / team workspace model** — would require an org/workspace abstraction that doesn't exist. Big feature, separate roadmap.
- **In-app notifications** — crew-add fires email today. In-app notification UI is a separate feature.
- **Mobile `/m/` parity** — explicit out of scope.
- **Crew-level audit log / activity history** — not needed for SPEC; `invited_by` + `invited_at` per ProjectMember row is the only audit trail.
- **Pro Tools export (Issue #5 followup)** — completely separate scope, awaiting sample file from Charlie's collaborator.

</deferred>

---

*Phase: 06-trusted-crew-rosters*
*Context gathered: 2026-05-14*
*Next step: /gsd-plan-phase 6 — break this into atomic plans with task breakdown and verification*
