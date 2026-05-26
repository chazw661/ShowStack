# Phase 12: Boundary Lines + Text Annotations — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `12-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 12-boundaries-and-text
**Areas discussed:** Drawing UX, Color + style picker, Z-order / layering, Text lifecycle

---

## Gray Area Selection

**Question:** Which areas do you want to discuss for Phase 12?

| Option | Description | Selected |
|--------|-------------|----------|
| Drawing UX | Mode entry/exit, click-drag vs pen-tool, snap, toolbar placement | ✓ |
| Color + style picker | Palette spec, picker location, double-line render, segmented vs dropdown | ✓ |
| Z-order / layering | Boundary/text defaults (behind vs front), override controls | ✓ |
| Text lifecycle | Placement flow, re-edit, empty-delete, multi-line, font sizes, background | ✓ |

**User's choice:** All four areas.

---

## Drawing UX

### Q1: How does the engineer enter and exit "draw boundary" mode?

| Option | Description | Selected |
|--------|-------------|----------|
| Sticky mode | Click button → mode active until Esc, button re-click, or another tool button. Draw multiple boundaries back-to-back. | ✓ |
| One-shot mode | Click button → draw one boundary → mode auto-exits. Lower error rate but tedious for multiple zones. | |

**User's choice:** Sticky mode.

### Q2: How does drag-input translate to polyline vertices?

| Option | Description | Selected |
|--------|-------------|----------|
| Click-each-vertex pen-tool | Click per vertex; double-click or Esc finishes. Clean vertex count, usable for DRAW-04 reshape. | ✓ |
| Click-drag freeform | Mousedown → drag → mouseup. Generates dozens of vertices per gesture; unusable for vertex-edit without decimation. | |
| Hybrid (drag OR click) | Both interaction models; flexible but doubles test surface. | |

**User's choice:** Click-each-vertex pen-tool.

### Q3: Do boundary vertices snap to the 20px grid when snap toggle is on?

| Option | Description | Selected |
|--------|-------------|----------|
| Snap to grid | Matches Phase 8 D-13; one snap rule across the whole canvas. | ✓ |
| Always freeform | Vertices ignore the grid; clashes with the 20px-everywhere mental model. | |
| Always snap | Vertices always snap regardless of toggle; breaks "snap toggle is universal" rule. | |

**User's choice:** Snap to grid.

### Q4: Where do the new toolbar buttons (Draw boundary + Place text) sit?

| Option | Description | Selected |
|--------|-------------|----------|
| New tools group between undo/redo and right-spacer | `.sfd-btn-group` with both buttons; matches toolbar grammar (zoom \| snap \| undo/redo \| **[new tools]** \| spacer \| export). | ✓ |
| Each button in its own group | Two single-button groups; cleaner separation but more dividers. | |
| Add as draggable tiles in left sidebar | Mixes "drag to add" with "click to arm mode" — different interaction model. | |

**User's choice:** New tools group between undo/redo and right-spacer.

### Q5: Esc mid-polyline behavior (after ≥1 vertex placed, before double-click)?

| Option | Description | Selected |
|--------|-------------|----------|
| Finish at current vertex | Esc commits vertices placed so far (≥2 required) and exits mode. Matches Lucidchart pen-tool. | ✓ |
| Cancel entire draw | Esc throws away all in-progress vertices. Loses work if almost done. | |
| Finish if ≥2 vertices, cancel if 1 | Hybrid; most forgiving but adds a branch. | |

**User's choice:** Finish at current vertex.

### Q6: How do vertex-edit handles (DRAW-04) appear on a selected boundary?

| Option | Description | Selected |
|--------|-------------|----------|
| Always-visible on selection | Small teal `#0d9488` circles on every vertex; matches Phase 11 D-05 corner-resize handles. | ✓ |
| Hover-revealed | Handles appear when cursor is near. Lower visual noise but engineer has to hunt. | |
| Edit-mode toggle in inspector | "Edit vertices" sub-mode; controlled but adds a step. | |

**User's choice:** Always-visible on selection.

### Q7: Cursor visual + button state when draw mode is active?

| Option | Description | Selected |
|--------|-------------|----------|
| Crosshair cursor + button `.is-active` | `#sfd-paper { cursor: crosshair }` + `aria-pressed="true"` on the button. Two strong signals. | ✓ |
| Button `.is-active` only | Just the button highlights; cursor stays default. Easier to lose track of mode. | |

**User's choice:** Crosshair cursor + button `.is-active`.

