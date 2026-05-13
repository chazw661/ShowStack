# Phase 3: Multitrack Templates — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 03-multitrack-templates
**Areas discussed:** Template content, Save / apply entry points, Apply behavior on cross-console, Spec optimism trim

---

## Template content

### Q1 — Primary use case for a template

| Option | Description | Selected |
|--------|-------------|----------|
| Track-list snapshot (Recommended) | Template remembers actual track positions, labels, colors. Apply on new console = pre-populated track list. | |
| Metadata defaults only | Save just target_daw, feed_source, etc. — no track list. Apply = new session with defaults but zero tracks. | |
| Hybrid — both | Templates contain metadata AND an optional track-list snapshot. | ✓ |

**User's choice:** Hybrid — both
**Notes:** Decision drives D-01.

### Q2 — Slot key for cross-console apply

| Option | Description | Selected |
|--------|-------------|----------|
| (source_type, source_number) — portable (Recommended) | Slot = 'input 5' or 'aux 3'. Apply finds that channel on target console. | ✓ |
| (source_type, source_id) — console-specific only | Slot = DB row ID; template only works on the saved-from console. | |
| (source_type, source_name) — fuzzy match by label | Slot = 'input named Kick'. Fragile when labels differ. | |

**User's choice:** (source_type, source_number) — portable across consoles
**Notes:** Drives D-02. Unmappable slots handled in Area 3 (D-10).

### Q3 — Per-slot data persisted

| Option | Description | Selected |
|--------|-------------|----------|
| Position + source-key + label_override + color_override (Recommended) | Everything that makes a track row visually distinct. | ✓ |
| Position + source-key only | No label/color overrides; new console's defaults win on apply. | |
| Full row — above plus enabled, notes, label/color overrides | Maximum fidelity including disabled tracks. | |

**User's choice:** Position + source-key + label_override + color_override
**Notes:** Drives D-03. No `enabled` field — every slot is opt-in by design.

### Q4 — Save with zero tracks

| Option | Description | Selected |
|--------|-------------|----------|
| Allow — saves a metadata-only template (Recommended) | Useful for 'just save my Reaper export settings.' | ✓ |
| Block with error | Force engineers to build a real template first. | |

**User's choice:** Allow — saves a metadata-only template
**Notes:** Drives D-04.

---

## Save / apply entry points

### Q1 — Template scope

| Option | Description | Selected |
|--------|-------------|----------|
| Project-scoped (Recommended) | Templates belong to a project; only visible in that project. Matches spec + Audio Checklist. | |
| Global / cross-project | No project FK; visible from any project. Matches Comm Config's pattern. | ✓ |
| Both — project-scoped with 'Promote to global' | Maximum flexibility, heaviest UI. | |

**User's choice:** Global / cross-project
**Notes:** Triggered a sanity-check follow-up (next Q) since ShowStack is multi-tenant.

### Q1b — Scope clarifier (sanity check)

| Option | Description | Selected |
|--------|-------------|----------|
| Across all projects within the same user/owner (Recommended) | Templates have NO project FK but DO have a `created_by` user FK. Only visible to the owner across their own projects. | ✓ |
| Truly global — every authenticated user sees every template | Cross-tenant exposure risk. | |
| Across project members (project-team-scoped) | Visible to team via ProjectMembership joins. | |

**User's choice:** Across all projects within the same user/owner
**Notes:** Drives D-05. Templates are owner-scoped, not project-scoped, not truly global.

### Q2 — Model implementation

| Option | Description | Selected |
|--------|-------------|----------|
| Separate MultitrackTemplate + MultitrackTemplateSlot models (Recommended) | Mirrors spec + Audio Checklist pattern. Clean separation from session/track models. | ✓ |
| Discriminator on MultitrackSession (is_template=True) | Match Comm Config: same model serves both roles. | |

**User's choice:** Separate MultitrackTemplate + MultitrackTemplateSlot models
**Notes:** Drives D-06.

### Q3 — Save button placement

| Option | Description | Selected |
|--------|-------------|----------|
| Inside the session editor only (Recommended) | Next to existing Export to Reaper / Edit metadata actions. | ✓ |
| On the dashboard (pick a session, click Save as Template) | Each session card gets a Save as Template action. | |
| Both — editor + dashboard card menu | Two paths. | |

**User's choice:** Inside the session editor only
**Notes:** Drives D-07.

### Q4 — Apply entry point

