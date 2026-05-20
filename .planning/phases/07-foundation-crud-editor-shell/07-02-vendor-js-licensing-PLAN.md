---
phase: 07
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - planner/static/planner/js/vendor/joint.min.js
  - planner/static/planner/js/vendor/html-to-image.min.js
  - THIRD_PARTY_LICENSES.txt
  - .planning/PROJECT.md
autonomous: true
requirements:
  - DGM-01
user_setup: []

must_haves:
  truths:
    - "planner/static/planner/js/vendor/joint.min.js exists and is the unmodified @joint/core 4.2.4 UMD bundle from jsDelivr"
    - "planner/static/planner/js/vendor/html-to-image.min.js exists and is the unmodified html-to-image 1.11.11 UMD bundle"
    - "THIRD_PARTY_LICENSES.txt exists at project root, attributes joint as MPL-2.0 and html-to-image as MIT"
    - "python manage.py collectstatic --noinput completes with no warnings related to the new vendor files"
    - ".planning/PROJECT.md contains zero references to JointJS being MIT — all references corrected to MPL-2.0"
  artifacts:
    - path: "planner/static/planner/js/vendor/joint.min.js"
      provides: "JointJS canvas library — exposes `joint` UMD global on window"
      contains: "joint"
    - path: "planner/static/planner/js/vendor/html-to-image.min.js"
      provides: "html-to-image library — exposes `htmlToImage` UMD global on window"
      contains: "htmlToImage"
    - path: "THIRD_PARTY_LICENSES.txt"
      provides: "MPL-2.0 attribution for @joint/core; MIT attribution for html-to-image and Sortable"
      contains: "Mozilla Public License 2.0"
    - path: ".planning/PROJECT.md"
      provides: "Corrected key-decisions row stating JointJS core is MPL-2.0 (not MIT)"
      contains: "MPL-2.0"
  key_links:
    - from: "THIRD_PARTY_LICENSES.txt"
      to: "planner/static/planner/js/vendor/joint.min.js"
      via: "explicit `Vendored as: planner/static/planner/js/vendor/joint.min.js` line"
      pattern: "Vendored as: planner/static/planner/js/vendor/joint.min.js"
    - from: "Whitenoise static serving"
      to: "vendor JS files"
      via: "collectstatic copies vendor/ into STATIC_ROOT; Whitenoise serves with application/javascript MIME"
      pattern: "joint.min.js"
---

<objective>
Vendor the two new third-party JS bundles the diagrammer requires (`@joint/core` 4.2.4 MPL-2.0 and `html-to-image` 1.11.11 MIT) into `planner/static/planner/js/vendor/`, create the `THIRD_PARTY_LICENSES.txt` file at project root that MPL-2.0 attribution requires, and correct the two existing occurrences in `.planning/PROJECT.md` that misstate JointJS as MIT-licensed.

Purpose: DGM-01 (list page renders) depends on the editor shell loading without 404s; Plan 04 will reference these static files in `editor.html`. Both files must exist and pass `collectstatic` BEFORE Plan 04 templates land, otherwise local serving and Railway deploys break. Per locked decision (research SUMMARY.md and PITFALLS.md Pitfall 11), MPL-2.0 compliance requires the unmodified `joint.min.js` plus a `THIRD_PARTY_LICENSES.txt` attribution file.

Output: Two new vendored JS files committed verbatim from upstream CDN, one new `THIRD_PARTY_LICENSES.txt` at project root, two corrected lines in `.planning/PROJECT.md`. `collectstatic --noinput` exits 0 with no warnings.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/research/STACK.md
@.planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md
@.planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md
@CLAUDE.md

<interfaces>
<!-- Existing vendor file — the precedent for the new ones -->
From planner/static/planner/js/vendor/:
- Sortable.min.js (existing UMD vendored bundle; analog for new vendored files)

<!-- Existing settings — Whitenoise serves everything under STATIC_ROOT after collectstatic -->
From audiopatch/settings.py:
- STATIC_URL = '/static/'
- STATIC_ROOT = BASE_DIR / 'staticfiles'  (collectstatic target)
- STATICFILES_DIRS includes planner/static
- Whitenoise serves from STATIC_ROOT in production

