---
phase: 06-trusted-crew-rosters
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - planner/models.py
  - planner/migrations/0157_crew_crewmember_crewprojectadd.py
autonomous: true
requirements:
  - SPEC-06-R01
  - SPEC-06-R02
  - SPEC-06-R05
  - SPEC-06-R08
user_setup: []
must_haves:
  truths:
    - "Crew model exists, owner-scoped, with unique (owner, name) constraint"
    - "CrewMember model exists, single table with nullable user FK XOR nullable email"
    - "DB rejects CrewMember rows with both user and email set"
    - "DB rejects duplicate (crew, user) rows when user is non-null"
    - "DB rejects duplicate (crew, email) rows when email is non-null (Postgres NULL-not-distinct workaround)"
    - "CrewProjectAdd link table tracks which projects each crew has been bulk-added to"
    - "Invitation model is byte-identical to pre-phase state (SPEC R5 additivity)"
    - "Migration 0157 applies to local SQLite without errors"
  artifacts:
    - path: "planner/models.py"
      provides: "Crew, CrewMember, CrewProjectAdd model definitions"
      contains: "class Crew(models.Model)"
    - path: "planner/migrations/0157_crew_crewmember_crewprojectadd.py"
      provides: "Additive migration creating planner_crew, planner_crewmember, planner_crewprojectadd tables"
      contains: "CreateModel"
  key_links:
    - from: "planner/models.py:Crew"
      to: "settings.AUTH_USER_MODEL"
      via: "ForeignKey owner with related_name='owned_crews'"
      pattern: "owner = models.ForeignKey\\("
    - from: "planner/models.py:CrewMember"
      to: "planner/models.py:Crew"
      via: "ForeignKey crew with on_delete=CASCADE"
      pattern: "crew = models.ForeignKey\\(Crew"
    - from: "planner/models.py:CrewProjectAdd"
      to: "planner/models.py:Project"
      via: "ForeignKey project with related_name='crew_adds'"
      pattern: "project = models.ForeignKey\\(Project"
---

<objective>
Create the three new Phase 6 models — `Crew`, `CrewMember`, `CrewProjectAdd` — in `planner/models.py`, then generate and locally-apply migration `0157_crew_crewmember_crewprojectadd.py`. This is the schema foundation that Plans 02–07 depend on.

Purpose: Establish the data substrate for trusted crew rosters per locked decisions D-01, D-02, D-09, D-13, D-15. All downstream plans (admin registration, CRUD views, bulk-add, auto-claim, tests) read these tables directly.
Output: Three new model classes + one new migration file. Zero edits to existing models. `python manage.py check` exits 0.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/phases/06-trusted-crew-rosters/06-SPEC.md
@.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md
@.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md
@.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md
@planner/models.py

<interfaces>
<!-- Existing models that the new Phase 6 models reference. Executor uses these directly — no codebase exploration needed. -->

From planner/models.py:692 (ProjectMember — newer style with auth.User direct import):
```python
class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ROLES = [('editor', 'Editor - Can view and edit'), ('viewer', 'Viewer - Can only view')]
    role = models.CharField(max_length=20, choices=ROLES, default='editor')
    invited_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitations_sent')
    class Meta:
        unique_together = ['project', 'user']
```

From planner/models.py:720 (ProjectAccessRequest — newer style using settings.AUTH_USER_MODEL — PREFER this style for Phase 6 per Pitfall 4):
```python
class ProjectAccessRequest(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='access_requests')
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='access_requests')
    ...
    class Meta:
        unique_together = ('project', 'requester')
        ordering = ['-requested_at']
```

Existing imports at top of planner/models.py (verify before adding):
- `from django.db import models`
- `from django.conf import settings`
- `from django.contrib.auth.models import User`

Imports NOT yet at top of file (must be added):
- `from django.db.models import CheckConstraint, UniqueConstraint, Q`

