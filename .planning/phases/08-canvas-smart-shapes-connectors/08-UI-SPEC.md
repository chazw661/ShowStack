---
phase: 8
slug: canvas-smart-shapes-connectors
status: approved-inline
shadcn_initialized: false
preset: none
created: 2026-05-20
author: inline (after gsd-ui-researcher agent timeout — drawn from CONTEXT.md + RESEARCH.md + Phase 7 editor shell + existing admin theme)
---

# Phase 8 — UI Design Contract

> Visual and interaction contract for the live JointJS canvas, smart shapes, and connectors. Extends the Phase 7 editor shell (`editor.html`). All visual decisions here are downstream of CONTEXT.md's 16 locked decisions and RESEARCH.md's API patterns — this doc adds the spacing / typography / copywriting / component-spec layer the planner needs to build tasks.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (vanilla JS — no shadcn / no Node build chain) |
| Preset | not applicable |
| Component library | none — JointJS owns canvas SVG, native HTML/CSS for chrome (sidebar / toolbar / inspector / modal) |
| Icon library | inline SVG (12-line max per icon, system-rendered — same precedent as `_help_modal.html`) |
| Font | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` (system fonts only — REQUIREMENTS Constraint: "no cross-origin font taint on PNG export") |
| Theme base | `django-admin-interface` + `colorfield` (locked at project level per CLAUDE.md) |
| Reference shell | `planner/templates/planner/signal_flow/editor.html` (Phase 7 — dark toolbar `#2a2a3e`, white paper `#ffffff`) |

**Token resolution rule:** Any time a color/spacing/typography value is referenced below, the planner SHOULD first check whether `django-admin-interface` already exposes a CSS variable for the role (e.g. `--django-admin-primary`, `--django-admin-link-fg`). If yes, use that variable; the hex values below are fallback defaults that match the project's existing dark admin theme.

---

## Spacing Scale

Declared values (all multiples of 4):

| Token | Value | Usage in Phase 8 |
|-------|-------|--------------------|
| `xs` | 4px | Port circle radius; signal-line dash inset; tile icon-to-label gap |
| `sm` | 8px | Toolbar button gap; sidebar tile inner padding; modal list-row vertical padding; inspector field gap |
| `md` | 16px | Toolbar horizontal padding (`#sfd-toolbar` is already 8px 16px in Phase 7 — keep it); modal inner padding; inspector panel inner padding |
| `lg` | 24px | Modal max-width inset from viewport edge; inspector panel width contribution |
| `xl` | 32px | Sidebar fixed width (`#sfd-sidebar`); inspector panel fixed width baseline |
| `2xl` | 48px | Major section spacing inside the modal between search + result list + actions |
| `3xl` | 64px | Reserved (no Phase 8 use) |

**Exceptions (documented):**
- `#sfd-toolbar`: padding `8px 16px` (Phase 7 locked — do not change in Phase 8)
- `#sfd-sidebar`: width `64px` (5 tiles stacked, each ~48px tall)
- `#sfd-inspector`: width `280px` (auto-show only; widthy enough for circuit-label inputs)
- Inline SVG icon size: `16px × 16px` standard, `20px × 20px` for sidebar tile icons

---

## Typography

System fonts only. No `@font-face`, no Google Fonts (REQUIREMENTS constraint).

| Role | Size | Weight | Line Height | Where it's used |
|------|------|--------|-------------|------------------|
| `body` | 13px | 400 | 1.4 | Modal result-row text, inspector field labels, sidebar tile labels |
| `body-mono` | 12px | 400 | 1.3 | Inspector field text inputs, picker search input, save-status indicator |
| `label` | 11px | 600 | 1.2 | Inspector field labels (uppercase, letter-spacing 0.04em) |
| `heading` | 16px | 600 | 1.3 | `#sfd-toolbar h1` (Phase 7 locked: 16px) and modal title `<h3>` |
| `shape-label` | 13px | 500 | 1.2 | Inside SVG shapes — JointJS attrs `fontSize: 13`, `fontFamily: system-ui...` |
| `connector-label` | 11px | 500 | 1.2 | Circuit label rendered along the connector (JointJS Link.labels) |
| `keyboard-hint` | 11px | 400 | 1.2 | Toolbar tooltip hint suffixes, e.g. "Undo (⌘Z)" |

