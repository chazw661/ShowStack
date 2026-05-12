---
phase: 02-console-csv-import
plan: "03"
subsystem: planner
tags:
  - django
  - views
  - forms
  - urls
  - csv-import
  - security
dependency_graph:
  requires:
    - 02-01   # ConsoleImport model + channel model color fields
    - 02-02   # parse_upload, is_default_row, SECTION_TARGET_MAP, OUT_OF_SCOPE_SECTIONS
  provides:
    - ConsoleCsvUploadForm (planner/forms.py)
    - console_import_upload view
    - console_import_preview view
    - console_import_commit view
    - _console_import_viewer_block helper
    - _stereo_type_for_row helper
    - _compute_diff_rows helper
    - _apply_console_import helper
    - _family_matches_console_name helper
    - Three URL routes under /audiopatch/multitrack/import/
  affects:
    - planner/forms.py
    - planner/views.py
    - planner/urls.py
tech_stack:
  added: []
  patterns:
    - request= kwarg form pattern (mirrors MultitrackSessionForm)
    - transaction.atomic + select_for_update double-commit guard (T-02-18)
    - IDOR guard via console__project=current_project on all ConsoleImport fetches
    - Viewer gate (D-09) at top of every view endpoint
key_files:
  created: []
  modified:
    - planner/forms.py
    - planner/views.py
    - planner/urls.py
decisions:
  - "_apply_console_import kept in views.py (not a separate utils file) — consistent with the plan spec; file is already large and helpers are tightly coupled to view lifecycle"
  - "filter_kwargs dict pattern used for create_kwargs in _apply_console_import to avoid duplicating stereo_type vs. lookup_field logic"
  - "_family_matches_console_name uses .upper() comparison to handle mixed-case console names (e.g. 'CL5 Main' and 'cl5 main' both match 'cl_ql')"
metrics:
  duration_minutes: 6
  completed_date: "2026-05-12T22:28:07Z"
  tasks_completed: 4
  files_modified: 3
---

# Phase 02 Plan 03: Console CSV Import — Forms, Views, URLs Summary

**One-liner:** Upload form + three views (upload → preview → commit) + URL routes wiring `parse_upload` to `ConsoleImport` with D-09 viewer gate, IDOR guard, and R-02 family-mismatch warning.

---

## What Was Built

### ConsoleCsvUploadForm (`planner/forms.py:1232`)

```python
class ConsoleCsvUploadForm(forms.Form):
    console = forms.ModelChoiceField(queryset=Console.objects.none(), ...)
    csv_file = forms.FileField(widget=forms.FileInput(attrs={'accept': '.csv,.zip'}), ...)

    def __init__(self, *args, request=None, **kwargs): ...
    def clean_csv_file(self): ...  # .csv/.zip extension + 5 MB cap
```

### View Function Signatures (`planner/views.py`)

```python
@staff_member_required
def console_import_upload(request): ...           # line 6983

@staff_member_required
def console_import_preview(request, import_id): ...  # line 7039

@login_required
@require_POST
def console_import_commit(request, import_id): ...   # line 7100
```

### Helper Signatures (`planner/views.py`)

```python
def _console_import_viewer_block(request): ...        # line 6696 — returns HttpResponseForbidden | None
def _stereo_type_for_row(section, family, row): ...   # line 6708 — returns 'L'|'R'|'M'|None
def _compute_diff_rows(snap): ...                     # line 6721 — returns {stats, rows, errors}
def _apply_console_import(snap, keep_showstack_refs): # line 6847 — returns summary dict
def _family_matches_console_name(detected_family, console_name): ...  # line 6961 — returns bool
```

---

## Field-Mapping Table (Section → Model → Lookup → Name Field)

| Section | Model | Lookup field | Name field | Notes |
|---------|-------|-------------|------------|-------|
| InName | ConsoleInput | `input_ch` (str) | **`source`** | NOT `.name` — critical |
| MixName | ConsoleAuxOutput | `aux_number` (str) | `name` | |
| MtxName | ConsoleMatrixOutput | `matrix_number` (str) | `name` | |
| StMonoName | ConsoleStereoOutput | `stereo_type` | `name` | {1→L, 2→R, 3→M} |
| StName (rivage_pm) | ConsoleStereoOutput | `stereo_type` | `name` | {_AL→L, _AR→R} |
| DCAName, MuteDCAName | — (OUT_OF_SCOPE) | — | — | skipped, errors carried forward |
| StName (cl_ql) | — (OUT_OF_SCOPE) | — | — | parser returns 0 rows; defensive skip |

---

## URL-Name Reverse Table

| Name | Pattern | Resolves to |
|------|---------|-------------|
| `planner:console_import_upload` | `multitrack/import/` | `/audiopatch/multitrack/import/` |
| `planner:console_import_preview` | `multitrack/import/<int:import_id>/preview/` | `/audiopatch/multitrack/import/1/preview/` |
| `planner:console_import_commit` | `multitrack/import/<int:import_id>/commit/` | `/audiopatch/multitrack/import/1/commit/` |

---

## Security Properties Implemented

| Threat | Mitigation |
|--------|-----------|
| T-02-10 Unauthenticated upload | `@staff_member_required` on upload + preview; `@login_required` on commit |
| T-02-13 Unbounded file size | `clean_csv_file` rejects files > 5 MB |
| T-02-16 IDOR cross-project | Every `ConsoleImport.objects.*` call filters `console__project=current_project` |
| T-02-17 Viewer elevation | `_console_import_viewer_block` called at top of all 3 views (D-09) |
| T-02-18 Double-commit | `select_for_update()` + `if snap.committed: return HttpResponseBadRequest` |
| T-02-19 Mass assignment | Explicit field assignment (`setattr(existing, name_field, ...)`) — never `**row` |

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Open Items for Plan 04 (Templates + E2E Tests)

Plan 04 must provide:

1. **Templates** (currently referenced by string only — no TemplateDoesNotExist at check time):
   - `planner/templates/planner/multitrack/import_upload.html` — renders `ConsoleCsvUploadForm`
   - `planner/templates/planner/multitrack/import_preview.html` — renders diff table with `family_mismatch_warning` banner + `keep_showstack` checkboxes + Commit button

2. **Dashboard CTA** — "Import from CSV" button/link visible to staff/editors on the multitrack dashboard; must be hidden for `Viewer` group (D-09 template-level gate).

3. **E2E test ledger** (tests Plan 04 must add):
   - Upload-flow e2e: valid CL5 InName.csv → ConsoleImport created → preview renders → commit applies rows
   - `ConsoleInput.source` populated after commit (CSV-05 picker integration smoke)
   - Viewer-403 on all four endpoints (upload GET, upload POST, preview GET, commit POST)
   - IDOR test: preview/commit with import_id from another project returns 404
   - Family-mismatch warning: Rivage CSV targeting "QL5 Main" → `family_mismatch_warning=True`
   - Double-commit: POST commit twice on same import_id → second returns 400 "Already committed."
   - Parse-error: upload file with no `[Information]` → no ConsoleImport row, messages.error rendered
   - Extension validation: upload `.exe` → form error, no ConsoleImport row
   - Size validation: upload 6 MB file → form error, no ConsoleImport row

---

## Self-Check

Checked created/modified files exist and commits are present.
