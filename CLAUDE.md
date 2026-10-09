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
- **Static files:** Whitenoise with hashed filenames (`collectstatic` runs in `railway.json`'s `startCommand` on every deploy)
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
- `admin_ordering.py` controls sidebar hierarchy. **Update it whenever a new admin-registered model is added**, otherwise the sidebar grouping will be wrong.

### Deployment
- Pushing to `main` on GitHub triggers automatic Railway redeploy.
- Solo development typically goes straight to `main`; use feature branches only when the work is risky or spans multiple sessions.
- **Railway deploy steps live in `railway.json`'s `startCommand`.** It runs: `collectstatic --noinput && migrate && create_initial_superuser && setup_user_groups && load_amp_profiles && gunicorn`. There is no longer a `Procfile` -- it was deleted because Railway never read it and keeping a second, silently-ignored copy of the deploy command invited editing the wrong one.

---

## Modules

| Module | Notes |
|---|---|
| Consoles | Yamaha Rivage PM series CSV export emits 11 files in exact Rivage PM Editor format |
| I/O Devices | |
| Amplifiers | |
| System Processors | |
| PA Cable Schedule | |
| COMM Config | Clear-Com Arcadia + FreeSpeak II `.cca` offline config export (see COMM Config section below) |
| Mic Tracker | |
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
Runs in `railway.json`'s `startCommand` on every Railway deploy. If static files are missing in prod, check `STATICFILES_DIRS` and `STATIC_ROOT` before assuming a deploy failure. `ForgivingManifestStaticFilesStorage` logs a warning naming any asset it could not find in the manifest, so grep the Railway logs for `static asset missing from manifest`.

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
- If a proposed change touches COMM Config export logic, verify against the rules in the COMM Config section before implementing.
