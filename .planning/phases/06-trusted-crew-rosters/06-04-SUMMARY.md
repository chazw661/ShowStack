---
phase: 06-trusted-crew-rosters
plan: "04"
subsystem: accounts/views + accounts/urls + templates/accounts
tags: [views, urls, templates, bulk-add, crew-rosters, email, resend]
dependency_graph:
  requires:
    - planner.Crew
    - planner.CrewMember
    - planner.CrewProjectAdd
    - migration 0157
    - accounts.views.invite_user
    - accounts.views.crew_member_remove
  provides:
    - accounts.views.send_crew_added_email
    - accounts.views.bulk_add_crew
    - owner_crews context injection in invite_user
    - url:bulk_add_crew
    - Additive 'Add your crew' panel in invite_user.html
  affects:
    - accounts/views.py
    - accounts/urls.py
    - templates/accounts/invite_user.html
tech_stack:
  added: []
  patterns:
    - D-10 log+swallow email pattern (mirrors send_access_approved_email)
    - SPEC R8 upfront dedupe via values_list user_id set
    - Pitfall 2 .create() loop (not bulk_create) so auto_now_add fires
    - D-09 CrewProjectAdd.get_or_create idempotent audit row
    - SPEC R4 no-token email (set_project direct link)
    - SPEC R5 strictly additive template insertion (zero deletions)
key_files:
  created: []
  modified:
    - accounts/views.py
    - accounts/urls.py
    - templates/accounts/invite_user.html
decisions:
  - "D-10: send_crew_added_email uses try/except print log+swallow (not re-raise) — mirrors send_access_approved_email, not send_invitation_email"
  - "SPEC R4: email body links directly to reverse('set_project', args=[project.id]) — no accept_url token since access is already active"
  - "SPEC R8: single upfront dedupe query (ProjectMember.filter(user_id__in=...).values_list) rather than per-row get_or_create, to give accurate already/new counts for flash message"
  - "D-09: CrewProjectAdd.get_or_create(crew=crew, project=project) written after the ProjectMember loop so the audit row always exists even on re-add"
  - "Pitfall 2: ProjectMember.objects.create() loop (not bulk_create) so auto_now_add fires for invited_at on each row"
  - "SPEC R5 additivity: owner_crews injected alongside existing form/project keys; template insertion uses zero-deletion edit"
  - "Local SQLite migration 0157 applied mid-task (table planner_crewprojectadd was missing) — per MEMORY.md rule, migrate locally after makemigrations"
metrics:
  duration: "~74 minutes"
  completed: "2026-05-14"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 3
  files_created: 0
---

# Phase 06 Plan 04: Bulk-Add Email + Invite Panel Summary

**One-liner:** bulk_add_crew POST view + send_crew_added_email D-10 helper + additive owner_crews panel on invite_user.html — closes SPEC R3 (bulk-add), R4 (confirmation email), R5 (additive panel), R8 (dedupe).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add bulk_add_crew view + send_crew_added_email helper + inject owner_crews into invite_user | 6ba1867 | accounts/views.py |
| 2 | Add bulk_add_crew URL route to accounts/urls.py | a081a29 | accounts/urls.py |
| 3 | Add additive 'Add your crew' panel to invite_user.html | 0b81ebc | templates/accounts/invite_user.html |

## What Was Built

### Task 1 — accounts/views.py (lines 785–906)

**`send_crew_added_email(project_member, request)` — line 785**
- D-10 log+swallow: try/except around `resend.Emails.send()`; print log on success AND failure; no re-raise
- SPEC R4: no accept_url token — links directly to `reverse('set_project', args=[project_member.project.id])`
- Email body: owner_label, project.name, role display, "Open project" button, "No action required" note

