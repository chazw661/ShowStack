---
phase: 05-channel-record-defaults
reviewed: 2026-05-14T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - planner/models.py
  - planner/migrations/0155_channel_record_defaults.py
  - planner/forms.py
  - planner/views.py
  - planner/tests/test_channel_record_defaults.py
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-05-14
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found (3 Info-level only — no Critical, no Warning)

## Summary

Phase 05 (channel-record-defaults) adds two seed fields (`default_record`, `default_record_color`) to all 4 `ConsoleChannel` models, exposes them on the admin inline ModelForms with hex validation, and wires them into `multitrack_add_tracks` so picker-added tracks inherit `enabled` and `color_override` from the source channel.

**Security posture is strong.** The XSS surface flagged in the plan (T-05-02-01 / T-05-03-01) is mitigated at three layers: form-level `clean_default_record_color`, picker-boundary `_HEX_COLOR_RE.match` defence-in-depth at `planner/views.py:6709`, and Django template autoescaping. IDOR is closed by reusing the existing `valid_input_ids` / `valid_aux_ids` / `valid_matrix_ids` / `valid_stereo_ids` set-intersection (already constrained to `console=session.console` at lines 6657-6672, where `session.console` is itself scoped to `request.current_project` at line 6629-6633). N+1 risk is eliminated by the bulk-fetch pattern (exactly 4 queries regardless of selection size).

**Migration is additive-only.** `planner/migrations/0155_channel_record_defaults.py` is 8 `AddField` operations with constant defaults (`True` for the boolean, `''` for the CharField). Safe to apply against Railway Postgres on next deploy with no downtime risk.

**Tests cover the contract.** 5 tests including an end-to-end Reaper RPP export assertion that proves the seeded color flows channel → seed → MultitrackTrack.color_override → exporter PEAKCOL.

The 3 Info findings below are noted-and-accepted observations, not blockers. Each is a deliberate trade-off documented in plans 05-02 / 05-03; logged here so future maintainers see the rationale.

## Info

### IN-01: Verbatim duplication of `clean_default_record_color` across 4 forms

**File:** `planner/forms.py:119, 189, 255, 302`
**Issue:** The `clean_default_record_color` validator is copy-pasted verbatim into all 4 `ConsoleXxxForm` classes (4 instances of the same 13-line method including identical docstring, regex, and error message). The hex regex `r'^#[0-9A-Fa-f]{6}$'` is also a verbatim copy of `_HEX_COLOR_RE` at `planner/views.py:6259`.

This is deliberate per Plan 02 — extracting to a shared mixin or importing `_HEX_COLOR_RE` from `views.py` would create a circular dependency (`views.py` already imports `MultitrackSessionForm` from `forms.py`). The 4× duplication is the documented trade-off.

**Fix:** No action required for v1. If a future refactor extracts a shared validator module, the canonical place is a new `planner/validators.py` (no Django-app dependencies) that both `forms.py` and `views.py` can import without a cycle:

```python
# planner/validators.py
import re
HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')

def validate_hex_color(value):
    value = (value or '').strip()
    if value and not HEX_COLOR_RE.match(value):
        raise ValueError(f"Color must be empty or #RRGGBB hex, got: {value!r}")
    return value
```

Then both `forms.py` and `views.py` can `from .validators import HEX_COLOR_RE, validate_hex_color` without circular risk.

---

### IN-02: `import re` inside `clean_default_record_color` method bodies

**File:** `planner/forms.py:127, 197, 263, 309`
**Issue:** Each of the 4 `clean_default_record_color` methods does a local `import re` inside the function body instead of at the module top. Plan 02 calls this an intentional choice ("keep the module top clean — `re` only appears inside these methods").

The cost is real but small: each invocation re-runs the import machinery (cached after first call, so cost is one dict lookup per call). The trade-off is favourable in this file because `re` truly is used nowhere else in `forms.py`.

**Fix:** No action required. If a future plan adds any other regex usage in `forms.py`, hoist `import re` to the module top alongside the existing `from django import forms` block at line 4.

---

### IN-03: Long dict-comprehension lines in `seed_maps` reduce readability