The latest existing migration is `0156_remove_device_parent_console.py`, so the new migration MUST be `0157_crew_crewmember_crewprojectadd.py` with `dependencies = [('planner', '0156_remove_device_parent_console')]`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add Crew, CrewMember, CrewProjectAdd models to planner/models.py</name>
  <files>planner/models.py</files>
  <read_first>
    - `planner/models.py:1-50` (existing imports — verify `Q`, `CheckConstraint`, `UniqueConstraint` are NOT already imported)
    - `planner/models.py:692-748` (ProjectMember + ProjectAccessRequest analogs)
    - `planner/models.py:3809-3849` (Invitation reference for EmailField shape — do NOT modify)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` §"Decisions" D-01, D-02, D-09, D-13, D-15
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` §"Pattern 1: XOR check constraint (D-01)" and §"Pitfall 1: unique_together on a nullable column"
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` §"planner/models.py — Crew + CrewMember + CrewProjectAdd (model, CRUD)" — has the verbatim model code
  </read_first>
  <action>
Insert the three new models at the end of the "Project Membership" cluster — immediately AFTER the existing `class ProjectAccessRequest` ends (around line 748) and BEFORE the next non-membership section comment. Add `from django.db.models import CheckConstraint, UniqueConstraint, Q` near the top of the file with the other `from django.db...` imports if not already present.

Append the EXACT code below (per D-01, D-02, D-09, D-15 — uses Django 5.2 `condition=` not deprecated `check=`, uses partial `UniqueConstraint` per Pitfall 1, uses `settings.AUTH_USER_MODEL` per Pitfall 4):

```python
class Crew(models.Model):
    """Owner-scoped named roster of trusted collaborators (Phase 6 — SPEC-06-R01, R02, D-02)."""
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_crews',
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('owner', 'name'),)
        ordering = ['name']
        verbose_name = "Crew"
        verbose_name_plural = "Crews"

    def __str__(self):
        return f"{self.name} (owned by {self.owner.username})"


class CrewMember(models.Model):
    """Single-table polymorphic roster row: existing user XOR pending email (Phase 6 — SPEC-06-R01, R02, R06, D-01, D-15)."""
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='crew_memberships',
    )
    email = models.EmailField(null=True, blank=True)

    ROLES = [
        ('editor', 'Editor'),
        ('viewer', 'Viewer'),
    ]
    default_role = models.CharField(max_length=20, choices=ROLES, default='editor')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=(
                    Q(user__isnull=False, email__isnull=True) |
                    Q(user__isnull=True, email__isnull=False)
                ),
                name='crewmember_user_xor_email',
            ),
            UniqueConstraint(
                fields=['crew', 'user'],
                condition=Q(user__isnull=False),
                name='uniq_crewmember_crew_user',
            ),
            UniqueConstraint(
                fields=['crew', 'email'],
                condition=Q(email__isnull=False),
                name='uniq_crewmember_crew_email',
            ),
        ]
        ordering = ['added_at']
        verbose_name = "Crew Member"
        verbose_name_plural = "Crew Members"

    def __str__(self):
        label = self.user.username if self.user_id else f"{self.email} (pending)"
        return f"{label} → {self.crew.name}"


class CrewProjectAdd(models.Model):
    """Tracks which projects a crew has been bulk-added to (Phase 6 — D-09, supports SPEC-06-R06 auto-claim).

    Read by the auto-claim helper (planner/crew.py) to materialize ProjectMember rows
    for newly-registered users whose email matched a pending CrewMember.
    """
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, related_name='project_adds')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='crew_adds')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('crew', 'project'),)
        ordering = ['-added_at']
        verbose_name = "Crew Project Add"
        verbose_name_plural = "Crew Project Adds"

    def __str__(self):
        return f"{self.crew.name} → {self.project.name}"
