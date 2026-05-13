# Phase 3: Multitrack Templates — Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Engineer can save a `MultitrackSession`'s structure as a named **`MultitrackTemplate`** scoped to the engineer's account (visible across all of that engineer's projects), and apply a template when creating a new session to pre-seed the track list and metadata. Per-track values remain overrideable after apply.

**In scope:**
- New `MultitrackTemplate` + `MultitrackTemplateSlot` models (separate from `MultitrackSession`/`MultitrackTrack`)
- "Save as Template" action on the session editor page
- "Start from template (optional)" dropdown on the existing new-session form
- "Templates" list view on the multitrack landing page with rename + delete actions
- Apply logic: cross-console portable via `(source_type, source_number)` slot keys; unmappable slots skipped with a summary banner

**Out of scope (defer):**
- Re-applying a template to an existing session with tracks (apply is new-session-only per TPL-02 wording)
- `include_aux` / `include_matrix` / `include_groups` boolean flags — redundant with the slot list
- `color_scheme` JSON map — redundant with per-slot `color_override`
- `naming_pattern` format string — redundant with per-slot `label_override`
- Promote-to-shared / project-team-scoped sharing
- Re-applying templates as a "merge" against existing track lists
- Template versioning / edit history
- Template duplication
- Editing a saved template's slot list after creation (rename + delete only in v3.0)

</domain>

<decisions>
## Implementation Decisions

### Template Content (Area 1)

