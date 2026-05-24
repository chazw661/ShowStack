---
phase: 11-ports-and-resize
plan: 07
subsystem: ui
tags: [signal-flow-diagrammer, autocomplete, ports, min-size, gap-closure, jointjs, django, javascript]

# Dependency graph
requires:
  - phase: 10-autocomplete-png-export-new-shapes
    provides: signal_flow_label_autocomplete endpoint (9 source SOURCES list, IDOR-scoped)
  - phase: 11-ports-and-resize
    provides: addAuthoredPort + refreshPortAuthorBlock + computeMinSize from plans 11-02..11-06
provides:
  - shape_class-scoped autocomplete (per-shape catalog narrowing on the Phase 10 endpoint)
  - clickable engineer-authored ports (opacity:1 — unblocks PORT-04/PORT-05 browser UAT)
  - bounded autocomplete listbox lifecycle (no stale orphans after N add/rename/remove cycles)
  - Σ(label widths)-based Top/Bottom min-size (PORT-06 auto-expansion fits horizontal labels)
affects: 11-08, 12-boundary-lines-text-annotations, future v2.4+ port-related work

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Allowlist-only query-param filter for multi-source endpoint extension (no 500 on unknown values; missing param = full broadcast)"
    - "Per-render stale-DOM purge before rebuild in dynamic inspector blocks (querySelectorAll + remove pattern)"

key-files:
  created: []
  modified:
    - planner/views.py (SHAPE_CLASS_SOURCES allowlist + shape_class filter branch in signal_flow_label_autocomplete)
    - planner/static/planner/js/signal_flow_editor.js (authored portBody opacity 1; sumLabelWidths/edgeWidthRequired helpers; W_topbottom formula; refreshPortAuthorBlock listbox purge + portAutocompleteUrl builder)

key-decisions:
  - "SHAPE_CLASS_SOURCES allowlist scopes 4 shape types (Console/Device/Amp/Processor); SpeakerArray/CommBeltPack/Generic intentionally absent → fall through to all 9 sources (no labeled-channel catalog of their own)."
  - "Unknown shape_class values also fall through to all 9 sources — allowlist-only filtering means the endpoint never 500s on bad input and the Phase 10 BC caller (connector circuit-label) sees zero behavior change."
  - "Authored portBody opacity bumped to 1 (always visible); Phase 8 generic ports in standardPortGroups() stay opacity:0 (hover-reveal preserved for D-13 back-compat shapes with zero authored ports)."
  - "Top/Bottom width = Σ(label widths) + (N-1) × MIN_PORT_SPACING + 2 × EDGE_PADDING_PARALLEL — per RESEARCH §Q2. Left/Right vertical formula left untouched (vertical edges use uniform spacing because labels are horizontal and stack vertically)."

patterns-established:
  - "Query-param allowlist extension of shared autocomplete endpoint: caller opts-in by sending param; backend silently narrows OR falls through; old callers untouched."
  - "Inspector-block lifecycle hygiene: every refresh-time DOM rebuild purges its own stale children (listboxes, popovers, etc.) before rebuilding."

requirements-completed: [PORT-03, PORT-04, PORT-05, PORT-06, SHP-RESIZE-02]

# Metrics
duration: 12min
completed: 2026-05-24
---

# Phase 11 Plan 07: Ports & Resize Gap Closure Summary

**Per-shape autocomplete scoping + always-visible authored ports + listbox-orphan purge + Σ(label-widths) min-size — four UAT gaps closed with surgical edits to two files.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-24T20:34Z (plan execution kicked off)
- **Completed:** 2026-05-24T20:46Z
- **Tasks:** 2 (1 backend, 1 JS)
- **Files modified:** 2

## Accomplishments

