---
phase: 05-channel-record-defaults
plan: 02
subsystem: forms

tags: [admin-forms, channel-record-defaults, pol-01, pol-02, hex-validator, defence-in-depth]

# Dependency graph
requires:
  - phase: 05-channel-record-defaults
    provides: ConsoleInput/ConsoleAuxOutput/ConsoleMatrixOutput/ConsoleStereoOutput.default_record (Bool, default=True) + default_record_color (CharField max_length=7, blank=True, default='') — added by Plan 05-01 commits 8003594 + f4c0a99
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: _HEX_COLOR_RE at planner/views.py:6259 — the canonical hex-format regex this plan's clean_default_record_color validators mirror verbatim
provides:
  - "Editable default_record (checkbox) + default_record_color (#RRGGBB text input) on each of 4 ConsoleChannel ModelForms in planner/forms.py — surfaces the Plan 05-01 schema fields in the Console admin TabularInline rows"
  - "Form-layer hex validator clean_default_record_color on all 4 forms — rejects non-hex strings server-side regardless of input source (raw HTTP / curl bypass of HTML pattern attr also caught)"
  - "Consistent widget styling on default_record_color: 80px width, monospace, #RRGGBB placeholder/pattern/title hint"
affects: [05-03, console-admin-change-form, multitrack-session-seed-logic]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Form-layer regex validator on each of 4 ConsoleChannel ModelForms — verbatim duplicate of planner/views.py:6259 _HEX_COLOR_RE, inlined per-form to avoid circular-import risk (views.py imports MultitrackSessionForm from forms.py)"
    - "Local `import re` inside clean_default_record_color (not module-top) — matches Phase 1's import-locality style; re used only inside this one method per form"
    - "Verbatim shared error string `Color must be empty or #RRGGBB hex, got: <value!r>` across all 4 forms — single grep target keeps regression tests cheap"

key-files:
  created: []
  modified:
    - "planner/forms.py — +108 lines / -8 lines across 4 ModelForm classes (ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm, ConsoleStereoOutputForm)"

key-decisions:
  - "Append new fields to Meta.fields tail (no reordering) — keeps the visual column order in the inline stable for engineers used to today's layout (per plan instruction)"
  - "Verbatim regex copy in each form (not `from .views import _HEX_COLOR_RE`) — views.py already imports MultitrackSessionForm from forms.py, so the reverse import would create a circular dependency; Django docs explicitly endorse per-form local regexes"
  - "Local `import re` inside each clean_default_record_color (not at planner/forms.py top) — re is used only inside this one method per form; matches Phase 1 forms.py import-locality posture"
  - "Added explicit `def __init__` to ConsoleStereoOutputForm (previously implicit) — needed so default_record_color widget styling lands; kept the existing Meta.widgets dict for dante_number untouched (different field, different concern)"
  - "Widget styling: 80px width, monospace, #RRGGBB placeholder + HTML pattern attr + title tooltip — HTML pattern is UI hint only (server-side clean_default_record_color is the security control per threat T-05-02-03)"
  - "DID NOT touch planner/admin.py — the 4 inlines pull `form = ConsoleXxxForm` via Meta and the new fields appear automatically; no admin class edit needed"
  - "DID NOT touch planner/admin_ordering.py — per CLAUDE.md, that file is only updated when a new admin-REGISTERED model is added; this plan adds fields to existing inlines, not new registrations"

patterns-established:
  - "Form-layer hex validator pattern: `import re` local, `(value or '').strip()`, `re.match(r'^#[0-9A-Fa-f]{6}$', value)`, raise forms.ValidationError with f-string carrying repr(value) — reusable for any future #RRGGBB form field elsewhere in planner/forms.py"
  - "Two-field seed-default surface on admin TabularInline: BooleanField renders as default checkbox (no widget override needed — TabularInline already vertically centers the checkbox column), CharField hex gets explicit 80px-monospace styling for visual consistency with the existing inline-row aesthetic"

requirements-completed: [POL-01, POL-02]

# Metrics
duration: ~2min
completed: 2026-05-14
---

# Phase 5 Plan 02: Channel Record Defaults — Admin Form Surface Summary

