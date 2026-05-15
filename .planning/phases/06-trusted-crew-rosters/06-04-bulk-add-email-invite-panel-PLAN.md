---
phase: 06-trusted-crew-rosters
plan: 04
type: execute
wave: 3
depends_on:
  - 06-01
  - 06-03
files_modified:
  - accounts/views.py
  - accounts/urls.py
  - templates/accounts/invite_user.html
autonomous: true
requirements:
  - SPEC-06-R03
  - SPEC-06-R04
  - SPEC-06-R05
  - SPEC-06-R08
user_setup: []
must_haves:
  truths:
    - "Owner POSTs to /projects/<id>/invite/add-crew/<crew_id>/ creates ProjectMember rows for every resolved-user crew member not already a member"
    - "Bulk-add writes a single CrewProjectAdd(crew, project) row (idempotent via get_or_create) so the Plan 05 auto-claim hook knows which projects to materialize for new registrations"
    - "Bulk-add sends exactly one confirmation email per NEW ProjectMember row (skipped/already-member rows trigger no email)"
    - "Bulk-add returns flash message 'Added N members from {crew}; M were already on this project.'"
    - "Email-send failure on any single recipient is logged + swallowed (D-10) and does NOT roll back the bulk-add"
    - "Email contains no accept_url token (SPEC R4) — direct link via reverse('set_project', args=[project.id])"
    - "ProjectMember rows are created with .save() (not bulk_create) so auto_now_add fires for invited_at (Pitfall 2)"
    - "Non-project-owner POST is rejected with messages.error + redirect to dashboard"
    - "Non-crew-owner POST (project owner != crew owner) is rejected — get_object_or_404(Crew, id=crew_id, owner=request.user)"
    - "User in two of owner's crews bulk-added to same project gets exactly ONE ProjectMember row (SPEC R8 dedupe)"
    - "templates/accounts/invite_user.html receives ADDITIVE 'Add your crew' panel below the existing form — no edits to existing form markup (SPEC R5)"
    - "Existing invite_user view passes owner_crews context to template (additive context update — SPEC R5 preserved)"
  artifacts:
    - path: "accounts/views.py"
      provides: "bulk_add_crew view + send_crew_added_email helper + owner_crews context injection in invite_user"
      contains: "def bulk_add_crew(request, project_id, crew_id)"
    - path: "accounts/urls.py"
      provides: "POST /projects/<int:project_id>/invite/add-crew/<int:crew_id>/ route"
      contains: "name='bulk_add_crew'"
    - path: "templates/accounts/invite_user.html"
      provides: "Additive 'Add your crew' panel below existing form"
      contains: "Add this crew"
  key_links:
    - from: "templates/accounts/invite_user.html"
      to: "accounts/views.py:bulk_add_crew"
      via: "url tag bulk_add_crew with project.id and crew.id"
      pattern: "bulk_add_crew"
    - from: "accounts/views.py:bulk_add_crew"
      to: "planner.models.CrewProjectAdd"
      via: "get_or_create(crew=crew, project=project)"
      pattern: "CrewProjectAdd\\.objects\\.get_or_create"
    - from: "accounts/views.py:bulk_add_crew"
      to: "accounts/views.py:send_crew_added_email"
      via: "per-row call wrapped in try/except (D-10 log + swallow)"
      pattern: "send_crew_added_email"
---

<objective>
Build the bulk-add endpoint that lets a project owner add an entire crew to a project in one POST: creates `ProjectMember` rows (skip-existing per SPEC R8), records `CrewProjectAdd` (D-09), sends per-row confirmation emails (SPEC R4 + D-10 log-and-swallow), and surfaces a flash banner with the count. Also adds the additive "Add your crew" panel to `invite_user.html` (SPEC R5 — additivity-only).

Purpose: This is the user-visible heart of Phase 6. Closes SPEC R3 (bulk-add), R4 (confirmation email), R5 (additive panel), R8 (dedupe).
Output: One new view (`bulk_add_crew`), one new email helper (`send_crew_added_email`), context injection in existing `invite_user`, one new URL route, additive template markup.
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
@templates/accounts/invite_user.html

<interfaces>
<!-- Existing patterns the executor MUST mirror verbatim. -->

From accounts/views.py:122-131 (invite_user — owner gate analog the bulk-add view duplicates):

    @login_required
    def invite_user(request, project_id):
        project = get_object_or_404(Project, id=project_id)
        if project.owner != request.user:
            messages.error(request, 'Only the project owner can invite users.')
            return redirect('dashboard')