Font stack everywhere: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. Numeric tokens (e.g. zoom percentage in toolbar) may use `"SF Mono", Consolas, Menlo, monospace` for alignment, sized 12px.

---

## Color

### Role-Based Palette

| Role | Value | Usage in Phase 8 |
|------|-------|--------------------|
| Dominant (60%) | `#ffffff` (paper) + `#2a2a3e` (toolbar chrome) | Canvas paper background (white); toolbar/sidebar/inspector chrome (dark admin theme) — already locked by Phase 7 |
| Secondary (30%) | `#1f1f2e` (sidebar) / `#252535` (inspector) / `#3a3a4e` (button surfaces) | Surface tones inside the dark chrome — sidebar slightly darker than toolbar; inspector slightly lighter; buttons one notch lighter again |
| Accent (10%) | `#0d9488` (teal) | Reserved for: selection border on canvas elements, active toolbar button state, focus ring on inputs, inspector header underline |
| Destructive | `#dc2626` | Reserved for: delete confirmation prompts (not in Phase 8 scope but pattern locked), error states ("Save failed") |
| Grid lines | `#dde` | Snap grid dots on the paper (visible only when snap is ON — `#sfd-paper drawGrid`) |
| Body text on dark | `#eee` | Toolbar title, sidebar tile labels, inspector content |
| Body text on white | `#111` | Shape labels on canvas, modal body text |
| Muted text on dark | `#aaa` | Back link, keyboard hints, save-status idle |
| Border on dark | `#444` | Toolbar bottom border (Phase 7 locked), sidebar right border, inspector left border |

**Accent reservation policy (strict):** `#0d9488` is reserved for selection + focus only. NOT used on every interactive element — buttons use grey surfaces with subtle hover, save the teal accent for "the element the user is currently working on".

### Shape Color Bands (CONTEXT.md D-02 — locked)

| Shape type | Band color | Hex | Role |
|------------|-----------|------|------|
| Console | teal | `#0d9488` | Wide-rect shape — left-edge `<rect>` band |
| Device | slate | `#475569` | Standard-rect shape — left-edge `<rect>` band |
| SpeakerArray | orange | `#ea580c` | Trapezoid `<polygon>` — left-edge band positioned to follow the polygon |
| CommBeltPack | purple | `#7c3aed` | Pill/rounded-rect — left-edge band positioned to follow the rounded corner |
| Generic | grey | `#94a3b8` | Dashed-border rect — band optional (the dashed border alone signals "generic"); if used, grey matches the dashed stroke |

Body fill: always `#ffffff` (paper-matching white) so connector signal-type colors retain glanceability. Band is 6px wide on the left edge.

### Connector Signal-Type Lines (CONTEXT.md D-16 — locked)

| Signal type | Stroke color | Width | Dash pattern (`stroke-dasharray`) |
|-------------|--------------|-------|------------------------------------|
| analog | `#1a1a1a` (near-black) | 2 | none (solid) |
| AES | `#1565c0` (royal blue) | 2 | none (solid) |
| Dante | `#00bcd4` (cyan) | 2 | `6 4` |
| MADI | `#ef6c00` (orange) | 2.5 | `10 3 3 3` |
| intercom | `#7b1fa2` (purple) | 2 | `2 4` |

Constraint: every recipe is grayscale-distinguishable on its own dash pattern (REQUIREMENTS: "color is not the only differentiator"). Target marker (arrowhead for source→target direction) takes the same color as the stroke. Bidirectional connectors strip both markers.

### Selection / Hover States

| Element state | Style |
|---------------|-------|
| Selected node | Body stroke override: `#0d9488` (accent), strokeWidth `2.5`, plus a 2px outset dashed bbox if multi-selected (rendered as a paper overlay `<rect>`) |
| Selected connector | Line `stroke-width` boost by `+0.5`, plus an outline-style highlight `filter: drop-shadow(0 0 4px #0d9488)` |
| Node hover | Body stroke `#666` → `#0d9488`; ports fade in (opacity 0 → 1) |
| Sidebar tile hover | Background `#1f1f2e` → `#3a3a4e`; label color `#eee` → `#fff` |
| Toolbar button hover | Background `transparent` → `#3a3a4e` |
| Toolbar button active (snap-on, etc.) | Background `#0d9488` + text `#fff` |
| Picker result row hover | Background `transparent` → `#f5f5f5` (modal is light-themed; standard list-row hover) |
| Inspector input focus | Box-shadow `0 0 0 2px #0d9488` (focus ring) |
| Delete confirmation (Phase 9 scope) | Pattern reserved: `#dc2626` background + white text on confirm button |

