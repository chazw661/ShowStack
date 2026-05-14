---
phase: 04-nuendo-live-export
plan: 06
subsystem: multitrack-session-builder
tags: [forms, templates, ui-gate-removal, atomic-commit]
requires:
  - MultitrackSession.TARGET_DAW_CHOICES (planner/models.py:978-981) — already includes 'nuendo_live' from Phase 1; the model side never needed Phase-4 changes.
  - MultitrackSessionForm dynamic radio loop (already shipping pre-Phase-4 at new_session.html:66-71).
provides:
  - Engineers can pick "Nuendo Live" as target_daw on the new-session form. Form validation accepts the value end-to-end.
affects:
  - planner/forms.py — MultitrackSessionForm.__init__ no longer strips the nuendo_live choice; class no longer defines clean_target_daw.
  - planner/templates/planner/multitrack/new_session.html — Target DAW radio group now sourced 100% from the dynamic {% for radio in form.target_daw %} loop; no static disabled placeholder.
tech_stack:
  added: []
  patterns:
    - "Atomic three-place gate removal in a single commit (RESEARCH Pitfall 6)."
    - "Trust ModelForm choice propagation from TARGET_DAW_CHOICES — no manual choices override remains."
key_files:
  created: []
  modified:
    - planner/forms.py
    - planner/templates/planner/multitrack/new_session.html
decisions:
  - "Removed all three Phase 1 belt-and-suspenders gates in ONE atomic commit (c53a9ce), per CONTEXT.md D-12 and RESEARCH Pitfall 6. Splitting across commits would have left the choice half-broken in the intermediate state."
  - "Did NOT touch the model layer: MultitrackSession.TARGET_DAW_CHOICES already enumerates both values. Phase 1 Plan 01 had already cleaned up the stale '# disabled in UI until Phase 4 ships' comment at planner/models.py:980 (confirmed: comment is absent on lines 977-982)."
  - "Did NOT add any new tests asserting nuendo_live acceptance. Verification is the existing 95-test planner suite (still 95/95 passing) plus an inline shell-driven form-instantiation check — see Verification Notes. No Phase 1 test asserted the ValidationError, so nothing needed updating."
metrics:
  duration_seconds: 128
  duration_human: "~2 minutes"
  completed_date: "2026-05-14"
  tasks_total: 1
  tasks_completed: 1
  files_modified: 2
  files_created: 0
  lines_removed: 26
  lines_added: 0
  commits: 1
---

# Phase 4 Plan 06: Enable nuendo_live Target DAW Summary

Atomic three-place removal of the Phase 1 form gates that disabled
`nuendo_live` as a `target_daw` choice on the new-session form. One file
in `planner/forms.py` (two deletions inside `MultitrackSessionForm`), one
file in the new-session template (one deletion of a static placeholder),
all landed in a single commit (c53a9ce) to avoid the intermediate
half-broken state RESEARCH Pitfall 6 warns about.

## One-liner

Removed three Phase 1 form gates that disabled `nuendo_live` — choices
restriction, `clean_target_daw` ValidationError, and static disabled
template radio — in one atomic commit, so the new-session form now
renders and accepts both `reaper` and `nuendo_live` target_daw values
via Django's standard `ModelForm` choice propagation.

## What Was Built

### Deletion 1 — `planner/forms.py` choices restriction

Removed 8 lines from `MultitrackSessionForm.__init__` that stripped
`nuendo_live` from `self.fields['target_daw'].choices` via a
list-comprehension assignment. Surrounding code flows from the
`template`-queryset block directly into the required-asterisk styling
block (no blank-line drift, no whitespace artifacts).

### Deletion 2 — `planner/forms.py` `clean_target_daw` method

Removed the entire 9-line `clean_target_daw` method (docstring,
ValidationError block, return) from `MultitrackSessionForm`. The class
now flows from `__init__` directly into `clean_name`. The
`'Nuendo Live export ships in v2.0 Phase 4. Pick Reaper for now.'`
error message is gone from the codebase.

### Deletion 3 — `new_session.html` static disabled radio

Removed 7 lines from the new-session template: the
`{# Nuendo Live disabled until Phase 4 ships ... #}` comment plus the
`<label class="mts-radio-option" title="...">` block containing the
inert `<input type="radio" disabled>` and the
`mts-radio-label--disabled` span. The dynamic
`{% for radio in form.target_daw %}` loop (lines 66-71) is the sole
renderer of the two radio inputs after this change.

## Atomicity (Critical — RESEARCH Pitfall 6)

All three deletions landed in commit **c53a9ce**, single message
`feat(04-06): enable nuendo_live target_daw atomically (3-place gate removal)`.
This is the most important property of this plan: removing only one
or two gates would have produced a confusing intermediate state:

| Removed alone   | Resulting bug                                                |
| --------------- | ------------------------------------------------------------ |
| Gate 1 only     | User picks Nuendo Live → server raises ValidationError       |
| Gate 2 only     | "Select a valid choice" — `nuendo_live` stripped from form   |
| Gate 3 only     | Disabled placeholder still renders alongside enabled radios  |

The single-commit removal flips the choice from "disabled" to "fully
enabled" with no intermediate broken state.

**Future archaeology note:** If the gate ever needs to resurface (e.g.
Nuendo Live exporter rolled back), the inverse operation is "re-add the
three gates per RESEARCH Pitfall 6, also in one commit." Searching for
"Pitfall 6" or "three places gate nuendo_live" in the planning archive
will surface this plan and the original RESEARCH note.

## Decisions Made

### D-12 implementation (gate removal)
Located all three gates exactly where RESEARCH §"Pitfall 6" predicted
(`forms.py:1192-1199`, `forms.py:1209-1217`, `new_session.html:72-78`).
No new gates surfaced; no fourth-place gate hiding in JS / view / URL
layer. The grep audit (10 grep checks, all returning 0 except the
dynamic loop returning 1) confirms exhaustive removal.

