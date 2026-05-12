---
phase: 02-console-csv-import
plan: "02"
subsystem: csv-parser
tags:
  - django
  - csv
  - parser
  - yamaha
  - testing
dependency_graph:
  requires:
    - planner/data/csv_fixtures/CL_Editor_Blank_Export/ (source fixtures)
    - planner/data/csv_fixtures/QL_Editor_Blank_Export/ (source fixtures)
    - planner/data/csv_fixtures/Rivage_PM_Blank_Export/ (source fixtures)
  provides:
    - planner/utils/console_csv_import.py (parse_upload, parse_section_file, detect_family, is_default_row)
    - planner/tests/test_console_csv_import.py (39 passing unit tests)
    - planner/tests/fixtures/csv_import/ (7 test fixture files)
  affects:
    - Plan 03 (view layer imports parse_upload, SECTION_TARGET_MAP, OUT_OF_SCOPE_SECTIONS)
    - Plan 04 (DB integration tests import from this module + extend fixture set)
tech_stack:
  added: []
  patterns:
    - Pure-function parser module (no ORM) importable without DB setup
    - TextIOWrapper(encoding='utf-8', newline='', errors='replace') — Yamaha CRLF + encoding safety
    - zipfile.is_zipfile detection for single-CSV vs zip-bundle upload (R-04)
    - Per-row error accumulation without abort (CSV-04)
    - Default-row detection via RESEARCH § Per-Section Default-Row Rules (D-01 smart-skip foundation)
key_files:
  created:
    - planner/utils/console_csv_import.py
    - planner/tests/test_console_csv_import.py
    - planner/tests/fixtures/csv_import/cl5_inname.csv
    - planner/tests/fixtures/csv_import/ql5_inname.csv
    - planner/tests/fixtures/csv_import/rivage_inname.csv
    - planner/tests/fixtures/csv_import/rivage_stname.csv
    - planner/tests/fixtures/csv_import/cl5_stmononame.csv
    - planner/tests/fixtures/csv_import/cl5_dirty_mixname.csv
    - planner/tests/fixtures/csv_import/rivage_export_zip.zip
  modified: []
decisions:
  - "detect_family uses raw CSV rows rejoined with comma (not file lines) — csv.reader strips CRLF so rejoining reconstructs clean line strings for the [Information] block classifier"
  - "FAMILY_LIMITS uses cl_ql cap of 72 for InName (CL5 max) — QL5 files only produce 64 rows so can never trigger a false E_KEY_OUT_OF_RANGE"
  - "CL/QL [StName] skipped at section level (returns zero rows before any row loop) — guarantees Plan 03 apply step never receives stereo-return rows (Warning 7 fix)"
  - "Rivage StName _BL/_BR skipped at row level — _AL/_AR map to ConsoleStereoOutput L/R per existing STEREO_CHOICES"
  - "TextIOWrapper errors='replace' per T-02-08 — non-UTF-8 bytes become U+FFFD instead of raising; encoding errors recorded in result['errors'] not raised as exceptions"
metrics:
  duration: "~7 minutes"
  completed: "2026-05-12T22:12:43Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 9
  tests_added: 39
  test_pass_rate: "39/39 (100%)"
---

# Phase 02 Plan 02: Console CSV Import Parser Summary

Pure-function Yamaha CL/QL and Rivage PM CSV parser with zip-bundle support, per-row error accumulation, default-row detection, and 39 SimpleTestCase unit tests covering all three console families.

## What Was Built

### Parser module: `planner/utils/console_csv_import.py` (600 lines)

**Exported names (Plan 03 API surface):**
- `detect_family(lines)` — classifies `[Information]` block as `cl_ql`, `rivage_pm`, or `unknown`
- `parse_section_file(uploaded_file, filename)` — parses one section CSV, returns `{family, section, header_row, rows, errors, source_filename}`
- `parse_upload(uploaded_file, filename)` — top-level entry; detects zip vs single CSV, returns `{family, sections, fatal_error, is_zip}`
- `is_default_row(section, family, row)` — D-01 smart-skip: True iff row matches factory default for that section/channel
- `SECTION_TARGET_MAP` — `{InName: ConsoleInput, MixName: ConsoleAuxOutput, MtxName: ConsoleMatrixOutput, StMonoName: ConsoleStereoOutput}`
- `OUT_OF_SCOPE_SECTIONS` — `{DCAName, MuteDCAName}`

**Per-row error codes implemented:**
- `E_BAD_KEY` — key doesn't match section's expected shape
- `E_KEY_OUT_OF_RANGE` — channel number exceeds family max
- `E_UNKNOWN_COLOR` — COLOR not in YAMAHA_COLORS; falls back to Blue, included in rows
- `E_COLUMN_COUNT` — fewer than 4 columns
- `E_DUPLICATE_KEY` — same key twice; first wins
- `E_NAME_TOO_LONG` — NAME > 100 chars; truncated, logged
- `W_NO_MODEL_TARGET` — informational skip (DCAName, MuteDCAName, CL/QL StName, Rivage _BL/_BR)

