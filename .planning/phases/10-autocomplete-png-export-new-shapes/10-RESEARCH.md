# Phase 10: Autocomplete, PNG Export & New Shape Types — Research

**Researched:** 2026-05-21
**Domain:** Django 5 / JointJS 4.2.4 / html-to-image 1.11.11 / accessible-combobox UX
**Confidence:** HIGH — all critical questions answered from verified codebase sources

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Autocomplete triggers after 1 character typed, 200 ms debounce.
- **D-02:** Result format: `<label text> — <source tag>` (e.g., `FOH Lead — Device Input`).
- **D-03:** At most 8 results, alphabetical by label. No relevance ranking.
- **D-04:** Phase 10 wires autocomplete to connector circuit-label field only. Same endpoint reused by Phase 11 PORT-03 without re-implementation.
- **D-05:** `SystemProcessor` autocomplete source is research-determined. **Research conclusion: EXCLUDE — no canonical channel/label field exists on `SystemProcessor` itself.** See §D-05 Finding below.
- **D-06:** PNG filename: `<diagram-slug>-<YYYYMMDD>.png`, fallback `signal-flow-<YYYYMMDD>.png`.
- **D-07:** PNG resolution: `pixelRatio: 2`.
- **D-08:** Canvas-as-seen: captures `#sfd-paper` only, including orphan ghosts. No clean-mode.
- **D-09:** PNG background: white (`#ffffff`).
- **D-10:** One sidebar tile labeled "Processor". Picker combines all 3 models with type badges.
- **D-11:** Sidebar order: Console → Device → Processor → Amp → SpeakerArray → CommBeltPack → Generic.
- **D-12:** Processor + Amp shapes each get unique SVG glyph + color accent. No icon reuse across types.
- **D-13:** Export button in new right-side toolbar group (scaffold for future PDF/SVG in same group).
- **D-14:** No new inspector controls in Phase 10. Autocomplete wires into the existing `#sfd-circuit-label` input.

### Claude's Discretion

- Exact SVG glyph designs for Processor + Amp shape icons.
- HTML structure of autocomplete dropdown (popover positioning, ARIA roles, focus management).
- Internal naming: new label-autocomplete view (`signal_flow_label_autocomplete` or `?source=labels` extension). CONTEXT.md comment at views.py:7764 says "Phase 10 will add a SEPARATE `signal_flow_label_autocomplete` URL" — the existing comment already resolved this to a new sibling view.
- Whether PNG export uses `<a download>` click or `URL.createObjectURL + revoke`.

### Deferred Ideas (OUT OF SCOPE)

- "Clean mode" PNG export (skip orphans/chrome): defer to v2.4.
- PDF export: PDF-01 future list.
- SVG export: explicitly excluded project-level.
- Three sidebar tiles for Processor brands: defer to v2.4.
- Manual port positioning (PORT-MANUAL-01): already deferred at milestone level.
- Per-keystroke autocomplete on PORT-03: Phase 11 concern.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LBL-01 | Typing in connector's circuit-label field surfaces autocomplete from all project signal-name fields | Endpoint design in §Architecture Patterns; field inventory in §Standard Stack |
| LBL-02 | Autocomplete results scoped to `request.current_project`; cross-project signals never appear | IDOR pattern verified in `signal_flow_autocomplete` — same guard applies to label endpoint |
| LBL-03 | Engineer can override autocomplete with free-text; field accepts any string | Inspector `<input>` already accepts free text; only JS behavior changes |
| EXP-01 | One-click PNG export from toolbar; white background, full canvas, system fonts only | `html-to-image` 1.11.11 verified vendored; `#sfd-paper` scoping documented; `pixelRatio: 2` |
| SHP-10 | Processor shape from sidebar; picker combines SystemProcessor + P1Processor + GalaxyProcessor | Multi-model UNION pattern documented; IDOR paths per model documented |
| SHP-11 | Amp shape from sidebar; picker scoped to project Amp records | `Amp.project` FK confirmed; `AmpChannel.channel_name` confirmed as label field |
</phase_requirements>

---

## Summary

Phase 10 extends the already-shipped v2.2 Signal Flow Diagrammer (Phases 7–9) in four
directions: label autocomplete on connectors, one-click PNG export, and two new smart shape
types (Processor + Amp).

Every research question from CONTEXT.md has been answered by direct codebase inspection.
No external documentation lookups were required — the stack is fully locked and the vendor
libraries are already installed. All patterns (shape registration, IDOR guard, autosave
allowlist, `_enrich_nodes`) are verified at specific line numbers and are ready for
mechanical extension.

The single highest-risk finding is the autosave IDOR allowlist at `planner/views.py:7704`.
The literal `('Console', 'Device', 'CommBeltPack')` is confirmed at that line; if the planner
forgets to extend it to include `Amp`, `SystemProcessor`, `P1Processor`, and `GalaxyProcessor`,
every autosave for the new shape types will return HTTP 422 — silently failing saves with no
error visible to the user (the 422 is handled gracefully by the client but causes data loss).

