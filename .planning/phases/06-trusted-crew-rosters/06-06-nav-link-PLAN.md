---
phase: 06-trusted-crew-rosters
plan: 06
type: execute
wave: 3
depends_on:
  - 06-03
files_modified:
  - templates/admin/base_site.html
  - templates/accounts/dashboard.html
autonomous: true
requirements:
  - SPEC-06-R01
user_setup: []
must_haves:
  truths:
    - "Authenticated users see a 'My Crew' link in the admin chrome's top-right user menu (templates/admin/base_site.html — Django admin pages)"
    - "Authenticated users see a 'My Crew' link in the dashboard header-right cluster (templates/accounts/dashboard.html)"
    - "Both links resolve via {% url 'crew_index' %} (no hardcoded path)"
    - "Both links are visible regardless of account_type — empty state on /crew/ handles the no-crews case per D-12"
    - "Both edits are strictly additive — no existing markup deleted or rewritten"
    - "Hover styles match the existing Help button (admin) and btn-admin (dashboard) sibling patterns for visual coherence"
  artifacts:
    - path: "templates/admin/base_site.html"
      provides: "Additive 'My Crew' anchor inside the userlinks block before block.super"
      contains: "{% url 'crew_index' %}"
    - path: "templates/accounts/dashboard.html"
      provides: "Additive 'My Crew' anchor inside .header-right before the Logout link"
      contains: "My Crew"
  key_links:
    - from: "templates/admin/base_site.html"
      to: "accounts/views.py:crew_index"
      via: "{% url 'crew_index' %}"
      pattern: "url 'crew_index'"
    - from: "templates/accounts/dashboard.html"
      to: "accounts/views.py:crew_index"
      via: "{% url 'crew_index' %}"
      pattern: "url 'crew_index'"
---

<objective>
Add a "My Crew" link to TWO template surfaces so logged-in users can reach `/crew/` from both the admin chrome and the dashboard header, per D-04 + D-12. Strictly additive — no existing markup deleted or rewritten (SPEC R5 additivity ethos applies here too).

Purpose: Closes SPEC R1 navigation requirement (Crew page reachable from where users live). The two surfaces are per RESEARCH §"Architecture Patterns" Code Examples 2 + 3, both verified by file read.
Output: One additive `<a>` tag in `templates/admin/base_site.html` (before `{{ block.super }}` in the `userlinks` block) and one additive `<a>` tag in `templates/accounts/dashboard.html` (inside `.header-right` before the Logout link).
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
@templates/admin/base_site.html
@templates/accounts/dashboard.html

<interfaces>
<!-- Existing markup the executor MUST locate and insert before. -->

From templates/admin/base_site.html (userlinks block — RESEARCH cites lines 91-132; the Help button sibling at ~128 has the exact inline-style template for the new anchor):

    {% block userlinks %}
        ... existing badges + project switcher ...
        <button onclick="helpOpen()" style="background:none;border:1px solid #444;border-radius:4px;color:#ccc;font-size:13px;padding:5px 12px;cursor:pointer;margin-right:12px;" onmouseover="this.style.color='#00ff88';this.style.borderColor='#00ff88'" onmouseout="this.style.color='#ccc';this.style.borderColor='#444'">? Help</button>

        {{ block.super }}
    {% endblock %}

INSERTION POINT: immediately before `{{ block.super }}` (and immediately after the existing Help button). Mirror the Help button's inline-style verbatim — same border, padding, hover green `#00ff88` — for visual coherence.

From templates/accounts/dashboard.html (`.header-right` div — RESEARCH cites lines 285-294):

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

INSERTION POINT: between the conditional `Planner` anchor block (which ends after `{% endif %}`) and the `Logout` anchor. Reuse the existing `.btn-admin` CSS class — NO new CSS needed.

D-12 (always visible, no account-type gating): the link renders for any `{% if user.is_authenticated %}` user in admin, and unconditionally inside dashboard's `.header-right` (which only renders for logged-in users — verified by reading dashboard.html structure).

