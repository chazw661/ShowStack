# Phase 04: Nuendo Live Export — Pattern Map

**Mapped:** 2026-05-13
**Files analyzed:** 9 (3 new + 6 modified, plus `requirements.txt`)
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `planner/utils/nuendo_live_export.py` (NEW) | utility / pure exporter | transform (in-memory) | `planner/utils/reaper_export.py` | exact (sibling exporter, same module dir, same trust-boundary contract) |
| `planner/data/multitrack/nuendo_live_3_template.nlpr` (NEW) | data fixture / opaque vendor binary | file-I/O (read at runtime) | `planner/data/csv_fixtures/CL_Editor_Blank_Export/` + `planner/data/comm_config/pouchdb_factory/` | exact (both established by Phases 2 and Comm Config as bundled vendor-binary references) |
| `planner/tests/test_nuendo_live_export.py` (NEW) | test | transform / assertion | `planner/tests/test_reaper_export.py` | exact (sibling exporter, reuses `_SessionFixtureMixin` shape) |
| `planner/models.py` (MOD) — add `MultitrackTrack.resolved_yamaha_name` `@property` | model property | CRUD-adjacent (read-only ORM) | `MultitrackTrack.resolved_label` / `resolved_color` / `resolved_dante_number` at `planner/models.py:1068-1106` | exact (same class, same `@property` style, no migration) |
| `planner/views.py` (MOD) — add `multitrack_export_nlpr` | controller / download view | request-response (file download) | `multitrack_export_rpp` at `planner/views.py:6875-6919` and `multitrack_export_rtracktemplate` at `:6922-6961` | exact (same view, same auth gate, same fallback) |
| `planner/urls.py` (MOD) — add `.nlpr` route | route | request-response | `planner/urls.py:138-139` (existing `.rpp` / `.rtracktemplate` routes) | exact (same path shape, same `<int:session_id>` capture) |
| `planner/templates/planner/multitrack/editor.html` (MOD) — add 3rd toolbar button | template | request-response (link) | Two existing `<a class="mts-btn ...">` anchors at `editor.html:77-81` | exact (same toolbar div, same class grammar `mts-btn mts-btn-success` / `mts-btn-secondary`) |
| `planner/templates/planner/multitrack/new_session.html` (MOD) — REMOVE static disabled radio | template | request-response (form) | The dynamic radio loop at `new_session.html:66-71` (what stays after deletion) | exact (deletion only; leaves dynamic loop unchanged) |
| `planner/forms.py` (MOD) — REMOVE 2 gates | form | validation | The 3-place gate pattern at `planner/forms.py:1192-1217` (what gets removed) | self-referential (the gate code itself documents what to delete) |
| `requirements.txt` (MOD) — add `lxml~=5.3.0` | config | package-management | `requirements.txt` line-list (e.g. `Django==5.2.4`) | exact (one-line addition to flat list) |

## Pattern Assignments

### `planner/utils/nuendo_live_export.py` (NEW, utility / pure exporter)

**Analog:** `planner/utils/reaper_export.py` (236 lines, same module dir, same trust-boundary contract)

**Module-header / trust-boundary pattern** (`planner/utils/reaper_export.py:1-13`):
```python
"""Reaper .RPP and .RTrackTemplate exporter for MultitrackSession.

References:
- Reaper RPP format verified from CharlesHolbrow/rppp fixtures + LASS-2 RTrackTemplate
- PEAKCOL bit layout verified across 5 sources: ...
- Phase 1 of v2.0 multitrack module — see .planning/phases/01-.../01-RESEARCH.md

Trust boundary note (T-02-02): this module does NOT filter sessions by
project. The caller (Plan 04 view) is responsible for verifying that the
session passed in belongs to the current project — this module trusts its
input and is intentionally a pure string-builder with no DB writes.
"""
```
Phase 4 mirrors this docstring shape verbatim — change "string-builder" to "bytes-builder", reference RESEARCH.md instead of Reaper-format sources, keep the trust-boundary paragraph intact (CONTEXT.md §"Established Patterns" makes this binding).

