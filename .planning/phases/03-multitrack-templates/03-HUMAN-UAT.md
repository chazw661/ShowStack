---
status: partial
phase: 03-multitrack-templates
source: [03-VERIFICATION.md]
started: 2026-05-13
updated: 2026-05-13
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end save → list → rename → delete flow on a live browser session
expected: Engineer clicks 'Save as Template' on `/audiopatch/multitrack/<id>/`, enters a name, sees success toast; navigates to `/audiopatch/multitrack/` and sees the template card; clicks ⋯ → Rename, enters new name, page reloads with renamed card; clicks ⋯ → Delete, confirms, card disappears.
result: [pending]

### 2. Apply a CL5-saved template to a QL5 target — confirm skipped-slot banner appears with correct count
expected: Save a template from a session whose console has matrix 9–12; create a new session on a console with only 8 matrices and pick the template. Banner reads exactly: `Applied template '<name>' — 16 of 20 slots mapped; 4 skipped (matrix 9, 10, 11, 12 not present on this console).`
result: [pending]

### 3. Empty-template apply — confirm the metadata-seeded banner appears
expected: Save a template from a session with zero enabled tracks. Create a new session and pick the template. Banner reads exactly: `Applied template '<name>' — metadata seeded; no tracks in template.` and the editor opens with the track picker auto-opened on Inputs per Phase 1 D-12.
result: [pending]

### 4. Multi-user owner-scoping smoke test (user A's templates don't appear in user B's dropdown)
expected: User A saves template T1; user B opens `/audiopatch/multitrack/new/` and the dropdown does NOT list T1. User B crafts a POST with `template=<T1's id>`; form validation rejects with 'Select a valid choice.'
result: [pending]

### 5. Viewer-group write blocks (save/rename/delete return 403)
expected: Add a user to the Viewer group; attempt to POST `/audiopatch/multitrack/templates/save/`, `/rename/`, `/delete/`. All three return HTTP 403 with body `{'error': 'Read-only access.'}`.
result: [pending]

### 6. TPL-04 visual parity with Audio Checklist / Comm Config template patterns
expected: The Save-as-Template button placement, the rename modal/prompt behavior, and the empty-state copy on the Templates dashboard section look and feel comparable to AudioChecklistTemplate's existing patterns (rename/load/delete dropdown shape).
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
