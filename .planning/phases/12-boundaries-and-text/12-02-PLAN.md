---
phase: 12
plan_number: 02
wave: 1
depends_on: []
files_modified:
  - planner/static/planner/css/signal_flow.css
autonomous: true
requirements_addressed: [DRAW-02, DRAW-03, TXT-02]
must_haves:
  truths:
    - "signal_flow.css contains Section 17 (Boundary lines — DRAW) header comment with phase-and-decision references"
    - "signal_flow.css contains Section 18 (Text annotations — TXT) header comment with phase-and-decision references"
    - "Section list comment at top of signal_flow.css enumerates entries 17 and 18 with Phase 12 attribution"
    - ".sfd-color-swatches, .sfd-color-swatch, .sfd-color-swatch[data-active=true], .sfd-color-swatches--text, .sfd-text-edit-overlay, .sfd-text-fontsize-segmented button[data-size=*] selectors exist"
  artifacts:
    - path: "planner/static/planner/css/signal_flow.css"
      provides: "Section 17 + Section 18 stylesheet skeleton"
      contains: "SECTION 17 — Boundary lines (Phase 12 DRAW-01..04)"
      contains_also: "SECTION 18 — Text annotations (Phase 12 TXT-01..03)"
  key_links:
    - from: "inspector color-swatch elements (built by Plan 05)"
      to: ".sfd-color-swatch CSS rule"
      via: "class application"
      pattern: ".sfd-color-swatch"
    - from: "text-edit overlay <input> (built by Plan 04)"
      to: ".sfd-text-edit-overlay CSS rule"
      via: "class application"
      pattern: ".sfd-text-edit-overlay"
---

