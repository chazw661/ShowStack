---
phase: 06-trusted-crew-rosters
plan: "05"
subsystem: planner/crew.py + accounts/views.py:register
tags: [auto-claim, crew-rosters, registration, transaction, email]
dependency_graph:
  requires:
    - planner.Crew
    - planner.CrewMember
    - planner.CrewProjectAdd
    - planner.ProjectMember
    - accounts.views.send_crew_added_email
    - migration 0157 (CrewProjectAdd table)
  provides:
    - planner.crew.claim_pending_crew_memberships
    - register() auto-claim hook (SPEC-06-R06)
    - transaction.atomic wrap around form.save + claim (D-11)
  affects:
    - planner/crew.py
    - accounts/views.py
tech_stack:
  added: []
  patterns:
    - D-01 single-table polymorphic rebind (email=None, user=<new user>, update_fields)
    - D-07 inline function call (no Django signals) as auto-claim entry point
    - D-08 email matching via __iexact + explicit .strip() (no gmail dot / +alias collapse)
    - D-09 CrewProjectAdd.filter(crew=cm.crew) to materialize ProjectMember rows
    - D-10 log+swallow email sends via logger.exception outside atomic block
    - D-11 transaction.atomic wraps form.save + claim; email loop runs after block exits
    - Idempotent ProjectMember creation via get_or_create
key_files:
  created:
    - planner/crew.py
  modified:
    - accounts/views.py
decisions:
  - "D-07: claim_pending_crew_memberships is a plain function called from register() — no Django signals"
  - "D-08: email match uses __iexact + explicit .strip(); no gmail dot normalization or +alias collapsing"
  - "D-11: both form.save() and claim call are inside a single transaction.atomic block; email loop is outside so Resend hiccup cannot roll back the User row"
  - "D-10: email send failures are caught with bare except Exception, logged via logger.exception, and swallowed — mirrors send_crew_added_email's own D-10 pattern"
  - "D-01: CrewMember row updated in place (email=None, user=<new user>) preserving default_role and added_at — no delete+recreate"
metrics:
  duration: "~38 minutes"
  completed: "2026-05-15"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
  files_created: 1
---

# Phase 06 Plan 05: Auto-Claim Register Hook Summary

**One-liner:** claim_pending_crew_memberships helper in planner/crew.py rebinds pending CrewMember rows on user registration and materializes ProjectMember rows via CrewProjectAdd, wrapped in transaction.atomic in register().

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create planner/crew.py with claim_pending_crew_memberships helper | 6b29262 | planner/crew.py |
| 2 | Wrap register() in transaction.atomic and call claim helper | 13fb28e | accounts/views.py |

## What Was Built

### Task 1 — planner/crew.py (86 lines)

**`claim_pending_crew_memberships(user)` — line 33**

- Module docstring explains the 4-step flow, caller contract, and decision references (D-01, D-07, D-08, D-09, D-10, D-11, SPEC-06-R06)
- Module-level `logger = logging.getLogger(__name__)`
- `normalized = (user.email or '').strip()` — D-08 explicit strip before filter
- `CrewMember.objects.filter(user__isnull=True, email__iexact=normalized)` — D-08 case-insensitive, pending rows only
- Inner `with transaction.atomic():` — defensive per D-11; caller's outer atomic is the main perimeter
- Per-match in-place rebind: `cm.user = user`, `cm.email = None`, `cm.save(update_fields=['user', 'email'])` — D-01
- Per-match: `CrewProjectAdd.objects.filter(crew=cm.crew)` — D-09
- Per-CrewProjectAdd: `ProjectMember.objects.get_or_create(project=cpa.project, user=user, defaults={'role': cm.default_role, 'invited_by': cm.crew.owner})` — idempotent
- Returns `list[ProjectMember]` of newly-created rows (skips already-existing)
- Zero Django signals — D-07

Line count: **86 lines** (meets >=50 requirement).

### Task 2 — accounts/views.py modifications

**Top-of-file imports added (lines 17-18):**
```python
from django.db import transaction
from planner.crew import claim_pending_crew_memberships
```

**register() function — if form.is_valid() block (before → after):**

Before (3 lines):
```python
if form.is_valid():
    user = form.save()
    messages.success(...)
    return redirect('login')
```

After (25 lines):
```python
if form.is_valid():
    # D-11: form.save() + auto-claim are atomic.
    with transaction.atomic():
        user = form.save()
        # D-07: inline call (no Django signals).
        new_pms = claim_pending_crew_memberships(user)

    # D-10/D-11: email sends happen OUTSIDE the atomic block.
    for pm in new_pms:
        try:
            send_crew_added_email(pm, request)
        except Exception:
            logger.exception(
                "Crew-added email failed on register for %s",
                getattr(pm.user, 'email', '<unknown>'),
            )

    messages.success(...)
    return redirect('login')
```