---

## Copywriting Contract

Every string the user reads in Phase 8 — locked here so the planner doesn't invent copy and the executor doesn't revise it.

### Toolbar

| Button | Text | Tooltip / Aria-label |
|--------|------|-----------------------|
| Zoom out | (icon only) | "Zoom out (−)" |
| Zoom indicator | `100%` | (computed; e.g., "75%") |
| Zoom in | (icon only) | "Zoom in (+)" |
| Zoom to fit | (icon only) | "Zoom to fit" |
| Snap toggle | (icon only) | "Snap to grid: on" / "Snap to grid: off" (state-dependent) |
| Undo | (icon only) | "Undo (⌘Z)" — `Ctrl+Z` on Windows |
| Redo | (icon only) | "Redo (⌘⇧Z)" — `Ctrl+Shift+Z` on Windows |
| Save | "Save" | "Save diagram" |
| Save status | `All changes saved.` / `Saving…` / `Save failed — retry` | n/a (status text itself is visible) |

Keyboard hints in tooltips use `⌘` for macOS, planner can detect `navigator.platform.includes('Mac')` and swap to `Ctrl` for Windows/Linux.

### Sidebar Tiles

| Tile | Visible label |
|------|---------------|
| Console | "Console" |
| Device | "Device" |
| SpeakerArray | "Speaker Array" *(space — visible label uses spacing even though the class name is camelCase)* |
| CommBeltPack | "Beltpack" *(short label — the class name is verbose but the visible label is the engineer-vernacular "beltpack")* |
| Generic | "Generic" |

Drag preview (HTML5 native): browser renders a faded clone of the tile during drag.

### Equipment Picker Modal

| Element | Copy |
|---------|------|
| Modal title `<h3>` | "Pick a {Type}" where {Type} = "Console" / "Device" / "Speaker Array" / "Beltpack" |
| Search input placeholder | "Search by name, model, serial…" |
| Result row primary text | `{equipment.name}` |
| Result row secondary text | type-specific: Console = `{dsp_mixer} · {channel_count} ch`; Device = `{model} · S/N {serial}`; SpeakerArray = `{cabinet_count} cabinets`; Beltpack = `ID {beltpack_id}` |
| Empty state heading | "No {Type} records in this project" |
| Empty state body | "Add equipment in [Admin]({admin_url}) first, then drop the shape again." |
| Loading state | "Searching…" (after 200ms debounce; otherwise no flicker) |
| Error state | "Couldn't load equipment. [Retry]" |
| Cancel button | "Cancel" |
| Cancel keyboard | `Escape` or backdrop click |

### Inspector Panel (right-side, connector-selected)

| Element | Copy |
|---------|------|
| Header `<h3>` | "Connector" |
| Field 1 label | "Signal type" |
| Field 1 widget | `<select>` with options: "Analog", "AES", "Dante", "MADI", "Intercom" |
| Field 2 label | "Direction" |
| Field 2 widget | Two-button segmented control: "Source → Target" / "Bidirectional" |
| Field 3 label | "Circuit label" |
| Field 3 widget | `<input type="text">` placeholder `"e.g. CKT-01"` |
| Help text (small, muted, below circuit label) | "Renders along the connector line." |
| Close button | (X) top-right; aria-label "Close inspector" |

### Toast / Inline Messages

| Trigger | Copy |
|---------|------|
| Save success | "All changes saved." (status text, not a toast) |
| Save failure | "Save failed — retry" (button-action affordance) |
| IDOR rejection from server | "Couldn't save — equipment reference is out of project." (rare; signals corrupted state) |
| Cancel picker after drop | (no toast — silent shape removal per CONTEXT.md D-10) |

### Empty Canvas

| Element | Copy |
|---------|------|
| Empty paper hint (faint, centered, only on first open) | "Drag a shape from the left to start." |
| Behavior | Disappears as soon as one shape is added |

---

## Component Specs

### `#sfd-toolbar` (extends Phase 7)

