# Phase 6: Trusted Crew Rosters — Research

**Researched:** 2026-05-14
**Domain:** Django 5.2 multi-tenant SaaS — collaboration model + bulk-add view + email + auto-claim hook
**Confidence:** HIGH

## Summary

Every research question for Phase 6 reduces to verifying a Django syntax shape or locating an existing file. SPEC.md is locked at 8 requirements; CONTEXT.md locks D-01 through D-08. This research:

1. Confirms the **exact Django 5.2 constraint syntax** for D-01 (CheckConstraint XOR) and D-02 (two partial UniqueConstraints).
2. Locates the **canonical top-right user-menu insertion point** for the "My Crew" link (D-04) — there are TWO surfaces that need it, not one.
3. Documents the **`send_invitation_email` shape** so the new "you've been added" email can mirror it.
4. Identifies the **canonical project-landing URL** (`/set-project/<id>/`, URL name `set_project`) for the email body.
5. Calls out **two stale facts in CONTEXT.md** — line numbers in `accounts/views.py` are off by ~11 (e.g. register is at 16, not 27; accept_invitation is at 181, not 181's claimed 207-line check), and `accounts/templates/accounts/` does NOT exist (templates actually live at project-level `templates/accounts/`). Planner must use the corrected paths from this research, not CONTEXT.md.

**Primary recommendation:** Put the new models in `planner/models.py` (not `accounts/models.py`) to match the existing `ProjectMember`/`Invitation` pattern; use `condition=` (not deprecated `check=`) on CheckConstraint per Django 5.1+ rename; use two partial `UniqueConstraint(condition=Q(field__isnull=False))` entries instead of `unique_together` so Postgres NULL-not-distinct semantics don't allow duplicate pending-email rows.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Crew + CrewMember persistence | API / Backend (Django models) | Database (Postgres prod, SQLite local) | Standard Django model, additive migration |
| Crew CRUD UI (`/accounts/crew/`) | Frontend Server (SSR via Django views + templates) | — | Custom user-facing pages per D-03, NOT admin |
| Bulk-add view (creates ProjectMember rows + emails) | API / Backend | — | Synchronous server-side per SPEC Constraint (no Celery) |
| Confirmation email | API / Backend (Resend Python SDK) | External (Resend SaaS) | Mirrors `send_invitation_email` shape |
| Auto-claim hook on register | API / Backend (inline call in `register()` view) | — | D-07 explicitly forbids Django signals |
| Top-right "My Crew" nav link | Frontend Server (template edit) | — | Two surfaces: `templates/admin/base_site.html` + `templates/accounts/dashboard.html` |
| Admin audit registration | API / Backend (`showstack_admin_site`) | — | Per CLAUDE.md convention |

## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Single `CrewMember` table with nullable user + nullable email.**
- `user` is a nullable FK to `auth.User`
- `email` is a nullable `EmailField`
- DB CHECK constraint: exactly one of `user` or `email` is non-null per row
- On auto-claim, UPDATE IN PLACE (`email=None`, `user=<new_user_fk>`) — preserves `default_role` + future audit fields
- Roster reads via `crew.crewmember_set.select_related('user').all()`

**D-02: Crew model is minimal: `owner` FK + `name` CharField + standard timestamps.**
- `CrewMember.default_role` CharField, choices editor/viewer, default `editor`
- Crew has no crew-level default role, no color/icon
- `unique_together = ('owner', 'name')` on Crew (so an owner can't have two crews with same name)
- `CrewMember` needs two uniqueness constraints: `('crew', 'user')` AND `('crew', 'email')` — researcher confirms PARTIAL UniqueConstraints required (see Pitfall 1)

**D-03: `/accounts/crew/` is the index URL — new top-level route under the accounts app.**
- `@login_required` for the routes; `request.user == project.owner` check for project-touching actions
- Templates live in `templates/accounts/` (project-level, NOT app-level — see Pitfall 5)
- NOT under Django admin
- Routes: `/accounts/crew/`, `/accounts/crew/new/`, `/accounts/crew/<crew_id>/`, `/accounts/crew/<crew_id>/members/add/`, `/accounts/crew/<crew_id>/members/<member_id>/remove/`

**D-04: Nav surface is the top-right user menu, next to logout.**
- Add "My Crew" link to whatever template renders the top-right user dropdown
- Researcher located TWO surfaces (see Question 3 below)
- NO dashboard card alongside audio modules

**D-05: Stacked layout on `/projects/<id>/invite/`. Existing email form stays at top; new panel below.**
- One card per crew with name, count, member list, "Add this crew" button
- Already-members visually greyed/struck
- Pending-email pill for placeholders
- Markup is additive (insert below `</form>` at `templates/accounts/invite_user.html:218`)

**D-06: Single-click bulk-add. No confirmation modal. Result is a confirmation banner.**
- POST → redirect → flash message `"Added {N} members from {crew_name}; {M} were already on this project."`
- Per-member email sent synchronously
- Button disabled/hidden when N would be 0

**D-07: Inline call in `register()` view body — researcher confirmed actual location is `accounts/views.py:27` (after `form.save()` returns `user`).**
- Helper `claim_pending_crew_memberships(user)` — researcher recommends `planner/crew.py` (models live in `planner.models`, helper lives next to them)
- NO Django signals

**D-08: Email match strictness — case-insensitive + whitespace strip, no provider-specific normalization.**
- `user.email.strip().lower() == pending.email.strip().lower()`
- Implemented via `__iexact` + explicit `.strip()` on user-side value
- No gmail dot-stripping, no `+alias` collapsing

### Claude's Discretion

- Confirmation email HTML/template — model after `send_invitation_email` at `accounts/views.py:241` (actual line; CONTEXT.md said 252)
- Admin registration on `showstack_admin_site` per CLAUDE.md
- Exact button labels, microcopy, CSS
- Bulk-add URL shape (suggested: `POST /projects/<id>/invite/add-crew/<crew_id>/`)
- Test fixture shape — mirror `planner/tests/test_channel_record_defaults.py` style (`accounts/tests.py` is an empty stub today)

### Deferred Ideas (OUT OF SCOPE)

- Per-project role override at bulk-add time
- Bulk REMOVE crew from project
- Multi-select "add multiple crews at once"
- Cascade options on crew remove (explicit no-cascade design)
- Cross-owner crew sharing / team-workspace model
- In-app notifications (crew-add fires email only)
- Mobile `/m/` parity
- Crew-level audit log / activity history
- Pro Tools export

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| Req 1 | Named crew rosters per owner (CRUD `/accounts/crew/`) | Standard Django CRUD pattern; admin-ordering update; new templates in `templates/accounts/` |
| Req 2 | Per-crew member `default_role` (editor/viewer) | `CrewMember.default_role = CharField(choices=..., default='editor')` — mirrors `ProjectMember.role` shape at `planner/models.py:702` |
| Req 3 | Bulk-add crew to project — single `ProjectMember.objects.bulk_create` after `user_id`-diff query; reuse existing `invited_by` + `invited_at` |
| Req 4 | Confirmation email per new ProjectMember row | Mirror `send_invitation_email` (Resend Emails.send, inline HTML) — no `accept_url` token; use `reverse('set_project', args=[project.id])` for the landing link |
| Req 5 | Strictly additive — Invitation flow untouched | Insertion point in `templates/accounts/invite_user.html` after line 218 (after `</form>`); no edits to `Invitation` model, `accept_invitation`, `send_invitation_email` |
| Req 6 | Pre-onboarding placeholder + auto-claim on register | Helper called from `accounts/views.py:27` (after `form.save()`); `CrewMember.objects.filter(user__isnull=True, email__iexact=user.email.strip())` |
| Req 7 | No-cascade removal | `CrewMember.delete()` only — `ProjectMember` rows untouched. Verify via post-delete `ProjectMember.objects.filter(project=..., user=...).exists() == True` |
| Req 8 | Dedupe on bulk-add | `Q(project=p) & Q(user__in=crew_user_ids)` upfront query → compute `set` diff → `bulk_create` only missing rows. `ProjectMember.unique_together = ('project', 'user')` (`planner/models.py:711`) is the DB-level safety net |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Django | 5.2.4 (already pinned in `requirements.txt:4`) | Models, views, templates, ORM, migrations | Project's only web framework |
| resend | already pinned (`requirements.txt`) | Confirmation email sending | Project's existing transactional-email backend (`accounts/views.py:245`) |
| PostgreSQL (Railway prod) / SQLite (local) | — | Persistence | Both backends support `CheckConstraint` AND partial `UniqueConstraint` per `django/db/backends/{sqlite3,postgresql}/features.py` (`supports_table_check_constraints=True`, `supports_partial_indexes=True`) `[VERIFIED: source grep]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `django.contrib.messages` | bundled | Flash banner for bulk-add result | `messages.success(request, "Added 3 members; 0 were already...")` per D-06 |
| `django.db.models.Q` + `CheckConstraint` + `UniqueConstraint` | bundled | D-01 XOR check + D-02 partial uniques | See Code Examples below |
| `django.contrib.auth.decorators.login_required` | bundled | Auth-gate crew routes | Per D-03; existing pattern at `accounts/views.py:62, 72, 121` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline call in `register()` | `post_save` signal on `User` | D-07 explicitly rules signals out — too magic; harder to unit-test |
| Two `CrewMember` tables (one for users, one for pending emails) | — | D-01 explicitly mandates ONE table with nullable user + email |
| Celery for bulk email | Synchronous in-request | SPEC Constraint: crews are 1-10 members; sync is fine |
| `unique_together` for `(crew, user)` and `(crew, email)` | Partial `UniqueConstraint` with `condition=Q(...isnull=False)` | `unique_together` would let multiple rows with `user=NULL` and same email coexist on Postgres (NULL-not-distinct default) — see Pitfall 1 |

**Installation:** Zero new dependencies. All libraries already in `requirements.txt`.

**Version verification:** Django pin `5.2.4` confirmed via `grep '^Django' requirements.txt` `[VERIFIED: file read]`. Constraint API changes (the `check`→`condition` rename for `CheckConstraint`) verified against installed `venv/lib/python3.14/site-packages/django/db/models/constraints.py` lines 158-201 `[VERIFIED: source grep]`.

## Architecture Patterns

### System Architecture Diagram

```
                            BROWSER
                               │
                               │  (1) GET /accounts/crew/
                               │  (2) POST /accounts/crew/new/
                               │  (3) GET /accounts/crew/<id>/
                               │  (4) POST /accounts/crew/<id>/members/add/
                               │  (5) POST /accounts/crew/<id>/members/<m>/remove/
                               │  (6) POST /projects/<id>/invite/add-crew/<c>/  ← bulk-add
                               │  (7) POST /register/                            ← may trigger auto-claim
                               ▼
                    ┌──────────────────────────┐
                    │  accounts/urls.py        │  ← new routes added here
                    └──────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │  accounts/views.py       │  ← new views added; register() body gets 1 new line
                    │                          │
                    │  • crew_index            │
                    │  • crew_create           │
                    │  • crew_detail           │
                    │  • crew_add_member       │
                    │  • crew_remove_member    │
                    │  • bulk_add_crew         │ ──┐
                    │  • register (1-line     │   │ (sends email per new row)
                    │     append)              │   │
                    └──────────────────────────┘   │
                               │                   │
                ┌──────────────┼───────────────┐   │
                ▼              ▼               ▼   │
       ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐
       │ planner/    │ │ planner/     │ │ resend.Emails.send │
       │ models.py   │ │ crew.py      │ │ (inline HTML)      │
       │            │ │ (new module) │ │                    │
       │ • Crew     │ │              │ │ "You've been added │
       │ • CrewMember│ │ • claim_     │ │  to {project}"     │
       │ • Project   │ │   pending_   │ └────────────────────┘
       │ • ProjectMbr│ │   crew_      │
       │ • User      │ │   member-    │
       │            │ │   ships(user)│
       └─────────────┘ └──────────────┘
                │              │
                ▼              ▼
       ┌──────────────────────────┐
       │ Postgres (prod) /        │
       │ SQLite (local)           │
       │                          │
       │ • planner_crew           │  ← new table
       │ • planner_crewmember     │  ← new table (CheckConstraint + 2 partial UniqueConstraints)
       │ • planner_projectmember  │  ← bulk-add writes here (no schema change)
       │ • planner_invitation     │  ← UNTOUCHED per SPEC Req 5
       └──────────────────────────┘

                    ┌──────────────────────────────────────────────────────┐
                    │  TEMPLATES                                            │
                    │                                                       │
                    │  templates/accounts/crew_index.html       (new)       │
                    │  templates/accounts/crew_detail.html       (new)      │
                    │  templates/accounts/invite_user.html       (additive  │
                    │       — new <div class="card"> after line 218)       │
                    │  templates/admin/base_site.html            (additive  │
                    │       — "My Crew" link before {{ block.super }}      │
                    │       at line 131)                                    │
                    │  templates/accounts/dashboard.html         (additive  │
                    │       — "My Crew" link inside .header-right          │
                    │       at line 290 (before "Logout"))                 │
                    └──────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────────────────────┐
                    │  ADMIN (per CLAUDE.md)                                │
                    │                                                       │
                    │  accounts/admin.py  → register Crew + CrewMember on   │
                    │                       showstack_admin_site            │
                    │  planner/admin_ordering.py  → add 'crew': 2.5,        │
                    │                                'crewmember': 2.6      │
                    │                       under "User/Project Management" │
                    └──────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
planner/
├── models.py                                  # Crew, CrewMember append here (line ~750, before #-----Console Model----)
├── crew.py                                    # NEW — claim_pending_crew_memberships(user)
└── migrations/
    └── 0157_crew_crewmember.py                # NEW — additive migration

accounts/
├── views.py                                   # new views + 1-line append to register() at :27
├── urls.py                                    # new routes for /accounts/crew/*  and /projects/<id>/invite/add-crew/<c>/
├── admin.py                                   # CrewAdmin, CrewMemberAdmin registered on showstack_admin_site
├── invitation_forms.py                        # InviteCrewMemberForm (new) — or inline in views
└── tests.py                                   # currently empty; replace stub OR create accounts/tests/ package

templates/
├── accounts/
│   ├── crew_index.html                        # NEW — list of owner's crews
│   ├── crew_detail.html                       # NEW — single crew roster
│   ├── invite_user.html                       # MODIFIED — additive "Add your crew" panel after </form>
│   └── dashboard.html                         # MODIFIED — additive "My Crew" link in .header-right
└── admin/
    └── base_site.html                         # MODIFIED — additive "My Crew" link in userlinks block before {{ block.super }}
```

### Pattern 1: XOR check constraint (D-01)

**What:** Enforce that exactly one of two nullable fields is non-null per row.
**When to use:** Polymorphic single-table inheritance like `CrewMember.user XOR CrewMember.email`.

```python
# planner/models.py (new — Phase 6)
from django.db import models
from django.db.models import CheckConstraint, UniqueConstraint, Q
from django.conf import settings
# from django.contrib.auth.models import User  ← project uses User directly,
# not settings.AUTH_USER_MODEL — see Pitfall 4 for the recommendation

class CrewMember(models.Model):
    crew = models.ForeignKey('Crew', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
    )
    email = models.EmailField(null=True, blank=True)
    default_role = models.CharField(
        max_length=20,
        choices=[('editor', 'Editor'), ('viewer', 'Viewer')],
        default='editor',
    )
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
                name='crewmember_unique_crew_user_when_user',
            ),
            UniqueConstraint(
                fields=['crew', 'email'],
                condition=Q(email__isnull=False),
                name='crewmember_unique_crew_email_when_email',
            ),
        ]
