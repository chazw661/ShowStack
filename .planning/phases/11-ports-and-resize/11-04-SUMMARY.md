---
phase: 11-ports-and-resize
plan: "04"
subsystem: signal-flow-diagrammer
tags:
  - phase-11
  - ports
  - canvas-rendering
  - css

dependency_graph:
  requires:
    - "11-02-SUMMARY.md (portLabelPositionForEdge + portLabelMarkupForEdge stubs to replace)"
    - "11-03-SUMMARY.md (CSS Section 16 already appended; file-header section list already pre-listed Section 14)"
  provides:
    - "portLabelPositionForEdge(edge) — real per-edge label position per RESEARCH §Q10 + D-08"
    - "portLabelMarkupForEdge() — font-locked SVG <text> markup (FONT_STACK, 11px, #444)"
    - "CSS Section 14 — .joint-port-label text always-visible; system-font lock"
    - "CSS Section 7 header — Phase 11 cross-reference comment added"
  affects:
    - "Plan 11-05 (resize tool) — measureLabelWidth can now read real label rendering; min-size math has accurate label geometry to measure against"
    - "Plan 11-06 (maybeAutoExpand) — label positions are now accurate, so auto-expand shrink threshold math is meaningful"

tech_stack:
  added: []
  patterns:
    - "JointJS port label position: {name:'manual', args:{x,y, attrs:{'.joint-port-label':{textAnchor}}}} — RESEARCH §Q10 per-edge variant"
    - "JointJS port label markup: [{tagName:'text', selector:'label', attributes:{...}}] — font-attrs inline in markup"
    - "Two-layer font-taint defense: JS markup sets font-family inline + CSS Section 14 sets !important override"
    - "Labels always-visible; dots hover-reveal only — two independent CSS rules with non-overlapping selectors"

key_files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js"
    - "planner/static/planner/css/signal_flow.css"

decisions:
  - "FONT_STACK reused (not literal): constant declared at line 94, in scope at lines 335–380 — avoids duplicating the system-font string"
  - "Defensive fallback added to portLabelPositionForEdge after switch — returns middle-anchored {x:0,y:0} if edge arg is unexpected; callers already restrict to T/B/L/R so this path is dead code, but defensive"
  - "Section 7 header comment amended (cross-reference only); two CSS selectors at lines 498/502 left verbatim — they already correctly target circle not .joint-port-label"
  - "Section 14 appended after Section 16 (port-list rows) — consistent with append-at-end convention; Plan 11-05 will append Section 15 (resize handles) after Section 14"

metrics:
  duration: "8 minutes"
  completed_date: "2026-05-24"
  tasks_completed: 2
  files_modified: 2
---

# Phase 11 Plan 04: Port-Label Canvas Rendering Summary

**One-liner:** Replaced Plan 11-02 portLabelPositionForEdge + portLabelMarkupForEdge stubs with real per-edge implementations (RESEARCH §Q10 D-08 perpendicular-inside) and appended CSS Section 14 to make authored port labels always-visible on the canvas.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Replace portLabelPositionForEdge + portLabelMarkupForEdge stubs with per-edge implementations | 6a08a70 | `signal_flow_editor.js` |
| 2 | Append CSS Section 14 + add Phase 11 cross-reference comment to Section 7 header | a853c28 | `signal_flow.css` |

## Task 1 Detail — JS stub replacement

**Insertion location:** Lines 335–380 (replacing lines 336–347 stubs from Plan 11-02)

**Before (Plan 11-02 stubs):**
```javascript
// Stubs — Plan 11-04 replaces these with the per-edge implementations
// from RESEARCH §Q10. Stub return values are placeholders that JointJS
// accepts but produce no visible label (which is fine: Plan 11-02 ships
// only the data layer; label rendering is Plan 11-04's job).
function portLabelPositionForEdge(edge) {
  // Plan 11-04 replaces with per-edge x/y/textAnchor switch (RESEARCH §Q10).
  return { name: 'manual', args: { x: 0, y: 0 } };
}
function portLabelMarkupForEdge() {
  // Plan 11-04 replaces with full font-attrs markup (RESEARCH §Q10).
  return [{ tagName: 'text', selector: 'label' }];
}
```

**After (Plan 11-04 implementations, 45 lines):**
- `portLabelPositionForEdge(edge)`: switch on edge → top (y=14/middle), bottom (y=-6/middle), left (x=8/start), right (x=-8/end) + defensive fallback
- `portLabelMarkupForEdge()`: returns `[{tagName:'text', selector:'label', attributes:{font-size:11, font-family:FONT_STACK, fill:'#444', pointer-events:'none'}}]`

**FONT_STACK decision:** Reused — constant declared at line 94 (`var FONT_STACK = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'`), in scope throughout the IIFE. No literal string duplication needed.

