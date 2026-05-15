---
phase: 06-trusted-crew-rosters
plan: 05
type: execute
wave: 3
depends_on:
  - 06-01
files_modified:
  - planner/crew.py
  - accounts/views.py
autonomous: true
requirements:
  - SPEC-06-R06
user_setup: []
must_haves:
  truths:
    - "planner/crew.py exists with claim_pending_crew_memberships(user) helper (D-07, D-13)"
    - "Helper finds CrewMember rows with user__isnull=True AND email__iexact matching the new user's stripped email (D-08)"
    - "Helper rebinds each match in place: email=None, user=new_user, save(update_fields=['user','email']) — preserves default_role + added_at (D-01)"
    - "Helper materializes ProjectMember rows for every CrewProjectAdd of the matching crew via get_or_create (idempotent)"
    - "Helper returns the list of newly-created ProjectMember rows so the caller can send confirmation emails"
    - "Helper uses NO Django signals (D-07)"
    - "accounts/views.py:register() wraps form.save() + claim helper call in a single transaction.atomic() (D-11)"
    - "Confirmation emails for materialized ProjectMember rows are sent AFTER the atomic block exits (per D-10/D-11 — Resend hiccup must not roll back the User row)"
    - "Plus-aliased and gmail dot-stripped emails are NOT normalized (D-08) — case-insensitive + whitespace strip only"
  artifacts:
    - path: "planner/crew.py"
      provides: "claim_pending_crew_memberships(user) function"
      contains: "def claim_pending_crew_memberships"
      min_lines: 50
    - path: "accounts/views.py"
      provides: "register() view body wraps form.save + claim helper in transaction.atomic"
      contains: "claim_pending_crew_memberships"
  key_links:
    - from: "accounts/views.py:register"
      to: "planner/crew.py:claim_pending_crew_memberships"
      via: "from planner.crew import claim_pending_crew_memberships"
      pattern: "from planner.crew import"
    - from: "planner/crew.py:claim_pending_crew_memberships"
      to: "planner.models.CrewProjectAdd"
      via: "CrewProjectAdd.objects.filter(crew=cm.crew)"
      pattern: "CrewProjectAdd\\.objects\\.filter"
---

<objective>
Build the auto-claim hook that links a newly-registered user to any pending CrewMember rows whose email matches theirs, and materializes ProjectMember rows for every project the crew has been bulk-added to. Wrap the registration flow in a transaction.atomic per D-11.

Purpose: Closes SPEC R6 (pre-onboarding placeholder + auto-claim on register). Owners can add unregistered emails to crews; when those users sign up, they auto-join all bulk-added projects without owner intervention.
Output: New module `planner/crew.py` (helper function + module docstring + logger). Two-line edit to `accounts/views.py:register()` (import + atomic wrapper around form.save and claim call) + post-atomic email loop.
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

<interfaces>
<!-- Existing patterns the executor MUST mirror. -->

From accounts/views.py:16-37 (register — the existing function body to wrap):

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

From accounts/views.py:497-502 (idempotent ProjectMember create — pattern Plan 05 reuses):

    ProjectMember.objects.get_or_create(
        project=project,
        user=access_req.requester,
        defaults={'role': role, 'invited_by': request.user}
    )

From planner/utils/yamaha_export.py (existing helper-module convention — planner/crew.py mirrors this shape: module docstring, top-level imports, pure functions, no class wrapper).

`send_crew_added_email` lives in `accounts/views.py` (added in Plan 04). The post-atomic email loop in `register()` imports it locally to avoid a circular-import surface with `planner.crew`.

D-08 email match: case-insensitive via `__iexact` plus explicit `.strip()` on the user-side value. NO gmail dot normalization, NO `+alias` collapsing.

D-11 atomicity: `form.save()` AND `claim_pending_crew_memberships(user)` BOTH inside `transaction.atomic()`. If the claim raises, the User row rolls back so the user can re-register cleanly. The email loop runs AFTER the atomic block exits — per D-10 a Resend hiccup must not roll back the user account.

