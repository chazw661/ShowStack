---
phase: 02-console-csv-import
plan: "04"
subsystem: planner
tags:
  - django
  - templates
  - integration-tests
  - ui
  - security
dependency_graph:
  requires:
    - 02-01   # ConsoleImport model + channel color fields
    - 02-02   # parse_upload, is_default_row, SECTION_TARGET_MAP
    - 02-03   # views, forms, URLs
  provides:
    - import_upload.html template
    - import_preview.html template (with R-02 family-mismatch guardrail)
    - dashboard.html Import CTA + messages block
    - test_console_csv_import_views.py (16 tests, CSV-01..CSV-05 + security)
    - cl5_inname_customized.csv fixture
  affects:
    - planner/templates/planner/multitrack/dashboard.html
    - planner/migrations/0112_fix_showday_date_constraint.py (SQLite compat fix)
    - planner/migrations/0113_audiochecklist_created_at_audiochecklist_name_and_more.py (SQLite compat fix)
    - planner/migrations/0126_alter_micassignment_shared_presenters.py (SQLite compat fix)
tech_stack:
  added: []
  patterns:
    - mts-* CSS shell (extends admin/base_site.html, same as Phase 1 multitrack templates)
    - enctype=multipart/form-data on upload form
    - SeparateDatabaseAndState for pre-existing managed=False migration issue
    - RunPython(postgres-only) guard for PostgreSQL-specific DDL migrations
    - assertContains checking rendered div element markup (not CSS class name)
key_files:
  created:
    - planner/templates/planner/multitrack/import_upload.html  (57 lines)
    - planner/templates/planner/multitrack/import_preview.html (163 lines)
    - planner/tests/test_console_csv_import_views.py (455 lines, 16 tests)
    - planner/tests/fixtures/csv_import/cl5_inname_customized.csv (77 lines)
  modified:
    - planner/templates/planner/multitrack/dashboard.html (+14 lines)
    - planner/migrations/0112_fix_showday_date_constraint.py (SQLite compat)
    - planner/migrations/0113_audiochecklist_created_at_audiochecklist_name_and_more.py (SQLite compat)
    - planner/migrations/0126_alter_micassignment_shared_presenters.py (SQLite compat)
decisions:
  - "Viewer gate in dashboard.html uses inline request.user.groups.filter check (no existing can_edit flag found in context processor or dashboard view)"
  - "assertNotContains checks for rendered div markup 'class=\"mts-banner mts-banner-warning\"' not just the CSS class name — the class appears in every <style> block"
  - "test_warning_set_when_name_mismatch renamed from test_warning_set_when_count_gap_large — Rivage all-default fixture has new_count=0 so count-gap heuristic doesn't trip; name-mismatch heuristic trips because 'CL5 Main' has no 'rivage'/'PM' tokens"
  - "3 pre-existing SQLite-incompatible migrations fixed as Rule 3 (blocking issue) — required to run any Django TestCase locally"
metrics:
  duration_minutes: 45
  completed_date: "2026-05-12"
  tasks_completed: 4
  files_modified: 8
---

# Phase 02 Plan 04: Templates + Integration Tests Summary

**One-liner:** Three multitrack import templates (upload form, diff preview with R-02 guardrail, dashboard CTA) plus 16-test integration suite covering CSV-01..CSV-05, D-09 viewer gate, IDOR, and Phase 1 picker hand-off.

---

## What Was Built

### Task 1 — `import_upload.html` (57 lines)

Upload form template modeled on `new_session.html`. Key delta: `enctype="multipart/form-data"`. Renders `ConsoleCsvUploadForm` with console dropdown + CSV/zip file input. Cancel button links back to multitrack dashboard. Messages block filters on `'multitrack_import' in message.tags` for parse-error banners.

### Task 2 — `import_preview.html` (163 lines)

Diff preview template — the most complex template in Phase 2:

- **R-02 / Blocker 2 guardrail:** When `family_mismatch_warning=True`, renders `<div class="mts-banner mts-banner-warning">` (red) instead of the blue info banner. Adds a required `<input type="checkbox" name="confirm_family">` and renders the Commit button with `disabled`. A 4-line JS snippet enables the button when the checkbox is checked. When `family_mismatch_warning=False`, only the blue info banner renders — no checkbox, no disabled button.
- **Stats strip:** 5 color-coded chips — Created (green), Updated (blue), Conflicts (amber), Unchanged (grey), Errors (red).
- **Filter chips:** `Show unchanged` and `Errors only` toggles — JS adds/removes CSS classes on `<body>`. `status-unchanged` rows are hidden by default.
- **Diff table:** All channel data rendered via `{{ }}` — no `|safe` filter (T-02-21 XSS mitigated).
- **Conflict checkboxes:** Only rendered for `status='conflict'` rows; `name="keep_showstack"`, default unchecked = CSV wins (D-02).
- **Commit form:** POSTs to `planner:console_import_commit` with `{% csrf_token %}` (T-02-22).

