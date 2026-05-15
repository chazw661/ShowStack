---
phase: 06-trusted-crew-rosters
plan: 03
type: execute
wave: 2
depends_on:
  - 06-01
files_modified:
  - accounts/views.py
  - accounts/urls.py
  - templates/accounts/crew_index.html
  - templates/accounts/crew_detail.html
autonomous: true
requirements:
  - SPEC-06-R01
  - SPEC-06-R02
  - SPEC-06-R06
  - SPEC-06-R07
user_setup: []
must_haves:
  truths:
    - "Owner sees /crew/ index listing all their crews with member counts (per D-03 amended)"
    - "Owner with zero crews sees empty state with 'Create your first crew' CTA"
    - "Owner can POST /crew/new/ to create a new named crew (unique per owner)"
    - "Owner sees /crew/<id>/ roster with each member's user/email, default_role, and pending-signup badge for placeholder rows"
    - "Owner can POST /crew/<id>/members/add/ to add a user (by username/email lookup) or a pending email to a crew, with per-member default_role"
    - "Owner can POST /crew/<id>/members/<member_id>/remove/ to delete a CrewMember row WITHOUT cascading to any existing ProjectMember rows (SPEC R7 no-cascade)"
    - "Owner can POST /crew/<id>/delete/ to delete a crew (cascades to CrewMember and CrewProjectAdd via FK CASCADE — but does NOT cascade to ProjectMember rows)"
    - "Non-owner attempts to view another owner's crew are redirected to dashboard with messages.error"
    - "All routes require @login_required"
  artifacts:
    - path: "accounts/views.py"
      provides: "crew_index, crew_create, crew_detail, crew_delete, crew_member_add, crew_member_remove views"
      contains: "def crew_index(request)"
    - path: "accounts/urls.py"
      provides: "URL routes for /crew/* per D-03 (amended 2026-05-14)"
      contains: "name='crew_index'"
    - path: "templates/accounts/crew_index.html"
      provides: "Standalone page listing owner's crews with create CTA"
      min_lines: 80
    - path: "templates/accounts/crew_detail.html"
      provides: "Standalone page with roster table + add-member form + remove buttons"
      min_lines: 100
  key_links:
    - from: "templates/accounts/crew_index.html"
      to: "templates/accounts/crew_detail.html"
      via: "{% url 'crew_detail' crew.id %}"
      pattern: "url 'crew_detail'"
    - from: "templates/accounts/crew_detail.html"
      to: "accounts/views.py:crew_member_remove"
      via: "POST form with csrf_token"
      pattern: "url 'crew_member_remove'"
    - from: "accounts/views.py:crew_member_remove"
      to: "planner.models.CrewMember.delete()"
      via: "single .delete() call — no cascade to ProjectMember"
      pattern: "\\.delete\\(\\)"
---

<objective>
Build the user-facing crew CRUD surface: 6 views in `accounts/views.py`, 6 URL routes in `accounts/urls.py`, and 2 standalone templates (`crew_index.html`, `crew_detail.html`) per D-03 (amended 2026-05-14) + D-14.

Purpose: Owners can manage their crews from `/crew/` without touching Django admin. Covers SPEC R1 (named crew rosters), R2 (per-crew default_role), R6 (pending-email placeholder rows are visible on the roster), R7 (no-cascade removal — verified by acceptance criteria).
Output: 6 new view functions, 6 new URL routes, 2 new templates. Plan 04 (bulk-add) will reuse the `owner_crews` context shape this plan establishes.
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
@accounts/views.py
@accounts/urls.py
@templates/accounts/dashboard.html
@templates/accounts/project_invitations.html

<interfaces>
<!-- Existing patterns the executor MUST mirror verbatim. Extracted from current codebase. -->

From accounts/views.py:122-157 (invite_user — closest analog for auth gate + owner gate + form+render pattern):
```python
@login_required
def invite_user(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can invite users.')
        return redirect('dashboard')
    if request.method == 'POST':
        form = InviteUserForm(request.POST, project=project, invited_by=request.user)
        if form.is_valid():
            invitation = form.save()
            send_invitation_email(invitation, request)
            messages.success(request, f'Invitation sent to {invitation.email} as {invitation.get_role_display()}!')
            return redirect('project_invitations', project_id=project.id)
    else:
        form = InviteUserForm(project=project, invited_by=request.user)
    return render(request, 'accounts/invite_user.html', {'form': form, 'project': project})
```

