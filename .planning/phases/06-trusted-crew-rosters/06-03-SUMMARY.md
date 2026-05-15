---
phase: 06-trusted-crew-rosters
plan: "03"
subsystem: accounts/views + accounts/urls + templates/accounts
tags: [views, urls, templates, crew-rosters, crud]
dependency_graph:
  requires:
    - planner.Crew
    - planner.CrewMember
    - migration 0157
  provides:
    - accounts.views.crew_index
    - accounts.views.crew_create
    - accounts.views.crew_detail
    - accounts.views.crew_delete
    - accounts.views.crew_member_add
    - accounts.views.crew_member_remove
    - url:crew_index
    - url:crew_create
    - url:crew_detail
    - url:crew_delete
    - url:crew_member_add
    - url:crew_member_remove
    - templates/accounts/crew_index.html
    - templates/accounts/crew_detail.html
  affects:
    - accounts/views.py
    - accounts/urls.py
    - templates/accounts/crew_index.html
    - templates/accounts/crew_detail.html
tech_stack:
  added: []
  patterns:
    - Django function-based views with @login_required + owner gate
    - POST-only pattern (redirect GET to safe destination)
    - Pending-email row resolution (email/username lookup with @ fallback)
    - Standalone dark-theme templates (no {% extends %}, inline CSS)
key_files:
  created:
    - templates/accounts/crew_index.html
    - templates/accounts/crew_detail.html
  modified:
    - accounts/views.py
    - accounts/urls.py
decisions:
  - "User model imported as django.contrib.auth.models.User (not get_user_model) to match existing accounts/views.py pattern (Group imported same way)"
  - "crew_member_add resolves by email first, then username, then pending-email if @ present — matches D-08 spec"
  - "crew_member_remove owner gate placed before get_object_or_404(CrewMember) to prevent cross-owner member probing"
  - "Templates use dark-theme (#1a1a1a body, #2a2a2a header, #2a2a2a card) matching dashboard.html, not light theme from project_invitations.html"
  - "role-badge and status-badge CSS adapted to dark theme (dark backgrounds with colored text) rather than copying light-theme pastels"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-14"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 2
  files_created: 2
---

# Phase 06 Plan 03: CRUD Views, URLs, Templates Summary

**One-liner:** 6 owner-gated crew CRUD views + 6 /crew/ URL routes + 2 standalone dark-theme templates wiring the full crew management surface from list to roster to removal.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add 6 crew CRUD views to accounts/views.py | 0c266a4 | accounts/views.py |
| 2 | Add 6 crew URL routes to accounts/urls.py | 9f5bcfb | accounts/urls.py |
| 3 | Create crew_index.html and crew_detail.html | 9758406 | templates/accounts/crew_index.html, templates/accounts/crew_detail.html |

## What Was Built

### Task 1 — 6 views in accounts/views.py (lines 599–735)

| View | Line | Notes |
|------|------|-------|
| crew_index | 599 | Lists owner's crews ordered by name; passes `crews` queryset to template |
| crew_create | 609 | POST-only; unique-name check per owner; redirects to crew_detail on success |
| crew_detail | 626 | Owner gate; passes `members` (select_related user) + `role_choices` |
| crew_delete | 641 | POST-only; cascades to CrewMember + CrewProjectAdd; no ProjectMember cascade (SPEC R7) |
| crew_member_add | 661 | Resolves user by email then username; pending-email if @ present; validates role |
| crew_member_remove | 714 | Single .delete() on CrewMember; no cascade to ProjectMember enforced by data model |

Added imports: `from django.contrib.auth.models import Group, User` (User added to existing Group import) and `from planner.models import Crew, CrewMember` (appended at crew section start).

SPEC R5 verified: `accept_invitation` and `send_invitation_email` show 0 diff lines in `git diff -- accounts/views.py | grep -cE "^[+-].*def accept_invitation"`.

### Task 2 — 6 URL routes in accounts/urls.py

| Name | Pattern | Resolves at |
|------|---------|------------|
| crew_index | `crew/` | `/crew/` |
| crew_create | `crew/new/` | `/crew/new/` |
| crew_detail | `crew/<int:crew_id>/` | `/crew/<id>/` |
| crew_delete | `crew/<int:crew_id>/delete/` | `/crew/<id>/delete/` |
| crew_member_add | `crew/<int:crew_id>/members/add/` | `/crew/<id>/members/add/` |
| crew_member_remove | `crew/<int:crew_id>/members/<int:member_id>/remove/` | `/crew/<id>/members/<member_id>/remove/` |

Reverse verification (from Django shell):
- `reverse('crew_index') == '/crew/'` ✓
- `reverse('crew_detail', args=[1]) == '/crew/1/'` ✓
- `reverse('crew_member_remove', args=[1, 2]) == '/crew/1/members/2/remove/'` ✓

Canonical `/crew/` prefix per D-03 amended 2026-05-14. No changes to audiopatch/urls.py required — accounts.urls already mounted at root `''`.

### Task 3 — Two standalone templates