**Primary recommendation:** Start with the two server-side extensions (`signal_flow_autosave`
allowlist + `_enrich_nodes` model list + new `signal_flow_label_autocomplete` view +
`signal_flow_autocomplete` Processor/Amp entries) in Wave 1, then move to JS/HTML in Wave 2.
The server-side work has zero JS interdependencies and is immediately testable.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Label autocomplete suggestions | API/Backend (Django view) | Browser JS (debounce + render) | Project-scoped queryset must run server-side for IDOR safety; client handles debounce + dropdown UI |
| PNG export | Browser JS (html-to-image) | — | html-to-image captures the live DOM/SVG canvas; no server-side rasterization needed |
| Processor picker (multi-model) | API/Backend (Django view) | Browser JS (modal + badge render) | UNION across 3 models is a queryset concern; JS renders the badge from the `model_type` field returned by the view |
| Amp picker | API/Backend (Django view) | Browser JS (modal) | Same pattern as existing console/device pickers |
| IDOR validation for new shapes | API/Backend (Django view) | — | `signal_flow_autosave` allowlist is the enforcement point |
| Orphan enrichment for new shapes | API/Backend (Django view) | Browser JS (applyOrphanState) | `_enrich_nodes` runs on GET; JS reads `isOrphan` flag to apply CSS |
| Sidebar tile + shape class | Browser JS + HTML | — | `joint.shapes.showstack` namespace + `editor.html` sidebar HTML |

---

## D-05 Finding: SystemProcessor Autocomplete Source

**VERIFIED by codebase inspection of `planner/models.py:1898–1933`.**

`SystemProcessor` has the following fields:
- `name` (CharField, max 200) — device name/identifier, e.g., "P1 Stage Left"
- `device_type` (CharField choices: 'P1' or 'GALAXY')
- `location` (FK to Location)
- `ip_address` (GenericIPAddressField, optional)
- `notes` (TextField, optional)
- `created_at`

There is NO `*Input` / `*Output` companion model on `SystemProcessor` itself. The channel-level
labels live on the child models: `P1Input.label`, `P1Output.label` (via `P1Processor`),
`GalaxyInput.label`, `GalaxyOutput.label` (via `GalaxyProcessor`).

`P1Processor` and `GalaxyProcessor` each link to `SystemProcessor` via `OneToOneField`
(`system_processor`, `related_name='p1_config'` and `'galaxy_config'` respectively).

**Conclusion: EXCLUDE `SystemProcessor` from the autocomplete label source list.**

Reasoning:
1. The only human-readable field on `SystemProcessor` is `name` — a device identifier
   (e.g., "P1 Stage Left"), not a channel signal name. Including it would pollute the
   signal-name autocomplete with device identifiers.
2. The actual channel signal-name data lives on `P1Input.label`, `P1Output.label`,
   `GalaxyInput.label`, `GalaxyOutput.label`. These are accessed through `P1Processor`
   and `GalaxyProcessor`, which are scoped via `system_processor__project`.
3. The `signal_flow_label_autocomplete` view should query `P1Input` and `P1Output`
   (via `p1_processor__system_processor__project=project`) and `GalaxyInput` /
   `GalaxyOutput` (via `galaxy_processor__system_processor__project=project`).

**Code comment template (for the label-autocomplete view):**
```python
# SystemProcessor is excluded from the label autocomplete source list (D-05).
# SystemProcessor.name is a device identifier ("P1 Stage Left"), not a signal-name.
# Signal-name data lives on P1Input.label / P1Output.label (accessed via P1Processor)
# and GalaxyInput.label / GalaxyOutput.label (accessed via GalaxyProcessor).
# See planner/models.py:1898 (SystemProcessor), 2028 (P1Input), 2067 (P1Output),
# 2128 (GalaxyInput), 2163 (GalaxyOutput).
```

---

## Amp Label Sources Finding

**VERIFIED by codebase inspection of `planner/models.py:1841–1876`.**

`AmpChannel` has these fields:
- `amp` (FK to Amp)
- `channel_number` (IntegerField)
- `channel_name` (CharField, max 100, blank=True, default="") — **this is the canonical label field**
- `avb_stream` (CharField, choices, optional)
- `aes_input` (CharField, optional)
- `analog_input` (CharField, optional)

**Conclusion:** `AmpChannel.channel_name` is the canonical engineer-facing label for autocomplete.
`Amp.name` is a device identifier ("LA12X-1", "Stage Left 1") — include it only if
the planner wants device-level suggestions. `channel_name` is the per-channel signal assignment.

**IDOR path:** `AmpChannel.amp.project` — so filter via `amp__project=current_project`.

Both are worth including: `AmpChannel.channel_name` (channel signal labels) and
`Amp.name` (equipment name suggestions). Source tags would be "Amp Channel" vs. "Amp".

---

## Standard Stack

### Core (no new dependencies — all already vendored or installed)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| `@joint/core` | 4.2.4 | Canvas shapes, graph, paper | Vendored — `joint.min.js` [VERIFIED: ls vendor/] |
| `html-to-image` | 1.11.11 | PNG rasterization of DOM/SVG | Vendored — `html-to-image.min.js` [VERIFIED: ls vendor/] |
| Django | 5.x | Backend, queryset, views | In use [VERIFIED: CLAUDE.md] |
| `django.contrib.contenttypes` | built-in | GFK resolution in `_enrich_nodes` + autosave IDOR | Already imported in views.py [VERIFIED: views.py:7678] |

### Zero New Dependencies

The constraint is locked. Phase 10 does not add any Python packages or JS libraries.
The autocomplete dropdown UI is implemented in vanilla JS. The PNG export uses the
already-vendored `html-to-image.min.js`.

---

## Architecture Patterns

### System Architecture Diagram