**`bulk_add_crew(request, project_id, crew_id)` — line 839**
- `@login_required` + project owner gate (`project.owner != request.user` → error + redirect dashboard)
- `get_object_or_404(Crew, id=crew_id, owner=request.user)` — crew-owner gate (T-06-04-02)
- GET redirect to invite_user (POST-only contract)
- `crew.crewmember_set.filter(user__isnull=False).select_related('user')` — resolved members only
- SPEC R8: `existing_user_ids = set(ProjectMember.filter(...).values_list('user_id', flat=True))`
- `to_add` list comprehension; `already = len(resolved) - len(to_add)` for flash count
- `ProjectMember.objects.create(...)` loop — Pitfall 2: auto_now_add fires for invited_at
- `CrewProjectAdd.objects.get_or_create(crew=crew, project=project)` — D-09 audit row
- Per-row `send_crew_added_email` wrapped in try/except with `logger.exception(...)` — D-10
- Flash: `"Added {N} members from {crew.name}; {M} were already on this project."`
- Redirect to `invite_user` on completion

**`invite_user` context injection (additive, SPEC R5)**
- `owner_crews_qs`: `Crew.filter(owner=request.user).prefetch_related('crewmember_set__user').order_by('name')`
- `existing_member_ids`: set of current ProjectMember user_ids for this project
- Per-crew dict: `id`, `name`, `eligible_count`, `member_display` (list of `{label, is_already_member, is_pending}`)
- Context keys: `form` and `project` preserved unchanged; `owner_crews` added

Added at module top: `import logging` + `logger = logging.getLogger(__name__)`
Extended import: `from planner.models import Crew, CrewMember, CrewProjectAdd`

SPEC R5 verified: `git diff -- accounts/views.py | grep -cE "^[+-].*def accept_invitation"` = 0,
`git diff -- accounts/views.py | grep -cE "^[+-].*def send_invitation_email"` = 0.

### Task 2 — accounts/urls.py

Added one route:

```python
path('projects/<int:project_id>/invite/add-crew/<int:crew_id>/', views.bulk_add_crew, name='bulk_add_crew'),
```

`reverse('bulk_add_crew', args=[1, 2])` → `/projects/1/invite/add-crew/2/` ✓

### Task 3 — templates/accounts/invite_user.html (additive only)

Inserted 27 lines after the existing `.card` close (line 219) and before the `.container` close (was line 220).

Zero deletions: `git diff -- templates/accounts/invite_user.html | grep -cE "^-[^-]"` = 0

Panel behavior:
- `{% if owner_crews %}` outer guard — page byte-identical when owner has no crews
- Per-crew `.card` with `{{ crew.name }} ({{ crew.eligible_count }} eligible to add)` header
- Member list: struck+grey for `is_already_member`, amber "pending signup" pill for `is_pending`, plain text for eligible
- POST form to `{% url 'bulk_add_crew' project.id crew.id %}` with `{% csrf_token %}`
- Submit button: `disabled` when `eligible_count == 0` (all already members)
- Inherits existing `.card` and `.btn-primary` styles — no new CSS

Template render verified: `render_to_string('accounts/invite_user.html', {'form': <InviteUserForm>, 'project': p, 'owner_crews': [], ...})` returns non-empty string. ✓

## Verification Results