- **GAP-11.1 closed** (commits `133cc97` + `fabffdf`): Port-row autocomplete on a Device shape now suggests only `Device Input` / `Device Output` (no more `Amp Channel` cross-catalog noise). Backend `SHAPE_CLASS_SOURCES` allowlist narrows the 9-source SOURCES list when the client sends `?shape_class=`. The connector circuit-label at `signal_flow_editor.js:2652` still sends no `shape_class` param → backend falls through → Phase 10 BC preserved byte-for-byte.
- **GAP-11.2 BLOCKER closed** (commit `fabffdf`): Engineer-authored ports render at `opacity: 1` instead of the inherited Phase 8 hover-reveal `0`. JointJS now actually sees the magnet at click time, so clicking starts a connector drag instead of pan-dragging the cell. Phase 8 generic ports (the 4 `portsForRect()` ones used by D-13 back-compat shapes) stay `opacity: 0` — hover-reveal continues to apply for zero-authored shapes.
- **GAP-11.3 closed** (commit `fabffdf`): `refreshPortAuthorBlock()` now drops every `.sfd-ac-listbox` descendant of `portAuthorBlock` before rebuilding rows. Listbox count is now bounded by visible-row count, never accumulates across add/rename/remove cycles. WR-02 code-review warning is resolved.
- **GAP-11.5 closed** (commit `fabffdf`): `computeMinSize` Top/Bottom width contribution rewritten from `count × MIN_PORT_SPACING` to `Σ(label widths) + (N-1) × MIN_PORT_SPACING + 2 × EDGE_PADDING_PARALLEL`. New helpers `sumLabelWidths()` and `edgeWidthRequired()` apply RESEARCH §Q2 formula. Auto-expansion (PORT-06) now grows the shape wide enough to keep horizontal port labels from overlapping inside the body.

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend `signal_flow_label_autocomplete` shape_class scoping** — `133cc97` (`feat`)
2. **Task 2: JS port-row autocomplete URL + opacity + listbox purge + min-size sum** — `fabffdf` (`fix`)

**Plan metadata:** _(commit after this SUMMARY + STATE/ROADMAP updates)_

## Files Created/Modified

- `planner/views.py` (+22 lines) — `SHAPE_CLASS_SOURCES` allowlist dict at top of `signal_flow_label_autocomplete` function body; `shape_class` query-param read + SOURCES filter branch immediately after the SOURCES list definition. 9-source list itself textually unchanged.
- `planner/static/planner/js/signal_flow_editor.js` (+43/-5, net +38 lines) — four narrowly-scoped edits:
  - `addAuthoredPort` `portBody.opacity` literal 0 → 1 (GAP-11.2)
  - `computeMinSize` new `sumLabelWidths()` helper + new `edgeWidthRequired()` helper + rewritten `W_topbottom` (GAP-11.5). Left/right vertical formula, body-label reserves, and `Math.max` aggregations are byte-for-byte unchanged.
  - `refreshPortAuthorBlock` top-of-function purge: `Array.from(portAuthorBlock.querySelectorAll('.sfd-ac-listbox')).forEach(remove)` (GAP-11.3)
  - `refreshPortAuthorBlock` URL builder `portAutocompleteUrl = labelAutocompleteUrl + (...) + 'shape_class=' + encodeURIComponent(cell.get('type'))` + swap in per-row `attachAutocompleteToInput(input, portAutocompleteUrl, …)` (GAP-11.1 client)

The connector circuit-label call at `signal_flow_editor.js:2652` is **explicitly unchanged** — verified by grep returning exactly 1 match for `attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)`. Phase 10 BC is preserved.

## Decisions Made

### SHAPE_CLASS_SOURCES mapping rationale (for future v2.4+ revisit)

| Shape `type` | Equipment record | Autocomplete sources | Rationale |
|---|---|---|---|
| `showstack.Console` | `Console` | `Console Input`, `Console Aux Out` | Console I/O is labeled per-channel via these fields. |
| `showstack.Device` | `Device` | `Device Input`, `Device Output` | Device I/O is labeled per-port via `signal_name`. |
| `showstack.Amp` | `Amp` | `Amp Channel` | Amp channels carry their own `channel_name`. |
| `showstack.Processor` | `P1Processor` / `GalaxyProcessor` | `P1 Input/Output`, `Galaxy Input/Output` | Phase 10 D-05 excluded `SystemProcessor.name` (device identifier, not signal name); P1/Galaxy I/O records hold the canonical labels. |
| `showstack.SpeakerArray` | (none — output transducer) | **fall through (all 9)** | No labeled-channel catalog. Restricting to "no suggestions" would punish engineers for choosing a flexible shape; broadcasting all 9 matches connector circuit-label behavior. |
| `showstack.CommBeltPack` | (none — comm endpoint) | **fall through (all 9)** | Same rationale as SpeakerArray. |
| `showstack.Generic` | (no equipment record by design) | **fall through (all 9)** | Same rationale as SpeakerArray. |