### Q8: Add/delete vertex on an existing boundary line — in scope for Phase 12?

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to v2.4+ | Phase 12 ships drag-existing-vertices only (DRAW-04 as written). Keeps scope tight. | ✓ |
| Include right-click vertex → delete | Cheap to implement; scope addition beyond requirements. | |
| Include both add + delete | Full vertex CRUD; arguably overkill for the FOH/Stage-Left use case. | |

**User's choice:** Defer to v2.4+.

---

## Color + Style Picker

### Q9: 8-color palette — Tailwind 600 family hex values?

| Option | Description | Selected |
|--------|-------------|----------|
| 8 saturated print-safe colors | Black `#000000`, Grey `#666666`, Red `#dc2626`, Orange `#ea580c`, Yellow `#eab308`, Green `#16a34a`, Blue `#2563eb`, Purple `#9333ea`. | ✓ |
| 8 muted/pastel colors | Easier on the eye on-screen but may wash out in printed riders. | |
| Charlie supplies specific hex values | Brand-spec round-trip; locks brand fidelity. | |

**User's choice:** 8 saturated print-safe colors (Tailwind 600 family).

### Q10: Where do the color + line-style pickers live?

| Option | Description | Selected |
|--------|-------------|----------|
| Inspector-only + sticky defaults | All editing in inspector; next-drawn inherits last-used. Zero toolbar bloat. | ✓ |
| Toolbar defaults + inspector edit | Toolbar gets color swatch + style dropdown; inspector mirrors. Doubles UI surface. | |
| Inspector-only + first-time-default | Inspector-only; new boundaries always start at black/solid. Tedious when drawing 6 red zones. | |

**User's choice:** Inspector-only + sticky defaults.

### Q11: How does "double" line style render visually (DRAW-02)?

| Option | Description | Selected |
|--------|-------------|----------|
| Two parallel solid lines, 3px apart | Architectural-drawing convention; SVG `<g>` with two `<polyline>` siblings. Most readable. | ✓ |
| Thick single stroke | Cheap but visually identical to a heavier solid line. | |
| Solid + parallel offset shadow | Uncommon convention. | |

**User's choice:** Two parallel solid lines, 3px apart.

### Q12: Line-style UI in the inspector — segmented buttons or dropdown?

| Option | Description | Selected |
|--------|-------------|----------|
| Segmented buttons with stroke previews | 4 buttons with SVG stroke previews. Matches `.sfd-segmented` connector signal-type pattern. | ✓ |
| Dropdown with text labels | `<select>` with text options. Compact but slower. | |
| Segmented buttons with text labels only | Cheaper to render but no visual preview. | |

**User's choice:** Segmented buttons with stroke previews.

---

## Z-Order / Layering

### Q13: Default z-order for newly drawn boundary lines?

| Option | Description | Selected |
|--------|-------------|----------|
| Behind shapes + connectors | "FOH zone is a background wall, console rack sits inside it" mental model. Low JointJS `z`. | ✓ |
| In front of shapes + connectors | Overlay use case; wrong for live-audio zones. | |
| Above shapes, below connectors | Compromise but counter-intuitive (zones would clip shapes). | |

**User's choice:** Behind shapes + connectors.

### Q14: Default z-order for newly placed text annotations?

| Option | Description | Selected |
|--------|-------------|----------|
| On top of everything | Above shapes, connectors, and boundaries. Labels stay readable. Highest JointJS `z`. | ✓ |
| Above boundaries, below shapes | Cleaner but engineer can't annotate a specific shape. | |
| Behind shapes (same as boundaries) | Almost certainly wrong; callouts would disappear under racks. | |

**User's choice:** On top of everything.

### Q15: Engineer-controlled layer overrides — in scope for Phase 12?

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to v2.4+ | Fixed z-order defaults only; bring-forward/send-back deferred. Keeps inspector simple. | ✓ |
| Inspector arrows (↑ / ↓) | Selected element gets bring-forward / send-back controls; rarely used. | |
| Inspector + right-click context menu | Full 4-button set; more than the use case needs. | |

**User's choice:** Defer to v2.4+.

---

## Text Lifecycle

### Q16: Placement + initial-edit flow when engineer clicks "Place text" then clicks the canvas?

| Option | Description | Selected |
|--------|-------------|----------|
| Click → inline edit immediately | Click places element AND drops engineer into edit mode with blinking caret. Enter / click-out commits; Esc cancels (deletes empty). Matches Figma/Lucidchart/Miro. | ✓ |
| Click → select → separate edit step | Click places placeholder; engineer double-clicks (or Enter) to enter edit mode. Two steps to type one label. | |