**Exposed the Plan 05-01 schema fields (`default_record` boolean + `default_record_color` hex) as editable fields on all 4 ConsoleChannel ModelForms (`ConsoleInputForm`, `ConsoleAuxOutputForm`, `ConsoleMatrixOutputForm`, `ConsoleStereoOutputForm`), with consistent inline-row widget styling and a server-side `clean_default_record_color` hex-format validator on each form. Phase 5 Success Criterion 1 ("engineer can set default_record and default_record_color from the channel admin/edit UI") is now delivered end-to-end.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-14T19:51:14Z
- **Completed:** 2026-05-14T19:53:22Z
- **Tasks:** 1 / 1
- **Files modified:** 1 (planner/forms.py)
- **Files created:** 0

## Accomplishments

- All 4 channel ModelForms in `planner/forms.py` now carry `default_record` and `default_record_color` as the trailing two entries of their `Meta.fields` lists. Verified by direct in-process introspection — `from planner.forms import ConsoleInputForm, ConsoleAuxOutputForm, ConsoleMatrixOutputForm, ConsoleStereoOutputForm; assert all(set(['default_record','default_record_color']).issubset(F.Meta.fields) for F in ...)` passes.
- Each of the 4 forms gains a `clean_default_record_color` method whose body is identical across all 4 — local `import re`, strip the cleaned value, regex-match `r'^#[0-9A-Fa-f]{6}$'`, raise `forms.ValidationError(f"Color must be empty or #RRGGBB hex, got: {value!r}")` on mismatch, return the value on pass. Empty strings pass through unchanged (no-seed-color semantics preserved).
- Widget styling pattern applied to `default_record_color` on all 4 forms: 80px width, centered text, `font-mono`, placeholder `#RRGGBB`, HTML `pattern="#[0-9A-Fa-f]{6}"` for browser-level hint, and a `title` tooltip "Hex color like #FF0000, or leave blank for no seed". The `default_record` BooleanField renders as default Django checkbox — no override needed; admin TabularInline already vertically centers checkbox columns.
- `ConsoleStereoOutputForm` previously had no `__init__` (relying on the implicit Meta.widgets dict for `dante_number` styling alone) — added an explicit `__init__` matching the other 3 forms' shape so the new `default_record_color` widget styling lands. The existing `Meta.widgets = {'dante_number': forms.NumberInput(...)}` block was left untouched.
- Plan's `<verify>` automated script runs to completion and prints `OK -- all 4 forms expose new fields and the hex regex contract is correct`. All 7 regex contract assertions pass (3 positive: `#FF8800`, `#abcdef`, `#A1B2C3`; 4 negative: `not-a-hex`, `#GG0000`, `#FF00`, `FF8800`).
- `python manage.py check planner` → 0 issues. The only output is the pre-existing `RuntimeWarning: Model 'planner.audiochecklist' was already registered` and the pre-existing `ADMIN_ORDERING.PY LOADED` print — both pre-date this plan and are out-of-scope per the scope-boundary rule.
- All acceptance-criteria grep counts pass: `'default_record'` literal → 4 (one Meta.fields entry per form), `'default_record_color'` literal → 12 (one Meta.fields entry + one `self.fields['default_record_color'].widget.attrs.update(...)` + one `self.cleaned_data.get('default_record_color')` per form × 4 forms — well above the "≥ 4" floor), `def clean_default_record_color` → 4, `must be empty or #RRGGBB hex` → 4, regex literal `^#[0-9A-Fa-f]{6}$` → 4.

## Task Commits

Single atomic commit on `main` (sole-developer workflow per CLAUDE.md):

1. **Task 1: Add default_record and default_record_color to all 4 ConsoleChannel ModelForms** — `7121792` (feat) — `planner/forms.py` only, +108 lines / −8 lines.

No file deletions (`git diff --diff-filter=D HEAD~1 HEAD` empty).

## Files Created/Modified

### `planner/forms.py` (modified — commit `7121792`)

Final canonical `Meta.fields` order on each of the 4 forms (canonical tail position `default_record, default_record_color` for any future record-default fields):

