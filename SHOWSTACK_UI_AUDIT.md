# ShowStack UI Audit — Oct 1, 2026

Scope: console + I/O patching, PA Cable, Amp Assignments, COMM Belt Packs, Mic Tracker.
Reviewed live on production (UiPath Fusion 26), view-only — nothing saved.
Hand items to Claude Code one at a time, in priority order.

---

## Status — Oct 2, 2026 (after PRs #77–#79)

**Done:** neutral charcoal surfaces; one-button system on console save bar (Delete separated); console/I-O grids: Safari fix, fixed column widths, 36px/14px inputs, Source capped at 360px, "Multitrack" header, row-1 alignment, "↳ linked" stereo rows, neutral section headers, monochrome widget icons, "Planner" removed from breadcrumbs, dashboard title/breadcrumb fixed; hashed static files (no more stale CSS after deploys), committed staticfiles/ removed.

**Next (in order):**
1. Amp Assignments restyle (yellow/red/green blocks, white CH dropdowns, 3 button colors)
2. Steel-blue leftovers: PA Cable buttons + summary table headers, Belt Pack Add button, green POSITION header, green Save
3. Mic Tracker show-mode branch — first extract the 146 inline colors in mic_tracker.html / mic_tracker_overview.html into CSS variables
4. Remaining P1/P2 items below (admin wording, sidebar grouping, empty states, Belt Pack manufacturer list, PA Cable destination picklist)

---

## The root problem

ShowStack currently has **four visual languages**:

1. Django admin changelists/forms (`/admin/planner/*`): "Select X to change", grey/black inputs, admin Action dropdown + Go, filter sidebar.
2. Custom purple/navy dashboard (`/admin/` System Overview): clean cards, good.
3. Custom tool pages (Amp Rack View, Mic Tracker): each with their own button colors, headers, and breadcrumbs.
4. Mobile `/m/`: iOS-style, the most polished of the four.

Every page *works*, but moving between pages feels like switching apps. That — not any single screen — is why it doesn't read as a professional tool. Polishing individual pages before fixing this will be wasted effort.

---

## P0 — Fix first (credibility + safety)

### 1. Remove Django admin language from user-facing pages
- "Select Console to change", "Select Day to change", "Change I/O Device", "Add Comm Belt Pack" → "Consoles", "Show Days", "Y001 A2 3224", "New Belt Pack".
- Header: drop "VIEW SITE / CHANGE PASSWORD / LOG OUT" text links → a single user menu (avatar or name ▾) containing My Crew, Change password, Log out.
- URLs under `/admin/` are visible to users. Lower priority, but long-term move crew-facing pages off `/admin/`.
- Several pages have an **empty `<title>`** (console change, device change, PA cable, belt pack add). Browser tabs show the raw URL. Set `<title>` to "Page — Project — ShowStack" everywhere.

### 2. Save bar on console edit takes ~25% of the screen
- Four full-width stacked buttons (Save / Save and add another / Save and continue editing / Delete) fixed to the bottom at narrower widths. On the input grid only ~3 rows are visible.
- **Delete is a full-width red button directly under Save** — one mis-click from destroying a console patch.
- Fix: one slim sticky bar, right-aligned: `[Save]` primary, `Save & continue` secondary. Move Delete into an overflow menu (⋯) or the page bottom, with a confirm that types the console name.
- The keyboard-shortcut toast (bottom-right) overlaps the save buttons. Make it dismissible and remember dismissal, or move shortcuts behind a "?" key.
- There are also **two** save controls (top "💾 Save" + bottom bar). Pick one.

### 3. Mic Tracker: destructive control in the live-show header
- Trash icon sits next to Settings in the session header. In a dark room under show pressure that's a liability. Move delete-session into the settings panel with confirmation.

### 4. Mic Tracker is not dark-room safe
- Bright `#5be38a`-style green ON buttons + green presenter names on every mic'd row = 10+ glowing blocks. Kills night vision and is visible from the audience at a dark FOH.
- Add a **Show Mode** (toggle or auto when viewing today): dim background, no neon fills, use a low-luminance dot/outline for ON state, red-shifted or amber accents, larger RF# and presenter names, hide Export/Add Day/Presenters buttons.
- Mic'd state should be the strongest signal on the row, not the presenter name color *and* the button *and* row tint all at once.