`CrewProjectAdd` is populated by Plan 04's `bulk_add_crew` view (idempotent via `get_or_create`). This plan READS from it.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Create planner/crew.py with claim_pending_crew_memberships helper</name>
  <files>planner/crew.py</files>
  <read_first>
    - `planner/utils/yamaha_export.py:1-35` (module-shape convention — top-level imports, module docstring, pure functions)
    - `accounts/views.py:181-238` (accept_invitation — pattern reference for case-insensitive email match; do NOT modify per SPEC R5)
    - `accounts/views.py:497-502` (ProjectMember.get_or_create idempotency pattern)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` Decisions D-07 (location), D-08 (iexact + strip), D-09 (CrewProjectAdd), D-10 (log + swallow), D-11 (atomic), D-13 (planner/crew.py location)
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` Pattern 5 (auto-claim hook)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` planner/crew.py section
  </read_first>
  <action>
Create a brand-new file `planner/crew.py` (NOT `accounts/crew_claim.py` per D-13 — models live in planner.models, the helper lives next to them). Write the full file verbatim:

```
"""Auto-claim helper: rebind pending CrewMember rows on user registration.

When a new user registers, this helper:
  1. Finds CrewMember rows with user__isnull=True whose email matches the new
     user's email case-insensitively (D-08: __iexact + explicit .strip()).
  2. UPDATES each match in place — sets email=None, user=<new user>, save with
     update_fields=['user', 'email']. Preserves default_role + added_at
     (D-01 — single-table polymorphic rebind, no row delete+recreate).
  3. For every CrewProjectAdd of the matched crew, creates a ProjectMember
     row for the new user via get_or_create (idempotent). Skips rows that
     already exist (e.g. the user was previously added directly).
  4. Returns the list of newly-created ProjectMember rows so the caller can
     send confirmation emails (SPEC R4 / R6).

Called from accounts/views.py:register() per D-07 — inside a transaction.atomic
block per D-11. NO Django signals (D-07) — register() is the single, visible,
testable entry point.

Phase 6 — SPEC-06-R06.
"""
import logging

from django.db import transaction

from planner.models import CrewMember, CrewProjectAdd, ProjectMember

logger = logging.getLogger(__name__)


def claim_pending_crew_memberships(user):
    """Rebind pending CrewMember rows and materialize ProjectMember rows for the new user.

    Args:
        user: A freshly-saved auth User instance.

    Returns:
        list[ProjectMember]: Newly-created ProjectMember rows. The caller is
        expected to send a confirmation email per row (D-10: log + swallow
        send failures).

    D-08: Case-insensitive via __iexact. Explicit .strip() on the user-side
    value before passing to filter() — NO gmail dot normalization, NO
    +alias collapsing (too surprising for users who legitimately use plus
    addressing).

    D-11: Caller wraps form.save() + this call in a single transaction.atomic.
    This helper opens its own inner transaction defensively so partial state
    cannot leak if the caller forgets the outer wrap.
    """
    normalized = (user.email or '').strip()
    if not normalized:
        return []

    pending = list(
        CrewMember.objects.filter(
            user__isnull=True,
            email__iexact=normalized,
        ).select_related('crew')
    )
    if not pending:
        return []

    new_memberships = []

    with transaction.atomic():
        for cm in pending:
            # Step 1 (D-01): UPDATE IN PLACE — preserves default_role + added_at.
            cm.user = user
            cm.email = None
            cm.save(update_fields=['user', 'email'])

            # Step 2 (D-09): materialize ProjectMember rows for every project
            # this crew has been bulk-added to.
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

The helper imports only from `django.db` (transaction) and `planner.models` (CrewMember, CrewProjectAdd, ProjectMember). It does NOT import from `accounts.views` — the confirmation-email send happens in the caller (per D-11: send AFTER the atomic block exits).
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && test -f planner/crew.py && test "$(wc -l < planner/crew.py)" -ge 50 && grep -q "^def claim_pending_crew_memberships" planner/crew.py && grep -q "from django.db import transaction" planner/crew.py && grep -q "from planner.models import CrewMember, CrewProjectAdd, ProjectMember" planner/crew.py && grep -q "email__iexact=normalized" planner/crew.py && grep -q "cm.save(update_fields=\\['user', 'email'\\])" planner/crew.py && grep -q "CrewProjectAdd.objects.filter(crew=cm.crew)" planner/crew.py && grep -q "ProjectMember.objects.get_or_create" planner/crew.py && ! grep -q "signal" planner/crew.py && python manage.py check 2>&1 | tee /tmp/check_crew.out && python -c "from planner.crew import claim_pending_crew_memberships; print('importable')" 2>&1 | grep -q "importable"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f planner/crew.py` exits 0
    - `wc -l < planner/crew.py` outputs >= 50
    - `grep -c "^def claim_pending_crew_memberships" planner/crew.py` outputs `1`
    - `grep -q "from django.db import transaction" planner/crew.py` exits 0
    - `grep -q "from planner.models import CrewMember, CrewProjectAdd, ProjectMember" planner/crew.py` exits 0
    - `grep -q "email__iexact=normalized" planner/crew.py` exits 0 (D-08)
    - `grep -q "user__isnull=True" planner/crew.py` exits 0 (D-08 — filter pending rows only)
    - `grep -q "cm.save(update_fields=\\['user', 'email'\\])" planner/crew.py` exits 0 (D-01 in-place update)
    - `grep -q "CrewProjectAdd.objects.filter(crew=cm.crew)" planner/crew.py` exits 0 (D-09)
    - `grep -q "ProjectMember.objects.get_or_create" planner/crew.py` exits 0 (idempotent materialization)
    - `grep -q "with transaction.atomic" planner/crew.py` exits 0 (defensive inner atomic per D-11)
    - `grep -c "signal" planner/crew.py` outputs `0` (D-07 — no Django signals)
    - `python manage.py check` exits 0
    - `python -c "from planner.crew import claim_pending_crew_memberships"` exits 0 (module importable)
  </acceptance_criteria>
  <done>
`planner/crew.py` exists, exports `claim_pending_crew_memberships`, uses `__iexact` + `.strip()` per D-08, updates rows in place per D-01, reads `CrewProjectAdd` per D-09, uses NO Django signals per D-07, and is importable without ImportError.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Wrap register() in transaction.atomic and call claim helper</name>
  <files>accounts/views.py</files>
  <read_first>
    - `accounts/views.py:16-37` (register — the function being edited)
    - `accounts/views.py:1-15` (top-of-file imports — verify which of `transaction`, logger are already imported by Plan 04)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` Decisions D-07, D-10, D-11
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` Pitfall 3 (auto-claim runs after form.save returns), Pitfall 7 (concurrent registration race)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` accounts/views.py:register() edit section
  </read_first>
  <action>
