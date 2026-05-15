---
phase: 06-trusted-crew-rosters
verified: 2026-05-14T00:00:00Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open /crew/ as a logged-in owner. Create two crews ('Concert team', 'Corporate team'). Add 2-3 existing users to each with different default roles. Verify each crew card shows correct member count and 'View / Edit Roster' link."
    expected: "Both crews appear in the grid with correct member counts and member names. Role badges (editor/viewer) display correctly in the dark theme."
    why_human: "Visual appearance, card layout, and dark-theme CSS are not machine-verifiable."
  - test: "Open /crew/<id>/ for a crew. Add a pending email (e.g. newbie@example.com). Verify the roster shows a 'pending signup' amber badge for that row."
    expected: "The pending row is visually distinct from active-user rows, with an amber 'pending signup' pill and no username displayed."
    why_human: "Visual badge appearance and color treatment require human inspection."
  - test: "Navigate to /projects/<id>/invite/ as the project owner (who has at least one crew). Scroll past the existing invite form. Verify the 'Add your crew' panel appears with correct crew names, eligible member counts, and greyed-out already-members."
    expected: "The panel appears below the existing form (not replacing it). Already-member rows are visually struck/greyed. Pending-email members show 'pending signup' pill. 'Add this crew' button is disabled when eligible_count == 0."
    why_human: "Panel layout, strike-through styling, and button disabled state require visual confirmation."
  - test: "Click 'Add this crew' on a crew with 3 members, all new to the project. Verify the success flash message and that all 3 members appear in the project's membership list."
    expected: "Flash message reads 'Added 3 members from <crew name>; 0 were already on this project.' ProjectMember rows visible in the admin or project members page."
    why_human: "Flash message display and flow through Django messages framework require browser-level testing."
  - test: "Pre-onboarding HUMAN-UAT (SPEC R6, acceptance criterion 9): As owner, add unregistered@example.com to a crew. Bulk-add that crew to a project. Register a new account as unregistered@example.com. Verify on first login that the new user has a ProjectMember row for that project."
    expected: "After registration, the new user can access the project without any manual invitation. The crew roster shows the pending row converted to an active user row."
    why_human: "Requires a real registration flow, email, and account creation through the browser. Explicitly noted as HUMAN-UAT in SPEC acceptance criteria 9."
  - test: "Verify confirmation email is received after bulk-add. Check subject line contains the project name, body contains owner name, role, and 'Open project' button with no accept_url token."
    expected: "Email subject: '{owner} added you to {project} on ShowStack'. Body: owner label, project name, role, direct project link. No token URL, no 'click here to accept' language. 'No action required' note present."
    why_human: "Email delivery and visual rendering in an email client require live Resend API key and browser/email client."
---

# Phase 6: Trusted Crew Rosters Verification Report