**File-level fatal codes:**
- `E_ENCODING`, `E_NO_INFORMATION`, `E_UNKNOWN_FAMILY`, `E_NO_SECTION`, `E_MIXED_FAMILIES`

### Test fixtures: `planner/tests/fixtures/csv_import/` (7 files)

| File | Source | Purpose |
|------|--------|---------|
| `cl5_inname.csv` | Byte-copy of CL_Editor_Blank_Export/InName.csv | CL5 family detection + 72-row parse |
| `ql5_inname.csv` | Byte-copy of QL_Editor_Blank_Export/InName.csv | QL5 family detection + 64-row parse |
| `rivage_inname.csv` | Byte-copy of Rivage_PM_Blank_Export/InName.csv | Rivage family + 288-row parse + leading-zero strip |
| `rivage_stname.csv` | Byte-copy of Rivage_PM_Blank_Export/StName.csv | _AL/_AR import + _BL/_BR skip test |
| `cl5_stmononame.csv` | Byte-copy of CL_Editor_Blank_Export/StMonoName.csv | ST L/ST R/MONO default mapping |
| `cl5_dirty_mixname.csv` | Hand-crafted CRLF CSV | Exercises E_UNKNOWN_COLOR, E_KEY_OUT_OF_RANGE, E_BAD_KEY, E_NAME_TOO_LONG |
| `rivage_export_zip.zip` | Built from Rivage_PM_Blank_Export (4 members) | Zip-upload path + multi-section iteration |

### Test file: `planner/tests/test_console_csv_import.py` (469 lines, 39 tests)

| Class | Tests | What it validates |
|-------|-------|------------------|
| `FamilyDetectTest` | 5 | detect_family with direct calls + real fixture files |
| `ParserFixtureTest` | 4 | Row counts (72/64/288/3), zero hard errors on blank fixtures |
| `DefaultRowTest` | 10 | Every blank InName row is default; MixName Fx rows; negative cases |
| `DirtyFixtureTest` | 6 | Per-row error catalog; unknown-color Blue fallback; bad/range rows excluded |
| `ZipUploadTest` | 2 | 4-section Rivage zip + mixed-family E_MIXED_FAMILIES |
| `RivageStNameTest` | 1 | _AL/_AR rows imported; _BL/_BR produce W_NO_MODEL_TARGET |
| `ClQlStNameTest` | 1 | CL/QL [StName] skipped wholesale; skip count + reason in error entry |
| `OutOfScopeSectionTest` | 2 | DCAName + MuteDCAName produce empty rows + W_NO_MODEL_TARGET |
| `SectionTargetMapTest` | 3 | SECTION_TARGET_MAP contents + OUT_OF_SCOPE_SECTIONS |
| `ParserEdgeCaseTest` | 3 | Empty file, no [Information] block, single-CSV parse_upload |

**Test run:** `python manage.py test planner.tests.test_console_csv_import -v 2` — 39/39 OK, 0.003s, no DB required.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `226c236` | chore | Add CSV import test fixtures (7 files) |
| `c77aeda` | feat | Add pure-function Yamaha CSV import parser (600 lines) |
| `5c6fdda` | test | Add parser unit tests (39 tests, 469 lines) |

## Deviations from Plan

None — plan executed exactly as written. The parser implementation closely follows the code sketch in the plan's `<action>` block. Minor structural differences are cosmetic (docstring formatting, comment layout).

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. `parse_upload` and `parse_section_file` operate entirely in memory (no filesystem writes). The T-02-07 zip-slip mitigation (`..` rejection + in-memory `zf.open`) and T-02-08 encoding mitigation (`errors='replace'`) are implemented as specified.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `planner/utils/console_csv_import.py` | FOUND |
| `planner/tests/test_console_csv_import.py` | FOUND |
| `planner/tests/fixtures/csv_import/cl5_inname.csv` | FOUND |
| `planner/tests/fixtures/csv_import/ql5_inname.csv` | FOUND |
| `planner/tests/fixtures/csv_import/rivage_inname.csv` | FOUND |
| `planner/tests/fixtures/csv_import/rivage_stname.csv` | FOUND |
| `planner/tests/fixtures/csv_import/cl5_stmononame.csv` | FOUND |
| `planner/tests/fixtures/csv_import/cl5_dirty_mixname.csv` | FOUND |
| `planner/tests/fixtures/csv_import/rivage_export_zip.zip` | FOUND |
| Commit `226c236` | FOUND |
| Commit `c77aeda` | FOUND |
| Commit `5c6fdda` | FOUND |
| 39 tests pass | VERIFIED (0.003s, no DB) |
