---
phase: 11-ports-and-resize
fixed_at: 2026-05-24T17:30:00Z
review_path: .planning/phases/11-ports-and-resize/11-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 11: Code Review Fix Report

**Fixed at:** 2026-05-24T17:30:00Z
**Source review:** .planning/phases/11-ports-and-resize/11-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1 (1 critical, 0 warnings; Info findings excluded by scope `critical_warning`)
- Fixed: 1
- Skipped: 0

## Fixed Issues

### CR-01: `portAutocompleteUrl` produces malformed double-`?` query string, breaking GAP-11.1 silently

**Files modified:** `planner/static/planner/js/signal_flow_editor.js`
**Commit:** 7ccc537
**Applied fix:** Replaced the unconditional `'?q=' + encodeURIComponent(q)` in `fetchAcResults` (line 2607) with a separator check: `var sep = (url.indexOf('?') === -1) ? '?' : '&';` then `var fetchUrl = url + sep + 'q=' + encodeURIComponent(q);`. This matches the reviewer's recommended patch verbatim. Result:

- Phase 10 connector-label path (`labelAutocompleteUrl` with no query string) → `sep === '?'`, fetched URL is `…/?q=<term>` — identical to pre-fix behaviour, no regression.
- Phase 11 port-autocomplete path (`labelAutocompleteUrl + '?shape_class=…'`) → `sep === '&'`, fetched URL is `…/?shape_class=showstack.Device&q=<term>` — Django's QueryDict now parses both params correctly, restoring both the GAP-11.1 shape-scoping (allowlist-driven catalog filter) and the search-term `__icontains` filter.

Added a 4-line inline comment tagging the fix to GAP-11.1 / CR-01 so future readers understand why the separator check exists (the call site that produces a pre-`?` URL is ~475 lines away in `refreshPortAuthorBlock`).

**Verification performed:**
- Tier 1: Re-read lines 2600-2623, confirmed `sep` declaration + `fetchUrl` construction present, surrounding code (`getJSON`/`renderAcResults`/`closeAcListbox` callbacks) unchanged.
- Tier 2: `node -c planner/static/planner/js/signal_flow_editor.js` exited 0 — full-file JS syntax check passes.
- Working tree clean after commit (only pre-existing `.DS_Store` modification remains, unrelated to this fix).

## Skipped Issues

None — the single in-scope finding (CR-01) was fixed cleanly. IN-01 and IN-02 were excluded by the `critical_warning` fix scope and remain documented in REVIEW.md for future consideration.

---

_Fixed: 2026-05-24T17:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
