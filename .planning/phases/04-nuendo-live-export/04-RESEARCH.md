# Phase 4: Nuendo Live Export — Research

**Researched:** 2026-05-13
**Domain:** Nuendo Live 3 `.nlpr` template-injection XML exporter (Django + lxml)
**Confidence:** HIGH for codebase findings; MEDIUM for lxml mechanics (verified against official docs); LOW only for ID-collision tolerance and CRLF/LF acceptance in Nuendo Live 3 (no public spec — the canonical authority is `multitrack_session_builder_spec.md` and Charlie's real-file reverse engineering, not external sources).

---

## Summary

Phase 4 ships a single pure-function exporter `build_nlpr(session) → bytes` that mutates a bundled, Charlie-generated `.nlpr` template fixture in place via `lxml`. The exporter (a) loads the template, (b) locates the `Audio` MFolderTrack's single seed `MAudioTrackEvent` child, (c) deep-copies that seed once per enabled `MultitrackTrack`, (d) rewrites names, `Channel ID`, `Farb`, every `ID` attribute, and every `RuntimeID` value, and (e) serializes back to UTF-8 bytes. Everything else in the template (Devices block, Input/Output Channels folder, WindowLayouts, marker/tempo/signature tracks, UColorSet, transport state) passes through untouched. A new `MultitrackTrack.resolved_yamaha_name` property does color-name reverse-resolution. Exactly one automated test (`ID/RuntimeID` uniqueness) ships; the rest is HUMAN-UAT (open-in-Nuendo-Live-3 round-trip). The view layer mirrors `multitrack_export_rpp` (`planner/views.py:6875-6919`) verbatim down to the auth decorator (`@staff_member_required`) and no-tracks fallback pattern. The `target_daw='nuendo_live'` option is enabled in the new-session form by deleting two specific gates in `planner/forms.py:1192-1217` and one static disabled radio block in `planner/templates/planner/multitrack/new_session.html:72-78`.

**Primary recommendation:**
- Bundle the template at `planner/data/multitrack/nuendo_live_3_template.nlpr` and load it with `lxml.etree.parse(Path(__file__).parent.parent / 'data' / 'multitrack' / 'nuendo_live_3_template.nlpr')` at first export (deferred-cost pattern), keeping a module-level cache.
- Pin `lxml~=5.3.0` in `requirements.txt` (most recent stable major series with broad wheel coverage; lxml 6.x is also available but 5.x is the conservative pick).
- Match Phase 1's `@staff_member_required` decorator on `multitrack_export_nlpr` — Phase 1's code review (CR-01/CR-02) **kept** `@staff_member_required` on the read/download views and added `@login_required` + viewer-block only to the AJAX *mutate* endpoints. Phase 4's download view is a download, so it matches `@staff_member_required`.
- Use `copy.deepcopy(seed_track)` per-track, mutate with `.set('attr', value)` for `ID` attributes and `elem.find(...).set('value', ...)` for child `<int>` / `<string>` values. Run an `etree.tostring(root, xml_declaration=True, encoding='utf-8')` at the end.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Template Fixture Lifecycle

- **D-01:** Bundled fixture lives at `planner/data/multitrack/nuendo_live_3_template.nlpr`. Mirrors the existing convention used by `planner/data/csv_fixtures/` (Phase 2) and `planner/data/comm_config/pouchdb_factory/` (Comm Config) for opaque vendor-binary reference artifacts.
- **D-02:** Generation contract for the fixture (Charlie hand-generates on Windows + Nuendo Live 3 before plan execution finishes):
  - Exactly **1 default audio track** inside the `Audio` MFolderTrack, named `"Audio 01"` (spec §"Nuendo Live (.nlpr)" template-injection step 1).
  - Empty session settings — stock 120 BPM, 48 kHz sample rate, no markers, no signature changes, no tempo changes.
  - Saved on **Windows** so the `Application Version` block reports `Platform="WIN64"`.
  - No audio interface routings beyond Nuendo's defaults — the `Devices` block and `Input/Output Channels` folder pass through untouched.
- **D-03:** Runtime behavior when the fixture is missing, empty, or doesn't parse to exactly 1 audio track inside the `Audio` MFolderTrack: render `editor.html` with an `export_error` string, no download attempt. Matches the Phase 1 no-enabled-tracks pattern at `planner/views.py:6900-6912`. Suggested banner copy: *"Nuendo Live export is unavailable on this server — bundled template missing or malformed. Contact support."*

#### Color → Farb Resolution

- **D-04:** Add a new property `MultitrackTrack.resolved_yamaha_name` (Phase 4 helper, separate from `resolved_color`). Resolution order:
  1. If `color_override` is set AND its hex value exists as a value in `YAMAHA_TO_HEX` (`planner/utils/reaper_export.py:26-37`), return the matching palette name. (Reverse-lookup; only 8 of the 10 Yamaha names have hex values — `Off` and `White` map to `None` in `YAMAHA_TO_HEX` and are not reachable via the override path.)
  2. Else, if the track has a `resolved_source` AND that source has a `color` field with a non-default Yamaha palette name (`ConsoleInput.color`, `ConsoleAuxOutput.color`, `ConsoleMatrixOutput.color`, `ConsoleStereoOutput.color` — all added in Phase 2 D-07), return that palette name.
  3. Else, return `None`.
  Leaves `resolved_color` (hex) untouched. The Reaper exporter is unaffected by Phase 4 — its byte-stable Phase 1 contract holds.
- **D-05:** When `color_override` is a hex that does NOT match any value in `YAMAHA_TO_HEX`, the exporter emits **no `Farb` element** for that track, so Nuendo Live renders the default appearance.
- **D-06:** Single `YAMAHA_TO_FARB` table covers CL/QL and Rivage consoles. Phase 2 D-07 (amended L-05) already constrains channel-level color storage to `YAMAHA_COLOR_CHOICES` (the 10-name CL/QL palette) regardless of the source console family.
- **D-07:** `YAMAHA_TO_FARB` constant lives in `planner/utils/nuendo_live_export.py`. Locked table:

  | Yamaha name | Farb | Notes               |
  |-------------|------|---------------------|
  | `Off`       | omit | no color override   |
  | `Red`       | 0    |                     |
  | `Orange`    | 1    |                     |
  | `Yellow`    | 2    |                     |
  | `Green`     | 5    |                     |
  | `Sky Blue`  | 8    | maps to cyan        |
  | `Blue`      | 10   |                     |
  | `Purple`    | 12   |                     |
  | `Pink`      | 14   |                     |
  | `White`     | omit | use Nuendo default  |

#### ID & RuntimeID Generation

- **D-08:** Deterministic sequential allocation. At module load (or first export call), scan the bundled template once with `lxml` and find the maximum existing integer value across every `<obj ID="...">` attribute and every `<int name="RuntimeID" value="..."/>` child. Allocate fresh IDs sequentially starting from `max + 1000` per export.
- **D-09:** Test coverage = ONE automated assertion. Parse the generated `.nlpr` bytes back with `lxml`, collect every `ID` attribute and every `RuntimeID` value, assert `len(set(values)) == len(values)`. Directly verifies success criterion 5 / NLP-06.
- **D-10:** **All IDs replaced for every track**, including track 1. The bundled template's existing track-level IDs are seed data only — never reused in the output.

#### Export Button Visibility & target_daw Semantics

- **D-11:** All three export buttons are always shown in the editor toolbar. Add "Export to Nuendo Live (.nlpr)" as a third button alongside the existing two at `planner/templates/planner/multitrack/editor.html:75-82`. No gating on `session.target_daw`.
- **D-12:** Enable the `target_daw='nuendo_live'` choice in the new-session form dropdown. The model choice already exists at `planner/models.py:980`; the UI / form gate is the only change.
- **D-13:** Nuendo Live button reuses the existing toolbar button styles (`mts-btn mts-btn-success` for the primary download link).
- **D-14:** Single `.nlpr` button — no "Nuendo Live track template" variant.

### Claude's Discretion

- **Exact wave structure for plan execution.** Suggested: Wave 1 = exporter logic + ID-uniqueness test against Python-generated fake template; Wave 2 = view + URL + guards; Wave 3 = form enable + toolbar button. Charlie generates the real fixture as a prerequisite before Wave 2 completes.
- **Module-load vs first-export fixture parse timing.** Either is fine.
- **Django system check** verifying the fixture parses at deploy time — allowed (not required since D-03 handles runtime gracefully).
- **`lxml` version pin.** Pick a recent stable (≥4.9.x) and pin to `~=`.
- **CRLF / encoding preservation strategy.** lxml default is LF — verify Nuendo Live 3 accepts LF; if not, explicitly write CRLF.
- **Permission gate on the export view.** Match whatever Phase 1 ships post-fix.
- **Filename for the download.** `<_safe_filename(session.name)>.nlpr`, reusing the helper at `planner/views.py:6856`.
- **Whether to expose `build_nlpr` from a public module path** — yes, mirror `build_rpp`/`build_rtracktemplate`.
- **Whether `MultitrackTrack.resolved_yamaha_name` is a `@property`** or a helper function — recommendation is property for consistency.

### Deferred Ideas (OUT OF SCOPE)

- Snapshot byte-for-byte regression tests for `.nlpr` output (rejected per D-09).
- Structural / parsed-XML regression test beyond uniqueness.
- Automated round-trip-via-real-Nuendo-Live test (no Nuendo Live 3 in CI).
- Channel-level color storage feeding `MultitrackTrack.resolved_color` (hex) — separate phase, do NOT touch the Phase 1 byte-stable Reaper output.
- Nearest-Farb-by-RGB-distance mapping for arbitrary hex overrides.
- Nuendo Live "track template" / merge-into-existing-project variant (no such format exists).
- Separate Rivage→Farb mapping table.
- Pro Tools `.txt` / AAF exporter (deferred to v2.1).
- `target_daw`-driven button gating in the editor toolbar.
- Per-user last-used `target_daw` default for new sessions.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NLP-01 | User can export the current session as a Nuendo Live 3 `.nlpr` file via the bundled empty-template injection path. | Standard Stack §lxml + Architecture Pattern 1 (template-injection); view layer mirrors `multitrack_export_rpp` (`planner/views.py:6875-6919`). |
| NLP-02 | The exported `.nlpr` loads in Nuendo Live 3 without errors. | HUMAN-UAT only — spec §"Round-trip test plan" (`multitrack_session_builder_spec.md:305-310`). No automated coverage. |
| NLP-03 | Each track's name renders correctly inside Nuendo Live (outer `Name` and inner `DeviceAttributes → Name → String` match). | Architecture Pattern 2 (two writes per track to the two `<string ... wide="true" value="..."/>` elements); spec lines 213, 228-230. |
| NLP-04 | Each track's color renders correctly using a `Farb` palette index. | D-04/D-07 `YAMAHA_TO_FARB` table; new `MultitrackTrack.resolved_yamaha_name` property; reverse-lookup via `{v: k for k, v in YAMAHA_TO_HEX.items() if v}` at module load. |
| NLP-05 | Tracks with no assigned color export with `Farb` omitted. | When `resolved_yamaha_name` returns `None`, remove the `<int name="Farb" .../>` element from the deep-copied subtree before append (lxml: `farb_elem.getparent().remove(farb_elem)`). |
| NLP-06 | All `ID` and `RuntimeID` values in the exported file are unique within the document. | D-08 sequential allocator + D-09 single automated assertion (`len(set(values)) == len(values)`). |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Django 5.x + PostgreSQL (Railway).** All views project-scope via `request.current_project` (`CurrentProjectMiddleware`). The Nuendo export view does exactly this — see Architecture Pattern 3.
- **Templates layout — two dirs.** `editor.html` lives in the app-level `planner/templates/planner/multitrack/`, not the project-level `templates/`. Confirmed at `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/templates/planner/multitrack/editor.html`.
- **Custom admin site.** N/A this phase — no new admin registrations. The `admin_ordering.py` sidebar list is untouched.
- **Deploys via `railway.json`'s `startCommand`, NOT `Procfile`.** Phase 4 adds `lxml` to `requirements.txt`; the existing `collectstatic && migrate && create_initial_superuser && setup_user_groups && load_amp_profiles && gunicorn` startCommand needs no edit (lxml is a pure pip install).
- **Don't commit `.env` / Resend keys / Railway tokens.** Nothing in Phase 4 touches secrets.
- **Beta-tester safety: additive migrations only.** Phase 4 ships **zero** migrations (D-04 is a `@property`, not a DB field) — naturally compliant.
- **Don't run destructive SQL against Railway Postgres without confirming.** Phase 4 has no DB writes from the exporter (pure function); the view does ORM reads only.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `.nlpr` file generation | Pure Python (`planner/utils/`) | — | Pure function `build_nlpr(session) → bytes`. No DB writes, no HTTP shape concerns. Mirrors `reaper_export.py` pattern. |
| ID/RuntimeID allocation | Pure Python (`planner/utils/`) | — | Internal to the exporter module. Sequential counter scoped to one `build_nlpr()` call. |
| Template fixture loading | Pure Python (`planner/utils/`) | Filesystem | `pathlib.Path(__file__).parent.parent / 'data' / 'multitrack' / 'nuendo_live_3_template.nlpr'` — same pattern as Phase 1's CSV fixtures. |
| Color name → Farb mapping | Pure Python (`planner/utils/`) | — | Static dict `YAMAHA_TO_FARB`, module-level constant. |
| Color resolution (override/source) | Django ORM model (`planner/models.py`) | — | `MultitrackTrack.resolved_yamaha_name` `@property`. Reads `color_override` + `resolved_source.color`. No DB write. |
| HTTP response shape / filename | Django view (`planner/views.py`) | — | `HttpResponse(body, content_type='application/xml; charset=utf-8')` + `Content-Disposition`. Mirrors `multitrack_export_rpp`. |
| Project-scope guard | Django middleware (`CurrentProjectMiddleware`) | View (filter ORM by `project=current_project`) | Standard ShowStack pattern. |
| Auth gate | Django decorator (`@staff_member_required`) | — | Matches Phase 1 download views post-CR-01/CR-02. |
| Form gate removal | Django form (`planner/forms.py`) | Template (`new_session.html`) | Three separate gates to remove (see Pitfall 6). |
| Toolbar button | Django template (`editor.html`) | — | Static HTML, no JS. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `lxml` | `~=5.3.0` | XML parsing, deep-copy, attribute mutation, namespaced serialization | The spec explicitly mandates lxml (not stdlib ElementTree) because *"stdlib ElementTree mangles output"* — preserves source formatting, supports `tostring(..., xml_declaration=True, encoding='utf-8')`, supports `copy.deepcopy(element)`. lxml is the de facto standard for any production-grade Python XML work where formatting / round-trip matters. `[VERIFIED: spec line 200; CITED: lxml.de/tutorial.html]` |

**Note on `lxml` version choice:** lxml 6.x exists (`6.1.0` released 2026-04-17) but 5.3.x is the conservative pick — broader wheel coverage on older Linux base images, stable API, no breaking changes for the ops Phase 4 uses (parse / deepcopy / tostring / xpath). `[VERIFIED: pypi.org/project/lxml]`

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `copy` (stdlib) | — | `deepcopy(seed_track)` to clone the template's seed `MAudioTrackEvent` per output track | Always. lxml docs explicitly recommend `copy.deepcopy()` for element duplication. `[CITED: lxml.de/tutorial.html]` |
| `pathlib` (stdlib) | — | Locate the bundled fixture via `Path(__file__).parent.parent / 'data' / 'multitrack' / ...` | Always. Matches Phase 1 pattern (`planner/views.py:4222` uses `os.path.join(settings.BASE_DIR, ...)` but pathlib is cleaner inside `planner/utils/`). |
| `io.BytesIO` (stdlib) | — | If you ever want to parse from an in-memory buffer (e.g. tests) | Tests only. Production parses the bundled fixture from disk. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `lxml` | `xml.etree.ElementTree` (stdlib) | Rejected by spec — mangles whitespace and namespace prefix output. Nuendo's XML has very specific formatting; round-trip safety needs lxml. `[CITED: spec line 200]` |
| `lxml` | `xmltodict` + manual rebuild | Rejected — dict-roundtrip loses element order and attribute ordering. Template-injection needs an element-tree mutation model, not a dict-based one. `[ASSUMED]` |
| Sequential ID allocator | Random 32-bit ints | Rejected per D-08 (deterministic > random for test stability; "same input → same output IDs across runs" enables future snapshot tests if ever added). Spec lines 290-291 mention "Random unique ints work" but D-08 explicitly chooses sequential. |
| `Path(__file__).parent` chain | `django.conf.settings.BASE_DIR` | Either works; the Comm Config code uses `settings.BASE_DIR` (`planner/views.py:4222`). For `planner/utils/`, `Path(__file__).parent.parent / 'data' / ...` keeps the utility self-contained — no settings import — and is preferable. |

**Installation:**
```bash
# Add to requirements.txt:
lxml~=5.3.0
```
Railway deploys via `pip install -r requirements.txt`; lxml ships pre-built manylinux wheels for Python 3.9–3.12 so no compilation is required. `[CITED: pypi.org/project/lxml]`

**Version verification:** Most recent stable as of research date: lxml 6.1.0 (2026-04-17). Conservative pick: 5.3.0 (released mid-2024, stable API for the operations this phase uses). Locked range `~=5.3.0` admits 5.3.x patch releases. `[VERIFIED: pypi.org/project/lxml]`

## Architecture Patterns

### System Architecture Diagram

```
                    ┌──────────────────────────────────────────────┐
   Engineer click   │  Browser                                     │
   ─────────────►   │  GET /audiopatch/multitrack/<id>/export.nlpr/│
                    └────────────────────┬─────────────────────────┘
                                         │
                                         ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  Django (Railway)                                               │
   │                                                                 │
   │  CurrentProjectMiddleware → request.current_project ────┐       │
   │                                                          │       │
   │  multitrack_export_nlpr(request, session_id)             │       │
   │  ├─ @staff_member_required (auth gate)                   │       │
   │  ├─ MultitrackSession.objects.filter(id, project=p)──────┘       │
   │  ├─ _has_enabled_tracks(session) ──── False ─► render editor.html│
   │  │                                            with export_error  │
   │  └─ True                                                          │
   │      │                                                            │
   │      ▼                                                            │
   │  build_nlpr(session)  [planner/utils/nuendo_live_export.py]      │
   │      │                                                            │
   │      ▼                                                            │
   │  ┌─────────────────────────────────────────────────────────┐    │
   │  │  1. _load_template() ─► parse                            │    │
   │  │     planner/data/multitrack/nuendo_live_3_template.nlpr  │    │
   │  │     (cached at module-level after first call)            │    │
   │  │                                                          │    │
   │  │     If missing/malformed ─► raise ExportTemplateError    │    │
   │  │                                                          │    │
   │  │  2. tree = deepcopy(cached_template)                     │    │
   │  │     allocator = SequentialIdAllocator(start=max+1000)    │    │
   │  │                                                          │    │
   │  │  3. audio_folder = _find_audio_folder(tree)              │    │
   │  │     seed_track  = _find_seed_track(audio_folder)         │    │
   │  │     track_list  = seed_track.getparent()  # <list>       │    │
   │  │                                                          │    │
   │  │  4. for n, mt_track in enumerate(                        │    │
   │  │              _ordered_enabled_tracks(session), start=1): │    │
   │  │       new_track = copy.deepcopy(seed_track)              │    │
   │  │       _replace_ids(new_track, allocator)                 │    │
   │  │       _set_names(new_track, mt_track.resolved_label)     │    │
   │  │       _set_channel_id(new_track, n)                      │    │
   │  │       _apply_farb(new_track, mt_track.resolved_yamaha_   │    │
   │  │                                 name)                    │    │
   │  │       track_list.append(new_track)                       │    │
   │  │                                                          │    │
   │  │  5. track_list.remove(seed_track)   # drop template seed │    │
   │  │                                                          │    │
   │  │  6. return etree.tostring(tree.getroot(),                │    │
   │  │            xml_declaration=True, encoding='utf-8')       │    │
   │  └─────────────────────────────────────────────────────────┘    │
   │      │                                                            │
   │      ▼                                                            │
   │  HttpResponse(body, content_type='application/xml; charset=utf-8')│
   │  Content-Disposition: attachment;                                 │
   │      filename="<_safe_filename(session.name)>.nlpr"               │
   │                                                                   │
   └──────────────────────────┬────────────────────────────────────────┘
                              │ HTTP 200, file download
                              ▼
                    ┌─────────────────────────────────┐
                    │  Engineer opens .nlpr in        │
                    │  Nuendo Live 3 (HUMAN-UAT)      │
                    └─────────────────────────────────┘
```

### Component Responsibilities

| Layer | File | Responsibility |
|-------|------|----------------|
| URL | `planner/urls.py:140` (new) | Route `multitrack/<int:session_id>/export.nlpr/` → `multitrack_export_nlpr` |
| View | `planner/views.py` (after line 6961) | Auth, project scope, no-tracks guard, missing-fixture guard, HTTP response shape |
| Exporter | `planner/utils/nuendo_live_export.py` (NEW) | Pure `build_nlpr(session) → bytes`. No DB writes. No HTTP. |
| Color helper | `planner/models.py:1088` (new property) | `MultitrackTrack.resolved_yamaha_name → str|None` |
| Fixture | `planner/data/multitrack/nuendo_live_3_template.nlpr` (NEW, hand-generated) | Read-only binary asset, committed to git |
| Form | `planner/forms.py:1192-1217` (REMOVE 3 gates) | Enable `nuendo_live` choice in `target_daw` field |
| Template (form) | `planner/templates/planner/multitrack/new_session.html:72-78` (REMOVE) | Remove the static disabled radio |
| Template (editor) | `planner/templates/planner/multitrack/editor.html` (after line 81) | Add third toolbar button |
| Test | `planner/tests/test_nuendo_live_export.py` (NEW) | ONE assertion: ID/RuntimeID uniqueness |

### Pattern 1: Template-Injection Mutation Loop

**What:** Load a known-good fixture, locate the single seed track, deep-copy it per output track, mutate names/IDs/color in place, append back as siblings, drop the original seed.

**When to use:** Any XML format where (a) you don't fully understand all fields and (b) a real-world saved file exists. Synthesizing from scratch risks missing opaque-but-required fields (e.g. `Eths`, `OwnInputBus`, `SendFolder` boilerplate — spec lines 232-234).

**Why:** Per spec line 195: *"Bundle a known-good empty `.nlpr` template as a fixture in the module... Do NOT synthesize the file from scratch."*

**Example:**
```python
# Source: spec lines 196-205 (template-injection algorithm)
# Plus lxml.de/tutorial.html (deepcopy + parent/append mechanics)
from io import BytesIO
import copy
from pathlib import Path
from lxml import etree

_TEMPLATE_PATH = (
    Path(__file__).parent.parent / 'data' / 'multitrack' /
    'nuendo_live_3_template.nlpr'
)
_TEMPLATE_TREE = None  # module-level cache

def _load_template():
    global _TEMPLATE_TREE
    if _TEMPLATE_TREE is None:
        if not _TEMPLATE_PATH.exists():
            raise ExportTemplateError(f'Template missing: {_TEMPLATE_PATH}')
        _TEMPLATE_TREE = etree.parse(str(_TEMPLATE_PATH))
    # Return a deepcopy of the *root* so callers can mutate freely.
    return copy.deepcopy(_TEMPLATE_TREE.getroot())

def build_nlpr(session):
    root = _load_template()
    audio_folder = _find_audio_folder(root)        # see Pattern 2
    track_list = audio_folder.find(".//list[@name='Tracks']")
    seed_track = track_list.find("./obj[@class='MAudioTrackEvent']")
    if seed_track is None:
        raise ExportTemplateError('Template has no seed audio track')

    max_id = _scan_max_id(root)
    next_id = max_id + 1000

    for n, mt_track in enumerate(_ordered_enabled_tracks(session), start=1):
        new_track = copy.deepcopy(seed_track)
        next_id = _replace_all_ids(new_track, next_id)
        _set_names(new_track, mt_track.resolved_label)
        _set_channel_id(new_track, n)
        _apply_farb(new_track, mt_track.resolved_yamaha_name)
        track_list.append(new_track)

    track_list.remove(seed_track)  # drop the template's original
    return etree.tostring(root, xml_declaration=True, encoding='utf-8')
```

### Pattern 2: XPath Lookup for `Audio` MFolderTrack

**What:** Find the `<obj class="MFolderTrack">` whose inner `<string name="Name" value="Audio"/>` says "Audio" — NOT the one whose name is "Input/Output Channels" (which holds device routings).

**Why this matters:** Per spec lines 200-201: *"locate the audio track folder: `MFolderTrack` whose `MTrackList → Name` value is `'Audio'` (NOT the `'Input/Output Channels'` folder, which holds device routings — leave that alone)."*

**Example:**
```python
# Use XPath to filter by inner child value — more robust than walking
# child-by-child because the order of MFolderTrack siblings is not
# guaranteed across Nuendo versions.
def _find_audio_folder(root):
    folders = root.xpath(
        ".//obj[@class='MFolderTrack']"
        "[.//string[@name='Name' and @value='Audio']]"
    )
    if not folders:
        raise ExportTemplateError(
            "No MFolderTrack named 'Audio' found in template"
        )
    if len(folders) > 1:
        raise ExportTemplateError(
            f"Multiple Audio folders found ({len(folders)})"
        )
    return folders[0]
```

### Pattern 3: View Layer (mirror `multitrack_export_rpp`)

**What:** Standard ShowStack download-view shape — auth decorator, project scope, no-tracks fallback rendering editor with `export_error`, missing-fixture fallback identical to no-tracks, HttpResponse with Content-Disposition.

**When to use:** Always for this phase. Phase 1's pattern is the canonical reference (`planner/views.py:6875-6919`).

**Example:**
```python
# Source: planner/views.py:6875-6919 verbatim — adapt for .nlpr.
@staff_member_required
def multitrack_export_nlpr(request, session_id):
    """GET: download a Nuendo Live .nlpr file for this session (NLP-01..06)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    session = MultitrackSession.objects.filter(
        id=session_id, project=current_project
    ).select_related('console').first()
    if not session:
        return redirect('planner:multitrack_dashboard')

    if not _has_enabled_tracks(session):
        enabled_tracks_qs = session.tracks.filter(enabled=True).order_by('track_number')
        return render(request, 'planner/multitrack/editor.html',
            _editor_context(session, tracks=enabled_tracks_qs,
                current_project=current_project,
                export_error='This session has no enabled tracks. '
                             'Enable at least one track to export.',
                auto_open_picker=False))

    try:
        body = build_nlpr(session)
    except ExportTemplateError:
        # D-03: render editor with banner instead of 500.
        return render(request, 'planner/multitrack/editor.html',
            _editor_context(session, current_project=current_project,
                export_error='Nuendo Live export is unavailable on this server '
                             '— bundled template missing or malformed. '
                             'Contact support.',
                auto_open_picker=False))

    response = HttpResponse(body, content_type='application/xml; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="{_safe_filename(session.name)}.nlpr"'
    )
    return response
```

### Pattern 4: `resolved_yamaha_name` Reverse-Lookup

**What:** A new `@property` on `MultitrackTrack` that returns the Yamaha palette name (string) or `None`, used by the exporter to look up the Farb index.

**Why a property:** Mirrors `resolved_label`, `resolved_color`, `resolved_dante_number`, `resolved_source` (all `@property` at `planner/models.py:1060-1106`). The convention is set; deviating to a free function would create asymmetry.

**Example:**
```python
# Add at planner/models.py, alongside other resolved_* properties.
# Source: D-04 resolution order; YAMAHA_TO_HEX at planner/utils/reaper_export.py:26-37.

# Module-level reverse lookup, built once.
from .utils.reaper_export import YAMAHA_TO_HEX
_HEX_TO_YAMAHA_NAME = {
    hex_val.lower(): name
    for name, hex_val in YAMAHA_TO_HEX.items()
    if hex_val  # skip 'Off' / 'White' (both None)
}

class MultitrackTrack(models.Model):
    # ... existing fields and properties ...

    @property
    def resolved_yamaha_name(self):
        """D-04: Yamaha palette name for Nuendo Farb mapping, or None.

        Resolution order:
          1. color_override hex → reverse-lookup against YAMAHA_TO_HEX.
          2. resolved_source.color (channel-level YAMAHA_COLOR_CHOICES name).
          3. None.

        Returning None signals 'omit Farb' to the Nuendo exporter (D-05).
        Phase 1's resolved_color (hex) is intentionally untouched.
        """
        if self.color_override:
            name = _HEX_TO_YAMAHA_NAME.get(self.color_override.lower())
            if name:
                return name
            # color_override is hex but NOT a palette match → D-05: omit Farb
            return None
        src = self.resolved_source
        if src is None:
            return None
        color = getattr(src, 'color', None)
        if not color or color == 'Off':
            return None
        return color
```

### Anti-Patterns to Avoid

- **Don't synthesize the `.nlpr` from scratch.** Spec line 195 mandates template-injection. The opaque fields (`Eths`, `Volume`, `Panner`, `SendFolder`, `OwnInputBus`, `IDString`, ~150 lines of boilerplate per track) cannot be safely synthesized without breaking Nuendo on import.
- **Don't reuse template IDs for track 1.** Per D-10, every output track's IDs come from the sequential allocator, including track 1. The seed track is removed entirely after the loop.
- **Don't touch the `Input/Output Channels` MFolderTrack.** Spec line 301: it holds device routings — the spec explicitly lists it among "Things NOT to touch in the template."
- **Don't mutate the cached module-level template tree.** Always deepcopy *after* loading from cache (see Pattern 1's `_load_template`). Mutating the cached tree would corrupt subsequent exports.
- **Don't apply `_sanitize_name` from `reaper_export.py` to Nuendo strings.** That helper turns `"` into `'` because Reaper's NAME token uses bare-quote wrapping. Nuendo uses proper XML attribute escaping — lxml's `.set('value', user_string)` handles `<`, `>`, `&`, `"`, `'` automatically. (See Pitfall 1 below for what Nuendo *does* require.)
- **Don't add a Django system check that imports the exporter at AppConfig.ready().** Importing lxml at startup is fine; *parsing the template* at startup adds ~10-50ms to gunicorn worker boot. Defer to first export (D-03 handles the missing-fixture case gracefully).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XML attribute escaping | Manual `str.replace('<', '&lt;')` etc. | `lxml.etree.Element.set('value', user_string)` | lxml auto-escapes the five XML special chars (`<`, `>`, `&`, `"`, `'`) on `set()`. Hand-rolling misses edge cases (e.g. NUL bytes, surrogate pairs in `wide="true"` UTF-16 strings). `[CITED: lxml.de/tutorial.html § "Elements carry attributes as a dict"]` |
| Element deep-copy | Manual recursive walk | `copy.deepcopy(element)` | Per lxml docs: *"etree elements can be copied using `copy.deepcopy()` and `copy.copy()`."* Handles namespaces, attributes, text, tail, child order. `[CITED: lxml.de/tutorial.html]` |
| XPath traversal | `for child in elem: ...` walks | `elem.xpath("./obj[@class='MFolderTrack']")` | XPath handles attribute predicates and depth navigation in one expression. Walking is fragile to sibling-order changes across Nuendo versions. `[CITED: lxml.de/tutorial.html § XPath]` |
| ID uniqueness check (test) | Hand-coded `for x in ids: if x in seen ...` | `assert len(set(ids)) == len(ids)` | One-line invariant; D-09 specifies this exact shape. |
| Fixture file loading path | `os.path.join('planner', 'data', ...)` from arbitrary cwd | `Path(__file__).parent.parent / 'data' / ...` | `__file__`-relative paths work regardless of `manage.py runserver` vs `gunicorn` cwd. Phase 2's CSV fixtures and Comm Config's pouchdb both use this pattern. |
| Color name → Farb index lookup | Long `if/elif` chain | Module-level dict `YAMAHA_TO_FARB` | Mirrors `YAMAHA_TO_HEX` (`planner/utils/reaper_export.py:26-37`). Static lookup, locked at D-07. |
| Track ordering across DAW formats | Reimplement console/dante/custom logic | `from .reaper_export import _ordered_enabled_tracks` | Already implemented at `planner/utils/reaper_export.py:134-169`. Track order is universal across DAW formats — Phase 4 reimports verbatim. |
| Filename sanitization | New helper | `from planner.views import _safe_filename` | Reuse `planner/views.py:6856-6868`. ASCII-only, hyphen/underscore preserved, everything else `_`. |

**Key insight:** lxml's API closes ~90% of the manual XML work this phase would otherwise need. The only Nuendo-specific logic is (a) where the seed track lives (Pattern 2), (b) what mutations apply to each clone (Pattern 1's loop body), and (c) the Yamaha→Farb mapping table (D-07). Everything else — parsing, escaping, deep-copy, serialization — is library work.

## Runtime State Inventory

> Phase 4 is a greenfield exporter (new file + new view). Not a rename/refactor. **Section omitted.**

## Common Pitfalls

### Pitfall 1: Stdlib ElementTree mangles output

**What goes wrong:** Using `xml.etree.ElementTree` instead of `lxml.etree` produces output that Nuendo Live may not parse cleanly — namespace prefix reassignment, whitespace collapse, and attribute reordering all happen silently.

**Why it happens:** stdlib ElementTree was designed for "any valid XML in/out," not for round-tripping vendor formats.

**How to avoid:** Use `lxml.etree.parse()` and `lxml.etree.tostring()` exclusively. Never `from xml.etree import ElementTree` in this exporter.

**Warning signs:** Diff between Charlie's hand-generated template and a no-op round-trip (`parse → tostring`) shows changes — that means the chosen library is mutating things. lxml should be a perfect round-trip absent any deliberate mutations.

`[CITED: spec line 200 — "preserves formatting; stdlib ElementTree mangles output"]`

### Pitfall 2: Forgetting to drop the seed track

**What goes wrong:** The seed track from the template stays in the output `<list>` alongside the N appended clones. Engineer sees N+1 tracks in Nuendo with an unexpected "Audio 01" prepended.

**Why it happens:** D-10 says "every output track is generated identically" — easy to read that as "deep-copy the seed for every track" without remembering to also remove the original.

**How to avoid:** The exporter must call `track_list.remove(seed_track)` **after** the loop appends all clones. Pattern 1's code example shows the correct sequence.

**Warning signs:** Generated `.nlpr` has `enabled_track_count + 1` `<obj class="MAudioTrackEvent">` elements instead of `enabled_track_count`. (A cheap structural test if planner adds one under Claude's Discretion per CONTEXT.md §"Test budget — one assertion.")

### Pitfall 3: Mutating the cached module-level template

**What goes wrong:** First export's mutations leak into the cached `_TEMPLATE_TREE`, so subsequent exports start from a corrupted base. Each export adds another N tracks on top of the previous N.

**Why it happens:** lxml elements are mutable. If you cache `etree.parse(path).getroot()` and return that directly, callers append to the cached tree.

**How to avoid:** Cache the parsed tree but always return `copy.deepcopy(root)` from the loader. See Pattern 1's `_load_template`.

**Warning signs:** Two consecutive exports of the same session produce different byte outputs (second has more tracks). The ID-uniqueness test would still pass (the allocator starts at `max+1000` per call, but if max is recomputed each call against a growing cached tree, IDs creep up). Actual symptom: track count grows on each export.

### Pitfall 4: `wide="true"` UTF-16 string considerations

**What goes wrong:** Nuendo's `<string name="Name" value="..." wide="true"/>` elements signal UTF-16 storage. Most Latin characters are safe, but surrogate pairs (e.g. emoji, some CJK supplementary plane characters) might confuse Nuendo's UTF-16 decoder.

**Why it happens:** XML attribute values are always UTF-8 in the file, but `wide="true"` is Nuendo's hint to its in-memory model that it should store the value as UTF-16. The conversion happens inside Nuendo. lxml doesn't care — it just escapes the chars per XML spec.

**How to avoid:** lxml's `.set('value', user_string)` correctly escapes `<`, `>`, `&`, `"`, `'`. For NUL bytes, the XML spec forbids them entirely — lxml will raise `ValueError` on `set('value', '\x00')`. Validate or strip NUL bytes from `mt_track.resolved_label` before calling `.set()`. Most label fields are `CharField(max_length=100)` and Django's form validation already rejects NUL by default, but defense-in-depth: strip control chars (`\x00-\x08\x0B\x0C\x0E-\x1F`) before writing.