Executor MUST read each file before inserting to confirm exact line numbers — RESEARCH line numbers are a hint, not a guarantee.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add 'My Crew' anchor to templates/admin/base_site.html userlinks block</name>
  <files>templates/admin/base_site.html</files>
  <read_first>
    - `templates/admin/base_site.html` (full file — to locate the `userlinks` block, the Help button at the end of it, and the `{{ block.super }}` line)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` Decisions D-04, D-12
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` Code Example 2 (admin user-menu insertion)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` templates/admin/base_site.html edit section
  </read_first>
  <action>
**SPEC R5 ethos — strictly additive.** Do NOT modify ANY existing line. INSERT a new `{% if user.is_authenticated %}` block IMMEDIATELY BEFORE `{{ block.super }}` inside the `userlinks` block, AFTER the existing Help button.

Insert this exact block:

```
    {# Phase 6 (D-04, D-12): My Crew link — always visible for authenticated users. #}
    {% if user.is_authenticated %}
    <a href="{% url 'crew_index' %}"
       style="background:none;border:1px solid #444;border-radius:4px;color:#ccc;font-size:13px;padding:5px 12px;cursor:pointer;margin-right:12px;text-decoration:none;"
       onmouseover="this.style.color='#00ff88';this.style.borderColor='#00ff88'"
       onmouseout="this.style.color='#ccc';this.style.borderColor='#444'">My Crew</a>
    {% endif %}

```

The inline style mirrors the existing Help button verbatim (same border, padding, hover green `#00ff88`) but adds `text-decoration:none;` because anchors default to underlined and the Help button is a `<button>` (no underline). Color, hover behavior, and spacing match exactly.

After inserting, the rendered admin top-right cluster shows: [existing badges] → [project switcher] → [Help button] → [My Crew anchor] → [Django default block.super: View site / Documentation / Change password / Log out / theme toggle].
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "Phase 6" templates/admin/base_site.html && grep -q "{% url 'crew_index' %}" templates/admin/base_site.html && grep -q ">My Crew</a>" templates/admin/base_site.html && grep -q "{% if user.is_authenticated %}" templates/admin/base_site.html && test "$(git diff -- templates/admin/base_site.html | grep -cE '^-[^-]')" -eq 0 && python manage.py check 2>&1 | tee /tmp/check_admin_tpl.out</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "Phase 6" templates/admin/base_site.html` exits 0
    - `grep -q "{% url 'crew_index' %}" templates/admin/base_site.html` exits 0
    - `grep -q ">My Crew</a>" templates/admin/base_site.html` exits 0
    - `grep -q "{% if user.is_authenticated %}" templates/admin/base_site.html` exits 0 (gate present per D-12 — "logged-in users")
    - `grep -q "border:1px solid #444" templates/admin/base_site.html` exits 0 (INFO 8: My Crew anchor's inline style matches the existing Help button border verbatim)
    - `git diff -- templates/admin/base_site.html | grep -cE "^-[^-]"` outputs `0` (zero deletions — SPEC R5 additive)
    - `git diff -- templates/admin/base_site.html | grep -cE "^[+][^+]"` is at least 5 (insertion happened)
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
"My Crew" anchor inserted in `templates/admin/base_site.html` `userlinks` block before `{{ block.super }}`. Zero existing lines deleted. Hover style matches the Help button sibling.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add 'My Crew' anchor to templates/accounts/dashboard.html header-right cluster</name>
  <files>templates/accounts/dashboard.html</files>
  <read_first>
    - `templates/accounts/dashboard.html` (full file or at minimum lines 280-310 — to locate the exact `.header-right` div, the conditional Planner anchor, and the Logout anchor)
    - `.planning/phases/06-trusted-crew-rosters/06-CONTEXT.md` Decisions D-04, D-12
    - `.planning/phases/06-trusted-crew-rosters/06-RESEARCH.md` Code Example 3 (dashboard insertion)
    - `.planning/phases/06-trusted-crew-rosters/06-PATTERNS.md` templates/accounts/dashboard.html edit section
  </read_first>
  <action>
**SPEC R5 ethos — strictly additive.** Do NOT modify ANY existing line. INSERT one new anchor INSIDE the existing `.header-right` div, BETWEEN the conditional `Planner` anchor block (which ends with `{% endif %}`) and the existing `Logout` anchor.

Insert this exact line:

```
            {# Phase 6 (D-04, D-12): My Crew — always visible for logged-in dashboard users. #}
            <a href="{% url 'crew_index' %}" class="btn-admin">My Crew</a>
```

The anchor reuses the existing `.btn-admin` CSS class already defined in dashboard.html (around lines 67-80) — NO new CSS, NO new color rules. The class gives it the same blue styling as the conditional "Planner" anchor next to it.

After inserting, `.header-right` reads: [user-info] → [conditional Planner anchor] → [My Crew anchor] → [Logout anchor].
  </action>
  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -q "Phase 6" templates/accounts/dashboard.html && grep -q "{% url 'crew_index' %}" templates/accounts/dashboard.html && grep -q "class=\"btn-admin\">My Crew</a>" templates/accounts/dashboard.html && test "$(git diff -- templates/accounts/dashboard.html | grep -cE '^-[^-]')" -eq 0 && python manage.py shell -c "from django.template.loader import render_to_string; from django.contrib.auth import get_user_model; U=get_user_model(); u,_=U.objects.get_or_create(username='__dash_test__', defaults={'email':'d@d.d'}); print('ok' if render_to_string('accounts/dashboard.html', {'user':u, 'account_type':'free', 'projects':[], 'owned_projects':[], 'invitations':[], 'access_requests':[], 'messages':[]}) else 'FAIL'); u.delete()" 2>&1 | tee /tmp/render_dash.out | grep -q "ok"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "Phase 6" templates/accounts/dashboard.html` exits 0
    - `grep -q "{% url 'crew_index' %}" templates/accounts/dashboard.html` exits 0
    - `grep -q "class=\"btn-admin\">My Crew</a>" templates/accounts/dashboard.html` exits 0
    - `git diff -- templates/accounts/dashboard.html | grep -cE "^-[^-]"` outputs `0` (additive only — SPEC R5)
    - `git diff -- templates/accounts/dashboard.html | grep -cE "^[+][^+]"` is at least 2 (insertion happened)
    - `render_to_string('accounts/dashboard.html', stub_ctx)` returns non-empty string with no NoReverseMatch
    - `python manage.py check` exits 0
  </acceptance_criteria>
  <done>
"My Crew" anchor inserted in `templates/accounts/dashboard.html` `.header-right` between the conditional Planner anchor and the Logout anchor. Reuses existing `.btn-admin` class — zero new CSS. Zero existing lines deleted.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Server template render → Browser | Templates emit HTML; trust boundary is on the request side (auth check on /crew/ itself) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-06-01 | Information Disclosure | "My Crew" link visible to unauthenticated users on admin chrome | mitigate | `{% if user.is_authenticated %}` gate in base_site.html insertion (D-12 — "logged-in users") |
| T-06-06-02 | Elevation of Privilege | Anonymous user clicks the link and bypasses auth | accept | `crew_index` view has `@login_required` decorator from Plan 03 — link is convenience only, view is the perimeter |
| T-06-06-03 | Tampering | Hardcoded `/crew/` path drifts from URL conf | mitigate | Both insertions use `{% url 'crew_index' %}` — Django's URL reverser is the single source of truth |
| T-06-06-04 | Tampering | Existing admin chrome rewritten by the insertion | mitigate | `git diff` acceptance criteria require zero deletions (SPEC R5 additivity) |
</threat_model>

<verification>
- `python manage.py check` exits 0
- Both templates render via `render_to_string` (or by visiting `/admin/` and `/dashboard/`) without `NoReverseMatch`
- `git diff` for both files shows zero deletions
- Visiting `/admin/` shows "My Crew" between Help and the Django default user menu
- Visiting `/dashboard/` shows "My Crew" between Planner (when applicable) and Logout
</verification>

<success_criteria>
- Logged-in superuser at `/admin/` sees "My Crew" in the top-right cluster, clicks it, lands on `/crew/`
- Logged-in free-account user at `/dashboard/` sees "My Crew" between (no Planner button) and Logout, clicks it, lands on `/crew/`
- Anonymous visitor to `/admin/login/` does NOT see "My Crew" (admin login page hides userlinks)
- No existing styling regression on either page
</success_criteria>

<output>
After completion, create `.planning/phases/06-trusted-crew-rosters/06-06-SUMMARY.md` capturing: insertion line numbers in both files, git-diff stats (additive only — zero deletions), and render-test confirmation.
</output>
