# Phase 9: Autosave & Orphan Rendering — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 09-autosave-orphan-rendering
**Areas discussed:** Autosave triggers + debounce, Conflict detection + 409 banner UX, Keepalive on unload, _enrich_nodes() + ghost rendering

---

## Autosave Triggers + Debounce

### Which graph events trigger the autosave debounce timer?

| Option | Description | Selected |
|--------|-------------|----------|
| Structural + label only (Recommended) | Listen for: cell add, cell remove, link source/target change, node position change-end (pointerup), label/prop changes. Skip mid-drag spam. | ✓ |
| All graph change events, but debounced | Listen for broad 'change' event; trust debounce + dirty flag to absorb noise. | |
| Mutations only (no position) | add, remove, link change, prop change — ignore position entirely. Engineer who only moves nodes never triggers a save. | |

**User's choice:** Structural + label only (Recommended)
**Notes:** Aligns with PITFALLS.md §6 "autosave flooding" mitigation.

### What debounce floor (last edit → POST)?

| Option | Description | Selected |
|--------|-------------|----------|
| 1500 ms (Recommended) | PITFALLS.md §6 minimum; comfortably under 2.5 s spec ceiling. | ✓ |
| 2000 ms | More conservative; small chance Saved feels laggy on quick edits. | |
| 2500 ms (spec ceiling) | Max allowed by DGM-06; best server-load, least responsive. | |

**User's choice:** 1500 ms (Recommended)

### What happens to the Phase 8 manual Save button?

| Option | Description | Selected |
|--------|-------------|----------|
| Remove the button; keep the status span (Recommended) | Autosave makes it redundant. Status indicator stays. 'Save failed — retry' becomes clickable. | ✓ |
| Hide button; expose as Cmd/Ctrl+S shortcut | No visible button; power-users can force-flush. | |
| Keep the button as 'Save now' (force-flush) | Visible Save now button bypasses debounce. | |

**User's choice:** Remove the button; keep the status span (Recommended)

### How does the 'Saved' indicator reflect autosave activity?

| Option | Description | Selected |
|--------|-------------|----------|
| Three states only — Saved / Saving… / Failed — retry (Recommended) | Matches spec exactly. | ✓ |
| Add a 'Saved 12s ago' relative time | Same three states + relative-time updating every 10s. | |
| Add a 'Dirty (unsaved)' state | Four states with 'Editing…' between last edit and debounce fire. | |

**User's choice:** Three states only (Recommended)

---

## Conflict Detection + 409 Banner UX

### How does the client send the loaded version on save?

| Option | Description | Selected |
|--------|-------------|----------|
| If-Match request header (Recommended) | Standard HTTP semantics; doesn't pollute body. Matches Phase 8 comment. | ✓ |
| expected_version field in JSON body | Easier to test, mixes transport with payload. | |
| Both — body required, header optional | Defensive but more code paths. | |

**User's choice:** If-Match request header (Recommended)

### How does the server detect the conflict?

| Option | Description | Selected |
|--------|-------------|----------|
| atomic() + UPDATE ... WHERE version=? (Recommended) | PITFALLS.md §3 recipe; race-free; no row lock across request. | ✓ |
| select_for_update inside atomic() then compare | Lock row, re-read, compare, save. Explicit but holds lock for POST duration. | |

**User's choice:** atomic() + UPDATE ... WHERE version=? (Recommended)

### How does the 409 banner render and behave?

| Option | Description | Selected |
|--------|-------------|----------|
| Full-width red bar pinned below the toolbar (Recommended) | Above #sfd-paper. Non-dismissable. Single Reload button. Locks canvas (pointer-events:none). | ✓ |
| Top-of-page banner (above toolbar) | Pushes toolbar down; layout shift. | |
| Inline within #sfd-save-status | Most minimal; risks being overlooked. | |

**User's choice:** Full-width red bar pinned below the toolbar (Recommended)

### When the 409 fires, what about pending unsaved edits?

| Option | Description | Selected |
|--------|-------------|----------|
| Lock the canvas; only Reload escapes (Recommended) | Cancel in-flight debounce; set conflicted flag; ignore further edits. | ✓ |
| Allow edits; suppress autosave only | Engineer keeps editing; saves blocked; risks 'reverted my changes' confusion. | |

**User's choice:** Lock the canvas; only Reload escapes (Recommended)

---

## Keepalive on Unload

### Which unload event(s) trigger the keepalive flush?

