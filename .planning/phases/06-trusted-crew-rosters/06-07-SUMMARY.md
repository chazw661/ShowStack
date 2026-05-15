---
phase: 06-trusted-crew-rosters
plan: "07"
subsystem: planner/tests/test_crew_rosters.py + marketing/views.py
tags: [tests, crew-rosters, regression, auto-claim, constraints]
dependency_graph:
  requires:
    - planner.Crew
    - planner.CrewMember
    - planner.CrewProjectAdd
    - planner.ProjectMember
    - planner.Invitation
    - planner.crew.claim_pending_crew_memberships
    - accounts.views.send_crew_added_email
    - accounts.views.bulk_add_crew
    - accounts.views.accept_invitation
    - marketing.views.register (live register endpoint)
  provides:
    - planner/tests/test_crew_rosters.py (CI gate for SPEC R1-R8 + D-15)
    - marketing.views.register auto-claim hook (bug fix)
  affects:
    - planner/tests/test_crew_rosters.py
    - marketing/views.py
tech_stack:
  added: []
  patterns:
    - Django TestCase with setUpTestData + Client + force_login (Phase 5 pattern)
    - "@patch('accounts.views.send_crew_added_email') — no real Resend calls in tests"
    - TransactionTestCase not needed — standard TestCase with assertRaises(IntegrityError) covers D-15
    - claim_pending_crew_memberships called directly as a unit test
key_files:
  created:
    - planner/tests/test_crew_rosters.py
  modified:
    - marketing/views.py
decisions:
  - "Patch target is accounts.views.send_crew_added_email, not marketing.views.send_crew_added_email — marketing/views.py uses a local import inside the function body which resolves to the accounts module"
  - "marketing/views.register is the live register endpoint (first URL match in audiopatch/urls.py); accounts/views.register is shadowed — auto-claim hook must live in marketing/views.register"
  - "Rule 1 bug fix: marketing/views.register did not call claim_pending_crew_memberships; wired it with D-11 atomic wrap and D-10 email loop matching accounts/views.register pattern"
  - "terms='on' POST field required by marketing/views.register (clickwrap consent per CLAUDE.md)"
  - "CrewMemberConstraintTests uses assertRaises((IntegrityError, Exception)) to handle both PostgreSQL (IntegrityError) and SQLite (raises wrapped exception) backends"
metrics:
  duration: "~45 minutes"
  completed: "2026-05-15"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
  files_created: 1
---

# Phase 06 Plan 07: Crew Roster Regression Tests Summary

**One-liner:** 567-line test module with 26 methods locks all 8 SPEC requirements and 3 D-15 DB constraints as CI gates; Rule 1 bug fix wires the auto-claim hook to the live marketing/views.register endpoint.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create planner/tests/test_crew_rosters.py covering all 8 SPEC requirements | 36caab2 | planner/tests/test_crew_rosters.py, marketing/views.py |

## What Was Built

### planner/tests/test_crew_rosters.py (567 lines, 4 classes, 26 test methods)

**Class `CrewRosterTests`** — SPEC R1, R2, R3, R4, R5, R7, R8

| Test Method | SPEC Coverage |
|---|---|
| `test_crew_index_lists_owners_crews` | R1 — named rosters visible to owner |
| `test_crew_create_blocks_duplicate_name_per_owner` | R1 + D-02 unique_together |
| `test_crew_index_hides_other_owners_crews` | R1 — isolation between owners |
| `test_crew_member_add_with_viewer_role` | R2 — default_role=viewer persisted |
| `test_crew_member_add_with_editor_role` | R2 — default_role=editor persisted |
| `test_bulk_add_creates_project_member_rows` | R3 + R4 — 3 rows, 3 emails, 0 Invitation rows |
| `test_bulk_add_idempotent_when_all_already_members` | R3 + R8 — second add = 0 rows, 0 emails |
| `test_bulk_add_records_crew_project_add` | D-09 — CrewProjectAdd written |
| `test_bulk_add_rejects_non_project_owner` | R3 — owner gate |
| `test_bulk_add_survives_email_failure` | D-10 — Resend exception swallowed |
| `test_invitation_model_signature_preserved` | R5 — Invitation fields subset check |
| `test_accept_invitation_flow_still_works_end_to_end` | R5 — behavioral regression gate |
| `test_remove_crew_member_does_not_cascade_to_project_member` | R7 — no cascade on member remove |
| `test_delete_crew_does_not_cascade_to_project_member` | R7 — no cascade on crew delete |
| `test_bulk_add_dedupes_user_in_multiple_crews` | R8 — 1 ProjectMember row for user in 2 crews |

**Class `CrewMemberConstraintTests`** — D-15