```

Do NOT touch `class Invitation` (`planner/models.py:3809`) or any existing model. SPEC R5 mandates strict additivity.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && python manage.py check planner 2>&1 | tee /tmp/check.out && test "$(grep -c 'class Crew(models.Model)' planner/models.py)" -eq 1 && test "$(grep -c 'class CrewMember(models.Model)' planner/models.py)" -eq 1 && test "$(grep -c 'class CrewProjectAdd(models.Model)' planner/models.py)" -eq 1 && grep -q "condition=Q(user__isnull=False, email__isnull=True)" planner/models.py && grep -q "name='crewmember_user_xor_email'" planner/models.py && grep -q "name='uniq_crewmember_crew_user'" planner/models.py && grep -q "name='uniq_crewmember_crew_email'" planner/models.py && test "$(git diff -- planner/models.py | grep -cE '^[+-].*class Invitation\\b')" -eq 0</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "class Crew(models.Model)" planner/models.py` outputs `1`
    - `grep -c "class CrewMember(models.Model)" planner/models.py` outputs `1`
    - `grep -c "class CrewProjectAdd(models.Model)" planner/models.py` outputs `1`
    - `grep -q "from django.db.models import.*CheckConstraint" planner/models.py` exits 0 (import added)
    - `grep -q "condition=Q(user__isnull=False, email__isnull=True)" planner/models.py` exits 0 (D-15 XOR constraint)
    - `grep -q "name='crewmember_user_xor_email'" planner/models.py` exits 0
    - `grep -q "name='uniq_crewmember_crew_user'" planner/models.py` exits 0
    - `grep -q "name='uniq_crewmember_crew_email'" planner/models.py` exits 0
    - `grep -q "related_name='owned_crews'" planner/models.py` exits 0
    - `grep -q "related_name='crew_memberships'" planner/models.py` exits 0
    - `grep -q "related_name='project_adds'" planner/models.py` exits 0
    - `grep -q "related_name='crew_adds'" planner/models.py` exits 0
    - `git diff -- planner/models.py | grep -cE "^[+-].*class Invitation\\b"` outputs `0` (SPEC R5 — Invitation untouched)
    - `python manage.py check planner` exits 0 with no errors
  </acceptance_criteria>
  <done>