**User's choice:** Click → inline edit immediately.

### Q17: How does engineer re-edit text after it's been committed?

| Option | Description | Selected |
|--------|-------------|----------|
| Double-click on canvas | Double-click enters inline edit; single-click selects + shows style controls. Matches placement-edit flow. | ✓ |
| Inspector "Edit text" button | Textarea in inspector; eye jumps canvas ↔ inspector. | |
| Always-on inline edit when selected | Single-click selects AND enters edit; hard to drag. | |

**User's choice:** Double-click on canvas.

### Q18: Multi-line text + empty-text handling?

| Option | Description | Selected |
|--------|-------------|----------|
| Single-line + auto-delete empty | Enter commits; no newlines. Empty body auto-deletes the element. Aligns with no-rich-text constraint. | ✓ |
| Multi-line via Shift+Enter, empty preserved | Shift+Enter inserts newline; empty stays as placeholder. Adds wrap/measurement work. | |
| Multi-line via Shift+Enter, auto-delete empty | Hybrid; best of both if engineers want paragraphs. Adds wrap plus empty-delete branch. | |

**User's choice:** Single-line + auto-delete empty.

### Q19: Font sizes S/M/L pixel values + text background fill?

| Option | Description | Selected |
|--------|-------------|----------|
| 12 / 16 / 24 px, transparent background | S matches port-label 12px; M matches toolbar 16px (default); L = 24px callout. Transparent — engineer color-picks for legibility. | ✓ |
| 12 / 18 / 28 px, transparent background | Slightly larger spread; 18px M reads better at moderate zoom. | |
| 12 / 16 / 24 px, white background pill | White rounded-rect background for legibility against colored boundaries. Conflicts with white PNG-export look. | |

**User's choice:** 12 / 16 / 24 px, transparent background.

---

## Closing Confirmation

**Question:** Ready to create CONTEXT.md, or any gray area still unclear?

| Option | Description | Selected |
|--------|-------------|----------|
| Create context | All 4 areas resolved; carried-forward constraints cover the rest. | ✓ |
| Explore more gray areas | Meaningful decisions still open (text palette specifics, stroke width, multi-select drag, canvas_state cell encoding). | |

**User's choice:** Create context.

---

## Claude's Discretion

The following items were intentionally left to the researcher / planner:

- JointJS cell-class strategy (custom `joint.shapes.showstack.BoundaryLine` / `.TextLabel` vs extending `joint.shapes.standard.Polyline` / `.TextBlock`).
- Color-swatch grid layout in the inspector (4×2 vs 8×1 vs 9×1 with white for TXT).
- Selected-swatch visual treatment (ring, outline, checkmark; teal `#0d9488` suggested).
- Boundary stroke width default (likely 2 px; not engineer-configurable in v2.3).
- Session-sticky default storage (closure-scoped IIFE state vs `sessionStorage`).
- Initial defaults before any sticky value exists (suggested: boundary black solid 2px; text medium 16px black).
- Vertex-handle hit-target size (visible 6 px circle; transparent hit area ~12 px).
- Edge-case behavior: click outside the canvas while a mode is sticky-active (suggested: no-op, do not exit mode).
- Toast on first boundary/text creation — not required.
- Text element bounding box / drag-target geometry (researcher decides per JointJS-native vs custom-element).

---

## Deferred Ideas

Captured during discussion, explicitly out of Phase 12 scope:

- Curved boundary lines (Bezier) — milestone-deferred (`DRAW-CURVE-01`).
- Filled translucent zone shapes — milestone-deferred (`DRAW-FILL-01`).
- Rich text formatting (bold/italic) — milestone-deferred.
- Multi-line text via Shift+Enter — v2.4+ if engineers report needing paragraphs.
- Add/delete vertex post-creation (right-click delete, double-click insert) — v2.4+.
- Engineer-controlled z-order overrides (bring-forward / send-back) — v2.4+ if defaults aren't enough.
- Toolbar color/style defaults (vs inspector-only) — rejected per D-10.
- White-pill text background (vs transparent) — rejected per D-19 (PNG export contrast issue).
- "Clean export" mode (hide DRAW + TXT in PNG) — not requested; PNG includes everything per Phase 10 D-08.
- Boundary stroke width as engineer-configurable — not in v2.3; default fixed.
- Per-port routing intelligence on boundaries — milestone-excluded; boundaries are decorative.
- Right-click context menu on canvas — out of editor scope (no right-click anywhere today).