From accounts/views.py:160-178 (project_invitations — list view pattern):
```python
@login_required
def project_invitations(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can view invitations.')
        return redirect('dashboard')
    invitations = Invitation.objects.filter(project=project).order_by('-invited_at')
    return render(request, 'accounts/project_invitations.html', {'project': project, 'invitations': invitations})
```

From accounts/urls.py (existing pattern — confirmed via audiopatch/urls.py:36 that accounts.urls is included at root prefix `''`, so `path('register/', ...)` resolves at `/register/` and `path('crew/', ...)` will resolve at `/crew/`):
```python
from django.urls import path
from . import views
urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.ShowStackLoginView.as_view(), name='login'),
    ...
    path('projects/<int:project_id>/invite/', views.invite_user, name='invite_user'),
    ...
]
```

From planner/models.py (the queries this plan needs):
- `Crew.objects.filter(owner=request.user).order_by('name')` returns owner's crews
- `crew.crewmember_set.select_related('user').all()` returns roster rows (resolved-user AND pending-email)
- `crew.crewmember_set.count()` gives member count for index display
- `CrewMember(crew=crew, user=user_obj, default_role='editor').save()` creates a resolved-user member row
- `CrewMember(crew=crew, email='alice@example.com', default_role='viewer').save()` creates a pending-email row
- `CrewMember.objects.get(id=member_id, crew=crew).delete()` removes a roster row (no cascade to ProjectMember per SPEC R7)

CrewMember role choices (from Plan 01): `[('editor', 'Editor'), ('viewer', 'Viewer')]` — `default='editor'` per D-02.

Template directory per D-14 + RESEARCH Pitfall 5: project-level `templates/accounts/` (NOT app-level `accounts/templates/accounts/` which does not exist on disk).

Resolving "user_or_email" input on add-member form: try `User.objects.filter(email__iexact=value).first()` then `User.objects.filter(username__iexact=value).first()`. If neither match AND value contains `@`, store as pending email. Otherwise show form error.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add 6 crew CRUD views to accounts/views.py</name>
  <files>accounts/views.py</files>
  <read_first>
    - `accounts/views.py:1-50` (imports — verify which are needed)
    - `accounts/views.py:122-178` (invite_user + project_invitations analogs)
    - `accounts/views.py:181-238` (accept_invitation — DO NOT modify per SPEC R5)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` §"Decisions" D-03 (URL shapes — amended 2026-05-14 to `/crew/` not `/accounts/crew/`), D-13 (helper module location)
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` §"Architecture Patterns" routes 1–5
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` §"accounts/views.py (+crew_index, crew_create, ...)"
  </read_first>
  <action>
Append the following 6 views to `accounts/views.py` AFTER the existing `project_access_requests` cluster (after line 591). Add imports at the top of the file if not already present: `from planner.models import Crew, CrewMember` (Project, ProjectMember are already imported per existing views).

All views use `@login_required`. The owner gate copies `accounts/views.py:128-131` verbatim (mutatis mutandis for `crew.owner`).

```python
# ==================== PHASE 6: TRUSTED CREW ROSTERS — CRUD ====================
from planner.models import Crew, CrewMember


@login_required
def crew_index(request):
    """List the logged-in user's crews (SPEC-06-R01).

    Empty state per D-12: page handles no-crews case with a 'Create your first crew' CTA.
    """
    crews = Crew.objects.filter(owner=request.user).order_by('name')
    return render(request, 'accounts/crew_index.html', {'crews': crews})


@login_required
def crew_create(request):
    """POST-only: create a new crew owned by the logged-in user (SPEC-06-R01)."""
    if request.method != 'POST':
        return redirect('crew_index')
    name = (request.POST.get('name') or '').strip()
    if not name:
        messages.error(request, 'Crew name is required.')
        return redirect('crew_index')
    if Crew.objects.filter(owner=request.user, name=name).exists():
        messages.error(request, f'You already have a crew named "{name}".')
        return redirect('crew_index')
    crew = Crew.objects.create(owner=request.user, name=name)
    messages.success(request, f'Crew "{crew.name}" created.')
    return redirect('crew_detail', crew_id=crew.id)