<objective>
Append CSS Section 17 (boundary line styles — DRAW) and Section 18 (text annotation styles — TXT) to `signal_flow.css` per the append-at-end convention established by Phase 11. Update the section-list comment at the top of the file to include the two new sections. All rules respect the dark-navy inspector palette per the user MEMORY rule (#eee primary text, #aaa muted labels) — GAP-11.7 lesson learned. This plan is foundation-only: no UI is wired yet; downstream plans (03, 04, 05) attach classes built by the JS lazily-built blocks.
</objective>

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Dark-navy inspector contrast bugs (user MEMORY GAP-11.7) | medium | Acceptance criterion: every `color:` declaration in Sections 17 + 18 uses `#eee` (primary) or `#aaa` (muted) — NOT Django-admin light-bg defaults. Light backgrounds rejected because the inspector lives on a dark surface. |
| Django admin CSS overrides our styles (no `!important`) | medium | Per signal_flow.css file-header rule (lines 1-17) and CLAUDE.md, EVERY declaration in Sections 17 + 18 carries `!important`. Acceptance criterion grep-checks for `!important` count. |
| Section header comment misses Phase 12 attribution → audit trail loss | low | Section header MUST contain literal "Phase 12" and the relevant decision IDs (D-04, D-09, D-12, D-19). |
| Overriding existing `.sfd-segmented` rules in Section 4 by accident | low | Section 17 only ADDS new rules — `button[data-style] svg` selectors are net-new and do not override Section 4's `.sfd-segmented button` rules. |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Update section-list comment + append Section 17 (DRAW) + Section 18 (TXT)</name>
  <files>planner/static/planner/css/signal_flow.css</files>
  <read_first>
    - planner/static/planner/css/signal_flow.css lines 1-40 (file header + section-list comment to be updated)
    - planner/static/planner/css/signal_flow.css lines 80-117 (#sfd-toolbar button.is-active rule — Section 1 already covers our new buttons)
    - planner/static/planner/css/signal_flow.css lines 275-301 (.sfd-segmented base — Section 17/18 extend with new data-attr selectors, do NOT override)
    - planner/static/planner/css/signal_flow.css lines 670-685 (Section 13 header — exact format to clone for Sections 17 + 18)
    - planner/static/planner/css/signal_flow.css lines 850-875 (current end of file — append target)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-12 (lines 850-961 — verbatim section-list update + Sections 17 + 18 skeleton)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "Section 17 + 18" (lines 393-423 — change directive)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md Violation 4 (lines 703-715 — dark-navy palette audit rule)
    - CLAUDE.md "Overriding Django admin CSS from JavaScript" — informs the `!important` discipline.
  </read_first>
  <action>
    Two edits to `planner/static/planner/css/signal_flow.css`:

    **EDIT 1 — Update section-list comment (replace lines 21-37 of the file header).** Locate the existing comment block listing Sections 1-16. Replace it with the full 18-entry list. The line numbers may have shifted slightly across Phase 11 closeouts; locate the block by the literal text " *   1. Toolbar button groups + dividers" and " *  16. Inspector port-list rows + trash icon". Replace those lines (and any intervening section-list lines, keeping the surrounding `/*` open and `*/` close) with EXACTLY:

    ```css
     * Sections:
     *   1. Toolbar button groups + dividers (extends Phase 7 #sfd-toolbar)
     *   2. Canvas container layout (sidebar | paper | inspector)
     *   3. Left sidebar shape picker (#sfd-sidebar + .sfd-tile)
     *   4. Right inspector panel (#sfd-inspector + .sfd-field + .sfd-segmented)
     *   5. Equipment picker modal (.sfd-picker-overlay + .sfd-pick-*)
     *   6. Toast (.sfd-toast)
     *   7. JointJS port hover-reveal (Phase 8; amended Phase 11 — see Section 14)
     *   8. Selection visual (.is-selected + .sfd-multi-bbox)
     *   9. Empty canvas hint (.sfd-empty-hint)
     *  10. 409 Conflict banner (Phase 9 D-07)
     *  11. Orphan ghost render (Phase 9 D-15 + SHP-07)
     *  12. Autocomplete dropdown (Phase 10 LBL-01..03)
     *  13. Export button group (Phase 10 EXP-01)
     *  14. Port-label rendering (Phase 11 D-08 — perpendicular-inside)
     *  15. Resize handles (Phase 11 D-05 — four corners)
     *  16. Inspector port-list rows + trash icon (Phase 11 D-02 / D-04)
     *  17. Boundary lines — DRAW (Phase 12 D-04 toolbar group, D-09 color swatches, D-12 line-style picker)
     *  18. Text annotations — TXT (Phase 12 D-19 font-size segmented, D-19 9-color picker incl. white)
    ```

    **EDIT 2 — Append Sections 17 + 18 at end of file.** Locate the current end-of-file (around line 875). Append (with one blank line before the section divider comment) the following block VERBATIM:

    ```css

    /* =========================================================================
       SECTION 17 — Boundary lines (Phase 12 DRAW-01..04)
       Toolbar buttons #sfd-tool-boundary / #sfd-tool-text inherit Section 1
       button styling and the `.is-active` teal active-state. Inspector
       boundary-mode panel uses an 8-swatch color grid (D-09) and a 4-button
       line-style segmented picker (D-12).
       Dark-navy inspector palette (#eee primary, #aaa muted) per Phase 11
       GAP-11.7 user-MEMORY rule — light-bg defaults must not leak into the
       new panel.
       ========================================================================= */

    /* Color swatch grid — 4×2 for boundary panel. Text panel overrides to 3×3
       in Section 18 via the `.sfd-color-swatches--text` modifier. */
    .sfd-color-swatches {
      display: grid !important;
      grid-template-columns: repeat(4, 1fr) !important;
      gap: 4px !important;
      margin-top: 4px !important;
    }

    .sfd-color-swatch {
      width: 100% !important;
      height: 28px !important;
      border: 1px solid #444 !important;
      border-radius: 3px !important;
      cursor: pointer !important;
      padding: 0 !important;
      /* background-color is set inline by JS to each palette hex —
         do NOT set a fallback here. */
    }

    .sfd-color-swatch[data-active="true"] {
      box-shadow: 0 0 0 2px #0d9488 inset, 0 0 0 1px #fff inset !important;
    }

    /* Line-style segmented preview — SVG <line> sized to render inside each
       segmented button. The segmented base styling (background, hover, active)
       comes from Section 4 .sfd-segmented; this rule only sizes the SVG. */
    .sfd-segmented button[data-style] svg {
      display: block !important;
      width: 28px !important;
      height: 12px !important;
    }

    /* Field labels inside boundary-mode + text-mode panels — dark-navy muted
       per the inspector palette. */
    #sfd-inspector .sfd-field[data-mode="boundary"] label,
    #sfd-inspector .sfd-field[data-mode="text"] label {
      color: #aaa !important;
      font-size: 11px !important;
    }

    /* =========================================================================
       SECTION 18 — Text annotations (Phase 12 TXT-01..03)
       Inline-edit overlay <input> (D-16, D-17), font-size segmented S/M/L
       (D-19), 9-color picker including white (D-19).
       ========================================================================= */

    /* Inline-edit overlay <input> — positioned absolutely over the cell bbox
       during edit. JS (Plan 04) sets font-size + color inline via
       setProperty(... 'important') to match the cell's current props. */
    .sfd-text-edit-overlay {
      position: absolute !important;
      border: 1px solid #0d9488 !important;
      background-color: transparent !important;
      outline: none !important;
      padding: 0 !important;
      margin: 0 !important;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
      z-index: 100 !important;
    }

    /* Font-size segmented S/M/L — each button shows its size letter scaled
       proportionally so engineer recognizes 'small'/'medium'/'large' at a glance. */
    .sfd-text-fontsize-segmented button[data-size="small"]  { font-size: 11px !important; }
    .sfd-text-fontsize-segmented button[data-size="medium"] { font-size: 13px !important; }
    .sfd-text-fontsize-segmented button[data-size="large"]  { font-size: 16px !important; }

    /* Text-mode 9-color picker — 3×3 grid (includes white per D-19).
       Overrides the 4×2 grid from Section 17. */
    .sfd-color-swatches--text {
      grid-template-columns: repeat(3, 1fr) !important;
    }
    ```

    Do NOT modify any existing section. Do NOT change Section 7 port hover-reveal (Phase 11 amendment stays as-is). Do NOT add light-background colors anywhere in Sections 17 or 18.
  </action>
  <verify>
    <automated>grep -n "SECTION 17 — Boundary lines (Phase 12 DRAW-01..04)" planner/static/planner/css/signal_flow.css && grep -n "SECTION 18 — Text annotations (Phase 12 TXT-01..03)" planner/static/planner/css/signal_flow.css && grep -n "17. Boundary lines — DRAW (Phase 12" planner/static/planner/css/signal_flow.css && grep -n "18. Text annotations — TXT (Phase 12" planner/static/planner/css/signal_flow.css && grep -n "\.sfd-color-swatches {" planner/static/planner/css/signal_flow.css && grep -n "\.sfd-color-swatch\[data-active=\"true\"\]" planner/static/planner/css/signal_flow.css && grep -n "\.sfd-text-edit-overlay {" planner/static/planner/css/signal_flow.css && grep -n "\.sfd-color-swatches--text {" planner/static/planner/css/signal_flow.css</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "SECTION 17 — Boundary lines (Phase 12 DRAW-01..04)" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "SECTION 18 — Text annotations (Phase 12 TXT-01..03)" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "17. Boundary lines — DRAW (Phase 12 D-04 toolbar group" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "18. Text annotations — TXT (Phase 12 D-19" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-color-swatches {" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-color-swatch {" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-color-swatch\\[data-active=\"true\"\\]" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-text-edit-overlay {" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-color-swatches--text {" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-text-fontsize-segmented button\\[data-size=\"small\"\\]" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-text-fontsize-segmented button\\[data-size=\"medium\"\\]" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - `grep -c "\\.sfd-text-fontsize-segmented button\\[data-size=\"large\"\\]" planner/static/planner/css/signal_flow.css` returns exactly `1`
    - The Section 17 + 18 block contains NO `color: #000;` or `color: black;` or `color: #111;` declarations (dark-navy audit) — verified by `grep -c "color: #0\\|color: black\\|color: #1" planner/static/planner/css/signal_flow.css | tail` returning the SAME count as before the edit (no new dark-on-dark text introduced).
    - The Section 17 + 18 block contains NO `background-color: #fff` or `background: white` declarations (light-bg audit) — verified by `grep -c "background.*white\\|background-color: #fff" planner/static/planner/css/signal_flow.css` returning the SAME count as before the edit.
    - Every declaration appended to the file carries `!important` — `grep -c "!important" planner/static/planner/css/signal_flow.css` count must INCREASE by at least 20 compared to pre-edit.
    - Section 17 header line number is GREATER than line 875 (i.e., appended at end, not inserted in the middle).
    - Section 18 header line number is GREATER than Section 17 header line number.
    - Browser manual: load the editor page — no broken CSS warnings in DevTools console; the page renders without visual regression on any existing inspector control.
  </acceptance_criteria>
  <done>signal_flow.css contains Sections 17 + 18 with all required selectors; section-list comment includes entries 17 + 18; editor page renders without regression.</done>
</task>

</tasks>

<verification>
- `grep -n "SECTION 1[7-8] —\\|17. Boundary lines\\|18. Text annotations" planner/static/planner/css/signal_flow.css` — expect 4 hits: section-list entries 17/18, and section header lines for 17/18.
- `grep -nc "!important" planner/static/planner/css/signal_flow.css` — count must increase by at least 20 from pre-edit baseline.
- Browser manual: open /audiopatch/signal-flow/<id>/edit/, open DevTools "Elements" panel, inspect the inspector — confirm `.sfd-color-swatches`, `.sfd-color-swatch`, `.sfd-text-edit-overlay` are declared in the stylesheet (rules visible in the Styles panel of any inspector element). No visual change yet; Plans 03-06 attach classes.
- Visual regression check: every existing inspector control (`.sfd-segmented`, `.sfd-field label`, port-list rows from Section 16) renders unchanged.
</verification>

<must_haves>
- Section 17 header comment exists with literal "SECTION 17 — Boundary lines (Phase 12 DRAW-01..04)" (DRAW-02, DRAW-03 supporting CSS).
- Section 18 header comment exists with literal "SECTION 18 — Text annotations (Phase 12 TXT-01..03)" (TXT-02 supporting CSS).
- Section-list comment at top of file enumerates entries 17 + 18 with Phase 12 attribution.
- `.sfd-color-swatches` (4×2 grid) + `.sfd-color-swatches--text` (3×3 override) + `.sfd-color-swatch` + `.sfd-color-swatch[data-active="true"]` (teal inset ring) declared.
- `.sfd-text-edit-overlay` (positioned-absolute teal-border transparent-bg overlay) declared.
- `.sfd-text-fontsize-segmented button[data-size="small"|"medium"|"large"]` (proportional letter sizing) declared.
- Every appended declaration carries `!important` (file-header convention + admin-CSS override rule).
- All `color:` declarations in Sections 17/18 use `#eee` primary / `#aaa` muted; zero light-bg defaults (dark-navy palette audit).
</must_haves>
