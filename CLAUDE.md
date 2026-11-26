# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**ShowStack** is a Django 5.x multi-tenant SaaS platform for professional live audio production management, deployed at **https://showstack.io**.

- **Sole developer:** Charlie Lawson
- **Legal owner:** Lawson Design & Engineering (USPTO trademark Class 42, filed March 19, 2026)
- **Target users:** A1/lead live audio engineers working corporate events, tours, and broadcast with Yamaha consoles, L'Acoustics amplification, Dante networking, and Clear-Com intercom systems.

---

## Development Commands

```bash
# Local dev
python manage.py runserver
python manage.py makemigrations
python manage.py migrate

# Production (Railway)
railway login --browserless
railway logs
railway run python manage.py <command>   # run Django mgmt commands against prod
```

**Do not** run destructive SQL against Railway Postgres without confirming with Charlie first.

### Running tests

```bash
# Fast iteration: no migrations, tables built straight from the models
python manage.py test --settings=audiopatch.test_settings

# Before opening any PR: the plain suite, migrations on
python manage.py test
```

Fast iteration: `--settings=audiopatch.test_settings`. Before opening any PR,
run the plain suite (migrations on). Mandatory for PRs that add a migration.

**Working rule:** while iterating, run only the affected module's tests, e.g.
`python manage.py test planner.tests.test_amp_profiles --settings=audiopatch.test_settings`.
Run the full suite (both modes, ~17 min) once, before opening the PR.

**Browser gate:** every Playwright module is named `*_browser.py` (13 today),
so one glob runs them all; they are skipped without `SS_BROWSER_TESTS=1`:

```bash
SS_BROWSER_TESTS=1 python manage.py test planner.tests --pattern "*_browser.py" \
    --settings=audiopatch.test_settings
```

Name any new module that reads `SS_BROWSER_TESTS` `*_browser.py`:
`planner.tests.test_browser_gate` fails otherwise. Some of them also hold
plain tests (the Mic Overview ones), which still run in the normal suites.

The two modes differ: `test_settings` skips migrations, so seeded rows (Source
Hardware options, the amp catalogue) are absent there and present in the plain
run. Tests must pass in both, so assert on the rows a test creates, never on
whole-table counts.

### Running management commands against prod — without the database proxy

**Use this, not the proxy, for anything that only needs to run a management
command.** It never exposes Postgres to the internet and puts no credentials on
your laptop. The app container already holds `DATABASE_URL` pointing at
`postgres.railway.internal`, which resolves on Railway's private network, so a
command run *inside* the container reaches the database directly:

```bash
# read-only reports (safe to run any time)
railway ssh --service ShowStack -- /opt/venv/bin/python /app/manage.py report_duplicate_amp_channels
railway ssh --service ShowStack -- /opt/venv/bin/python /app/manage.py report_duplicate_mic_assignments

# narrow to one project / session
railway ssh --service ShowStack -- /opt/venv/bin/python /app/manage.py report_duplicate_amp_channels --project 3
railway ssh --service ShowStack -- /opt/venv/bin/python /app/manage.py report_duplicate_mic_assignments --session 24

# or get a shell and stay there
railway ssh --service ShowStack
cd /app && /opt/venv/bin/python manage.py report_duplicate_amp_channels
```

Four things that will otherwise waste your time:

1. **`/opt/venv/bin/python`, not `python`.** The SSH session's `PATH` is
   `/nix/var/nix/profiles/default/bin:...`, which has a bare `python3` *without
   Django* — `python manage.py` there fails with "Couldn't import Django". The
   deploy's `startCommand` gets a different environment, which is why it can
   say plain `python`. Dependencies live in `/opt/venv`.
2. **`/app/manage.py`, not `manage.py`**, unless you `cd /app` first.
3. **`railway run` does NOT work for this.** It runs the command *locally* with
   the service's variables injected, and `postgres.railway.internal` does not
   resolve off Railway's network. `railway ssh` runs inside the container;
   that is the difference.
