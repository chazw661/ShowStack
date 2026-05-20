# Phase 8: Canvas, Smart Shapes & Connectors — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 08-canvas-smart-shapes-connectors
**Areas discussed:** Shape style + sidebar picker, Toolbar + connector inspector, Equipment picker modal, Canvas + signal-type visual conventions

---

## Shape Style + Sidebar Picker

### Q1: Should the 5 shape types have distinct geometry, or all share the same rectangle with a type indicator?

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct geometry per type | Console=wide rect, Device=standard rect, SpeakerArray=trapezoid/parallelogram, CommBeltPack=pill/rounded-rect, Generic=dashed-border rect | ✓ |
| All rectangles, color band + icon | Type encoded by colored edge or corner icon | |
| All rectangles, type as text badge | Type label as small text inside body ("CONSOLE \| CL5-FOH") | |

**User's choice:** Distinct geometry per type (Recommended)
**Rationale:** Live audio engineers visually parse topology faster when silhouette encodes role.

### Q2: Visual identity — should each shape type carry a brand color, or stay monochrome?

| Option | Description | Selected |
|--------|-------------|----------|
| Subtle color band per type | Thin colored stripe (top/left edge): teal/slate/orange/purple/grey; body stays white | ✓ |
| Full-fill color per type | Body fill matches type color (light tint) | |
| Pure monochrome (white body, black border) | All shapes look identical except for geometry | |

**User's choice:** Subtle color band per type (Recommended)
**Rationale:** Adds glanceability without dominating the diagram or competing with signal-type connector colors.

### Q3: Where should the shape picker sidebar live in the editor?

| Option | Description | Selected |
|--------|-------------|----------|
| Left vertical sidebar | Narrow column on the left; 5 tiles stacked vertically (icon + label) | ✓ |
| Top horizontal strip below toolbar | Second row beneath top toolbar; tiles laid out horizontally | |
| Collapsible left drawer (off by default) | Hidden behind hamburger toggle | |

**User's choice:** Left vertical sidebar (Recommended)
**Rationale:** Matches Lucidchart / draw.io convention. Keeps top toolbar clean for canvas actions.

### Q4: How does the user move a shape from the sidebar onto the canvas?

| Option | Description | Selected |
|--------|-------------|----------|
| Drag-to-canvas, drop at cursor | Standard HTML5 drag-drop; lands at exact cursor coords via `paper.clientToLocalPoint()` | ✓ |
| Click tile, then click canvas | Two-step: arm shape on sidebar click, drop on canvas click | |
| Double-click tile drops at canvas center | One-action shortcut | |

**User's choice:** Drag-to-canvas, drop at cursor (Recommended)
**Rationale:** Matches CNV-01 acceptance criterion verbatim. Industry standard.

---

## Toolbar + Connector Inspector

### Q1: Where should the connector property editor live?

| Option | Description | Selected |
|--------|-------------|----------|
| Floating right-side inspector panel | Slides in on connector select; signal-type / direction / circuit-label fields | ✓ |
| Inline floating popover anchored to connector midpoint | Small popover at midpoint when selected | |
| Modal on double-click | Modal with 3 fields, OK/Cancel | |
| Right-click context menu + inline label edit | Context menu for signal type / direction, inline label edit | |

**User's choice:** Floating right-side inspector panel (Recommended)
**Rationale:** Standard Figma / Lucidchart / draw.io pattern. Same panel reusable for node properties later.

### Q2: Top toolbar contents — minimal canvas controls only, or include connector quick-actions?

| Option | Description | Selected |
|--------|-------------|----------|
| Canvas controls only | Zoom in/out/fit + snap toggle + undo/redo + save status (Phase 9) | ✓ |
| Canvas controls + connector quick-actions | Also includes signal-type dropdown + direction toggle when connector selected | |
| Canvas controls + delete button | Adds a dedicated delete button alongside Delete/Backspace keys | |

**User's choice:** Canvas controls only (Recommended)
**Rationale:** Toolbar stays uncluttered. All connector-specific actions live in the right-side inspector.

### Q3: Inspector visibility behavior — when should the right-side panel be open?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-show on connector select, auto-hide on clear | Panel state driven entirely by selection | ✓ |
| Manual toggle button in toolbar | Panel state persists; user toggles open/closed | |
| Always-visible right-side panel | Permanent panel; shows 'No selection' state when nothing selected | |

**User's choice:** Auto-show on connector select, auto-hide on clear (Recommended)
**Rationale:** Zero config; canvas gets max space when not editing.

### Q4: When a node or connector is selected, how should the selection be visually indicated?

| Option | Description | Selected |
|--------|-------------|----------|
| Highlighted border + dotted bbox | 2px accent border + dashed bbox around multi-select group | ✓ |
| Glow / shadow effect | Soft colored glow via CSS filter / SVG shadow | |
| Border only, no group bbox | Border accent only; every multi-select member gets its own border | |

**User's choice:** Highlighted border + dotted bbox (Recommended)
**Rationale:** Standard CAD/diagram convention. Easy to read in dark + light themes.

---

## Equipment Picker Modal

### Q1: When a user drops a typed shape (Console / Device / SpeakerArray / CommBeltPack), when should the picker open?

| Option | Description | Selected |
|--------|-------------|----------|
| Drop first, then modal opens at drop site | Placeholder shape lands at coords; modal opens centered | ✓ |
| Pick record first in sidebar, then drag | Sidebar tile expands to filterable list of project records; drag specific record | |
| Drop first, deferred picker (open on click) | Shape lands as "Click to assign"; user clicks later to bind | |