<!-- PROJECT.md lines requiring correction (verified via grep) -->
Line 51: "Drag-and-drop canvas powered by **JointJS core** (vanilla JS, MIT) — matches ShowStack's no-framework frontend"
Line 100: "| JointJS core (MIT) chosen over drawio iframe and maxGraph for v2.2 | ..."
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Download vendored JS bundles + verify collectstatic passes</name>
  <files>planner/static/planner/js/vendor/joint.min.js, planner/static/planner/js/vendor/html-to-image.min.js</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (section: "planner/static/planner/js/vendor/joint.min.js and html-to-image.min.js")
    - .planning/research/STACK.md (section: "Acquisition" — exact curl commands)
    - .planning/research/PITFALLS.md (Pitfall 12 — Whitenoise + JointJS CSS asset path resolution)
    - CLAUDE.md section "Static files" (collectstatic runs in railway.json on every deploy; missing static files break prod)
  </read_first>

  <behavior>
    - Two new files exist at planner/static/planner/js/vendor/joint.min.js and planner/static/planner/js/vendor/html-to-image.min.js
    - Both files are non-empty (size lower bound: joint.min.js typically 700KB+, html-to-image.min.js typically 50KB+)
    - Both files start with characters consistent with minified JavaScript (not an HTML 404 page captured by curl error)
    - python manage.py collectstatic --noinput exits 0 and includes both new files in its "X static files copied" report
    - No CSS file is downloaded (per STACK.md: @joint/core 4.x requires no CSS)
    - Per MPL-2.0: files are vendored UNMODIFIED — do not edit, minify-rebuild, or patch them
  </behavior>

  <action>
**Step A — Create vendor directory if missing and download both bundles:**

Run (from project root):

    mkdir -p planner/static/planner/js/vendor
    curl -fL "https://cdn.jsdelivr.net/npm/@joint/core@4.2.4/dist/joint.min.js" \
         -o planner/static/planner/js/vendor/joint.min.js

The `-f` flag causes curl to fail (non-zero exit) if HTTP status is not 2xx. The `-L` flag follows redirects. If this curl fails, STOP and report the error — do NOT retry from a different URL silently.

Then:

    curl -fL "https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js" \
         -o planner/static/planner/js/vendor/html-to-image.min.js

If the cdnjs URL fails, fallback to jsDelivr per RESEARCH.md A2:

    curl -fL "https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/dist/html-to-image.min.js" \
         -o planner/static/planner/js/vendor/html-to-image.min.js

**Step B — Sanity-check the downloaded files:**

    ls -la planner/static/planner/js/vendor/joint.min.js
    ls -la planner/static/planner/js/vendor/html-to-image.min.js

Both files should report a non-trivial size (joint.min.js typically ~700KB–1.1MB; html-to-image.min.js typically ~50KB–100KB). If either reports a size under 10KB, the download likely captured an HTML error page rather than the JS bundle — re-download and verify.

Quick content sanity check — both files should be minified JS (not HTML, not JSON):

    head -c 200 planner/static/planner/js/vendor/joint.min.js
    head -c 200 planner/static/planner/js/vendor/html-to-image.min.js

joint.min.js head should contain references to the joint namespace (look for `joint` or UMD-wrap code like `(function(e,t)`). html-to-image.min.js head should contain UMD-wrap code mentioning `htmlToImage` or similar.

Confirm both files contain their expected global identifiers (loosely):

    grep -c "joint" planner/static/planner/js/vendor/joint.min.js
    grep -c "htmlToImage\|html-to-image" planner/static/planner/js/vendor/html-to-image.min.js

Both grep counts MUST be greater than zero.

**Step C — DO NOT MODIFY the files:**

Per MPL-2.0 (PITFALLS.md Pitfall 11): the file-level copyleft attaches only to MODIFICATIONS. Vendoring the unmodified file is fully compliant. Do NOT:
- Re-minify
- Strip the source-map comment (if present)
- Add a Charlie / ShowStack comment header
- Reformat
- Apply Prettier or any linter to it

If a future linter complains about the file, add it to a project lint ignore list — never edit the file itself.

**Step D — Run collectstatic to confirm Whitenoise compatibility:**

    python manage.py collectstatic --noinput