```

**Source:** Django 5.2 docs https://docs.djangoproject.com/en/5.2/ref/models/constraints/ + verified against installed `django/db/models/constraints.py:158-201` (the `check=` kwarg is deprecated as of Django 5.1; `condition=` is canonical) `[VERIFIED: source grep]`.

### Pattern 2: `Crew` model with `unique_together` on the simple case

```python
# planner/models.py (new — Phase 6)
class Crew(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_crews',
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['owner', 'name'],
                name='crew_unique_owner_name',
            ),
        ]
        # Note: NOT using unique_together — UniqueConstraint is the recommended
        # form in Django 5.2+ (unique_together "may be deprecated in the future"
        # per docs). The existing ProjectMember/Invitation models in this codebase
        # still use unique_together — Phase 6 chooses the new style consistently
        # for both Crew and CrewMember, since CrewMember REQUIRES partial
        # UniqueConstraint (NULL handling) and mixing styles would be confusing.

    def __str__(self):
        return f"{self.name} (owned by {self.owner.username})"
```

**Source:** Django 5.2 docs explicit recommendation https://docs.djangoproject.com/en/5.2/ref/models/options/#unique-together `[CITED: docs.djangoproject.com]`.

### Pattern 3: Bulk-add view (dedupe + skip + email)

```python
# accounts/views.py (new — Phase 6)
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from planner.models import Project, ProjectMember, Crew