```python
# ConsoleInputForm.Meta.fields
['dante_number', 'input_ch', 'source', 'source_hardware', 'group',
 'dca', 'mute', 'direct_out', 'omni_in',
 'default_record', 'default_record_color']

# ConsoleAuxOutputForm.Meta.fields
['dante_number', 'aux_number', 'name', 'mono_stereo', 'bus_type', 'omni_out',
 'default_record', 'default_record_color']

# ConsoleMatrixOutputForm.Meta.fields
['dante_number', 'matrix_number', 'name', 'mono_stereo', 'omni_out',
 'default_record', 'default_record_color']

# ConsoleStereoOutputForm.Meta.fields
['dante_number', 'stereo_type', 'name', 'omni_out',
 'default_record', 'default_record_color']
```

Each form gains the same `clean_default_record_color` body (verbatim across all 4):

```python
def clean_default_record_color(self):
    """POL-02: validate hex format at the form boundary. Empty string allowed.

    Defence-in-depth: matches _HEX_COLOR_RE at planner/views.py:6259 and
    the Plan-03 picker-add validator. Mirrors the threat-T-05-02-01
    mitigation in this plan's threat_model.
    """
    import re
    value = (self.cleaned_data.get('default_record_color') or '').strip()
    if value and not re.match(r'^#[0-9A-Fa-f]{6}$', value):
        raise forms.ValidationError(
            f"Color must be empty or #RRGGBB hex, got: {value!r}"
        )
    return value
```

And each form's `__init__` gains the same widget-styling block on `default_record_color`:

```python
self.fields['default_record_color'].widget.attrs.update({
    'style': 'width: 80px; text-align: center;',
    'class': 'bg-white text-black rounded-sm font-mono',
    'placeholder': '#RRGGBB',
    'pattern': '#[0-9A-Fa-f]{6}',
    'title': 'Hex color like #FF0000, or leave blank for no seed',
})
```

`ConsoleStereoOutputForm` had no prior `__init__` — one was added wholesale, matching the other 3 forms' shape; the existing `Meta.widgets = {'dante_number': forms.NumberInput(...)}` dict was preserved unchanged.

### Files NOT modified (per CLAUDE.md compliance)

- **`planner/admin.py`** — not touched. The 4 `TabularInline` subclasses (`ConsoleInputInline`, `ConsoleAuxOutputInline`, `ConsoleMatrixOutputInline`, `ConsoleStereoOutputInline`) at `planner/admin.py:583-761` reference each form via `form = ConsoleXxxForm`; the new fields appear automatically via `Meta.fields` without any admin class edit.
- **`planner/admin_ordering.py`** — not touched. CLAUDE.md rule: "Update it whenever a new admin-REGISTERED model is added". This plan added fields to existing inlines, not new registrations — sidebar grouping is unchanged.
- **`planner/models.py`** — not touched. Plan 05-01 owns the model layer; Plan 05-02 is form-surface-only.

## Decisions Made

- **Verbatim regex copy in each form, not `from .views import _HEX_COLOR_RE`.** Per the plan's explicit `DO NOT` clause: `planner/views.py` already imports `MultitrackSessionForm` from `planner/forms.py`, so a reverse import would create a circular-dependency risk. Django docs explicitly endorse per-form local regexes for validators. Plan 03 will re-validate at the AJAX boundary for defence-in-depth — this duplication is the established pattern.
- **Local `import re` inside each `clean_default_record_color` method** (not a module-top `import re` in `forms.py`). `re` is used only inside this single method per form, so import-locality matches Phase 1's `forms.py` style (compare against views.py:6249 where `re` is module-level because of heavy multi-function use).
- **Append new fields to `Meta.fields` tail, no reordering.** Keeps the visual column order in the Console admin inline rows stable for engineers used to today's layout. Future field additions to record-default semantics should follow the same tail-append pattern (canonical position established).
- **`default_record` widget = Django default checkbox** (no `widget.attrs.update`). Plan note confirms: "the admin TabularInline checkbox column is already vertically centered." No custom CSS needed.
- **`default_record_color` widget = 80px width, monospace, #RRGGBB placeholder + HTML pattern attr.** Matches the existing `bg-white text-black rounded-sm` channel-row aesthetic. The HTML `pattern` attribute is UI hint only — `clean_default_record_color` is the actual security control per threat T-05-02-03 (raw HTTP / curl bypass of the pattern attr is still caught server-side).
- **Added explicit `def __init__` to `ConsoleStereoOutputForm`** (previously had no `__init__`, only an implicit `Meta.widgets` dict). Needed so `self.fields['default_record_color'].widget.attrs.update(...)` can land. The existing `Meta.widgets = {'dante_number': forms.NumberInput(...)}` block was preserved unchanged — it styles a different field via a different mechanism (instantiation-time widget override vs `__init__`-time attrs.update), and there's no semantic conflict between the two.
- **`admin_ordering.py` not touched.** CLAUDE.md: "Update it whenever a new admin-REGISTERED model is added." This plan added fields to existing inlines, no new model registrations — compliance check passes naturally.
- **`admin.py` not touched.** The 4 `TabularInline` classes already pull `form = ConsoleXxxForm` via Meta; Django binds the new fields automatically from `Meta.fields`. Touching admin.py would have been over-edit.

