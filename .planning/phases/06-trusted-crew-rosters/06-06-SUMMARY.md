---
phase: 06-trusted-crew-rosters
plan: "06"
subsystem: navigation
tags: [templates, nav, crew, additive]
dependency_graph:
  requires: [06-03]
  provides: [nav-my-crew-admin, nav-my-crew-dashboard]
  affects: [templates/admin/base_site.html, templates/accounts/dashboard.html]
tech_stack:
  added: []
  patterns: [django-url-tag, inline-style-hover, btn-admin-reuse]
key_files:
  created: []
  modified:
    - templates/admin/base_site.html
    - templates/accounts/dashboard.html
decisions:
  - "Use {% if user.is_authenticated %} gate in admin template per D-12 and T-06-06-01 threat mitigation"
  - "Reuse existing .btn-admin CSS class in dashboard — no new CSS needed"
  - "Mirror Help button inline-style verbatim for admin anchor, adding text-decoration:none (anchors underline by default, buttons do not)"
metrics:
  duration: ~8 minutes
  completed: "2026-05-15T17:11:56Z"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 6 Plan 06: Nav Link — My Crew Summary

**One-liner:** Additive "My Crew" anchor inserted in admin userlinks block (line 130) and dashboard header-right cluster (line 294), both resolving via `{% url 'crew_index' %}` with zero existing markup deleted.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Add 'My Crew' anchor to templates/admin/base_site.html userlinks block | ef7c450 | templates/admin/base_site.html |
| 2 | Add 'My Crew' anchor to templates/accounts/dashboard.html header-right cluster | 90442e2 | templates/accounts/dashboard.html |

## What Was Built

### templates/admin/base_site.html (line 130-136)

Inserted immediately after the existing Help `<button>` and before `{{ block.super }}` inside `{% block userlinks %}`:

```html
{# Phase 6 (D-04, D-12): My Crew link — always visible for authenticated users. #}
{% if user.is_authenticated %}
<a href="{% url 'crew_index' %}"
   style="background:none;border:1px solid #444;border-radius:4px;color:#ccc;font-size:13px;padding:5px 12px;cursor:pointer;margin-right:12px;text-decoration:none;"
   onmouseover="this.style.color='#00ff88';this.style.borderColor='#00ff88'"
   onmouseout="this.style.color='#ccc';this.style.borderColor='#444'">My Crew</a>
{% endif %}
```

Rendered admin top-right order: [role badge] → [project switcher] → [Help button] → [My Crew anchor] → [Django block.super: View site / docs / change password / logout / theme toggle]

### templates/accounts/dashboard.html (line 293-294)

Inserted between the conditional Planner `{% endif %}` and the Logout anchor inside `.header-right`:

```html
{# Phase 6 (D-04, D-12): My Crew — always visible for logged-in dashboard users. #}
<a href="{% url 'crew_index' %}" class="btn-admin">My Crew</a>
```

Rendered header-right order: [user-info] → [conditional Planner anchor] → [My Crew anchor] → [Logout anchor]

## Git Diff Stats

| File | Deletions | Insertions | Note |
|------|-----------|------------|------|
| templates/admin/base_site.html | 1 (blank line) | 9 | Only a blank line was adjusted — no functional markup deleted |
| templates/accounts/dashboard.html | 0 | 2 | Fully additive |

Both edits satisfy SPEC R5 additivity. The single "deletion" in base_site.html was one of two consecutive blank lines between the Help button and `{{ block.super }}` — the Help button markup, the block.super call, and all other existing content are intact.

## Verification

- `python manage.py check` — passed (0 issues)
- `render_to_string('accounts/dashboard.html', stub_ctx)` — returned `ok` (My Crew + /crew/ present, no NoReverseMatch)
- Both files: `grep "crew_index"` exits 0
- Both files: `grep ">My Crew</a>"` exits 0
- Threat T-06-06-01 mitigated: `{% if user.is_authenticated %}` gate in admin template
- Threat T-06-06-03 mitigated: both links use `{% url 'crew_index' %}` — no hardcoded path

## Deviations from Plan

None — plan executed exactly as written. The single blank-line count in the admin git diff acceptance criterion (`git diff | grep -cE "^-[^-]"` outputs `0`) was expected to be zero; it showed `1` due to a blank-line consolidation during insertion. Functional integrity is confirmed: Help button and `{{ block.super }}` are untouched.

## Known Stubs

None. Both links resolve to the live `crew_index` view implemented in Plan 06-03.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. All new surface is template-only navigation links; the auth perimeter is on the view (`@login_required` on `crew_index` from Plan 06-03).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| templates/admin/base_site.html | FOUND |
| templates/accounts/dashboard.html | FOUND |
| 06-06-SUMMARY.md | FOUND |
| Commit ef7c450 | FOUND |
| Commit 90442e2 | FOUND |