**Phase Goal:** Owner can define named crew rosters (e.g. "Concert team", "Corporate team") and bulk-add an entire crew to a project as ProjectMembers without the email-acceptance round-trip
**Verified:** 2026-05-14
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Owner can create, rename, and delete named crews per SPEC R1 | VERIFIED | `crew_index`, `crew_create`, `crew_delete` views exist; `Crew` model with `unique_together(owner,name)`; 6 URL routes resolve correctly; tests pass |
| 2 | Each crew member has a per-member default role (editor/viewer) per SPEC R2 | VERIFIED | `CrewMember.default_role` CharField with choices; `crew_member_add` validates and persists role; test `test_crew_member_add_with_viewer_role` and `_with_editor_role` pass |
| 3 | Owner can bulk-add entire crew to project without email acceptance per SPEC R3 | VERIFIED | `bulk_add_crew` view at `POST /projects/<id>/invite/add-crew/<crew_id>/`; creates `ProjectMember` rows directly; no `Invitation` rows created; upfront dedupe via `values_list('user_id')`; test `test_bulk_add_creates_project_member_rows` passes |
| 4 | Each added member receives informational email with no accept_url per SPEC R4 | VERIFIED | `send_crew_added_email` exists; links to `set_project` (not a token URL); D-10 log+swallow contract in place; test `test_bulk_add_creates_project_member_rows` verifies exactly 3 email calls via `@patch`; email delivery to live Resend needs human verification |
| 5 | Invitation flow is untouched (SPEC R5 strict additivity) | VERIFIED | `git diff 93cb00a^ HEAD -- planner/models.py` shows 0 lines touching `class Invitation`; `accept_invitation` at line 246 and `send_invitation_email` at line 306 unchanged; test `test_accept_invitation_flow_still_works_end_to_end` passes |
| 6 | Pre-onboarding placeholder row + auto-claim on register per SPEC R6 | VERIFIED | `CrewMember` accepts nullable `user` XOR nullable `email`; `claim_pending_crew_memberships` in `planner/crew.py` rebinds pending rows and materializes `ProjectMember` rows via `CrewProjectAdd`; hook wired in live `marketing/views.register` (D-11 atomic); tests `test_claim_rebinds_pending_row_and_materializes_project_member` and `test_register_triggers_auto_claim` pass; full live smoke test is HUMAN-UAT |
| 7 | Removing a user from a crew does not cascade to ProjectMember per SPEC R7 | VERIFIED | `crew_member_remove` calls `member.delete()` on `CrewMember` only; no FK from `ProjectMember` to `CrewMember`; confirmation dialog text says "removes them from the crew only"; test `test_remove_crew_member_does_not_cascade_to_project_member` and `test_delete_crew_does_not_cascade_to_project_member` pass |
| 8 | Bulk-add dedupes when user is in multiple crews per SPEC R8 | VERIFIED | Upfront `existing_user_ids` set query before creating rows; `ProjectMember.unique_together = ('project','user')` as DB safety net; test `test_bulk_add_dedupes_user_in_multiple_crews` passes; test `test_bulk_add_idempotent_when_all_already_members` passes |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `planner/models.py` | Crew, CrewMember, CrewProjectAdd model definitions | VERIFIED | Classes at lines 752, 773, 820; all FK relationships and constraints present |
| `planner/migrations/0157_crew_crewmember_crewprojectadd.py` | Additive migration creating 3 new tables | VERIFIED | File exists; 3 CreateModel ops; depends on 0156; applied to local SQLite |
| `accounts/admin.py` | CrewAdmin, CrewMemberAdmin, CrewProjectAddAdmin on showstack_admin_site | VERIFIED | All 3 classes exist (lines 216-239); all registered on `showstack_admin_site`, not `admin.site` |
| `planner/admin_ordering.py` | crew/crewmember/crewprojectadd sidebar order entries | VERIFIED | Slots 2.3/2.5/2.7 inserted between projectmember=2 and invitation=3 |
| `accounts/views.py` | 6 crew CRUD views + bulk_add_crew + send_crew_added_email | VERIFIED | All 8 functions exist at documented line numbers; owner gates on all views |
| `accounts/urls.py` | 7 crew/bulk-add URL routes | VERIFIED | All 7 routes present; all URL names resolve to correct paths |
| `templates/accounts/crew_index.html` | Crew index page with create form and crew cards | VERIFIED | 373-line template; dark theme; empty-state CTA; member count display |
| `templates/accounts/crew_detail.html` | Roster page with member table, add/remove forms | VERIFIED | 450-line template; pending signup badge; role badges; confirmation dialog for remove |
| `templates/accounts/invite_user.html` | Additive "Add your crew" panel (zero deletions) | VERIFIED | Panel inserted at line 221; 0 existing markup deletions confirmed; pending/eligible/already-member display |
| `planner/crew.py` | claim_pending_crew_memberships auto-claim helper | VERIFIED | 86-line module; `email__iexact` + `.strip()` (D-08); in-place rebind (D-01); CrewProjectAdd reads (D-09); inner transaction.atomic (D-11) |
| `marketing/views.py` | Auto-claim hook wired to live register endpoint | VERIFIED | D-11 atomic block + D-10 email loop at lines 87-103; `marketing/views.register` is the URL-winning register view |
| `templates/admin/base_site.html` | "My Crew" link in admin userlinks block | VERIFIED | Link at line 132; `{% if user.is_authenticated %}` gate; resolves `crew_index` |
| `templates/accounts/dashboard.html` | "My Crew" link in header-right | VERIFIED | Link at line 294; `btn-admin` class; resolves `crew_index` |
| `planner/tests/test_crew_rosters.py` | 26 tests covering all 8 SPEC requirements | VERIFIED | 567 lines; 4 test classes; 26 methods; all pass (129/129 full suite) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `Crew` model | `settings.AUTH_USER_MODEL` | `owner = ForeignKey(related_name='owned_crews')` | WIRED | Line 754-758 in planner/models.py |
| `CrewMember` model | `Crew` | `crew = ForeignKey(Crew, CASCADE)` | WIRED | Line 775 |
| `CrewProjectAdd` model | `Project` | `project = ForeignKey(Project, related_name='crew_adds')` | WIRED | Line 827 |
| `accounts/views.invite_user` | `Crew.objects.filter(owner=request.user)` | `owner_crews_qs` query + `owner_crews` context key | WIRED | Lines 179-221; `{% if owner_crews %}` in template |
| `accounts/views.bulk_add_crew` | `ProjectMember.objects.create(...)` | loop over `to_add` list | WIRED | Lines 903-911; creates rows with `invited_by=request.user` |
| `accounts/views.bulk_add_crew` | `CrewProjectAdd.objects.get_or_create` | D-09 audit row | WIRED | Line 915 |
| `planner/crew.py:claim_pending_crew_memberships` | `CrewMember.objects.filter(user__isnull=True, email__iexact=normalized)` | D-08 email match | WIRED | Lines 54-58 |
| `planner/crew.py:claim_pending_crew_memberships` | `ProjectMember.objects.get_or_create(...)` | per-CrewProjectAdd materialize | WIRED | Lines 75-84 |
| `marketing/views.register` | `claim_pending_crew_memberships(user)` | D-07 inline call inside `transaction.atomic` | WIRED | Lines 87-92 |
| `accounts/views.register` | `claim_pending_crew_memberships(user)` | D-07 inline call inside `transaction.atomic` | WIRED | Lines 35-40 (shadowed by marketing URL, but present) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `crew_index` view | `crews` | `Crew.objects.filter(owner=request.user).order_by('name')` | Yes — DB query | FLOWING |
| `crew_detail` view | `members` | `crew.crewmember_set.select_related('user').all()` | Yes — DB query | FLOWING |
| `invite_user` view | `owner_crews` | `Crew.objects.filter(owner=request.user).prefetch_related(...)` loop | Yes — DB query | FLOWING |
| `bulk_add_crew` view | `new_rows` | `ProjectMember.objects.create()` loop over `to_add` | Yes — creates real rows | FLOWING |
| `claim_pending_crew_memberships` | `pending` | `CrewMember.objects.filter(user__isnull=True, email__iexact=...)` | Yes — DB query | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All crew URL names resolve to correct paths | Django shell reverse() calls | `/crew/`, `/crew/new/`, `/crew/1/`, `/crew/1/delete/`, `/crew/1/members/add/`, `/crew/1/members/2/remove/`, `/projects/1/invite/add-crew/2/` | PASS |
| `python manage.py check` exits 0 | Django system check | `System check identified no issues (0 silenced)` | PASS |
| `makemigrations --dry-run` shows no outstanding changes | Dry-run makemigrations | `No changes detected in app 'planner'` | PASS |
| All 26 Phase 6 tests pass | `manage.py test planner.tests.test_crew_rosters` | `Ran 26 tests in 3.276s OK` | PASS |
| Full suite (129 tests) passes | `manage.py test planner accounts` | `Ran 129 tests in 8.302s OK` | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SPEC-06-R01 | Plans 01, 03 | Named crew rosters per owner | SATISFIED | Crew model + CRUD views + 5 tests |
| SPEC-06-R02 | Plans 01, 03 | Per-crew default role | SATISFIED | CrewMember.default_role field + crew_member_add view + 2 tests |
| SPEC-06-R03 | Plans 04 | Bulk-add crew to project (no acceptance click) | SATISFIED | bulk_add_crew view + upfront dedupe + 3 tests |
| SPEC-06-R04 | Plans 04 | Confirmation email after bulk-add (no token) | SATISFIED | send_crew_added_email helper; live delivery requires HUMAN |
| SPEC-06-R05 | Plans 01, 04, 06 | Invitation flow strictly untouched | SATISFIED | git diff confirms 0 Invitation modifications; behavioral regression test passes |
| SPEC-06-R06 | Plans 05, 07 | Pre-onboarding pending member + auto-claim on register | SATISFIED | claim_pending_crew_memberships in planner/crew.py; wired in marketing/views.register; 6 unit+integration tests; full smoke test is HUMAN-UAT |
| SPEC-06-R07 | Plans 03, 07 | No-cascade removal | SATISFIED | crew_member_remove deletes CrewMember only; no FK to ProjectMember; 2 tests |
| SPEC-06-R08 | Plans 01, 04, 07 | Dedupe on bulk-add | SATISFIED | Upfront user_id set diff in bulk_add_crew; DB unique_together safety net; 2 tests |

