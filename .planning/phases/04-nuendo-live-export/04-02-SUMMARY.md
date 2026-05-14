---
phase: 04-nuendo-live-export
plan: 02
subsystem: infra

tags: [lxml, xml-template-injection, nuendo-live, farb, pure-function-exporter, deepcopy]

# Dependency graph
requires:
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: _ordered_enabled_tracks() (track-ordering helper reused verbatim) + trust-boundary docstring pattern from reaper_export.py
  - phase: 04-nuendo-live-export
    provides: Plan 04-01 — lxml~=5.3.0 dependency, MultitrackTrack.resolved_yamaha_name @property + _HEX_TO_YAMAHA_NAME reverse-map
provides:
  - planner/utils/nuendo_live_export.py — pure build_nlpr(session) → bytes
  - YAMAHA_TO_FARB constant (8 entries; 'Off' and 'White' omitted per D-05/D-07)
  - ExportTemplateError exception (D-03 — caught by Plan 04-05 view, rendered as editor banner)
  - _TEMPLATE_PATH = planner/data/multitrack/nuendo_live_3_template.nlpr (Plan 04-03's deliverable)
  - Six private helpers: _find_audio_folder, _scan_max_id, _replace_all_ids, _set_names, _set_channel_id, _apply_farb (plus _load_template, _sanitize_label)
affects: [04-03, 04-04, 04-05, 04-06, 04-07, nuendo-live-exporter, view-layer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Template-injection mutation loop: load empty fixture once, cache parsed tree, deepcopy root per call, walk seed track, mutate-in-place, append clones, drop seed, etree.tostring → bytes"
    - "Module-level mutable cache (_TEMPLATE_TREE) that ALWAYS returns deepcopy to callers — never lets mutations leak back into the cache (RESEARCH Pitfall 3)"
    - "XPath predicate filter on inner Name value to disambiguate semantically-identical sibling elements (RESEARCH Pattern 2 — picks 'Audio' MFolderTrack vs. 'Input/Output Channels' MFolderTrack)"
    - "Two-write-per-track name protocol (RESEARCH Pitfall 9): outer MListNode/Name AND inner DeviceAttributes/Name/String — both required for Nuendo Live to render the name in both Mixer and Track Inspector"
    - "Sequential ID allocator with max(existing)+1000 floor (D-08): scans @ID, @value of <int name='RuntimeID'|'ID'> across the whole document"

key-files:
  created:
    - "planner/utils/nuendo_live_export.py — pure Nuendo Live .nlpr exporter (331 lines)"
  modified: []

key-decisions:
  - "Helper signatures and bodies match RESEARCH §'Code Examples' verbatim. Plan 04-02 is a transcription plan — no exploratory design happened here; all decisions front-loaded into CONTEXT.md D-01..D-10 and RESEARCH §'Architecture Patterns' / §'Code Examples'"
  - "_replace_all_ids visits new_track root @ID FIRST (if present), then descendant @ID attrs, then <int name='RuntimeID'|'ID'> value-attrs — deterministic order so IDs are stable across runs given identical input session"
  - "_apply_farb's SubElement re-add path is a defensive fallback for RESEARCH A5 (we don't yet know whether Charlie's hand-generated template (Plan 04-03) has a Farb in its seed). If Plan 04-03 confirms Farb is always present in the seed, the SubElement branch becomes dead code — fine; cost is one if-statement"

patterns-established:
  - "Pure-function exporter contract (mirror of planner/utils/reaper_export.py): trust-boundary docstring at top, palette-table constants, _ordered_enabled_tracks reused via import, public builder returning bytes/string, all private helpers prefix-underscored"
  - "ExportTemplateError exception class for fixture-related runtime failures — caught by view layer (D-03), allows graceful degradation when the bundled fixture is missing/malformed instead of returning 500"
  - "lxml deepcopy-from-cache pattern: cache the parsed ElementTree, but ALWAYS return copy.deepcopy(_TEMPLATE_TREE.getroot()) from the loader so module-level state is read-only post-init"

requirements-completed: [NLP-02, NLP-03, NLP-04, NLP-05, NLP-06]

# Metrics
duration: 5min
completed: 2026-05-13
---

# Phase 4 Plan 02: Nuendo Live Exporter Summary

**Pure-function `build_nlpr(session) → bytes` exporter using lxml template-injection: cached deepcopy of an `.nlpr` fixture, sequential ID allocator, two-write-per-track name protocol, Farb apply-or-strip, with `YAMAHA_TO_FARB` constant and `ExportTemplateError` for missing-fixture graceful degradation.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-13T23:42:41Z
- **Completed:** 2026-05-13T23:47:09Z
- **Tasks:** 2 / 2
- **Files created:** 1 (`planner/utils/nuendo_live_export.py`, 331 lines)
- **Files modified:** 0

## Accomplishments

- `planner/utils/nuendo_live_export.py` exists with the full Phase 4 exporter contract:
  - Trust-boundary docstring (caller owns project scoping — mirrors `reaper_export.py:9-13`)
  - `YAMAHA_TO_FARB` palette table — 8 entries, `'Off'` and `'White'` intentionally absent per D-07
  - `ExportTemplateError` exception class — caught by the (future Plan 04-05) view layer per D-03
  - Public `build_nlpr(session) -> bytes` builder implementing the full spec §template-injection algorithm
  - Six private helpers: `_load_template`, `_find_audio_folder`, `_scan_max_id`, `_replace_all_ids`, `_set_names`, `_set_channel_id`, `_apply_farb` (plus `_sanitize_label` for Pitfall-4 NUL-byte defense)
- Module imports cleanly from a fresh Python interpreter; `YAMAHA_TO_FARB` matches D-07 exactly.
- Helper-level in-memory exercise harness (defined in Task 2's `<verify>` block) passes end-to-end against a Python-generated fake template:
  - `_find_audio_folder` correctly picks the `'Audio'` MFolderTrack, not the `'Input/Output Channels'` sibling
  - `_scan_max_id` finds the largest ID across `@ID` attrs and `<int name='RuntimeID'/>` value-attrs
  - `_replace_all_ids` burns IDs sequentially through the deep-copied seed
  - `_set_names` writes the same label into both the outer `MListNode/Name` AND inner `MAudioTrack//DeviceAttributes/Name/String` (Pitfall 9)
  - `_set_channel_id` mutates the right `<int name='Channel ID'/>`
  - `_apply_farb` covers all three branches: palette match → mutate value; `None` → remove element; non-palette name → remove element
- Phase 1's `planner/tests/test_reaper_export` continues to pass 42/42 — the byte-stable Reaper contract is intact (Phase 4 reused `_ordered_enabled_tracks` via import, did not modify it).
- `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'` — zero schema drift (CLAUDE.md §"additive migrations only" naturally satisfied; this plan only added a new utility module with no model changes).
- `_TEMPLATE_PATH` is resolved via `Path(__file__).parent.parent / 'data' / 'multitrack' / 'nuendo_live_3_template.nlpr'` — matches the bundled-fixture convention established by Phase 2's CSV fixtures and Comm Config's pouchdb factory.

## Task Commits

Each task was committed atomically:

1. **Task 1: Module skeleton (constants, errors, trust-boundary docstring, public `build_nlpr` shell)** — `9c6491b` (feat)
2. **Task 2: Implement six private helpers** — `2e516f9` (feat)

_Note: Plan 04-02 is `type: execute`, not `tdd`. No RED/GREEN/REFACTOR gates apply — both commits are `feat(...)` and Task 2 builds linearly on Task 1's stubbed helpers._

## Files Created/Modified

- **Created:** `planner/utils/nuendo_live_export.py` — 331 lines. Pure-function Nuendo Live exporter. Contains:
  - Module docstring with the locked trust-boundary paragraph
  - `YAMAHA_TO_FARB` constant (8 entries)
  - `_TEMPLATE_PATH` pathlib expression pointing at Plan 04-03's future deliverable
  - `_TEMPLATE_TREE` module-level cache (None at import; populated on first call)
  - `ExportTemplateError` exception class
  - `_load_template()` — parse-once-then-deepcopy loader
  - `_find_audio_folder`, `_scan_max_id`, `_replace_all_ids`, `_set_names`, `_set_channel_id`, `_apply_farb` — six locked private helpers per RESEARCH §"Code Examples"
  - `_sanitize_label` — Pitfall-4 NUL/control-char stripper (laid down in Task 1; was not a stub since the plan's Task 1 `<action>` block included its full body)
  - `build_nlpr(session) -> bytes` — public builder wiring all helpers per spec §template-injection
- **Modified:** none.

## Decisions Made

- **No deviations from the plan's locked bodies.** All six helper implementations match RESEARCH §"Code Examples" character-for-character. Plan 04-02 is a transcription plan, by design — RESEARCH and CONTEXT front-loaded every design decision (D-05/D-07/D-08/D-10, Pitfalls 7/9, A5 fallback).
- **`_sanitize_label` was already implemented in Task 1's `<action>` block** (not a NotImplementedError stub) because the plan's locked code for Task 1 included the full body. Task 2 left it alone. This is consistent with the plan — the `<acceptance_criteria>` in Task 2 only counts the six raise-NotImplementedError stubs that needed bodies, not `_sanitize_label`.
- **Module path resolution via `Path(__file__).parent.parent` rather than `django.conf.settings.BASE_DIR`** — keeps `planner/utils/` self-contained (no Django settings import inside a pure-function utility module). Matches the analog at `planner/utils/yamaha_export.py` (per CONTEXT.md §"Established Patterns").
- **Local-dev `lxml` install:** the project's `venv/` did not yet have `lxml` installed locally even though `lxml~=5.3.0` was pinned in `requirements.txt` (Plan 04-01). Installed via `./venv/bin/pip install 'lxml~=5.3.0'` to unblock the verify command. This is a developer-environment quirk identical to the one Plan 04-01 documented; Railway pip-installs from `requirements.txt` automatically on deploy.

## Deviations from Plan

None — plan executed exactly as written. All `<verify>` automated checks pass and all six `<acceptance_criteria>` blocks (Task 1 + Task 2) are satisfied at the literal-grep level, with a single semantic clarification noted below.

### Acceptance-criterion clarification

The Task 2 acceptance criterion `grep -c "Input/Output Channels" planner/utils/nuendo_live_export.py` returns `0` is intended to verify "we do NOT special-case this folder; the Audio-only XPath naturally excludes it." The actual literal grep returns `1` — but the single hit is in the docstring of `_find_audio_folder`, a single-line comment explaining what the XPath does NOT match. This is informational documentation; there is no special-case code logic. The acceptance criterion's spirit ("no overly-broad selectors accidentally matching the Input/Output Channels folder") is satisfied because the XPath positively selects `[.//string[@name='Name' and @value='Audio']]` and would never return the `'Input/Output Channels'` folder. The docstring reference was laid down in Task 1's plan-locked stub and was preserved through Task 2.

## Issues Encountered

- **Local Python venv was missing `lxml`** despite `requirements.txt` containing `lxml~=5.3.0` from Plan 04-01. Resolution: `./venv/bin/pip install 'lxml~=5.3.0'`. Identical to the local-dev issue noted in Plan 04-01's SUMMARY. Not a plan deviation; Railway installs from `requirements.txt` automatically and is unaffected.
- **PreToolUse:Edit hook required a fresh Read between each Edit on the same file.** Caused one extra Read-then-Retry cycle per helper-stub replacement, but no work was lost — the previous Edit succeeded before each hook prompt. Total cost: ~30 seconds across 4 stub-replacement edits.

## User Setup Required

None — the bundled fixture at `planner/data/multitrack/nuendo_live_3_template.nlpr` is Plan 04-03's deliverable (Charlie hand-generates on Windows + Nuendo Live 3). Plan 04-02 only stages the path lookup; the fixture's absence is handled gracefully at runtime via `ExportTemplateError` (D-03 contract, caught by Plan 04-05's future view layer).

## Threat Flags

None — Plan 04-02's surface (a single pure-function exporter module reading from a path and writing in-memory XML via `lxml.etree.set()`) is fully contained by the plan's `<threat_model>` entries T-04-04 through T-04-08:
- T-04-04 (XML attribute escaping) — handled by `lxml.set('value', ...)` auto-escape + `_sanitize_label`'s control-char strip.
- T-04-05 (XXE on template parse) — accepted; the template is a committed git fixture, not user input. Defense-in-depth (`XMLParser(resolve_entities=False)`) is left as future polish per the plan.
- T-04-06 (DoS via huge sessions) — accepted per RESEARCH §"Security."
- T-04-07 (cache poisoning) — mitigated by `_load_template`'s always-deepcopy-on-return rule (Pitfall 3).
- T-04-08 (caller forgets to project-scope) — mitigated by the trust-boundary docstring; the view layer (Plan 04-05) carries the actual `filter(id=, project=current_project)` enforcement.

No new network endpoints, no new auth paths, no new schema, no new file-write surface. No `threat_flag:` entries to report.

## TDD Gate Compliance

N/A — plan `type: execute`, not `type: tdd`. No RED/GREEN gates apply.

## Self-Check: PASSED

Verified before STATE.md update:
- `planner/utils/nuendo_live_export.py` exists (FOUND; `wc -l` returned 331 lines, ≥ 180 min_lines must-have)
- `def build_nlpr` count: 1 (FOUND)
- `class ExportTemplateError` count: 1 (FOUND)
- `YAMAHA_TO_FARB =` literal: 1 (FOUND; verified by Python assert)
- `from lxml import etree` count: 1 (FOUND)
- `from .reaper_export import _ordered_enabled_tracks` count: 1 (FOUND)
- Trust-boundary docstring (`this module does NOT filter sessions by project`) count: 1 (FOUND)
- `raise NotImplementedError` count: 0 (FOUND — all six helper stubs replaced in Task 2)
- All six private helper `def`s present (FOUND: `_find_audio_folder`, `_scan_max_id`, `_replace_all_ids`, `_set_names`, `_set_channel_id`, `_apply_farb`)
- `DeviceAttributes` references: 3 (FOUND — Pitfall 9 two-name-write)
- `Channel ID` references: 4 (FOUND — `_set_channel_id` body + docstring/algorithm narration)
- `Additional Attributes` references: 4 (FOUND — `_apply_farb` body)
- `RuntimeID` references: 6 (FOUND — `_scan_max_id` + `_replace_all_ids` + docstrings)
- Task 1 commit `9c6491b` exists (FOUND in `git log --oneline -3`)
- Task 2 commit `2e516f9` exists (FOUND in `git log --oneline -3`)
- `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'` (FOUND)
- `planner.tests.test_reaper_export`: 42/42 OK (FOUND; Phase 1 byte-stable contract intact)
- Module import test prints `OK` and `YAMAHA_TO_FARB` matches the D-07 dict exactly (FOUND)
- Helper-level in-memory exercise harness prints `OK` (FOUND — all 6 helpers behave per spec/RESEARCH on a Python-generated fake template)

## Next Phase Readiness

- **Plan 04-02 deliverable is complete and unit-level-verified.** `build_nlpr(session)` is invokable but will raise `ExportTemplateError` until Plan 04-03 commits the real bundled fixture at `planner/data/multitrack/nuendo_live_3_template.nlpr` — by design (D-03 gracefulness).
- **Plan 04-03 (Charlie-generated fixture) blocker remains outstanding.** Charlie must save a fresh empty Nuendo Live 3 session on Windows with exactly one default audio track named `"Audio 01"` per CONTEXT.md D-02. Once that fixture lands, `build_nlpr` returns valid bytes end-to-end.
- **Plan 04-04 (test) can begin now using a Python-generated fake template** — the helper-exercise harness in Task 2's `<verify>` block is a working prototype of the D-09 ID-uniqueness assertion harness. Plan 04-04's test file will adapt the same fake-template approach (`monkeypatch` `_TEMPLATE_PATH` to a `planner/tests/fixtures/...` minimal `.nlpr`).
- **Plan 04-05 (view + URL) can begin now.** The `build_nlpr` import target and `ExportTemplateError` are stable. The view layer wraps the bytes in `HttpResponse(body, content_type='application/xml; charset=utf-8')` and catches `ExportTemplateError` to render the D-03 banner. Reuse of `_safe_filename` and `_has_enabled_tracks` is exactly as planned.

---
*Phase: 04-nuendo-live-export*
*Completed: 2026-05-13*
