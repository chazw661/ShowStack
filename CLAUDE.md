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

# Direct psql when migrations need manual fix
psql "$DATABASE_PUBLIC_URL"              # turntable.proxy.rlwy.net:34865
```

**Do not** run destructive SQL against Railway Postgres without confirming with Charlie first.

---

## Tech Stack

- **Backend:** Django 5.x, PostgreSQL (Railway-managed), `dj_database_url` (SQLite fallback for local dev)
- **Config:** `python-decouple` — secrets via `.env` locally, Railway env vars in prod
- **Static files:** Whitenoise (`collectstatic` runs in Procfile on every deploy)
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
- **Railway uses `railway.json`'s `startCommand`, NOT the `Procfile`.** Editing the Procfile alone will have no effect in production. The active startCommand runs: `collectstatic --noinput && migrate && create_initial_superuser && setup_user_groups && load_amp_profiles && gunicorn`. Update `railway.json` (and keep the Procfile in sync) when changing deploy steps.

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
Runs in `Procfile` on every Railway deploy. If static files are missing in prod, check `STATICFILES_DIRS` and `STATIC_ROOT` before assuming a deploy failure.

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