| Option | Description | Selected |
|--------|-------------|----------|
| visibilitychange (hidden) AND pagehide (Recommended) | Covers tab-hide, close, navigation, iOS Safari quirks. NOT beforeunload (cancelled). | ✓ |
| pagehide only | Misses tab-switch case. | |
| visibilitychange only | Less reliable on iOS Safari + bfcache. | |

**User's choice:** visibilitychange + pagehide (Recommended)

### What does the keepalive flush actually send?

| Option | Description | Selected |
|--------|-------------|----------|
| Cancel debounce + fire immediate fetch(keepalive:true) (Recommended) | Only if dirty. Same payload (canvas_state + viewport + If-Match). NOT sendBeacon. | ✓ |
| Always fire, even if not dirty | Redundant POST; bumps version unnecessarily. | |
| Same as above, but skip if 409 banner is showing | Same as recommended with explicit guard. | |

**User's choice:** Cancel debounce + fire immediate fetch(keepalive:true) (Recommended)

### How does the keepalive interact with a save already in flight?

| Option | Description | Selected |
|--------|-------------|----------|
| Skip if a save is in flight (Recommended) | Lets in-flight finish; cheaper; avoids self-collision. | ✓ |
| Fire anyway | Two POSTs land; one wins. Slight self-collision risk. | |

**User's choice:** Skip if a save is in flight (Recommended)

---

## _enrich_nodes() + Ghost Rendering

### Where does `_enrich_nodes()` live and when does it run?

| Option | Description | Selected |
|--------|-------------|----------|
| Helper in planner/views.py above signal_flow_state; runs on GET only (Recommended) | Co-located with other signal_flow helpers. Save path leaves blob untouched. | ✓ |
| Same helper, runs on GET and on POST response | Returns enriched cells in autosave 200; adds latency to every save. | |
| New module planner/utils/signal_flow_enrich.py | Split off for growth; less consistent with views.py helpers. | |

**User's choice:** Helper in planner/views.py; runs on GET only (Recommended)

### How does the server flag an orphan in the response?

| Option | Description | Selected |
|--------|-------------|----------|
| Set cell.showstack.isOrphan = true + leave savedLabel (Recommended) | Live cells get savedLabel refreshed (SHP-06); missing get isOrphan flag. | ✓ |
| Set isOrphan + null out contentTypeId/objectId | Cleaner but loses option of future 'restore equipment' relink. | |
| Don't flag — client compares enriched vs stored | More client logic; less explicit. | |

**User's choice:** Set cell.showstack.isOrphan = true + leave savedLabel (Recommended)

### What's the orphan ghost visual?

| Option | Description | Selected |
|--------|-------------|----------|
| Dashed grey border + 50% opacity + faded fill (Recommended) | Matches SHP-07 'muted style, dashed border' wording. Connectors at 50% opacity. | ✓ |
| Same + small warning badge icon | Adds ⚠ glyph; more SVG work. | |
| Dashed border only, no opacity change | Less distinct; may fail UX intent. | |

**User's choice:** Dashed grey border + 50% opacity + faded fill (Recommended)

### Re-link affordance for orphans?

| Option | Description | Selected |
|--------|-------------|----------|
| Inspector reopens picker on orphan select (Recommended) | Right-side inspector with Re-link + Delete buttons. Reuses openEquipmentPicker — no new modal. | ✓ |
| Right-click context menu | New UI surface; more work. | |
| Delete-only (no relink) | Loses topology; doesn't satisfy SHP-07 wording. | |

**User's choice:** Inspector reopens picker on orphan select (Recommended)

---

## Claude's Discretion

- Exact CSS values for the 409 banner (font weight, padding, exact red hex)
- Retry policy on transient failures — single immediate retry on click of "Save failed — retry"; no auto-backoff
- Logging — reuse `_signal_flow_logger`; no new logger
- Telemetry / analytics on autosave success rate — out of scope
- Node-inspector layout when a node (vs connector) is selected — extend the existing right-side panel

## Deferred Ideas

### Phase 10
- LBL-01/02/03, EXP-01

### v2.3+
- Cmd/Ctrl+S force-flush shortcut
- Exponential backoff / auto-retry
- Restore-from-trash for deleted equipment (un-orphan flow)
- Real-time collaborative editing
- Conflict-merge UI
- Telemetry / analytics
- Offline-aggregated save-failed toasts

### Rejected During Discussion
- sendBeacon (64 KB cap; PITFALLS.md §6)
- beforeunload autosave (browser cancels the fetch)
- select_for_update conflict detection (holds row lock across POST)
- Server re-enriching the autosave POST response (doubles work; adds save latency)
- Nulling contentTypeId/objectId on orphans (loses future restore option)