| Option | Description | Selected |
|--------|-------------|----------|
| Inside the New Session form — template dropdown (Recommended) | Add a 'Start from template (optional)' field to the existing new-session form. | ✓ |
| Separate '+ New from Template' CTA on the dashboard | Two-step wizard: pick template → pick console. | |
| Both | Cover both flows. | |

**User's choice:** Inside the New Session form — template dropdown
**Notes:** Drives D-08. Template selection pre-fills the rest of the form (D-11).

---

## Apply behavior on cross-console

### Q1 — Unmappable slots

| Option | Description | Selected |
|--------|-------------|----------|
| Skip with summary banner (Recommended) | Apply proceeds, unmappable slots dropped, banner explains what was skipped. | ✓ |
| Create as Manual tracks | Unmappable slots become 'manual' source_type tracks with label preserved. | |
| Fail loudly — refuse to apply | 'This template has 4 channels your console doesn't have. Pick a different one.' | |

**User's choice:** Skip with summary banner
**Notes:** Drives D-10.

### Q2 — Metadata interaction with form

| Option | Description | Selected |
|--------|-------------|----------|
| Template values pre-fill the form when picked (Recommended) | Dropdown selection auto-populates other form fields client-side. | ✓ |
| Template overrides the form silently on submit | Form fields stay as engineer set them; template wins on submit. Magic; confusing. | |
| Form values win; template metadata ignored on apply | Template only applies track-list snapshot. | |

**User's choice:** Template values pre-fill the form when picked
**Notes:** Drives D-11.

### Q3 — Re-apply

| Option | Description | Selected |
|--------|-------------|----------|
| Apply only at new-session creation (Recommended) | Template is a starting-point seed. No re-apply on existing sessions. | ✓ |
| Allow re-apply with 'replace' or 'append' choice | Editor gets an Apply Template button with a choice modal. | |

**User's choice:** Apply only at new-session creation
**Notes:** Drives D-12. Honors TPL-02's "seeding" language literally.

### Q4 — Metadata-only template apply

| Option | Description | Selected |
|--------|-------------|----------|
| Same flow as full template, just no tracks seeded (Recommended) | Metadata pre-fills form, session created empty, picker auto-opens. | ✓ |
| Special-case — show a slightly different success message | Same behavior, slightly tailored banner copy. | |

**User's choice:** Same flow as full template, just no tracks seeded
**Notes:** Drives D-13.

---

## Spec optimism trim

### Q1 — Include flags

| Option | Description | Selected |
|--------|-------------|----------|
| Drop — track-list snapshot encodes inclusion (Recommended) | Slots imply inclusion; flags create two sources of truth. | ✓ |
| Keep as apply-time filters | 'Apply this template but skip the aux tracks this gig.' | |

**User's choice:** Drop
**Notes:** Drives D-14. Spec deviation.

### Q2 — color_scheme JSONField

| Option | Description | Selected |
|--------|-------------|----------|
| Drop — per-slot color_override covers it (Recommended) | Each slot stores its own color. Category-to-color abstraction doesn't exist in ShowStack. | ✓ |
| Keep as a fallback when a slot has no color_override | Adds a category-derivation step we don't have a model for. | |

**User's choice:** Drop
**Notes:** Drives D-15. Spec deviation.

### Q3 — naming_pattern format string

| Option | Description | Selected |
|--------|-------------|----------|
| Drop — per-slot label_override covers it (Recommended) | Each slot stores exactly what the engineer wants. Format strings = debugging tax. | ✓ |
| Simplify to a single 'label prefix' string | Trivial prefix at apply time. | |
| Keep verbatim per spec | Full format-string support. | |

**User's choice:** Drop
**Notes:** Drives D-16. Spec deviation.

---

## Claude's Discretion

The planner / executor decides:
- Exact UI mark-up for the templates section on the dashboard (under the session grid as a second grid vs. a tab).
- Modal vs full-page for "Rename template".
- JS approach for the new-session-form template dropdown auto-population.
- Whether `MultitrackTemplateSlot.notes` is stored at all.
- Whether `recorder_capacity` is in the metadata auto-populate set or opt-in.
- Index choices on the new tables.

## Deferred Ideas

- Re-apply template on existing sessions
- Editing a template's slot list after creation
- Template duplication
- include_aux / include_matrix / include_groups flags
- color_scheme JSON map
- naming_pattern format-string
- Promote-to-shared / project-team-scoped sharing
- Template versioning / edit history
- POL-01 (default_record on ConsoleChannel — Phase 5)
- Auto-pre-populate recorder_capacity on form load