@login_required
def bulk_add_crew(request, project_id, crew_id):
    project = get_object_or_404(Project, id=project_id)
    if project.owner != request.user:  # mirrors accounts/views.py:129
        messages.error(request, 'Only the project owner can add a crew.')
        return redirect('dashboard')

    crew = get_object_or_404(Crew, id=crew_id, owner=request.user)

    if request.method != 'POST':
        return redirect('invite_user', project_id=project.id)

    # Resolve crew members with a user FK (pending-email rows skipped here;
    # they materialize via the auto-claim hook in register()).
    resolved = crew.crewmember_set.filter(user__isnull=False).select_related('user')

    # Single upfront query: who's already a member? (SPEC Req 8 dedupe)
    existing_user_ids = set(
        ProjectMember.objects.filter(
            project=project,
            user_id__in=[m.user_id for m in resolved],
        ).values_list('user_id', flat=True)
    )

    to_add = [m for m in resolved if m.user_id not in existing_user_ids]
    already = len(resolved) - len(to_add)

    new_rows = [
        ProjectMember(
            project=project,
            user=m.user,
            role=m.default_role,
            invited_by=request.user,
            # invited_at = auto_now_add fires on .save(); bulk_create does NOT
            # trigger auto_now_add — see Pitfall 2 — use .save() in a loop OR
            # set invited_at=timezone.now() explicitly in the ProjectMember(...)
            # call above (CONFIRM SHAPE WITH PLANNER).
        )
        for m in to_add
    ]
    # Decision point for planner: bulk_create vs .save() in loop —
    # auto_now_add quirk forces the choice (see Pitfall 2).

    for row in new_rows:
        row.save()  # individual saves so invited_at populates via auto_now_add
        send_crew_added_email(row, request)  # new helper (see Pattern 4)

    messages.success(
        request,
        f"Added {len(to_add)} members from {crew.name}; "
        f"{already} were already on this project."
    )
    return redirect('invite_user', project_id=project.id)
```

### Pattern 4: Confirmation email (mirror `send_invitation_email`)

```python
# accounts/views.py (new — Phase 6)
def send_crew_added_email(project_member, request):
    """
    Mirrors accounts/views.py:241 send_invitation_email shape but with
    NO accept_url token — recipient is already a member.
    """
    import resend
    import os
    from django.urls import reverse

    project_url = request.build_absolute_uri(
        reverse('set_project', args=[project_member.project.id])
    )
    # set_project sets request.session['current_project_id'] then redirects
    # to /admin/ — that's the canonical "land inside the project" entry
    # point used elsewhere in the codebase (templates/accounts/dashboard.html:382).

    owner = project_member.project.owner
    subject = (
        f"{owner.get_full_name() or owner.username} added you to "
        f"{project_member.project.name} on ShowStack"
    )
    html = f"""
<h2>You've been added to a ShowStack project!</h2>
<p><strong>{owner.get_full_name() or owner.username}</strong> added you to
their crew on ShowStack:</p>
<ul>
    <li><strong>Project:</strong> {project_member.project.name}</li>
    <li><strong>Your role:</strong> {project_member.get_role_display()}</li>
</ul>
<p><a href="{project_url}" style="display:inline-block;padding:12px 24px;background:#4a9eff;color:white;text-decoration:none;border-radius:6px;margin:20px 0;">
Open project</a></p>
<p><small>No action required — your access is already active.</small></p>
<hr>
<p><small>ShowStack — Professional Audio Production Management</small></p>
"""
    resend.api_key = os.environ.get('RESEND_API_KEY')
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [project_member.user.email],
            "subject": subject,
            "html": html,
        })
    except Exception as e:
        # Mirrors send_invitation_email pattern (lines 287-290)
        print(f"❌ Error sending crew-add email to {project_member.user.email}: {e}")
        # Decision for planner: re-raise or swallow? send_invitation_email
        # re-raises; the bulk-add view catches at the top level OR not.
        # Recommend: log + swallow (one bad email shouldn't undo a successful
        # crew-add — defensive in-prod, easier to debug per-recipient via Resend
        # dashboard).