@login_required
def crew_detail(request, crew_id):
    """Roster page for a single crew (SPEC-06-R01, R02, R06)."""
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can view this roster.')
        return redirect('crew_index')
    members = crew.crewmember_set.select_related('user').all()
    return render(request, 'accounts/crew_detail.html', {
        'crew': crew,
        'members': members,
        'role_choices': CrewMember.ROLES,
    })


@login_required
def crew_delete(request, crew_id):
    """POST-only: delete a crew and cascade to CrewMember + CrewProjectAdd.

    Per SPEC R7, this does NOT cascade to ProjectMember rows — Django ORM
    cascade only follows the declared FK paths (Crew → CrewMember,
    Crew → CrewProjectAdd). ProjectMember rows have no FK to Crew.
    """
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can delete this crew.')
        return redirect('crew_index')
    if request.method != 'POST':
        return redirect('crew_detail', crew_id=crew.id)
    crew_name = crew.name
    crew.delete()
    messages.success(request, f'Crew "{crew_name}" deleted. Existing project memberships were not affected.')
    return redirect('crew_index')


@login_required
def crew_member_add(request, crew_id):
    """POST-only: add a user (by username/email) OR a pending email to a crew (SPEC-06-R01, R02, R06).

    Form fields:
      - user_or_email (text): looked up case-insensitively against User.email then User.username.
        If neither match AND value contains '@', stored as a pending-email row (D-01).
        Otherwise renders an error.
      - default_role (choice): 'editor' or 'viewer' (D-02).

    D-08: email match is case-insensitive (__iexact) with whitespace strip.
    """
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can manage this roster.')
        return redirect('crew_index')
    if request.method != 'POST':
        return redirect('crew_detail', crew_id=crew.id)

    raw = (request.POST.get('user_or_email') or '').strip()
    default_role = request.POST.get('default_role') or 'editor'
    if default_role not in dict(CrewMember.ROLES):
        default_role = 'editor'
    if not raw:
        messages.error(request, 'Username or email is required.')
        return redirect('crew_detail', crew_id=crew.id)

    user_obj = (
        User.objects.filter(email__iexact=raw).first()
        or User.objects.filter(username__iexact=raw).first()
    )

    try:
        if user_obj is not None:
            if CrewMember.objects.filter(crew=crew, user=user_obj).exists():
                messages.error(request, f'{user_obj.username} is already in "{crew.name}".')
                return redirect('crew_detail', crew_id=crew.id)
            CrewMember.objects.create(crew=crew, user=user_obj, default_role=default_role)
            messages.success(request, f'Added {user_obj.username} to "{crew.name}".')
        elif '@' in raw:
            if CrewMember.objects.filter(crew=crew, email__iexact=raw).exists():
                messages.error(request, f'{raw} is already pending in "{crew.name}".')
                return redirect('crew_detail', crew_id=crew.id)
            CrewMember.objects.create(crew=crew, email=raw, default_role=default_role)
            messages.success(request, f'Added pending member {raw} to "{crew.name}" — will claim on signup.')
        else:
            messages.error(request, f'No user found matching "{raw}". To pre-invite, enter a full email address.')
    except Exception as e:
        # D-15 DB constraints (XOR check, partial uniques) surface as IntegrityError here.
        messages.error(request, f'Could not add member: {e}')
    return redirect('crew_detail', crew_id=crew.id)


@login_required
def crew_member_remove(request, crew_id, member_id):
    """POST-only: delete a single CrewMember row (SPEC-06-R07 no-cascade).

    SPEC R7 is enforced by the data model: CrewMember has no FK from
    ProjectMember, so deleting a CrewMember row never touches a
    ProjectMember row, regardless of whether the underlying user has
    previously been bulk-added to any of the crew's projects.
    """
    crew = get_object_or_404(Crew, id=crew_id)
    if crew.owner != request.user:
        messages.error(request, 'Only the crew owner can manage this roster.')
        return redirect('crew_index')
    member = get_object_or_404(CrewMember, id=member_id, crew=crew)
    if request.method != 'POST':
        return redirect('crew_detail', crew_id=crew.id)
    label = member.user.username if member.user_id else f'{member.email} (pending)'
    member.delete()
    messages.success(
        request,
        f'Removed {label} from "{crew.name}". Their existing project memberships are unaffected — '
        'manage each project separately to remove project access.'
    )
    return redirect('crew_detail', crew_id=crew.id)