From accounts/views.py:241-290 (send_invitation_email — DO NOT MODIFY; pattern reference for the new email helper). Note this function uses `raise` on Resend error; Phase 6's new helper does NOT re-raise per D-10.

From accounts/views.py:571-591 (send_access_approved_email — the log-and-swallow analog Phase 6 must mirror per D-10):

    def send_access_approved_email(access_req, request):
        import resend, os
        resend.api_key = os.environ.get('RESEND_API_KEY')
        ...
        try:
            resend.Emails.send({...})
        except Exception as e:
            print(f"Approval email error: {e}")
        # NO raise — log + swallow

From accounts/views.py:497-502 (idempotent ProjectMember create pattern):

    ProjectMember.objects.get_or_create(
        project=project,
        user=access_req.requester,
        defaults={'role': role, 'invited_by': request.user}
    )

URL name `set_project` (verified at accounts/urls.py:13) — used for the email body's "Open project" link:

    path('set-project/<int:project_id>/', views.set_project, name='set_project'),

InviteUserForm constructor signature (verified at accounts/invitation_forms.py:23):

    def __init__(self, *args, project=None, invited_by=None, **kwargs):

Existing invite_user view instantiates it as `InviteUserForm(project=project, invited_by=request.user)` for GET and `InviteUserForm(request.POST, project=project, invited_by=request.user)` for POST. The Task 3 template render-test MUST instantiate a real form (not pass `None`) because `invite_user.html` unconditionally renders `{{ form.role }}` — passing `None` raises VariableDoesNotExist / AttributeError when Django attempts to call the Select widget render with a None object.

Queries this plan needs (from planner/models.py):
- `crew.crewmember_set.filter(user__isnull=False).select_related('user')` — resolved-user members; pending-email rows skipped here, they materialize via Plan 05's auto-claim hook.
- `ProjectMember.objects.filter(project=project, user_id__in=[...]).values_list('user_id', flat=True)` — upfront dedupe query (SPEC R8).
- `ProjectMember.objects.create(project=project, user=u, role=default_role, invited_by=request.user)` — uses .save() per Pitfall 2 so auto_now_add fires for invited_at.
- `CrewProjectAdd.objects.get_or_create(crew=crew, project=project)` — D-09 link table; idempotent.

Existing invite_user view signature: `def invite_user(request, project_id)` at accounts/views.py:122. Current context dict at line ~155 contains `{'form': form, 'project': project}`. Phase 6 ADDS `owner_crews` key — does NOT replace existing keys (SPEC R5 additivity).

Existing invite_user.html insertion point: the existing `.card` closes around line 219; insertion is AFTER that closing div and BEFORE the closing div of `.container` at line 220. Executor MUST read the file first to confirm exact lines; do NOT trust line numbers blindly.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add bulk_add_crew view + send_crew_added_email helper + inject owner_crews into invite_user</name>
  <files>accounts/views.py</files>
  <read_first>
    - `accounts/views.py:122-157` (invite_user — must inject `owner_crews` into its context dict additively)
    - `accounts/views.py:241-290` (send_invitation_email — DO NOT modify; pattern reference)
    - `accounts/views.py:571-591` (send_access_approved_email — log-and-swallow pattern Phase 6 mirrors per D-10)
    - `accounts/views.py:478-547` (project_access_requests — owner-gate + ProjectMember get_or_create idempotency)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` Decisions D-05 (panel layout), D-06 (single-click + flash), D-09 (CrewProjectAdd), D-10 (log + swallow)
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` Pattern 3 (bulk-add view), Pattern 4 (confirmation email), Pitfall 2 (bulk_create + auto_now_add), Pitfall 8 (email failures)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` accounts/views.py (+bulk_add_crew) and (+send_crew_added_email) sections
  </read_first>
  <action>
**Step A:** Add a module-level logger near the top of `accounts/views.py` (if not already present):

    import logging
    logger = logging.getLogger(__name__)

Also extend the existing `from planner.models import Crew, CrewMember` line from Plan 03 to include `CrewProjectAdd`:

    from planner.models import Crew, CrewMember, CrewProjectAdd

**Step B:** Append the following code to `accounts/views.py` AFTER the existing `crew_member_remove` view (added in Plan 03):

```
def send_crew_added_email(project_member, request):
    """Inform a user they have been added to a project via crew bulk-add (SPEC-06-R04).

    NO accept_url token per SPEC R4 — access is already active. The 'Open project'
    button reverses to set_project (the canonical land-inside-project URL used
    elsewhere in the codebase).

    D-10: log + swallow exceptions. The bulk-add contract is 'ProjectMember rows
    exist' — one bad email must not undo a successful crew-add. Resend dashboard
    surfaces per-recipient delivery failures. Mirrors send_access_approved_email
    (NOT send_invitation_email which re-raises).
    """
    import resend
    import os
    from django.urls import reverse

    resend.api_key = os.environ.get('RESEND_API_KEY')
    project_url = request.build_absolute_uri(
        reverse('set_project', args=[project_member.project.id])
    )
    owner = project_member.project.owner
    owner_label = owner.get_full_name() or owner.username

    subject = (
        f"{owner_label} added you to "
        f"{project_member.project.name} on ShowStack"
    )
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
        print(f"Crew-added email sent to {project_member.user.email}")
    except Exception as e:
        # D-10: log + swallow — do NOT re-raise.
        print(f"Crew-added email error: {e}")


