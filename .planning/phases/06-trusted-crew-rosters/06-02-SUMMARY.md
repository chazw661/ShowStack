---
phase: 06-trusted-crew-rosters
plan: "02"
subsystem: accounts/admin + planner/admin_ordering
tags: [admin, crew-rosters, sidebar-ordering]
dependency_graph:
  requires:
    - planner.Crew
    - planner.CrewMember
    - planner.CrewProjectAdd
    - migration 0157
  provides:
    - accounts.admin.CrewAdmin
    - accounts.admin.CrewMemberAdmin
    - accounts.admin.CrewProjectAddAdmin
    - showstack_admin_site registrations for Crew/CrewMember/CrewProjectAdd
    - sidebar order slots 2.3 / 2.5 / 2.7
  affects:
    - accounts/admin.py
    - planner/admin_ordering.py
tech_stack:
  added: []
  patterns:
    - BaseEquipmentAdmin subclass for new ModelAdmin classes (mirrors ProjectMemberAdmin)
    - showstack_admin_site.register() — NEVER admin.site.register()
    - Float slot ordering in order_map dict (2.3/2.5/2.7 between projectmember=2 and invitation=3)
key_files:
  created: []
  modified:
    - accounts/admin.py
    - planner/admin_ordering.py
decisions:
  - "Used BaseEquipmentAdmin (not BaseAdmin) for all three crew admins — consistent with ProjectMemberAdmin analog"
  - "Float slots 2.3/2.5/2.7 per plan Pitfall 6: slot between projectmember=2 and invitation=3 without renumbering existing entries"
  - "CrewProjectAddAdmin marked with readonly_fields=['added_at'] — audit-read-mostly intent per plan"
metrics:
  duration: "~3 minutes"
  completed: "2026-05-15"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
  files_created: 0
---

# Phase 06 Plan 02: Admin Registration Summary

**One-liner:** Three Phase 6 ModelAdmin classes (CrewAdmin, CrewMemberAdmin, CrewProjectAddAdmin) registered on showstack_admin_site with sidebar order slots 2.3/2.5/2.7 in planner/admin_ordering.py.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add CrewAdmin/CrewMemberAdmin/CrewProjectAddAdmin to accounts/admin.py | c4e4ee7 | accounts/admin.py |
| 2 | Add crew/crewmember/crewprojectadd entries to planner/admin_ordering.py | a796109 | planner/admin_ordering.py |

## What Was Built

### Task 1 — ModelAdmin classes in accounts/admin.py

Three new classes appended at lines 216–238, after the existing `showstack_admin_site.register(UserProfile, UserProfileAdmin)` line:

- **`CrewAdmin`** (line 216): `list_display = ['name', 'owner', 'created_at', 'updated_at']`, `readonly_fields = ['created_at', 'updated_at']`, search by name/owner.
- **`CrewMemberAdmin`** (line 223): `list_display = ['crew', 'user', 'email', 'default_role', 'added_at']`, `readonly_fields = ['added_at']`, search by crew name/user/email.
- **`CrewProjectAddAdmin`** (line 230): `list_display = ['crew', 'project', 'added_at']`, `readonly_fields = ['added_at']`, read-mostly audit surface.

Three register calls at lines 237–239:
```python
showstack_admin_site.register(Crew, CrewAdmin)
showstack_admin_site.register(CrewMember, CrewMemberAdmin)
showstack_admin_site.register(CrewProjectAdd, CrewProjectAddAdmin)
```

No `admin.site.register()` calls introduced (CLAUDE.md mandate).

### Task 2 — order_map entries in planner/admin_ordering.py

Three new keys inserted between `'projectmember': 2` and `'invitation': 3`:

```python
'crew': 2.3,           # Phase 6
'crewmember': 2.5,     # Phase 6
'crewprojectadd': 2.7, # Phase 6
```

The existing `ordered_get_app_list` monkey-patch picks up new keys automatically via `order_map.get(model_lower, 999)` — no other changes required.

## Verification Results

```
grep -c "class CrewAdmin(BaseEquipmentAdmin)" accounts/admin.py         -> 1
grep -c "class CrewMemberAdmin(BaseEquipmentAdmin)" accounts/admin.py   -> 1
grep -c "class CrewProjectAddAdmin(BaseEquipmentAdmin)" accounts/admin.py -> 1
grep -c "showstack_admin_site.register(Crew, CrewAdmin)" accounts/admin.py -> 1
grep -c "showstack_admin_site.register(CrewMember, CrewMemberAdmin)" accounts/admin.py -> 1
grep -c "showstack_admin_site.register(CrewProjectAdd, CrewProjectAddAdmin)" accounts/admin.py -> 1
grep -c "'crew': 2.3" planner/admin_ordering.py                          -> 1
grep -c "'crewmember': 2.5" planner/admin_ordering.py                    -> 1
grep -c "'crewprojectadd': 2.7" planner/admin_ordering.py                -> 1
grep -E "^admin\.site\.register\(Crew" accounts/admin.py                 -> (no match — exit 1, correct)
python manage.py check                                                   -> System check identified no issues (0 silenced)
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. This plan is admin registration only — no views, no templates, no data flow. The admin surfaces are fully functional for CRUD operations once models from Plan 01 are migrated.

## Threat Surface Scan

No new network endpoints or auth paths introduced. The `showstack_admin_site` inherits Django admin's `staff_member_required` gate — T-06-02-01 (elevation of privilege for non-staff) is fully mitigated by the existing gate. T-06-02-02 (tamper via admin with both user+email) is mitigated at DB level by the CheckConstraint from Plan 01 migration 0157. No new threat surface beyond what is documented in the plan's threat model.

## Self-Check: PASSED

- `accounts/admin.py` exists: FOUND
- `planner/admin_ordering.py` exists: FOUND
- Commit c4e4ee7 exists: FOUND (`feat(06-02): add CrewAdmin, CrewMemberAdmin, CrewProjectAddAdmin to accounts/admin.py`)
- Commit a796109 exists: FOUND (`feat(06-02): add crew/crewmember/crewprojectadd to admin_ordering.py order_map`)
- `python manage.py check` exits 0: PASSED
- No `admin.site.register(Crew` in accounts/admin.py: CONFIRMED