Note: SPEC-06-R01..R08 are Phase 6 SPEC requirements (v2.1 milestone). They do not appear in `.planning/REQUIREMENTS.md` which covers the v2.0 milestone only. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `accounts/views.py` | 853, 856 | `print()` instead of `logger` in `send_crew_added_email` | Warning | Email success/failure not visible in Railway structured log stream. D-10 "log+swallow" contract documented but implemented with stdout instead of logging module. Functional correctness unaffected. |
| `accounts/views.py` | 919-925 | Double-wrapping email exception: outer `try/except` in `bulk_add_crew` is dead code since `send_crew_added_email` already swallows internally | Warning | Outer `logger.exception` at line 921 will never fire for Resend failures. Creates false sense of resilience. Fixable by removing inner catch or removing outer wrapper. Not a correctness issue. |
| `accounts/views.py` | 603-610 | Unreachable duplicate block in `project_access_requests` after `return render(...)` at line 601 | Warning | Dead code — paste artifact from Phase 6 edit. The function works correctly; the duplicate block never executes. Pre-existing and worsened by Phase 6 editing. |
| `planner/admin_ordering.py` | 8-10, 45 | Pre-existing `print()` statements that fire on every admin page load | Info | Railway log noise. Not introduced by Phase 6. |
| `templates/accounts/crew_index.html` | 347 | `crew.crewmember_set.count` in template loop (N+1 queries) | Info | One extra COUNT query per crew card. Acceptable for small rosters (1-10 crews typical). Not a correctness issue. |