```

### Pattern 5: Auto-claim hook (D-07)

```python
# planner/crew.py (new module — Phase 6)
"""
Auto-claim helper: when a new user registers, link any pending CrewMember
rows whose email matches their account.

Called from accounts/views.py:27 (after form.save() in register()).
"""
from django.db import transaction
from planner.models import CrewMember, ProjectMember


def claim_pending_crew_memberships(user):
    """
    For every CrewMember row with user__isnull=True and email matching
    user.email (case-insensitive, whitespace-stripped per D-08):
      1. UPDATE IN PLACE: email=None, user=user.
      2. For every project the crew has been bulk-added to (i.e. every
         project that has a ProjectMember row created via that crew —
         which we approximate by 'every ProjectMember row whose user is
         another member of the same crew' — see open question), create a
         ProjectMember row for `user` with role=default_role.

    Returns: list of newly-created ProjectMember rows (so the caller can
    send confirmation emails per Req 4).
    """
    normalized = user.email.strip()  # __iexact handles the lowercase

    pending = CrewMember.objects.filter(
        user__isnull=True,
        email__iexact=normalized,
    ).select_related('crew')

    new_memberships = []

    with transaction.atomic():
        for cm in pending:
            # Step 1: rebind to new user (preserve default_role)
            cm.user = user
            cm.email = None
            cm.save(update_fields=['user', 'email'])

            # Step 2: materialize ProjectMember rows for every project
            # this crew has been bulk-added to. Open question: how do we
            # KNOW which projects the crew was added to?
            # See Open Questions §1 — needs a Decision.
            for project_id in _projects_crew_was_added_to(cm.crew):
                pm, created = ProjectMember.objects.get_or_create(
                    project_id=project_id,
                    user=user,
                    defaults={
                        'role': cm.default_role,
                        'invited_by': cm.crew.owner,
                    },
                )
                if created:
                    new_memberships.append(pm)

    return new_memberships


def _projects_crew_was_added_to(crew):
    """
    OPEN QUESTION — see Open Questions §1.

    Two viable options:
      A) Add a Crew.added_to_projects M2M field on Crew (or a new
         CrewProjectLink table) populated by the bulk-add view.
      B) Infer from existing ProjectMember rows: 'every project where ANY
         crew_member of `crew` is already a ProjectMember'.

    Option A is explicit/auditable; B is zero new schema but has a corner
    case (if the LAST other crew member leaves a project, the link is
    lost). Recommend A.
    """
    raise NotImplementedError("Planner: pick A vs B per Open Questions §1")
```

### Anti-Patterns to Avoid

- **`unique_together` for nullable composite uniqueness:** breaks under Postgres' default NULL-not-distinct semantics — multiple pending rows for the same email would coexist. Use partial `UniqueConstraint(condition=...)` instead.
- **Using `check=` kwarg on `CheckConstraint`:** deprecated in Django 5.1 (`RemovedInDjango60Warning`); use `condition=`.
- **`post_save` signal for auto-claim:** D-07 explicitly rules signals out. Inline call in `register()` is the documented, testable insertion point.
- **`bulk_create` for `ProjectMember` rows:** `invited_at` uses `auto_now_add=True` which does NOT fire on `bulk_create` — see Pitfall 2.
- **Trying to put new models in `accounts/models.py`:** the file is an empty stub (no migrations at all). The whole codebase's User/Project/Invitation/ProjectMember pattern keeps models in `planner/models.py`. Stay consistent.
- **Forgetting to update `planner/admin_ordering.py`:** CLAUDE.md mandates it, and the sidebar grouping breaks silently if you skip it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XOR field enforcement | Custom `clean()` method on `CrewMember` (form-layer only) | DB `CheckConstraint(condition=Q(...) | Q(...))` | Form-layer can be bypassed by direct ORM `.create()` calls (incl. admin, bulk imports, test fixtures). DB constraint is the perimeter. |
| Partial uniqueness for nullable composite key | `unique_together` + custom `clean()` | `UniqueConstraint(fields=..., condition=Q(...isnull=False))` | Same reason — DB constraint is the truth. |
| Confirmation-email template engine | New Django `loaders` config, separate `.html` template file | Inline f-string HTML, mirror `send_invitation_email` at `accounts/views.py:241` | Existing codebase convention; no template engine swap needed for one-off email |
| "Pre-onboarding state machine" abstraction | A new `PendingMember` model + signals + state-machine library | Single nullable FK on existing `CrewMember` (D-01) + inline call in `register()` | D-01 decision is already locked; over-engineering rejected at discuss-phase |
| Case-insensitive email matching | Custom string comparison | Django `__iexact` lookup + explicit `.strip()` on user-side value | Mirrors `accept_invitation`'s case-insensitive pattern (existing project convention) |
| Bulk-add validation for already-members | Multiple per-row `.exists()` queries | Single `Q(project=p) & Q(user_id__in=set)` upfront query, compute diff in Python | Order N queries → Order 1 query; SPEC Req 8 dedupe pattern |

**Key insight:** The codebase already has all the patterns Phase 6 needs — owner-check, message framework, Resend send, `__iexact` lookups, `unique_together` (existing-row safety net). The new pieces (partial UniqueConstraint, XOR CheckConstraint) ARE the modern Django way and don't require any new libraries.

## Runtime State Inventory

Phase 6 is mostly greenfield (new models + new views) — not a rename/refactor. But two runtime concerns deserve naming:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | New `planner_crew` and `planner_crewmember` Postgres tables on Railway after migration 0157 deploys. No DATA to backfill (zero rows exist pre-phase). | None — additive only |
| Live service config | None — Phase 6 introduces no new external services. Resend already wired. | None — verified by reading `accounts/views.py:241-290` and `requirements.txt` |
| OS-registered state | None — no Task Scheduler, no pm2, no launchd, no systemd touched. | None |
| Secrets/env vars | None added. Existing `RESEND_API_KEY` env var reused. | None — verified by reading `accounts/views.py:277` |
| Build artifacts | None — Phase 6 is pure Python source + migration. No `egg-info`, no compiled artifact rename. | None |

**Migration rollout note:** Per CLAUDE.md, Railway runs `migrate` on every deploy via `railway.json` `startCommand`. Migration 0157 (new tables) is metadata-only and will apply sub-second on prod. No `python manage.py migrate` against Railway needed manually. **Local SQLite migrate** is required before marking the phase complete (per MEMORY.md user preference: "apply new migrations to local SQLite before marking the plan complete").

## Common Pitfalls

### Pitfall 1: `unique_together` on a nullable column allows duplicate "pending" rows under Postgres default NULL semantics

**What goes wrong:** Writing `unique_together = [('crew', 'user'), ('crew', 'email')]` looks correct but in Postgres, the unique index on `(crew_id, email)` treats two rows where `email='alice@example.com'` and another row where `email='alice@example.com'` BUT with different `user_id` values as already non-duplicate (different user_id breaks the composite uniqueness). Worse: when `user_id IS NULL`, two `(crew=1, email='alice@example.com', user=NULL)` rows are considered DISTINCT by Postgres' default `NULL != NULL` semantics — so you can have duplicate pending invites for the same email on the same crew.

**Why it happens:** Postgres docs: *"By default, null values in a unique column are not considered equal, allowing multiple nulls in the column."* `[CITED: postgresql.org/docs/current/indexes-unique.html]`

**How to avoid:** Use TWO partial `UniqueConstraint`s, each filtered to its own non-null side:

```python
class Meta:
    constraints = [
        UniqueConstraint(
            fields=['crew', 'user'],
            condition=Q(user__isnull=False),
            name='crewmember_unique_crew_user_when_user',
        ),
        UniqueConstraint(
            fields=['crew', 'email'],
            condition=Q(email__isnull=False),
            name='crewmember_unique_crew_email_when_email',
        ),
    ]