@login_required
def bulk_add_crew(request, project_id, crew_id):
    """Bulk-add an entire crew to a project (SPEC-06-R03, R04, R05, R08; D-06, D-09, D-10).

    POST-only. Creates ProjectMember rows for every CrewMember with a User FK
    that is not already a member of the project. Sends one confirmation email
    per new row. Records a CrewProjectAdd row so the Plan 05 auto-claim hook
    can materialize ProjectMember rows for future registrations matching
    pending-email CrewMember rows.

    Per Pitfall 2: uses .save() (via ProjectMember.objects.create) rather than
    bulk_create so auto_now_add fires for invited_at.
    """
    project = get_object_or_404(Project, id=project_id)
    # Mirror accounts/views.py:128-131 — project owner gate.
    if project.owner != request.user:
        messages.error(request, 'Only the project owner can add a crew.')
        return redirect('dashboard')

    crew = get_object_or_404(Crew, id=crew_id, owner=request.user)

    if request.method != 'POST':
        return redirect('invite_user', project_id=project.id)

    # Resolve crew members with a User FK. Pending-email rows (user=NULL) are
    # skipped here; they materialize via the auto-claim hook in register()
    # (Plan 05) once the email-holder signs up.
    resolved = list(
        crew.crewmember_set.filter(user__isnull=False).select_related('user')
    )

    # SPEC R8: single upfront dedupe query.
    existing_user_ids = set(
        ProjectMember.objects.filter(
            project=project,
            user_id__in=[m.user_id for m in resolved],
        ).values_list('user_id', flat=True)
    )

    to_add = [m for m in resolved if m.user_id not in existing_user_ids]
    already = len(resolved) - len(to_add)

    # Pitfall 2: .save() loop (via .create) so auto_now_add fires for invited_at.
    # Crews are 1-10 members per SPEC Constraint — sync is fine.
    new_rows = []
    for m in to_add:
        pm = ProjectMember.objects.create(
            project=project,
            user=m.user,
            role=m.default_role,
            invited_by=request.user,
        )
        new_rows.append(pm)

    # D-09: record bulk-add so the auto-claim hook (Plan 05) knows which
    # projects to materialize for newly-registered crew members.
    CrewProjectAdd.objects.get_or_create(crew=crew, project=project)

    # D-10: log + swallow email failures (per-recipient, defensive).
    for pm in new_rows:
        try:
            send_crew_added_email(pm, request)
        except Exception:
            logger.exception(
                "Crew-added email failed for %s",
                getattr(pm.user, 'email', '<unknown>'),
            )

    messages.success(
        request,
        f"Added {len(to_add)} members from {crew.name}; "
        f"{already} were already on this project."
    )
    return redirect('invite_user', project_id=project.id)
```

**Step C:** Update the EXISTING `invite_user` view (around accounts/views.py:122-157) to inject `owner_crews` into its context dict — additively. Do NOT touch any other line of the function body.

Locate the `render(request, 'accounts/invite_user.html', ...)` call near the end of `invite_user` and insert this block immediately BEFORE it:

```
    # Phase 6: build owner_crews annotated for the additive 'Add your crew' panel.
    owner_crews_qs = (
        Crew.objects.filter(owner=request.user)
        .prefetch_related('crewmember_set__user')
        .order_by('name')
    )
    existing_member_ids = set(
        ProjectMember.objects.filter(project=project)
        .values_list('user_id', flat=True)
    )
    owner_crews = []
    for crew_obj in owner_crews_qs:
        members_payload = []
        eligible_count = 0
        for cm in crew_obj.crewmember_set.all():
            if cm.user_id is None:
                members_payload.append({
                    'label': cm.email,
                    'is_already_member': False,
                    'is_pending': True,
                })
                # Pending-email rows do not count toward eligible_count —
                # they materialize via the auto-claim hook (Plan 05) on register.
            else:
                is_member = cm.user_id in existing_member_ids
                members_payload.append({
                    'label': cm.user.get_full_name() or cm.user.username,
                    'is_already_member': is_member,
                    'is_pending': False,
                })
                if not is_member:
                    eligible_count += 1
        owner_crews.append({
            'id': crew_obj.id,
            'name': crew_obj.name,
            'eligible_count': eligible_count,
            'member_display': members_payload,
        })
