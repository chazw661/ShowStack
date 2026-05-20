---
phase: 07
plan: 04
type: execute
wave: 3
depends_on:
  - "07-01"
  - "07-02"
  - "07-03"
files_modified:
  - planner/templates/planner/signal_flow/list.html
  - planner/templates/planner/signal_flow/editor.html
  - planner/static/planner/js/signal_flow_editor.js
  - templates/planner/dashboard.html
autonomous: false   # Task 3 is a checkpoint:human-verify (browser smoke test)
requirements:
  - DGM-01
  - DGM-05
  - DGM-08
user_setup: []

must_haves:
  truths:
    - "GET /audiopatch/signal-flow/ renders a styled list page extending admin/base_site.html; shows all diagrams for current_project; shows empty state when no diagrams exist"
    - "GET /audiopatch/signal-flow/<id>/ renders editor.html with a #sfd-container div carrying all 5 data-* URL attributes (data-diagram-id, data-state-url, data-autosave-url, data-autocomplete-url, data-export-png-url)"
    - "joint.min.js + html-to-image.min.js + signal_flow_editor.js are loaded by editor.html via {% static %} with the correct order"
    - "Browser console on editor page shows '[SFD] JointJS ready — version <X>' from the stub JS"
    - "No 404 errors in browser network tab on JS/CSS assets when editor page is loaded"
    - "Main dashboard at /dashboard/ has a quick-action link to /audiopatch/signal-flow/"
    - "CSRF cookie is set via <form>{% csrf_token %}</form> on both list.html and editor.html (DGM-08 prerequisite — Phase 9 AJAX needs the cookie present)"
  artifacts:
    - path: "planner/templates/planner/signal_flow/list.html"
      provides: "Diagram list page with create/rename/delete affordances"
      contains: "{% url 'planner:signal_flow_create' %}"
    - path: "planner/templates/planner/signal_flow/editor.html"
      provides: "HTML editor shell with #sfd-container + data-* attributes; loads vendor JS"
      contains: "data-autosave-url"
    - path: "planner/static/planner/js/signal_flow_editor.js"
      provides: "Phase 7 stub JS — confirms joint global is loaded; logs to console"
      contains: "[SFD] JointJS ready"
    - path: "templates/planner/dashboard.html"
      provides: "Quick-action link to /audiopatch/signal-flow/"
      contains: "/audiopatch/signal-flow/"
  key_links:
    - from: "planner/templates/planner/signal_flow/editor.html"
      to: "vendor/joint.min.js (Plan 02 artifact)"
      via: "<script src=\"{% static 'planner/js/vendor/joint.min.js' %}\"></script>"
      pattern: "planner/js/vendor/joint.min.js"
    - from: "planner/templates/planner/signal_flow/editor.html"
      to: "planner:signal_flow_autosave URL name (Plan 03 artifact)"
      via: "data-autosave-url=\"{% url 'planner:signal_flow_autosave' diagram.id %}\""
      pattern: "data-autosave-url"
    - from: "templates/planner/dashboard.html quick-action"
      to: "signal_flow_list view"
      via: "href='/audiopatch/signal-flow/'"
      pattern: "/audiopatch/signal-flow/"
---

<objective>
Ship the user-visible HTML+JS layer for Phase 7: the diagram list page, the editor HTML shell with vendored JointJS loaded, the Phase 7 stub JS that confirms the canvas library loads, and the dashboard quick-action entry point. After this plan, an engineer can navigate from dashboard -> Signal Flow -> list page -> create a new diagram -> open the editor shell. The browser console shows `[SFD] JointJS ready` confirming the canvas library loaded — Phase 8 will then wire the actual canvas.

Purpose: Closes DGM-01 (list page actually rendering for users), the user-visible portion of DGM-05 (editor page loads via project-scoped lookup), and the editor-shell portion of DGM-08 (data-autosave-url present in DOM so Phase 9 JS has the URL to fetch).

Output: Four file changes — two new HTML templates, one new JS file, one additive line in the dashboard. Browser smoke test confirms editor page loads with no 404s and the joint global is available.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md
@.planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md
@CLAUDE.md

<interfaces>
<!-- URL names from Plan 03 — referenced via {% url %} tags -->
From planner/urls.py (after Plan 07-03):
- planner:signal_flow_list                   /audiopatch/signal-flow/
- planner:signal_flow_create                 /audiopatch/signal-flow/create/
- planner:signal_flow_editor (diagram_id)    /audiopatch/signal-flow/<id>/
- planner:signal_flow_state (diagram_id)     /audiopatch/signal-flow/<id>/state/
- planner:signal_flow_autosave (diagram_id)  /audiopatch/signal-flow/<id>/save/
- planner:signal_flow_rename (diagram_id)    /audiopatch/signal-flow/<id>/rename/
- planner:signal_flow_delete (diagram_id)    /audiopatch/signal-flow/<id>/delete/
- planner:signal_flow_autocomplete           /audiopatch/signal-flow/autocomplete/
- planner:signal_flow_export_png (diagram_id) /audiopatch/signal-flow/<id>/export.png/

