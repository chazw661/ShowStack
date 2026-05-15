---
phase: 06-trusted-crew-rosters
plan: 02
type: execute
wave: 2
depends_on:
  - 06-01
files_modified:
  - accounts/admin.py
  - planner/admin_ordering.py
autonomous: true
requirements:
  - SPEC-06-R01
  - SPEC-06-R02
user_setup: []
must_haves:
  truths:
    - "Superuser can list, create, edit, delete Crew rows from the showstack_admin_site"
    - "Superuser can list, create, edit, delete CrewMember rows from the showstack_admin_site"
    - "Superuser can list CrewProjectAdd rows for audit (read-mostly)"
    - "Crew/CrewMember/CrewProjectAdd appear in the correct sidebar grouping (User/Project Management cluster, between projectmember=2 and invitation=3)"
    - "All registrations use showstack_admin_site, NOT admin.site (CLAUDE.md mandate)"
  artifacts:
    - path: "accounts/admin.py"
      provides: "CrewAdmin, CrewMemberAdmin, CrewProjectAddAdmin classes + registrations"
      contains: "showstack_admin_site.register(Crew"
    - path: "planner/admin_ordering.py"
      provides: "Sidebar order entries for crew, crewmember, crewprojectadd"
      contains: "'crew':"
  key_links:
    - from: "accounts/admin.py"
      to: "planner.admin_site.showstack_admin_site"
      via: "import + register call"
      pattern: "showstack_admin_site\\.register\\(Crew"
    - from: "planner/admin_ordering.py"
      to: "order_map dict"
      via: "key insertion"
      pattern: "'crew':\\s*2\\."
---

<objective>
Register `Crew`, `CrewMember`, and `CrewProjectAdd` on `showstack_admin_site` per CLAUDE.md convention, and update `planner/admin_ordering.py` so the new models appear in the correct sidebar position (between `projectmember=2` and `invitation=3`).

Purpose: Give superusers an audit/edit surface for crew rosters (per CONTEXT.md "Claude's Discretion: Admin registration"). The primary end-user UI is the custom `/accounts/crew/` pages (Plan 03), but admin must remain functional per CLAUDE.md.
Output: Three new ModelAdmin classes + three register calls in `accounts/admin.py`; three new entries in `planner/admin_ordering.py` `order_map`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md
@.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md
@.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md
@accounts/admin.py
@planner/admin_ordering.py

<interfaces>
<!-- Existing admin registration pattern executor MUST mirror. Extracted verbatim from accounts/admin.py:192-209. -->

From accounts/admin.py (existing pattern at lines 192-209):
```python
# ==================== REGISTER ALL MODELS ====================
from planner.admin_site import showstack_admin_site
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin

# Register User with our custom admin
showstack_admin_site.register(User, BaseUserAdmin)

# Register Group with our custom admin
showstack_admin_site.register(Group, GroupAdmin)

# Register accounts models with their admin classes
showstack_admin_site.register(ProjectMember, ProjectMemberAdmin)
showstack_admin_site.register(Invitation, InvitationAdmin)
showstack_admin_site.register(UserProfile, UserProfileAdmin)
```

From accounts/admin.py:66 (ProjectMemberAdmin — closest analog with BaseEquipmentAdmin subclass):
```python
class ProjectMemberAdmin(BaseEquipmentAdmin):
    list_display = ['project', 'user', 'role', 'invited_by', 'invited_at']
    list_filter = ['role', 'invited_at']
    search_fields = ['project__name', 'user__username', 'user__email']
```

From planner/admin_ordering.py (User/Project Management cluster):
```python
order_map = {
    # Authentication & Authorization (0)
    'user': 0,
    'group': 0.5,
    # User/Project Management (1-4)
    'userprofile': 1,
    'projectmember': 2,
    'invitation': 3,
    'project': 4,
    ...
}
```