**Call-site comment updated:** The Plan 11-02 stub-reference comment at line 289 (inside `addAuthoredPort`) replaced with `// Per-edge label positioning + markup — RESEARCH §Q10 (Plan 11-04).` — no behavioral change.

## Task 2 Detail — CSS edits

**Edit A — Section 7 header amendment (lines 489–497):**

Added 4-line Phase 11 cross-reference paragraph clarifying that `opacity:0` targets only `.joint-port circle` (dot), and `.joint-port-label text` (label) stays always-visible per Section 14. Two rule selectors at lines 498 and 502 left verbatim.

**Edit B — Section 14 appended (lines 811–830, end-of-file):**
- Section header comment: 13 lines
- `.joint-port-label text` rule block: 6 lines (5 properties, all `!important`)
- Properties: `opacity:1`, `pointer-events:none`, `font-family:system-ui stack`, `font-size:11px`, `fill:#444`

**Append order note:** Section 14 appended after Section 16 (port-list rows, Plan 11-03). The section numbering in the file header pre-listed Section 14 at position 14 in the section list (Plan 11-03 Task 2 already added the header entry). The actual CSS block is now at the physical end of the file after Section 16 — this is consistent with the append-at-end convention and causes no functional issue (CSS section numbers are commentary only, not load-order-sensitive).

## Verification Results

| Check | Result |
|-------|--------|
| `node --check signal_flow_editor.js` | PASS (exit 0) |
| `grep -c "Plan 11-04 replaces"` | 0 (stub comments removed) |
| `grep -c "textAnchor: 'middle'"` | 7 (>=2 required) |
| `grep -c "textAnchor: 'start'"` | 5 (>=1 required) |
| `grep -c "textAnchor: 'end'"` | 1 (>=1 required) |
| `grep -c "'font-size': 11"` | 1 (>=1 required) |
| `grep -c "'pointer-events': 'none'"` | 1 (>=1 required) |
| `grep -c "RESEARCH §Q10"` | 3 (>=2 required) |
| `grep -c "SECTION 14 — Port-label rendering"` (CSS) | 1 |
| `grep -c "Phase 11 cross-reference:"` (CSS) | 1 |
| `grep -c "\.joint-port-label text"` (CSS) | 2 (>=1 required) |
| `grep -c "\.joint-paper \.joint-element:hover \.joint-port circle"` (CSS) | 1 (unchanged) |
| `python manage.py check` | 0 issues |
| `collectstatic --noinput --dry-run` | 2 static files + 274 unmodified, no errors |
| Browser smoke-test | Manual — Charlie to verify in browser per plan §verification |

## Plan 11-05 Handoff Note

Plan 11-05 (resize tool) reads port-label widths via `measureLabelWidth` to compute per-shape min-size. The per-edge label positioning is now real (not stub) — Plan 11-05's min-size math has accurate label rendering geometry to measure against. `portLabelMarkupForEdge` also pins font-family and font-size, giving the canvas predictable text metrics.

## Deviations from Plan

None — plan executed exactly as written. One minor addition: a defensive fallback return was added after the `switch` in `portLabelPositionForEdge` (returns `{name:'manual', args:{x:0,y:0,attrs:{'.joint-port-label':{textAnchor:'middle'}}}}` for any unexpected edge value). The plan's action spec called this out as an optional defensive fallback; it was included since it costs one line and protects against future callers passing an unexpected edge string.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `maybeAutoExpand(cell)` — empty body | `signal_flow_editor.js` | Plan 11-06 fills with Q7 auto-expansion logic (computeMinSize + shape grow + sfd-toast) |

The two stubs targeted by this plan (`portLabelPositionForEdge`, `portLabelMarkupForEdge`) are now fully implemented. The only remaining stub in the port-authoring layer is `maybeAutoExpand`.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Pure presentation layer.

- T-11-04-01 (XSS via SVG text content): JointJS renders engineer text via `textContent` into the SVG `<text>` element (never `innerHTML`). SVG `<text>` cannot execute scripts. No new attack surface.
- T-11-04-02 (font taint of PNG export): Two-layer defense implemented — `portLabelMarkupForEdge` sets `font-family` inline on the markup attributes AND CSS Section 14 sets `.joint-port-label text { font-family: ... !important; }`. Both reference the same system-fonts-only stack (FONT_STACK constant + verbatim CSS literal).

## Self-Check: PASSED

Files exist:
- `planner/static/planner/js/signal_flow_editor.js` — confirmed (`node --check` exit 0)
- `planner/static/planner/css/signal_flow.css` — confirmed (Section 14 at line 811)

Commits exist:
- `6a08a70` — Task 1 (feat: replace portLabelPositionForEdge + portLabelMarkupForEdge stubs)
- `a853c28` — Task 2 (feat: CSS Section 14 + Section 7 cross-reference comment)