**Step A:** Add these top-of-file imports to `accounts/views.py` (if not already present from Plan 04):

    from django.db import transaction
    from planner.crew import claim_pending_crew_memberships

**Step B:** Modify the existing `register()` function (currently accounts/views.py:16-37). The ONLY change is wrapping `form.save()` + the new claim call in `transaction.atomic()`, then running the email loop OUTSIDE the atomic block. Do NOT rename the function, do NOT change its decorator (it has none), do NOT change its signature, do NOT change the GET branch.

Replace the existing if-form-is-valid block. Before:

    if form.is_valid():
        user = form.save()
        messages.success(
            request,
            f'Welcome to ShowStack, {user.first_name}! Your free account has been created. '
            'You can now accept project invitations from other users.'
        )
        return redirect('login')

After:

    if form.is_valid():
        # D-11: form.save() + auto-claim are atomic. If claim raises, the
        # User row rolls back so the user can re-register cleanly.
        with transaction.atomic():
            user = form.save()
            # D-07: inline call (no Django signals). Rebinds pending CrewMember
            # rows and materializes ProjectMember rows for every project the
            # crew has been bulk-added to (D-09 via CrewProjectAdd).
            new_pms = claim_pending_crew_memberships(user)

        # D-10/D-11: email sends happen OUTSIDE the atomic block — a Resend
        # hiccup must not roll back the user account. Log + swallow per row.
        for pm in new_pms:
            try:
                send_crew_added_email(pm, request)
            except Exception:
                logger.exception(
                    "Crew-added email failed on register for %s",
                    getattr(pm.user, 'email', '<unknown>'),
                )

        messages.success(
            request,
            f'Welcome to ShowStack, {user.first_name}! Your free account has been created. '
            'You can now accept project invitations from other users.'
        )
        return redirect('login')

The `send_crew_added_email` symbol resolves to the function defined in `accounts/views.py` by Plan 04 (same module — no import needed). The `logger` symbol is the module-level logger added by Plan 04.