### 5. Mic Tracker on phone: the key control is off-screen
- At 375px the MIC'D toggle and notes are scrolled off the right edge; first mic row starts ~1.5 screens down behind the header, export buttons, and tabs.
- `/m/` exists and looks better — make sure Mic Tracker has a first-class `/m/` view (RF#, presenter, mic'd toggle, one-tap notes), and link to it from the desktop page when a small viewport is detected.

---

## P1 — Navigation and consistency

### 6. One button system
Currently seen: steel-blue (Add Console, History, Add Day), purple (Go, Search, Save and add another), bright blue (Export to PDF), tan (Collapse/Expand All), green (Save), red (Delete), outlined gold (Listen Setup), outlined steel (Export PDF/CSV on Mic Tracker).
- Define 4 variants only: **Primary** (one per page), **Secondary** (outlined), **Ghost** (text), **Danger** (only for destructive, never full-width).
- Pick one casing. Today it's mixed: "ADD CONSOLE" (caps), "Save and add another" (sentence), "Export to PDF" (title).
- Put these in one CSS file of tokens and delete per-page overrides (including the `setProperty(..., 'important')` hacks fighting admin CSS).

### 7. Sidebar order = model order, not workflow order
Current: Planner, Projects, Equip Locations, Consoles, Source Hardware Options, I/O Devices, Amplifier Assignments, System Processors, PA Cable Entries, Comm Belt Packs, Comm Configurations, Mic Tracker, Soundvision, Power, Audio Checklists, Multitrack, Signal Flow.
- Group by phase and hide setup/lookup tables:
  - **Signal**: Consoles, I/O Devices, Processors, Multitrack
  - **PA**: Soundvision, Amplifiers, PA Cable, Power
  - **Comms**: Belt Packs, COMM Config
  - **Show Day**: Mic Tracker, Checklists
  - **Docs**: Signal Flow, System PDF
  - **Setup** (collapsed): Projects, Locations, Source Hardware Options
- Match these groupings on the System Overview dashboard (it already roughly does: Signal Flow / Communications / Wireless / Electrical / Network / Documentation) so the two navigation surfaces agree.
- Sidebar only appears at wide widths; below that there's no module nav except going back to the dashboard. Add a compact module switcher (dropdown or icon rail) at all widths.

### 8. Header and breadcrumbs differ per page
- Mic Tracker header has no project selector; admin pages do. Breadcrumb on Mic Tracker ends in a dangling "›".
- Admin breadcrumbs say "Home › Planner › Consoles" — "Planner" is the Django app label and means nothing to a user.
- One shared header component: logo, project switcher, module switcher, user menu. Breadcrumb: Project › Module › Item.

### 9. Empty states
- Belt Packs with zero entries shows "0 Comm Belt Packs" plus a full filter panel for nothing. Show a centered empty state: what this module does, one primary "Add belt pack" button, and "Import" if supported.
- Mic Tracker header fields Show / Venue / Room / Dates all render "—". Either pull from the project or hide until filled.

---

## P2 — Workflow-specific

### Console + I/O patching
- Patching is split across two pages (console inputs on the console; device inputs on each I/O device). A device input dropdown shows the source name ("Wless 1") but not the console channel, so you can't verify the patch from either side. Show `Ch 1 · Wless 1` in the device grid, and show the device/port on the console input row.
- Long-term: a single **Patch view** (rows = console channels, columns = Source / Device / Port / Dante #) is the screen A1s actually think in.
- Console list shows "Is Template ✓" on the real show console (and its title is prefixed `[TEMPLATE]`). Either a data mistake or confusing UI — templates should live only in Template Library, not mixed into a show's console list.
- Input grid is wider than the content area at laptop width (columns clipped past "Include in Multitrack"). Freeze the first two columns (Dante #, Input Ch) and let the rest scroll, or move low-use columns (Omni In, Direct Out) into an expandable row.
- Input cells are pure black (`#000`) on near-black panels: low edge contrast. Use a slightly raised input background with a 1px border.

### PA Cable
- Filter sidebar steals width and clips the table (Couplers onward cut off). Move filters to a single row of chips above the table.
- Destination is free text, which produces "LA Rak 3 HL" vs "LA Rak3 HL", "HL Amp Rack" vs "HL Amp Racks", and typos like "X12 Folback". Make destination a picklist of project locations/racks with type-to-add.
- Cable summary table: "Cables needed" and "Order qty" share identical length headers (100' 50' 25' 10' 5'). Add a grouped header row or visual divider so the two blocks aren't read as one.

### Amp Assignments
- Each amp renders all 16 AVB rows + AES rows even when 1 is used ("None" × 15). 18 amps → very long scroll. Collapse unused rows by default ("+ 15 unused") or switch to a compact table: one row per amp, expand for detail.
- Pastel yellow IP/Preset blocks and green AES header are the brightest things on a dark page and look like placeholder styling. Use the same panel/inputs as everywhere else; reserve color for status.
- Channel selector row (CH 1–16 tiny dropdowns) has no visible values at a glance. Show the assigned value in the cell; dropdown on click.
- Content overflows the card on the right (SC32 OUT column cut off at narrower widths).
- Spelling: "Analogue" here vs American English elsewhere. Pick one.

### COMM Belt Packs
- System/Manufacturer list does **not** include Clear-Com Arcadia or FreeSpeak II, which COMM Config supports. Users can't create belt packs matching the config module.
- IP Address field shows for Wireless packs ("for hardwired belt packs") — hide it unless System Type = Hardwired. Same for "Checked out" (wireless only) in reverse.
- One pack per form page. Entering 20 packs = 20 page loads. Add a grid/bulk-add view (BP#, Position, Name, Headset, Group) like the console input grid.
- "Name" dropdown mixes people and positions ("Adrian (ME)", "GFX 1", "LED 2"). Keep Position and Crew Name as separate lists so the data stays clean.

---

## What's already working (keep it)
- System Overview dashboard: clear grouping, status dots, counts. This is the visual direction to extend everywhere.
- `/m/` mobile UI: closest to "professional tool" quality.
- Mic Tracker structure (Day → Session → A1/A2 tabs, per-RF row, D-mic count) is right; it's the styling and show-mode behavior that need work.
- Console input grid keyboard navigation (Enter/Tab) — keep it, just make the hint less intrusive.

---

## Suggested order for Claude Code
1. Shared header + user menu + page titles (item 1, 8)
2. Button/token CSS (item 6) — do this before restyling individual pages
3. Console save bar + delete placement (item 2)
4. Mic Tracker show mode + delete placement (items 3, 4)
5. Sidebar regrouping (item 7)
6. Belt pack manufacturer list + conditional fields (quick wins)
7. Everything else in P2