```

**Warning signs:** Tests pass on SQLite (which has the same default behavior for safety) but engineer can manually add the same `(crew=1, email='alice@example.com', user=NULL)` row twice via admin or shell. Verify with: `CrewMember.objects.filter(crew=c, email='alice@example.com', user__isnull=True).count() <= 1` after duplicate insert attempt.

### Pitfall 2: `bulk_create` does NOT fire `auto_now_add` for `invited_at`

**What goes wrong:** Writing `ProjectMember.objects.bulk_create([ProjectMember(project=p, user=u, role='editor', invited_by=owner) for u in new_users])` leaves `invited_at = NULL` (or DB default) on the new rows because `auto_now_add` is a Python-side hook that fires in `Model.save()`, not in bulk insert.

**Why it happens:** Django ORM behavior — `auto_now` and `auto_now_add` are model-field hooks, not DB DEFAULTs. `bulk_create` bypasses `Model.save()`.

**How to avoid:** Either:
1. Use `.save()` in a loop (acceptable for crews of 1-10 members per SPEC Constraint — keeps `auto_now_add` firing and keeps the email-send-per-row inline in the same loop).
2. Pre-populate `invited_at = timezone.now()` explicitly when constructing each `ProjectMember()` and then use `bulk_create`.

**Recommendation:** Option 1 (loop with `.save()`) — pairs naturally with per-row email send.

**Warning signs:** `pm.invited_at is None` immediately after bulk-add, or `ProjectMember.objects.filter(invited_at__isnull=True).exists() == True` post-phase. Add `assertIsNotNone(pm.invited_at)` to the test.

### Pitfall 3: Auto-claim hook fires BEFORE the `UserProfile` exists

**What goes wrong:** `register()` at `accounts/views.py:27` is `user = form.save()` — but `RegistrationForm.save()` (`accounts/forms.py:65-81`) is `user = super().save()` THEN `UserProfile.objects.get_or_create(user=user, ...)`. So the `user.userprofile` lookup is valid by the time `claim_pending_crew_memberships(user)` runs after the form save returns.

However, **`form.save()` happens inside Django's atomic block ONLY when wrapped explicitly**. The auto-claim helper opens its own `transaction.atomic()` (Pattern 5) which is fine, but planner must ensure the helper runs BEFORE `messages.success(...)` and the redirect — otherwise if claim_pending fails, the user account is created but stuck without their crew rows. Test scenario: throw an exception inside `claim_pending_crew_memberships` and verify the user-creation rolls back OR (acceptable alternative) the user is created and a friendly error is shown so they can try again.

**Recommendation:** Wrap `form.save()` AND `claim_pending_crew_memberships(user)` in a single `transaction.atomic()` block in `register()`. Then any failure rolls back the whole operation.

**Warning signs:** Test "registration succeeds, claim raises" → user exists in DB but crew rows still pending. That's the bug — the test asserts atomic rollback.

### Pitfall 4: Hardcoding `from django.contrib.auth.models import User` vs `settings.AUTH_USER_MODEL`

**What goes wrong:** The codebase mixes both styles — `ProjectMember.user = ForeignKey(User, ...)` (`planner/models.py:695`) and `ProjectAccessRequest.requester = ForeignKey(settings.AUTH_USER_MODEL, ...)` (`planner/models.py:728`). For Phase 6, Django docs recommend `settings.AUTH_USER_MODEL` for new code so the app is portable to a custom User model later.

**Why it happens:** Project uses default `auth.User`, hasn't customized AUTH_USER_MODEL, so both styles work today.

**How to avoid:** Use `settings.AUTH_USER_MODEL` in `Crew.owner` and `CrewMember.user` for new Phase 6 models. Pattern matches the more recent `ProjectAccessRequest`.

**Warning signs:** None today. Future regression if Charlie ever introduces a custom User model.

### Pitfall 5: CONTEXT.md template paths and line numbers are stale

**What goes wrong:** CONTEXT.md says `accounts/templates/accounts/register.html` (D-03) and references line numbers that are off — e.g. `register()` is at `accounts/views.py:16` not `:27`; `send_invitation_email` is at `:241` not `:252`; `accept_invitation` is at `:181` (correct) but its case-insensitive lookup is at `:207` (correct line, but the project iexact pattern is also at `:91` in `dashboard`). Templates actually live at the PROJECT-level `templates/accounts/` (in `TEMPLATES['DIRS']`), NOT `accounts/templates/accounts/`.

**How to avoid:** Use the file paths from THIS research, not from CONTEXT.md, when writing tasks. Specifically:
- Template directory: `templates/accounts/` (project-level)
- `register()`: `accounts/views.py:16` (the line after the `register` def)
- `accept_invitation`: `accounts/views.py:181` (correct in CONTEXT)
- `send_invitation_email`: `accounts/views.py:241` (CONTEXT said 252 — off by 11)
- Project-owner gate pattern: `accounts/views.py:129` (correct in CONTEXT)

**Warning signs:** Planner writes "edit `accounts/templates/accounts/invite_user.html`" and the task fails because the file doesn't exist there.

### Pitfall 6: Forgetting to update `planner/admin_ordering.py`

**What goes wrong:** CLAUDE.md explicitly says: *"Update `admin_ordering.py` whenever a new admin-registered model is added, otherwise the sidebar grouping will be wrong."* Phase 6 registers two new models (`Crew`, `CrewMember`) on `showstack_admin_site` per CLAUDE.md convention.

**How to avoid:** Add entries to `order_map` in `planner/admin_ordering.py` under the existing "User/Project Management" grouping. Recommended slots:
```python
'crew': 2.5,
'crewmember': 2.6,
```
(between `projectmember=2` and `invitation=3`).

**Warning signs:** New Crew + CrewMember rows appear at the BOTTOM of the admin sidebar (default `999` order from `order_map.get(..., 999)`).

### Pitfall 7: Email-already-exists race on auto-claim

**What goes wrong:** Auto-claim runs `CrewMember.objects.filter(user__isnull=True, email__iexact=user.email.strip())` then for each match does `cm.user = user; cm.save()`. If TWO concurrent registrations with the same email somehow happen, the second `cm.save()` could violate the partial `UniqueConstraint('crew', 'user', condition=Q(user__isnull=False))` if the first already updated the row.

**Why it happens:** `RegistrationForm.clean_email` (`accounts/forms.py:58-63`) already prevents duplicate User emails — so the race is theoretical. But the partial-uniqueness constraint adds an extra safety net.

**How to avoid:** `transaction.atomic()` around the claim (Pattern 5 already shows this). Plus `RegistrationForm`'s existing `clean_email` makes this a defense-in-depth concern only.

**Warning signs:** `IntegrityError` traceback mentioning `crewmember_unique_crew_user_when_user` in prod logs.

### Pitfall 8: Email send failures should NOT undo a successful crew-add

**What goes wrong:** `send_invitation_email` at `accounts/views.py:289` does `raise` — the email error propagates back to the view. For bulk-add, if email #2 of 3 fails, the user sees a 500 error after rows #1 and #2 of `ProjectMember` are already created, leaving inconsistent state.

**How to avoid:** In `send_crew_added_email`, log + swallow (do NOT re-raise). The Resend dashboard surfaces delivery failures per recipient anyway. Bulk-add's correctness contract is "ProjectMember rows created" — email delivery is best-effort.

**Warning signs:** Test "Resend API returns 500 on second email" → view returns 200, flash message reads "Added 3 members" but engineer needs to manually re-send the failed email. Acceptable per SPEC Constraint (informational email only).

## Code Examples

Verified patterns from official sources:

### Example 1: Two partial UniqueConstraints + XOR CheckConstraint on the same model

```python
# Source: https://docs.djangoproject.com/en/5.2/ref/models/constraints/
from django.db import models
from django.db.models import CheckConstraint, UniqueConstraint, Q