Do NOT touch any other function in `accounts/views.py`. The GET branch of register and `accept_invitation` / `send_invitation_email` must remain byte-identical (SPEC R5).
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "from django.db import transaction" accounts/views.py && grep -q "from planner.crew import claim_pending_crew_memberships" accounts/views.py && grep -q "with transaction.atomic():" accounts/views.py && grep -q "new_pms = claim_pending_crew_memberships(user)" accounts/views.py && grep -q "for pm in new_pms:" accounts/views.py && grep -q "send_crew_added_email(pm, request)" accounts/views.py && test "$(git diff -- accounts/views.py | grep -cE '^[+-].*def accept_invitation')" -eq 0 && test "$(git diff -- accounts/views.py | grep -cE '^[+-].*def send_invitation_email')" -eq 0 && python manage.py check 2>&1 | tee /tmp/check_register.out</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "from django.db import transaction" accounts/views.py` exits 0
    - `grep -q "from planner.crew import claim_pending_crew_memberships" accounts/views.py` exits 0
    - `grep -c "with transaction.atomic():" accounts/views.py` >= 1
    - `grep -q "new_pms = claim_pending_crew_memberships(user)" accounts/views.py` exits 0
    - `grep -q "for pm in new_pms:" accounts/views.py` exits 0
    - `grep -q "send_crew_added_email(pm, request)" accounts/views.py` exits 0 (post-atomic email loop)
    - `grep -A 4 "for pm in new_pms:" accounts/views.py | grep -q "except Exception"` exits 0 (D-10: explicit broad except — narrower exception classes are rejected by the checker)
    - `grep -q "logger.exception" accounts/views.py` exits 0 (D-10 log + swallow)
    - `git diff -- accounts/views.py | grep -cE "^[+-].*def accept_invitation"` outputs `0` (SPEC R5)
    - `git diff -- accounts/views.py | grep -cE "^[+-].*def send_invitation_email"` outputs `0` (SPEC R5)
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
`register()` wraps `form.save()` + `claim_pending_crew_memberships(user)` in a single `transaction.atomic()` per D-11. Confirmation emails for newly-materialized ProjectMember rows are sent AFTER the atomic block exits per D-10. `accept_invitation` and `send_invitation_email` byte-identical to pre-phase state.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser POST → register | Untrusted: form data; RegistrationForm.clean_email already prevents duplicate User emails |
| register → claim_pending_crew_memberships | Server-internal, but the helper trusts the user.email value already validated by RegistrationForm |
| claim helper → ProjectMember.create | DB-level unique_together('project','user') is the perimeter; get_or_create is the idempotent gate |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-05-01 | Spoofing | Attacker registers with a victim's email to claim their pending crew rows | mitigate | `RegistrationForm.clean_email` (accounts/forms.py:58-63) already blocks duplicate User emails; the new user owning the email is the SPEC-defined claim |
| T-06-05-02 | Tampering | Concurrent registrations with the same email cause partial UniqueConstraint violations | mitigate | `RegistrationForm.clean_email` blocks duplicate User emails BEFORE form.save; inner `transaction.atomic` in claim helper is defence in depth (Pitfall 7) |
| T-06-05-03 | Tampering | Claim helper rolls back the User row on email-send failure (state mismatch) | mitigate | Email sends happen OUTSIDE the atomic block (D-10/D-11) — Resend hiccup never rolls back User |
| T-06-05-04 | Tampering | Email normalization differs between owner-input and registration | mitigate | D-08: same `__iexact` + `.strip()` rules apply to both pending row storage AND new-user match; NO gmail dot or +alias normalization (intentional) |
| T-06-05-05 | Elevation of Privilege | Pending CrewMember rebound to wrong user via case-collision | accept | `__iexact` is the only collapse rule; legitimate `foo@x.com` vs `FOO@x.com` are intended to match (Django auth treats them as distinct usernames but RegistrationForm should reject duplicates at form layer) |
| T-06-05-06 | Information Disclosure | Auto-claim leaks which projects the user was added to without their consent | accept | SPEC R6 explicitly designs this as friction-free onboarding; user can leave any project from the standard UI |
| T-06-05-07 | Repudiation | Inability to trace auto-claim materialization | mitigate | `ProjectMember.invited_by = cm.crew.owner` + `invited_at = auto_now_add` on the new row provides the audit trail per SPEC R3 |
</threat_model>

<verification>
- `python manage.py check` exits 0
- `python -c "from planner.crew import claim_pending_crew_memberships"` exits 0
- `register()` body contains exactly one `with transaction.atomic():` block wrapping `form.save()` + the claim call
- Email loop runs OUTSIDE the atomic block (verified by visual inspection: indentation level matches the loop body, not the with-block)
- `git diff -- accounts/views.py` shows no edits to `accept_invitation` or `send_invitation_email`
</verification>

<success_criteria>
- Owner adds `newbie@example.com` as a pending CrewMember to "Concert team" with default_role='editor'.
- Owner bulk-adds "Concert team" to Project X (creates CrewProjectAdd row).
- `newbie@example.com` registers via /register/. After registration:
  - CrewMember row updates: `user=<newbie>`, `email=None`, `default_role='editor'` preserved.
  - ProjectMember row exists: `(project=Project X, user=<newbie>, role='editor', invited_by=<owner>)`.
  - One confirmation email is attempted to newbie@example.com.
  - User can log in and see Project X in their accessible-projects list.
- If `newbie@example.com` was added to MULTIPLE crews (some not yet bulk-added anywhere): all matching CrewMember rows rebind; only crews with CrewProjectAdd entries produce ProjectMember rows.
- If Resend is offline during register, the User row is still created and login succeeds; ProjectMember rows still exist; failed email is logged for follow-up.
</success_criteria>

<output>
After completion, create `.planning/phases/06-trusted-crew-rosters/06-05-SUMMARY.md` capturing: line count of planner/crew.py, register() pre/post diff excerpts, confirmation that the email loop is OUTSIDE the atomic block, and grep output proving no Django signals were introduced.
</output>