### Bonus cleanup check (models.py:980 comment)
RESEARCH Pitfall 6 mentioned a stale `# disabled in UI until Phase 4
ships` comment at `planner/models.py:980` as a possible additional
cleanup target. Verified by reading `planner/models.py:975-984` that
Plan 04-01 already removed this comment (STATE.md "From Phase 04 Plan
01" entry confirms it: *"Stale `# disabled in UI until Phase 4 ships`
comment at planner/models.py:980 updated"*). No additional edit needed
this plan.

### Test strategy
No new test added asserting `nuendo_live` is now accepted by the form.
Reasons:
1. Plan 04-04's `test_nuendo_live_export.py` already builds sessions
   with `target_daw='nuendo_live'` and exports them — that path now
   has fewer guards but the exporter logic was already independent of
   the form gate.
2. No Phase 1 test asserted the `ValidationError` (grep verified). So
   nothing needed updating — the existing suite is the safety net.
3. The 95-test planner suite still passes (95/95). If any future test
   regresses on form choices, the suite will catch it.

Verified instead via an inline shell-driven form-instantiation check
(see Verification Notes below) — kept as a one-off proof, not committed
as a test file.

## Verification Notes

All acceptance criteria checks passed:

```
grep -c 'def clean_target_daw' planner/forms.py                                       → 0
grep -c 'nuendo_live' planner/forms.py                                                → 0
grep -c 'Nuendo Live export ships in v2.0' planner/forms.py                           → 0
grep -c 'Disable Nuendo Live in Phase 1' planner/forms.py                             → 0
grep -c "fields\['target_daw'\]\.choices" planner/forms.py                            → 0
grep -c 'disabled until Phase 4 ships' planner/templates/planner/multitrack/new_session.html  → 0
grep -c '<input type="radio" disabled>' planner/templates/planner/multitrack/new_session.html → 0
grep -c 'coming v2.0' planner/templates/planner/multitrack/new_session.html           → 0
grep -c 'mts-radio-label--disabled' planner/templates/planner/multitrack/new_session.html     → 0
grep -c '{% for radio in form.target_daw %}' planner/templates/planner/multitrack/new_session.html → 1
```

Django + migration checks:
- `python manage.py check` → System check identified no issues (0 silenced).
- `python manage.py makemigrations planner --dry-run` → No changes detected in app 'planner'.
- `python manage.py test planner -v 1` → Ran 95 tests in 4.750s. OK.

Live form behavior (driven by an inline `manage.py shell`-style script,
not committed):
- `MultitrackSessionForm(data={'target_daw': 'nuendo_live', ...}).is_valid()` → True.
- `MultitrackSessionForm(data={'target_daw': 'reaper', ...}).is_valid()` → True.
- `MultitrackSessionForm(data={'target_daw': 'protools', ...}).is_valid()` → False (T-04-20 mitigation intact: Django ChoiceField still rejects values outside `TARGET_DAW_CHOICES`).
- `form.fields['target_daw'].choices` keys → `['reaper', 'nuendo_live']` (both present, in the order declared on the model).

## Deviations from Plan

None — plan executed exactly as written. The three deletions matched
the line ranges given in PLAN.md and PATTERNS.md verbatim. No
auto-fixes (Rules 1-3) and no architectural questions (Rule 4) were
needed.

## Threat Model Compliance

PLAN.md `<threat_model>`:

| ID      | Disposition | Status                                                                      |
| ------- | ----------- | --------------------------------------------------------------------------- |
| T-04-20 | mitigate    | Mitigated — Django's stdlib ChoiceField still rejects values not in `TARGET_DAW_CHOICES`. Verified inline: `target_daw='protools'` is rejected with `form.is_valid() → False`. |
| T-04-21 | accept      | Accepted — `nuendo_live` is now accepted by the form. Existing sessions unaffected (this plan changes no data). |

No new threat surface introduced. The change is a pure deletion that
removes restrictions on an already-existing model choice; no new
endpoints, no new auth paths, no new file or schema access.

## Files Changed

| File                                                       | Lines removed | Lines added |
| ---------------------------------------------------------- | ------------- | ----------- |
| planner/forms.py                                           | 19            | 0           |
| planner/templates/planner/multitrack/new_session.html      | 7             | 0           |
| **Total**                                                  | **26**        | **0**       |

## Commits

| Hash    | Type | Message                                                              |
| ------- | ---- | -------------------------------------------------------------------- |
| c53a9ce | feat | `feat(04-06): enable nuendo_live target_daw atomically (3-place gate removal)` |

## TDD Gate Compliance

Plan type is `execute`, not `tdd`. RED/GREEN/REFACTOR gates do not
apply. The plan instead relies on Phase 1's existing 95-test planner
suite plus an inline live-behavior check for safety — both passed.

## Known Stubs

None — no stub patterns introduced. The change is a pure deletion;
existing data flow (`form.target_daw` → `TARGET_DAW_CHOICES` →
template radio loop) is now the sole path and was already in place
pre-Phase-4 (Phase 1 belt-and-suspenders-ed restrictions on top of it
rather than replacing it).

## Self-Check: PASSED

- planner/forms.py modifications verified: present (commit c53a9ce, 19 lines removed).
- planner/templates/planner/multitrack/new_session.html modifications verified: present (commit c53a9ce, 7 lines removed).
- Commit c53a9ce verified: `git log --oneline | grep c53a9ce` → found.
- No new files claimed; nothing to verify on creation.
- All 10 grep checks confirmed.
- Django checks confirmed.
- Test suite confirmed (95/95).
- Live form-behavior check confirmed.