### Task 3 — `dashboard.html` modifications

- **Messages block:** Added above the header; renders `mts-banner-{{ message.level_tag }}` with `data-tags="{{ message.tags }}"`. Provides the D-06 post-commit success banner landing.
- **Import CTA:** `<a class="mts-btn mts-btn-secondary" href="{% url 'planner:console_import_upload' %}">Import Console CSV</a>` inside a `{% if not request.user.groups.filter(name="Viewer").exists %}` guard (D-09 / Blocker 3).
- **Visual hierarchy preserved:** `+ New Session` retains `mts-btn-primary`; Import CSV uses `mts-btn-secondary`.

### Task 4 — Integration tests (16 tests) + fixture

**`cl5_inname_customized.csv`:** 72 rows — `_01,Kick,Red,Dynamic,` and `_02,Snare,Orange,Dynamic,` customized; rows 3–72 are factory defaults.

**Test classes:**

| Class | Tests | Requirement |
|-------|-------|-------------|
| `AnonymousAccessTest` | `test_anon_redirected_to_login_on_upload_get` | Auth gate |
| `ViewerGateTest` | upload GET, preview GET, upload POST, commit POST → 403 | D-09 / Blocker 3 |
| `UploadFlowTest` | valid upload, junk upload, IDOR 404 | CSV-01, CSV-02 |
| `PreviewTest` | context keys, diff recomputation | CSV-03 |
| `CommitTest` | channels created, double-commit 400, smart-skip D-01 | CSV-03, CSV-04 |
| `CommitToPickerTest` | Phase 1 picker query sees imported channels | CSV-05 |
| `FamilyMismatchWarningTest` | warning branch + clean branch | R-02 / Blocker 2 |

---

## CSV-01..CSV-05 Verification Matrix

| Requirement | Test method | What it proves |
|-------------|-------------|----------------|
| CSV-01 (CL5 import) | `UploadFlowTest.test_valid_csv_creates_draft_and_redirects_to_preview` | Valid CL5 InName → 1 draft ConsoleImport |
| CSV-01 (commit) | `CommitTest.test_commit_creates_channels_and_redirects` | ConsoleInput rows created; Kick/Snare on correct channels |
| CSV-02 (Rivage upload) | `FamilyMismatchWarningTest.test_warning_set_when_name_mismatch` | Rivage InName uploaded and previewed; family=rivage_pm detected |
| CSV-03 (preview + per-row errors) | `PreviewTest.test_preview_context_keys` | All 8 context keys present |
| CSV-04 (non-aborting errors) | `UploadFlowTest.test_junk_upload_no_import_row_created` | Parse error → no ConsoleImport row, 200 re-render |
| CSV-05 (picker hand-off) | `CommitToPickerTest.test_imported_channels_appear_in_phase_one_queries` | `ConsoleInput.objects.filter(console=...)` returns Kick+Snare post-commit |

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Three pre-existing SQLite-incompatible migrations blocked all `TestCase` (DB) tests**

- **Found during:** Task 4 (first test run)
- **Issue:** Migrations 0112, 0113, and 0126 contained PostgreSQL-specific DDL or Django-unsupported operations that raised exceptions when the SQLite test DB was created from scratch.
  - `0112`: `ALTER TABLE ... DROP CONSTRAINT IF EXISTS` — PostgreSQL-only syntax
  - `0113`: `AddField` / `AlterModelTable` on `AudioChecklist` whose `managed=False` meant the table never existed in SQLite
  - `0126`: `AlterField` adding `through=` to an existing M2M — Django explicitly rejects this operation
- **Fix:**
  - `0112`: replaced `RunSQL` with `RunPython` that guards on `connection.vendor == 'postgresql'`
  - `0113`: replaced all `audiochecklist` DDL ops with `RunPython(postgres-only)` + `SeparateDatabaseAndState` to keep Django's migration state correct; non-audiochecklist ops (`commbeltpack`, `showday`) kept as standard ORM operations
  - `0126`: replaced `AlterField` with `SeparateDatabaseAndState(database_operations=[], state_operations=[...])` — the through table already existed in prod, only Django's state needed updating