No blockers found. All anti-patterns are warnings or info items.

### Human Verification Required

#### 1. Crew UI visual appearance

**Test:** Log in as an owner. Navigate to `/crew/`. Create two crews. Add members with different roles.
**Expected:** Dark-theme crew cards; role badges (editor=green, viewer=blue) correctly styled; empty-state CTA visible when no crews exist; "View / Edit Roster" links work.
**Why human:** CSS styling, dark theme fidelity, and card layout are not machine-verifiable.

#### 2. Pending signup badge on crew roster

**Test:** On a crew detail page, add an unregistered email (e.g. `notyet@example.com`) as a member.
**Expected:** The roster shows the row with an amber "pending signup" badge and no username, visually distinct from active user rows.
**Why human:** Badge color and visual treatment require browser inspection.

#### 3. "Add your crew" panel on invite page

**Test:** Navigate to `/projects/<id>/invite/` as an owner who has at least one crew with some members already on the project.
**Expected:** Panel appears below the existing invite form (not replacing it). Already-member names are struck/greyed. Pending-email members show "pending signup" pill. "Add this crew" button is disabled when eligible_count == 0.
**Why human:** Panel layout and per-member visual treatment require browser-level inspection.

#### 4. Flash message after bulk-add

**Test:** Click "Add this crew" for a crew with eligible new members.
**Expected:** Flash banner reads "Added {N} members from {crew_name}; {M} were already on this project." Redirect lands back on the invite page.
**Why human:** Flash message display and redirect behavior require browser testing.

#### 5. Pre-onboarding smoke test — SPEC R6 HUMAN-UAT

**Test:** Owner adds `unregistered@example.com` to a crew. Owner bulk-adds the crew to a project. `unregistered@example.com` registers via `/register/`. After registration, verify the new user has a `ProjectMember` row for the project.
**Expected:** New user can access the project without any separate invitation. Crew roster shows the pending row converted to an active-user row.
**Why human:** Requires live registration flow through a browser. Explicitly designated HUMAN-UAT in SPEC acceptance criteria 9.

#### 6. Confirmation email format and delivery

**Test:** Perform a bulk-add with Resend API key configured in `.env`. Check the email received by the added member.
**Expected:** Subject: "{owner} added you to {project} on ShowStack". Body contains owner name, project name, role, "Open project" button linking to `set_project` URL. No token URL, no "click to accept" language. "No action required" note visible.
**Why human:** Requires live Resend API key, real email delivery, and visual inspection in email client. Code review WR-02 notes `print()` vs `logger` inconsistency in `send_crew_added_email` — this should be spot-checked in Railway logs after a live send.

---

## Deviations and Notes

### CR-01 (Code Review Critical — Confirmed False Positive)

The code review flagged `Crew` being used in `invite_user` (line 180) while the `from planner.models import Crew, CrewMember, CrewProjectAdd` import is at line 660 — below the function definition. The orchestrator confirmed this is a false positive: Python evaluates all module-level statements at import time, so the import at line 660 executes before any request handler is invoked. `Crew` is bound in the module namespace by the time any HTTP request reaches `invite_user`. No NameError risk.

### Marketing/Views Bug Fix (Plan 07)

A critical routing bug was discovered and fixed during Plan 07: `audiopatch/urls.py` includes `marketing.urls` before `accounts.urls`, so `reverse('register')` and all `/register/` requests hit `marketing.views.register`, not `accounts.views.register`. The auto-claim hook from Plan 05 had been wired to `accounts/views.register` (shadowed). Plan 07 correctly wired the hook to `marketing/views.register`. The test suite validates this path via `RegisterIntegrationTests`.

### WR-02 / WR-03 Not Blocking

The `print()` vs `logger` inconsistency in `send_crew_added_email` and the dead outer exception wrapper in `bulk_add_crew` are code quality issues noted in the review. They do not affect functionality. The D-10 "log+swallow" contract is implemented correctly (exceptions are caught and not re-raised); only the logging destination (stdout vs logger) differs from the contract's intent. Recommend fixing before go-live per WR-02 suggestion.

---

_Verified: 2026-05-14_
_Verifier: Claude (gsd-verifier)_