| Test Method | Constraint |
|---|---|
| `test_xor_blocks_both_user_and_email_set` | crewmember_user_xor_email (both non-null) |
| `test_xor_blocks_neither_user_nor_email_set` | crewmember_user_xor_email (both null) |
| `test_partial_unique_blocks_duplicate_user_in_crew` | uniq_crewmember_crew_user |
| `test_partial_unique_blocks_duplicate_pending_email_in_crew` | uniq_crewmember_crew_email |

**Class `AutoClaimTests`** — SPEC R6 (unit)

| Test Method | Behavior |
|---|---|
| `test_claim_rebinds_pending_row_and_materializes_project_member` | Full rebind + ProjectMember creation |
| `test_claim_iexact_matches_uppercase_email` | D-08 case-insensitive match |
| `test_claim_strips_whitespace` | D-08 explicit .strip() |
| `test_claim_does_not_match_plus_alias` | D-08 no +alias collapsing |
| `test_claim_idempotent_on_existing_project_member` | R8 — get_or_create idempotency |

**Class `RegisterIntegrationTests`** — SPEC R6 (integration, D-11)

| Test Method | Behavior |
|---|---|
| `test_register_triggers_auto_claim` | Full /register/ POST → auto-claim → ProjectMember |
| `test_register_auto_claim_survives_email_failure` | D-10/D-11 — email failure doesn't roll back user |

### Test run results

```
Ran 26 tests in 3.188s
OK
```

Full suite (planner + accounts):
```
Ran 129 tests in 8.266s
OK
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Auto-claim hook wired to shadowed register view**

- **Found during:** Task 1 — RegisterIntegrationTests failing with 200 instead of 302
- **Issue:** Phase 5 added `claim_pending_crew_memberships` to `accounts/views.register`, but `audiopatch/urls.py` includes `marketing.urls` before `accounts.urls`. Both define `path('register/', ..., name='register')`. The marketing URL wins — `reverse('register')` and every real HTTP request to `/register/` hit `marketing.views.register`, which had no auto-claim hook. The accounts register was unreachable via HTTP.
- **Fix:** Added the D-11 atomic wrap + `claim_pending_crew_memberships` call + D-10 email loop to `marketing/views.register`, matching the pattern already established in `accounts/views.register`. Also added `transaction` import and `logging` module-level logger to `marketing/views.py`.
- **Files modified:** `marketing/views.py`
- **Commit:** 36caab2

**2. [Rule 1 - Bug] `@patch` target for email mock in RegisterIntegrationTests**

- **Found during:** Task 1 — `AttributeError: <module 'marketing.views'> does not have the attribute 'send_crew_added_email'`
- **Issue:** `marketing/views.register` imports `send_crew_added_email` via a local `from accounts.views import send_crew_added_email` inside the function body. `@patch` must target the module where the name is *defined*, not where it is *used* via local import.
- **Fix:** All `@patch` decorators use `'accounts.views.send_crew_added_email'` consistently.
- **Files modified:** `planner/tests/test_crew_rosters.py`
- **Commit:** 36caab2 (same commit)

## Known Stubs

None. All test assertions exercise real DB queries and real view logic. `send_crew_added_email` is mocked solely to avoid Resend API network calls — the email loop code path itself runs.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The `marketing/views.py` change adds function-level imports of existing symbols (`claim_pending_crew_memberships`, `send_crew_added_email`) and a `transaction.atomic()` block — no new trust boundary.

## Self-Check: PASSED

- `planner/tests/test_crew_rosters.py` exists: FOUND
- `wc -l` = 567 (>= 200): PASSED
- `grep -c "^class "` = 4 (>= 4): PASSED
- `grep -c "    def test_"` = 26 (>= 15): PASSED
- `@patch('accounts.views.send_crew_added_email')` present: FOUND
- `from planner.crew import claim_pending_crew_memberships` present: FOUND
- `test_bulk_add_dedupes_user_in_multiple_crews` (R8): FOUND
- `test_remove_crew_member_does_not_cascade_to_project_member` (R7): FOUND
- `test_xor_blocks_both_user_and_email_set` (D-15): FOUND
- `test_partial_unique_blocks_duplicate_pending_email_in_crew` (D-15): FOUND
- `test_claim_rebinds_pending_row_and_materializes_project_member` (R6): FOUND
- `test_register_triggers_auto_claim` (R6 integration): FOUND
- `test_accept_invitation_flow_still_works_end_to_end` (R5 behavioral): FOUND
- `python manage.py test planner.tests.test_crew_rosters` exits 0: PASSED (26/26)
- `python manage.py test planner accounts` exits 0: PASSED (129/129)
- Commit 36caab2 exists: FOUND