Expected output: a line like `N static files copied to ...` with no ValueError, no MissingFileError, no warnings naming the new files. Per PITFALLS.md Pitfall 12, the failure mode here is Whitenoise's CompressedManifestStaticFilesStorage choking on a url() reference inside a CSS file — but we are not vendoring CSS for @joint/core 4.x (CSS not required), so this should pass cleanly. If it fails because the bundle has a sourceMappingURL comment whose .map file is not present, that is typically a warning not a hard error. Only a non-zero exit code or a ValueError is a real failure.

If collectstatic warns about missing source map files (e.g. html-to-image.min.js.map), that is a soft warning — collectstatic still exits 0 and the deploy proceeds.

**Step E — Verify both files are picked up:**

    ls staticfiles/planner/js/vendor/joint.min.js 2>/dev/null && echo OK joint
    ls staticfiles/planner/js/vendor/html-to-image.min.js 2>/dev/null && echo OK h2i

(STATIC_ROOT is `staticfiles/` per ShowStack settings; both echoes should print OK).
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && ls -la planner/static/planner/js/vendor/joint.min.js planner/static/planner/js/vendor/html-to-image.min.js && python manage.py collectstatic --noinput 2>&1 | tail -5</automated>
  </verify>

  <acceptance_criteria>
    - File planner/static/planner/js/vendor/joint.min.js exists with size > 100000 bytes
    - File planner/static/planner/js/vendor/html-to-image.min.js exists with size > 10000 bytes
    - `grep -c "joint" planner/static/planner/js/vendor/joint.min.js` returns greater than zero
    - `grep -c "htmlToImage\|html-to-image" planner/static/planner/js/vendor/html-to-image.min.js` returns greater than zero
    - `python manage.py collectstatic --noinput` exits 0
    - `ls staticfiles/planner/js/vendor/joint.min.js` succeeds after collectstatic
    - `ls staticfiles/planner/js/vendor/html-to-image.min.js` succeeds after collectstatic
  </acceptance_criteria>

  <done>
    Both vendor JS files downloaded verbatim from their canonical CDN URLs, committed to planner/static/planner/js/vendor/, and verified to pass `collectstatic --noinput` without errors. Files are unmodified (MPL-2.0 compliance) and present in STATIC_ROOT after collectstatic.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Create THIRD_PARTY_LICENSES.txt + correct PROJECT.md MIT references</name>
  <files>THIRD_PARTY_LICENSES.txt, .planning/PROJECT.md</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (sections: "THIRD_PARTY_LICENSES.txt", ".planning/PROJECT.md — correct MIT → MPL-2.0")
    - .planning/research/STACK.md (section: "License: MPL-2.0 (Not MIT) — What This Means")
    - .planning/research/PITFALLS.md (Pitfall 11 — JointJS License Is MPL 2.0, Not MIT)
    - .planning/PROJECT.md (lines 51 and 100 specifically — confirm exact wording before edit)
  </read_first>

  <behavior>
    - File THIRD_PARTY_LICENSES.txt exists at project root (NOT inside planner/ or .planning/)
    - The file lists @joint/core 4.2.4 as MPL-2.0, html-to-image 1.11.11 as MIT, and Sortable.js as MIT
    - Each entry includes: package name + version, license name, source URL, vendored-as path, "Modifications: None" line
    - .planning/PROJECT.md no longer contains the word "MIT" adjacent to JointJS
    - .planning/PROJECT.md contains "MPL-2.0" in the two locations where "MIT" was previously paired with JointJS
    - All other content of PROJECT.md is preserved (no accidental deletions or reformatting of other sections)
  </behavior>

  <action>
**Step A — Create THIRD_PARTY_LICENSES.txt at project root:**