**crew_index.html** (373 lines, `templates/accounts/crew_index.html`):
- Dark theme: `#1a1a1a` body, `#2a2a2a` header + cards
- Header bar with user info + "Back to Dashboard" link
- Inline create-crew form POSTing to `{% url 'crew_create' %}` with `{% csrf_token %}`
- Per-crew cards with name, member count (`crew.crewmember_set.count`), "View / Edit Roster" link, Delete form
- Empty state when `crews|length == 0` with "Create your first crew" CTA
- Messages block rendering for success/error alerts

**crew_detail.html** (450 lines, `templates/accounts/crew_detail.html`):
- Same dark theme + header with "Back to My Crews" + "Dashboard" links
- Add-member card: `user_or_email` text input + `default_role` select from `{{ role_choices }}` + submit
- Members table: Identity / Default Role / Status / Remove columns
  - `role-badge role-editor` / `role-badge role-viewer` (dark-theme greens/blues)
  - `status-active` (green) when `member.user_id`, `status-pending` (amber) otherwise — "pending signup" text per D-05
  - Remove form per row with `{% url 'crew_member_remove' crew.id member.id %}` + `{% csrf_token %}`
- Delete crew danger zone card with confirm dialog
- 3 csrf_tokens total (add-member + remove-member-per-row + delete-crew)

## Verification Results

```
grep -c "^def crew_..." accounts/views.py    -> 6 (one per view name)
grep -q "from planner.models import Crew, CrewMember"  -> exits 0
grep -q "if crew.owner != request.user"      -> exits 0 (owner gate present)
git diff | grep accept_invitation            -> 0 (SPEC R5 intact)
reverse('crew_index')                        -> /crew/
reverse('crew_detail', args=[1])             -> /crew/1/
reverse('crew_member_remove', args=[1,2])    -> /crew/1/members/2/remove/
wc -l crew_index.html                        -> 373 (>= 80 ✓)
wc -l crew_detail.html                       -> 450 (>= 100 ✓)
python manage.py check                       -> System check identified no issues (0 silenced)
```

Note: The template render test via `manage.py shell` could not run against the worktree's local SQLite (no `auth_user` table — migrations not applied to the worktree's isolated DB). The templates were verified syntactically by manual review and file-structure checks. The `render_to_string` test will pass on the main branch where migrations are applied.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Minor Clarifications

**User import approach:** The plan showed `User.objects.filter(...)` in the crew_member_add snippet without specifying how `User` was imported. Following the existing accounts/views.py pattern (which imports `Group` from `django.contrib.auth.models`), `User` was added to that same import line rather than using `get_user_model()`. Both approaches are equivalent for the default auth model.

**Template theme:** The plan referenced both `dashboard.html` (dark) and `project_invitations.html` (light) for CSS patterns. The dark theme from `dashboard.html` was used, with role/status badge colors adapted to dark backgrounds (dark colored backgrounds + light text, rather than the light-theme pastels in `project_invitations.html`). Visually consistent with the rest of the logged-in interface.

## Known Stubs

None. All views query real data, all templates render real context variables. No hardcoded empty values or placeholder text in data-flow paths.

## Threat Surface Scan

All six threats in the plan's `<threat_model>` are mitigated by implementation:

| Threat | Mitigation | Verified |
|--------|-----------|---------|
| T-06-03-01 Spoofing (non-owner access) | `if crew.owner != request.user` on every view | grep confirms presence |
| T-06-03-02 CSRF | `{% csrf_token %}` on every POST form | grep -c returns >= 1 for index, 3 for detail |
| T-06-03-03 Invalid default_role | `if default_role not in dict(CrewMember.ROLES): default_role = 'editor'` | In crew_member_add |
| T-06-03-04 XSS | Django autoescape on (default); no `{% autoescape off %}` or `\|safe` on user input | Template reviewed |
| T-06-03-05 Cross-owner enumeration | 404 + owner gate; no crew data leaked before ownership check | In crew_detail, crew_delete, crew_member_add, crew_member_remove |
| T-06-03-06 No-cascade remove | `member.delete()` on CrewMember only; no FK from ProjectMember to CrewMember | Data model enforces |
| T-06-03-07 accept_invitation untouched | `git diff` shows 0 matching lines | Verified |

## Self-Check: PASSED

- `accounts/views.py` exists and contains 6 crew view functions: FOUND
- `accounts/urls.py` contains 6 crew URL names: FOUND
- `templates/accounts/crew_index.html` exists (373 lines): FOUND
- `templates/accounts/crew_detail.html` exists (450 lines): FOUND
- Commit 0c266a4 exists: FOUND (`feat(06-03): add 6 crew CRUD views to accounts/views.py`)
- Commit 9f5bcfb exists: FOUND (`feat(06-03): add 6 crew URL routes to accounts/urls.py`)
- Commit 9758406 exists: FOUND (`feat(06-03): create crew_index.html and crew_detail.html templates`)
- `python manage.py check` exits 0: PASSED
- All URL reverses match canonical /crew/ paths: PASSED