**User's choice:** Drop first, then modal opens at drop site (Recommended)
**Rationale:** Matches CNV-01 spec. Spatially natural: "I put it there, now I'll say what it is."

### Q2: If the user cancels the picker modal after dropping a typed shape, what happens?

| Option | Description | Selected |
|--------|-------------|----------|
| Shape is removed from canvas | Cancelling undoes the drop entirely | ✓ |
| Shape becomes a Generic shape with placeholder label | Cancelled shape converts to Generic type with "Untitled" label | |
| Shape stays, marked 'unassigned' with warning style | Warning-styled placeholder; user can re-open picker by clicking | |

**User's choice:** Shape is removed from canvas (Recommended)
**Rationale:** No half-built / unassigned-state nodes in canvas JSON. Engineers who want freeform use the Generic type.

### Q3: Search and filter behavior inside the picker modal:

| Option | Description | Selected |
|--------|-------------|----------|
| Instant text search across name + key fields | Search input at top filters as user types | ✓ |
| Categorized list (no search) | Records grouped by sub-type (e.g., Devices by family) | |
| Simple alphabetical list with scrollable column | No search/filter; alphabetical list only | |

**User's choice:** Instant text search across name + key fields (Recommended)
**Rationale:** Scales to projects with 20+ records per type.

### Q4: Modal styling and pattern — reuse the admin pattern, or build a custom one?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse Django admin modal pattern | Match `_help_modal.html` + admin theme variables | ✓ |
| Custom canvas-themed modal | Glass effect / softer shadow tuned to canvas context | |
| Floating dropdown anchored to drop site (no backdrop) | Compact dropdown attached to placeholder shape | |

**User's choice:** Reuse Django admin modal pattern (Recommended)
**Rationale:** Visually coherent with the rest of ShowStack. Lowest CSS surface.

---

## Canvas + Signal-Type Visual Conventions

### Q1: Snap-to-grid behavior on a fresh diagram — default state and grid size?

| Option | Description | Selected |
|--------|-------------|----------|
| ON by default, 20px grid | Snap enabled on first open; 20px grid visible as light dotted lines | ✓ |
| ON by default, 10px grid | Finer grid; less visible snap behavior on small shapes | |
| OFF by default, 20px grid when on | Free placement initially; grid kicks in only when toggled | |

**User's choice:** ON by default, 20px grid (Recommended)
**Rationale:** Engineers laying out signal flow benefit from aligned topology by default. 20px works for both Console (wide) and BeltPack (small) shapes.

### Q2: Canvas paper size strategy — finite (with bounds) or effectively infinite?

| Option | Description | Selected |
|--------|-------------|----------|
| Large finite bounds, 4000×3000 px | Bounded but generous; no PaperScroller complexity | ✓ |
| Smaller bounds, 2000×1500 px | Tighter; faster render; risk of wall on multi-zone PA / broadcast | |
| Effectively infinite (PaperScroller pattern) | Canvas grows as engineer pans; requires custom scroll handling | |

**User's choice:** Large finite bounds, 4000×3000 px (Recommended)
**Rationale:** Stays inside `@joint/core`'s standard finite-paper model. Viewport persistence (CNV-08) just stores x/y/scale.

### Q3: Initial viewport on opening a diagram that has no saved viewport state:

| Option | Description | Selected |
|--------|-------------|----------|
| 100% zoom, paper origin centered on screen | Predictable fallback when viewport JSONField is `{}` | ✓ |
| Zoom-to-fit any saved content, else 100% | Auto fit-to-content when shapes exist; else default | |
| Always 80% zoom centered | Slightly zoomed-out default for room to add | |

**User's choice:** 100% zoom, paper origin centered on screen (Recommended)
**Rationale:** Predictable. Engineers familiar with 1:1 canvases.

### Q4: Signal-type line style recipe — which color + dash combination set?

| Option | Description | Selected |
|--------|-------------|----------|
| Industry-leaning recipe | Analog=solid black, AES=solid royal blue, Dante=dashed cyan, MADI=dash-dot orange, Intercom=dotted purple | ✓ |
| Conservative recipe: all black, dash carries all meaning | Maximum grayscale fidelity; sterile on screen | |
| Charlie specifies exact 5 values | Custom (color, dash, width) tuples | |

**User's choice:** Industry-leaning recipe (Recommended)
**Rationale:** Five visually distinct lines that survive grayscale (dash pattern alone differentiates each).

---

## Claude's Discretion

Areas where Charlie did not override the default:

- **Connector creation UX** — Drag from port handle (matches CON-01 wording verbatim)
- **Port visual style** — Hover-revealed ports (canvas stays clean at rest)
- **Default values on new connectors** — `analog` / `source→target` / empty circuit-label
- **Sidebar tile icons** — lucide / material icons (whichever is already in templates)
- **Exact accent / theme colors** — Pulled from existing `django-admin-interface` theme variables
- **Save trigger for Phase 8 verification** — Manual "Save" toolbar button writing to the autosave URL is acceptable; real debounced autosave is Phase 9

## Deferred Ideas

- Connector right-click context menu — replaced by the inspector
- Click-port-then-click-port alternative connector creation — replaced by drag-from-port
- Always-visible port dots alternative — replaced by hover-reveal
- Per-channel ports on shapes (SHP-08 is per-side single port only) — v2.3+
- Copy/paste of selected nodes — gated on `@joint/core` Clipboard availability, deferred to v2.3+