**Allowlist-only filtering** is the security property worth preserving: any unknown / future shape_class also falls through to all 9 — the endpoint never 500s on bad input, and the IDOR project-scope filter still runs per source inside the loop regardless of shape_class.

When Phase 12 adds boundary-line and text-annotation shape types, they will likely also need a "no I/O label catalog → fall through" decision; this mapping is the natural place for that to land.

## Deviations from Plan

None — plan executed exactly as written. Both tasks ran clean on first pass; all automated verifications (node --check, grep counters, AST parse, Django check that proxy via AST since no venv is active) pass.

## Issues Encountered

None.

## User Setup Required

None — no environment variables, no migrations, no new dependencies, no URL routes. Browser smoke-test required after deploy (Charlie):

1. **GAP-11.2 (BLOCKER closed):** Drop a Device shape, add a port via inspector → port dot visible → click+drag starts a connector → drops on another shape's port → lands.
2. **GAP-11.1:** Type 1 char in a port-row label input on a Device → suggestions are Device Input / Device Output only. Type 1 char in a connector circuit-label → all 9 sources still appear.
3. **GAP-11.3:** Add 3 ports, rename each, trash 2 → `$$('.sfd-ac-listbox', $('.sfd-field--port-author'))` returns ≤ visible-row count.
4. **GAP-11.5:** Add 5 ports with realistic labels to the Top edge of a Console → shape auto-expands wide enough that no two labels overlap; toast fires.
5. **No regressions:** Selection visuals, corner-resize handles on single selection, no handles on multi-select, autosave POST within 1500ms of port mutation.

## Cross-plan coordination

- **GAP-11.4** (port-row input text too faint on dark inspector) is owned by sibling plan `11-08-PLAN.md` (CSS-only — `.sfd-port-label-input` color + placeholder color in Section 16). Runs in parallel because it touches a non-overlapping file.

## Next Phase Readiness

- Phase 11 gap closure functionally complete pending Charlie's browser UAT pass on the 5-point smoke list above.
- Once UAT passes, REQUIREMENTS.md traceability rows for PORT-01..06 and SHP-RESIZE-01..03 should flip from "TBD / Pending" → "Done" with this commit hash and plan 11-08's commit hash for GAP-11.4.
- Phase 12 (Boundary Lines + Text Annotations) is unblocked.

## Self-Check: PASSED

- `planner/views.py` — exists, contains `SHAPE_CLASS_SOURCES` (3 hits) and `shape_class = ` (1 hit), AST parses, Django check fails only on `ModuleNotFoundError: No module named 'decouple'` (no venv active — known environmental per plan acceptance criteria).
- `planner/static/planner/js/signal_flow_editor.js` — exists, `node --check` exits 0, line count 2746 (+38 net), all 13 grep verifications pass:
  - `GAP-11.2: authored ports always visible` = 1
  - `opacity: 0` = 2 (Phase 8 standardPortGroups in/out — preserved)
  - `opacity: 1` = 1 (new authored port)
  - `function sumLabelWidths` = 1
  - `function edgeWidthRequired` = 1
  - `Math.max(N_T, N_B) * MIN_PORT_SPACING` = 0 (old formula fully removed)
  - `querySelectorAll('.sfd-ac-listbox')` = 1
  - `shape_class=` = 1
  - `portAutocompleteUrl` = 2 (declaration + use)
  - `attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)` = 1 (BC preserved)
  - `function refreshPortAuthorBlock` = 1
  - `function computeMinSize` = 1
- Commits exist:
  - `133cc97` — Task 1 backend (verified via git log)
  - `fabffdf` — Task 2 JS (verified via git log)
- No unintentional file deletions in either commit (verified via `git diff --diff-filter=D`).

---
*Phase: 11-ports-and-resize*
*Completed: 2026-05-24*