- **D-01:** **Hybrid template content.** Every template carries metadata; the track-list snapshot is optional. An engineer can save a "settings-only" template (zero slots) or a "full kit" template (1..N slots). One save flow handles both — the slot count is whatever the source session has at save time.
- **D-02:** **Cross-console portable slot keys.** Each `MultitrackTemplateSlot` is keyed by `(source_type, source_number)` — e.g. `('input', '5')`, `('aux', '3')`. Apply matches that pair against the target console's `ConsoleInput.input_ch` / `ConsoleAuxOutput.aux_number` / `ConsoleMatrixOutput.matrix_number` / `ConsoleStereoOutput.stereo_type`. This makes templates portable CL5 → QL5 → Rivage as long as the channel number/type exists on the target console.
- **D-03:** **Slot payload** (the per-row data persisted in `MultitrackTemplateSlot`):
  - `position` (PositiveInteger — slot order)
  - `source_type` (`'input'`/`'aux'`/`'matrix'`/`'stereo'`/`'manual'`)
  - `source_number` (CharField; matches the corresponding channel-number field's `max_length`)
  - `label_override` (CharField, blank allowed)
  - `color_override` (CharField, 7-char hex, blank allowed)
  - Optional: `notes` if useful — planner discretion. No `enabled` field — every slot is an opt-in-by-design row.
- **D-04:** **Save-with-zero-tracks is allowed.** Hitting "Save as Template" on a session that has no tracks creates a metadata-only template. Apply seeds metadata, drops the engineer into the picker (matches Phase 1 D-12 — new session lands with zero tracks, picker auto-opens).

### Scope, Model, Entry Points (Area 2)

- **D-05:** **Account/owner-scoped templates — NOT project-scoped.** `MultitrackTemplate` has NO `project` FK. Templates have a `created_by = ForeignKey(User)` and are visible to that user across **all of their own projects**. They are NOT visible to other engineers' accounts (no cross-tenant exposure). This is a deliberate divergence from `multitrack_session_builder_spec.md` (which proposed project-scoped) and from `AudioChecklistTemplate` (which is project-scoped). It is closer to Comm Config's "global with project=None" pattern, but bounded by ownership.
- **D-06:** **Separate `MultitrackTemplate` + `MultitrackTemplateSlot` models.** Not a discriminator on `MultitrackSession`. Avoids polluting every session query with `.filter(is_template=False)` and keeps the slot child rows cleanly separated from `MultitrackTrack`.
- **D-07:** **Save button lives on the session editor only.** Place it alongside the existing `Export to Reaper (Track Template)` / `Edit session metadata` actions on `/audiopatch/multitrack/<id>/`. The engineer is already in the session they want to capture. No dashboard-card-menu duplication for v3.0.
- **D-08:** **Apply UX = "Start from template (optional)" dropdown inside the existing New Session form** (`multitrack_create_view` per Phase 1 analog). When the engineer picks a template, the other form fields (target_daw, feed_source, track_order_mode, recorder_capacity, notes) **auto-populate from the template's metadata** (D-12). One form, one place to learn. No separate "+ New from Template" CTA on the dashboard for v3.0.
- **D-09:** **Templates landing surface on the multitrack dashboard.** A "Templates" section under or alongside the session grid (TPL-03). Lists templates with rename + delete actions. Visual treatment matches the existing session-card grid pattern.

### Apply Behavior (Area 3)

- **D-10:** **Unmappable slots are skipped with a summary banner.** When applying a template whose slots reference channels the target console doesn't have (e.g. template has `('matrix', '12')` but the QL5 target only has 8 matrices), drop those slots and surface a banner on the new session: *"Applied template '{name}' — {mapped} of {total} slots mapped; {skipped} skipped (matrix 9–12 not present on this console)."* Engineer can manually add the missing tracks via the Phase 1 picker if needed.
- **D-11:** **Template metadata pre-fills the form when picked.** Selecting a template from the dropdown updates the other form fields client-side (via simple form-input population — likely a small JS handler on the dropdown's `change` event). Engineer can still tweak any of the fields before submitting. Predictable; no silent override on submit.
- **D-12:** **Apply is new-session-only.** No "Re-apply Template" action on the editor for existing sessions. TPL-02's "seeding" language is honored literally. If an engineer wants to redo, they duplicate or delete-and-create. Avoids "are you sure you want to wipe 32 tracks?" modals.
- **D-13:** **Empty-track-list templates** use the same apply flow — metadata seeded, session created with zero tracks, picker auto-opens on Inputs per Phase 1 D-12. Banner reads: *"Applied template '{name}' — metadata seeded; no tracks in template."* Consistent across template variants.

### Spec Trim (Area 4)

- **D-14:** **Drop `include_aux` / `include_matrix` / `include_groups` boolean flags from the template model.** The track-list snapshot encodes inclusion implicitly. Adding the flags creates two sources of truth that can disagree. (Spec deviation — see `multitrack_session_builder_spec.md:103-105`.)
- **D-15:** **Drop `color_scheme` JSONField from the template model.** Per-slot `color_override` already covers track coloring. ShowStack doesn't have first-class "category" semantics for the spec's `{"vocals": "#FF0000"}` map. (Spec deviation — see `multitrack_session_builder_spec.md:106-107`.)
- **D-16:** **Drop `naming_pattern` format-string field from the template model.** Per-slot `label_override` already stores exactly what the engineer wants per track. Format strings are debugging tax. (Spec deviation — see `multitrack_session_builder_spec.md:108-109`.)

### Model Shape (consolidated)

The Phase 3 migration introduces two new models. Planner refines exact field constraints; below is the locked shape:

```python
class MultitrackTemplate(models.Model):
    # NO project FK (D-05); owner-scoped
    created_by = ForeignKey(User, on_delete=CASCADE)
    name = CharField(max_length=200)
    target_daw = CharField(max_length=20, choices=MultitrackSession.TARGET_DAW_CHOICES)
    feed_source = CharField(max_length=20, choices=MultitrackSession.FEED_SOURCE_CHOICES)
    track_order_mode = CharField(max_length=10, choices=MultitrackSession.TRACK_ORDER_MODE_CHOICES)
    recorder_capacity = PositiveIntegerField(null=True, blank=True)
    notes = TextField(blank=True, default='')
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('created_by', 'name')]   # one template name per owner
        ordering = ['name']

class MultitrackTemplateSlot(models.Model):
    template = ForeignKey(MultitrackTemplate, on_delete=CASCADE, related_name='slots')
    position = PositiveIntegerField(default=1)
    source_type = CharField(max_length=10, choices=MultitrackTrack.SOURCE_TYPE_CHOICES)
    source_number = CharField(max_length=10, blank=True, default='')   # blank for source_type='manual'
    label_override = CharField(max_length=100, blank=True, default='')
    color_override = CharField(max_length=7, blank=True, default='')

    class Meta:
        unique_together = [('template', 'position')]
        ordering = ['position']
```

Both models register on `showstack_admin_site` (NOT `admin.site`) per CLAUDE.md, and both get an entry in `planner/admin_ordering.py` order_map.

### Claude's Discretion

The planner / executor decides these — defaults to existing project patterns:

- Exact UI mark-up for the templates section on the dashboard (under the session grid as a second grid vs. a tab — match whatever Phase 1's session-card pattern produces).
- Modal vs full-page for "Rename template" (Comm Config uses modals; Audio Checklist uses inline). Pick whichever has the lighter footprint.
- JS for the new-session-form template dropdown auto-population (vanilla JS is fine — Phase 1 already uses vanilla JS in `multitrack_editor.js` per editor.html).
- Whether `MultitrackTemplateSlot.notes` is stored at all — drop if the planner judges it useless given that templates are usually re-keyed in a fresh session.
- Whether to add `MultitrackTemplate.recorder_capacity` to D-11's auto-populate set, or treat it as opt-in (default behavior is auto-populate everything).
- Index choices on `MultitrackTemplateSlot(template, position)` and `MultitrackTemplate(created_by)` for query performance.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Module Specification
- `multitrack_session_builder_spec.md` — Canonical module spec. Phase 3 follows the spec EXCEPT where this CONTEXT explicitly deviates (D-05, D-14, D-15, D-16). Use this CONTEXT as the authoritative reconciliation.
- `multitrack_session_builder_spec.md:92-114` — `MultitrackTemplate` model proposal (with the spec-optimism fields we're dropping).
- `multitrack_session_builder_spec.md:162-170` — Module landing page + Templates tab UX sketch.
- `multitrack_session_builder_spec.md:351-353` — Phase 3 task list (MultitrackTemplate model + admin + ...).

### Project-Level Conventions
- `.planning/REQUIREMENTS.md` — Requirements ledger; Phase 3 owns TPL-01..TPL-04.
- `.planning/ROADMAP.md` §"Phase 3" — Phase boundary, depends-on, success criteria (4 numbered items).
- `.planning/PROJECT.md` — Architectural non-negotiables: `CurrentProjectMiddleware` (templates DO NOT use this — they're owner-scoped not project-scoped), `showstack_admin_site`, `BaseEquipmentAdmin` role-based perms, dark theme via `admin/base_site.html`.
- `CLAUDE.md` — Project conventions; especially: register admin on `showstack_admin_site`; update `planner/admin_ordering.py` when new admin-registered models are added; additive migrations only; two template directories.

### Phase 1 Reference (already-shipped patterns Phase 3 builds on)
- `.planning/phases/01-core-sessions-track-editor-reaper-export/01-CONTEXT.md` — Phase 1 locked decisions.
- `planner/models.py:971` — `MultitrackSession` model — the session shape templates capture.
- `planner/models.py:1038` — `MultitrackTrack` model — the row-level shape templates' slots mirror.
- `planner/models.py:1024` — `_source_model_for(source_type)` helper — pattern for slot → channel-model dispatch.
- `planner/templates/planner/multitrack/dashboard.html` — landing page; Phase 3 adds the Templates section.
- `planner/templates/planner/multitrack/editor.html:70-80` — editor action bar; Phase 3 adds "Save as Template" here.
- `planner/views.py` — Phase 1 view layer; `multitrack_create_view` is where the New Session form lives (D-08 adds the template dropdown there).

### Existing Template Pattern References (TPL-04 — the analogs)
- `planner/views.py:4955-5074` — Audio Checklist template save / list / load / delete pattern. **Closest analog** to Phase 3's pattern: separate dedicated `*Template` model + parallel slot/task model. Use this as the structural reference.
- `planner/views.py:5347-5440` — Comm Config template save / list / load pattern (discriminator-based). Reference for the JSON-endpoint shape; Phase 3 does NOT copy the discriminator approach.
- `planner/models.py:3860-3964` — `AudioChecklistTemplate` + `AudioChecklistTemplateTask` model definitions.

### Codebase Targets (existing files Phase 3 touches)
- `planner/models.py` — Add `MultitrackTemplate` + `MultitrackTemplateSlot` models.
- `planner/admin.py` — Register both new admins on `showstack_admin_site`.
- `planner/admin_ordering.py` — Add `multitracktemplate` and `multitracktemplateslot` keys to the order_map.
- `planner/migrations/` — New additive migration creating the two new tables; zero existing-table mutations.
- `planner/views.py` — Add `multitrack_template_save`, `multitrack_template_list`, `multitrack_template_rename`, `multitrack_template_delete` (JSON endpoints, matching the Audio Checklist pattern shape). Modify `multitrack_create_view` to accept an optional `template` form field and seed the new session from it.
- `planner/urls.py` — Add `/audiopatch/multitrack/templates/...` routes.
- `planner/forms.py` — Add `template` ModelChoiceField to the existing new-session form (queryset scoped to `request.user`).
- `planner/templates/planner/multitrack/editor.html` — Add "Save as Template" button + modal.
- `planner/templates/planner/multitrack/dashboard.html` — Add Templates section with rename + delete actions.
- `planner/templates/planner/multitrack/new_session.html` (or whatever the new-session template is named — planner verifies) — Add the template dropdown.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MultitrackTrack.SOURCE_TYPE_CHOICES` — reuse verbatim on `MultitrackTemplateSlot.source_type` so the two stay in sync.
- `MultitrackSession.TARGET_DAW_CHOICES` / `FEED_SOURCE_CHOICES` / `TRACK_ORDER_MODE_CHOICES` — reuse verbatim on `MultitrackTemplate` metadata fields.
- `_source_model_for(source_type)` helper (`planner/models.py:1024`) — apply logic uses this to resolve a slot's target channel on the new console.
- Phase 1's `multitrack_editor.js` — pattern reference for vanilla-JS form interaction (template dropdown change handler).
- Audio Checklist save/load JSON endpoint pattern (`planner/views.py:4955-5074`) — copy the shape (`@require_POST`, JSON body, `current_project` scoping replaced with `request.user` scoping per D-05).

### Established Patterns
- All planner admin classes register on `showstack_admin_site` (not `admin.site`). Phase 3 honors this for both new admins.
- Update `planner/admin_ordering.py` when new admin-registered models land — non-negotiable per CLAUDE.md.
- Additive migrations only against beta-tester data; zero `ALTER TABLE` of existing fields.
- All planner views scope to `request.current_project` via `CurrentProjectMiddleware`. **Templates DO NOT** — they're owner-scoped via `request.user`. This is the one place Phase 3 diverges from the project's standard scoping pattern. Document this clearly in views (a one-line comment per template endpoint).
- Role gates: `superuser` / `premium owner` / `editor` can mutate; `viewer` is read-only. Apply to all template POST endpoints.
- `@login_required` + role check on all mutate endpoints.

### Integration Points
- New URL routes under `/audiopatch/multitrack/templates/...` (or `multitrack/template/<id>/...` for per-template actions). Planner finalizes the URL shape.
- The new-session form (Phase 1's `multitrack_create_view`) gains a single new field: `template` (ModelChoiceField, scoped to `MultitrackTemplate.objects.filter(created_by=request.user)`).
- The session editor (`editor.html`) gains a single new action button + a small modal.
- The dashboard (`dashboard.html`) gains a new section listing templates with rename + delete actions.
- The `Console CSV Import` flow (Phase 2) creates new Consoles — those consoles immediately become available targets in the new-session form, which means Phase 3 templates can be applied to a freshly-imported console with zero extra steps. Phase 3 doesn't need to be aware of Phase 2; the cross-console portable slot keys (D-02) handle this naturally.

</code_context>

<specifics>
## Specific Ideas

- Engineer mental model captured during discussion: *"I want to save my drum-kit input layout as a template I can apply to any QL5 console."* This was the deciding use case for D-01 (hybrid) and D-02 (cross-console portable slot keys).
- Account/owner-scoped templates (D-05) was a deliberate departure from the spec. The reasoning: in a multi-tenant SaaS like ShowStack, "global" almost always means "across the projects I personally own," not "across every tenant in the database." The `created_by` FK + `unique_together = [('created_by', 'name')]` enforces the right boundary.
- TPL-04 ("match existing template patterns") — closest behavioral match is Audio Checklist save/list/load/delete (separate dedicated `*Template` model). Comm Config's discriminator approach is also a valid analog but adds query-time complexity that Phase 3 doesn't need.
- Recommendation for the planner: keep the `MultitrackTemplate` admin **read-only** for slot rows (inline display, no add/edit). Engineers shouldn't be editing slot lists in Django admin — they should rename/delete templates from the multitrack module. This mirrors how `ConsoleImport` was treated in Phase 2.

</specifics>

<deferred>
## Deferred Ideas

- **Re-apply template on existing sessions** with replace/append choice — defer to a future phase; D-12 keeps Phase 3 simple by making apply new-session-only.
- **Editing a template's slot list** after creation — out of scope. v3.0 supports rename + delete only. Engineer who wants to "edit" a template duplicates the template, applies it to a fresh session, edits the session, and re-saves as a new template name.
- **Template duplication** — useful but not required. Could ship in a polish phase.
- **`include_aux` / `include_matrix` / `include_groups` flags** — dropped per D-14. Revisit only if engineers ask for category-level apply filters.
- **`color_scheme` JSON map** — dropped per D-15. Revisit if a "track categories" feature lands later.
- **`naming_pattern` format-string** — dropped per D-16. Could revisit as a simpler "label prefix" if engineers ask.
- **Promote-to-shared / project-team-scoped sharing** — D-05 explicitly scopes templates to a single owner. Sharing across collaborators on a project could be a follow-on phase (would need `MultitrackTemplate.shared_with_project = FK(Project, null=True)` or similar).
- **Template versioning / edit history** — out of scope; templates are mutable but no version graph.
- **POL-01 (`default_record` boolean on `ConsoleChannel`)** — already a Phase 5 / Polish requirement; mentioned here only because Phase 1's D-12 anticipates it. Not Phase 3 work.
- **Auto-pre-populate `recorder_capacity` on form load** — Claude's Discretion (D-11 list) whether to include it; the planner can decide.

</deferred>

---

*Phase: 03-multitrack-templates*
*Context gathered: 2026-05-13*