Three new model classes (`Crew`, `CrewMember`, `CrewProjectAdd`) exist in `planner/models.py`, use `settings.AUTH_USER_MODEL` per Pitfall 4, use Django 5.2 `condition=` syntax per D-15, and `Invitation` is byte-identical to pre-phase state.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Generate migration 0157 + apply locally to SQLite</name>
  <files>planner/migrations/0157_crew_crewmember_crewprojectadd.py</files>
  <read_first>
    - `planner/migrations/0156_remove_device_parent_console.py` (confirms the dependency chain)
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` §"Runtime State Inventory" (additive migration; metadata-only on Postgres)
    - `CLAUDE.md` §"When in Doubt" — additive migrations on Phase 6 do NOT require Railway confirmation; local migrate IS required (MEMORY.md)
  </read_first>
  <action>
Run `python manage.py makemigrations planner --name crew_crewmember_crewprojectadd` from the repo root. Django will auto-generate `planner/migrations/0157_crew_crewmember_crewprojectadd.py` with three `CreateModel` operations and a single `dependencies = [('planner', '0156_remove_device_parent_console')]` line. No hand-edit of the generated file should be needed — if Django emits an unexpected operation (e.g. a duplicate `AddConstraint` for the implicit `unique_together`), inspect and confirm before proceeding.

Then apply locally to SQLite per MEMORY.md (`feedback_local_migrate_after_makemigrations.md`):

```bash
python manage.py migrate planner
```

This must succeed against local SQLite (which supports partial unique indexes and check constraints per `django/db/backends/base/features.py`).

Do NOT run `railway run python manage.py migrate` — Railway's `startCommand` runs `migrate` automatically on next deploy per CLAUDE.md, and the migration is purely additive (new tables, no ALTER on existing tables) so no manual Railway action is needed.

Per CLAUDE.md "Ask before destructive ops": this migration is non-destructive (additive only), so no confirmation step required.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && test -f planner/migrations/0157_crew_crewmember_crewprojectadd.py && grep -q "CreateModel" planner/migrations/0157_crew_crewmember_crewprojectadd.py && grep -q "name='Crew'" planner/migrations/0157_crew_crewmember_crewprojectadd.py && grep -q "name='CrewMember'" planner/migrations/0157_crew_crewmember_crewprojectadd.py && grep -q "name='CrewProjectAdd'" planner/migrations/0157_crew_crewmember_crewprojectadd.py && grep -q "0156_remove_device_parent_console" planner/migrations/0157_crew_crewmember_crewprojectadd.py && python manage.py makemigrations planner --dry-run 2>&1 | grep -q "No changes detected" && python manage.py migrate planner 2>&1 | tee /tmp/migrate.out && python manage.py check 2>&1 | tee /tmp/check2.out</automated>
  </verify>
  <acceptance_criteria>
    - `test -f planner/migrations/0157_crew_crewmember_crewprojectadd.py` exits 0
    - `grep -q "CreateModel" planner/migrations/0157_crew_crewmember_crewprojectadd.py` exits 0
    - `grep -q "name='Crew'" planner/migrations/0157_crew_crewmember_crewprojectadd.py` exits 0
    - `grep -q "name='CrewMember'" planner/migrations/0157_crew_crewmember_crewprojectadd.py` exits 0
    - `grep -q "name='CrewProjectAdd'" planner/migrations/0157_crew_crewmember_crewprojectadd.py` exits 0
    - `grep -q "0156_remove_device_parent_console" planner/migrations/0157_crew_crewmember_crewprojectadd.py` exits 0 (dependency chain correct)
    - `python manage.py makemigrations planner --dry-run` outputs "No changes detected in app 'planner'" (proves migration captures full model delta)
    - `python manage.py migrate planner` exits 0 (local SQLite apply per MEMORY.md)
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
Migration 0157 file exists, captures all three new models, depends on 0156, and has been applied to local SQLite. `makemigrations --dry-run` reports no further changes.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| ORM → DB | DB-level constraints are the perimeter; any caller (admin, views, tests, shell) can attempt invalid writes |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-01-01 | Tampering | CrewMember row with both user AND email set | mitigate | DB CheckConstraint `crewmember_user_xor_email` rejects at insert (D-15) |
| T-06-01-02 | Tampering | Duplicate pending-email CrewMember rows under Postgres NULL-not-distinct | mitigate | Partial UniqueConstraint `uniq_crewmember_crew_email` with `condition=Q(email__isnull=False)` (Pitfall 1) |
| T-06-01-03 | Tampering | Duplicate (crew, user) CrewMember row attempts | mitigate | Partial UniqueConstraint `uniq_crewmember_crew_user` (D-15) |
| T-06-01-04 | Repudiation | Cannot audit which crew was added to which project | mitigate | CrewProjectAdd table with `added_at` auto_now_add timestamp (D-09) |
| T-06-01-05 | Information Disclosure | Crew owner FK cross-tenant leak | accept | `Crew.owner` is a hard FK with CASCADE; views in Plans 03/04 enforce owner-only access checks |
| T-06-01-06 | Tampering | Invitation model edits violate SPEC R5 additivity | mitigate | `git diff` acceptance criterion in Task 1 verifies zero matches on Invitation diff |
</threat_model>

<verification>
- `python manage.py check` exits 0 (no system check errors)
- `python manage.py makemigrations planner --dry-run` reports "No changes detected" (model + migration agree)
- `python manage.py migrate planner` applies 0157 successfully to local SQLite (MEMORY.md requirement)
- `git diff -- planner/models.py | grep -cE "^[+-].*class Invitation\\b"` outputs `0` (SPEC R5)
- All grep acceptance criteria in both tasks pass
</verification>

<success_criteria>
- `Crew`, `CrewMember`, and `CrewProjectAdd` tables exist in local SQLite after `migrate`
- DB-level XOR check and two partial unique constraints are enforced
- `Invitation` model is untouched (SPEC R5)
- Migration 0157 ready to deploy on next Railway push (automatic via `startCommand`)
- Plans 02–07 unblocked (admin, CRUD views, bulk-add, auto-claim, nav, tests)
</success_criteria>

<output>
After completion, create `.planning/phases/06-trusted-crew-rosters/06-01-SUMMARY.md` capturing: line numbers of inserted models, migration file path, local migrate output, grep counts for D-15 constraint names, and confirmation that Invitation diff is zero.
</output>