**Warning signs:** lxml raises `ValueError: All strings must be XML compatible` on `.set()`. Track labels containing NUL or other control chars trigger this. The fix is sanitize before write, not catch-and-ignore.

`[ASSUMED for surrogate-pair behavior in Nuendo Live 3; VERIFIED for lxml escaping behavior]`

### Pitfall 5: Auth decorator mismatch with Phase 1's post-CR-01/CR-02 state

**What goes wrong:** Phase 4's view uses a different auth decorator than Phase 1's download views, creating a security inconsistency.

**Why it happens:** The Phase 1 code review report mentions CR-01/CR-02 added `@login_required` + viewer-block to AJAX *mutate* endpoints. It's tempting to assume the download views were also retightened.

**How to avoid:** Verify the current state of `multitrack_export_rpp` and `multitrack_export_rtracktemplate`. **As of 2026-05-13 they both have `@staff_member_required` only** — see `planner/views.py:6875` and `:6922`. The CR-01/CR-02 fix was scoped to AJAX mutate endpoints (set_color, set_label, set_enabled, remove_track, reorder — see the `@login_required` + `_multitrack_viewer_block` pattern at `planner/views.py:6697-6710`). The download views were NOT changed. Phase 4 matches: `@staff_member_required` only.

**Warning signs:** Lint / pre-commit doesn't catch this; only careful diff against Phase 1 will. Document the chosen decorator with a comment referencing CR-01/CR-02.