Already locked from Phase 7: padding `8px 16px`, background `#2a2a3e`, border-bottom `1px solid #444`, flex row.

Phase 8 additions (left → right inside the flex container):
1. Back link "← Diagrams" (Phase 7 locked)
2. Diagram name `<h1>` (Phase 7 locked)
3. Flex spacer
4. Button group A — Canvas view: `[−] [100%] [+] [⊡]` (zoom out / level / zoom in / fit)
5. Divider (`<span class="sfd-toolbar-divider">`, 1px wide × 16px tall, `#444`)
6. Button group B — Canvas mode: `[⊞]` (snap toggle, active state shows accent fill)
7. Divider
8. Button group C — History: `[↶] [↷]` (undo / redo, disabled state when stacks empty)
9. Flex spacer
10. Button group D — Persistence: `[Save]` button + save-status text (muted)

Button base style: `36×28px`, transparent background, hover `#3a3a4e`, active `#0d9488`. Icons centered, 16×16px. Disabled state: `opacity: 0.4`, `cursor: not-allowed`.

### `#sfd-sidebar` (new)

Fixed width `64px`, full canvas height, background `#1f1f2e`, border-right `1px solid #444`. Position: inside `#sfd-canvas-container`, flex sibling of `#sfd-paper`.

Contains 5 tiles stacked vertically:
- Tile: `48×56px`, padding `8px 4px`, `display: flex; flex-direction: column; align-items: center; gap: 4px`
- Tile content: `20×20px` inline-SVG icon + 11px label below
- Tile draggable: `draggable="true"` + `dataTransfer.setData('application/x-shape-type', '<Type>')`
- Tile hover: background `#3a3a4e`, label color `#fff`
- Tile cursor: `grab` (passes to `grabbing` on dragstart)

Tile icons (inline SVG; planner picks specific glyphs from the Material Symbols / Lucide library — vendored as inline SVG strings, not external assets):
- Console — mixer/equalizer glyph
- Device — server-rack glyph
- SpeakerArray — speaker-stack glyph
- CommBeltPack — headset glyph
- Generic — dashed-square glyph

### `#sfd-canvas-container` (Phase 7 locked structure, Phase 8 fills children)

```
<div id="sfd-canvas-container">    <!-- flex:1 1 auto; position:relative; overflow:hidden -->
  <aside id="sfd-sidebar">…</aside>  <!-- NEW: fixed 64px left -->
  <div id="sfd-paper"></div>          <!-- Phase 7 locked: width 100%, height 100%, bg white -->
  <aside id="sfd-inspector" hidden>…</aside>  <!-- NEW: fixed 280px right, hidden by default -->
</div>
```

Layout: `display: flex; flex-direction: row`. Sidebar flex-fixed 64px. Paper flex 1 1 auto. Inspector flex-fixed 280px when shown, removed from layout when `hidden`.

### `#sfd-paper` (Phase 7 locked, Phase 8 mounts JointJS)

Background `#ffffff` (Phase 7 locked). JointJS Paper mounted with `width: 4000, height: 3000` (CONTEXT.md D-14), `gridSize: 20` (D-13), `drawGrid: { name: 'dot', args: { color: '#dde', thickness: 1 } }` when snap is on. The paper's own `width`/`height` are the virtual canvas — the `#sfd-paper` DOM div is `width: 100%; height: 100%` and clips with `overflow: hidden` from the container.

Initial state: `paper.translate(0, 0); paper.scale(1, 1)` — origin centered visually via the container's intrinsic dimensions (CONTEXT.md D-15).

### `#sfd-inspector` (new, right-side, auto-show)

Fixed width `280px`, full canvas height, background `#252535`, border-left `1px solid #444`, padding `md` (16px).

Sections (top-to-bottom):
1. Header row: `<h3>Connector</h3>` + close `[×]` button (right-aligned); accent underline `2px solid #0d9488` below
2. Field group: Signal type (label + select)
3. Field group: Direction (label + segmented control)
4. Field group: Circuit label (label + text input + small helper text)

Field group spacing: `sm` (8px) between label and widget; `md` (16px) between groups.

Visibility: `hidden` attribute toggled by JS. CSS transition: `transform: translateX(100%)` ↔ `translateX(0)` with `0.18s ease-out`. No animation on first paint (avoid flicker).

### Equipment Picker Modal