Write a new file at `/Users/charlielawsonmacair/DjangoProjects/audiopatch/THIRD_PARTY_LICENSES.txt` with the following exact content:

    # Third-Party Licenses
    # ShowStack — Lawson Design & Engineering

    ## @joint/core 4.2.4

    License: Mozilla Public License 2.0 (MPL-2.0)
    Source: https://github.com/clientIO/joint
    Vendored as: planner/static/planner/js/vendor/joint.min.js
    Modifications: None. File vendored unmodified.

    Notes: MPL-2.0 is a file-level weak copyleft license. ShowStack does NOT
    modify joint.min.js — it is served verbatim from the @joint/core 4.2.4 npm
    distribution. Any future need to patch JointJS behavior MUST be implemented
    via the public JointJS API in separate ShowStack files; do not edit
    joint.min.js directly.

    ## html-to-image 1.11.11

    License: MIT
    Source: https://github.com/bubkoo/html-to-image
    Vendored as: planner/static/planner/js/vendor/html-to-image.min.js
    Modifications: None. File vendored unmodified.

    ## Sortable.js (existing)

    License: MIT
    Source: https://github.com/SortableJS/Sortable
    Vendored as: planner/static/planner/js/vendor/Sortable.min.js
    Modifications: None. File vendored unmodified.

Use the Write tool with the exact path `/Users/charlielawsonmacair/DjangoProjects/audiopatch/THIRD_PARTY_LICENSES.txt` and the content above (no leading 4-space indent on the actual file content — those indents in this action block are markdown code-fence indents, not file content).

**Step B — Correct the two MIT references in .planning/PROJECT.md:**

First, confirm exact line content:

    grep -n "JointJS\|MIT" /Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/PROJECT.md

Expected matches (per pre-flight verification):
- Line 51: `- Drag-and-drop canvas powered by **JointJS core** (vanilla JS, MIT) — matches ShowStack's no-framework frontend`
- Line 100: `| JointJS core (MIT) chosen over drawio iframe and maxGraph for v2.2 | Vanilla-JS drop-in matches ShowStack's no-framework frontend; iframe-embed loses native feel and complicates click-through-to-record; maxGraph requires TS build | Locked 2026-05-19 |`

Use the Edit tool to replace each MIT reference exactly. For line 51, change:

    `(vanilla JS, MIT)`

to:

    `(vanilla JS, MPL-2.0)`

For line 100, change:

    `JointJS core (MIT) chosen over drawio iframe`

to:

    `JointJS core (MPL-2.0) chosen over drawio iframe`

These are single targeted string replacements. Do NOT rewrite the surrounding paragraphs or reformat the markdown table — preserve all other characters exactly.

**Step C — Verify:**

After the edits, re-grep to confirm zero MIT references remain attached to JointJS:

    grep -n "JointJS.*MIT\|MIT.*JointJS" /Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/PROJECT.md

The above command must return zero lines (exit code 1 from grep). And:

    grep -n "JointJS.*MPL-2.0\|MPL-2.0.*JointJS" /Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/PROJECT.md

Must return at least 2 lines (the two corrected mentions).

Note: PROJECT.md may still mention MIT in OTHER contexts (e.g. html-to-image MIT, Sortable.js MIT). Those are factually correct and must NOT be changed. The replacement targets ONLY the two existing occurrences where MIT is incorrectly associated with JointJS.
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && test -f THIRD_PARTY_LICENSES.txt && grep -c "Mozilla Public License 2.0" THIRD_PARTY_LICENSES.txt && ! grep -E "JointJS.*MIT|MIT.*JointJS" .planning/PROJECT.md</automated>
  </verify>

  <acceptance_criteria>
    - File THIRD_PARTY_LICENSES.txt exists at /Users/charlielawsonmacair/DjangoProjects/audiopatch/THIRD_PARTY_LICENSES.txt (project root, NOT inside any subdirectory)
    - `grep -c "Mozilla Public License 2.0" THIRD_PARTY_LICENSES.txt` returns 1
    - `grep -c "@joint/core 4.2.4" THIRD_PARTY_LICENSES.txt` returns 1
    - `grep -c "html-to-image 1.11.11" THIRD_PARTY_LICENSES.txt` returns 1
    - `grep -c "Modifications: None" THIRD_PARTY_LICENSES.txt` returns 3 (one per vendored library)
    - `grep -cE "JointJS.*MIT|MIT.*JointJS" .planning/PROJECT.md` returns 0
    - `grep -cE "JointJS.*MPL-2.0|MPL-2.0.*JointJS" .planning/PROJECT.md` returns at least 2
  </acceptance_criteria>

  <done>
    THIRD_PARTY_LICENSES.txt is committed at project root with MPL-2.0 attribution for @joint/core and MIT attribution for html-to-image and Sortable. .planning/PROJECT.md no longer falsely states JointJS is MIT — both occurrences (lines 51 and 100) now correctly state MPL-2.0. All other PROJECT.md content preserved verbatim.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| External CDN (jsdelivr/cdnjs) → planner/static/planner/js/vendor/ | Third-party JS code being committed into the repo; supply-chain risk surface |