4. **The command has to be deployed first.** `railway ssh` runs whatever is
   live, which is `main`. A command that exists only on a branch is "Unknown
   command" until the PR merges and Railway finishes redeploying — check with
   `railway ssh --service ShowStack -- /opt/venv/bin/python /app/manage.py help`.

`--service ShowStack` is explicit on purpose; the repo directory is linked to
that service so it can be omitted, but being wrong about which service you are
in is not a mistake worth risking. Confirm with `railway status`.

For a cleanup command, the same invocation plus `--apply` (every cleanup here
is a dry-run without it). **Take a Railway Postgres backup first**, and run the
dry-run and read it before you add `--apply`.

### Connecting to prod Postgres from your laptop

This is for a local `psql` session or a tool that must speak to Postgres from
your machine. If you only need to run a management command, use `railway ssh`
as above instead and leave the proxy off.

**Public access to the Postgres service is disabled, and that is the default
state.** The app service only receives `DATABASE_URL` pointing at
`postgres.railway.internal`, which does not resolve outside Railway's network —
so nothing on your laptop can reach the production database until public
networking is deliberately turned on.

When a local `psql` or a one-off management command is genuinely needed:

1. Railway dashboard → **Postgres** service → **Settings → Networking** → enable
   the TCP proxy. Railway allocates a `*.proxy.rlwy.net` host and port; the pair
   may differ every time it is enabled, so never hard-code it anywhere — read it
   from `DATABASE_PUBLIC_URL` instead.
2. Run what you need:
   ```bash
   railway run --service Postgres psql "$DATABASE_PUBLIC_URL"

   # one-off Django management command against prod
   railway run --service Postgres bash -c \
     'DATABASE_URL="$DATABASE_PUBLIC_URL" ./venv/bin/python manage.py <command>'
   ```
   `--service Postgres` matters: `DATABASE_PUBLIC_URL` exists only on the
   Postgres service, not the app service. The re-alias is because
   `dj_database_url.config()` reads `DATABASE_URL` and nothing else.
3. **Disable the proxy again as soon as you are done.** While it is on, the
   production database is reachable from the public internet behind nothing but
   the Postgres password.

---

## Tech Stack

- **Backend:** Django 5.x, PostgreSQL (Railway-managed), `dj_database_url` (SQLite fallback for local dev)
- **Config:** `python-decouple` — secrets via `.env` locally, Railway env vars in prod
- **Static files:** Whitenoise with hashed filenames (`collectstatic` runs in the start command on every deploy, see Deployment)
- **Email:** Resend for transactional mail (API key in Railway env vars, not committed)
- **Hosting:** Railway — push to `main` triggers automatic redeploy
- **Admin UI theming:** `django-admin-interface` + `colorfield`

---

## Project Structure

Three Django apps inside the `audiopatch` project:

| App | Purpose |
|---|---|
| `planner` | Core app — all audio equipment models, views, admin, exports. ~95% of the codebase. |
| `accounts` | User registration, login, project invitations, user profiles |
| `marketing` | Public-facing pages (home, features, pricing, terms, privacy) |

### Key files (large, monolithic — know where to look)

| File | Lines | Contains |
|---|---|---|
| `planner/models.py` | ~4500 | All equipment models, Project/ProjectMember. Also contains orphan `DanteConsoleConfig`/`DanteDeviceConfig`/`DanteSubscription` from the scrapped Dante Subscription Planner — models and migrations remain, no views or templates. |
| `planner/views.py` | ~5700 | All planner views (mic tracker, COMM config, power dist, IP, exports, etc.) |
| `planner/admin.py` | ~6000 | All ModelAdmin classes, inlines, custom change_list actions |
| `planner/admin_site.py` | — | `ShowStackAdminSite` class → `showstack_admin_site` instance |
| `planner/admin_ordering.py` | — | Monkey-patches `get_app_list` for sidebar ordering + viewer filtering |
| `planner/middleware.py` | — | `CurrentProjectMiddleware` — session-based project scoping |
| `planner/context_processors.py` | — | `user_projects` — injects project list into all templates |
| `planner/utils/yamaha_export.py` | — | Rivage PM CSV export (11 files) |
| `planner/utils/pdf_exports/` | — | PDF generation per module (ReportLab) |