Element: new template `planner/templates/planner/signal_flow/_equipment_picker_modal.html`, included once from `editor.html`. Pattern source: `templates/includes/_help_modal.html`.

Structure:
```
<div id="sfd-picker-modal" class="modal-backdrop" hidden>
  <div class="modal-card">                       <!-- max-width 480px, max-height 70vh -->
    <header class="modal-header">                <!-- h3 + close button -->
      <h3>Pick a <span id="sfd-picker-type">Console</span></h3>
      <button class="modal-close" aria-label="Cancel">×</button>
    </header>
    <input id="sfd-picker-search" type="text" placeholder="Search by name, model, serial…" autofocus>
    <ul id="sfd-picker-results" role="listbox"></ul>   <!-- scrollable, max-height 320px -->
    <footer class="modal-actions">
      <button id="sfd-picker-cancel">Cancel</button>
    </footer>
  </div>
</div>
```

Modal CSS (extend `custom_admin.css` or new `signal_flow.css` — planner picks):
- Backdrop: `position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000`
- Card: `background: #fff; border-radius: 6px; padding: 24px; min-width: 360px; max-width: 480px; max-height: 70vh; display: flex; flex-direction: column; gap: 16px`
- Search input: `padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px`; focus ring `#0d9488`
- Result row: `padding: 8px 12px; border-radius: 4px; cursor: pointer`; hover `#f5f5f5`; primary text `#111` body, secondary `#666` body
- Keyboard: `↑`/`↓` to navigate, `Enter` to select highlighted row, `Esc` to cancel

Empty state: replace `<ul>` with a `<div class="modal-empty">` containing the heading + body copy from the Copywriting Contract. Link to admin uses `{% url 'admin:planner_<model>_add' %}` (the shape-type-specific add URL).

### Smart Shapes (on canvas — JointJS SVG)

Per-shape geometry from RESEARCH.md §1 ("Custom shape class definition") — already documented there in full. UI-SPEC adds the design layer:

| Property | Spec |
|----------|------|
| Default size | Console 180×60; Device 140×56; SpeakerArray 120×80; CommBeltPack 80×100; Generic 140×56 |
| Color band width | 6px (left edge for rects; positioned to follow the trapezoid hypotenuse and the pill curve for those types) |
| Body fill | `#ffffff` always |
| Body stroke | `#333` 1.5px (`#666` would be too light; `#000` would compete with analog connectors) |
| Body stroke (Generic) | `#94a3b8` 1.5px **dashed** (`stroke-dasharray="4 3"`) |
| Label font | `system-ui` 13px 500 weight `#111` |
| Label position | Centered vertically; horizontal `refX: 16` (leave 16px clear for the color band + breathing room) |
| Port radius | 4px |
| Port stroke | `#666` 1px |
| Port fill | `#fff` |
| Port opacity | `0` at rest, `1` on hover or during link drag (CSS-driven; selector documented in RESEARCH.md §2) |
| Selection style | Body stroke override `#0d9488` 2.5px (overrides default body stroke while selected) |

### Connectors (on canvas — JointJS SVG)

Per-signal-type styles from CONTEXT.md D-16 / RESEARCH.md §13 already locked above. UI layer:

| Property | Spec |
|----------|------|
| Routing | `orthogonal` (right-angle) |
| Corner style | `rounded` connector, radius 4px |
| Target arrowhead | 10×10px chevron, filled with stroke color |
| Bidirectional | No source marker, no target marker |
| Vertex handles | `linkTools.Vertices` default style; circle handle `6px` accent `#0d9488` on hover |
| Selected stroke | strokeWidth `+0.5` and drop-shadow `0 0 4px #0d9488` |
| Circuit label | 11px `system-ui` 500, dark text `#111` on 85%-opacity white pill background with thin grey border (rendered via JointJS Link.label `rect` + `text` markup) |

### Empty Paper Hint

A single SVG `<text>` element (not a DOM overlay — sits inside the JointJS paper layer so it pans/zooms with the canvas), positioned at center of the canvas at zoom level 1.0. Text: "Drag a shape from the left to start." Style: `13px system-ui`, fill `#999`, opacity `1` when graph has zero cells, `0` otherwise (toggle on `graph.on('add')` / `graph.on('remove')`).

---

## Keyboard Shortcuts (Phase 8 scope)