<!-- View context provided to templates (from Plan 03) -->
signal_flow_list -> { 'diagrams': QuerySet[SignalFlowDiagram], 'current_project': Project|None }
signal_flow_editor -> { 'diagram': SignalFlowDiagram }
  diagram.id, diagram.name, diagram.updated_at, diagram.canvas_state, diagram.viewport, diagram.version

<!-- Vendored JS from Plan 02 — referenced via {% static %} -->
- planner/static/planner/js/vendor/joint.min.js     # @joint/core 4.2.4 (UMD: exposes `joint` global)
- planner/static/planner/js/vendor/html-to-image.min.js  # html-to-image 1.11.11 (UMD: exposes `htmlToImage` global)

<!-- Existing templates to match for style/structure -->
- planner/templates/planner/multitrack/dashboard.html  # analog for list.html (multitrack dashboard)
- planner/templates/planner/multitrack/editor.html     # analog for editor.html (data-* attribute injection)
- templates/planner/dashboard.html lines 318-321       # existing Multitrack quick-action — analog for new link
- planner/static/planner/js/multitrack_editor.js       # IIFE + 'use strict' analog for signal_flow_editor.js

<!-- Base template -->
- templates/admin/base_site.html                       # extended by all planner module pages
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Create list.html + editor.html templates + signal_flow_editor.js stub</name>
  <files>planner/templates/planner/signal_flow/list.html, planner/templates/planner/signal_flow/editor.html, planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (sections: "planner/templates/planner/signal_flow/list.html", "planner/templates/planner/signal_flow/editor.html", "planner/static/planner/js/signal_flow_editor.js")
    - planner/templates/planner/multitrack/dashboard.html — read entire file to capture extend/block/CSRF/script patterns
    - planner/templates/planner/multitrack/editor.html — read lines 1-30 to capture data-* attribute injection pattern and `|escapejs` usage
    - planner/static/planner/js/multitrack_editor.js — read lines 1-30 to capture IIFE + 'use strict' header and the CLAUDE.md !important comment
    - .planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md (Pattern 7: editor.html shell, Pattern 11: stub JS)
    - CLAUDE.md "Overriding Django admin CSS from JavaScript" (use el.style.setProperty(..., 'important')); "Templates" (two template dirs both in TEMPLATES['DIRS'])
  </read_first>

  <behavior>
    - planner/templates/planner/signal_flow/ directory is created (mkdir if needed)
    - list.html extends admin/base_site.html, loads static, sets a page title, lists `diagrams` with name/updated_at, shows empty state if none, has a "+ New Diagram" affordance, includes a hidden CSRF form for Phase 9 AJAX
    - editor.html extends admin/base_site.html, has #sfd-container div with 5 data-* URL attributes injected via {% url %}, loads joint.min.js + html-to-image.min.js + signal_flow_editor.js, includes hidden CSRF form, has a placeholder #sfd-paper div with a white background
    - signal_flow_editor.js is an IIFE that reads container.dataset.diagramId, checks for `joint` global, logs "[SFD] JointJS ready" with the joint version, and does nothing else (canvas init lands in Phase 8)
    - Browser visit to /audiopatch/signal-flow/ (after login as staff) renders list page; browser visit to a diagram URL renders editor with the joint-ready console log
  </behavior>

  <action>
**Step A — Create the templates directory:**

Create `planner/templates/planner/signal_flow/` if it does not exist. From project root:

    mkdir -p planner/templates/planner/signal_flow

**Step B — Write list.html:**