```
grep -q "^def send_crew_added_email" accounts/views.py         -> exits 0
grep -q "^def bulk_add_crew" accounts/views.py                 -> exits 0
grep -q "from planner.models import Crew, CrewMember, CrewProjectAdd"  -> exits 0
grep -q "logger = logging.getLogger" accounts/views.py         -> exits 0
grep -q "CrewProjectAdd.objects.get_or_create" accounts/views.py -> exits 0
grep -q "ProjectMember.objects.create" accounts/views.py       -> exits 0
grep -q "owner_crews" accounts/views.py                        -> exits 0
grep -q "logger.exception" accounts/views.py                   -> exits 0
grep -q "reverse('set_project'" accounts/views.py              -> exits 0
git diff -- accounts/views.py | grep -cE "^[+-].*def accept_invitation"    -> 0
git diff -- accounts/views.py | grep -cE "^[+-].*def send_invitation_email" -> 0
grep -q "name='bulk_add_crew'" accounts/urls.py                -> exits 0
reverse('bulk_add_crew', args=[1, 2])                          -> /projects/1/invite/add-crew/2/
grep -q "Phase 6" templates/accounts/invite_user.html          -> exits 0
grep -q "Add this crew" templates/accounts/invite_user.html    -> exits 0
grep -q "pending signup" templates/accounts/invite_user.html   -> exits 0
grep -q "text-decoration:line-through" templates/accounts/invite_user.html -> exits 0
git diff -- templates/accounts/invite_user.html | grep -cE "^-[^-]"   -> 0
render_to_string('accounts/invite_user.html', owner_crews=[])  -> 'ok'
python manage.py check                                         -> 0 issues (0 silenced)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Applied migration 0157 to local SQLite**
- **Found during:** Task 3 template render test
- **Issue:** `django.db.utils.OperationalError: no such table: planner_crewprojectadd` — migration 0157 had not been applied to the local dev database (it was marked `[ ]` in showmigrations)
- **Fix:** `python manage.py migrate planner` — applied 0157 locally
- **Files modified:** local SQLite db (not committed per CLAUDE.md + MEMORY.md convention)
- **Note:** Per MEMORY.md "apply new migrations to local SQLite before marking the plan complete; CLAUDE.md's ask-first rule is Railway-only"

None further — plan executed exactly as written beyond the above.

## Known Stubs

None. All views query real DB data. The `owner_crews` panel wires to real `Crew`/`CrewMember` rows from the database. `send_crew_added_email` calls real Resend API (API key needed in env for live sends). The `{% if owner_crews %}` guard degrades gracefully when owner has no crews — not a stub, by design.

## Threat Surface Scan

All nine threats in the plan's `<threat_model>` are mitigated as implemented:

| Threat | Mitigation | Verified |
|--------|-----------|---------|
| T-06-04-01 Non-owner POST | `if project.owner != request.user` early-return | In bulk_add_crew |
| T-06-04-02 Wrong crew owner | `get_object_or_404(Crew, id=crew_id, owner=request.user)` | In bulk_add_crew |
| T-06-04-03 CSRF | `{% csrf_token %}` in panel form + Django CsrfViewMiddleware | In invite_user.html |
| T-06-04-04 Duplicate ProjectMember | Upfront dedupe set + DB unique_together safety net | In bulk_add_crew |
| T-06-04-05 Email storm (accepted) | SPEC Constraint: crews 1-10 members; sync send acceptable | Accepted as-is |
| T-06-04-06 Email info leak | Only owner_label + project.name + role + set_project URL in email | In send_crew_added_email |
| T-06-04-07 Email failure rolls back rows | D-10 log+swallow; rows committed before email loop | In bulk_add_crew |
| T-06-04-08 accept_invitation/send_invitation_email modified | git diff shows 0 matching lines | Verified |
| T-06-04-09 Repudiation | CrewProjectAdd + ProjectMember.invited_by + invited_at audit trail | In bulk_add_crew |

## Self-Check: PASSED

- `accounts/views.py` exists and contains `bulk_add_crew` and `send_crew_added_email`: FOUND
- `accounts/urls.py` contains `name='bulk_add_crew'`: FOUND
- `templates/accounts/invite_user.html` contains additive panel (27 new lines, 0 deletions): FOUND
- Commit 6ba1867 exists: FOUND (`feat(06-04): add bulk_add_crew view, send_crew_added_email helper, owner_crews context`)
- Commit a081a29 exists: FOUND (`feat(06-04): add bulk_add_crew URL route to accounts/urls.py`)
- Commit 0b81ebc exists: FOUND (`feat(06-04): add additive 'Add your crew' panel to invite_user.html`)
- `python manage.py check` exits 0: PASSED
- `reverse('bulk_add_crew', args=[1, 2])` resolves to `/projects/1/invite/add-crew/2/`: PASSED
- Template renders with `owner_crews=[]`: PASSED