```

Do NOT touch `accept_invitation`, `send_invitation_email`, or `Invitation` (SPEC R5).
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "^def crew_index" accounts/views.py && grep -q "^def crew_create" accounts/views.py && grep -q "^def crew_detail" accounts/views.py && grep -q "^def crew_delete" accounts/views.py && grep -q "^def crew_member_add" accounts/views.py && grep -q "^def crew_member_remove" accounts/views.py && grep -q "from planner.models import Crew, CrewMember" accounts/views.py && test "$(git diff -- accounts/views.py | grep -cE '^[+-].*def accept_invitation')" -eq 0 && test "$(git diff -- accounts/views.py | grep -cE '^[+-].*def send_invitation_email')" -eq 0 && python manage.py check 2>&1 | tee /tmp/check_views.out</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "^def crew_index" accounts/views.py` outputs `1`
    - `grep -c "^def crew_create" accounts/views.py` outputs `1`
    - `grep -c "^def crew_detail" accounts/views.py` outputs `1`
    - `grep -c "^def crew_delete" accounts/views.py` outputs `1`
    - `grep -c "^def crew_member_add" accounts/views.py` outputs `1`
    - `grep -c "^def crew_member_remove" accounts/views.py` outputs `1`
    - `grep -c "@login_required" accounts/views.py` is at least 6 higher than pre-edit count (every new view decorated)
    - `grep -q "if crew.owner != request.user" accounts/views.py` exits 0 (owner gate present)
    - `grep -q "from planner.models import Crew, CrewMember" accounts/views.py` exits 0
    - `git diff -- accounts/views.py | grep -cE "^[+-].*def accept_invitation"` outputs `0` (SPEC R5 — accept_invitation untouched)
    - `git diff -- accounts/views.py | grep -cE "^[+-].*def send_invitation_email"` outputs `0` (SPEC R5 — send_invitation_email untouched)
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
Six new views added; existing `accept_invitation` and `send_invitation_email` byte-identical to pre-phase state per SPEC R5.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add 6 crew URL routes to accounts/urls.py</name>
  <files>accounts/urls.py</files>
  <read_first>
    - `accounts/urls.py` (full file — 21 lines)
    - `audiopatch/urls.py:36` (confirms `accounts.urls` is included at root prefix `''` — so `path('crew/', ...)` resolves at `/crew/`)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` §"accounts/urls.py edits"
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` §"Decisions" D-03 routes block (amended 2026-05-14 — canonical URLs are `/crew/`, NOT `/accounts/crew/`)
  </read_first>
  <action>
Append the following 6 URL routes to the existing `urlpatterns` list in `accounts/urls.py`, BEFORE the closing `]`. Mirror the existing path-pattern style (e.g., `path('projects/<int:project_id>/invite/', views.invite_user, name='invite_user')`).

```python
    # Phase 6: Trusted Crew Rosters (D-03 amended — canonical URL prefix is /crew/)
    path('crew/', views.crew_index, name='crew_index'),
    path('crew/new/', views.crew_create, name='crew_create'),
    path('crew/<int:crew_id>/', views.crew_detail, name='crew_detail'),
    path('crew/<int:crew_id>/delete/', views.crew_delete, name='crew_delete'),
    path('crew/<int:crew_id>/members/add/', views.crew_member_add, name='crew_member_add'),
    path('crew/<int:crew_id>/members/<int:member_id>/remove/', views.crew_member_remove, name='crew_member_remove'),
```