class CrewMember(models.Model):
    crew = models.ForeignKey('Crew', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
    )
    email = models.EmailField(null=True, blank=True)
    default_role = models.CharField(
        max_length=20,
        choices=[('editor', 'Editor'), ('viewer', 'Viewer')],
        default='editor',
    )
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
                name='crewmember_unique_crew_user_when_user',
            ),
            UniqueConstraint(
                fields=['crew', 'email'],
                condition=Q(email__isnull=False),
                name='crewmember_unique_crew_email_when_email',
            ),
        ]
```

### Example 2: Inserting the "My Crew" link into the existing admin user-menu (D-04)

```html
<!-- templates/admin/base_site.html — additive insert at line ~130
     (immediately before `{{ block.super }}` at line 131) -->

    <!-- existing custom badges + project switcher + help button render above -->

    {% if user.is_authenticated %}
    <a href="{% url 'crew_index' %}"
       style="color:#fff;text-decoration:none;margin-right:15px;font-size:13px;border:1px solid #444;border-radius:4px;padding:5px 12px;"
       onmouseover="this.style.color='#00ff88';this.style.borderColor='#00ff88'"
       onmouseout="this.style.color='#fff';this.style.borderColor='#444'">
       My Crew
    </a>
    {% endif %}

    {{ block.super }}  {# renders Django default: View site / Documentation / Change password / Log out / theme toggle #}
{% endblock %}
```

### Example 3: Inserting the "My Crew" link into the dashboard header (D-04, second surface)

```html
<!-- templates/accounts/dashboard.html — additive insert at line ~290
     (inside .header-right div, BEFORE the existing .btn-logout) -->

<div class="header-right">
    <div class="user-info">
        <strong>{{ user.get_full_name|default:user.username }}</strong>
        <span class="account-badge badge-{{ account_type }}">{{ account_type }} Account</span>
    </div>
    {% if user.is_superuser or account_type == 'paid' or account_type == 'beta' %}
    <a href="/admin/" class="btn-admin">Planner</a>
    {% endif %}
    <!-- NEW: My Crew link before Logout -->
    <a href="{% url 'crew_index' %}" class="btn-admin">My Crew</a>
    <a href="{% url 'logout' %}" class="btn-logout">Logout</a>
</div>
```

### Example 4: "Add your crew" panel — additive insert in invite_user.html

```html
<!-- templates/accounts/invite_user.html — additive insert AFTER `</form>` at line 218
     (still inside `<div class="container">`) -->

            </form>
        </div>  <!-- end of existing email-invite card -->

        {% if owner_crews %}
        <!-- NEW: Add your crew panel -->
        {% for crew in owner_crews %}
        <div class="card" style="margin-top: 20px;">
            <h3>{{ crew.name }} ({{ crew.eligible_count }} eligible to add)</h3>
            <p>
                {% for cm in crew.member_display %}
                    {% if cm.is_already_member %}
                        <span style="color:#888;text-decoration:line-through">{{ cm.label }}</span>
                    {% elif cm.is_pending %}
                        <span>{{ cm.label }} <span style="background:#f39c12;color:white;font-size:11px;padding:2px 6px;border-radius:3px;">pending signup</span></span>
                    {% else %}
                        <span>{{ cm.label }}</span>
                    {% endif %}{% if not forloop.last %}, {% endif %}
                {% endfor %}
            </p>
            <form method="post" action="{% url 'bulk_add_crew' project.id crew.id %}">
                {% csrf_token %}
                <button type="submit" class="btn-primary"
                        {% if crew.eligible_count == 0 %}disabled{% endif %}>
                    Add this crew
                </button>
            </form>
        </div>
        {% endfor %}
        {% endif %}
    </div>  <!-- end of container -->
</body>
```

### Example 5: setUpTestData pattern from existing test_channel_record_defaults.py

```python
# planner/tests/test_crew_rosters.py — NEW Phase 6 test file
# Source: mirrors planner/tests/test_channel_record_defaults.py

import json
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from planner.models import Project, ProjectMember, Crew, CrewMember

User = get_user_model()

class CrewRosterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='charlie', email='charlie@example.com',
            password='test-pw-123', is_staff=True,
        )
        cls.mike = User.objects.create_user(
            username='mike', email='mike@example.com', password='pw',
        )
        cls.sarah = User.objects.create_user(
            username='sarah', email='sarah@example.com', password='pw',
        )
        cls.project = Project.objects.create(name='Test Show', owner=cls.owner)
        cls.crew = Crew.objects.create(owner=cls.owner, name='Concert team')
        CrewMember.objects.create(crew=cls.crew, user=cls.mike, default_role='editor')
        CrewMember.objects.create(crew=cls.crew, user=cls.sarah, default_role='editor')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.owner)

    def test_bulk_add_creates_project_member_rows(self):
        url = reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        response = self.client.post(url)
        # ...
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(),
            2,
        )

    def test_xor_check_constraint_blocks_user_and_email_both_set(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            CrewMember.objects.create(
                crew=self.crew, user=self.mike, email='mike@example.com',
            )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `CheckConstraint(check=Q(...))` | `CheckConstraint(condition=Q(...))` | Django 5.1 (Sept 2024) | Old kwarg deprecated; emits `RemovedInDjango60Warning`. Phase 6 MUST use `condition=` for new code. |
| `unique_together` | `UniqueConstraint(fields=[...], condition=Q(...))` | Recommended since Django 4.x; explicit in 5.2 docs | `unique_together` "may be deprecated in the future." `UniqueConstraint` also supports `condition`, `deferrable`, `include`, `expressions`. |
| Form-layer-only validation for nullable XOR fields | DB-level `CheckConstraint` | Standard Django pattern since 2.2 | DB constraint is the perimeter; form-layer is convenience. |

**Deprecated/outdated:**
- The `check=` kwarg on `CheckConstraint` — emits deprecation warning in Django 5.1+; removal scheduled for Django 6.0.
- `unique_together` — soft-deprecated in favor of `UniqueConstraint` per official docs.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Both `templates/admin/base_site.html` AND `templates/accounts/dashboard.html` need the "My Crew" link for D-04 to be "consistently reachable from the top-right user menu". CONTEXT.md said "the template that renders the top-right user dropdown" (singular). | Question 3 / Code Examples 2-3 | If Charlie only wants ONE surface, planner adds one and skips the other. If both — confirmed two artifacts. Low risk: additive markup, easy to remove. |
| A2 | The auto-claim helper module should live at `planner/crew.py` because the models live in `planner/models.py`. CONTEXT.md says "researcher: likely `planner/crew.py` or `accounts/crew_claim.py` — pick based on which app owns Crew/CrewMember." | D-07 recommendation | If models go to `accounts/models.py` instead, helper moves to `accounts/`. Confirmable by reading the existing pattern: `ProjectMember`/`Invitation` are in `planner/models.py` despite views being in `accounts/`. |
| A3 | The "direct link into the project" in the bulk-add confirmation email should use `reverse('set_project', args=[project.id])` — the canonical "land inside this project" URL used in `templates/accounts/dashboard.html:382`. | Pattern 4 (email body) | Alternative: `/admin/` directly (less specific). `/audiopatch/` (sets no project). `set_project` is the cleanest URL builder. Low risk — easy to swap. |
| A4 | The bulk-add view should use individual `.save()` calls (not `bulk_create`) so `invited_at = auto_now_add` fires correctly. | Pattern 3 + Pitfall 2 | If planner picks `bulk_create` and forgets to set `invited_at` explicitly, the rows have NULL/DB-default timestamps and SPEC acceptance criterion "invited_at≈now()" fails. |
| A5 | `_projects_crew_was_added_to(crew)` needs a NEW link table (or M2M) populated by the bulk-add view to track which projects each crew has been added to. CONTEXT.md / SPEC Req 6 references this concept ("every project the crew has already been bulk-added to") but does not specify the data shape. | Pattern 5 + Open Questions §1 | If we infer instead from "any crew member is a ProjectMember of that project", the corner case is: a crew of 3 is bulk-added to Project X; later all 3 leave Project X; a 4th member then registers — they should NOT auto-materialize on Project X (no other crew members there). Inferred approach would correctly skip. Explicit-link approach would also correctly skip if the bulk-add link is "remembered" but the membership is gone. PLANNER MUST PICK. |
| A6 | Email-send failure in bulk-add should log + swallow (not re-raise), unlike `send_invitation_email` which re-raises. | Pitfall 8 | If we re-raise, a single Resend hiccup leaves the bulk-add half-applied. If we swallow, engineers who never get the email don't know — but they have access (the contract is rows-created, not email-delivered). Mid-risk; needs explicit decision. |

## Open Questions

1. **How does the auto-claim hook know which projects to materialize ProjectMember rows for?**
   - What we know: SPEC Req 6 says "every project the crew has been bulk-added to since they joined."
   - What's unclear: Is there a link table (`CrewProjectAdd` or M2M `Crew.added_to_projects`) tracking this, or do we infer from existing `ProjectMember` rows?
   - Recommendation: Option A — add an explicit `CrewProjectAdd` table (3-field: `crew`, `project`, `added_at`) populated by the bulk-add view. Makes the auto-claim deterministic and auditable. Option B (inference from ProjectMember rows) has a corner case where the crew's "claim history" is lost if other members leave the project. Decision needed before Plan-time.

2. **Should email-send failure during bulk-add abort the whole operation (re-raise) or log + continue (swallow)?**
   - What we know: `send_invitation_email` re-raises. Bulk-add could create 2 of 3 ProjectMember rows then 500 if email #3 fails.
   - What's unclear: Charlie's preference.
   - Recommendation: Log + swallow. The contract is "ProjectMember rows exist" — Resend dashboard surfaces per-recipient failures and bulk-add is best-effort on the email side. (Aligns with Pitfall 8.)

3. **Should `register()` wrap `form.save()` + `claim_pending_crew_memberships(user)` in a single `transaction.atomic()`?**
   - What we know: Atomic would let us roll the whole thing back if claim raises.
   - What's unclear: Whether Charlie prefers "user account is created even if claim fails" (so they can re-try claim later) or "all-or-nothing".
   - Recommendation: Wrap both in `transaction.atomic()`. User-account-without-crew is a confusing half-state; rollback is safer.

4. **Should the "My Crew" link in the admin user-menu be conditional on the user owning at least one crew, or always visible?**
   - What we know: Owners always have access to create their first crew via `/accounts/crew/`. Non-owners (editors, viewers) technically have no use for the crew UI today.
   - What's unclear: Whether the link should hide for editor/viewer accounts.
   - Recommendation: Always visible for logged-in users (the `/accounts/crew/` index page can show an empty state and explain crew ownership requires a project — same pattern as dashboard's "free account" gating).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Django | All views/models | ✓ | 5.2.4 (requirements.txt:4) | — |
| Resend Python SDK | Email send (Pattern 4) | ✓ | already in requirements.txt | — |
| `RESEND_API_KEY` env var | Resend.api_key auth | ✓ (Railway prod), ✓ (local `.env`) | — | None — bulk-add silently fails to send emails in dev if missing (matches existing `send_invitation_email` behavior) |
| PostgreSQL on Railway | Prod DB | ✓ | 15+ (Railway default, supports partial unique indexes natively) | SQLite local also supports partial indexes per `django/db/backends/base/features.py` |
| SQLite | Local dev DB | ✓ | 3.x (Python 3.14 stdlib) | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — fully self-contained.

## Project Constraints (from CLAUDE.md)

The following CLAUDE.md directives MUST be honored by all Phase 6 plans:

1. **Always register models on `showstack_admin_site`, NOT `admin.site`.** Phase 6 registers `Crew` and `CrewMember` via `showstack_admin_site.register(Crew, CrewAdmin)` in `accounts/admin.py` (or a new file).
2. **Update `admin_ordering.py` whenever a new admin-registered model is added.** Phase 6 adds entries `'crew': 2.5` and `'crewmember': 2.6` to `order_map` in `planner/admin_ordering.py`.
3. **Email is via Resend; secrets in `.env` (gitignored).** Phase 6 reuses `RESEND_API_KEY` env var and `resend.Emails.send` pattern — no new email-template engine, no Celery.
4. **Never commit `.env`, Resend API keys, Railway tokens.** Standard.
5. **Solo dev typically goes straight to main; use feature branches only when work spans multiple sessions.** Plans can commit directly to `main` per usual; phase-branching not required.
6. **Local migrate after makemigrations** (MEMORY.md): apply new migration 0157 to local SQLite before marking the plan complete.
7. **Railway uses `railway.json`'s `startCommand`, NOT the `Procfile`.** Migration 0157 runs automatically on next Railway deploy via the `migrate` step in startCommand. No manual `railway run python manage.py migrate` needed.
8. **Ask before running destructive operations against Railway Postgres.** Phase 6 migration is purely additive (new tables, no ALTER on existing), so no confirmation needed — but planner should NOT include any RawSQL or data backfill steps without flagging them.

## Pattern-Map Risk Signal

Per the brief's question 10 — which new files have NO obvious analog in the codebase? **All Phase 6 files have a clean analog** except one ambiguity:

| New file | Analog | Risk |
|----------|--------|------|
| `planner/models.py` Crew + CrewMember additions | `ProjectMember` at line 692, `Invitation` at line 3809 | LOW — established model-shape pattern |
| `planner/crew.py` (auto-claim helper) | `planner/utils/reaper_export.py`, `planner/utils/yamaha_export.py` | LOW — pure-function helper module convention |
| `accounts/views.py` new views (crew_*, bulk_add_crew) | `accounts/views.py` invite_user (:122), project_invitations (:160), project_access_requests (:478) | LOW — function-based view pattern is uniform |
| `accounts/views.py` new email helper `send_crew_added_email` | `accounts/views.py` send_invitation_email (:241), send_access_request_email (:548), send_access_approved_email (:571) | LOW — three existing analogs for inline-HTML email helper |
| `accounts/admin.py` Crew + CrewMember admin classes | `accounts/admin.py` ProjectMemberAdmin (:66), InvitationAdmin (:100), UserProfileAdmin (:151) | LOW — admin-class pattern uniform |
| `templates/accounts/crew_index.html` and `crew_detail.html` | `templates/accounts/dashboard.html`, `invitation_preview.html`, `project_invitations.html` | LOW — standalone-page pattern (full `<html>`, inline `<style>`, project's dark theme) |
| `planner/tests/test_crew_rosters.py` | `planner/tests/test_channel_record_defaults.py` (recent, 5-test class with `Client` + `setUpTestData`) | LOW — recommended template |
| `planner/crew.py` `_projects_crew_was_added_to(crew)` | **NO ANALOG** — this is the "which projects has this crew been bulk-added to" tracking shape that Open Question §1 calls out | MEDIUM — Planner MUST resolve OQ §1 before writing this function |

**Single risk signal:** `_projects_crew_was_added_to` has no analog because the underlying data shape (link table vs inference) is unresolved. Planner must pick (recommend Option A: explicit `CrewProjectAdd` table) before this helper can be implemented.

## Sources

### Primary (HIGH confidence)
- Django 5.2 docs — constraints: https://docs.djangoproject.com/en/5.2/ref/models/constraints/ — `condition=` is the canonical kwarg for CheckConstraint and UniqueConstraint in 5.1+. `[VERIFIED]`
- Django 5.2 docs — unique_together: https://docs.djangoproject.com/en/5.2/ref/models/options/#unique-together — explicit recommendation to use UniqueConstraint over unique_together for new code. `[CITED]`
- Postgres docs — unique indexes: https://www.postgresql.org/docs/current/indexes-unique.html — quotes "null values in a unique column are not considered equal, allowing multiple nulls in the column." Confirms partial UniqueConstraint requirement for D-02. `[CITED]`
- Installed Django source `venv/lib/python3.14/site-packages/django/db/models/constraints.py:158-201` — verified `check=` deprecated, `condition=` canonical. `[VERIFIED]`
- Installed Django backend features `venv/lib/python3.14/site-packages/django/db/backends/base/features.py` — `supports_table_check_constraints=True` and `supports_partial_indexes=True` baseline for both SQLite and Postgres. `[VERIFIED]`
- Project code reads (`[VERIFIED]`):
  - `accounts/views.py` (590 lines) — register at :16, invite_user at :122, owner-check at :129, accept_invitation at :181, send_invitation_email at :241, set_project at :359
  - `accounts/forms.py` — RegistrationForm shape
  - `accounts/urls.py` — confirms route shapes; `set_project` URL name confirmed
  - `accounts/admin.py` — confirms `showstack_admin_site.register(...)` pattern
  - `planner/models.py:692-716` — ProjectMember (unique_together pattern)
  - `planner/models.py:3809-3849` — Invitation (untouched per SPEC Req 5)
  - `planner/admin_ordering.py` — order_map and grouping conventions
  - `templates/admin/base_site.html:91-132` — userlinks block (D-04 insertion point #1)
  - `templates/accounts/dashboard.html:285-294` — header-right (D-04 insertion point #2)
  - `templates/accounts/invite_user.html:179-220` — invite_user card (D-05 insertion point)
  - `planner/tests/test_channel_record_defaults.py` — test fixture pattern recommendation

### Secondary (MEDIUM confidence)
- None required — all critical facts verified against installed source or official docs.

### Tertiary (LOW confidence)
- None — Phase 6 problem domain is bounded by Django 5.2 + project's existing patterns.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified Django 5.2 + Resend pin; constraint syntax verified against installed source
- Architecture: HIGH — every new file has a code analog; insertion points verified by reading actual files
- Pitfalls: HIGH — `auto_now_add` + `bulk_create`, `unique_together` + NULL semantics, `check=` deprecation are all documented Django/Postgres known-issues
- Open Questions: MEDIUM — OQ §1 (`_projects_crew_was_added_to`) is a genuinely unresolved data-shape question that needs a planner decision; A5 recommends adding a `CrewProjectAdd` link table

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (30 days — stable framework, stable codebase)

---

*Phase: 06-trusted-crew-rosters*
*Research date: 2026-05-14*
*Next step: /gsd-plan-phase 6 — decomposition into atomic plans*
