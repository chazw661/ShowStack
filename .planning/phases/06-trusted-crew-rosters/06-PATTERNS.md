# Phase 6: Trusted Crew Rosters — Pattern Map

**Mapped:** 2026-05-14
**Files analyzed:** 13 (12 new/modified source files + 1 test file)
**Analogs found:** 13 / 13 (100% coverage; 1 MEDIUM-risk pattern is greenfield link table)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `planner/models.py` (+`Crew`) | model | CRUD | `planner/models.py:692` `ProjectMember` + `planner/models.py:720` `ProjectAccessRequest` | exact (owner-scoped FK + name + timestamps) |
| `planner/models.py` (+`CrewMember`) | model | CRUD | `planner/models.py:692` `ProjectMember` (role choices) + `planner/models.py:3809` `Invitation` (email field) | role-match (XOR shape is greenfield, base is exact) |
| `planner/models.py` (+`CrewProjectAdd`) | model (link table) | event-log | `planner/models.py:692` `ProjectMember` (FK+FK+timestamp pattern) | role-match (3-field link table is composable from `ProjectMember`'s shape) |
| `planner/crew.py` (NEW) | utility (pure-function helper) | transform | `planner/utils/yamaha_export.py` (module convention) + `accounts/views.py:181` `accept_invitation` (the email-match flow it functionally replaces) | exact for module shape; role-match for claim-on-register logic |
| `accounts/views.py:register()` edit | controller (1-line addition + atomic wrapper) | request-response | `accounts/views.py:16-37` self-analog | exact (own pattern) |
| `accounts/views.py` (+`crew_index`, `crew_create`, `crew_detail`, `crew_delete`, `crew_member_add`, `crew_member_remove`) | controller | request-response | `accounts/views.py:122` `invite_user` + `accounts/views.py:160` `project_invitations` | exact (function-based view, `@login_required` + owner-check + form-or-render pattern) |
| `accounts/views.py` (+`bulk_add_crew`) | controller | request-response (POST + redirect + flash) | `accounts/views.py:122` `invite_user` (owner-check + redirect+flash); `accounts/views.py:497` ProjectMember.get_or_create idempotency | exact (every primitive exists in invite_user + project_access_requests) |
| `accounts/views.py` (+`send_crew_added_email`) | utility (email helper) | side-effect (Resend send) | `accounts/views.py:241` `send_invitation_email`; `accounts/views.py:571` `send_access_approved_email` | exact (inline f-string HTML, `resend.Emails.send`) |
| `accounts/admin.py` (+`CrewAdmin`, `CrewMemberAdmin`, `CrewProjectAddAdmin`) | admin (registration) | CRUD | `accounts/admin.py:66` `ProjectMemberAdmin` + `accounts/admin.py:100` `InvitationAdmin` | exact (`BaseEquipmentAdmin` subclass + `showstack_admin_site.register(...)`) |
| `planner/admin_ordering.py` edits | config (sidebar order map) | static-data | `planner/admin_ordering.py:94-170` self-analog | exact (own dict pattern) |
| `accounts/urls.py` edits | route registration | static-data | `accounts/urls.py:4-21` self-analog | exact (own pattern) |
| `templates/accounts/crew_index.html` (NEW) | template (standalone page) | static-render | `templates/accounts/dashboard.html` (dark theme, inline `<style>`); `templates/accounts/project_invitations.html` (card+empty-state structure) | exact (standalone-page convention with inline CSS) |
| `templates/accounts/crew_detail.html` (NEW) | template (standalone page) | static-render | `templates/accounts/project_invitations.html` (table + back link + role-badge) | exact |
| `templates/accounts/invite_user.html` edit | template (additive panel) | static-render | `templates/accounts/invite_user.html:179-220` self-analog | exact (own structure; insertion-only at line ~218) |
| `templates/admin/base_site.html` edit | template (additive link in `userlinks` block) | static-render | `templates/admin/base_site.html:91-132` self-analog (Help button at line 128 is the closest sibling) | exact (own block) |
| `templates/accounts/dashboard.html` edit | template (additive link in `.header-right`) | static-render | `templates/accounts/dashboard.html:285-294` self-analog (existing `btn-admin`+`btn-logout` is the sibling) | exact (own block) |
| `planner/tests/test_crew_rosters.py` (NEW) | test | CRUD | `planner/tests/test_channel_record_defaults.py` | exact (Phase 5 style — `setUpTestData` + `Client` + `force_login`) |

## Pattern Assignments

### `planner/models.py` — Crew + CrewMember + CrewProjectAdd (model, CRUD)

**Insertion point:** After `class ProjectAccessRequest` ends at `planner/models.py:748` (around line 750) and BEFORE the `#-----Console Model----` comment at `planner/models.py:753`. This places new models inside the "Project Membership" cluster and keeps the file's existing section grouping intact.

**Imports pattern** — these are already present at the top of `planner/models.py` (verify before adding):

```python
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
```

ADD (only `Q` is not already imported earlier in the file — check before adding `from django.db.models import CheckConstraint, UniqueConstraint, Q` near top of file; if `models.Q` works inline that's also fine):

```python
from django.db.models import CheckConstraint, UniqueConstraint, Q
```

**ProjectMember analog excerpt** (`planner/models.py:692-716` — the closest CRUD shape to copy):

```python
class ProjectMember(models.Model):
    """Users who have been invited to collaborate on a project"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    ROLES = [
        ('editor', 'Editor - Can view and edit'),
        ('viewer', 'Viewer - Can only view'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLES, default='editor')
    invited_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
    User,
    on_delete=models.CASCADE,
    related_name='invitations_sent'
)
    
    class Meta:
        unique_together = ['project', 'user']
        verbose_name = "Project Member"
        verbose_name_plural = "Project Members"
    
    def __str__(self):
        return f"{self.user.username} → {self.project.name} ({self.role})"
```

**ProjectAccessRequest analog excerpt** (`planner/models.py:720-748` — newer style using `settings.AUTH_USER_MODEL`; PREFER this for new Phase 6 models per Pitfall 4):

```python
class ProjectAccessRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='access_requests')
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='access_requests')
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_access_requests'
    )
    ...
    class Meta:
        unique_together = ('project', 'requester')
        ordering = ['-requested_at']
```

**Invitation analog excerpt** (`planner/models.py:3826-3849` — for the `EmailField` + `STATUS/ROLE_CHOICES` shape used by `CrewMember`):

```python
project = models.ForeignKey(
    Project,
    on_delete=models.CASCADE,
    related_name='invitations'
)
email = models.EmailField()
role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')
...
invited_by = models.ForeignKey(
    User,
    on_delete=models.CASCADE,
    related_name='members_invite'
)
invited_at = models.DateTimeField(auto_now_add=True)
```

**Code to write (per D-01, D-02, D-09, D-15):**

```python
class Crew(models.Model):
    """Owner-scoped named roster of trusted collaborators (Phase 6)."""
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
    """Single-table polymorphic roster row: existing user XOR pending email (Phase 6)."""
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
    """Tracks which projects a crew has been bulk-added to (Phase 6, D-09).

    Read by the auto-claim helper to materialize ProjectMember rows for
    newly-registered users whose email matched a pending CrewMember.
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

**Key shape choices:**
- `settings.AUTH_USER_MODEL` (not `User`) per Pitfall 4 — mirrors `ProjectAccessRequest`.
- `Crew.unique_together` kept (both fields non-nullable; Django 5.2 docs say this is fine; matches existing style).
- `CrewMember.constraints` uses `condition=` (Django 5.1+ canonical, not deprecated `check=` per Pitfall — `[VERIFIED: source grep]` in RESEARCH.md).
- `Q` is imported once at top of file; the rest of the file likely already imports `models.Q` inline — confirm by reading the existing imports before adding.

---

### `planner/crew.py` (NEW) — auto-claim helper (utility, transform)

**Analog 1 (module convention):** `planner/utils/yamaha_export.py:1-30`

```python
# planner/utils/yamaha_export.py
from io import StringIO, BytesIO
from django.http import HttpResponse
import zipfile


def export_yamaha_csvs(console):
    """Export all Yamaha Rivage CSV files"""
    zip_buffer = BytesIO()
    ...
```

Lesson: pure-function module at the top of file, no class wrapper. One docstring per function. Imports at top.

**Analog 2 (the email-match flow it replaces):** `accounts/views.py:181-238` `accept_invitation` — note specifically the case-insensitive compare at line 207:

```python
# User is logged in - check if their email matches
if request.user.email.lower() != invitation.email.lower():
    messages.error(
        request,
        f'This invitation was sent to {invitation.email}. '
```

…and the `ProjectMember.objects.get_or_create` idempotency at `accounts/views.py:497-502` (inside `project_access_requests`):

```python
# Create ProjectMember
ProjectMember.objects.get_or_create(
    project=project,
    user=access_req.requester,
    defaults={'role': role, 'invited_by': request.user}
)
```

**Code to write (per D-07, D-08, D-09, D-10, D-11):**

```python
"""
Auto-claim helper: when a new user registers, rebind any pending
CrewMember rows whose email matches their account, and materialize
ProjectMember rows for every project the crew has been bulk-added to.

Called from accounts/views.py:register() (Phase 6, D-07).
NO Django signals — register() is the single, visible, testable entry point.
"""
import logging

from django.db import transaction
from planner.models import CrewMember, CrewProjectAdd, ProjectMember

logger = logging.getLogger(__name__)


def claim_pending_crew_memberships(user):
    """
    For every CrewMember(user=NULL, email iexact user.email):
      1. UPDATE IN PLACE: email=None, user=user (preserves default_role).
      2. For every CrewProjectAdd of that crew, create a ProjectMember
         row for `user` with role=default_role if one does not exist.

    Returns: list of newly-created ProjectMember rows so the caller can
    send confirmation emails (Req 4).

    D-08: case-insensitive via __iexact + explicit .strip() on the
    user-side value before passing to filter().
    D-11: caller wraps form.save() + this call in a single
    transaction.atomic() block; this helper opens its own inner
    transaction defensively.
    """
    normalized = (user.email or '').strip()
    if not normalized:
        return []

    pending = CrewMember.objects.filter(
        user__isnull=True,
        email__iexact=normalized,
    ).select_related('crew')

    new_memberships = []

    with transaction.atomic():
        for cm in pending:
            # Step 1: rebind to new user (preserves default_role + added_at)
            cm.user = user
            cm.email = None
            cm.save(update_fields=['user', 'email'])

            # Step 2: materialize ProjectMember rows for every project the
            # crew has been bulk-added to (D-09 — read CrewProjectAdd).
            for cpa in CrewProjectAdd.objects.filter(crew=cm.crew).select_related('project'):
                pm, created = ProjectMember.objects.get_or_create(
                    project=cpa.project,
                    user=user,
                    defaults={
                        'role': cm.default_role,
                        'invited_by': cm.crew.owner,
                    },
                )
                if created:
                    new_memberships.append(pm)

    return new_memberships
```

**Note:** Confirmation-email sends per D-10 happen in the caller (the planner can either send from inside this helper wrapped in try/except, or return the list and have the caller send). Recommend caller sends — keeps this helper transaction-pure and testable without monkey-patching Resend.

---

### `accounts/views.py:register()` edit (controller, request-response)

**Self-analog** at `accounts/views.py:16-37`:

```python
def register(request):
    """
    Public registration view - creates free accounts.
    Free users can accept invitations but cannot create projects.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request, 
                f'Welcome to ShowStack, {user.first_name}! Your free account has been created. '
                'You can now accept project invitations from other users.'
            )
            return redirect('login')
    else:
        form = RegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})
```

**Edit per D-07 + D-11:** Wrap `form.save()` + the new claim call in `transaction.atomic()`. Insertion is two lines added + one indent change:

```python
from django.db import transaction
from planner.crew import claim_pending_crew_memberships
# ...
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                # D-07: auto-claim pending CrewMember rows that match the new
                # user's email (case-insensitive). Confirmation emails for any
                # materialized ProjectMember rows are sent below — kept out of
                # the atomic block so a Resend hiccup never rolls back the user.
                new_pms = claim_pending_crew_memberships(user)
            # D-10: log + swallow email failures (per-recipient, defensive).
            from accounts.views import send_crew_added_email  # or local import
            for pm in new_pms:
                try:
                    send_crew_added_email(pm, request)
                except Exception:
                    logger.exception("Crew-added email failed for %s", pm.user.email)
            messages.success(
                request,
                f'Welcome to ShowStack, {user.first_name}! Your free account has been created. '
                'You can now accept project invitations from other users.'
            )
            return redirect('login')
```

(Planner: refine the import shape — `send_crew_added_email` lives in the same `accounts/views.py` file, so no import needed; use the inline function reference directly. The example above shows the structure.)

---

### `accounts/views.py` (+`crew_index`, `crew_create`, `crew_detail`, `crew_delete`, `crew_member_add`, `crew_member_remove`) (controller, request-response)

**Analog 1 (auth gate + render pattern):** `accounts/views.py:122-157` `invite_user`:

```python
@login_required
def invite_user(request, project_id):
    """
    Allow project owners to invite users via email.
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check if user is the project owner
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can invite users.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = InviteUserForm(
            request.POST,
            project=project,
            invited_by=request.user
        )
        if form.is_valid():
            invitation = form.save()
            
            # Send invitation email
            send_invitation_email(invitation, request)
            
            messages.success(
                request,
                f'Invitation sent to {invitation.email} as {invitation.get_role_display()}!'
            )
            return redirect('project_invitations', project_id=project.id)
    else:
        form = InviteUserForm(project=project, invited_by=request.user)
    
    context = {
        'form': form,
        'project': project,
    }
    return render(request, 'accounts/invite_user.html', context)
```

**Analog 2 (list view + render):** `accounts/views.py:160-178` `project_invitations`:

```python
@login_required
def project_invitations(request, project_id):
    """
    View all invitations for a project (owner only).
    """
    project = get_object_or_404(Project, id=project_id)
    
    # Check if user is the project owner
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can view invitations.')
        return redirect('dashboard')
    
    invitations = Invitation.objects.filter(project=project).order_by('-invited_at')
    
    context = {
        'project': project,
        'invitations': invitations,
    }
    return render(request, 'accounts/project_invitations.html', context)
```

**Copy patterns to mirror:**
- `@login_required` decorator.
- `get_object_or_404` for crew/member lookup.
- Owner gate: `if crew.owner != request.user:` → `messages.error(...)` → `redirect('dashboard')`.
- POST-handle branch with form save + flash + redirect; GET branch renders template.
- Context dict with the object + the form (if applicable).

---

### `accounts/views.py` (+`bulk_add_crew`) (controller, request-response)

**Analog 1 (owner gate + redirect):** `accounts/views.py:122-131` (excerpted above).

**Analog 2 (idempotent ProjectMember create + transactional intent):** `accounts/views.py:485-518` `project_access_requests` approve branch:

```python
if project.owner != request.user:
    messages.error(request, "Only the project owner can manage access requests.")
    return redirect('/audiopatch/mic-tracker/')

if request.method == 'POST':
    req_id = request.POST.get('request_id')
    action = request.POST.get('action')  # 'approve' or 'deny'
    role = request.POST.get('role', 'viewer')

    access_req = get_object_or_404(ProjectAccessRequest, id=req_id, project=project)

    if action == 'approve':
        # Create ProjectMember
        ProjectMember.objects.get_or_create(
            project=project,
            user=access_req.requester,
            defaults={'role': role, 'invited_by': request.user}
        )
```

**Code to write (per D-06, D-09, D-10; combine the dedupe upfront-query pattern from RESEARCH.md Pattern 3):**

```python
@login_required
def bulk_add_crew(request, project_id, crew_id):
    """
    Bulk-add an entire crew to a project (Phase 6, D-06).

    POST-only. Creates ProjectMember rows for every CrewMember with a User
    FK that is not already a member of the project. Sends one confirmation
    email per new row (D-10: log + swallow email failures).
    """
    project = get_object_or_404(Project, id=project_id)
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can add a crew.')
        return redirect('dashboard')

    crew = get_object_or_404(Crew, id=crew_id, owner=request.user)

    if request.method != 'POST':
        return redirect('invite_user', project_id=project.id)

    # Resolve crew members with a User FK; pending-email rows are skipped
    # here and will materialize via the auto-claim hook in register().
    resolved = list(crew.crewmember_set.filter(user__isnull=False).select_related('user'))

    # Single upfront dedupe query (SPEC Req 8).
    existing_user_ids = set(
        ProjectMember.objects.filter(
            project=project,
            user_id__in=[m.user_id for m in resolved],
        ).values_list('user_id', flat=True)
    )

    to_add = [m for m in resolved if m.user_id not in existing_user_ids]
    already = len(resolved) - len(to_add)

    # Pitfall 2: use .save() in a loop (not bulk_create) so auto_now_add
    # fires for ProjectMember.invited_at. Crews are small (1-10 members).
    new_rows = []
    for m in to_add:
        pm = ProjectMember.objects.create(
            project=project,
            user=m.user,
            role=m.default_role,
            invited_by=request.user,
        )
        new_rows.append(pm)

    # D-09: record that this crew has been added to this project so the
    # auto-claim hook can materialize future-registered members.
    CrewProjectAdd.objects.get_or_create(crew=crew, project=project)

    # D-10: log + swallow email failures (per-recipient, defensive).
    for pm in new_rows:
        try:
            send_crew_added_email(pm, request)
        except Exception:
            logger.exception("Crew-added email failed for %s", pm.user.email)

    messages.success(
        request,
        f"Added {len(to_add)} members from {crew.name}; "
        f"{already} were already on this project."
    )
    return redirect('invite_user', project_id=project.id)
```

---

### `accounts/views.py` (+`send_crew_added_email`) (utility, side-effect)

**Analog 1 (canonical):** `accounts/views.py:241-290` `send_invitation_email`:

```python
def send_invitation_email(invitation, request):
    """
    Send invitation email with acceptance link using Resend API.
    """
    import resend
    import os
    
    accept_url = request.build_absolute_uri(
        f'/invitations/accept/{invitation.token}/'
    )
    
    subject = f'Invitation to join {invitation.project.name} on ShowStack'
    
    message = f"""
<h2>You've been invited to collaborate!</h2>

<p><strong>{invitation.invited_by.get_full_name() or invitation.invited_by.username}</strong> has invited you to collaborate on their ShowStack project:</p>

<ul>
    <li><strong>Project:</strong> {invitation.project.name}</li>
    <li><strong>Role:</strong> {invitation.get_role_display()}</li>
    ...
</ul>

<p><a href="{accept_url}" style="display: inline-block; padding: 12px 24px; background-color: #4a9eff; color: white; text-decoration: none; border-radius: 6px; margin: 20px 0;">Accept Invitation</a></p>
...
"""
    
    # Send email using Resend API
    resend.api_key = os.environ.get('RESEND_API_KEY')
    
    try:
        params = {
           "from": "ShowStack <noreply@showstack.io>",
            "to": [invitation.email],
            "subject": subject,
            "html": message,
        }
        email = resend.Emails.send(params)
        print(f"✅ Email sent successfully to {invitation.email}")
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        raise
```

**Analog 2 (the new no-token "you've been added" framing):** `accounts/views.py:571-591` `send_access_approved_email`:

```python
def send_access_approved_email(access_req, request):
    import resend, os
    resend.api_key = os.environ.get('RESEND_API_KEY')
    login_url = request.build_absolute_uri('/login/')
    html = f"""
    <h2>You've been granted access!</h2>
    <p>Your request to join <strong>{access_req.project.name}</strong> has been approved.</p>
    <p><strong>Your role:</strong> {access_req.get_assigned_role_display()}</p>
    <p><a href="{login_url}" style="display:inline-block;padding:12px 24px;background:#4a9eff;color:white;text-decoration:none;border-radius:6px;">
    Open ShowStack</a></p>
    <p><small>ShowStack — Professional Audio Production Management</small></p>
    """
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [access_req.requester.email],
            "subject": f"Access Approved: {access_req.project.name}",
            "html": html,
        })
    except Exception as e:
        print(f"❌ Approval email error: {e}")
```

**Key choice (per D-10):** mirror `send_access_approved_email`'s log-and-swallow (try/except without `raise`), NOT `send_invitation_email`'s re-raise. Bulk-add contract is "rows exist"; email is best-effort.

**Code to write:**

```python
def send_crew_added_email(project_member, request):
    """
    Inform a user they have been added to a project via the crew bulk-add
    flow (Phase 6, Req 4). NO accept_url token — access is already active.

    D-10: log + swallow exceptions. Bulk-add is durable; one bad email
    must not undo a successful crew-add.
    """
    import resend, os
    from django.urls import reverse

    resend.api_key = os.environ.get('RESEND_API_KEY')
    project_url = request.build_absolute_uri(
        reverse('set_project', args=[project_member.project.id])
    )
    owner = project_member.project.owner
    owner_label = owner.get_full_name() or owner.username

    subject = f"{owner_label} added you to {project_member.project.name} on ShowStack"
    html = f"""
<h2>You've been added to a ShowStack project</h2>
<p><strong>{owner_label}</strong> added you to their crew on:</p>
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
    try:
        resend.Emails.send({
            "from": "ShowStack <noreply@showstack.io>",
            "to": [project_member.user.email],
            "subject": subject,
            "html": html,
        })
        print(f"✅ Crew-added email sent to {project_member.user.email}")
    except Exception as e:
        # D-10: log + swallow — do NOT re-raise.
        print(f"❌ Crew-added email error: {e}")
```

---

### `accounts/admin.py` (+`CrewAdmin`, `CrewMemberAdmin`, `CrewProjectAddAdmin`) (admin, CRUD)

**Analog 1:** `accounts/admin.py:66-96` `ProjectMemberAdmin`:

```python
class ProjectMemberAdmin(BaseEquipmentAdmin):
    list_display = ['project', 'user', 'role', 'invited_by', 'invited_at']
    list_filter = ['role', 'invited_at']
    search_fields = ['project__name', 'user__username', 'user__email']

    class Media:
        css = {
            'all': ('admin/css/project_member_admin.css',)
        }

    def has_module_permission(self, request):
        """Only show Projects section to premium users who own projects"""
        if request.user.is_superuser:
            return True
        
        # Must be premium AND own at least one project
        if not hasattr(request.user, 'userprofile'):
            return False
        
        from planner.models import Project
        is_premium = request.user.userprofile.account_type == 'premium'
        owns_projects = Project.objects.filter(owner=request.user).exists()
        
        return is_premium and owns_projects
```

**Analog 2:** `accounts/admin.py:100-147` `InvitationAdmin` (for fieldsets + readonly_fields patterns).

**Registration pattern** at `accounts/admin.py:192-209` (the EXACT lines to mirror — note: import at line 193 fetches `showstack_admin_site` from `planner/admin_site.py`):

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

**Code to add (after line 209):**

```python
# Phase 6: Trusted Crew Rosters
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

---

### `planner/admin_ordering.py` edits (config, static-data)

**Self-analog** at `planner/admin_ordering.py:94-170` — the `order_map` dict. Insertion point is inside the "User/Project Management (1-4)" cluster:

```python
    # Define the correct order with proper groupings
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
```

**Code to add (per the suggestion in RESEARCH.md Pitfall 6 — slot between `projectmember=2` and `invitation=3`):**

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

**No other edits required** — the file's monkey-patch is generic and will pick up the new keys automatically.

---

### `accounts/urls.py` edits (route registration, static-data)

**Self-analog** at `accounts/urls.py:1-21`:

```python
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.ShowStackLoginView.as_view(), name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Invitation URLs
    path('projects/<int:project_id>/invite/', views.invite_user, name='invite_user'),
    path('projects/<int:project_id>/invitations/', views.project_invitations, name='project_invitations'),
    path('invitations/accept/<uuid:token>/', views.accept_invitation, name='accept_invitation'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('set-project/<int:project_id>/', views.set_project, name='set_project'),
    path('delete-project/<int:project_id>/', views.delete_project, name='delete_project'),
    path('leave-project/<int:project_id>/', views.leave_project, name='leave_project'),

    path('projects/request/<uuid:invite_token>/', views.project_request_access, name='request_access'),
    path('projects/<int:project_id>/requests/', views.project_access_requests, name='access_requests'),
]
```

**Code to add (append at the end of the list, before the closing `]`, per D-03's route plan):**

```python
    # Phase 6: Trusted Crew Rosters
    path('crew/', views.crew_index, name='crew_index'),
    path('crew/new/', views.crew_create, name='crew_create'),
    path('crew/<int:crew_id>/', views.crew_detail, name='crew_detail'),
    path('crew/<int:crew_id>/delete/', views.crew_delete, name='crew_delete'),
    path('crew/<int:crew_id>/members/add/', views.crew_member_add, name='crew_member_add'),
    path('crew/<int:crew_id>/members/<int:member_id>/remove/', views.crew_member_remove, name='crew_member_remove'),
    path('projects/<int:project_id>/invite/add-crew/<int:crew_id>/', views.bulk_add_crew, name='bulk_add_crew'),
```

**URL prefix:** `accounts/urls.py` is included in the project under whatever root it currently lives — confirm by checking `audiopatch/urls.py`. The existing routes (e.g. `path('crew/...')`) will resolve relative to that root. Names (`crew_index`, etc.) match what RESEARCH.md and CONTEXT.md assume.

---

### `templates/accounts/crew_index.html` (NEW) — standalone page (template, static-render)

**Analog (page skeleton + dark theme):** `templates/accounts/dashboard.html:1-90` head + inline CSS, and `:280-294` body header structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - ShowStack</title>
        <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #1a1a1a;
            min-height: 100vh;
            color: #e0e0e0;
        }
        
        .header { ... }
        .logo h1 { ... color: #4a9eff; ... }
        .header-right { display: flex; gap: 20px; align-items: center; }
        .btn-logout { padding: 8px 16px; background: #dc3545; ... }
        .btn-admin { padding: 8px 16px; background: #4a9eff; ... }
        ...
        .container { max-width: 1200px; margin: 40px auto; padding: 0 30px; }
        ...
        </style>
</head>
<body>
    <div class="header">
        <div class="logo">
            <h1>ShowStack</h1>
        </div>
        <div class="header-right">
            <div class="user-info">
                <strong>{{ user.get_full_name|default:user.username }}</strong>
                <span class="account-badge badge-{{ account_type }}">{{ account_type }} Account</span>
            </div>
            {% if user.is_superuser or account_type == 'paid' or account_type == 'beta' %}
            <a href="/admin/" class="btn-admin">Planner</a>
            {% endif %}
            <a href="{% url 'logout' %}" class="btn-logout">Logout</a>
        </div>
    </div>
    <div class="container">
        ...
    </div>
</body>
</html>
```

**Lesson:** Standalone page (no `{% extends %}`), full `<html>` doc, inline `<style>` block, dark theme (`#1a1a1a` body, `#2a2a2a` header, `#4a9eff` accent), `.container { max-width; margin: 40px auto }`, `.btn-admin` blue button class. Header has a logo on the left and an action cluster on the right.

**Empty state pattern** from `templates/accounts/project_invitations.html:269-273`:

```html
<div class="empty-state">
    <p>No invitations sent yet.</p>
    <p>Click "Invite User" to invite collaborators to your project.</p>
</div>
```

---

### `templates/accounts/crew_detail.html` (NEW) — standalone page (template, static-render)

**Analog (table + back link + status/role badges):** `templates/accounts/project_invitations.html:209-275`:

```html
<body>
    <div class="header">
        <div class="logo">
            <h1>ShowStack</h1>
        </div>
        <div class="header-right">
            <a href="{% url 'dashboard' %}" class="btn-back">← Back to Dashboard</a>
            <a href="{% url 'invite_user' project.id %}" class="btn-invite">+ Invite User</a>
        </div>
    </div>
    
    <div class="container">
        <div class="page-header">
            <h2>Project Invitations</h2>
            <div class="project-info">
                <p><strong>{{ project.name }}</strong> - {{ project.start_date|date:"F d, Y" }} at {{ project.venue }}</p>
            </div>
        </div>
        
        {% if messages %}
        <div class="messages">
            {% for message in messages %}
            <div class="alert alert-{{ message.tags }}">{{ message }}</div>
            {% endfor %}
        </div>
        {% endif %}
        
        <div class="card">
            <h3>All Invitations ({{ invitations.count }})</h3>
            
            {% if invitations %}
            <table class="invitations-table">
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Status</th>
                        ...
```

**Key elements to mirror:**
- `.role-badge.role-editor` / `.role-viewer` color-coded pills (existing CSS at `project_invitations.html:179-195`).
- `.status-badge` family for the "pending signup" pill (orange/amber per D-05 — analog at `:159-162` `.status-pending`).
- The card-with-table layout.
- Empty state at `:269-273`.

---

### `templates/accounts/invite_user.html` edit (template, static-render)

**Self-analog at insertion point** — `templates/accounts/invite_user.html:179-221` (the full existing card; insertion is after `</form>` at line 218 and BEFORE the closing `</div>` of `.container` at line 220):

```html
        <div class="card">
            <h2>Invite User to Project</h2>
            
            <div class="project-info">
                <p><strong>Project:</strong> {{ project.name }}</p>
                <p><strong>Show Date:</strong> {{ project.start_date|date:"F d, Y" }}</p>
                <p><strong>Venue:</strong> {{ project.venue }}</p>
            </div>
            
            <form method="post">
                {% csrf_token %}
                
                <div class="form-group">
                    <label for="{{ form.email.id_for_label }}">Email Address</label>
                    {{ form.email }}
                    ...
                </div>
                
                <div class="form-group">
                    <label for="{{ form.role.id_for_label }}">Role</label>
                    {{ form.role }}
                    ...
                </div>
                
                <button type="submit" class="btn-primary">Send Invitation</button>
            </form>
        </div>
    </div>
</body>
</html>
```

**Insertion point** — exactly after the `</div>` that closes the existing `.card` at line 219, and BEFORE the `</div>` that closes `.container` at line 220:

```html
        </form>
    </div>  <!-- line 219: end of existing .card -->

    {# Phase 6: Add your crew — additive panel, no edits to existing form above #}
    {% if owner_crews %}
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
</div>  <!-- line 220: end of existing .container -->
</body>
</html>
```

**Note:** The existing template uses a light theme (`background: #f5f5f5` body, white cards). The new panel inherits these styles via the `.card` and `.btn-primary` classes already defined at lines 51-138. NO new CSS needed.

**View-side requirement:** `invite_user(request, project_id)` (`accounts/views.py:122`) must be updated to inject `owner_crews` into the context, with each crew annotated for `eligible_count`, `member_display`, and per-member `is_already_member` / `is_pending` flags. This is an additive context update — the existing `form` + `project` context keys stay intact. (SPEC Req 5 — additivity preserved.)

---

### `templates/admin/base_site.html` edit (template, static-render)

**Self-analog** at lines 91-132 — the `userlinks` block:

```html
{% block userlinks %}
    <!-- User Role Badge -->
    {% if user.is_authenticated %}
        <span style="display: inline-block; margin-right: 15px;">
            <span style="color: #fff; margin-right: 8px;">{{ user.username }}</span>
            {% if user.is_superuser %}
                <span style="background: #e74c3c; color: white; padding: 4px 10px; border-radius: 3px; font-size: 11px; font-weight: bold;">SUPERUSER</span>
            {% elif user_role == 'owner' %}
                <span style="background: #3498db; ...">OWNER</span>
            ...
        </span>
    {% endif %}
    
    <!-- Project Switcher (for superusers and owners) or Static Display (for editors/viewers) -->
    {% if show_project_dropdown %}
        ...
    {% endif %}
        <button onclick="helpOpen()" style="background:none;border:1px solid #444;border-radius:4px;color:#ccc;font-size:13px;padding:5px 12px;cursor:pointer;margin-right:12px;" onmouseover="this.style.color='#00ff88';this.style.borderColor='#00ff88'" onmouseout="this.style.color='#ccc';this.style.borderColor='#444'">? Help</button>

    
    {{ block.super }}
{% endblock %}
```

**Insertion point:** Immediately BEFORE `{{ block.super }}` at line 131, AFTER the existing Help button (line 128). The Help button is the closest sibling — copy its inline-style "button-like link" treatment for consistency:

```html
    <button onclick="helpOpen()" ...>? Help</button>

    {# Phase 6: My Crew link — always visible for authenticated users (D-12) #}
    {% if user.is_authenticated %}
    <a href="{% url 'crew_index' %}"
       style="background:none;border:1px solid #444;border-radius:4px;color:#ccc;font-size:13px;padding:5px 12px;cursor:pointer;margin-right:12px;text-decoration:none;"
       onmouseover="this.style.color='#00ff88';this.style.borderColor='#00ff88'"
       onmouseout="this.style.color='#ccc';this.style.borderColor='#444'">My Crew</a>
    {% endif %}

    {{ block.super }}
{% endblock %}
```

(Style matches the Help button verbatim — same border, padding, hover green `#00ff88` — preserves visual coherence.)

---

### `templates/accounts/dashboard.html` edit (template, static-render)

**Self-analog** at lines 285-294 — the `.header-right` div:

```html
        <div class="header-right">
            <div class="user-info">
                <strong>{{ user.get_full_name|default:user.username }}</strong>
                <span class="account-badge badge-{{ account_type }}">{{ account_type }} Account</span>
            </div>
            {% if user.is_superuser or account_type == 'paid' or account_type == 'beta' %}
            <a href="/admin/" class="btn-admin">Planner</a>
            {% endif %}
            <a href="{% url 'logout' %}" class="btn-logout">Logout</a>
        </div>
```

**Insertion point:** Between the existing `Planner` link (line 291) and the `Logout` link (line 293):

```html
            {% if user.is_superuser or account_type == 'paid' or account_type == 'beta' %}
            <a href="/admin/" class="btn-admin">Planner</a>
            {% endif %}
            {# Phase 6: My Crew — always visible (D-12) #}
            <a href="{% url 'crew_index' %}" class="btn-admin">My Crew</a>
            <a href="{% url 'logout' %}" class="btn-logout">Logout</a>
```

**Style class:** Reuse `.btn-admin` (already defined at dashboard.html:67-80). No new CSS needed.

---

### `planner/tests/test_crew_rosters.py` (NEW) (test, CRUD)

**Analog (the recommended Phase 5 template):** `planner/tests/test_channel_record_defaults.py:1-67` — module docstring + import block + `setUpTestData` + `setUp`:

```python
"""Regression tests for POL-01 (default_record) and POL-02 (default_record_color).
...
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from planner.models import (
    Console,
    ConsoleInput,
    MultitrackSession,
    MultitrackTrack,
    Project,
)
from planner.utils.reaper_export import hex_to_peakcol

User = get_user_model()


class ChannelRecordDefaultsSeedTests(TestCase):
    """multitrack_add_tracks must seed enabled + color_override from the channel."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pol-tester',
            email='pol-tester@example.com',
            password='test-password-123',
            is_staff=True,
        )
        cls.project = Project.objects.create(
            name='POL Test Show', owner=cls.user,
        )
        ...

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        # CurrentProjectMiddleware reads request.session['current_project_id'].
        session = self.client.session
        session['current_project_id'] = self.project.id
        session.save()
```

**Code to write (skeleton for SPEC Req 1, 3, 4, 6, 7, 8 + D-15 constraints):**

```python
"""Regression tests for Phase 6 — Trusted Crew Rosters.

Covers:
  - Crew + CrewMember + CrewProjectAdd CRUD (SPEC Req 1)
  - Bulk-add creates ProjectMember rows + emails (SPEC Req 3, 4)
  - Pre-onboarding pending row + auto-claim on register (SPEC Req 6)
  - No-cascade removal from crew (SPEC Req 7)
  - Dedupe when user is in multiple crews (SPEC Req 8)
  - D-15 constraints: XOR check + partial uniques
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from planner.models import (
    Crew,
    CrewMember,
    CrewProjectAdd,
    Project,
    ProjectMember,
)

User = get_user_model()


class CrewRosterTests(TestCase):
    """Core CRUD + bulk-add behavior."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='charlie',
            email='charlie@example.com',
            password='test-pw-123',
            is_staff=True,
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

    @patch('accounts.views.send_crew_added_email')
    def test_bulk_add_creates_project_member_rows(self, mock_email):
        url = reverse('bulk_add_crew', args=[self.project.id, self.crew.id])
        self.client.post(url)
        self.assertEqual(
            ProjectMember.objects.filter(project=self.project).count(), 2,
        )
        # SPEC Req 4: one email per new ProjectMember row.
        self.assertEqual(mock_email.call_count, 2)

    def test_xor_check_blocks_user_and_email_both_set(self):
        with self.assertRaises(IntegrityError):
            CrewMember.objects.create(
                crew=self.crew, user=self.mike, email='mike@example.com',
            )

    # ... additional tests for Req 6 (auto-claim), Req 7 (no-cascade),
    # Req 8 (dedupe across crews), D-12 (My Crew link visible) ...
```

## Shared Patterns

### Pattern: Owner Gate
**Source:** `accounts/views.py:128-131` (inside `invite_user`)
**Apply to:** Every new view that touches a `Crew`, `CrewMember`, or `Project` owned by the user (i.e., ALL Phase 6 controllers except `register()`).

```python
if project.owner != request.user:
    messages.error(request, 'Only the project owner can invite users.')
    return redirect('dashboard')
```

For crew-only views, mirror with `crew.owner != request.user`. For the bulk-add view, BOTH owner-gates apply (project owner AND crew owner — and the SPEC says they must be the same user since a crew is owner-scoped).

### Pattern: `@login_required` decorator
**Source:** `accounts/views.py:62, 72, 121, 160` (every authenticated view in the file)
**Apply to:** Every new Phase 6 view EXCEPT `register()` (which is the auth boundary itself).

```python
from django.contrib.auth.decorators import login_required

@login_required
def crew_index(request):
    ...
```

### Pattern: Message Framework Flash
**Source:** `accounts/views.py:130, 145-148, 380` (used throughout)
**Apply to:** Every Phase 6 view's success / error paths.

```python
from django.contrib import messages

messages.success(request, f"Added {n} members from {crew.name}; {m} were already on this project.")
messages.error(request, "Only the project owner can add a crew.")
messages.info(request, "You have been logged out successfully.")
```

The template-side rendering for flash messages is already present in every standalone page (see `dashboard.html:302-308`, `invite_user.html:171-177`, `project_invitations.html:228-234`) — new templates mirror this block verbatim.

### Pattern: Resend Email Send (inline HTML, no template engine)
**Source:** `accounts/views.py:241-290` (`send_invitation_email`) and `accounts/views.py:571-591` (`send_access_approved_email`)
**Apply to:** `send_crew_added_email` only.

```python
import resend, os
resend.api_key = os.environ.get('RESEND_API_KEY')
html = f"""<h2>...</h2>..."""
try:
    resend.Emails.send({
        "from": "ShowStack <noreply@showstack.io>",
        "to": [recipient_email],
        "subject": subject,
        "html": html,
    })
except Exception as e:
    print(f"❌ ...: {e}")
    # D-10: NO raise — log + swallow
```

### Pattern: ProjectMember idempotent create (skip-existing)
**Source:** `accounts/views.py:497-502` (inside `project_access_requests`)
**Apply to:** `bulk_add_crew` (already used in pattern above) and the auto-claim helper.

```python
ProjectMember.objects.get_or_create(
    project=project,
    user=user,
    defaults={'role': role, 'invited_by': owner},
)
```

### Pattern: Case-insensitive email match
**Source:** `accounts/views.py:91, 207` and `planner/models.py:3873`
**Apply to:** `claim_pending_crew_memberships` in `planner/crew.py`.

```python
# Existing pattern (in accept_invitation):
if request.user.email.lower() != invitation.email.lower():
    ...

# Phase 6 pattern (in claim_pending_crew_memberships) — D-08:
normalized = (user.email or '').strip()
pending = CrewMember.objects.filter(
    user__isnull=True,
    email__iexact=normalized,
)
```

### Pattern: Admin registration on showstack_admin_site
**Source:** `accounts/admin.py:192-209`
**Apply to:** `accounts/admin.py` Crew/CrewMember/CrewProjectAdd registration.

```python
from planner.admin_site import showstack_admin_site
showstack_admin_site.register(Model, ModelAdmin)
```

Per CLAUDE.md: **NEVER** use `admin.site.register(...)`.

### Pattern: admin_ordering update
**Source:** CLAUDE.md mandate; `planner/admin_ordering.py:94-170`
**Apply to:** `planner/admin_ordering.py` after registering Crew/CrewMember/CrewProjectAdd.

```python
'crew': 2.3,
'crewmember': 2.5,
'crewprojectadd': 2.7,
```

(slots between `projectmember=2` and `invitation=3` per Pitfall 6 recommendation)

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | All Phase 6 files have a clean analog in the codebase. |

**Single residual MEDIUM risk** (from RESEARCH.md Pattern-Map Risk Signal): the `_projects_crew_was_added_to(crew)` lookup logic. D-09 locks Option A — explicit `CrewProjectAdd` link table — so this risk is now resolved. The lookup is a one-liner:

```python
CrewProjectAdd.objects.filter(crew=cm.crew).select_related('project')
```

…which the planner can place directly inside `claim_pending_crew_memberships`. No separate helper function needed.

## Metadata

**Analog search scope:** `accounts/`, `planner/`, `templates/`, `templates/admin/`, `planner/tests/`
**Files read in this pass:**
- `accounts/views.py` (590 lines — full read)
- `accounts/admin.py` (209 lines — full read)
- `accounts/urls.py` (21 lines — full read)
- `planner/models.py:685-765` (ProjectMember + ProjectAccessRequest)
- `planner/models.py:3800-3879` (Invitation)
- `planner/admin_ordering.py` (full read)
- `planner/utils/yamaha_export.py:1-35` (module convention header)
- `planner/tests/test_channel_record_defaults.py` (full read)
- `templates/accounts/invite_user.html` (full read — 222 lines)
- `templates/accounts/dashboard.html:1-90` (head + header styles) and `:270-309` (header-right insertion point)
- `templates/accounts/project_invitations.html` (full read — 277 lines)
- `templates/admin/base_site.html:1-132` (branding + userlinks block insertion point)

**Pattern extraction date:** 2026-05-14
**Source confidence:** HIGH — every excerpt above is verbatim from a file read in this pass, with line numbers verified.

---

*Phase: 06-trusted-crew-rosters*
*Pattern map created: 2026-05-14*
*Next step: planner consumes this PATTERNS.md to write atomic plans with concrete `<action>` blocks*