**Palette table pattern** (`planner/utils/reaper_export.py:26-37`):
```python
YAMAHA_TO_HEX = {
    'Off':      None,        # → omit PEAKCOL or write 16576
    'Red':      '#FF0000',
    'Orange':   '#FF8800',
    'Yellow':   '#FFDD00',
    'Green':    '#33CC33',
    'Sky Blue': '#00BBDD',
    'Blue':     '#3366FF',
    'Purple':   '#9933FF',
    'Pink':     '#FF33AA',
    'White':    None,        # → use DAW default (Reaper omits PEAKCOL)
}
```
Phase 4 declares `YAMAHA_TO_FARB` (D-07 locked entries) in the analogous spot — module-level, after the docstring, before the public builders. Per RESEARCH.md Code Examples §"YAMAHA_TO_FARB Table", `'Off'` and `'White'` are intentionally **omitted from the dict** so `.get(name)` returns `None` → exporter strips the `<int name='Farb' .../>` element.

**Sanitization helper** (`planner/utils/reaper_export.py:76-85`):
```python
def _sanitize_name(name):
    """Sanitize a track label for the Reaper NAME token.

    Replaces double-quote with single-quote (Reaper NAME accepts either an
    unquoted single word or a "..."-wrapped string with NO internal `"`).
    Returns '(untitled)' for empty / None.
    """
    if not name:
        return '(untitled)'
    return name.replace('"', "'").strip() or '(untitled)'
```
**Anti-pattern warning (RESEARCH Pitfall §"Anti-Patterns to Avoid"):** **Do NOT reuse `_sanitize_name` for Nuendo.** That helper substitutes `"` → `'` for Reaper's bare-quote wrapping. Nuendo uses proper XML attribute escaping — lxml's `.set('value', user_string)` handles `<`, `>`, `&`, `"`, `'` automatically. Phase 4 needs a *different* helper (or none): strip control chars (`\x00-\x08\x0B\x0C\x0E-\x1F`) per RESEARCH Pitfall 4 — lxml raises `ValueError: All strings must be XML compatible` on NUL bytes.

**Track ordering — REUSED VERBATIM** (`planner/utils/reaper_export.py:134-169`):
```python
def _ordered_enabled_tracks(session):
    """Return a list of enabled tracks ordered per session.track_order_mode.

    'console' — by source-type priority then source channel number ascending.
                Manual tracks sort last (by track_number).
    'dante'   — by resolved_dante_number ascending. Tracks without dante
                number sort after those with a number, by track_number.
                Manual tracks sort last.
    'custom'  — by track_number ascending (engineer's drag order).
    """
```
Phase 4 imports this function: `from planner.utils.reaper_export import _ordered_enabled_tracks`. Track ordering is universal across DAW formats (CONTEXT.md §"Reusable Assets"). Re-importing is preferable to extracting to a shared helper for v4.0 (planner's discretion in CONTEXT.md, but re-import is the lower-risk path).

**Public-builder pattern** (`planner/utils/reaper_export.py:203-220`):
```python
def build_rpp(session):
    """Generate a complete Reaper .RPP file as a string.

    Tracks filtered to enabled=True and ordered per session.track_order_mode.
    """
    enabled_tracks = _ordered_enabled_tracks(session)
    out = StringIO()
    out.write(f'<REAPER_PROJECT 0.1 "7.0/AudiopatchExporter" {int(time.time())}\n')
    ...
    return out.getvalue()
```
Phase 4's `build_nlpr(session)` returns **`bytes`** (not `str`) — `etree.tostring(root, xml_declaration=True, encoding='utf-8')` produces bytes. The full algorithm sits at RESEARCH.md §"Pattern 1: Template-Injection Mutation Loop" (load template → deepcopy seed N times → mutate names/IDs/Channel ID/Farb → append clones → remove seed → tostring).

**Error handling pattern:** Phase 4 introduces an `ExportTemplateError` exception class (named per RESEARCH.md Pattern 1) raised when the bundled fixture is missing, malformed, or has 0 / >1 Audio MFolderTrack. The view catches this and renders `editor.html` with `export_error=` — see Pattern Assignment for `planner/views.py` below.

---

### `planner/data/multitrack/nuendo_live_3_template.nlpr` (NEW, data fixture)

**Analogs (two):**
- `planner/data/csv_fixtures/CL_Editor_Blank_Export/` (Phase 2 CSV fixture directory — bundled Yamaha vendor CSVs)
- `planner/data/comm_config/pouchdb_factory/` (Comm Config — opaque Clear-Com PouchDB factory binaries)

Both analogs establish the convention: a `planner/data/<module>/` subdirectory holds vendor-binary references committed to git, read-only at runtime via `pathlib.Path(__file__).parent.parent / 'data' / ...` relative paths (RESEARCH.md §"Don't Hand-Roll" row 5).

**No code excerpt — this is a Charlie-generated binary fixture.** Generation contract is fully specified in CONTEXT.md D-02:
- Exactly 1 default audio track named `"Audio 01"` inside the `Audio` MFolderTrack.
- Stock 120 BPM, 48 kHz, no markers, no signature changes, no tempo changes.
- Saved on Windows so `Application Version` block reports `Platform="WIN64"`.
- No audio interface routings beyond Nuendo's defaults.

**Wave-1 fake template (for unit tests):** Per RESEARCH.md §"Test fixture strategy (Wave 1 vs Wave 2)", a Python-generated minimal fake `.nlpr` lives in `planner/tests/fixtures/` (directory already exists) and is `monkeypatch`-injected into the module-level `_TEMPLATE_PATH` for the ID-uniqueness unit test. This unblocks Wave 1 before Charlie's real fixture lands.

---

### `planner/tests/test_nuendo_live_export.py` (NEW, test)

**Analog:** `planner/tests/test_reaper_export.py` (sibling exporter test file)

**File-header pattern** (`planner/tests/test_reaper_export.py:1-19`):
```python
"""Tests for planner.utils.reaper_export.

Covers every assertion in the Plan 01-02 <behavior> block:
  - hex_to_peakcol: PEAKCOL packing formula and fallback for malformed input
  - _sanitize_name: NAME-token sanitization (Pitfall 8)
  - build_rpp / build_rtracktemplate: full RPP / RTrackTemplate string output
  - track_order_mode dispatch (custom / console / dante)
  - enabled-only filtering

Combines pure-function unit tests (SimpleTestCase, no DB) with
integration tests against real ORM-backed MultitrackSession + Track rows
(TestCase, in-memory SQLite from `manage.py test`'s test database).
...
"""
```
Phase 4's test file ships **ONE** automated assertion per D-09 — the ID/RuntimeID uniqueness check. Header narrows the docstring to that single test plus the "everything else is HUMAN-UAT" note.

**Imports pattern** (`planner/tests/test_reaper_export.py:21-42`):
```python
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from planner.models import (
    Console,
    ConsoleAuxOutput,
    ConsoleInput,
    ConsoleMatrixOutput,
    ConsoleStereoOutput,
    MultitrackSession,
    MultitrackTrack,
    Project,
)
from planner.utils.reaper_export import (
    PEAKCOL_NO_COLOR,
    YAMAHA_TO_HEX,
    _ordered_enabled_tracks,
    _sanitize_name,
    build_rpp,
    build_rtracktemplate,
    hex_to_peakcol,
)
```
Phase 4 swaps the bottom block for `from planner.utils.nuendo_live_export import build_nlpr` plus `from lxml import etree`.

**Reusable session-fixture mixin** (`planner/tests/test_reaper_export.py:158-186`):
```python
class _SessionFixtureMixin:
    """Shared fixture builder. Not a TestCase itself (no test methods)."""

    @classmethod
    def _build_user(cls):
        return User.objects.create_user(
            username='reaper-tester',
            email='tester@example.com',
            password='test-password-123',
        )

    @classmethod
    def _build_project(cls, user):
        return Project.objects.create(name='Reaper Test Show', owner=user)

    @classmethod
    def _build_console(cls, project):
        return Console.objects.create(project=project, name='Test CL5')

    @classmethod
    def _build_session(cls, project, console, *, mode='console', name='Main Mix'):
        return MultitrackSession.objects.create(
            project=project,
            console=console,
            name=name,
            target_daw='reaper',
            feed_source='console_dante',
            track_order_mode=mode,
        )
```
Phase 4 either duplicates this mixin (faster) or imports it from `test_reaper_export` (cleaner). Either is acceptable — planner picks. Test target should set `target_daw='nuendo_live'` for consistency (though the exporter is target-agnostic per D-11).

**Test body — the ONE assertion (RESEARCH.md Code Examples §"ID-Uniqueness Test"):**
```python
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

---

### `planner/models.py` — add `MultitrackTrack.resolved_yamaha_name` `@property` (~line 1088)

**Analog:** Three sibling `@property` methods on the same class, immediately adjacent — `resolved_label` (`:1068-1086`), `resolved_color` (`:1088-1091`), `resolved_dante_number` (`:1093-1105`).

**Pattern to mirror** (`planner/models.py:1060-1106`):
```python
@property
def resolved_source(self):
    """D-14: return the live channel-model instance, or None for manual / orphan."""
    model = _source_model_for(self.source_type)
    if model is None or self.source_id is None:
        return None
    return model.objects.filter(pk=self.source_id).first()

@property
def resolved_label(self):
    """D-14: label_override → channel name field → channel number → '(untitled)'."""
    if self.label_override:
        return self.label_override
    src = self.resolved_source
    if src is None:
        return '(untitled)'
    ...

@property
def resolved_color(self):
    """D-14 / D-06: color_override only in Phase 1 (Phase 5 may extend)."""
    return self.color_override or None

@property
def resolved_dante_number(self):
    """D-14: int Dante stream number across all source types, or None.
    ConsoleInput.dante_number is CharField; the other three are IntegerField —
    normalise both via int() with try/except.
    """
    src = self.resolved_source
    if src is None or not getattr(src, 'dante_number', None):
        return None
    try:
        return int(src.dante_number)
    except (ValueError, TypeError):
        return None
```

**Insertion point:** After `resolved_dante_number` at `:1105`, before `def __str__` at `:1107`. Maintains the "all resolved_* properties grouped together" convention.

**Phase 4 implementation (RESEARCH.md Code Examples §"Reverse-Lookup Color Name from Hex"):**
```python
# Module-level reverse lookup, built once near the top of models.py
# (or imported from a local helper near the property — planner picks).
from .utils.reaper_export import YAMAHA_TO_HEX
_HEX_TO_YAMAHA_NAME = {
    hex_val.lower(): name
    for name, hex_val in YAMAHA_TO_HEX.items()
    if hex_val is not None
}

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
        return None  # D-05: hex override but not a palette match → omit Farb
    src = self.resolved_source
    if src is None:
        return None
    color = getattr(src, 'color', None)
    if not color or color == 'Off':
        return None
    return color
```
**Gotcha:** No migration. This is a `@property`, not a `models.Field()`. CLAUDE.md §"Active Work Queue" makes additive-migrations-only binding for beta data — Phase 4 ships zero migrations and is naturally compliant.

---

### `planner/views.py` — add `multitrack_export_nlpr` view (after line 6961)

**Analog:** `multitrack_export_rpp` at `planner/views.py:6875-6919` (preferred — most analogous flow including `build_rpp` body call).

**Section-header convention** (`planner/views.py:6845-6851`):
```python
# ──────────────────────────────────────────────────────────────────
# Multitrack — Reaper file-download views (Plan 01-04, Wave 3)
# Delegates RPP / RTrackTemplate body building to planner.utils.reaper_export
# (Plan 01-02). This view layer only handles HTTP response shape, filename
# sanitization (T-04-06 / T-04-12), and the no-enabled-tracks guard
# (T-04-13).
# ──────────────────────────────────────────────────────────────────
```
Phase 4 adds a parallel section header before the Nuendo view: *"Multitrack — Nuendo Live file-download view (Plan 04, Wave 2). Delegates .nlpr generation to planner.utils.nuendo_live_export."*

**Import pattern** (`planner/views.py:6853`):
```python
from .utils.reaper_export import build_rpp, build_rtracktemplate
```
Phase 4 adds: `from .utils.nuendo_live_export import build_nlpr, ExportTemplateError` next to (or below) this line.

**Full view pattern — verbatim adaptation of `multitrack_export_rpp`** (`planner/views.py:6875-6919`):
```python
@staff_member_required
def multitrack_export_rpp(request, session_id):
    """GET: download a Reaper .RPP file for this session (RPP-01..04).

    Returns text/plain attachment. Filename: <safe(session.name)>.RPP.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    session = MultitrackSession.objects.filter(
        id=session_id, project=current_project
    ).select_related('console').first()
    if not session:
        return redirect('planner:multitrack_dashboard')

    if not _has_enabled_tracks(session):
        # UI-SPEC error string verbatim. Render an HTML page (not a download).
        # Route through the shared _editor_context helper (defined in Plan 03)
        # so the editor template receives the full context contract ...
        enabled_tracks_qs = session.tracks.filter(enabled=True).order_by('track_number')
        return render(
            request,
            'planner/multitrack/editor.html',
            _editor_context(
                session,
                tracks=enabled_tracks_qs,
                current_project=current_project,
                export_error='This session has no enabled tracks. '
                             'Enable at least one track to export.',
                auto_open_picker=False,
            ),
        )

    body = build_rpp(session)
    response = HttpResponse(body, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="{_safe_filename(session.name)}.RPP"'
    )
    return response
```

**Phase 4 changes (RESEARCH.md Pattern 3):**
1. Function name: `multitrack_export_nlpr`.
2. Docstring: reference NLP-01..06 instead of RPP-01..04.
3. Wrap `body = build_nlpr(session)` in `try / except ExportTemplateError` and render `editor.html` with `export_error='Nuendo Live export is unavailable on this server — bundled template missing or malformed. Contact support.'` (D-03).
4. Response: `content_type='application/xml; charset=utf-8'` (NOT `text/plain`).
5. Filename: `f'attachment; filename="{_safe_filename(session.name)}.nlpr"'` — lowercase extension.

**Auth decorator decision (RESEARCH.md Pitfall 5 — VERIFIED):** Match `@staff_member_required`. Phase 1's CR-01/CR-02 retightened only AJAX *mutate* endpoints (`set_color`, `set_label`, `set_enabled`, `remove_track`, reorder — `planner/views.py:6697-6710` uses `@login_required` + `_multitrack_viewer_block`). Download views (`multitrack_export_rpp` and `multitrack_export_rtracktemplate`) **kept** `@staff_member_required` only. Document this with a comment referencing CR-01/CR-02.

**Reused helpers (verbatim, no copy):**
- `_safe_filename(name)` at `planner/views.py:6856-6868`.
- `_has_enabled_tracks(session)` at `planner/views.py:6871-6872`.
- `_editor_context(session, tracks=None, current_project=None, **extras)` at `planner/views.py:5892`.

---

### `planner/urls.py` — add `.nlpr` route (after line 139)

**Analog:** The existing `.rpp` / `.rtracktemplate` routes at `planner/urls.py:137-139`:
```python
# File downloads (Plan 04)
path('multitrack/<int:session_id>/export.rpp/', views.multitrack_export_rpp, name='multitrack_export_rpp'),
path('multitrack/<int:session_id>/export.rtracktemplate/', views.multitrack_export_rtracktemplate, name='multitrack_export_rtracktemplate'),
```

**Phase 4 addition (slot in at `:140`):**
```python
path('multitrack/<int:session_id>/export.nlpr/', views.multitrack_export_nlpr, name='multitrack_export_nlpr'),
```
Same `<int:session_id>` capture, same view-namespace pattern (`planner:multitrack_export_*`), same comment block — extend the existing `# File downloads (Plan 04)` comment to read `(Plan 04 + Plan 04-Phase 4)` or similar (planner's discretion).

---

### `planner/templates/planner/multitrack/editor.html` — add 3rd toolbar button (after line 81)

**Analog:** The two existing toolbar anchors at `editor.html:75-82`:
```html
<div class="mts-toolbar-actions">
  <button type="button" class="mts-btn mts-btn-secondary" onclick="mtsOpenPicker('inputs')">+ Add tracks</button>
  <a class="mts-btn mts-btn-success"
     href="{% url 'planner:multitrack_export_rpp' session.id %}">Export to Reaper (.RPP)</a>
  <a class="mts-btn mts-btn-secondary"
     href="{% url 'planner:multitrack_export_rtracktemplate' session.id %}"
     title="Reaper track template — import via Track menu › Insert track from template">Export to Reaper (Track Template)</a>
</div>
```

**Phase 4 addition (D-11, D-13):** Insert a third `<a>` immediately after the `.RTrackTemplate` anchor and before the closing `</div>`:
```html
<a class="mts-btn mts-btn-success"
   href="{% url 'planner:multitrack_export_nlpr' session.id %}">Export to Nuendo Live (.nlpr)</a>
```
**Pattern locked by D-13:** Reuse `mts-btn mts-btn-success` (primary success — same as `.RPP`). No new CSS classes for v4.0. All three buttons always render regardless of `session.target_daw` (D-11). Per RESEARCH.md Open Question #4, this is locked — no Nuendo-specific brand color.

---

### `planner/templates/planner/multitrack/new_session.html` — REMOVE static disabled radio (lines 72-78)

**Analog / target (the block to DELETE):**
```html
{# Nuendo Live disabled until Phase 4 ships — rendered statically (not in form choices) #}
<label class="mts-radio-option" title="Nuendo Live export ships in Phase 4">
  <input type="radio" disabled>
  <span class="mts-radio-label mts-radio-label--disabled">
    Nuendo Live <span class="mts-caption">(coming v2.0)</span>
  </span>
</label>
```

**Pattern that REMAINS** (`new_session.html:66-71` — the dynamic loop):
```html
<div class="mts-radio-group">
  {% for radio in form.target_daw %}
    <label class="mts-radio-option">
      {{ radio.tag }}
      <span class="mts-radio-label">{{ radio.choice_label }}</span>
    </label>
  {% endfor %}
```
After deletion, the dynamic `{% for radio in form.target_daw %}` loop renders both radios (Reaper + Nuendo Live) automatically — the model's `TARGET_DAW_CHOICES` at `planner/models.py:978-981` already lists both. **No template insertion** — pure deletion of lines 72-78.

---

### `planner/forms.py` — REMOVE 2 gates (lines 1192-1199 and 1209-1217)

**Analog / target — Pitfall 6 (RESEARCH.md) is the source of truth.** Phase 1 belt-and-suspenders-ed the gate three ways; Phase 4 removes all three.

**Gate 1 to DELETE — choices restriction** (`planner/forms.py:1192-1199`):
```python
# Disable Nuendo Live in Phase 1 (UI-SPEC: "(coming v2.0)").
# Restrict the field's choices so any submitted nuendo_live fails the
# built-in "Select a valid choice" validation. The template still
# renders a visible-but-disabled radio so users see it's coming.
# `clean_target_daw` remains as belt + suspenders.
self.fields['target_daw'].choices = [
    c for c in self.fields['target_daw'].choices if c[0] != 'nuendo_live'
]
```

**Gate 2 to DELETE — `clean_target_daw` method** (`planner/forms.py:1209-1217`):
```python
def clean_target_daw(self):
    """Phase 1 ships Reaper only; Nuendo Live arrives in Phase 4."""
    value = self.cleaned_data.get('target_daw')
    if value == 'nuendo_live':
        raise forms.ValidationError(
            'Nuendo Live export ships in v2.0 Phase 4. '
            'Pick Reaper for now.'
        )
    return value
```

**Gate 3 (already mapped in `new_session.html` above).**

**Atomicity warning (CONTEXT.md §"Specifics" + RESEARCH Pitfall 6):** Remove all three gates in the same commit. Removing one or two leaves the choice broken — either the user can't pick it (gate 1 still strips), or the form rejects it after submit (gate 2 still fires), or the visual shows it as disabled (gate 3 still renders the static radio). The atomic-delete is the planner's most-fragile mechanical step in Phase 4.

**Bonus cleanup (D-12 + RESEARCH Pitfall 6):** Update or delete the comment at `planner/models.py:980` (currently `# disabled in UI until Phase 4 ships`) — Phase 4 ships, so the comment is stale.

---

### `requirements.txt` — add `lxml~=5.3.0`

**Analog:** The 22-line flat dependency list. Existing entries like `Django==5.2.4`, `dj-database-url==3.0.1`, `pillow==12.0.0` establish the convention: one package per line, exact-pin (`==`) or range-pin (`>=N,<M`) depending on policy.

**Phase 4 addition (RESEARCH.md §"Standard Stack"):**
```
lxml~=5.3.0
```
Range pin (`~=` admits 5.3.x patch releases) per RESEARCH.md's stable-pick rationale. lxml 6.x exists (released 2026-04-17) but 5.3.x has broader manylinux wheel coverage on older Linux base images. No compilation needed on Railway — pip pulls a pre-built wheel for Python 3.9–3.12. CLAUDE.md §"Deployment" confirms Railway runs `pip install -r requirements.txt` as part of the `startCommand`; no `railway.json` edit needed.

---

## Shared Patterns

### Pure-function exporter contract (trust boundary)

**Source:** `planner/utils/reaper_export.py:9-13` (module docstring) and `planner/utils/yamaha_export.py` (companion exporter, per CONTEXT.md §"Established Patterns").
**Apply to:** `planner/utils/nuendo_live_export.py`.
```python
"""...
Trust boundary note (T-02-02): this module does NOT filter sessions by
project. The caller (Plan 04 view) is responsible for verifying that the
session passed in belongs to the current project — this module trusts its
input and is intentionally a pure string-builder with no DB writes.
"""
```
**Contract elements** (per CONTEXT.md §"Established Patterns"):
1. No DB writes from exporter module.
2. No HTTP / response-shape concerns.
3. No project-scoping (caller's job).
4. Input: ORM-loaded `MultitrackSession` instance. Output: file body (`str` for Reaper, `bytes` for Nuendo).

### Project scoping (`CurrentProjectMiddleware`)

**Source:** `planner/views.py:6881-6889` (in `multitrack_export_rpp`).
**Apply to:** `multitrack_export_nlpr`.
```python
current_project = getattr(request, 'current_project', None)
if not current_project:
    return redirect('/')

session = MultitrackSession.objects.filter(
    id=session_id, project=current_project
).select_related('console').first()
if not session:
    return redirect('planner:multitrack_dashboard')
```
CLAUDE.md §"Architecture" makes `request.current_project` the binding pattern — never URL-based project routing. The `.filter(id=session_id, project=current_project)` clause is the project-scope assertion; bypassing it is the IDOR vector Phase 1's CR-01/CR-02 hardened against on the mutate endpoints.

### Auth decorator (verbatim — verified by RESEARCH Pitfall 5)

**Source:** `planner/views.py:6875` and `:6922` (`@staff_member_required` on both Reaper download views).
**Apply to:** `multitrack_export_nlpr`.
```python
@staff_member_required
def multitrack_export_nlpr(request, session_id):
    ...
```
Import already exists at `planner/views.py:4`: `from django.contrib.admin.views.decorators import staff_member_required`.

### `editor.html` `export_error` fallback (D-03 reuse)

**Source:** `planner/views.py:6900-6912` (no-enabled-tracks fallback in `multitrack_export_rpp`).
**Apply to:** Both the no-enabled-tracks guard AND the missing-fixture guard in `multitrack_export_nlpr`.
```python
enabled_tracks_qs = session.tracks.filter(enabled=True).order_by('track_number')
return render(
    request,
    'planner/multitrack/editor.html',
    _editor_context(
        session,
        tracks=enabled_tracks_qs,
        current_project=current_project,
        export_error='<error string>',
        auto_open_picker=False,
    ),
)
```
D-03 reuses this exact shape for the missing-fixture path. Error strings per CONTEXT.md D-03 / RESEARCH.md §"Pattern 3".

### Reverse-lookup against `YAMAHA_TO_HEX`

**Source:** `planner/utils/reaper_export.py:26-37` (palette table) + RESEARCH.md Code Examples §"Reverse-Lookup Color Name from Hex".
**Apply to:** `MultitrackTrack.resolved_yamaha_name` property in `planner/models.py`.
```python
from .utils.reaper_export import YAMAHA_TO_HEX
_HEX_TO_YAMAHA_NAME = {
    hex_val.lower(): name
    for name, hex_val in YAMAHA_TO_HEX.items()
    if hex_val is not None  # skip 'Off' (None) and 'White' (None)
}
```
Built once at module load. D-04's three-step resolution order consumes this dict.

### Channel-level `color` field reads (Phase 2 D-07)

**Source:** Per CONTEXT.md §"Reusable Assets":
- `ConsoleInput.color` at `planner/models.py:845`
- `ConsoleAuxOutput.color` at `:883`
- `ConsoleMatrixOutput.color` at `:902`
- `ConsoleStereoOutput.color` at `:918`

All four are `CharField(max_length=20, choices=YAMAHA_COLOR_CHOICES, default='Blue', blank=True)`.
**Apply to:** Step 2 of `resolved_yamaha_name`'s resolution chain — `getattr(self.resolved_source, 'color', None)`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | All Phase 4 files have a direct or sibling-pattern analog in the codebase. Phase 4 is pure mirror-of-Phase-1 work plus one new pure-function exporter that closely parallels the existing `reaper_export.py`. |

The closest thing to "no analog" is `planner/utils/nuendo_live_export.py`'s use of `lxml` itself — the codebase has no existing `lxml` consumer (grep returned zero hits across `planner/` and `planner/utils/`). However, the *module-level patterns* (palette table, `_ordered_enabled_tracks` reuse, pure-function exporter, trust-boundary docstring, public builder name) all map cleanly to `reaper_export.py`. Library novelty is contained inside `build_nlpr`'s body — RESEARCH.md Pattern 1 / 2 plus Code Examples §"Reverse-Lookup", §"YAMAHA_TO_FARB Table", §"Apply Farb / Strip Farb", §"Sequential ID Allocator", §"Set Channel ID" give the executor the entire lxml-specific surface area.

## Metadata

**Analog search scope:**
- `planner/utils/` (exporter siblings)
- `planner/views.py` (download view pattern)
- `planner/urls.py` (URL pattern)
- `planner/templates/planner/multitrack/` (editor + new-session templates)
- `planner/forms.py` (form-gate locations)
- `planner/models.py` (`MultitrackTrack` property neighborhood + `TARGET_DAW_CHOICES`)
- `planner/tests/` (existing test file naming + `_SessionFixtureMixin`)
- `planner/data/` (existing bundled-fixture conventions)
- `requirements.txt`

**Files scanned:** 9 source files + 4 directory listings.

**Key cross-cutting observations:**
1. **Phase 4 is a near-perfect mirror of Phase 1.** Every new file has a Phase-1 sibling. The only structural novelty is `lxml` (library import) and the bundled binary fixture (filesystem read).
2. **The form-gate atomicity is Phase 4's most fragile mechanical step.** Three places gate `nuendo_live` (RESEARCH Pitfall 6); remove all three in one commit or the choice is half-broken.
3. **No migrations.** `resolved_yamaha_name` is `@property`. CLAUDE.md §"additive migrations only" is naturally satisfied.
4. **Trust-boundary docstring + project-scope filter must both be present.** They're complementary — the docstring tells the exporter author "don't filter," the view's `.filter(id, project=current_project)` is where filtering actually happens.
5. **The reusable helpers list (CONTEXT.md §"Reusable Assets") is exhaustive:** `_safe_filename`, `_has_enabled_tracks`, `_editor_context`, `_ordered_enabled_tracks`, `YAMAHA_TO_HEX`, `resolved_source`. The executor imports rather than duplicates.

**Pattern extraction date:** 2026-05-13.