```

Then change the existing `render(...)` call to ADD the `owner_crews` key alongside the existing keys (do NOT remove `form` or `project`):

```
    return render(request, 'accounts/invite_user.html', {
        'form': form,
        'project': project,
        'owner_crews': owner_crews,
    })
```

If the existing render uses an explicit `context = {...}` dict, add the new key to that dict instead.

Do NOT touch `accept_invitation`, `send_invitation_email`, or the existing form-submit branch logic in `invite_user`. Context injection is the only `invite_user` change.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "^def send_crew_added_email" accounts/views.py && grep -q "^def bulk_add_crew" accounts/views.py && grep -q "from planner.models import Crew, CrewMember, CrewProjectAdd" accounts/views.py && grep -q "logger = logging.getLogger" accounts/views.py && grep -q "CrewProjectAdd.objects.get_or_create(crew=crew, project=project)" accounts/views.py && grep -q "ProjectMember.objects.create" accounts/views.py && grep -q "owner_crews" accounts/views.py && grep -q "logger.exception" accounts/views.py && grep -q "reverse('set_project'" accounts/views.py && test "$(git diff -- accounts/views.py | grep -cE '^[+-].*def accept_invitation')" -eq 0 && test "$(git diff -- accounts/views.py | grep -cE '^[+-].*def send_invitation_email')" -eq 0 && python manage.py check 2>&1 | tee /tmp/check_bulk.out</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "^def send_crew_added_email" accounts/views.py` outputs `1`
    - `grep -c "^def bulk_add_crew" accounts/views.py` outputs `1`
    - `grep -q "from planner.models import Crew, CrewMember, CrewProjectAdd" accounts/views.py` exits 0
    - `grep -q "logger = logging.getLogger" accounts/views.py` exits 0
    - `grep -q "if project.owner != request.user" accounts/views.py` exits 0
    - `grep -q "CrewProjectAdd.objects.get_or_create(crew=crew, project=project)" accounts/views.py` exits 0 (D-09)
    - `grep -q "ProjectMember.objects.create" accounts/views.py` exits 0 (Pitfall 2)
    - `grep -q "owner_crews" accounts/views.py` exits 0 (additive context in invite_user — SPEC R5)
    - `grep -q "logger.exception" accounts/views.py` exits 0 (D-10)
    - `grep -q "send_crew_added_email" accounts/views.py` exits 0 (helper invoked from bulk_add_crew)
    - `grep -q "reverse('set_project'" accounts/views.py` exits 0 (no token; direct project link per SPEC R4)
    - `git diff -- accounts/views.py | grep -cE "^[+-].*def accept_invitation"` outputs `0` (SPEC R5)
    - `git diff -- accounts/views.py | grep -cE "^[+-].*def send_invitation_email"` outputs `0` (SPEC R5)
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
`bulk_add_crew` view and `send_crew_added_email` helper added. `invite_user` view has `owner_crews` injected additively (`form` and `project` keys still present). `accept_invitation` and `send_invitation_email` are byte-identical to pre-phase state per SPEC R5.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add bulk_add_crew URL route to accounts/urls.py</name>
  <files>accounts/urls.py</files>
  <read_first>
    - `accounts/urls.py` (full file)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` Claude's Discretion: Bulk-add URL shape
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` accounts/urls.py edits section
  </read_first>
  <action>
Append this single URL route to `urlpatterns` in `accounts/urls.py`, after the 6 crew routes added in Plan 03 and before the closing `]`:

    path('projects/<int:project_id>/invite/add-crew/<int:crew_id>/', views.bulk_add_crew, name='bulk_add_crew'),