Phase 6 new keys must slot between `projectmember=2` and `invitation=3` per Pitfall 6 / D-13. Use `'crew': 2.3`, `'crewmember': 2.5`, `'crewprojectadd': 2.7`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add Crew/CrewMember/CrewProjectAdd ModelAdmins to accounts/admin.py</name>
  <files>accounts/admin.py</files>
  <read_first>
    - `accounts/admin.py` (full file — 209 lines — to verify existing import block and register pattern)
    - `accounts/admin.py:66-96` (ProjectMemberAdmin — closest analog for `BaseEquipmentAdmin` subclass shape)
    - `accounts/admin.py:100-147` (InvitationAdmin — analog for fieldsets/readonly patterns)
    - `accounts/admin.py:192-209` (the `showstack_admin_site.register(...)` block — append AFTER this)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` §"Claude's Discretion: Admin registration"
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` §"accounts/admin.py (+CrewAdmin, CrewMemberAdmin, CrewProjectAddAdmin)"
  </read_first>
  <action>
Append the following code to `accounts/admin.py` AFTER the existing `showstack_admin_site.register(UserProfile, UserProfileAdmin)` line (currently around line 209). Mirrors the existing `ProjectMemberAdmin` and `InvitationAdmin` shapes verbatim — same `BaseEquipmentAdmin` subclass, same `list_display`/`list_filter`/`search_fields` triplet.

```python
# ==================== PHASE 6: TRUSTED CREW ROSTERS ====================
from planner.models import Crew, CrewMember, CrewProjectAdd


class CrewAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'owner', 'created_at', 'updated_at']
    list_filter = ['created_at']
    search_fields = ['name', 'owner__username', 'owner__email']
    readonly_fields = ['created_at', 'updated_at']


class CrewMemberAdmin(BaseEquipmentAdmin):
    list_display = ['crew', 'user', 'email', 'default_role', 'added_at']
    list_filter = ['default_role', 'added_at']
    search_fields = ['crew__name', 'user__username', 'user__email', 'email']
    readonly_fields = ['added_at']


class CrewProjectAddAdmin(BaseEquipmentAdmin):
    list_display = ['crew', 'project', 'added_at']
    list_filter = ['added_at']
    search_fields = ['crew__name', 'project__name']
    readonly_fields = ['added_at']


showstack_admin_site.register(Crew, CrewAdmin)
showstack_admin_site.register(CrewMember, CrewMemberAdmin)
showstack_admin_site.register(CrewProjectAdd, CrewProjectAddAdmin)
```

CRITICAL per CLAUDE.md: registrations use `showstack_admin_site.register(...)`, NEVER `admin.site.register(...)`.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "class CrewAdmin(BaseEquipmentAdmin)" accounts/admin.py && grep -q "class CrewMemberAdmin(BaseEquipmentAdmin)" accounts/admin.py && grep -q "class CrewProjectAddAdmin(BaseEquipmentAdmin)" accounts/admin.py && grep -q "showstack_admin_site.register(Crew, CrewAdmin)" accounts/admin.py && grep -q "showstack_admin_site.register(CrewMember, CrewMemberAdmin)" accounts/admin.py && grep -q "showstack_admin_site.register(CrewProjectAdd, CrewProjectAddAdmin)" accounts/admin.py && ! grep -E "^admin\.site\.register\(Crew" accounts/admin.py && python manage.py check 2>&1 | tee /tmp/check_admin.out</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "class CrewAdmin(BaseEquipmentAdmin)" accounts/admin.py` outputs `1`
    - `grep -c "class CrewMemberAdmin(BaseEquipmentAdmin)" accounts/admin.py` outputs `1`
    - `grep -c "class CrewProjectAddAdmin(BaseEquipmentAdmin)" accounts/admin.py` outputs `1`
    - `grep -c "showstack_admin_site.register(Crew, CrewAdmin)" accounts/admin.py` outputs `1`
    - `grep -c "showstack_admin_site.register(CrewMember, CrewMemberAdmin)" accounts/admin.py` outputs `1`
    - `grep -c "showstack_admin_site.register(CrewProjectAdd, CrewProjectAddAdmin)" accounts/admin.py` outputs `1`
    - `grep -E "^admin\\.site\\.register\\(Crew" accounts/admin.py` exits non-zero (no use of `admin.site` per CLAUDE.md)
    - `grep -q "from planner.models import Crew, CrewMember, CrewProjectAdd" accounts/admin.py` exits 0
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
Three new ModelAdmin classes registered on `showstack_admin_site`. `python manage.py check` exits 0. No use of `admin.site` introduced.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add crew/crewmember/crewprojectadd entries to planner/admin_ordering.py</name>
  <files>planner/admin_ordering.py</files>
  <read_first>
    - `planner/admin_ordering.py` (full file — to locate the `order_map` dict and the User/Project Management cluster)
    - `CLAUDE.md` §"Custom admin site" — "Update `admin_ordering.py` whenever a new admin-registered model is added, otherwise the sidebar grouping will be wrong."
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` §"Pitfall 6: Forgetting to update planner/admin_ordering.py"
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` §"planner/admin_ordering.py edits"
  </read_first>
  <action>
Edit the `order_map` dict in `planner/admin_ordering.py`. Insert three new keys between the existing `'projectmember': 2,` line and the `'invitation': 3,` line. Use exact float slot values 2.3, 2.5, 2.7 per Pitfall 6 recommendation:

Before:
```python
        # User/Project Management (1-4)
        'userprofile': 1,
        'projectmember': 2,
        'invitation': 3,
        'project': 4,