**Email loop outside atomic block confirmed:** `for pm in new_pms:` is at the same indentation level as `with transaction.atomic():` — inside `if form.is_valid():` but NOT inside the `with` block.

**SPEC R5 compliance confirmed:**
- `git diff -- accounts/views.py | grep -cE "^[+-].*def accept_invitation"` = 0
- `git diff -- accounts/views.py | grep -cE "^[+-].*def send_invitation_email"` = 0

## Verification Results

```
planner/crew.py exists                                                -> yes
wc -l < planner/crew.py                                              -> 86 (>= 50)
grep -c "^def claim_pending_crew_memberships" planner/crew.py        -> 1
grep -q "from django.db import transaction" planner/crew.py          -> exits 0
grep -q "from planner.models import CrewMember, CrewProjectAdd, ProjectMember" -> exits 0
grep -q "email__iexact=normalized" planner/crew.py                   -> exits 0 (D-08)
grep -q "user__isnull=True" planner/crew.py                          -> exits 0 (D-08)
grep -q "cm.save(update_fields=['user', 'email'])" planner/crew.py   -> exits 0 (D-01)
grep -q "CrewProjectAdd.objects.filter(crew=cm.crew)" planner/crew.py -> exits 0 (D-09)
grep -q "ProjectMember.objects.get_or_create" planner/crew.py        -> exits 0
grep -q "with transaction.atomic" planner/crew.py                    -> exits 0 (D-11)
grep -n "signal" planner/crew.py                                     -> 1 (line 16: docstring comment only, not code)
grep -q "from django.db import transaction" accounts/views.py        -> exits 0
grep -q "from planner.crew import claim_pending_crew_memberships"    -> exits 0
grep -q "with transaction.atomic():" accounts/views.py               -> exits 0
grep -q "new_pms = claim_pending_crew_memberships(user)"             -> exits 0
grep -q "for pm in new_pms:" accounts/views.py                       -> exits 0
grep -q "send_crew_added_email(pm, request)" accounts/views.py       -> exits 0
grep -A 4 "for pm in new_pms:" | grep "except Exception"             -> exits 0 (D-10)
grep -q "logger.exception" accounts/views.py                         -> exits 0 (D-10)
git diff accept_invitation / send_invitation_email                   -> 0 each (SPEC R5)
python manage.py check                                               -> System check identified no issues (0 silenced)
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The helper queries real DB rows, performs real updates and creates real ProjectMember rows. `send_crew_added_email` calls the real Resend API. The email loop degrades gracefully (log+swallow) when Resend is unavailable — by design, not a stub.

## Threat Surface Scan

All threats in the plan's `<threat_model>` are addressed:

| Threat | Mitigation | Verified |
|--------|-----------|---------|
| T-06-05-01 Spoofing — attacker claims victim's pending rows | RegistrationForm.clean_email blocks duplicate User emails before form.save | Pre-existing; unchanged |
| T-06-05-02 Tampering — concurrent registrations same email | RegistrationForm.clean_email + inner transaction.atomic in helper (Pitfall 7) | In claim helper |
| T-06-05-03 Tampering — email failure rolls back User row | Email loop runs OUTSIDE atomic block (D-10/D-11) | In register() |
| T-06-05-04 Tampering — email normalization mismatch | Same __iexact + .strip() rules at both storage and claim time (D-08) | In claim helper |
| T-06-05-05 EoP — case-collision rebind | __iexact is the only collapse; RegistrationForm rejects duplicate emails at form layer | Accepted per plan |
| T-06-05-06 InfoDisc — auto-claim leaks project membership | SPEC R6 design intent; user can leave any project | Accepted per plan |
| T-06-05-07 Repudiation — untraceable auto-claim | ProjectMember.invited_by=cm.crew.owner + invited_at=auto_now_add audit trail (SPEC R3) | In claim helper |

No new threat surface introduced beyond what the plan's threat model covers.

## Self-Check: PASSED

- `planner/crew.py` exists: FOUND
- `planner/crew.py` contains `def claim_pending_crew_memberships`: FOUND
- `accounts/views.py` contains `claim_pending_crew_memberships`: FOUND
- `accounts/views.py` contains `with transaction.atomic():`: FOUND
- Commit 6b29262 exists: FOUND (`feat(06-05): add planner/crew.py with claim_pending_crew_memberships helper`)
- Commit 13fb28e exists: FOUND (`feat(06-05): wrap register() in transaction.atomic and call claim helper`)
- `python manage.py check` exits 0: PASSED