This route lives semantically alongside the existing `projects/<int:project_id>/invite/` route at accounts/urls.py:9.
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "name='bulk_add_crew'" accounts/urls.py && python manage.py shell -c "from django.urls import reverse; out=reverse('bulk_add_crew', args=[1, 2]); print(out); assert out.endswith('/projects/1/invite/add-crew/2/'), out" 2>&1 | tee /tmp/reverse_bulk.out && python manage.py check 2>&1</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "name='bulk_add_crew'" accounts/urls.py` outputs `1`
    - `python manage.py shell -c "from django.urls import reverse; print(reverse('bulk_add_crew', args=[1, 2]))"` prints a URL ending in `/projects/1/invite/add-crew/2/`
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
URL route registered. `reverse('bulk_add_crew', args=[1, 2])` resolves without NoReverseMatch.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Add additive 'Add your crew' panel to templates/accounts/invite_user.html</name>
  <files>templates/accounts/invite_user.html</files>
  <read_first>
    - `templates/accounts/invite_user.html` (full file — to locate the exact line where the existing `.card` div ends and the `.container` div ends; do NOT trust the line number blindly)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` Decisions D-05 (stacked layout, pending-signup pill, greyed/struck for already-members)
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` Code Example 4 (additive panel HTML)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` templates/accounts/invite_user.html edit section
  </read_first>
  <action>
**SPEC R5 — strictly additive.** Do NOT rewrite or modify ANY existing line of `invite_user.html`. INSERT the new panel AFTER the closing `</div>` of the existing `.card` (which closes around line 219) and BEFORE the closing `</div>` of `.container` (which closes around line 220). The exact line numbers must be re-verified by reading the current file first.

Insert this block in that exact location:

```
    {# Phase 6 (SPEC-06-R03, R05): additive Add your crew panel. No edits to the existing form above. #}
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
```

The new markup inherits the existing `.card` / `.btn-primary` styles defined in `invite_user.html:51-138` — NO new CSS needed. The `{% if owner_crews %}` outer gate means the page renders byte-identically when an owner has no crews (i.e., until Plan 03 starts being used).