## Deviations from Plan

None — plan executed exactly as written. All `<verify>` automated checks pass and all `<acceptance_criteria>` items are green:

- ✅ `grep -c "'default_record'" planner/forms.py` → 4 (≥ 4 required)
- ✅ `grep -c "'default_record_color'" planner/forms.py` → 12 (≥ 4 required — well above the floor)
- ✅ `grep -c "def clean_default_record_color" planner/forms.py` → 4 (exact match required)
- ✅ `grep -c "must be empty or #RRGGBB hex" planner/forms.py` → 4 (exact match required)
- ✅ `grep -cE "\^#\[0-9A-Fa-f\]\{6\}\\\$" planner/forms.py` → 4 (≥ 4 required)
- ✅ `python manage.py check planner` exits 0
- ✅ Verify script runs to completion and prints `OK -- all 4 forms expose new fields and the hex regex contract is correct`

## Issues Encountered

- Local `python` not on PATH (Mac dev quirk inherited from Plan 05-01) — resolved by using `venv/bin/python` for all manage.py invocations. Same as Plan 05-01; not a plan deviation.
- Three `READ-BEFORE-EDIT REMINDER` PreToolUse hook warnings emitted on consecutive `Edit` calls against `planner/forms.py`. The file was read at session start (lines 1-230 then 280-340) so the warnings were spurious; all four form edits succeeded. Same hook-noise behaviour as Plan 05-01; not a plan deviation.
- Pre-existing `RuntimeWarning: Model 'planner.audiochecklist' was already registered` emitted by every `manage.py` invocation. Out of scope per the scope-boundary rule — pre-existing, unrelated to forms changes, reported by Django itself. Logged here for future cleanup tracking (same as Plan 05-01).

## Notes for Plan 03 (session-seed logic + AJAX boundary re-validation)

**Critical defence-in-depth contract:** the form-layer regex in this plan is a verbatim duplicate of `planner/views.py:6259` `_HEX_COLOR_RE`. Plan 03's `add_tracks` AJAX endpoint MUST re-validate at the boundary — do NOT trust that admin-form validation will have run for API-driven channel edits or for legacy DB rows (manual SQL, fixture import, etc.).

The Plan-01 Notes already provide the textbook pattern for the AJAX side:

```python
# In multitrack_add_tracks (or wherever Phase 1 instantiates MultitrackTrack from a picker selection):
if channel.default_record_color and _HEX_COLOR_RE.match(channel.default_record_color):
    track.color_override = channel.default_record_color
```

The leading `if` clause protects against any future channel record that somehow bypassed Plan 02's form validator. Same pattern Phase 1 uses for `MultitrackTrack.color_override` writes.

**For the boolean seed:** no validation needed — `default_record` is a Django `BooleanField`, so it's already coerced to `True`/`False` by the ORM. Just read it directly:

```python
track.enabled = channel.default_record
```

**Form-validator error string is verbatim shared across all 4 forms.** If Plan 03 needs to display the same error to the API client (e.g. inside `add_tracks` `JsonResponse`), match it byte-for-byte: `"Color must be empty or #RRGGBB hex, got: <value!r>"`. Keeps a single grep target for both the form and AJAX paths if regression tests ever need to assert on the string.

## User Setup Required

None — the form-layer changes are purely additive (no migration, no schema drift, no new admin model). On the next push to `main`:

1. Railway redeploys via `railway.json` `startCommand`.
2. `collectstatic` is a no-op for this plan (no CSS or JS changes — widget styling lives in inline `style=` and Tailwind utility classes already loaded by the admin pages).
3. The next visit to the Console admin change-form shows the two new columns (`default_record` checkbox + `default_record_color` hex text input) on each TabularInline row.