```

After:
```python
        # User/Project Management (1-4)
        'userprofile': 1,
        'projectmember': 2,
        'crew': 2.3,           # Phase 6
        'crewmember': 2.5,     # Phase 6
        'crewprojectadd': 2.7, # Phase 6
        'invitation': 3,
        'project': 4,
```

No other edits required — the file's `get_app_list` monkey-patch is generic and picks up new keys automatically via `order_map.get(model_lower, 999)`.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -qE "'crew':\\s*2\\.3" planner/admin_ordering.py && grep -qE "'crewmember':\\s*2\\.5" planner/admin_ordering.py && grep -qE "'crewprojectadd':\\s*2\\.7" planner/admin_ordering.py && python manage.py check 2>&1 | tee /tmp/check_ordering.out</automated>
  </verify>
  <acceptance_criteria>
    - `grep -cE "'crew':\\s*2\\.3" planner/admin_ordering.py` outputs `1`
    - `grep -cE "'crewmember':\\s*2\\.5" planner/admin_ordering.py` outputs `1`
    - `grep -cE "'crewprojectadd':\\s*2\\.7" planner/admin_ordering.py` outputs `1`
    - `python manage.py check` exits 0
    - `python manage.py shell -c "from planner.admin_ordering import *; from planner.admin_site import showstack_admin_site; apps = showstack_admin_site.get_app_list(__import__('django.test.client', fromlist=['RequestFactory']).RequestFactory().get('/')); print('OK')" 2>&1 | grep -q "OK"` (the monkey-patch picks up the new keys without raising)
  </acceptance_criteria>
  <done>
Three new keys inserted in `order_map` at slots 2.3, 2.5, 2.7. Sidebar grouping reflects new Phase 6 models between projectmember and invitation. `python manage.py check` exits 0.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → Django admin | Authenticated admin users (staff_member_required) cross this boundary; standard Django admin perms apply |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-02-01 | Elevation of Privilege | Non-staff user accesses /admin/ crew pages | mitigate | `showstack_admin_site` inherits Django admin's `staff_member_required` gate; superuser-only by ShowStack convention |
| T-06-02-02 | Tampering | Admin creates CrewMember with both user+email | mitigate | DB CheckConstraint from Plan 01 rejects at insert; admin will surface the IntegrityError |
| T-06-02-03 | Information Disclosure | Cross-tenant Crew visibility in admin | accept | Admin is superuser-only by project policy; cross-tenant view is intentional for support |
| T-06-02-04 | Repudiation | Admin edits to Crew rows are untracked | accept | Django admin log_entries cover this; no new audit needed per SPEC |
</threat_model>

<verification>
- `python manage.py check` exits 0
- Three new ModelAdmin classes appear in `accounts/admin.py`
- Three new `order_map` keys appear in `planner/admin_ordering.py`
- No `admin.site.register(...)` for any Phase 6 model
</verification>

<success_criteria>
- Superuser visits `/admin/` and sees Crew + CrewMember + CrewProjectAdd in the User/Project Management sidebar cluster
- All three admins are functional (can create/edit/delete rows)
- Sidebar order respects float slots 2.3, 2.5, 2.7
</success_criteria>

<output>
After completion, create `.planning/phases/06-trusted-crew-rosters/06-02-SUMMARY.md` capturing: line numbers of new admin classes, grep counts confirming registrations, and `python manage.py check` output.
</output>