```
Engineer types in #sfd-circuit-label
         |
         | (keyup, 1-char threshold, 200ms debounce)
         v
signal_flow_label_autocomplete (Django GET)
         |-- IDOR guard: request.current_project
         |-- Queries: DeviceInput, DeviceOutput, ConsoleInput, ConsoleAuxOutput,
         |            P1Input, P1Output, GalaxyInput, GalaxyOutput,
         |            AmpChannel (channel_name), Amp (name)
         |-- Returns: [{label, source_tag}] max 8, alphabetical
         v
Autocomplete dropdown renders below #sfd-circuit-label
         |
         | (row click or Enter)
         v
Inspector sets input.value -> scheduleAutosave()
         v
signal_flow_autosave POST (existing view)
         |-- IDOR allowlist: Console, Device, CommBeltPack, Amp,
         |                   SystemProcessor, P1Processor, GalaxyProcessor (EXTENDED)
         v
DB: canvas_state JSONField updated (version+1)

[Sidebar drop]
Processor tile drag -> canvas drop
         |
         v
joint.shapes.showstack.Processor (new shape class)
         |
         v
openEquipmentPicker('Processor', node)
         |
         v
signal_flow_autocomplete?type=processor (extended MODEL_MAP)
         |-- UNION: SystemProcessor.objects.filter(project=p) annotated with model_type
         |           [P1 / GALAXY badge from device_type field]
         v
User picks -> assignPickerResult(rec) -> scheduleAutosave()

[Export]
#sfd-export-png button click
         |
         v
htmlToImage.toPng(paperEl, {pixelRatio:2, backgroundColor:'#ffffff'})
         |
         v
<a download="..."> click -> browser saves PNG
```

### Recommended File Changes

```
planner/
├── views.py                          # signal_flow_label_autocomplete (new)
│                                     # signal_flow_autocomplete MODEL_MAP (+processor, +amp)
│                                     # signal_flow_autosave allowlist extended
│                                     # _enrich_nodes model_name set extended
│                                     # signal_flow_export_png stub (already exists — stays stub)
├── urls.py                           # +path for signal_flow_label_autocomplete
├── static/planner/js/
│   └── signal_flow_editor.js         # joint.shapes.showstack.Processor + .Amp
│                                     # PICKER_TYPE_CONFIG += {Processor, Amp}
│                                     # #sfd-circuit-label -> autocomplete widget
│                                     # #sfd-export-png button handler
├── static/planner/css/
│   └── signal_flow.css               # Section 12 (autocomplete dropdown)
│                                     # Section 13 (export button group)
└── templates/planner/signal_flow/
    └── editor.html                   # 2 new sidebar tiles (Processor, Amp — after Device)
                                      # export button group in toolbar
```

CSS section 11 (`signal_flow.css`) is the last existing section. Sections 12 and 13 are
appended per the established "append-at-end" convention. [VERIFIED: signal_flow.css:575]

---

## Integration Points (all verified against current code)

### 1. `signal_flow_autosave` IDOR Allowlist — Line 7704

**Current literal (VERIFIED: views.py:7704):**
```python
elif model_name in ('Console', 'Device', 'CommBeltPack'):
```

**Required extension for Phase 10:**
```python
elif model_name in ('Console', 'Device', 'CommBeltPack',
                    'Amp', 'SystemProcessor', 'P1Processor', 'GalaxyProcessor'):
```

**Why these four:**
- `Amp` — SHP-11 GFK target; has `project` FK directly.
- `SystemProcessor` — SHP-10 GFK target (the picker selects a `SystemProcessor` record
  regardless of whether it has a P1 or Galaxy child config); has `project` FK directly.
- `P1Processor` — NOT a GFK target (no `project` FK — only `system_processor` OneToOneField).
  **EXCLUDE from allowlist.** The picker targets `SystemProcessor`, not `P1Processor`.
- `GalaxyProcessor` — Same as P1Processor. **EXCLUDE from allowlist.**

**Revised extension (corrected):**
```python
elif model_name in ('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor'):
```

`P1Processor` and `GalaxyProcessor` are child-config models. The canvas cell's GFK
points to `SystemProcessor` (which has `project` FK). The child configs are never
stored as canvas GFK targets. The CONTEXT.md note saying to include all 4 is an
over-count; the research conclusion from model inspection is: add `Amp` and
`SystemProcessor` only.

**This is the most likely silent bug in Phase 10.** Confirm with planner before executing.

### 2. `_enrich_nodes` Model Name Set — Line 7573

**Current literal (VERIFIED: views.py:7573):**
```python
elif model_name in ('Console', 'Device', 'CommBeltPack'):
    qs = Model.objects.filter(id__in=obj_ids, project=project)
```

**Required extension:**
```python
elif model_name in ('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor'):
    qs = Model.objects.filter(id__in=obj_ids, project=project)
```

Both `Amp` and `SystemProcessor` have a direct `project` FK. The `name` field exists
on both (`Amp.name` [VERIFIED: models.py:1666], `SystemProcessor.name` [VERIFIED:
models.py:1907]). The `values_list('id', 'name')` call at line 7577 works unchanged.

### 3. `signal_flow_autocomplete` Equipment Picker — Lines 7778–7807

**Current MODEL_MAP keys:** `console`, `device`, `speakerarray`, `commbeltpack`

**Required additions:**

```python
'processor': (
    SystemProcessor,
    {'project': current_project},
    ['name'],
    lambda sp: sp.name,
    lambda sp: sp.get_device_type_display(),  # 'L\'Acoustics P1' or 'Meyer GALAXY'
),
'amp': (
    Amp,
    {'project': current_project},
    ['name'],
    lambda a: a.name,
    lambda a: str(a.amp_model) if a.amp_model else '—',
),
```

**Important:** The Processor picker targets `SystemProcessor`, not `P1Processor`/
`GalaxyProcessor`. The `device_type` field on `SystemProcessor` gives the badge text
(`sp.get_device_type_display()`). This resolves D-10 cleanly: one endpoint, one model,
model-type badge from `device_type`.

**Note on `select_related`:** Add `select_related('amp_model')` to the Amp queryset
to avoid N+1 for `str(a.amp_model)` across the result list. Pattern already present
in the view's structure — add `qs = qs.select_related('amp_model')` before the
search filter is applied.

### 4. `assignPickerResult` — Line 492

**VERIFIED: signal_flow_editor.js:492–511**