- **Production impact:** None. The PostgreSQL guards execute on `vendor == 'postgresql'` so production Railway deploys continue to work exactly as before.
- **Commits:** b9ba9a4 (included in Task 4 commit)

**2. [Rule 1 - Bug] `test_warning_set_when_name_mismatch` renamed from plan's `test_warning_set_when_count_gap_large`**

- **Found during:** Task 4
- **Issue:** The Rivage InName fixture is all factory-default rows, so `new_count=0` after smart-skip. `0 > (0 + 16)` is False — the count-gap heuristic doesn't trip. The name-mismatch heuristic does trip: `'CL5 Main'` contains no `'rivage'`/`'PM'` tokens.
- **Fix:** Renamed test to `test_warning_set_when_name_mismatch` and updated assertion message to explain the actual heuristic path.

**3. [Rule 1 - Bug] `assertNotContains` checked CSS class name instead of rendered element**

- **Found during:** Task 4 (test failure)
- **Issue:** `mts-banner-warning` appears in the `<style>` block on every render. `assertNotContains(response, 'mts-banner-warning')` always failed on the no-warning path.
- **Fix:** Changed both assertions to check for the rendered div markup: `'class="mts-banner mts-banner-warning"'` — this is only present when the warning branch is taken.

---

## Test Setup Quirks

- **`Project.objects.create` requires `owner=` (User FK).** Plan spec showed only `name` and `client`. Fixed in `CsvImportTestBase.setUp()` — creates an `owner_user` first, then passes it to `Project.objects.create(owner=self.owner_user)`.
- **Session key is `current_project_id`** (confirmed in `planner/middleware.py:36`). Used in `_login_staff()` and `_login_viewer()`.
- **`staff_user` and `owner_user` are the same User object** in the test base — the project owner is already `is_staff=True`, so no second user needed.

---

## No Phase 1 Code Modified (CSV-05 Confirmed)

The `CommitToPickerTest` re-runs the exact query Phase 1's `_build_picker_data` uses:

```python
ConsoleInput.objects.filter(console=self.console).order_by('input_ch')
```

No lines in `planner/views.py` from 5805–5826 (or anywhere else in Phase 1) were changed. CSV-05 is satisfied by writing to the same `ConsoleInput` table that Phase 1 reads.

---

## Manual Smoke-Test Plan (for Charlie before merging)

1. `python manage.py runserver` + log in as staff user
2. Navigate to `/audiopatch/multitrack/` — confirm:
   - `Import Console CSV` secondary CTA appears next to `+ New Session`
   - No Import CTA visible when logged in as a Viewer-group user
3. Click `Import Console CSV` → upload `cl5_inname_customized.csv` against a CL5 console → confirm redirect to preview page
4. Preview page: confirm stats strip shows `Created: 2`, `Unchanged: 70+`; confirm blue info banner (no warning)
5. Upload `rivage_inname.csv` against that same CL5 console → preview → confirm red `mts-banner-warning` banner appears, `confirm_family` checkbox present, Commit button disabled; check the checkbox → Commit button enables
6. Go back and upload `cl5_inname_customized.csv` → commit → confirm landing on `/audiopatch/multitrack/` with green success banner
7. Click `+ New Session` on that console → track picker should include `Kick` and `Snare` as available inputs (CSV-05)
8. Attempt to commit the same import a second time (direct POST) → confirm 400 response

---

## Self-Check

### Created files exist:
- `planner/templates/planner/multitrack/import_upload.html` — FOUND
- `planner/templates/planner/multitrack/import_preview.html` — FOUND
- `planner/tests/test_console_csv_import_views.py` — FOUND
- `planner/tests/fixtures/csv_import/cl5_inname_customized.csv` — FOUND

### Commits exist:
- `ea15364` feat(02-04): add import_upload.html template — FOUND
- `686ff54` feat(02-04): add import_preview.html template — FOUND
- `fe36494` feat(02-04): add Import CSV CTA + messages block to multitrack dashboard — FOUND
- `b9ba9a4` feat(02-04): add integration tests + cl5_inname_customized.csv fixture — FOUND

### Test results:
- `planner.tests.test_console_csv_import`: 39 tests — OK
- `planner.tests.test_console_csv_import_views`: 16 tests — OK
- Combined: 55 tests — OK

## Self-Check: PASSED