**File:** `planner/views.py:6680-6683`
**Issue:** Each line in the `seed_maps` dict literal is ~160 chars (e.g. line 6680 has a nested dict comprehension that spans the entire line). This violates the 100-char informal limit followed elsewhere in `multitrack_add_tracks` (lines 6657-6672 wrap at ~80 chars). Line 6680:

```python
'input':  {row[0]: (row[1], row[2]) for row in ConsoleInput.objects.filter(id__in=valid_input_ids).values_list('id', 'default_record', 'default_record_color')},
```

Readability suffers but the code is correct. The pattern is consistent across all 4 source_types.

**Fix:** Optional. If touched in a future refactor, prefer:

```python
seed_maps = {
    'input': {
        row[0]: (row[1], row[2])
        for row in ConsoleInput.objects
            .filter(id__in=valid_input_ids)
            .values_list('id', 'default_record', 'default_record_color')
    },
    'aux': {
        row[0]: (row[1], row[2])
        for row in ConsoleAuxOutput.objects
            .filter(id__in=valid_aux_ids)
            .values_list('id', 'default_record', 'default_record_color')
    },
    # ... matrix, stereo identical structure
}
```

This costs ~25 lines of diff for a multi-line comprehension, but each line stays under 100 chars and the intent is clearer.

---

## Cross-Cutting Observations (Not Findings)

The following were verified during review and confirmed clean — recorded here so future maintainers see the analysis:

- **IDOR closure (views.py:6680-6683):** The new bulk-fetch uses `id__in=valid_input_ids` etc. The `valid_*_ids` sets are intersections of (a) IDs the engineer submitted with (b) IDs that belong to `session.console`, and `session` was already filtered to `request.current_project`. The bulk-load cannot leak channels from another project.

- **XSS closure for `default_record_color`:** Three layers of defence cover the field:
  1. Form layer — `clean_default_record_color` rejects anything not `''` or `^#[0-9A-Fa-f]{6}$`.
  2. API boundary — `multitrack_add_tracks` at line 6709 re-validates via `_HEX_COLOR_RE.match(seed_hex)` and silently drops bad hexes (handles legacy data / direct SQL edits that bypass the form).
  3. Template — Django auto-escaping is the final fallback even if the regex were ever relaxed.

- **N+1 query risk:** The bulk-fetch is exactly 4 queries per request (one per source_type) regardless of selection size. Uses `.values_list('id', 'default_record', 'default_record_color')` to avoid loading other channel fields.

- **`bool(seed_record)` cast at views.py:6716:** Defensively coerces to bool. `default_record` is already a `BooleanField` so this is technically redundant — but harmless and documents intent.

- **Migration 0155:** All 8 AddField operations use constant scalar defaults (`True` and `''`), so PostgreSQL can apply them with a single fast `ALTER TABLE ... ADD COLUMN ... DEFAULT ...` per column. No table rewrite, no row-by-row backfill. Safe against Railway Postgres.

- **`multitrack_duplicate` intentionally untouched:** Per Plan 03, duplication should preserve source-session state, not re-seed from current channel defaults. Confirmed not modified.

- **`null=True` correctness on CharField:** Both `default_record_color` declarations use only `blank=True, default=''` (no `null=True`) — the Django-recommended pattern for CharField. Avoids the "two empty values" footgun.

- **Test file URL namespacing:** `reverse('planner:multitrack_add_tracks', ...)` and `reverse('planner:multitrack_export_rpp', ...)` are correct — `planner/urls.py:25` declares `app_name = 'planner'`.

- **Test field-type compatibility:** `_add_input` passes a string into `dante_number=input_ch`. Confirmed `ConsoleInput.dante_number` is a `CharField(max_length=3)` (line 809), not `IntegerField`. No type mismatch.

- **Test isolation:** Each test creates one `ConsoleInput` with a unique `input_ch` value (`'1'` through `'5'`). `TestCase` wraps each `test_*` in a transaction and rolls back, so the shared `setUpTestData` session is reused but per-test rows do not bleed.

---

_Reviewed: 2026-05-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