`assignPickerResult` is shape-type agnostic. It stores:
- `rec.contentTypeId` → `showstack/contentTypeId`
- `rec.id` → `showstack/objectId`
- `rec.name` → `showstack/savedLabel` and `attrs/label/text`

No changes required for Processor or Amp. The GFK mechanism works for any model.
The `PICKER_TYPE_CONFIG` table (lines 309–314) is the only JS change needed:

```javascript
Processor: { backend: 'processor', label: 'Processor', admin: '/admin/planner/systemprocessor/' },
Amp:       { backend: 'amp',       label: 'Amp',        admin: '/admin/planner/amp/' },
```

### 5. `signal_flow_export_png` Stub — Line 7860

**VERIFIED: views.py:7860**

The view exists and returns HTTP 501. The URL is already registered in `urls.py`
at line 343: `path('signal-flow/<int:diagram_id>/export.png/', ...)`.

The `data-export-png-url` attribute is already present on `#sfd-container` in
`editor.html:29`. The JS comment at `signal_flow_editor.js:30` explicitly defers
reading it to Phase 10.

**Phase 10 work:** The export is client-side only. The stub view can stay as-is or
be removed if it causes confusion. The JS reads `container.dataset.exportPngUrl`
(read the attribute in Phase 10 — line 30 says "do not read here" meaning Phase 8
didn't read it). `html-to-image` runs entirely in the browser; no round-trip to Django.

---

## Signal-Name Label Sources — Complete Field Inventory

| Model | Field | IDOR path | Source tag (D-02) |
|-------|-------|-----------|-------------------|
| `DeviceInput` | `signal_name` | `device__project=project` | `Device Input` |
| `DeviceOutput` | `signal_name` | `device__project=project` | `Device Output` |
| `ConsoleInput` | `source` | `console__project=project` | `Console Input` |
| `ConsoleAuxOutput` | `name` | `console__project=project` | `Console Aux Out` |
| `AmpChannel` | `channel_name` | `amp__project=project` | `Amp Channel` |
| `P1Input` | `label` | `p1_processor__system_processor__project=project` | `P1 Input` |
| `P1Output` | `label` | `p1_processor__system_processor__project=project` | `P1 Output` |
| `GalaxyInput` | `label` | `galaxy_processor__system_processor__project=project` | `Galaxy Input` |
| `GalaxyOutput` | `label` | `galaxy_processor__system_processor__project=project` | `Galaxy Output` |

**VERIFIED fields:**
- `DeviceInput.signal_name`: models.py:1519 [VERIFIED]
- `DeviceOutput.signal_name`: models.py:1552 [VERIFIED]
- `ConsoleInput.source`: models.py:898 [VERIFIED] — note: the field appears twice in source (line 898 + 899); Django uses the last definition; value is `models.CharField(max_length=100, blank=True, null=True)`
- `ConsoleAuxOutput.name`: models.py:978 [VERIFIED]
- `AmpChannel.channel_name`: models.py:1845 [VERIFIED]
- `P1Input.label`: models.py:2039 [VERIFIED]
- `P1Output.label`: models.py:2080 [VERIFIED]
- `GalaxyInput.label`: models.py:2143 [VERIFIED]
- `GalaxyOutput.label`: models.py:2178 [VERIFIED]

**Note on blanks:** Most label fields allow blank/null. The `signal_flow_label_autocomplete`
view MUST filter out empty strings: `.exclude(signal_name='').exclude(signal_name__isnull=True)`
(exact filter varies per field name). Otherwise empty-string suggestions fill the dropdown.

**Query pattern for `signal_flow_label_autocomplete`:**

```python
from itertools import chain

def _label_suggestions(project, q):
    """Return up to 8 label suggestions from all signal-name fields, alphabetical."""
    results = []

    SOURCES = [
        (DeviceInput,      'signal_name', 'device__project',                          'Device Input'),
        (DeviceOutput,     'signal_name', 'device__project',                          'Device Output'),
        (ConsoleInput,     'source',      'console__project',                         'Console Input'),
        (ConsoleAuxOutput, 'name',        'console__project',                         'Console Aux Out'),
        (AmpChannel,       'channel_name','amp__project',                             'Amp Channel'),
        (P1Input,          'label',       'p1_processor__system_processor__project',   'P1 Input'),
        (P1Output,         'label',       'p1_processor__system_processor__project',   'P1 Output'),
        (GalaxyInput,      'label',       'galaxy_processor__system_processor__project', 'Galaxy Input'),
        (GalaxyOutput,     'label',       'galaxy_processor__system_processor__project', 'Galaxy Output'),
    ]

    seen = set()
    for Model, field, scope_kwarg, tag in SOURCES:
        kw = {scope_kwarg: project, f'{field}__icontains': q} if q else {scope_kwarg: project}
        exclude_kw = {f'{field}': ''} if field != 'signal_name' else {f'{field}__exact': ''}
        qs = (Model.objects
              .filter(**kw)
              .exclude(**exclude_kw)
              .exclude(**{f'{field}__isnull': True})
              .values_list(field, flat=True)
              .distinct()[:50])
        for val in qs:
            key = (val, tag)
            if key not in seen:
                seen.add(key)
                results.append({'label': val, 'source': tag})

    results.sort(key=lambda r: r['label'].lower())
    return results[:8]
```

This is provided as design guidance. The planner may adjust. The key constraint is that
all 9 sources are queried in a single view call (not 9 separate AJAX requests).

---

## PNG Export — html-to-image Integration

### API Surface (VERIFIED: html-to-image.min.js 1.11.11 vendored)

`html-to-image` exposes a global `htmlToImage` object when loaded as a UMD bundle.
Key function for Phase 10: `htmlToImage.toPng(node, options)` returns a `Promise<string>`
(data URL).

**Required options:**
```javascript
htmlToImage.toPng(paperEl, {
    pixelRatio: 2,                    // D-07
    backgroundColor: '#ffffff',       // D-09
    width: paper.options.width,       // full JointJS canvas, not just viewport
    height: paper.options.height,
})
```

**Key pitfalls (ASSUMED for html-to-image 1.11.11 — not re-verified in this session):**

1. **`#sfd-paper` vs viewport:** `paper.el` (`#sfd-paper`) is the full 4000×3000 canvas
   defined in `new joint.dia.Paper`. The CSS `overflow: hidden` on `#sfd-canvas-container`
   clips the visible viewport — but `html-to-image` captures the full DOM element dimensions,
   not the CSS-clipped region. The engineer sees a subset; the PNG captures the full canvas.
   This is correct per D-08 ("full canvas"). If the engineer wants only the visible viewport,
   that is D-08's explicitly deferred "clean mode". No action needed.

2. **SVG filter/drop-shadow rendering:** `html-to-image` serializes SVG to a `<foreignObject>`
   then draws onto a canvas. SVG `filter` elements (e.g., `drop-shadow`) may render
   inconsistently across browsers. Phase 10 shapes should NOT rely on SVG filters for visual
   correctness — use SVG `stroke` + `fill` only (as the existing 5 shapes do). The orphan
   ghost dashed stroke (`stroke-dasharray`) is CSS-applied via JointJS attribute, which
   does render correctly via html-to-image. [ASSUMED — not re-verified; LOW risk given
   the current shapes have no filter effects]

3. **Cross-origin font taint:** Zero risk. All shapes use `FONT_STACK = 'system-ui, -apple-system,
   "Segoe UI", Roboto, sans-serif'` (signal_flow_editor.js:88) — no web fonts, no cross-origin
   resource requests. This was locked in v2.2 for exactly this reason. [VERIFIED: STATE.md,
   editor.js:88]

4. **Performance at pixelRatio: 2 for a 4000×3000 canvas:** The raw canvas will be
   8000×6000 px (144 MB uncompressed RGBA). PNG compression typically reduces this 10-20x
   for a diagram with mostly white space. Generation time is 1–3 seconds on a modern laptop.
   This is acceptable for an on-demand export. A "generating..." toast is advisable.
   [ASSUMED — no benchmark; LOW risk for typical diagram sizes with < 20 shapes]

5. **Background transparency:** JointJS paper's SVG background is set to `#ffffff` at
   construction (`background: { color: '#ffffff' }` at editor.js:243) but this sets a
   JointJS-managed `<rect>` element behind the cells, not a CSS background. The
   `backgroundColor: '#ffffff'` option to `htmlToImage.toPng` ensures the PNG gets a white
   background even if the SVG rect renders as transparent in some browsers. Both guards are
   needed. [ASSUMED — based on common html-to-image usage patterns]

### Export Button Integration Pattern

The existing toolbar already has a `<span class="sfd-toolbar-divider"></span>` pattern
between button groups. The export group goes after the existing groups:

```html
<span class="sfd-toolbar-divider"></span>
<div class="sfd-btn-group" data-group="export" id="sfd-export-group">
  <button type="button" id="sfd-export-png" aria-label="Export PNG">&#x1F5BC;</button>
</div>
```

The JS reads `container.dataset.exportPngUrl` (the URL is already in the data attribute
at `editor.html:29`). For the download trigger, `<a download>` with a data URL is
simpler than `createObjectURL` for small-to-medium files and has no cleanup requirement:

```javascript
htmlToImage.toPng(paperEl, { pixelRatio: 2, backgroundColor: '#ffffff',
                              width: paper.options.width, height: paper.options.height })
    .then(function (dataUrl) {
        var slug = (diagramName || 'signal-flow')
            .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
        var date = new Date().toISOString().slice(0,10).replace(/-/g,'');
        var a = document.createElement('a');
        a.download = (slug || 'signal-flow') + '-' + date + '.png';
        a.href = dataUrl;
        a.click();
    })
    .catch(function () { showToast('Export failed.', 'error'); });
```

`diagramName` is available from `container.dataset.diagramName` (already in template at
`editor.html:26`). The slug logic in Python (`slugify()`) should be mirrored in JS for
filename consistency. The JS implementation above is close enough; exact parity is not
required since the filename is cosmetic.

---

## New Shape Classes — Pattern Reference

**Existing pattern (VERIFIED: signal_flow_editor.js:125–223):**

All 5 existing shapes follow identical structure:
1. `joint.dia.Element.extend({ markup: [...], defaults: joint.util.deepSupplement({...}, joint.dia.Element.prototype.defaults) })`
2. `type` field in defaults: `'showstack.Console'`, `'showstack.Device'`, etc.
3. `size`: fixed dimensions.
4. `attrs`: `body` (rect/polygon), optional `band` (left color strip), `label` (text).
5. `ports: portsForRect(w, h)` — 4 mid-edge ports.

**Processor shape design (implementation discretion per D-12):**

```javascript
// ---- Processor (160×60, amber #b45309 left band) ----
joint.shapes.showstack.Processor = joint.dia.Element.extend({
    markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'rect', selector: 'band' },
        { tagName: 'text', selector: 'label' },
    ],
    defaults: joint.util.deepSupplement({
        type: 'showstack.Processor',
        size: { width: 160, height: 60 },
        attrs: {
            body:  { refWidth: '100%', refHeight: '100%', fill: '#ffffff', stroke: '#333', 'stroke-width': 1.5 },
            band:  { x: 0, y: 0, width: 6, refHeight: '100%', fill: '#b45309' },  // amber — unique per D-12
            label: { refX: 16, refY: '50%', textAnchor: 'start', textVerticalAnchor: 'middle',
                     fontSize: 13, fontFamily: FONT_STACK, fill: '#111', text: 'Processor' },
        },
        ports: portsForRect(160, 60),
    }, joint.dia.Element.prototype.defaults),
});

// ---- Amp (140×60, green #15803d left band) ----
joint.shapes.showstack.Amp = joint.dia.Element.extend({
    markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'rect', selector: 'band' },
        { tagName: 'text', selector: 'label' },
    ],
    defaults: joint.util.deepSupplement({
        type: 'showstack.Amp',
        size: { width: 140, height: 60 },
        attrs: {
            body:  { refWidth: '100%', refHeight: '100%', fill: '#ffffff', stroke: '#333', 'stroke-width': 1.5 },
            band:  { x: 0, y: 0, width: 6, refHeight: '100%', fill: '#15803d' },  // green — unique per D-12
            label: { refX: 16, refY: '50%', textAnchor: 'start', textVerticalAnchor: 'middle',
                     fontSize: 13, fontFamily: FONT_STACK, fill: '#111', text: 'Amp' },
        },
        ports: portsForRect(140, 60),
    }, joint.dia.Element.prototype.defaults),
});
```

**Color accent audit (existing shapes, verified):**

| Shape | Band color |
|-------|-----------|
| Console | `#0d9488` (teal) |
| Device | `#475569` (slate) |
| SpeakerArray | `#ea580c` (orange) |
| CommBeltPack | `#7c3aed` (purple) |
| Generic | none (dashed grey border only) |
| **Processor** (proposed) | `#b45309` (amber) — unique |
| **Amp** (proposed) | `#15803d` (green) — unique |

**Sidebar tile registration (editor.html):**

The 5 existing tiles are `data-shape-type="Console"`, `"Device"`, `"SpeakerArray"`,
`"CommBeltPack"`, `"Generic"`. Per D-11, the order after Phase 10 is:

```
Console → Device → Processor → Amp → SpeakerArray → CommBeltPack → Generic
```

Two new tiles inserted between Device and SpeakerArray. The drag-drop guard at
`signal_flow_editor.js:344` checks `joint.shapes.showstack[shapeType]` — the new
shape classes must be registered before the guard runs (they are, since shape
registration is at the top of the IIFE, before any event listeners).

**`PICKER_TYPE_CONFIG` extension:**

```javascript
var PICKER_TYPE_CONFIG = {
    Console:      { backend: 'console',      label: 'Console',       admin: '/admin/planner/console/' },
    Device:       { backend: 'device',       label: 'Device',        admin: '/admin/planner/device/' },
    Processor:    { backend: 'processor',    label: 'Processor',     admin: '/admin/planner/systemprocessor/' },
    Amp:          { backend: 'amp',          label: 'Amp',           admin: '/admin/planner/amp/' },
    SpeakerArray: { backend: 'speakerarray', label: 'Speaker Array', admin: '/admin/planner/speakerarray/' },
    CommBeltPack: { backend: 'commbeltpack', label: 'Beltpack',      admin: '/admin/planner/commbeltpack/' },
};
```

Generic is not in `PICKER_TYPE_CONFIG` (no picker for Generic — line 359 in editor.js).

---

## Autocomplete Dropdown — UX Pattern

### Accessible Combobox (Zero New Dependencies)

The dropdown is attached to the existing `#sfd-circuit-label` `<input>`. The
pattern follows the ARIA Authoring Practices combobox pattern [ASSUMED — standard
ARIA pattern, not re-verified against a specific spec URL in this session]:

**HTML structure (appended to `editor.html` inside `#sfd-inspector`):**

```html
<div class="sfd-autocomplete-wrapper">
  <input type="text" id="sfd-circuit-label" placeholder="e.g. CKT-01" maxlength="100"
         role="combobox" aria-autocomplete="list" aria-expanded="false"
         aria-haspopup="listbox" aria-controls="sfd-label-suggestions">
  <ul id="sfd-label-suggestions" role="listbox" class="sfd-autocomplete-list" hidden></ul>
</div>
```

Note: The existing `<input id="sfd-circuit-label">` at `editor.html:122` can be
enhanced with these ARIA attributes in the Phase 10 template edit.

**JS lifecycle:**
1. `input` event → debounce 200ms → fetch `signal_flow_label_autocomplete?q=<val>`.
2. Render `<li role="option">` rows. Set `aria-expanded="true"`.
3. Arrow keys: `ArrowDown`/`ArrowUp` cycle `aria-selected="true"` and update
   `aria-activedescendant` on the input.
4. `Enter` → select highlighted row → close dropdown.
5. `Escape` → close dropdown, leave input value unchanged.
6. Mouse hover → set `aria-selected="true"` on hovered row.
7. Mouse click → select row.
8. `blur` event → close dropdown with 150ms delay (allows click to register first).
9. On selection: set `input.value = chosen_label`, dispatch `input` event to trigger
   the existing inspector listener (`scheduleAutosave` via D-14 pattern).

**Positioning:** `position: absolute` below the input, `width: 100%` of the wrapper.
Z-index must exceed inspector z-index. Section 12 in signal_flow.css handles this.

**D-14 compliance (Phase 9 inspector field listener convention):** The autocomplete
widget fires a synthetic `input` event on selection so the existing `#sfd-circuit-label`
listener (which calls `scheduleAutosave()` after setting the label on the cell) triggers
without modification. [VERIFIED: the inspector listener is wired to the input event per
Phase 9 D-14 convention — this is the established pattern]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PNG rasterization of SVG+DOM | Custom canvas rendering | `html-to-image` 1.11.11 (already vendored) | Handles SVG serialization, foreignObject, cross-browser canvas; hand-roll misses dozens of edge cases |
| Debounce in autocomplete | `setTimeout` reimplementation per-feature | Single `debounce(fn, ms)` utility (< 5 lines) already present in pattern form at picker search (line 514) — reuse same pattern | Consistent delay behavior |
| IDOR validation | `hasattr(model, 'project')` check | Explicit allowlist (current pattern at views.py:7704) | `hasattr` silently passes models with non-FK `project` attrs |
| Multi-model queryset UNION | Raw SQL UNION | `chain()` of per-model value querysets | Django ORM `.union()` returns typed querysets; `itertools.chain` of `.values()` querysets is simpler for heterogeneous models |

---

## Common Pitfalls

### Pitfall 1: Forgetting the Autosave IDOR Allowlist Extension (CRITICAL)

**What goes wrong:** Every autosave POST for a Processor or Amp cell returns HTTP 422
(`'Type Amp has no project scope'`). The client's `flushAutosave` function logs an error
and stops saving. The diagram is not corrupted (the old version persists) but new changes
are silently not saved after the first 422.

**Why it happens:** `signal_flow_autosave` at line 7704 has an explicit allowlist. The
fallthrough `else` block returns 422 for any model not in the list.

**How to avoid:** Wave 1 task for `signal_flow_autosave` must include extending the allowlist.
The test suite (`test_signal_flow_phase10.py`) should include a test that POSTs a canvas
state containing an `Amp` cell and verifies HTTP 200.

**Warning signs:** DevTools Network tab shows 422 for autosave after dropping a Processor
or Amp shape.

### Pitfall 2: Wrong GFK Target for Processor Shape

**What goes wrong:** If the canvas stores `P1Processor.pk` as the GFK `objectId` instead
of `SystemProcessor.pk`, then `_enrich_nodes` cannot find the record (P1Processor is not
in the enrichment model list) and the cell renders as orphan immediately after assignment.

**Why it happens:** `P1Processor` is the child config model; `SystemProcessor` is the
device-level record. The equipment picker calls `signal_flow_autocomplete?type=processor`,
which queries `SystemProcessor` and returns `SystemProcessor.pk` as `id`. This is correct.
The mistake would be accidentally querying `P1Processor` instead.

**How to avoid:** The `MODEL_MAP` entry for `'processor'` must use `SystemProcessor` (not
`P1Processor` or `GalaxyProcessor`).

### Pitfall 3: `_enrich_nodes` Not Extended

**What goes wrong:** Processor and Amp cells load as permanent orphans (dashed ghost) even
when the equipment record exists. The engineer sees the shape greyed-out immediately after
creating it.

**Why it happens:** `_enrich_nodes` at line 7573 has an allowlist: `('Console', 'Device',
'CommBeltPack')`. Unknown models fall through to `continue` (orphan by default).

**How to avoid:** Wave 1 task for `_enrich_nodes` must add `'Amp'` and `'SystemProcessor'`.

### Pitfall 4: ConsoleInput.source Field Duplication

**What goes wrong:** `ConsoleInput` has `source = models.CharField(...)` defined twice
(lines 898 and 899). Django uses the last definition. This is benign for querying
(`signal_name='source'` in the ORM query) but the planner should be aware that the
field IS present as `CharField(max_length=100, blank=True, null=True)`.

**How to avoid:** Filter empty values explicitly: `.exclude(source='').exclude(source__isnull=True)`.

### Pitfall 5: AmpChannel.channel_name is Blank by Default

**What goes wrong:** The autocomplete includes empty-string `channel_name` values from
`AmpChannel` records that were created by `Amp.setup_channels()` with `channel_name=""`.
These appear as blank suggestions.

**Why it happens:** `AmpChannel.objects.create(..., channel_name="")` is the default in
`setup_channels()` at models.py:1832.

**How to avoid:** The label query must `.exclude(channel_name='')`.

### Pitfall 6: Processor Sidebar Tile Order in HTML vs D-11

**What goes wrong:** HTML tile order drives visual sidebar order. If Processor and Amp
tiles are appended after the existing 5 tiles instead of inserted between Device and
SpeakerArray, the order will be `Console → Device → SpeakerArray → CommBeltPack →
Generic → Processor → Amp` instead of the D-11-specified order.

**How to avoid:** Insert the two new tiles between the Device tile and the SpeakerArray
tile in `editor.html` (before the SpeakerArray `<button>`, after the Device `<button>`).

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 10 |
|-----------|-------------------|
| Always register models on `showstack_admin_site`, NOT `admin.site` | Not applicable — no new models in Phase 10 |
| Update `admin_ordering.py` for any new admin-registered model | Not applicable — no new models |
| Never use `element.style.property = value` in admin DOM | Export button + autocomplete dropdown HTML lives in admin template; use `setProperty('prop', val, 'important')` for any JS style writes |
| `CurrentProjectMiddleware` session-based scoping — no URL project IDs | `signal_flow_label_autocomplete` must use `request.current_project` for all queries |
| Railway deploy uses `railway.json` startCommand, not Procfile | Not applicable — no deploy config changes in Phase 10 |
| Ask before destructive Railway Postgres operations | Not applicable — no migrations in Phase 10 |
| Ask before touching factory pouchdb files | Not applicable — Phase 10 is Signal Flow only |
| Zero new Python dependencies | Confirmed — no new packages required |

---

## State of the Art

| Old Approach | Current Approach | Status |
|--------------|------------------|--------|
| `hasattr(model, 'project')` autosave guard | Explicit allowlist `('Console', 'Device', 'CommBeltPack')` | Shipped in Phase 9 WR-04 fix (views.py:7696 comment) |
| Phase 10 `signal_flow_export_png` stub (HTTP 501) | Phase 10 fills this as client-side html-to-image | Stub at views.py:7860 confirmed |
| 4 sidebar shape types (Phase 8) | 7 sidebar shape types after Phase 10 | Extend in editor.html + PICKER_TYPE_CONFIG |

**Already-resolved by stub:** `signal_flow_export_png` URL and data attribute are already
wired (views.py:7860, urls.py:343, editor.html:29). The Phase 10 JS work reads the already-
present attribute and does not require new template changes for the URL scaffold.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `html-to-image.toPng` options `width` + `height` capture the full JointJS paper (not just visible viewport) | PNG Export | PNG may crop to viewport; low risk — verify with one manual test |
| A2 | SVG `stroke-dasharray` orphan ghost renders correctly via html-to-image (no filter effects used) | PNG Export pitfall 2 | Orphan shapes may render incorrectly in export; low risk |
| A3 | PNG generation at pixelRatio:2 for a 4000×3000 canvas completes in < 5 seconds | PNG Export | UX degradation if too slow; add loading toast regardless |
| A4 | ARIA combobox pattern (role=combobox, aria-controls=listbox, aria-activedescendant) follows standard without library | Autocomplete UX | Minor a11y issue if pattern is incomplete; no functional breakage |
| A5 | `htmlToImage` is the global namespace name when html-to-image.min.js loads as UMD | PNG Export | Export fails entirely if namespace differs; verify with `typeof htmlToImage` in console |

---

## Open Questions

1. **CONTEXT.md allowlist lists 4 models; research concludes 2**
   - CONTEXT.md line 132 says extend to `('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor', 'P1Processor', 'GalaxyProcessor')`.
   - Research finding: `P1Processor` and `GalaxyProcessor` have no `project` FK and are never stored as canvas GFK targets (the picker targets `SystemProcessor`). Adding them to the allowlist without a project FK lookup path would require custom filter logic.
   - Recommendation: Add only `Amp` and `SystemProcessor`. If the planner disagrees, the custom filter for P1Processor would be `p1_processor__system_processor__project=current_project`.

2. **`Amp.select_related('amp_model')` in autocomplete queryset**
   - The existing `signal_flow_autocomplete` qs construction doesn't use `select_related`. Adding it for Amp avoids N+1 on `str(a.amp_model)`. This is a one-line addition in the view.

3. **`data-label-autocomplete-url` attribute on `#sfd-container`**
   - The label autocomplete endpoint is a new URL. The JS needs to know it. Two options: (a) add a `data-label-autocomplete-url` attribute to `#sfd-container` in `editor.html`, or (b) derive it from a hardcoded path. Option (a) follows the established pattern (all URLs come from `data-*` attributes per editor.html:26-29).

---

## Environment Availability

Step 2.6: SKIPPED — Phase 10 is code/config changes only. The `html-to-image` and
`joint.min.js` vendor files are already present (verified by `ls vendor/`). No new
CLI tools, runtimes, or services are required.

---

## Sources

### Primary (HIGH confidence — verified by direct codebase inspection)
- `planner/models.py:1841–1876` — AmpChannel model + `channel_name` field
- `planner/models.py:1898–1933` — SystemProcessor model (confirmed: no I/O companion model)
- `planner/models.py:1939–2091` — P1Processor, P1Input (`label`), P1Output (`label`)
- `planner/models.py:2097–2197` — GalaxyProcessor, GalaxyInput (`label`), GalaxyOutput (`label`)
- `planner/models.py:894–993` — ConsoleInput.source, ConsoleAuxOutput.name
- `planner/views.py:7529–7599` — `_enrich_nodes` implementation + current model allowlist
- `planner/views.py:7624–7749` — `signal_flow_autosave` + IDOR allowlist at line 7704
- `planner/views.py:7753–7856` — `signal_flow_autocomplete` MODEL_MAP + stub export view
- `planner/static/planner/js/signal_flow_editor.js:81–223` — shape namespace + all 5 shape classes
- `planner/static/planner/js/signal_flow_editor.js:309–314` — PICKER_TYPE_CONFIG
- `planner/static/planner/js/signal_flow_editor.js:492–511` — assignPickerResult (shape-type-agnostic)
- `planner/static/planner/css/signal_flow.css:575–596` — Sections 10+11 (last sections = append target)
- `planner/templates/planner/signal_flow/editor.html` — full template reviewed
- `planner/templates/planner/signal_flow/_equipment_picker_modal.html` — picker HTML reviewed
- `planner/urls.py:335–343` — signal_flow URL registrations
- `.planning/config.json` — `workflow.nyquist_validation: false` confirmed (validation section omitted)

### Tertiary (LOW confidence — assumed from training knowledge)
- html-to-image 1.11.11 `htmlToImage.toPng` API options (`pixelRatio`, `backgroundColor`, `width`, `height`)
- ARIA combobox pattern specifics
- PNG generation performance estimates

---

## Metadata

**Confidence breakdown:**
- D-05 SystemProcessor finding: HIGH — direct model inspection, no companion I/O model
- Amp label sources: HIGH — `AmpChannel.channel_name` verified at models.py:1845
- Autosave allowlist extension (2 models, not 4): HIGH — model FK structure verified
- `_enrich_nodes` extension: HIGH — current code verified at line 7573
- `assignPickerResult` no-change: HIGH — verified shape-type-agnostic
- html-to-image API behavior: LOW/ASSUMED — library is vendored but API docs not re-fetched
- Autocomplete ARIA pattern: ASSUMED — standard pattern, not spec-verified this session

**Research date:** 2026-05-21
**Valid until:** 2026-06-21 (stack is fully locked; no fast-moving dependencies)
