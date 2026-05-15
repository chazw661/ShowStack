---
phase: 06-trusted-crew-rosters
reviewed: 2026-05-14T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - accounts/admin.py
  - accounts/urls.py
  - accounts/views.py
  - marketing/views.py
  - planner/admin_ordering.py
  - planner/crew.py
  - planner/migrations/0157_crew_crewmember_crewprojectadd.py
  - planner/models.py
  - planner/tests/test_crew_rosters.py
  - templates/accounts/crew_detail.html
  - templates/accounts/crew_index.html
  - templates/accounts/dashboard.html
  - templates/accounts/invite_user.html
  - templates/admin/base_site.html
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-05-14
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 6 adds Trusted Crew Rosters: three new models (Crew, CrewMember, CrewProjectAdd), six CRUD views, a bulk-add view, a `claim_pending_crew_memberships` helper, admin registrations, migration, and a comprehensive test suite. The overall design is sound — the XOR constraint on CrewMember, the single-table rebind pattern for auto-claim, and the post-atomic email loop are all well-implemented. One critical bug will cause a NameError crash on the invite page in production. Three warnings cover dead code and logging inconsistencies introduced in this phase. Three info items are minor quality items.

---

## Critical Issues

### CR-01: `Crew` used in `invite_user` before it is imported — guaranteed NameError

**File:** `accounts/views.py:180`

**Issue:** `invite_user` (line 147) references `Crew.objects.filter(...)` at line 180. The module-level import of `Crew` does not happen until line 660 (`from planner.models import Crew, CrewMember, CrewProjectAdd`), which is below the function. In CPython, function bodies are executed at call time but name resolution happens against the module globals at that point. Because the module-level import for `Crew` is placed far below the function definition (not at the top of the file), any call to `invite_user` will raise `NameError: name 'Crew' is not defined`.

The top-of-file imports at lines 10 and 14 bring in `Project`, `ProjectMember`, and `Invitation` but do not include `Crew`, `CrewMember`, or `CrewProjectAdd`. The Phase 6 import block at line 660 comes after several hundred lines of pre-existing view functions.

**Fix:** Move the Phase 6 import to the top of the file alongside the other `planner.models` imports:

```python
# accounts/views.py — top of file, merge with existing planner.models imports
from planner.models import Project, ProjectMember, Invitation, Crew, CrewMember, CrewProjectAdd
```

Then remove the duplicate import at line 660.

---

## Warnings

### WR-01: Dead code block after `return` in `project_access_requests` (pre-existing, worsened by Phase 6 edits)

**File:** `accounts/views.py:603-610`

**Issue:** Lines 603-610 are unreachable — they are an exact duplicate of lines 594-601, placed after the `return render(...)` on line 601. This appears to be a paste artifact from Phase 6 editing. While not introduced by Phase 6, it is visible in the diff scope and would confuse future maintainers.

**Fix:** Delete lines 603-610.

```python
# DELETE the following duplicate block (lines 603-610):
    pending = ProjectAccessRequest.objects.filter(project=project, status='pending')
    reviewed = ProjectAccessRequest.objects.filter(project=project).exclude(status='pending')

    return render(request, 'accounts/access_requests.html', {
        'project': project,
        'pending': pending,
        'reviewed': reviewed,
    })
```

### WR-02: `send_crew_added_email` uses `print()` instead of `logger` — breaks D-10 log contract

**File:** `accounts/views.py:853,856`

**Issue:** The function docstring explicitly cites "D-10: log + swallow" as its contract, and `bulk_add_crew` (line 922) calls `logger.exception(...)` for email failures. However, `send_crew_added_email` itself uses bare `print()` for both success (line 853) and the caught exception (line 856). This means email failures are silent in Railway's structured log stream (which captures `logging` output but not stdout in all configurations) and success confirmation is inconsistently handled compared to every other email helper in the file.

**Fix:**

```python
# accounts/views.py — inside send_crew_added_email
try:
    resend.Emails.send({...})
    logger.debug("Crew-added email sent to %s", project_member.user.email)
except Exception:
    # D-10: log + swallow — do NOT re-raise.
    logger.exception(
        "Crew-added email error for %s",
        getattr(project_member.user, 'email', '<unknown>'),
    )
```

### WR-03: `bulk_add_crew` catches `Exception` from `send_crew_added_email` but the function already swallows it — double-wrapping is misleading

**File:** `accounts/views.py:918-925`

**Issue:** `send_crew_added_email` catches all exceptions internally and does not re-raise (line 854-856). The `try/except Exception` block in `bulk_add_crew` (lines 918-925) therefore can never fire for Resend failures — `send_crew_added_email` will return normally whether or not the email succeeded. The outer `logger.exception` call at line 921 will never execute. This is a latent bug: if `send_crew_added_email` is ever refactored to re-raise (matching `send_invitation_email`, which does re-raise), the outer catch would activate correctly — but as-is, the outer handler is dead code that creates a false sense of resilience.

The same pattern exists in `marketing/views.py` (lines 96-103) and `accounts/views.py` register hook (lines 44-51) where the function is `claim_pending_crew_memberships`, which does not swallow internally — so those outer catches are necessary. The inconsistency is only in the crew-email function.

**Fix:** Either have `send_crew_added_email` not catch the exception (let the caller handle it) and keep the outer catch, or keep the internal catch and remove the outer one. The latter is simpler given the D-10 "log + swallow" contract:

```python
# accounts/views.py — bulk_add_crew email loop: simplify to direct call
# (send_crew_added_email already swallows internally per D-10)
for pm in new_rows:
    send_crew_added_email(pm, request)
```

---

## Info

### IN-01: `print()` debug artifact in `admin_ordering.py` (pre-existing, not Phase 6)

**File:** `planner/admin_ordering.py:8-10, 45`

**Issue:** Three `print()` calls fire on every admin page load: the banner at lines 8-10 and the per-request debug line at line 45. Not introduced by Phase 6, but the new crew entries are adjacent. Not a bug, but it produces noise in Railway logs and should be removed before go-live.

**Fix:** Remove the print statements or replace line 45 with `logger.debug(...)`.

### IN-02: `send_crew_added_email` is not `@login_required` but is only reachable via authenticated callers — no vulnerability, but inconsistent pattern

**File:** `accounts/views.py:806`

**Issue:** Every view that calls `send_crew_added_email` (`bulk_add_crew`, `register` hook) is itself gated by `@login_required` or the registration form. The function is not a view and not URL-routable, so there is no exposure. However, it receives a `request` object and calls `request.build_absolute_uri`, which would work from any context. No action required — documenting for completeness.

### IN-03: `crew_index.html` calls `.crewmember_set.count` in the template loop — one extra query per crew card

**File:** `templates/accounts/crew_index.html:347`

**Issue:** `{{ crew.crewmember_set.count }}` issues one COUNT query per crew card in the grid. The `crew_index` view returns a plain queryset without `annotate(member_count=Count('crewmember'))`. For the small rosters typical of this app (1-10 crews per owner) this is not a correctness issue, but it is worth noting for future growth.

**Fix (optional):** In `crew_index` view, annotate:

```python
from django.db.models import Count
crews = Crew.objects.filter(owner=request.user).annotate(
    member_count=Count('crewmember')
).order_by('name')
```

Then in the template use `{{ crew.member_count }}` instead of `{{ crew.crewmember_set.count }}`.

---

_Reviewed: 2026-05-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
