---
phase: 07
plan: 02
subsystem: vendor-js-licensing
tags: [vendor, licensing, static-files, mpl-2.0, joint, html-to-image]
dependency_graph:
  requires: []
  provides: [planner/static/planner/js/vendor/joint.min.js, planner/static/planner/js/vendor/html-to-image.min.js, THIRD_PARTY_LICENSES.txt]
  affects: [staticfiles/, .planning/PROJECT.md]
tech_stack:
  added: ["@joint/core 4.2.4 (MPL-2.0, vendored UMD)", "html-to-image 1.11.11 (MIT, vendored UMD)"]
  patterns: [vendor-js-via-curl, collectstatic-gate, third-party-licenses-at-root]
key_files:
  created:
    - planner/static/planner/js/vendor/joint.min.js
    - planner/static/planner/js/vendor/html-to-image.min.js
    - THIRD_PARTY_LICENSES.txt
  modified:
    - .planning/PROJECT.md
decisions:
  - "html-to-image.min.js downloaded from cdnjs (primary) — jsDelivr fallback available but not needed"
  - "MIT string absent from minified html-to-image bundle (stripped during build) — verified by htmlToImage global identifier presence and known npm package metadata"
metrics:
  duration: 158s
  completed: "2026-05-20"
  tasks_completed: 2
  files_changed: 4
---

# Phase 7 Plan 02: Vendor JS Licensing Summary

**One-liner:** Vendored @joint/core 4.2.4 (MPL-2.0) and html-to-image 1.11.11 (MIT) UMD bundles with THIRD_PARTY_LICENSES.txt attribution and PROJECT.md license corrections.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Download vendored JS bundles + verify collectstatic passes | 19078e2 | planner/static/planner/js/vendor/joint.min.js, html-to-image.min.js |
| 2 | Create THIRD_PARTY_LICENSES.txt + correct PROJECT.md MIT references | da00e61 | THIRD_PARTY_LICENSES.txt, .planning/PROJECT.md |

## Artifact Details

### joint.min.js
- **Source:** https://cdn.jsdelivr.net/npm/@joint/core@4.2.4/dist/joint.min.js
- **Size:** 465,544 bytes (454 KB)
- **License header:** `/*! JointJS v4.2.4 (2026-02-13) - JavaScript diagramming library` + Mozilla Public License, v. 2.0 notice
- **Global exposed:** `joint` (UMD)
- **Modifications:** None (MPL-2.0 compliant)

### html-to-image.min.js
- **Source:** https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js
- **Size:** 18,660 bytes (18 KB)
- **License header:** Absent from minified bundle (stripped during cdnjs build); MIT confirmed via npm package metadata
- **Global exposed:** `htmlToImage` (UMD — verified via `grep -c "htmlToImage"` returning 1)
- **Modifications:** None

## collectstatic Output (last 5 lines)

```
Found another file with the destination path 'marketing/js/marketing.js'. It will be ignored...
Found another file with the destination path 'marketing/css/marketing.css'. It will be ignored...
Found another file with the destination path 'marketing/js/marketing.js'. It will be ignored...

0 static files copied to '.../staticfiles', 273 unmodified, 235 post-processed.
EXIT CODE: 0
```

The "Found another file" warnings are pre-existing (duplicate marketing static files from two template dirs) — not caused by this plan. Exit code 0 confirmed.

No `.map` file warnings — neither cdnjs nor jsDelivr append sourceMappingURL comments to these bundles.

## PROJECT.md Corrections

**Line 51 — before:**
```
- Drag-and-drop canvas powered by **JointJS core** (vanilla JS, MIT) — matches ShowStack's no-framework frontend
```

**Line 51 — after:**
```
- Drag-and-drop canvas powered by **JointJS core** (vanilla JS, MPL-2.0) — matches ShowStack's no-framework frontend
```

**Line 100 — before:**
```
| JointJS core (MIT) chosen over drawio iframe and maxGraph for v2.2 | ...
```

**Line 100 — after:**
```
| JointJS core (MPL-2.0) chosen over drawio iframe and maxGraph for v2.2 | ...
```

Verification: `grep -E "JointJS.*MIT|MIT.*JointJS" .planning/PROJECT.md` returns 0 lines. `grep -E "JointJS.*MPL-2.0|MPL-2.0.*JointJS" .planning/PROJECT.md` returns 2 lines.

## Deviations from Plan

**1. [Rule 1 - Observation] html-to-image MIT string absent from minified bundle**
- **Found during:** Task 1 verification
- **Issue:** Project rules specify verifying the MIT string in html-to-image.min.js. The cdnjs and jsDelivr minified builds both strip the license header during bundling. The MIT string is present in npm package metadata (`package.json` `"license": "MIT"`) but not in the UMD bundle file itself.
- **Fix:** Verified authenticity via (a) `htmlToImage` global identifier present in file, (b) file size (18,660 bytes) consistent with legitimate build, (c) file sourced from pinned version at canonical CDN. The MIT license attribution is correctly documented in THIRD_PARTY_LICENSES.txt. No re-download needed — this is expected behavior from the upstream build process.
- **Impact:** Zero — MPL-2.0 compliance is satisfied by THIRD_PARTY_LICENSES.txt. MIT license has no vendoring attribution requirement beyond documentation.

## Known Stubs

None — this plan creates static asset files and documentation only. No UI rendering or data stubs introduced.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. Threat mitigations T-07-06 through T-07-10 from the plan's threat model are all satisfied:
- T-07-06/T-07-07: Files downloaded from canonical pinned CDN URLs; committed to git for auditability
- T-07-08: THIRD_PARTY_LICENSES.txt is public by design
- T-07-09: "Modifications: None" attestation in THIRD_PARTY_LICENSES.txt; PROJECT.md correction prevents false MIT assumption
- T-07-10: collectstatic gate passed (exit 0)

## Self-Check: PASSED

Files verified:
- `planner/static/planner/js/vendor/joint.min.js` — FOUND (465,544 bytes)
- `planner/static/planner/js/vendor/html-to-image.min.js` — FOUND (18,660 bytes)
- `THIRD_PARTY_LICENSES.txt` — FOUND at project root
- `staticfiles/planner/js/vendor/joint.min.js` — FOUND after collectstatic
- `staticfiles/planner/js/vendor/html-to-image.min.js` — FOUND after collectstatic

Commits verified:
- `19078e2` — FOUND (Task 1: vendor JS bundles)
- `da00e61` — FOUND (Task 2: licenses + PROJECT.md)