`accounts.urls` is included at the root prefix `''` in `audiopatch/urls.py:36`, so existing accounts routes are `/register/`, `/login/`, `/dashboard/`, `/projects/<id>/invite/` etc. Crew routes follow the same pattern: the canonical URL is `/crew/` (per D-03 amended 2026-05-14). No edits to `audiopatch/urls.py` are required — the canonical decision now matches the implementation exactly.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "name='crew_index'" accounts/urls.py && grep -q "name='crew_create'" accounts/urls.py && grep -q "name='crew_detail'" accounts/urls.py && grep -q "name='crew_delete'" accounts/urls.py && grep -q "name='crew_member_add'" accounts/urls.py && grep -q "name='crew_member_remove'" accounts/urls.py && python manage.py shell -c "from django.urls import reverse; r1=reverse('crew_index'); r2=reverse('crew_detail', args=[1]); r3=reverse('crew_member_remove', args=[1,2]); print(r1, r2, r3); assert r1 == '/crew/', r1; assert r2 == '/crew/1/', r2; assert r3 == '/crew/1/members/2/remove/', r3" 2>&1 | tee /tmp/reverse.out</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "name='crew_index'" accounts/urls.py` outputs `1`
    - `grep -c "name='crew_create'" accounts/urls.py` outputs `1`
    - `grep -c "name='crew_detail'" accounts/urls.py` outputs `1`
    - `grep -c "name='crew_delete'" accounts/urls.py` outputs `1`
    - `grep -c "name='crew_member_add'" accounts/urls.py` outputs `1`
    - `grep -c "name='crew_member_remove'" accounts/urls.py` outputs `1`
    - `reverse('crew_index') == '/crew/'` (canonical D-03 amended)
    - `reverse('crew_detail', args=[1]) == '/crew/1/'`
    - `reverse('crew_member_remove', args=[1, 2]) == '/crew/1/members/2/remove/'`
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
Six new URL routes added to `accounts/urls.py`. All names reverse successfully to the canonical `/crew/...` paths (D-03 amended). `python manage.py check` exits 0.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Create templates/accounts/crew_index.html and crew_detail.html</name>
  <files>templates/accounts/crew_index.html, templates/accounts/crew_detail.html</files>
  <read_first>
    - `templates/accounts/dashboard.html:1-90` (head + dark-theme inline CSS — copy `<style>` block conventions verbatim)
    - `templates/accounts/dashboard.html:280-309` (header + .header-right with btn-admin / btn-logout pattern)
    - `templates/accounts/project_invitations.html` (full file — table layout, status-badge / role-badge CSS, empty-state pattern, messages framework rendering)
    - `templates/accounts/invite_user.html:170-220` (messages-block rendering pattern)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` §"templates/accounts/crew_index.html (NEW)" and §"templates/accounts/crew_detail.html (NEW)"
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` §"D-14" — templates live in project-level `templates/accounts/` NOT `accounts/templates/accounts/`
  </read_first>
  <action>
Create two standalone pages (no `{% extends %}`) using the project's dark theme. Both files live at project-level `templates/accounts/` per D-14.

**File 1: `templates/accounts/crew_index.html`**

Standalone page (full `<!DOCTYPE html>`, inline `<style>`) listing the owner's crews. Match the visual language of `dashboard.html` and `project_invitations.html`:
- Dark background (`#1a1a1a` body), white text
- Header bar (`#2a2a2a`) with logo on left, header-right cluster on right with: user info + "Back to Dashboard" link
- `.container { max-width: 1200px; margin: 40px auto; padding: 0 30px; }`
- One `.card` per crew with name, member count, "View / Edit" link to crew_detail, optional "Delete" form
- Empty state when `crews|length == 0`: "You don't have any crews yet. Create one to get started." + create form
- Inline "Create new crew" form: POSTs to `{% url 'crew_create' %}` with `name` text input + submit button
- Messages rendering: `{% if messages %}<div class="messages">{% for message in messages %}<div class="alert alert-{{ message.tags }}">{{ message }}</div>{% endfor %}</div>{% endif %}`

Required template tags / URL references:
- `{% url 'crew_create' %}` (form action for new-crew input)
- `{% url 'crew_detail' crew.id %}` (per-card link)
- `{% url 'crew_delete' crew.id %}` (delete form action; wrap in `<form method="post">` with csrf_token; button onclick="return confirm('Delete crew? Existing project memberships will not be affected.')")
- `{% url 'dashboard' %}` (back link)
- `{{ crew.crewmember_set.count }}` (member count)
- Every POST form includes `{% csrf_token %}`
- Page title: `<title>My Crews — ShowStack</title>`

Minimum 80 lines (head + style + body + container + form + crew list + empty state).

**File 2: `templates/accounts/crew_detail.html`**