No environment variables, secrets, or external service configuration required. No local-dev migration step — Plan 05-01's migration 0155 already ran on prior local-dev `runserver` invocation.

## Threat Flags

None.

The plan's `<threat_model>` correctly captured the full attack surface (T-05-02-01 through T-05-02-04). Post-implementation scan confirms:

- **T-05-02-01 (I — XSS via color injection)** — mitigated. `clean_default_record_color` rejects everything except `''` or `^#[0-9A-Fa-f]{6}$`. Hex strings matching this regex cannot contain `<`, `>`, `"`, `'`, or `\`, eliminating the XSS injection class. Django template auto-escaping is a second line of defence at render time.
- **T-05-02-02 (E — Elevation of Privilege)** — accepted (no new permission scope). Console admin access is already gated by `BaseEquipmentAdmin` role checks per CLAUDE.md (superuser / premium owner / editor / viewer). Adding two new fields to an existing inline does not change the auth surface.
- **T-05-02-03 (T — Tampering via raw HTTP/curl)** — mitigated. The validator runs server-side in `clean_default_record_color` regardless of input source. The HTML `pattern` attribute on the widget is UI hint only, not the security control.
- **T-05-02-04 (D — Denial of Service via fat-finger)** — mitigated. Django CharField `max_length=7` (set in Plan 01) truncates at the model layer; the form-layer regex rejects anything not matching `^#[0-9A-Fa-f]{6}$` (length 7). Bounded input size.

No new threat surface introduced beyond the plan's pre-registered T-IDs. ASVS L1 §5.1.3 (input validation) and §5.2.5 (output encoding) both satisfied.

## Self-Check: PASSED

Verified before STATE.md update:

- `.planning/phases/05-channel-record-defaults/05-02-SUMMARY.md` (this file) exists — FOUND (the file you're reading)
- `planner/forms.py` modified in commit `7121792` — FOUND (`git show --stat 7121792` confirms +108/-8 on planner/forms.py only)
- Commit `7121792` exists in `git log --oneline --all` — FOUND
- `grep -c "'default_record'" planner/forms.py` returns `4` — FOUND
- `grep -c "'default_record_color'" planner/forms.py` returns `12` (≥ 4) — FOUND
- `grep -c "def clean_default_record_color" planner/forms.py` returns `4` — FOUND
- `grep -c "must be empty or #RRGGBB hex" planner/forms.py` returns `4` — FOUND
- `grep -cE "\^#\[0-9A-Fa-f\]\{6\}\\\$" planner/forms.py` returns `4` — FOUND
- `python manage.py check planner` exits 0 — FOUND
- In-process verify script prints `OK -- all 4 forms expose new fields and the hex regex contract is correct` — FOUND

## Next Phase Readiness

- **Plan 05-03 unblocked.** All 4 `Console{Input,AuxOutput,MatrixOutput,StereoOutput}Form` classes expose `default_record` and `default_record_color` and reject non-hex strings server-side. Plan 03 can land the seed logic in `multitrack_add_tracks` (read `channel.default_record` → `track.enabled`, read `channel.default_record_color` → `track.color_override` with `_HEX_COLOR_RE` re-validation) and the regression test suite.
- **Phase-level Success Criterion 1 — DELIVERED.** Engineer can set `default_record` (boolean) and `default_record_color` (hex) on each `ConsoleChannel` from the channel admin/edit UI. Visible end-to-end on next Railway deploy.
- **Phase-level Success Criterion 2** (pre-check tracks where `default_record=True`) — schema floor (Plan 01) and admin surface (Plan 02) now both in place; Plan 03 owns the seed logic.
- **Phase-level Success Criterion 3** (seed color from `default_record_color`) — schema floor (Plan 01) and admin surface + validator (Plan 02) now both in place; Plan 03 owns the seed copy + AJAX-boundary re-validation.
- **POL-01 admin surface (boolean toggle visible) and POL-02 admin surface (hex input visible + validated) both in place.** Requirements ledger updates POL-01 + POL-02 from Pending to Complete after Plan 03 ships and the seed logic actually consumes them.

---
*Phase: 05-channel-record-defaults*
*Completed: 2026-05-14*
