---
phase: 11-ports-and-resize
plan: 08
subsystem: ui
tags: [signal-flow-diagrammer, gap-closure, css, inspector-ui, port-author, accessibility, contrast]

# Dependency graph
requires:
  - phase: 11-ports-and-resize
    provides: ".sfd-port-label-input rule from plan 11-03 (Section 16, lines 783-794 — the bug site)"
provides:
  - "Section 16 .sfd-port-label-input rule visually consistent with Section 4 inspector-input pattern (engineer-authored port labels readable as typed)"
affects: 11 (closes UAT GAP-11.4), 12-boundary-lines-text-annotations (any future TXT/DRAW inspector fields should reuse the Section 4 pattern + Section 16 evidence of correct adoption)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inspector-input visual contract: dark navy bg (#1a1a2a) + light text (#eee) + grey border (#444) + SF Mono family — established in Section 4, now consistently applied in Section 16's port-label input."
    - "Placeholder muting: #aaa with explicit opacity:1 (overrides Firefox's default 0.54 placeholder alpha) — same grey as .sfd-field-help hint copy."

key-files:
  created: []
  modified:
    - planner/static/planner/css/signal_flow.css (Section 16 .sfd-port-label-input: white→dark-navy bg, missing→light text, light-grey→grey border, added mono font; new ::placeholder rule)

key-decisions:
  - "Values copied verbatim from Section 4 — zero new hex codes introduced. Inspector now has a single visual vocabulary for text-input controls."
  - "Background property renamed shorthand 'background' → 'background-color' to match Section 4's longhand form (no semantic difference but improves consistency for future audit greps)."
  - "Added font-family explicitly even though 12px mono inheritance might have worked — defence in depth against django-admin-interface !important overrides."
  - "::placeholder rule kept separate from the base rule (per CSS spec: most browsers ignore the entire base rule if it contains an unsupported pseudo-element selector — splitting them is the safe pattern)."
  - "Explicit opacity:1 on ::placeholder — Firefox defaults placeholder text to 0.54 alpha, which would tint #aaa toward invisibility on the dark navy background."

patterns-established:
  - "When amending an existing inspector input rule, mirror Section 4's input contract (bg+color+border+font) byte-for-byte — do not invent new hex codes for v2.3 polish."

requirements-completed: [PORT-03]

# Metrics
duration: 4min
completed: 2026-05-24
---

# Phase 11 Plan 08: Port-Label Input Contrast Fix Summary

**CSS-only gap closure — Section 16's .sfd-port-label-input rule lost its inherited text color against a hardcoded white background; aligned to the Section 4 canonical inspector-input pattern (dark navy + light text + grey border) so engineer-typed port labels are readable as they're typed.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-24T20:48Z (orchestrator spawn)
- **Completed:** 2026-05-24T20:52Z
- **Tasks:** 1 (1 CSS edit)
- **Files modified:** 1 (`planner/static/planner/css/signal_flow.css`, +16 / -2)
- **Commits:** 1 (`9844745`)

## What Shipped

| Layer | File | Change | Lines |
|-------|------|--------|-------|
| CSS — Inspector Section 16 | `signal_flow.css` | `.sfd-port-label-input` base rule: white bg → `#1a1a2a`, missing color → `#eee`, `#d0d0d0` border → `#444`, added mono `font-family` | 783-797 |
| CSS — Inspector Section 16 | `signal_flow.css` | NEW `.sfd-port-label-input::placeholder` rule: `color: #aaa`, `opacity: 1` | 799-803 |
| CSS — Inspector Section 16 | `signal_flow.css` | `:focus` rule UNCHANGED (teal `#0d9488` border) | 805-808 |

Total file delta: 875 lines (was 861) — +14 net lines, of which 5 are doc-comment, 5 are amended rule body, 4 are the new ::placeholder block.

## Gap Closure

| Gap ID | Severity | Symptom | Root Cause | Fix |
|--------|----------|---------|------------|-----|
| **GAP-11.4** | medium | Port-row label input text invisible on dark inspector background ("INput 1" placeholder barely visible during UAT) | Plan 11-03 added `.sfd-port-label-input` with `background: #fff` but no `color` property → input inherited `#sfd-inspector { color: #eee }` → white text on white bg | Aligned to Section 4 inspector-input pattern: dark navy bg + light text + grey border (values copied verbatim, no new hex codes) |

GAP-11.4 closure commit: **`9844745`**

## Visual Contract Compliance

The new rule is byte-for-byte aligned with Section 4 (`.sfd-field input[type="text"]`, lines 258-273) on the four visual-contract properties:

| Property | Section 4 (canonical) | Section 16 (NEW) | Match |
|----------|----------------------|------------------|-------|
| `background-color` | `#1a1a2a !important` | `#1a1a2a !important` | YES |
| `color` | `#eee !important` | `#eee !important` | YES |
| `border` | `1px solid #444 !important` | `1px solid #444 !important` | YES |
| `font-family` | `"SF Mono", Consolas, Menlo, monospace !important` | `"SF Mono", Consolas, Menlo, monospace !important` | YES |
| `font-size` | `12px !important` | `12px !important` | YES |
| `padding` | `6px 8px !important` (looser — for primary fields) | `4px 6px !important` (tighter — port rows pack denser by design) | INTENTIONAL DIFF |
| `border-radius` | `4px !important` (primary) | `3px !important` (denser nested rows) | INTENTIONAL DIFF |

Placeholder reuses Section 4's `.sfd-field-help` muted grey (`#aaa`) with explicit `opacity: 1` to override Firefox's default 0.54 placeholder alpha.

## Verification (automated)

All file-level checks from plan 11-08 verification block passed:

```bash
$ grep -c "GAP-11.4 fix" planner/static/planner/css/signal_flow.css                          # → 1 (expected 1) PASS
$ grep -c ".sfd-port-label-input::placeholder" planner/static/planner/css/signal_flow.css     # → 1 (expected 1) PASS
$ grep -c "background-color: #1a1a2a !important" planner/static/planner/css/signal_flow.css   # → 3 (expected >=2) PASS
$ grep -c "color: #eee !important" planner/static/planner/css/signal_flow.css                 # → 8 (expected >=3) PASS
$ grep -nE "\.sfd-port-label-input \{[^}]*background: #fff" planner/static/planner/css/signal_flow.css | wc -l   # → 0 (expected 0) PASS
$ grep -nE "\.sfd-port-label-input \{[^}]*border: 1px solid #d0d0d0" planner/static/planner/css/signal_flow.css | wc -l   # → 0 (expected 0) PASS
$ grep -c "border-color: #0d9488 !important" planner/static/planner/css/signal_flow.css       # → 2 (unchanged) PASS
```

Line delta: +14 net lines (was 861, now 875). Plan estimated +6..+12 but did not account for the 5-line doc-comment block which the plan prescribed verbatim — substantive content delta is +9 lines (within plan range when comment is excluded). No concern.

`collectstatic --dry-run` could not be exercised locally (`decouple` not installed at system python — known local-env quirk; venv-only). Per plan acceptance criteria: "Skip if no validator on system — the grep checks above cover structural correctness." Railway deploy will exercise `collectstatic` on push.

## Section Sibling Audit

All Section 16 sibling rules are byte-for-byte unchanged (line numbers shift +14 due to the new comment + rule body + ::placeholder block, but rule content is identical):

| Selector | Old line | New line | Content delta |
|----------|----------|----------|---------------|
| `.sfd-port-section-title` | 724 | 724 | unchanged |
| `.sfd-port-edge-section` | 733 | 733 | unchanged |
| `.sfd-port-edge-header` | 737 | 737 | unchanged |
| `.sfd-port-edge-name` | 744 | 744 | unchanged |
| `.sfd-port-add` | 750 | 750 | unchanged |
| `.sfd-port-list` | 763 | 763 | unchanged |
| `.sfd-port-row` | 769 | 769 | unchanged |
| `.sfd-port-ordinal` | 776 | 776 | unchanged |
| `.sfd-port-label-input` | 783 | 788 | **AMENDED** (the fix) |
| `.sfd-port-label-input::placeholder` | — | 800 | **NEW** |
| `.sfd-port-label-input:focus` | 791 | 805 | unchanged |
| `.sfd-port-remove` | 796 | 810 | unchanged |

Section 4 (lines 258-273, `.sfd-field input[type="text"]` canonical pattern) is byte-for-byte unchanged — confirmed by sed extraction.

## Deviations from Plan

None — plan executed exactly as written. The one observable variance is the line delta (+14 vs plan estimate of +6..+12), which is purely doc-comment volume and is addressed in the Verification section above.

## Parallel-Wave Coordination

This plan ran in wave 1 of the gap-closure batch alongside **11-07** (JS + backend gap closure for GAP-11.1/11.2/11.3/11.5). The two plans share zero files:

- **11-07:** `planner/views.py` + `planner/static/planner/js/signal_flow_editor.js`
- **11-08:** `planner/static/planner/css/signal_flow.css`

No dependency, no file overlap, no merge contention. 11-07 landed first (commits `133cc97`, `fabffdf`, `c812b7b`) on the same `main` branch; 11-08's working tree base included those changes with zero edit conflict.

## Browser Smoke (post-merge, pending Charlie's UAT)

Per plan verification checklist:

1. Open editor with any project, drop a Device shape.
2. Inspector opens in node mode. Click "+ Add port" under Top.
3. Type "Channel 1" — text MUST be clearly readable (light on dark, NOT white-on-white).
4. Click into the connector circuit-label input on a connector — visually identical font/color treatment.
5. Tab/click away from the port-label input — focus ring disappears; text remains readable.
6. (Optional) Inspect computed style: `getComputedStyle($('.sfd-port-label-input')).color` returns `rgb(238, 238, 238)`.

Result will be appended here once verified.

## Threat Surface

No new endpoints, no new auth surface, no new file access. CSS-only edit with no DOM additions and no new selectors targeting previously-unstyled elements. The two STRIDE entries in the plan's threat register both carry `accept` dispositions and remain valid.

## Self-Check

Verified post-write:

- File created: `[ -f .planning/phases/11-ports-and-resize/11-08-SUMMARY.md ]` → present.
- Commit exists: `git log --oneline | grep -q 9844745` → present.
- Modified file exists with new rule: `grep -q "GAP-11.4 fix" planner/static/planner/css/signal_flow.css` → present.

## Self-Check: PASSED