Standalone page with a single crew's roster. Same theme as crew_index. Contains:
- Header bar same as crew_index, plus a "Back to My Crews" link in `.header-right` pointing to `{% url 'crew_index' %}`
- `.container` with `<h2>{{ crew.name }}</h2>` + member count
- A `.card` "Add member" form POSTing to `{% url 'crew_member_add' crew.id %}`:
  - Text input `name="user_or_email"` placeholder "username or email"
  - Select `name="default_role"` with options from `{{ role_choices }}` (defaults to editor)
  - Submit button
  - csrf_token
- A `.card` "Members" with a table:
  - Columns: Identity / Default Role / Status / Remove
  - For each `member` in `members`:
    - Identity: `{{ member.user.username }}` if `member.user_id` else `{{ member.email }}`
    - Default role: `<span class="role-badge role-{{ member.default_role }}">{{ member.get_default_role_display }}</span>` (reuse `role-editor` / `role-viewer` CSS from project_invitations.html:179-195 — duplicate the rules inline)
    - Status: "Active" if `member.user_id` else `<span class="status-badge status-pending">pending signup</span>` (per D-05 pending-email pill — orange/amber, copy `.status-pending` rule from project_invitations.html:159-162)
    - Remove: `<form method="post" action="{% url 'crew_member_remove' crew.id member.id %}">{% csrf_token %}<button type="submit" onclick="return confirm('Remove this member from the crew? This removes them from the crew only — their existing project memberships are NOT affected. To remove them from active projects, manage each project separately.')">Remove</button></form>`
  - Empty state: "No members in this crew yet. Use the form above to add one."
- A `.card` "Delete crew" with a destructive button POSTing to `{% url 'crew_delete' crew.id %}` (with confirm dialog: "Delete this crew? Existing project memberships will not be affected.")
- Messages-block render same as crew_index

Minimum 100 lines (head + style + body + 3 cards + table + forms).

Both files use existing CSS class names (`.btn-admin`, `.btn-logout`, `.alert-success`, `.alert-error`, `.role-badge`, `.status-badge`) that appear in dashboard.html / project_invitations.html — copy the rules verbatim into each file's `<style>` block. NO new external CSS files needed.

Verify both files render without `TemplateSyntaxError` by running a one-line render check in the verify step.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && test -f templates/accounts/crew_index.html && test -f templates/accounts/crew_detail.html && test "$(wc -l < templates/accounts/crew_index.html)" -ge 80 && test "$(wc -l < templates/accounts/crew_detail.html)" -ge 100 && grep -q "{% url 'crew_create' %}" templates/accounts/crew_index.html && grep -q "{% url 'crew_detail' crew.id %}" templates/accounts/crew_index.html && grep -q "{% url 'crew_member_add' crew.id %}" templates/accounts/crew_detail.html && grep -q "{% url 'crew_member_remove' crew.id member.id %}" templates/accounts/crew_detail.html && grep -q "{% csrf_token %}" templates/accounts/crew_index.html && grep -q "{% csrf_token %}" templates/accounts/crew_detail.html && grep -q "pending signup" templates/accounts/crew_detail.html && python manage.py shell -c "from django.template.loader import render_to_string; from django.contrib.auth import get_user_model; from planner.models import Crew; U=get_user_model(); u,_=U.objects.get_or_create(username='__tmpl_test__', defaults={'email':'t@t.t'}); c=Crew.objects.create(owner=u, name='__tmpl_test_crew__'); from unittest.mock import MagicMock; req=MagicMock(); req.user=u; print('index_ok' if render_to_string('accounts/crew_index.html', {'crews':[c], 'user':u, 'messages':[]}) else 'FAIL'); print('detail_ok' if render_to_string('accounts/crew_detail.html', {'crew':c, 'members':[], 'role_choices':[('editor','Editor'),('viewer','Viewer')], 'user':u, 'messages':[]}) else 'FAIL'); c.delete(); u.delete()" 2>&1 | tee /tmp/render.out | grep -q "index_ok" && grep -q "detail_ok" /tmp/render.out</automated>
  </verify>
  <acceptance_criteria>
    - `test -f templates/accounts/crew_index.html` exits 0
    - `test -f templates/accounts/crew_detail.html` exits 0
    - `wc -l < templates/accounts/crew_index.html` outputs >= 80
    - `wc -l < templates/accounts/crew_detail.html` outputs >= 100
    - `grep -q "{% url 'crew_create' %}" templates/accounts/crew_index.html` exits 0
    - `grep -q "{% url 'crew_detail' crew.id %}" templates/accounts/crew_index.html` exits 0
    - `grep -q "{% url 'crew_delete' crew.id %}" templates/accounts/crew_index.html` exits 0
    - `grep -q "{% url 'crew_member_add' crew.id %}" templates/accounts/crew_detail.html` exits 0
    - `grep -q "{% url 'crew_member_remove' crew.id member.id %}" templates/accounts/crew_detail.html` exits 0
    - `grep -c "{% csrf_token %}" templates/accounts/crew_index.html` >= 1
    - `grep -c "{% csrf_token %}" templates/accounts/crew_detail.html` >= 3 (add-member + remove-member + delete-crew)
    - `grep -q "pending signup" templates/accounts/crew_detail.html` exits 0 (D-05 pending-email pill)
    - `render_to_string('accounts/crew_index.html', ...)` returns non-empty string without exception
    - `render_to_string('accounts/crew_detail.html', ...)` returns non-empty string without exception
  </acceptance_criteria>
  <done>