`[VERIFIED: grep of planner/views.py:6875, 6922 + 01-REVIEW-FIX.md scope]`

### Pitfall 6: Three places gate `nuendo_live` — must remove all three

**What goes wrong:** Removing only the form's `clean_target_daw()` or only the template's static disabled radio leaves the choice broken in a subtle way (either the user can't pick it, or they can pick it but it shows visually as disabled, or the form rejects it).

**Why it happens:** Phase 1 belt-and-suspenders-ed the gate three ways:
1. `planner/forms.py:1197-1199` — strips `nuendo_live` from `self.fields['target_daw'].choices`
2. `planner/forms.py:1209-1217` — `clean_target_daw()` raises ValidationError on `nuendo_live`
3. `planner/templates/planner/multitrack/new_session.html:72-78` — static `<input type="radio" disabled>` next to the dynamic radios

**How to avoid:** Remove all three together in the same commit. Recommended approach:
1. **Delete** the choices-restriction block at `forms.py:1192-1199`.
2. **Delete** the entire `clean_target_daw` method at `forms.py:1209-1217`.
3. **Delete** the static-radio block in `new_session.html:72-78` (the `{# Nuendo Live disabled... #}` comment and the following `<label>` element).

After removal, the `target_daw` field uses the model's `TARGET_DAW_CHOICES` directly (`planner/models.py:978-981`), which already includes `nuendo_live`. The dynamic `{% for radio in form.target_daw %}` loop in `new_session.html:66-71` will then render both radios.

Update the comment at `planner/models.py:980` from `# disabled in UI until Phase 4 ships` to a Phase 4 reference (e.g. delete the comment entirely).

**Warning signs:** Form submission with `target_daw='nuendo_live'` fails with "Nuendo Live export ships in v2.0 Phase 4" — that's the `clean_target_daw` method still firing. Or: radio renders disabled — that's the static template block still present.

`[VERIFIED: planner/forms.py:1192-1217, planner/templates/planner/multitrack/new_session.html:72-78]`

### Pitfall 7: ID/RuntimeID uniqueness — what to scan, what to allocate

**What goes wrong:** Sequential allocator collides with an ID buried somewhere in the untouched parts of the template (e.g. inside `<UColorSet>`, `<Devices>`, or `<WindowLayouts>`).

**Why it happens:** D-08 says "scan the template once and find the maximum existing integer value across every `<obj ID="...">` attribute and every `<int name='RuntimeID' value='...'/>`." If the scan misses any element shape that carries an ID (e.g. another attribute name, or RuntimeID stored as an `<obj ID=...>` not `<int name='RuntimeID'>`), the allocator's starting point could land below an existing ID.

**How to avoid:** Be thorough on the scan. Match on `@ID` attribute on **any** element AND `<int name='RuntimeID' .../>` AND `<int name='ID' .../>` if present. Use lxml XPath: `root.xpath("//*[@ID]")` for the attribute form, `root.xpath("//int[@name='RuntimeID' or @name='ID']")` for the value form. Take `max()` across both populations.

**Warning signs:** The single D-09 assertion (`len(set(values)) == len(values)`) is precisely the test for this. If it fails on the real fixture (after Charlie generates it), the scan missed an ID location. Fix the scan, not the test.

`[CITED: spec lines 290-291 — "All `ID` attributes... must be unique within the document"]`

### Pitfall 8: CRLF / LF / encoding mismatch with Nuendo Live 3

**What goes wrong:** lxml writes LF line endings by default; some Nuendo-saved `.nlpr` files use CRLF (Windows) and some use bare CR (classic Mac style, per spec line 191). Nuendo's parser appears lenient (it reads both), but it's worth verifying.

**Why it happens:** Spec line 191: *"the McKesson file uses CRLF, the others use bare CR (classic Mac style). Both are accepted by Nuendo Live."* So Nuendo Live 3 reads both — and presumably LF too — but the spec doesn't explicitly say LF works.

**How to avoid:**
1. Ship lxml default output (LF) and verify in HUMAN-UAT (open in Nuendo Live 3).
2. If LF fails, post-process: `body.replace(b'\n', b'\r\n')` to write CRLF. Or use `etree.tostring(..., method='xml').replace(b'\n', b'\r\n')`.
3. The XML declaration: lxml emits `<?xml version='1.0' encoding='utf-8'?>` (lowercase) when called with `encoding='utf-8'`. Nuendo's hand-generated files may use uppercase `UTF-8`. If round-trip fails, post-process the first line: `body.replace(b"encoding='utf-8'", b'encoding="UTF-8"', 1)` — note lxml emits single quotes; real files use double quotes. Cosmetic difference unless Nuendo's parser is strict.

**Warning signs:** Nuendo Live 3 refuses to open the file with a parse error. The HUMAN-UAT step (spec lines 305-309) catches this. The fix is downstream of the test result — start with lxml defaults, escalate to CRLF/encoding-case if needed.

`[VERIFIED for lxml's default output; UNVERIFIED for Nuendo Live 3's tolerance — HUMAN-UAT confirms]`

### Pitfall 9: Two-name-write per track

**What goes wrong:** Exported track shows the right name in Nuendo's mixer but the wrong name in the inspector (or vice versa).

**Why it happens:** Spec lines 213, 228-230 show two name elements per track:
1. **Outer:** `<obj class="MListNode" ...>` → `<string name="Name" value="{track_label}" wide="true"/>` — this is the track's display name.
2. **Inner:** `<obj class="MAudioTrack" ...>` → `<member name="DeviceAttributes">` → `<member name="Name">` → `<string name="String" value="{track_label}" wide="true"/>` — Nuendo expects this to match the outer.

Both must be set, and to the same value. NLP-03 verifies this.

**How to avoid:** In `_set_names(new_track, label)`, locate both elements and set both. Recommended XPath shapes:
- Outer: `new_track.find("./obj[@class='MListNode']/string[@name='Name']")`
- Inner: `new_track.find(".//obj[@class='MAudioTrack']//member[@name='DeviceAttributes']/member[@name='Name']/string[@name='String']")`

**Warning signs:** Tracks display correctly in mixer but show wrong name in Track Inspector when selected.

`[CITED: spec lines 213, 228-230]`

## Code Examples

### Reverse-Lookup Color Name from Hex (D-04 step 1)

```python
# Source: planner/utils/reaper_export.py:26-37 + D-04 reverse-lookup rule.
# Build once at module load.
from planner.utils.reaper_export import YAMAHA_TO_HEX

_HEX_TO_YAMAHA_NAME = {
    hex_val.lower(): name
    for name, hex_val in YAMAHA_TO_HEX.items()
    if hex_val is not None  # skip 'Off' (None) and 'White' (None)
}
# Result: {'#ff0000': 'Red', '#ff8800': 'Orange', '#ffdd00': 'Yellow',
#          '#33cc33': 'Green', '#00bbdd': 'Sky Blue', '#3366ff': 'Blue',
#          '#9933ff': 'Purple', '#ff33aa': 'Pink'}
```

### YAMAHA_TO_FARB Table (D-07)

```python
# Source: D-07 locked entries. Yamaha-name → Farb-int. 'Off' and 'White'
# absent from the dict — caller treats KeyError or .get() returning None as
# "omit Farb" per D-05.
YAMAHA_TO_FARB = {
    'Red':      0,
    'Orange':   1,
    'Yellow':   2,
    'Green':    5,
    'Sky Blue': 8,
    'Blue':     10,
    'Purple':   12,
    'Pink':     14,
    # 'Off' and 'White' intentionally omitted -> .get(name) returns None ->
    # exporter strips the <int name='Farb' .../> element from the deep-copy.
}
```

### Apply Farb / Strip Farb on Deep-Copied Track

```python
# Source: D-05 (no palette match → omit Farb); spec lines 220-221.
def _apply_farb(new_track, yamaha_name):
    """Set Farb to the mapped index, or remove the element entirely.

    new_track: deepcopy of the seed MAudioTrackEvent.
    yamaha_name: str palette name (e.g. 'Red') or None.
    """
    farb = new_track.find(".//member[@name='Additional Attributes']"
                          "/int[@name='Farb']")
    if yamaha_name is None or yamaha_name not in YAMAHA_TO_FARB:
        # D-05: no recognized palette color → remove Farb so Nuendo uses
        # default appearance.
        if farb is not None:
            farb.getparent().remove(farb)
        return
    if farb is None:
        # Template didn't have a Farb in its seed — add one. Place it as the
        # first child of <member name="Additional Attributes">. Note: if
        # Charlie's hand-generated template has the seed track colored (e.g.
        # default red), Farb will be present and we just mutate it.
        attrs = new_track.find(".//member[@name='Additional Attributes']")
        if attrs is None:
            raise ExportTemplateError(
                'Template missing Additional Attributes member'
            )
        farb = etree.SubElement(attrs, 'int', {'name': 'Farb'})
    farb.set('value', str(YAMAHA_TO_FARB[yamaha_name]))
```

### Sequential ID Allocator

```python
# Source: D-08 — start at max(existing) + 1000.
def _scan_max_id(root):
    """Find the largest integer ID anywhere in the document."""
    ids = []
    # All elements with an ID attribute (covers <obj ID="..."/> etc).
    for elem in root.xpath("//*[@ID]"):
        try:
            ids.append(int(elem.get('ID')))
        except (TypeError, ValueError):
            pass
    # All <int name='RuntimeID' value='...'> and <int name='ID' value='...'>.
    for elem in root.xpath(
        "//int[@name='RuntimeID' or @name='ID']"
    ):
        try:
            ids.append(int(elem.get('value')))
        except (TypeError, ValueError):
            pass
    return max(ids) if ids else 0


def _replace_all_ids(new_track, next_id):
    """Replace every ID attribute and RuntimeID/ID int value in new_track.

    Returns the next available id after consuming for this track.
    """
    # @ID attributes
    for elem in new_track.xpath(".//*[@ID]"):
        elem.set('ID', str(next_id))
        next_id += 1
    # The new_track root itself
    if new_track.get('ID') is not None:
        new_track.set('ID', str(next_id))
        next_id += 1
    # <int name='RuntimeID' .../> children
    for elem in new_track.xpath(".//int[@name='RuntimeID' or @name='ID']"):
        elem.set('value', str(next_id))
        next_id += 1
    return next_id
```

### Set Channel ID (per-track index)

```python
# Source: spec lines 224, 292 — Channel ID is the 1-based track index.
def _set_channel_id(new_track, index_1_based):
    """Set <int name='Channel ID' value='N'/> inside MAudioTrack."""
    ch = new_track.find(".//obj[@class='MAudioTrack']/int[@name='Channel ID']")
    if ch is None:
        raise ExportTemplateError('Template MAudioTrack missing Channel ID')
    ch.set('value', str(index_1_based))
```

### ID-Uniqueness Test (D-09 — the ONE automated assertion)

```python
# Source: planner/tests/test_nuendo_live_export.py (NEW).
# This is the single automated test the phase ships. Manual round-trip
# is HUMAN-UAT.
from io import BytesIO
from django.test import TestCase
from lxml import etree

class NuendoLiveExportIdUniquenessTests(TestCase):
    """D-09: every ID attribute and RuntimeID value in the exported .nlpr
    is unique within the document. Verifies NLP-06 directly.
    """

    @classmethod
    def setUpTestData(cls):
        # Build a session with N enabled tracks spanning all source types.
        # (Use the same _build_session helper pattern as
        # test_reaper_export.py's _SessionFixtureMixin.)
        ...

    def test_ids_unique(self):
        body = build_nlpr(self.session)
        root = etree.fromstring(body)
        ids = []
        for elem in root.xpath("//*[@ID]"):
            ids.append(elem.get('ID'))
        for elem in root.xpath(
            "//int[@name='RuntimeID' or @name='ID']"
        ):
            ids.append(elem.get('value'))
        self.assertEqual(
            len(set(ids)), len(ids),
            f'Found {len(ids) - len(set(ids))} duplicate IDs in export',
        )
```

**Test fixture strategy (Wave 1 vs Wave 2):** Wave 1 needs a Python-generated **minimal fake** `.nlpr` template — just enough structure to satisfy `_load_template()` (a root, a `MFolderTrack` named "Audio", a seed `MAudioTrackEvent` with inner `MListNode`/`MAudioTrack`/`DeviceAttributes`, plus one `Farb` and one `RuntimeID`). This fake lives in `planner/tests/fixtures/` and gets `monkeypatch`-injected into the module-level `_TEMPLATE_PATH` for the unit test. The real Charlie-generated fixture (D-02) lands separately as the production artifact at `planner/data/multitrack/nuendo_live_3_template.nlpr` — used by manual HUMAN-UAT, not by the automated test.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `xml.etree.ElementTree` (stdlib) | `lxml.etree` | 2010s onwards | lxml became the de facto standard for production XML work. Stdlib still ships but is recommended only for read-only / trivial output. |
| Yamaha Console Extension protocol | ShowStack-side `.nlpr` template-injection | Phase 4 ships | Works regardless of Dante topology; pre-fills track names/colors from console label data. See marketing positioning in `multitrack_session_builder_spec.md:388-393`. |

**Deprecated/outdated:**
- N/A — Phase 4 uses current-generation libraries throughout.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Nuendo Live 3 accepts LF line endings on import. (Spec confirms CR and CRLF; LF is inferred-not-stated.) | Pitfall 8 | Medium — if LF rejected, post-process to CRLF. Caught by HUMAN-UAT. |
| A2 | Nuendo Live 3 accepts lowercase `encoding='utf-8'` in XML declaration. Real files may use `UTF-8`. | Pitfall 8 | Low — XML spec is case-insensitive for the encoding name; nearly certain Nuendo parses both. |
| A3 | Surrogate-pair / supplementary-plane characters in track labels render correctly in Nuendo's UTF-16 model. | Pitfall 4 | Low for typical use (engineer labels are usually plain ASCII). HUMAN-UAT confirms. |
| A4 | `xmltodict` is unsuitable because dict-roundtrip loses element ordering. | Standard Stack §Alternatives | Low — lxml is clearly the correct tool per spec; xmltodict wasn't a serious candidate anyway. |
| A5 | Nuendo's `<int name='Farb'/>` element specifically — re-adding it as a `SubElement` after removal places it correctly. The spec doesn't show the exact child order within `<member name='Additional Attributes'>`. | Code Examples §Apply Farb | Medium — if Nuendo cares about child order inside `Additional Attributes` (i.e. `Farb` must come before `Eths`), `SubElement` appends to the end and would put `Farb` AFTER `Eths`. Mitigation: if the seed track always has a Farb (Charlie-generated default red), we never hit the SubElement path; we always mutate. Verify in D-02 that the hand-generated template has a Farb in its seed track. |
| A6 | Sequential allocator starting at `max+1000` produces IDs Nuendo accepts. Nuendo's max ID range is implicitly assumed to be 32-bit signed (~2.1B). Real templates' max-ID values are not yet measurable (need Charlie's fixture). | D-08 / Pitfall 7 | Very low — Nuendo's own files use values in the millions or low billions; `max+1000+N` for N up to ~200 tracks stays well under any conceivable cap. |
| A7 | `_safe_filename()` from `planner/views.py:6856` produces ASCII-only output suitable for Nuendo file names. Nuendo Live 3's tolerance for Unicode in file paths on Windows: assumed equivalent to any Windows app (works for typical Unicode; legacy NTFS APIs cap at 255 chars). | Standard Stack §Reuse | Low — `_safe_filename` strips to ASCII alphanumeric + `-_`, which is safe everywhere. |

**If a claim moves from `[ASSUMED]` to `[VERIFIED]` during execution:** update this log and remove the row.

## Open Questions

1. **What is the exact maximum ID value in the Charlie-generated template?**
   - What we know: Spec line 290 says "Random unique ints work"; D-08 specifies `max+1000` allocator base.
   - What's unclear: Won't know until Charlie commits the real fixture (D-02). Could be anywhere from a few thousand to tens of millions.
   - Recommendation: Allocator's logic is `max+1000` regardless of magnitude — no plan change needed. Document expected scan result in a comment when Wave 2 lands.

2. **Does the Charlie-generated template have a `<Farb>` in its seed track?**
   - What we know: D-02 says "1 default audio track named `'Audio 01'`. No color." But "default audio track" in Nuendo Live 3 actually has Farb=0 (red) by default — verified in spec lines 250-269.
   - What's unclear: Whether Charlie's freshly-saved empty session writes Farb=0 explicitly or omits it.
   - Recommendation: Plan for both cases. `_apply_farb` handles "Farb present in seed" (mutate value) and "Farb absent" (SubElement to add). If the absent case adds Farb in wrong sibling order (Pitfall A5), plan a small post-processing step. **Worth grepping the committed fixture for `Farb` once it lands.**

3. **Does Nuendo Live 3 accept LF-only line endings?**
   - What we know: Spec line 191 — real files use CRLF or bare CR. LF not mentioned.
   - What's unclear: Whether Nuendo's parser is fully lenient or strict.
   - Recommendation: Ship lxml default (LF). If HUMAN-UAT fails open-in-Nuendo with a parse error, escalate to CRLF post-processing. Don't pre-emptively post-process — keep the simple path until evidence forces the complex path.

4. **Should the toolbar's `mts-btn-success` class be reused, or is there a Nuendo-specific brand color?**
   - What we know: D-13 locks reuse of existing styles — `mts-btn mts-btn-success` for the primary download.
   - What's unclear: Whether Charlie or beta users will later want visual differentiation between Reaper and Nuendo buttons.
   - Recommendation: Locked. Defer any visual differentiation to a polish phase.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.x | Django + lxml | ✓ | Python 3.12.x (Railway default) | — |
| Django 5.x | All views, forms, templates | ✓ | 5.2.4 (per requirements.txt) | — |
| `lxml` | Exporter | ✗ | — | **Blocking.** Must add to `requirements.txt`. Pre-built manylinux wheels available for Python 3.9-3.12 — no compilation needed on Railway. `[VERIFIED: pypi.org/project/lxml]` |
| `copy` (stdlib) | Deep-copy seed track | ✓ | stdlib | — |
| `pathlib` (stdlib) | Fixture path resolution | ✓ | stdlib | — |
| `planner/data/multitrack/nuendo_live_3_template.nlpr` | Production exporter | ✗ | — | **Wave-2 blocker.** Charlie generates on Windows + Nuendo Live 3 per D-02. Wave 1 (exporter logic + unit test) can land first using a Python-generated fake fixture; Wave 2 (view wiring + E2E manual UAT) waits on the real file. D-03 ensures graceful runtime degradation if the fixture is missing in production. |
| Nuendo Live 3 on Windows | HUMAN-UAT round-trip | ✓ (Charlie's machine) | 3.0.0 / WIN64 | — — but this is **manual UAT only**, never runs in CI. |

**Missing dependencies with no fallback:**
- `lxml` — add to `requirements.txt`, pinned `~=5.3.0`.

**Missing dependencies with fallback:**
- Production template fixture — handled gracefully at runtime (D-03 missing-fixture banner); Wave 1 substitutes a generated fake for unit tests.

## Security Domain

Phase 4 inherits the project's security posture. No new attack surface vs Phase 1 once the auth decorator matches.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `@staff_member_required` on the download view (matches Phase 1 `multitrack_export_rpp`). |
| V3 Session Management | yes (inherited) | Django session middleware + `CurrentProjectMiddleware` for project scope. Phase 4 adds no new session logic. |
| V4 Access Control | yes | Project-scope filter `MultitrackSession.objects.filter(id=session_id, project=current_project)` — IDOR-safe combined filter (same as Phase 1). Viewer-block N/A on read-only download. |
| V5 Input Validation | yes | `session_id` is `<int>` in the URL path — Django coerces. Track labels read from DB are TrustedSource (already validated at write time by Phase 1's editor forms / AJAX endpoints). XML-escape via lxml `.set()` per Pitfall 1. Filename via `_safe_filename` to ASCII-only (header injection / path traversal closed). |
| V6 Cryptography | no | No crypto in this phase. |

### Known Threat Patterns for {Django 5.x + lxml + XML download}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XML External Entity (XXE) injection on parse | Tampering / Information Disclosure | We **only parse a known fixture** (`planner/data/multitrack/nuendo_live_3_template.nlpr`) committed to git — no user-supplied XML enters lxml. Threat does not apply. Defense: explicit `etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)` — defensible polish even though the input is trusted. `[CITED: lxml.de/parsing.html]` |
| Path traversal on Content-Disposition filename | Tampering | `_safe_filename` strips to ASCII alphanumeric + `-_` — defeats `../`, NUL, and CRLF header injection. Reused verbatim from Phase 1. `[VERIFIED: planner/views.py:6856-6868]` |
| Header injection via session name | Tampering / Privilege Escalation | `_safe_filename` defeats CR/LF in the filename component. `[VERIFIED]` |
| IDOR on `session_id` URL param | Elevation of Privilege | Combined-filter query `filter(id=session_id, project=current_project)` returns None for any session not in the user's current project. **Returns 302 redirect to dashboard rather than 404** — see Phase 1 `multitrack_export_rpp` for the established pattern. |
| Cross-tenant data leak via XML content | Information Disclosure | All track data already passes through `MultitrackTrack.resolved_*` properties that respect the session's project scope (the queryset already filtered by `project=current_project`). Exporter is a pure function of `session`; no risk of leakage. |
| Denial-of-service via huge session | Resource Exhaustion | A 1000-track session with deep-copied subtrees would peak at maybe 30-50MB RAM during build. Acceptable for a one-engineer-at-a-time download endpoint on Railway. No explicit limit needed for v4.0. Could revisit if abuse surfaces. `[ASSUMED]` |
| File-on-disk fixture tampering | Integrity | Fixture is committed to git; Railway deploy is reproducible from `main`. Threat = unauthorized commit, mitigated by GitHub branch protections (out of scope for this phase). |

## Sources

### Primary (HIGH confidence)
- `multitrack_session_builder_spec.md` (repo root) — canonical spec, especially:
  - Lines 187-310 (`.nlpr` format details)
  - Lines 241-269 (Farb / UColorSet decoded table)
  - Lines 273-284 (Yamaha → Nuendo color mapping)
  - Lines 305-310 (Round-trip test plan)
  - Lines 357-362 (Phase 4 task list)
- `.planning/phases/04-nuendo-live-export/04-CONTEXT.md` — locked decisions D-01..D-14
- `planner/utils/reaper_export.py` (lines 1-236) — structural mirror; specifically YAMAHA_TO_HEX (26-37), `_sanitize_name` (76-85), `_ordered_enabled_tracks` (134-169)
- `planner/views.py:6845-6961` — `multitrack_export_rpp` + `multitrack_export_rtracktemplate` (view layer to mirror)
- `planner/views.py:6856-6868` — `_safe_filename` helper (reuse verbatim)
- `planner/views.py:6871-6872` — `_has_enabled_tracks` helper (reuse verbatim)
- `planner/views.py:5892-5972` — `_editor_context` shared helper
- `planner/models.py:758-768` — `YAMAHA_COLOR_CHOICES`
- `planner/models.py:845, 883, 902, 918` — channel-level `color` fields (Phase 2 D-07)
- `planner/models.py:978-981` — `MultitrackSession.TARGET_DAW_CHOICES` (Nuendo Live already in model)
- `planner/models.py:1038-1118` — `MultitrackTrack` (host class for `resolved_yamaha_name` property)
- `planner/models.py:1061-1066` — `resolved_source` property (D-04 step 2 dependency)
- `planner/forms.py:1128-1217` — `MultitrackSessionForm` (three gates to remove)
- `planner/templates/planner/multitrack/new_session.html:63-81` — `target_daw` radio block (static gate to remove)
- `planner/templates/planner/multitrack/editor.html:75-82` — toolbar action block (add third button)
- `planner/urls.py:138-139` — Reaper URL patterns (Nuendo route slots in immediately after)
- `planner/tests/test_reaper_export.py` — pattern for test structure (SimpleTestCase + TestCase mix)
- `.planning/phases/01-core-sessions-track-editor-reaper-export/01-CONTEXT.md` — Phase 1 decisions Phase 4 builds on (D-06, D-13, D-14)
- `.planning/phases/01-core-sessions-track-editor-reaper-export/01-REVIEW-FIX.md` — confirms CR-01/CR-02 scope was AJAX mutate endpoints, NOT download views

### Secondary (MEDIUM confidence — verified against official sources)
- `https://lxml.de/tutorial.html` — XPath, namespace handling, deepcopy mechanics. Verified for `parse`/`tostring`/`SubElement`/`Element.set()` API used in this phase.
- `https://lxml.de/parsing.html` — XMLParser configuration for XXE defense (if planner adds defensible polish).
- `https://pypi.org/project/lxml/` — current version 6.1.0, also 5.3.x stable line. Pinning `~=5.3.0` confirmed compatible with Python 3.9-3.12.

### Tertiary (LOW confidence — assumptions flagged)
- Nuendo Live 3's tolerance for LF line endings — no public spec, A1 assumption.
- Nuendo Live 3's parser strictness on lowercase vs uppercase `utf-8` encoding name — A2 assumption.
- Nuendo's UTF-16 surrogate-pair behavior for track labels — A3 assumption.
- Nuendo's tolerance for `Farb` element ordering inside `Additional Attributes` — A5 assumption.

## Metadata

**Confidence breakdown:**
- Standard stack (lxml): HIGH — spec explicitly mandates lxml, pypi confirms current stable.
- Architecture (template-injection): HIGH — spec lines 196-205 dictate the exact algorithm.
- Codebase pattern mirroring (Phase 1 reuse): HIGH — files read and confirmed line-by-line.
- Auth decorator (`@staff_member_required`): HIGH — `planner/views.py:6875, 6922` directly confirmed; Phase 1 review fix scope verified.
- Form/template gate locations (Pitfall 6): HIGH — three exact line ranges identified.
- ID/RuntimeID semantics (D-08): MEDIUM — spec line 290 confirms uniqueness requirement; max-value scan strategy is reasoning, not verified against real fixture.
- LF/CRLF tolerance (Pitfall 8): LOW — assumption-based, HUMAN-UAT-resolved.
- `Farb` element re-add ordering (A5): LOW — depends on Charlie's fixture; verify after D-02 lands.
- Color resolution order (D-04): HIGH — fields read directly from Phase 2 models.

**Research date:** 2026-05-13
**Valid until:** 2026-06-12 (30 days — Django/lxml are stable; the only volatile input is Charlie's hand-generated fixture, which lands during Wave 1/2 of execution)