Create `planner/templates/planner/signal_flow/list.html` with exactly this content:

    {% extends "admin/base_site.html" %}
    {% load static %}

    {% block title %}Signal Flow Diagrams | ShowStack{% endblock %}

    {% block extrahead %}
    {{ block.super }}
    {# Phase 7: no module-level CSS yet — Phase 8 may add planner/css/signal_flow.css #}
    <style>
      .sfd-container { padding: 24px; max-width: 1100px; margin: 0 auto; }
      .sfd-header { display: flex; justify-content: space-between; align-items: flex-end;
                    border-bottom: 1px solid #444; padding-bottom: 12px; margin-bottom: 24px; }
      .sfd-h1 { margin: 0 0 4px 0; font-size: 24px; }
      .sfd-subtitle { margin: 0; color: #aaa; font-size: 13px; }
      .sfd-btn { display: inline-block; padding: 8px 14px; border-radius: 4px; border: 1px solid #555;
                 background: #2a2a3e; color: #eee; text-decoration: none; cursor: pointer; font-size: 13px; }
      .sfd-btn-primary { background: #0a84ff; border-color: #0a84ff; color: #fff; }
      .sfd-grid { display: grid; gap: 12px; }
      .sfd-card { background: #1a1a2e; border: 1px solid #333; border-radius: 6px; padding: 16px;
                  display: flex; justify-content: space-between; align-items: center; }
      .sfd-card-name { font-size: 15px; font-weight: 600; }
      .sfd-card-meta { color: #888; font-size: 12px; margin-top: 4px; }
      .sfd-card-actions { display: flex; gap: 8px; }
      .sfd-empty { text-align: center; padding: 64px 16px; border: 1px dashed #444; border-radius: 8px; }
      .sfd-empty-h { font-size: 18px; margin: 0 0 8px 0; }
      .sfd-empty-p { color: #888; margin: 0 0 16px 0; }
    </style>
    {% endblock %}

    {% block content %}
    <div class="sfd-container">
      <div class="sfd-header">
        <div>
          <h1 class="sfd-h1">Signal Flow Diagrams</h1>
          <p class="sfd-subtitle">Draw block diagrams of your audio system; nodes link to your ShowStack consoles, devices, speaker arrays, and intercom belt-packs.</p>
        </div>
        <div>
          <button type="button" class="sfd-btn sfd-btn-primary" id="sfd-new-diagram-btn">+ New Diagram</button>
        </div>
      </div>

      {% if diagrams %}
        <div class="sfd-grid">
          {% for d in diagrams %}
            <div class="sfd-card" data-diagram-id="{{ d.id }}">
              <div>
                <div class="sfd-card-name">{{ d.name }}</div>
                <div class="sfd-card-meta">Updated {{ d.updated_at|date:"M j, Y H:i" }}</div>
              </div>
              <div class="sfd-card-actions">
                <a class="sfd-btn" href="{% url 'planner:signal_flow_editor' d.id %}">Open</a>
                <button type="button" class="sfd-btn" data-action="rename" data-id="{{ d.id }}" data-name="{{ d.name|escapejs }}">Rename</button>
                <button type="button" class="sfd-btn" data-action="delete" data-id="{{ d.id }}" data-name="{{ d.name|escapejs }}">Delete</button>
              </div>
            </div>
          {% endfor %}
        </div>
      {% else %}
        <div class="sfd-empty">
          <h2 class="sfd-empty-h">No diagrams yet</h2>
          <p class="sfd-empty-p">Create your first signal-flow diagram for this project to start mapping your system.</p>
          <button type="button" class="sfd-btn sfd-btn-primary" id="sfd-empty-new-btn">+ New Diagram</button>
        </div>
      {% endif %}
    </div>

    {# CSRF cookie for AJAX create/rename/delete — Phase 7 wires basic create flow; full rename/delete UX lands here as inline JS #}
    <form style="display:none">{% csrf_token %}</form>

    <script>
    (function () {
      'use strict';

      function getCsrfToken() {
        return document.cookie.split('; ')
          .find(function (row) { return row.startsWith('csrftoken='); })
          .split('=')[1];
      }

      function promptName(defaultName) {
        var name = window.prompt('Diagram name:', defaultName || '');
        if (name === null) return null;
        name = name.trim();
        if (!name) { alert('Name is required.'); return null; }
        if (name.length > 200) { alert('Name must be 200 characters or fewer.'); return null; }
        return name;
      }

      function ajaxJson(url, body) {
        return fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
          },
          credentials: 'same-origin',
          body: JSON.stringify(body || {}),
        }).then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
        });
      }

      function newDiagram() {
        var name = promptName('');
        if (name === null) return;
        ajaxJson('{% url "planner:signal_flow_create" %}', { name: name }).then(function (res) {
          if (res.ok && res.body.redirect_url) {
            window.location.href = res.body.redirect_url;
          } else {
            alert(res.body.error || 'Create failed (status ' + res.status + ').');
          }
        });
      }

      function bindAll(sel, fn) {
        var els = document.querySelectorAll(sel);
        for (var i = 0; i < els.length; i++) { els[i].addEventListener('click', fn); }
      }

      var newBtn = document.getElementById('sfd-new-diagram-btn');
      if (newBtn) newBtn.addEventListener('click', newDiagram);
      var emptyBtn = document.getElementById('sfd-empty-new-btn');
      if (emptyBtn) emptyBtn.addEventListener('click', newDiagram);

      bindAll('button[data-action="rename"]', function (ev) {
        var id = ev.currentTarget.dataset.id;
        var current = ev.currentTarget.dataset.name;
        var name = promptName(current);
        if (name === null) return;
        ajaxJson('/audiopatch/signal-flow/' + id + '/rename/', { name: name }).then(function (res) {
          if (res.ok) { window.location.reload(); }
          else { alert(res.body.error || 'Rename failed (status ' + res.status + ').'); }
        });
      });

      bindAll('button[data-action="delete"]', function (ev) {
        var id = ev.currentTarget.dataset.id;
        var name = ev.currentTarget.dataset.name;
        if (!window.confirm('Delete diagram "' + name + '"? This cannot be undone.')) return;
        ajaxJson('/audiopatch/signal-flow/' + id + '/delete/', {}).then(function (res) {
          if (res.ok) { window.location.reload(); }
          else { alert(res.body.error || 'Delete failed (status ' + res.status + ').'); }
        });
      });
    })();
    </script>
    {% endblock %}

Notes:
- The CSS block is intentionally inline in `{% block extrahead %}` rather than a separate `signal_flow.css` file. Phase 8 may extract a CSS file once the canvas UX matures; for Phase 7 the styles are minimal scaffolding and inline is faster.
- The inline `<script>` at the bottom of `{% block content %}` is the list-page CRUD JS. It uses `window.prompt` and `window.confirm` for v1 minimal UX (no modal library). The CSRF cookie + X-CSRFToken pattern matches CLAUDE.md / the `getCsrfToken` precedent at mic_tracker.html:1212.
- No reference to `signal_flow_editor.js` here — that JS is editor-only.

**Step C — Write editor.html:**

Create `planner/templates/planner/signal_flow/editor.html` with exactly this content:

    {% extends "admin/base_site.html" %}
    {% load static %}

    {% block title %}{{ diagram.name }} — Signal Flow | ShowStack{% endblock %}

    {% block extrahead %}
    {{ block.super }}
    {# No CSS required for @joint/core 4.x — paper background set inline on #sfd-paper below. #}
    <style>
      #sfd-container { display: flex; flex-direction: column; height: calc(100vh - 64px); }
      #sfd-toolbar { padding: 8px 16px; background: #2a2a3e; border-bottom: 1px solid #444;
                     display: flex; gap: 12px; align-items: center; }
      #sfd-toolbar h1 { margin: 0; font-size: 16px; color: #eee; }
      #sfd-canvas-container { flex: 1 1 auto; position: relative; overflow: hidden; }
      #sfd-paper { width: 100%; height: 100%; background: #ffffff; }
      .sfd-back-link { color: #aaa; text-decoration: none; font-size: 13px; }
      .sfd-back-link:hover { color: #fff; text-decoration: underline; }
    </style>
    {% endblock %}

    {% block content %}
    <div id="sfd-container"
         data-diagram-id="{{ diagram.id }}"
         data-diagram-name="{{ diagram.name|escapejs }}"
         data-state-url="{% url 'planner:signal_flow_state' diagram.id %}"
         data-autosave-url="{% url 'planner:signal_flow_autosave' diagram.id %}"
         data-autocomplete-url="{% url 'planner:signal_flow_autocomplete' %}"
         data-export-png-url="{% url 'planner:signal_flow_export_png' diagram.id %}">

      <div id="sfd-toolbar">
        <a class="sfd-back-link" href="{% url 'planner:signal_flow_list' %}">&larr; Diagrams</a>
        <h1>{{ diagram.name }}</h1>
        <span style="color:#888;font-size:12px;">(Phase 8 will wire the canvas; this is the shell.)</span>
      </div>

      <div id="sfd-canvas-container">
        {# JointJS paper mounts here in Phase 8. Phase 7 shows a blank white div. #}
        <div id="sfd-paper"></div>
      </div>
    </div>

    {# CSRF cookie available for all AJAX POST calls (Phase 9 autosave will use it). #}
    <form style="display:none">{% csrf_token %}</form>

    {# Vendor bundles — load order matters: joint first, then html-to-image, then app JS. #}
    {# joint is NOT deferred — it must be on `window.joint` when signal_flow_editor.js evaluates. #}
    <script src="{% static 'planner/js/vendor/joint.min.js' %}"></script>
    <script src="{% static 'planner/js/vendor/html-to-image.min.js' %}"></script>
    <script src="{% static 'planner/js/signal_flow_editor.js' %}" defer></script>
    {% endblock %}

CRITICAL details:
- `data-diagram-name` uses `|escapejs` — required because the value is consumed by JS as a string. Without escapejs, a diagram named `Alice's diagram` breaks the attribute parser.
- All five data-* URL attributes are present even though only `data-diagram-id`, `data-state-url`, and `data-autosave-url` are read by the Phase 7 stub JS. The rest are present so Phase 8/9/10 JS does not need to add template changes — only fill in behavior.
- `joint.min.js` is loaded WITHOUT `defer` (it must be synchronous so `joint` is on `window` before any code that references it runs). `html-to-image.min.js` could safely be deferred but is kept synchronous here for symmetry with joint.min.js and to match PATTERNS.md template. `signal_flow_editor.js` IS deferred — it's our application code, and `defer` ensures DOM is ready before its IIFE runs.

**Step D — Write the Phase 7 stub JS:**

Create `planner/static/planner/js/signal_flow_editor.js` with exactly this content:

    // planner/static/planner/js/signal_flow_editor.js
    //
    // Signal Flow Diagrammer — editor controller.
    // Phase 7: STUB only. Confirms vendor bundles loaded; canvas init lands in Phase 8.
    //
    // IMPORTANT: All DOM color/style writes use
    //     el.style.setProperty(prop, value, 'important')
    // Direct property assignment (the dot-style.color form) silently fails
    // against Django admin's !important rules (CLAUDE.md > Coding Conventions).
    //
    // Note: JointJS canvas SVG elements (added in Phase 8) are NOT in the admin DOM
    // and are unaffected by the !important rule. This guidance only matters for any
    // toolbar / modal HTML rendered by Django admin templates.

    (function () {
      'use strict';

      var container = document.getElementById('sfd-container');
      if (!container) {
        // Either we're not on the editor page or the template was changed unexpectedly.
        return;
      }

      var diagramId = container.dataset.diagramId;
      var stateUrl = container.dataset.stateUrl;
      var autosaveUrl = container.dataset.autosaveUrl;

      // Confirm JointJS UMD bundle loaded and exposes `joint` global.
      if (typeof joint === 'undefined') {
        console.error('[SFD] joint is not defined — check vendor/joint.min.js load order in editor.html');
        return;
      }

      // Confirm html-to-image bundle loaded (Phase 10 needs this).
      // Some UMD builds expose `htmlToImage`; some expose individual functions on window.
      // For now, just log whichever shape is present.
      var h2iAvailable = (typeof htmlToImage !== 'undefined') ||
                         (typeof window.htmlToImage !== 'undefined');

      console.log('[SFD] JointJS ready — version', joint.version || '(unknown)',
                  '— diagram', diagramId,
                  '— html-to-image:', h2iAvailable ? 'loaded' : 'MISSING',
                  '— stateUrl:', stateUrl,
                  '— autosaveUrl:', autosaveUrl);

      // Phase 8 will: graph + paper init, graph.fromJSON(stateUrl), shape picker.
      // Phase 9 will: autosave debounce on graph events, keepalive fetch on visibilitychange.
      // Phase 10 will: circuit-label autocomplete widget, PNG export button.
    })();

Notes:
- The stub deliberately reads `stateUrl` and `autosaveUrl` (not used yet) so a future developer can see at a glance what URLs are available without re-reading editor.html.
- The `joint.version` reference may be `undefined` in some `@joint/core` builds — the `|| '(unknown)'` fallback prevents a confusing log line.
- `htmlToImage` global presence check is informational; if missing, Phase 10 will hard-fail and PNG export won't work — easier to detect now.
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && test -f planner/templates/planner/signal_flow/list.html && test -f planner/templates/planner/signal_flow/editor.html && test -f planner/static/planner/js/signal_flow_editor.js && python manage.py check && python manage.py collectstatic --noinput 2>&1 | tail -3</automated>
  </verify>

  <acceptance_criteria>
    - File planner/templates/planner/signal_flow/list.html exists
    - `grep -c "{% url 'planner:signal_flow_create' %}" planner/templates/planner/signal_flow/list.html` returns 1
    - `grep -c "{% extends \"admin/base_site.html\" %}" planner/templates/planner/signal_flow/list.html` returns 1
    - `grep -c "{% csrf_token %}" planner/templates/planner/signal_flow/list.html` returns 1
    - File planner/templates/planner/signal_flow/editor.html exists
    - `grep -c "data-diagram-id=\"{{ diagram.id }}\"" planner/templates/planner/signal_flow/editor.html` returns 1
    - `grep -c "data-autosave-url=\"{% url 'planner:signal_flow_autosave' diagram.id %}\"" planner/templates/planner/signal_flow/editor.html` returns 1
    - `grep -c "data-state-url=" planner/templates/planner/signal_flow/editor.html` returns 1
    - `grep -c "data-export-png-url=" planner/templates/planner/signal_flow/editor.html` returns 1
    - `grep -c "data-autocomplete-url=" planner/templates/planner/signal_flow/editor.html` returns 1
    - `grep -c "planner/js/vendor/joint.min.js" planner/templates/planner/signal_flow/editor.html` returns 1
    - `grep -c "planner/js/vendor/html-to-image.min.js" planner/templates/planner/signal_flow/editor.html` returns 1
    - `grep -c "planner/js/signal_flow_editor.js" planner/templates/planner/signal_flow/editor.html` returns 1
    - File planner/static/planner/js/signal_flow_editor.js exists
    - `grep -c "\\[SFD\\] JointJS ready" planner/static/planner/js/signal_flow_editor.js` returns 1
    - `grep -c "'use strict'" planner/static/planner/js/signal_flow_editor.js` returns 1
    - `python manage.py check` exits 0
    - `python manage.py collectstatic --noinput` exits 0 (must succeed before Wave 4 / next phase)
  </acceptance_criteria>

  <done>
    Three files exist: list.html, editor.html, signal_flow_editor.js. All `{% url %}` references resolve (Plan 03 URLs exist), all `{% static %}` paths resolve (Plan 02 vendor files committed). `python manage.py check` and `python manage.py collectstatic --noinput` both pass.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add Signal Flow quick-action link to main dashboard</name>
  <files>templates/planner/dashboard.html</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (section: "templates/planner/dashboard.html — add quick-action link")
    - templates/planner/dashboard.html lines 315-325 — locate the existing Multitrack quick-action link to use as exact insertion-point reference
  </read_first>

  <behavior>
    - templates/planner/dashboard.html contains a new <a class="quick-action"> link pointing to /audiopatch/signal-flow/ with a "Signal Flow" label
    - Link uses the same structural pattern (icon div + label) as the existing Multitrack entry
    - All other dashboard content is preserved verbatim
  </behavior>

  <action>
**Step A — Locate the Multitrack quick-action block:**

    grep -n "Multitrack Sessions\|/audiopatch/multitrack/" templates/planner/dashboard.html

Expected matches around lines 318-321. The block should look like:

        <a href="/audiopatch/multitrack/" class="quick-action">
            <div class="quick-action-icon">🎚️</div>
            Multitrack Sessions
        </a>

**Step B — Insert the new Signal Flow quick-action immediately after the Multitrack block:**

Use the Edit tool to insert (after the closing `</a>` of the Multitrack quick-action, before the next sibling element):

        <a href="/audiopatch/signal-flow/" class="quick-action">
            <div class="quick-action-icon">📐</div>
            Signal Flow
        </a>

CRITICAL: Match the surrounding indentation exactly (typically 4 or 8 spaces — copy from the Multitrack `<a>` line's leading whitespace). Do not add or remove blank lines around the insertion.

**Step C — Verify the dashboard still renders:**

    python manage.py check

(System check passes — templates are not parsed for syntax errors by `check`, but anything that imports the dashboard module would surface here.)

A real verification of the dashboard template rendering correctly belongs to the Phase 7 browser smoke test (Task 3 below).
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && grep -c '/audiopatch/signal-flow/' templates/planner/dashboard.html && grep -c 'Signal Flow' templates/planner/dashboard.html && python manage.py check</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "/audiopatch/signal-flow/" templates/planner/dashboard.html` returns at least 1
    - `grep -c "Signal Flow" templates/planner/dashboard.html` returns at least 1
    - `grep -c "class=\"quick-action\"" templates/planner/dashboard.html` is greater than its pre-edit value (specifically, one more occurrence after this task)
    - The line containing `/audiopatch/multitrack/` still exists (Multitrack link preserved)
    - `python manage.py check` exits 0
  </acceptance_criteria>

  <done>
    Main dashboard has a new "Signal Flow" quick-action link adjacent to "Multitrack Sessions", matching the existing pattern. No other dashboard content modified.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Manual browser smoke test — visit list + editor pages</name>
  <what-built>
    Plan 07-04 has delivered:
    - planner/templates/planner/signal_flow/list.html (diagram list page with create/rename/delete affordances)
    - planner/templates/planner/signal_flow/editor.html (HTML shell with vendored JointJS loaded)
    - planner/static/planner/js/signal_flow_editor.js (Phase 7 stub logging "[SFD] JointJS ready")
    - templates/planner/dashboard.html updated with Signal Flow quick-action link

    Combined with Plans 07-01, 07-02, 07-03, all Phase 7 deliverables are now in place. This checkpoint verifies the end-to-end user-visible flow before Phase 7 ships.
  </what-built>

  <how-to-verify>
    From the project root, start the local dev server:

        cd /Users/charlielawsonmacair/DjangoProjects/audiopatch
        python manage.py runserver

    Then in a browser:

    1. **Dashboard entry point:**
       - Visit http://localhost:8000/dashboard/ (log in as a staff user if prompted; ensure a current_project is selected)
       - Confirm a "Signal Flow" quick-action card is present next to "Multitrack Sessions"
       - Confirm the card icon and styling matches surrounding cards
       - Click the card -> browser navigates to /audiopatch/signal-flow/

    2. **List page — empty state:**
       - On /audiopatch/signal-flow/ for a project with no diagrams, confirm the "No diagrams yet" empty state renders with the "+ New Diagram" button
       - Open browser DevTools Network tab; confirm zero 404 responses for any asset

    3. **Create flow:**
       - Click "+ New Diagram", type a name (e.g. "Test FOH"), submit
       - Browser navigates to /audiopatch/signal-flow/<id>/
       - Confirm the editor shell renders with the back-link toolbar, diagram name in the header, and a blank white #sfd-paper div
       - Open DevTools Console; confirm a single log line: `[SFD] JointJS ready — version <X> — diagram <id> — html-to-image: loaded — stateUrl: /audiopatch/signal-flow/<id>/state/ — autosaveUrl: /audiopatch/signal-flow/<id>/save/`
       - Open DevTools Network tab; confirm /static/planner/js/vendor/joint.min.js returns 200, /static/planner/js/vendor/html-to-image.min.js returns 200, /static/planner/js/signal_flow_editor.js returns 200, no 404 responses anywhere

    4. **List page — populated state:**
       - Navigate back to /audiopatch/signal-flow/
       - Confirm the new "Test FOH" diagram appears as a card with Open / Rename / Delete buttons
       - Click "Rename", change name to "Test FOH 2", confirm the page reloads and shows the new name
       - Click "Delete", confirm via prompt, confirm the card disappears and you're back at the empty state

    5. **IDOR isolation (manual verification of DGM-05):**
       - Note the diagram_id from a known existing diagram (create one on Project A if necessary)
       - Switch the current project (via ShowStack project switcher) to Project B (if you have two projects available)
       - Visit /audiopatch/signal-flow/<diagram_id from Project A>/ directly in the URL bar
       - Confirm the browser is redirected back to /audiopatch/signal-flow/ (no leak of Project A's diagram)
       - This proves DGM-05 holds: cross-project access redirects, not 200-with-data.

    Expected outcome: ALL of the above behaviors work without browser console errors or unexpected network failures.
  </how-to-verify>

  <resume-signal>
    Type "approved" if all five verification scenarios pass.

    Otherwise describe what failed:
    - "404 on /static/planner/js/vendor/joint.min.js" -> Plan 02 vendor file missing or collectstatic not run
    - "TemplateDoesNotExist signal_flow/list.html" -> Task 1 file path wrong; Django couldn't find the template
    - "NoReverseMatch 'signal_flow_autosave'" -> Plan 03 URL pattern missing or misspelled
    - "[SFD] joint is not defined" -> joint.min.js downloaded as HTML error page (Plan 02 Task 1 sanity check failed)
    - "IDOR leak: Project B user saw Project A diagram" -> signal_flow_editor view inline filter is buggy; return to Plan 03 Task 1
    - Any 500 error -> capture the Django traceback and return to the offending plan
  </resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser DOM -> data-* attributes | URL strings are injected into HTML attributes; XSS risk if escaping is missed |
| Browser JS (signal_flow_editor.js, list.html inline) -> Django views via fetch() | AJAX boundary; CSRF and same-origin checks apply |
| Whitenoise -> browser (vendor JS) | Static file delivery; same-origin to ShowStack |
| `window.prompt` user input -> name field | Untrusted free-text crosses the AJAX boundary |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-18 | XSS via diagram.name in templates | editor.html data-diagram-name, list.html card name, editor.html toolbar h1 | mitigate | Django template auto-escaping applies to `{{ diagram.name }}` in HTML content. For values consumed by JS (data-diagram-name in editor.html, data-name on rename/delete buttons in list.html), `\|escapejs` filter is applied explicitly. Per OWASP cheat-sheet for Django: this combination is sufficient for both HTML-context and JS-string-context escaping. |
| T-07-19 | XSS via injected name through create endpoint | signal_flow_create accepts any string name, stored as-is, displayed in list.html | mitigate | Django template auto-escape on `{{ d.name }}` in the card render path. The .strip() and length check in signal_flow_create do not strip HTML — that's intentional (engineers may legitimately use `<`, `>`, etc in diagram names). Auto-escape handles all output safety. |
| T-07-20 | CSRF on inline list.html JS create/rename/delete | The inline `<script>` in list.html sends POST via fetch() | mitigate | `getCsrfToken()` reads the csrftoken cookie fresh on every fetch() call. The hidden `<form>{% csrf_token %}</form>` block ensures Django sets the cookie. `credentials: 'same-origin'` ensures the cookie is sent. Same-origin enforcement plus X-CSRFToken header == standard Django CSRF protection. |
| T-07-21 | Supply-chain — joint.min.js or html-to-image.min.js is tampered | Vendored JS files served by Whitenoise | mitigate | Plan 02 already addressed this (file pinned to specific version, attested unmodified in THIRD_PARTY_LICENSES.txt, committed to git for diff-reviewability). Plan 04 only references the files; no additional surface added. |
| T-07-22 | Information Disclosure — editor.html leaks data-* URLs to non-owner | All 5 data-* URLs include the diagram_id | accept | The diagram_id is non-secret (it's already in the URL bar). The URLs themselves are deterministic patterns, not bearer tokens. Authentication and per-request project scoping (Plan 03 `_get_diagram_for_request`) enforce who can actually use those URLs. |
| T-07-23 | CSRF / clickjacking on dashboard quick-action link | New link to /audiopatch/signal-flow/ | accept | GET-only navigation link, no side effects until the user clicks something on the target page. Standard Django X-Frame-Options: SAMEORIGIN (CLAUDE.md / settings) prevents iframe-based clickjacking. |
| T-07-24 | Stored XSS via dashboard.html if Multitrack analog inadvertently disturbed | templates/planner/dashboard.html edit | mitigate | Task 2 only INSERTS a new `<a>` element with hardcoded text "Signal Flow" — no Django template variables in the new markup that could carry untrusted data. Surrounding Multitrack link is preserved verbatim per the action steps. |

## Non-Security Compliance Notes

- The inline `<script>` in list.html does NOT use `@csrf_exempt` server-side — Plan 03's views require CSRF, and the JS sends X-CSRFToken header per Django convention.
- The editor.html `joint.min.js` script tag is intentionally not `defer`red — JointJS must be available synchronously so `signal_flow_editor.js` (which IS deferred) sees `joint` on the global namespace when its IIFE runs.
- CLAUDE.md `!important` CSS rule is documented in signal_flow_editor.js header comment for future Phase 8+ work, even though Phase 7 stub does not touch any admin DOM elements.
</threat_model>

<verification>
After all three tasks complete, verify the full Phase 7 user-visible layer:

    cd /Users/charlielawsonmacair/DjangoProjects/audiopatch
    python manage.py check                                                                                  # exits 0
    python manage.py collectstatic --noinput                                                                # exits 0
    test -f planner/templates/planner/signal_flow/list.html && echo list-ok
    test -f planner/templates/planner/signal_flow/editor.html && echo editor-ok
    test -f planner/static/planner/js/signal_flow_editor.js && echo stub-js-ok
    grep -c '/audiopatch/signal-flow/' templates/planner/dashboard.html                                     # at least 1
    grep -c 'data-autosave-url' planner/templates/planner/signal_flow/editor.html                            # 1
    grep -c '\[SFD\] JointJS ready' planner/static/planner/js/signal_flow_editor.js                         # 1
    # Browser smoke (Task 3 checkpoint) must pass before marking phase complete.
</verification>

<success_criteria>
- planner/templates/planner/signal_flow/list.html renders the diagram list with create/rename/delete affordances
- planner/templates/planner/signal_flow/editor.html includes 5 data-* URL attributes, loads vendored joint.min.js + html-to-image.min.js + signal_flow_editor.js, and includes a hidden CSRF form
- planner/static/planner/js/signal_flow_editor.js logs "[SFD] JointJS ready" to the console on page load
- templates/planner/dashboard.html has a quick-action link to /audiopatch/signal-flow/
- `python manage.py collectstatic --noinput` passes (verifies the new JS file collects correctly)
- Browser smoke test (checkpoint Task 3) confirms: list page renders, create flow works, editor shell renders with no 404s, IDOR isolation holds
- All `{% url %}` and `{% static %}` references resolve at template render time (proven by browser smoke test loading without TemplateSyntaxError or NoReverseMatch)
</success_criteria>

<output>
After completion, create `.planning/phases/07-foundation-crud-editor-shell/07-04-SUMMARY.md` documenting:
- Final file sizes for list.html, editor.html, signal_flow_editor.js
- Exact line range where the Signal Flow quick-action landed in templates/planner/dashboard.html
- Browser smoke test result (paste the user's "approved" message or describe issues found and resolution)
- Confirmation that `[SFD] JointJS ready` appears in the browser console
- The `joint.version` value as observed in the console (for Phase 8 reference)
</output>