### URL routing

- `/admin/` → `showstack_admin_site.urls` (custom admin)
- `/audiopatch/` → `planner.urls` (all planner views)
- `/m/` → `planner.mobile_urls` (mobile interface)
- `/` → `marketing.urls` + `accounts.urls`
- `/dashboard/` → main dashboard view

### Templates

Two template directories (both in `TEMPLATES['DIRS']`):
- `templates/` — project-level: admin overrides, marketing, mobile, accounts
- `planner/templates/` — app-level (via `APP_DIRS`)

---

## Architecture

### Session-based project resolution
The active project is resolved from the session via `CurrentProjectMiddleware`. Views and querysets scope themselves to `request.current_project` rather than taking a project ID in the URL. **Follow this pattern** — don't introduce URL-based project routing.

### Role-based permissions
Implemented via Django groups and `BaseEquipmentAdmin`:
- `superuser` — full access
- `premium owner` — paying project owner
- `editor` — can edit project data
- `viewer` — read-only

### Custom admin site
- **Always register models on `showstack_admin_site`, NOT `admin.site`.**
- `admin_ordering.py` controls the sidebar: `SECTIONS` (Project, System, Comms, Mics, Show, Libraries, Admin) lists every row in order, `GROUPS` the rows that fold under a parent, `SUPERUSER_ONLY` the rows hidden from everyone else (sidebar only, permissions unchanged), `NOT_IN_SIDEBAR` the registered models deliberately left out. **Whenever a new admin-registered model is added, put it in a section or in `NOT_IN_SIDEBAR`** -- it is not listed otherwise, and `planner.tests.test_sidebar` fails until it is placed. That test also pins the whole sidebar for superuser / owner / editor / viewer. Folding rows are matched by model name (`data-sidebar-parent` in `templates/admin/app_list.html`), never by link text.

### Deployment
- Pushing to `main` on GitHub triggers automatic Railway redeploy.
- Solo development typically goes straight to `main`; use feature branches only when the work is risky or spans multiple sessions.
- **Railway deploy settings live in the ShowStack service's settings on Railway, and nowhere else.** `.railway/railway.ts` (Railway Infrastructure as Code) mirrors them in the repo; `railway.json` is gone (Railway stopped reading those files on 2026-12-01). The file declares the ShowStack service only (a named partial, so Postgres is not managed from this repo): the Nixpacks builder, the start command, the `showstack.io` domain, one replica, and the `showstack-volume` mount at `/data/media`. No variables are in the file (`variables: { managed: false }`); they stay in Railway.
- **The start command** runs: `collectstatic --noinput && migrate && create_initial_superuser && setup_user_groups && load_amp_profiles && load_cabinets && load_drive_capacity && gunicorn`.
- **To change a deploy setting** (the start command included): edit `.railway/railway.ts`, run `railway config plan`, read it for deletions and for the volume, then `railway config apply` — Charlie runs these. **Pushing the file does nothing by itself**: Railway does not read `.railway/` during deploys. A setting changed in the dashboard instead leaves the file out of date; `railway config plan` shows the difference.
- **Restart policy is dashboard-only.** `railway.ts` has no field for it, so it is whatever the service's settings in the Railway dashboard say (the old `railway.json` asked for ON_FAILURE, 10 retries). Change it there.
- **Never run `railway config pull --include-variables`.** It decrypts variables and writes their values, secrets included, into `railway.ts`. This repo is public.
- `railway.ts` imports `railway/iac`; `npm install railway` locally to plan or apply, and never commit `node_modules/`, `package.json` or a lockfile. There is no `Procfile` and no `railway.json`.

---

## Modules