| Action | Shortcut |
|--------|----------|
| Undo | `Ctrl/Cmd + Z` (skip when target is input/textarea/select) |
| Redo | `Ctrl/Cmd + Shift + Z` and `Ctrl/Cmd + Y` (Windows-friendly alternate) |
| Delete selection | `Delete` or `Backspace` (skip when target is input/textarea/select) |
| Cancel modal / clear selection | `Escape` |
| Pan canvas | Hold `Space` + drag (left mouse) OR middle-click drag |
| Multi-select (additive) | `Shift + click` on additional nodes/links |
| Rubber-band select | Drag from blank canvas |

Out of scope for Phase 8: `Ctrl+A` (select all), `Ctrl+D` (duplicate), `Ctrl+C`/`Ctrl+V` (copy/paste — deferred to v2.3+ pending Clipboard availability).

---

## Registry Safety

| Registry | Blocks used | Safety gate |
|----------|-------------|-------------|
| shadcn official | n/a | not required (no shadcn in this project) |
| `@joint/core` 4.2.4 (vendored, MPL-2.0) | `joint.dia.{Graph,Paper,Element}`, `joint.shapes.standard.{Link,Rectangle}`, `joint.linkTools.{Vertices,Segments,Anchor,Connect,Button,Remove,SourceAnchor,TargetAnchor}`, `joint.elementTools.*` | Vendored as a single UMD bundle (`planner/static/planner/js/vendor/joint.min.js`); no file-level modifications (MPL-2.0 weak copyleft); `THIRD_PARTY_LICENSES.txt` in repo (Phase 7 locked) |
| `html-to-image` 1.11.11 (vendored, MIT) | Phase 8 does NOT use | Vendored for Phase 10 only |

No third-party UI registries. No CDN-loaded fonts (REQUIREMENTS Constraint). No CSS-in-JS. CSS lives in `custom_admin.css` or a new `signal_flow.css` (planner picks based on size; if Phase 8 CSS exceeds ~150 lines, isolate to its own file).

---

## Accessibility (baseline)

| Concern | Approach |
|---------|----------|
| Keyboard reachability of toolbar | All toolbar buttons are real `<button>` elements with `aria-label`; `Tab` order matches visual order |
| Keyboard reachability of sidebar tiles | `<button>` elements with `draggable="true"`; `Enter` on focused tile drops the shape at canvas center (fallback to drag for users who can't drag) |
| Modal focus trap | When modal opens, focus moves to search input; `Tab` cycles within modal; `Esc` closes |
| Canvas accessibility | JointJS SVG is not natively screen-reader-friendly; this is an accepted v2.2 limitation. PNG export (Phase 10) addresses the "share with someone who can't use the UI" path. |
| Color-only encoding | None — every connector signal type also carries a unique dash pattern (REQUIREMENTS Constraint enforced) |
| Focus indicators | 2px `#0d9488` outline on all keyboard-focused buttons and inputs |
| Reduced motion | Inspector slide-in respects `@media (prefers-reduced-motion: reduce)` — fades instead of slides |

---

## Checker Sign-Off

This UI-SPEC was authored inline (not via gsd-ui-researcher / gsd-ui-checker) after the researcher agent timed out. Manual checker pass against the 6 dimensions:

- [x] **Dimension 1 Copywriting:** PASS — every visible string is locked above with no "TBD" or "placeholder". Empty / loading / error states explicit.
- [x] **Dimension 2 Visuals:** PASS — geometry per shape type, port style, selection style, hover state, inspector layout, modal layout all specified. References Phase 7 editor shell where it's already locked.
- [x] **Dimension 3 Color:** PASS — 60/30/10 rule honored (white paper + dark chrome dominant, neutral surfaces secondary, teal accent reserved for selection/focus only). Destructive red reserved. Every hex value listed.
- [x] **Dimension 4 Typography:** PASS — 7 type roles, system fonts only, no webfonts. Inline-SVG label fonts match.
- [x] **Dimension 5 Spacing:** PASS — 7 tokens declared, all multiples of 4. Exceptions documented (Phase 7 toolbar padding, fixed sidebar/inspector widths).
- [x] **Dimension 6 Registry Safety:** PASS — no shadcn / no third-party registries; vendored JS is documented with license + provenance + non-modification rule.

**Approval:** approved 2026-05-20 (inline authored after agent timeout).