| Whitenoise → browser | Vendored JS served to authenticated users; same-origin to ShowStack |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-06 | Tampering | Vendored joint.min.js could be modified post-download (supply chain) | mitigate | Download from canonical jsdelivr CDN with pinned version (`@joint/core@4.2.4`). The file is committed to git so any future modification is reviewable in diff. THIRD_PARTY_LICENSES.txt explicitly documents "Modifications: None" — any future PR that modifies the file violates the documented invariant and is auditable. |
| T-07-07 | Tampering | Vendored html-to-image.min.js (same supply-chain risk as joint) | mitigate | Same as above — pinned version (1.11.11) from cdnjs (or jsdelivr fallback), committed verbatim, "Modifications: None" attestation in THIRD_PARTY_LICENSES.txt. |
| T-07-08 | Information Disclosure | THIRD_PARTY_LICENSES.txt is public via Whitenoise / GitHub | accept | This is the intended behavior. MPL-2.0 attribution requires the license file be discoverable. The file contains only public license metadata (no secrets). |
| T-07-09 | Legal / Compliance | MPL-2.0 source-disclosure obligation on JointJS modifications | mitigate | "Modifications: None" attestation in THIRD_PARTY_LICENSES.txt + planner-level rule documented (action Step C of Task 1) that future patches MUST go through the public JointJS API, not direct file edits. PROJECT.md correction prevents future developers relying on the false "MIT" claim. |
| T-07-10 | Denial of Service | Whitenoise collectstatic could fail on bundled source-map references and silently block Railway deploys | mitigate | Plan 02 task 1 explicitly runs `collectstatic --noinput` locally before Plan 04 templates reference the vendor files. PITFALLS.md Pitfall 12 documents this exact failure mode and the gate test. Soft warnings about missing .map files are acceptable; only ValueError / non-zero exit is a hard failure. |

## Non-Security Compliance Note

The PROJECT.md correction (Task 2 Step B) is a documentation-accuracy fix, not a security mitigation in the STRIDE sense. It is captured here because the false MIT claim could lead future contributors to make MPL-2.0-violating modifications to joint.min.js. Fixing it now closes that path.
</threat_model>

<verification>
After both tasks complete, verify the full vendor + licensing posture:

    cd /Users/charlielawsonmacair/DjangoProjects/audiopatch
    ls planner/static/planner/js/vendor/joint.min.js planner/static/planner/js/vendor/html-to-image.min.js
    test -f THIRD_PARTY_LICENSES.txt && echo "OK licenses file present"
    grep -c "Mozilla Public License 2.0" THIRD_PARTY_LICENSES.txt   # returns 1
    ! grep -E "JointJS.*MIT|MIT.*JointJS" .planning/PROJECT.md       # returns nothing (no false MIT)
    python manage.py collectstatic --noinput                         # exits 0
</verification>

<success_criteria>
- planner/static/planner/js/vendor/joint.min.js present (unmodified @joint/core 4.2.4 UMD bundle)
- planner/static/planner/js/vendor/html-to-image.min.js present (unmodified html-to-image 1.11.11 UMD bundle)
- Both files have non-trivial size and pass content sanity checks
- THIRD_PARTY_LICENSES.txt at project root with all three vendored libraries attributed
- .planning/PROJECT.md contains zero references to "JointJS … MIT" — both former occurrences corrected to "MPL-2.0"
- `python manage.py collectstatic --noinput` exits 0 with no errors related to the new vendor files
</success_criteria>

<output>
After completion, create `.planning/phases/07-foundation-crud-editor-shell/07-02-SUMMARY.md` documenting:
- Exact byte sizes of the two downloaded vendor files
- collectstatic output (last 5 lines)
- The two PROJECT.md lines before/after correction (paste both for audit trail)
- Confirmation no .map file warnings caused a non-zero exit
</output>