| Module | Notes |
|---|---|
| Consoles | Yamaha Rivage PM series CSV export emits 11 files in exact Rivage PM Editor format |
| Devices | Sidebar "Devices" (model `Device`). `Device.kind`: `io` (stage boxes, interfaces: the I/O grids, patched to consoles / amps / processors) or `comm` (an intercom main station, e.g. Arcadia; nothing to do with COMM Config or the beltpack models). `Device.dante_network` is free text on both, compared with `Device.network_key`. A comm device's `input_count` / `output_count` are its Dante ins / outs (`DeviceInput` / `DeviceOutput` rows); `CommPort` holds its 4-wire and 2-wire ports. Its patch is edited only on its own page ("Comms patch" grids posted with the device form: `connections/comm_patch.py` `build` / `apply`, `forms.CommDeviceForm`, `templates/admin/planner/device/change_form.html`): datalist text that must be exactly one entry, stored as `Connection` rows running the way the signal does (`Connection.COMM_LINKS`: Dante Out → an I/O OUTPUT, an I/O INPUT → Dante In, Dante Out → another comm device's Dante In, 4W send → an I/O INPUT, an I/O OUTPUT → 4W receive); 2W is text on `CommPort`. No stored text copy. Other devices show the link read-only under the port (`comm_patch.port_notes`). Comm ports are excluded from `console_patch`, `console_patch_edit`, `device_patch`, `link_device_inputs_by_name` and the amp / processor pickers (`device__kind='io'`); `matchers.ProjectIndex` keeps them out of `device_inputs` / `device_outputs`. Wiring diagram: comm edges carry `comm: true`; warning kind `dante_network`. The Comms tab (`connections/comms_tab.py` `comms_view` → `layout(scheme=COMMS_SCHEME)`, `_CommsBuilder`) draws them, one line per port, in three columns (To comms / Comm devices / From comms) with every box in port-row mode (`Box.out_slot` beside `in_slot`: a 4W row's receive comes in on the left and its send leaves on the right at one height); a device patched both ways is two boxes so every route runs rightward; 2W text is a `destination` node. The other tabs only list comm edges in the Connections table (keys C1…, "see the Comms tab"). The project graph and its digest are untouched by the tab: the split happens in the view. Dante tab: boxes every device on Dante (`tabs.on_dante`: Console connection dante, or `dante_network` set, or kind comm), console link or not, under a header per Dante network (`tabs._network_groups` → `node['group']`, "No network set" last, consoles ungrouped, no headers until a network is set). The "no Console connection set" banner (`tabs.unset_devices`) lists only I/O devices with a console link (A or B) and a blank Console connection. Overview and Dante tabs: a device whose only links are comms links gets a last box line "N comms patches · see Comms tab" (`tabs.comms_notes` → node `comms_note` → `Box.note`, added in `views_wiring.tab_view`, never in the project graph; N = its comms links + its 2-wire destinations; one `<a class="wd-note" href="?view=comms">` in the SVG, plain text in the PDF). `layout()`'s default scheme is the seven columns. |
| Amplifiers | |
| System Processors | |
| PA Cable Schedule | A run's `length`/`cable` are the home run (amp to first speaker). Daisy-chain links are `PACableLink` children (migration 0241: order, Qty, cable, length, note), edited in the Links inline behind the chain-icon "Linked" toggle (`pa_cable_links.js`; no stored flag: linked = has links). A link's Qty is its own, like a fan-out's: Count never multiplies it. Every total (changelist summary, Quick Order List, CSV, System Report) iterates `pa_cable_math.entry_pieces(row)` (home run, then each link, each under its own type; never merged into the home run's footage). `test_pa_cable_unlinked_totals` pins that a run with no links totals exactly as before links existed: fix the code, not its GOLDEN. Exports list links as rows under the run ("— Link 1"; no arrow glyphs, the PDFs are Helvetica). The wiring diagram's Speaker cables tab, PDF and DXF all print `graph._pa_cable_label`, which carries the chain. |
| COMM Config | Clear-Com Arcadia + FreeSpeak II `.cca` offline config export (see COMM Config section below) |
| Mic Tracker | |
| Mic Planner | Shown to users as "Mic Planner" (sidebar label set in `admin_ordering`, just above Mic Tracker; code, URLs `/mic-plan/…`, models, help slugs and the tutorials key keep `mic_plan`; `mic-planner-*` help slugs redirect). Dashboard card (admin index, from `dashboard_stats` → `mic_plan/status.py` `day_status`): per day imported / plan version / channels used of the rig's usable channels (`channel_count`: "9 of 13 ch · 1 spare", amber "— over the rig") / walkthrough rows still open (`open_rows` = not confirmed + reopened, the page's own count) / sent or changed since; Mic Tracker's card says "Planned in Mic Planner" for a pushed day. Not on `/m/`. Showflow PDF import per ShowDay (`planner/mic_plan/`, `views_mic_plan.py`). PDF parsed in memory, never stored. Walkthrough data (PR W1, migration 0230): `ShowflowRow.bbox` = [x0, top, x1, bottom] as fractions of the page's crop box after /Rotate (`extract._box`, what pdf.js draws; pdfplumber already gives the shown frame for /Rotate 90/180/270 — `RotatedPageTests`, fixture `build_rotated_pdf`, which must pass ReportLab the size AS SHOWN (it swaps the stored MediaBox itself); None on older imports — Re-read can't add it, only a new import); `ShowflowEvent.source_rows` = the row orders a cue's words came from (more than one when it spills onto the next row/page; `parser.Event.rows`); `ShowflowImport.file_sha256` of the upload (a hash, never the file). `extract` uses `find_tables` + `Table.extract` exactly as `extract_tables` does: the switch changed no parse output on the corpus. Walkthrough PR W2 (migration 0231): row overrides `ShowflowImport.row_overrides` (`mic_plan/overrides.py`: on/off/not_on/not_off/mic per row, by person name_key) become plan input in `planning._apply_overrides` — a cued part's on/off are cues, a cue-free part's are listings/exits, `not_off` also `GroupExit.keep`, mic `Day.mic_at`; never applied unless the row's raw text is unchanged, else `override_changed` (was/now) or `override_gone` plan flags (`Day.issues`), `overrides.accept`/`drop`; kept on Replace. Which row is "the same row": `mic_plan/rowkey.py` (unique line label, else start time + fuzzy text, ties by neighbours, n-th twin, distance; corpus-checked with an inserted segment, labels on and off). Day-level `MicPlannerDayOverride`: `not_a_person` (phrase name_key; `Roster(rejected=)` drops it everywhere incl. leftovers, description and mic-list flags; `importer.reject_phrase`) and `vog` (`importer.set_vog_pack`: a ShowflowPerson with flags role 'vog', `solver.Person.fixed_rows` = the `parser.is_vog` rows, one pack first-to-last VOG line, never on stage; no pack = no VOG). `importer.same_as` = merge, or a typed new name made then merged. Source spans: `ShowflowPerson.flags['spans']` = {import: [[row order, column, start, end]]} (parser column: speaker/description/bsm; `_speaker_text` blanks rather than cuts). Line-estimate people start unconfirmed: `planning.people_to_confirm`, `importer.confirm_person` (`flags['confirmed']`, a USER_FLAG). Speaker-cell notes, list labels and "Name, Company" lists (`parser.split_cell`, `_notes`, `_company_list`) are stored per row as `ShowflowImport.warnings` kind `speaker_marks` (`importer.MARKS`): not an issue, so anything counting flags must skip it; the walkthrough shows them grey, unlocked. Rules: `docs/mic_plan/PARSING_RULES.md`. Headers are matched on letters and digits only (`extract.HEADER_ALIASES`); the Audio column is stored (`ShowflowRow.audio_text`); document-style files are detected and refused (`ShowflowError.layout`). Showflow mic numbers: `parser.mic_callouts`, by line in `flags['mics']` (a number belongs to a block, never one per person); `planning.showflow_numbers` maps them to wearings (latest entry at or before the off line), `showflow_rf` to RFs; `MicPlanSettings.showflow_numbers` compare (Review card `SHOWFLOW_CARD`, "Use the showflow's numbers" = `move_rf` edits sharing `value['batch']`, Undo removes the batch) or follow (pins outside the edit log; any log entry for that appearance beats them, `solver.Fixed.showflow`). `solver.Person.no_host` (`build_day(follow=)`, on in follow or while a Use batch is in the log, `planning._showflow_hosts`): a mic that changes in the showflow is never an all-day pack (`planning._mic_changes`); compare keeps the normal hosts rule. Draft plan: pure solver `mic_plan/solver.py` (no Django), saved by `mic_plan/planning.py` as `MicPlan` (+ appearances, assignments, A2 actions); page built from the stored plan by `mic_plan/page.py` (three views: Showflow + plan, Pack chart, Walkthrough); every A2-action wording in `mic_plan/display.py`; `plan.json` per day for the A2 schedule. Look: `static/css/mic_plan.css` (fonts self-hosted, reference `docs/mic_plan/mic_plan_theme.css`). Edits (PR 3): ordered log `MicPlanEdit` keyed by appearance key (`name_key|on line|n`, never pk), replayed as hard pins; every re-solve but "Start over" prefers the previous version's RFs (`solver.Fixed`); edit/undo = one POST per change against `MicPlan.version`. A2 schedule (PR 4): `mic_plan/schedule.py` groups one A2's stored actions by session (`solver.session_starts`) then segment; screen `mic-plan/day/<pk>/a2/?a2=N` (standalone template, read-only, current segment tapped and kept in localStorage, polls `plan.json?head=1` every 30 s and only banners a new version); PDF `mic-plan/day/<pk>/pdf/` (`utils/pdf_exports/mic_plan_pdf.py`: schedule per A2, pack sheet, review; plan header + "Printed" footer on every page, `?tz=` from the browser). Overlapping parts are one stage (warned everywhere, #169). Send to Mic Tracker (PR 5): `mic_plan/push.py` is the only Mic Plan code that writes Mic Tracker — `preview` (writes nothing) then `apply` (one transaction, refused unless the preview digest still matches); one MicSession per plan session, rows = the plan's RFs (gaps kept: `MicSession.rf_from_plan` turns off renumbering, #171), one PresenterSlot per wearing; `MicPlanPush` keeps the maps (session/row/slot keys → pks) and snapshots the next push matches and diffs against. Never write A2 fields (photo, notes the A2 typed, placement, sensitivity, output level, groups, MIC'D). Host on-stage spans: `MicPlanAppearance.stage`. Revert last push: `mic_plan/revert.py` undoes the latest non-reverted push from `MicPlanPush.before` (created/updated/deleted rows, plus `after` = what the push left, `mic_plan/mt_rows.py`); refused if Mic Tracker changed since unless "Revert anyway"; marks `summary['reverted']`, which `push.last_push` skips. Pushed session names use a plain hyphen. PR 5.4: every pushed session has a card (MicAssignment) for each channel, RF 1..N of the rig (no rig: 1..the day's highest RF); unworn ones are empty rows (no slot, blank mic type); rows go only above the top, and only without A2 data; a gapped session gets `cards_added`. Rig settings cap at 100 channels (form-level, `views_mic_plan.MAX_CHANNELS` = `push.MAX_ROWS`). PR 5.3: de-mic helpers per segment (0–3, `solver.Segment.helpers`), stored in `ShowflowImport.break_overrides[line]['helpers']` beside the Break override (`planning.set_helpers`); in the solver each is a worker who only de-mics, starting inside that segment; their actions are MicPlanA2Action with `a2_index` 0 — ALWAYS test with `solver.is_helper()`, never index an A2 list with it; busy minutes in `plan.helper_busy` / segment `helper_busy`; `_suggest_helpers` adds "1 de-mic helper at …" to late/tight/break/shortage cards on Generate only; schedule `?a2=helpers` (never `?a2=0`). PR 5.2: cue-free parts use exit / re-entry / group-exit lines (`parser.exits_and_entries`, `parser.group_exit`; `solver._staged`), hosts still by the old count; people added by hand live in `ShowflowPerson.flags['added']` (by line label, `importer.add_people` / `resolve_added`). PR 5.1: RFs are the rig's channel numbers (`MicPlanSettings.wireless_channels` / `handheld_channels` = the last N / `spare_handhelds` = the last N of those; blank channels = no rig, numbered as needed). `solver.Rig`. PR 5.1b: the channels but the spares are ONE pool either type takes (`Rig.limit`); `handheld_channels` is only a zone. At the limit a mic takes a free pack of the other type rather than go over (a transmitter swap, `_Pack.swaps` → plan pack `swaps`, Review `swap` at a break / `swap_mid`, an A2 schedule SWAP line, the pushed slot note); `_number`: body lowest free, HH highest free, over only when every non-spare channel is taken; a channel outside its zone is a `rig_use` card. A move keeps the wearer's mic type (only Switch changes it; old logs replay as stored). A pin only misfits on a spare or past the rig (`planning._fixed`); a rig change drops out-of-zone preferences (`rezone`). Send to Mic Tracker is blocked while any pack is over (`push.short_of_rig`). Plans numbered before the rig with counts set (`planning.before_rig`) need a Re-generate; `planning.plan_values` reads old settings. Walkthrough (PR W3, migration 0232; replaced the Review tab and dropped `MicPlanReviewCheck`): `mic_plan/walkthrough.py` builds one panel per showflow row from the parse + overrides alone (`planning.build_day` + `solver.appearances(fold_hosts=False)`, no solve, so it works before Generate and never shows an RF). Every on/off sits on the row that caused it (`solver.Appearance.off_how`: catch / exit / added / fixed / end); an `end` off sits on the segment's last row as "assumed: end of segment". `fold`: a row that is the first with text on a later page with no line label and no start time folds into the row above. Highlights: `flags['spans']` (names) and `unmatched_speaker` warning `spans` (leftovers; `parser.split_cell(leftover_spans=)`, `Analysis.leftovers`) plus `description_candidates` located in the text. Locks: person lock only for weak-source names (in a line-estimate part, or no ShowflowEvent behind them) on their first row until Person (`importer.confirm_person`) / Not a person (`reject_phrase`) / Same as (`same_as`; a typed name close to someone, `importer.close_names`, asks first); cue-sourced names get a first-row highlight. Row locks: exit wording, split across pages, inferred mic type, leftover text — "Looks right" (ack) or any edit confirms. Confirm = `MicPlannerRowCheck` (part FK, `row` = rowkey.describe, `digest` = raw text + what the panel shows, plan flags excluded, `shown` for "was → now"); moved to the new part on Replace (`importer.confirm`). A row with nobody on/off, no issue and no lock is `auto`. Plan flags are label-only badges with "Show in plan" and never reopen a row. Blockers (conflict, shortage while over the rig, held-back `override_changed`) block Send whatever is confirmed (`push.refusal` refuses held-back overrides too); the push page and the PDF's Issues section read `walkthrough.build`. One JSON endpoint `mic-plan/day/<pk>/walk/<action>/` (confirm, unconfirm, row, person, add, unreject, override); `confirm` answers with that panel alone, the rest with the whole walk, and `mic_plan_walkthrough.js` redraws only panels whose `sig` changed. Enter is optimistic (cursor moves before the answer; a digest mismatch redraws that panel and points to it, no error). All user text goes in by textContent (`test_xss_browser` walkthrough case). `test_mic_planner_walkthrough.ConfirmTests`: a no-data Re-generate/Replace reopens nothing; an inserted segment reopens only rows whose output changed. |
| Power Distribution Calculator | |
| Soundvision Predictions | L'Acoustics PDF parsing |
| IP Address Management | |
| Console Templates | |
| Mobile interface | Mounted at `/m/` |

---

## COMM Config — Technical Reference

ShowStack is the **first software capable of generating offline `.cca` config files for both Clear-Com Arcadia and FreeSpeak II**. The rules below are verified on hardware. Do not change them without a test device available.

### Arcadia `.cca` export
- **Factory pouchdb:** `planner/data/comm_config/pouchdb_factory/`
- **Factory sys_id:** `lKcw3zUU`

**sys_id routing rules (critical):**
- `3.06` docs must use the **hardware sys_id** (e.g. `ff080f1f`) detected from the factory pouchdb — **NOT** `lKcw3zUU`
- `4.44` **owners** → `3.06.<hw_sys_id>.*`
- `4.44` **destinations** → `3.20.lKcw3zUU.*`
- `userId` is sequential, starting from `135208704`

**Default password:** factory hash `037ee3...` corresponds to factory password `04312B48`.

**Verified working scope:** all device types + 2W/4W/SA/PGM ports + `4.44` partyline.port assignments. Confirmed on Arcadia hardware.

**Port settings export caused Arcadia crashes in a previous attempt.** Safe rollback commit: `66874bb`.

### FreeSpeak II `.cca` export
- **Factory files:** `planner/data/comm_config/fsii_factory/`
- **FSII-BP beltpack:** 4 channel keys + 1 reply key
- **E-BP beltpack:** 8 channel keys + 1 reply key
- **V-panel session types:** `P.V12`, `P.V24`, `P.V32`
- **V-panel doc ID prefixes:** `000b`, `000c`, `000d` (matched to the session types above in order)

### Current state
Partylines, Roles, and Ports tabs are working for **both** Arcadia and FreeSpeak II.

### Outstanding COMM Config items
1. Fix 4W port 1/4 port function swap in FSII export.
2. Project access request / invite-by-link system — `ProjectAccessRequest` model + `invite_token` UUID on `Project`, Resend for email notifications.

---

## Coding Conventions & Gotchas

### Overriding Django admin CSS from JavaScript
Django admin styles use `!important` pervasively. `element.style.property = value` will **not** override them.

```js
// ❌ Does not work
element.style.color = 'red';

// ✅ Correct
element.style.setProperty('color', 'red', 'important');
```

### `collectstatic`
Runs in the service's start command on every Railway deploy. If static files are missing in prod, check `STATICFILES_DIRS` and `STATIC_ROOT` before assuming a deploy failure. `ForgivingManifestStaticFilesStorage` logs a warning naming any asset it could not find in the manifest, so grep the Railway logs for `static asset missing from manifest`.

---

## Legal / Compliance

- Terms of Service: https://showstack.io/terms
- Privacy Policy: https://showstack.io/privacy
- Clickwrap consent checkbox is live on the registration form — **do not remove** without consulting Charlie.

---

## Active Work Queue

**Ongoing:**
- Beta tester bug fixes across: Console Templates, Power Distribution Calculator, Mic Tracker, mobile interface (`/m/`)
- COMM Config: invite-by-link flow for project access (partially built)
- COMM Config: 4W port 1/4 function swap fix in FSII export (confirm with Charlie before touching)

---

## When in Doubt

- **Ask before running destructive operations against Railway Postgres.** Fake migrations, manual `ALTER TABLE`s, and data backfills need confirmation.
- **Ask before touching factory pouchdb files** in `planner/data/comm_config/`. These are binary references; a wrong edit breaks `.cca` export for all users.
- **Never commit** `.env`, Resend API keys, Railway tokens, or anything already listed in `.gitignore`.
- **Any PR that touches `requirements.txt`** must be verified with `pip install -r requirements.txt` in a fresh venv, then `pip check`, before the PR is opened. `pip install <pkg>` into the existing venv can silently upgrade a pinned dependency, so the old venv passes while Railway's clean build fails (pdfplumber vs the Pillow pin broke the #160 deploy). On macOS, plyvel needs `CPPFLAGS=-I/opt/homebrew/include LDFLAGS=-L/opt/homebrew/lib ARCHFLAGS="-arch arm64"` to build against Homebrew leveldb.
- If a proposed change touches COMM Config export logic, verify against the rules in the COMM Config section before implementing.