Both templates exist at project-level `templates/accounts/`, render without TemplateSyntaxError or NoReverseMatch, include all required URL references and CSRF tokens, and surface the "pending signup" badge for placeholder members per D-05.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → Django view | Untrusted POST inputs (user_or_email text, default_role) cross here on add-member |
| Django view → DB | Owner-gate check; DB constraints from Plan 01 are the perimeter for malformed CrewMember rows |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-03-01 | Spoofing | Non-owner views/edits another owner's crew | mitigate | `if crew.owner != request.user` gate on every view; redirect to crew_index with error |
| T-06-03-02 | Tampering | Cross-site request forgery on POST endpoints | mitigate | Every POST form includes `{% csrf_token %}`; Django's CsrfViewMiddleware enforces |
| T-06-03-03 | Tampering | Add-member with invalid default_role injects unknown value | mitigate | View validates `default_role in dict(CrewMember.ROLES)`, falls back to 'editor' |
| T-06-03-04 | Tampering | XSS via user-supplied crew name or email in templates | mitigate | Django template autoescape on (default); no `{% safe %}` filter used on user input |
| T-06-03-05 | Information Disclosure | Cross-owner roster enumeration via /crew/<id>/ | mitigate | `get_object_or_404(Crew, id=crew_id)` then `if crew.owner != request.user` redirect — no leak of crew existence (404 vs redirect leak only confirms id-exists; acceptable for owner-scoped feature) |
| T-06-03-06 | Tampering | Remove-member click triggers cascade delete to ProjectMember | mitigate | Data model enforces no-cascade (no FK from ProjectMember to CrewMember); covered by Plan 07 regression test |
| T-06-03-07 | Tampering | Edits to accept_invitation or send_invitation_email | mitigate | `git diff` acceptance criterion verifies zero matches; SPEC R5 enforced |
</threat_model>

<verification>
- `python manage.py check` exits 0
- All 6 URL names reverse successfully — `reverse('crew_index') == '/crew/'`, `reverse('crew_detail', args=[1]) == '/crew/1/'`, etc. (D-03 amended)
- Both templates render via `render_to_string` without TemplateSyntaxError
- `git diff -- accounts/views.py` shows no edits to `accept_invitation` or `send_invitation_email` (SPEC R5)
- Every new view has `@login_required` + owner gate
</verification>

<success_criteria>
- Owner logged in, visits crew index at `/crew/`, sees empty state if no crews
- Owner creates "Concert team" via the inline form, lands on its detail page at `/crew/<id>/`
- Owner adds Mike (via username "mike") and Sarah (via email "sarah@example.com") with default_role=editor; both appear on roster
- Owner adds pending email "newbie@example.com" → row shows "pending signup" badge
- Owner removes Sarah → row disappears, success flash mentions no-cascade to project memberships
- Owner tries to view another owner's `/crew/<id>/` → redirected to `/crew/` with error flash
</success_criteria>

<output>
After completion, create `.planning/phases/06-trusted-crew-rosters/06-03-SUMMARY.md` capturing: line numbers of inserted views, URL list, template file sizes, render-test output, and confirmation that accept_invitation / send_invitation_email diffs are zero.
</output>