After inserting, verify by:
- diffing the file to confirm only `+` lines were added (no `-` lines aside from a trailing-whitespace adjustment if any)
- rendering the template with a stub context and confirming no TemplateSyntaxError or NoReverseMatch
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "Phase 6" templates/accounts/invite_user.html && grep -q "Add this crew" templates/accounts/invite_user.html && grep -q "{% url 'bulk_add_crew' project.id crew.id %}" templates/accounts/invite_user.html && grep -q "pending signup" templates/accounts/invite_user.html && grep -q "owner_crews" templates/accounts/invite_user.html && test "$(git diff -- templates/accounts/invite_user.html | grep -cE '^-[^-]')" -le 1 && python manage.py shell -c "from django.template.loader import render_to_string; from django.contrib.auth import get_user_model; from planner.models import Project; from accounts.invitation_forms import InviteUserForm; U=get_user_model(); u,_=U.objects.get_or_create(username='__tmpl_inv_test__', defaults={'email':'t@t.t'}); p=Project.objects.create(name='__tmpl_inv_test__', owner=u); f=InviteUserForm(project=p, invited_by=u); print('ok' if render_to_string('accounts/invite_user.html', {'form':f,'project':p,'owner_crews':[],'user':u,'messages':[]}) else 'FAIL'); p.delete(); u.delete()" 2>&1 | tee /tmp/render_inv.out | grep -q "ok"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "Phase 6" templates/accounts/invite_user.html` exits 0 (insertion marker present)
    - `grep -q "Add this crew" templates/accounts/invite_user.html` exits 0
    - `grep -q "{% url 'bulk_add_crew' project.id crew.id %}" templates/accounts/invite_user.html` exits 0
    - `grep -q "pending signup" templates/accounts/invite_user.html` exits 0 (D-05 pending pill)
    - `grep -q "text-decoration:line-through" templates/accounts/invite_user.html` exits 0 (D-05 already-member greyed/struck)
    - `grep -q "owner_crews" templates/accounts/invite_user.html` exits 0
    - `git diff -- templates/accounts/invite_user.html | grep -cE "^-[^-]"` outputs `0` or `1` (SPEC R5 additivity — no deletions except possible trailing whitespace)
    - `render_to_string('accounts/invite_user.html', {'form':<InviteUserForm instance>,'project':<obj>,'owner_crews':[]})` returns non-empty string (empty owner_crews case still renders, real form instance because invite_user.html unconditionally references `{{ form.role }}` which raises on None)
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
Additive panel inserted in `invite_user.html`. No existing lines modified. Template renders cleanly when `owner_crews` is empty (byte-identical UX to pre-phase) AND when populated.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser POST → bulk_add_crew | Untrusted: project_id + crew_id from URL; owner gate is the perimeter |
| bulk_add_crew → Resend SDK | Outbound SaaS; D-10 dictates per-recipient try/except so one bad email cannot poison the bulk operation |
| invite_user view → invite_user.html | Trusted server-side render; owner_crews context built from owner-scoped queries only |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-04-01 | Elevation of Privilege | Non-project-owner POSTs bulk-add | mitigate | `if project.owner != request.user` early-return mirrors accounts/views.py:129 |
| T-06-04-02 | Elevation of Privilege | Project owner uses ANOTHER owner's crew | mitigate | `get_object_or_404(Crew, id=crew_id, owner=request.user)` constrains crew lookup to the requesting user's owned crews |
| T-06-04-03 | Tampering | CSRF on bulk-add endpoint | mitigate | Standard Django CsrfViewMiddleware + `{% csrf_token %}` in the panel form |
| T-06-04-04 | Tampering | Race produces duplicate ProjectMember row | mitigate | `ProjectMember.unique_together = ('project', 'user')` (planner/models.py:711) is the DB-level safety net; upfront dedupe query is the application-layer prevention (SPEC R8) |
| T-06-04-05 | Denial of Service | Mega-crew (50+ members) triggers email storm | accept | SPEC Constraint: crews are 1-10 members; per-row sync send acceptable; future async migration is documented as out of scope |
| T-06-04-06 | Information Disclosure | Email body leaks unrelated project metadata | mitigate | Email body inlines only owner_label + project.name + role + set_project URL — no other project fields exposed |
| T-06-04-07 | Tampering | Email-send failure rolls back ProjectMember rows mid-bulk | mitigate | D-10 log + swallow; bulk-add commits ProjectMember rows before email loop; Resend dashboard surfaces failures |
| T-06-04-08 | Tampering | Edits to Invitation/accept_invitation/send_invitation_email violate SPEC R5 | mitigate | `git diff` acceptance criteria in Task 1 + Task 3 verify zero matches |
| T-06-04-09 | Repudiation | Cannot tell which crew added which user to which project | mitigate | CrewProjectAdd row (D-09) records the crew→project link with auto_now_add timestamp; ProjectMember.invited_by + invited_at record the per-row audit (SPEC R3 audit reuse) |
</threat_model>

<verification>
- `python manage.py check` exits 0
- `reverse('bulk_add_crew', args=[1, 2])` resolves to URL ending in `/projects/1/invite/add-crew/2/`
- `invite_user.html` renders successfully with `owner_crews=[]` (existing flow preserved) AND with a populated `owner_crews` list, when passed an instantiated `InviteUserForm` (not `None` — the template unconditionally references `{{ form.role }}`)
- `git diff -- accounts/views.py` and `git diff -- templates/accounts/invite_user.html` show ZERO changes to `accept_invitation`, `send_invitation_email`, or the existing invite form markup (SPEC R5)
- All Task 1 + Task 2 + Task 3 grep acceptance criteria pass
</verification>

<success_criteria>
- Owner with a 3-member "Concert team" clicks "Add this crew" on a fresh project: 3 ProjectMember rows created (role=editor, invited_by=owner, invited_at populated), 1 CrewProjectAdd row created, 3 emails attempted, flash reads "Added 3 members from Concert team; 0 were already on this project."
- Re-clicking "Add this crew" on the same project: 0 new ProjectMember rows, 0 new CrewProjectAdd row (get_or_create idempotent), 0 emails, flash reads "Added 0 members from Concert team; 3 were already on this project."
- User in both "Concert team" and "Corporate team", bulk-add Concert (3 rows) then bulk-add Corporate (shared user already a member): exactly 1 ProjectMember row for that user, no IntegrityError.
- Resend API simulated failure on row #2 of a 3-row bulk-add: still creates all 3 ProjectMember rows, logs the failed send, flash still reads "Added 3 members..."
- Non-owner cannot bulk-add: redirected to dashboard with error flash.
</success_criteria>

<output>
After completion, create `.planning/phases/06-trusted-crew-rosters/06-04-SUMMARY.md` capturing: bulk_add_crew + send_crew_added_email line numbers, owner_crews context shape excerpt, invite_user.html diff stats (additive only), reverse('bulk_add_crew') output, and confirmation that accept_invitation / send_invitation_email diffs remain zero.
</output>
