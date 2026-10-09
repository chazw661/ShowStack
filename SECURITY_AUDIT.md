# Multi-tenant isolation audit

Scope: every admin page, dashboard widget, dropdown, API/AJAX endpoint, export
and count in `planner`, `accounts` and `marketing`. Question asked of each one:
**can a logged-in user see or select data from a project they don't own or
belong to?**

Every finding below is reproduced by a test in
`planner/tests/test_tenant_isolation.py`. Against the unfixed tree, 23 of 39
failed with 0 errors — each failure a real finding. The suite now stands at 51
tests, all passing; the 12 added after the fixes assert the *opposite* failure
mode, that scoping did not lock out the rightful owner (see
`OwnProjectStillWorksTests`). Full project suite: 366 passing.

```bash
python manage.py test planner.tests.test_tenant_isolation \
    --settings=audiopatch.test_settings
```

**Status: all findings below are fixed on this branch**, in four commits —
proof tests, the anonymous default-deny, the view-layer scoping, then the
admin. Each section's fix is described in its commit message; the short
version is at the end of this document.

---

## Answer to the question you asked first

**Yes — names and patch data leak, not just counts. And the worst of it leaks
to unauthenticated visitors, not just to logged-in users of other projects.**

`audiopatch/settings.py:91-102` has no `LoginRequiredMiddleware`, and ~60
routed views carry no `@login_required`. Eleven argument-free planner routes
answer an anonymous GET with HTTP 200 today; several of them return other
tenants' data. Separately, one admin page (`CommConfigAdmin`) grants every
`is_staff` user full read/write on every tenant's COMM config, and that is
reachable right now by any invited editor or viewer — no extra permissions
needed. Issue #100's dashboard counts are real but are the mildest item here.

---

## F1 — Anonymous cross-tenant reads (names + patch data)

No authentication decorator, no project check. All verified serving HTTP 200 to
`Client()` with no session.

| # | Location | What leaks |
|---|---|---|
| F1.1 | `planner/views.py:239` `console_pdf_export` | Any console's full patch sheet as PDF, by id. Channel names, sources, groups, DCAs, omni I/O. **Names + patch data.** |
| F1.2 | `planner/views.py:3900` `all_comm_beltpacks_pdf_export` | Passes `project=None` into `generate_comm_beltpacks_pdf`, which at `planner/utils/pdf_exports/comm_pdf.py:45-47` only filters `if project is not None` — so `None` means *every project*. Crew names, positions, channel assignments, IPs for all tenants in one PDF. **Names + patch data.** |
| F1.3 | `planner/views.py:2892` `predictions_list` | `SoundvisionPrediction.objects.all()` + `ShowDay.objects.all()`. Every tenant's prediction filenames and show-day names. **Names.** |
| F1.4 | `planner/views.py:2916` `prediction_detail` | Any prediction by id: array names, weights, trim heights, rigging, motor counts. **Names + data.** |
| F1.5 | `planner/views.py:2987` `export_prediction_summary` | Same, as CSV. **Names + data.** |
| F1.6 | `planner/views.py:3413` `device_pdf_export` | Guard is `if current_project: if device.project != current_project: deny`. An anonymous request has no `current_project`, so the guard is **skipped entirely** — classic fail-open. Any device's I/O patch. **Names + patch data.** |
| F1.7 | `planner/views.py:5325` `comm_config_export` | Any tenant's complete `.cca` Arcadia/FreeSpeak config by id. **Names + config data.** |
| F1.8 | `planner/views.py:6656` `comm_config_list_templates` | `CommConfig.objects.filter(is_template=True)` — every tenant's COMM template names. **Names.** |
| F1.9 | `planner/views.py:5774` `debug_device_ordering` | Leftover debug view routed at `planner/urls.py:308`. Dumps `Device.objects.all()[:3]` with input/output signal names as HTML. **Names + patch data.** |
| F1.10 | `planner/views.py:5220` `comm_config_role_chips` | Any role's keyset labels by id. **Names.** |
| F1.11 | `planner/views.py:2272` `get_assignment_details` | Any mic assignment by id: presenter names. **Names.** |

Three further anonymous 200s **fail closed** and leak nothing — listed so the
fix doesn't get credit it hasn't earned: `all_pa_cables_pdf_export`
(`views.py:3874`, `none()`), `export_all_locations_pdf`
(`utils/pdf_exports/location_pdf.py:21`, `none()`), `system_report_pdf`
(`utils/pdf_exports/system_report.py:310`, empty PDF). They still should not be
public.

## F2 — Anonymous cross-tenant writes and deletes

| # | Location | Impact |
|---|---|---|
| F2.1 | `planner/views.py:1058` `delete_session` | POST `{"session_id": N}` **deletes any tenant's MicSession** and its assignments. No auth, no scoping. Destructive. |
| F2.2 | `planner/views.py:5054-5305, 6312-6493, 6575, 6662, 4894` — the whole `comm_config_*` family (~24 endpoints) | Each takes a raw `partyline_id` / `config_id` / `role_id` / `port_id` / `keyset_id` and writes it. Verified: `comm_config_update_partyline` and `comm_config_add_partyline` both returned **HTTP 200** acting on project B's objects from project A's session. |
| F2.3 | `planner/views.py:1348-2290` — the Mic Tracker write family (`update_mic_assignment`, `dmic_and_rotate`, `reset_presenter_rotation`, `update_slot_field`, `assign_slot_group`, `assign_slot_a2_group`, `toggle_slot_micd`, `advance_presenter_slot`, `previous_presenter_slot`, `add_presenter_slot`, `remove_presenter_slot`, `activate_presenter_slot`, `assign_mic_group`) | Raw `assignment_id` / `slot_id`, no auth, no membership check. Verified: `update_mic_assignment` returned **HTTP 200** modifying project B's row. `update_mic_assignment` deliberately derives the project *from the row being edited* (`views.py:1363`) — correct for the duplicate-presenter bug it was fixing, but it means there is no tenancy check at all. |
| F2.4 | `planner/views.py:3437, 3487, 3499` `amp_reorder`, `amp_divider_update`, `amp_divider_delete` | Raw ids, no auth. |
| F2.5 | `planner/views.py:6183, 6243, 6293` audio-checklist template save/load/delete | Raw ids, no auth. |
| F2.6 | `planner/views.py:87` `console_detail` | Unauthenticated and unscoped, and its POST branch writes `ConsoleInput` rows. **Not currently exploitable**: the formset at `views.py:90-98` names `output` and `omni_out`, which no longer exist on `ConsoleInput`, so the view raises `FieldError` before saving — and its GET branch separately references an undefined `project` (`views.py:261`). Reported because it is one field rename from being a live unauthenticated write. |

## F3 — Admin changelists with no project scoping

`get_queryset` is Django's default (all rows). Verified returning project-B rows
from project A's session.

| # | Location | Leak | Reachable today? |
|---|---|---|---|
| F3.1 | `planner/admin.py:7311` `CommConfigAdmin` | Unscoped **and** `has_view/change/add/delete_permission` all return bare `request.user.is_staff` (`admin.py:7313-7326`). Every invited user is made `is_staff` at `accounts/views.py:301-302`. **Verified: an invited editor of project B opened project A's COMM config change form, HTTP 200.** Names + full config data, read and write. | **Yes — no extra permissions needed. The most serious admin finding.** |
| F3.2 | `planner/admin.py:7391` `ProjectSNMPConfigAdmin` | Unscoped; `list_display` includes `community_string` — the SNMP v2c credential for every project's switches. | Gated by `planner.view_projectsnmpconfig`, which `setup_user_groups.py` does not grant. Latent. |
| F3.3 | `planner/admin.py:7353, 7358, 7363, 7374, 7397` `MonitorSessionAdmin`, `DiscoveredDeviceAdmin`, `PollResultAdmin`, `DeviceEventAdmin`, `SwitchPortSnapshotAdmin` | Unscoped. Device labels, IP addresses, port state across all tenants. | Same — gated only by model permissions no group currently grants. Latent. |

F3.2/F3.3 are defence-in-depth today and live the moment anyone is granted
those permissions. They are fixed anyway.

## F4 — Dropdowns that offer another tenant's rows

A dropdown is a read surface: anything selectable is also visible. These FK
fields have **no** `formfield_for_foreignkey` override, so they render the whole
table. Verified by listing the actual offered labels.

| # | Admin.field | Offers |
|---|---|---|
| F4.1 | `MultitrackSessionAdmin.console` | other tenants' Console names |
| F4.2 | `ConsoleImportAdmin.console` | Console names |
| F4.3 | `P1ProcessorAdmin.system_processor` | SystemProcessor names |
| F4.4 | `GalaxyProcessorAdmin.system_processor` | SystemProcessor names |
| F4.6 | `MicAssignmentAdmin.session` | MicSession names |
| F4.7 | `MicGroupAdmin.session` | MicSession names |
| F4.8 | `SpeakerArrayAdmin.prediction` | prediction filename + show-day name |
| F4.9 | `PollResultAdmin.device` / `.session` | device labels, project names |
| F4.10 | `DeviceEventAdmin.device` / `.session` | device labels, project names |
| F4.11 | `SwitchPortSnapshotAdmin.device` / `.session` | device labels, project names |

**Withdrawn finding.** `PACableSchedule.amp_location` first appeared in this
list: the existing `PACableAdmin.formfield_for_foreignkey` (`admin.py:3352`)
scopes `label`, `speaker_array` and `amp` but not this fourth FK. It is
`editable=False` (`models.py:2547`), so Django drops it from every ModelForm —
it is never rendered and never selectable. Not a leak; the isolation test now
skips non-editable fields for this reason.

The dropdowns that *are* correctly scoped, for contrast: `ConsoleAdmin.location`,
`DeviceAdmin.location`, `AmpAdmin.location`, `SystemProcessorAdmin.location`,
`PACableAdmin.label/speaker_array/amp`, `CommBeltPackAdmin.unit_location/
position/name/channel_a-f`, `CommBeltPackChannelInline.channel`,
`MicSessionAdmin.day`, `MicAssignmentInline.presenter/shared_presenters`,
`SoundvisionPredictionAdmin.show_day`, `PAFanOutExtensionInline.fan_out`.

## F5 — Filter sidebars enumerate the whole related table

`list_filter` on a bare relation makes Django render **every** row of the
related table in the sidebar. `RelatedFieldListFilter.field_choices` calls
`field.get_choices()`
(`django/contrib/admin/filters.py:271-273`), which ignores the admin's scoped
`get_queryset` entirely. So these leak names on pages users legitimately access
— a project member browsing their own consoles sees every other tenant's
location names in the filter rail. Verified by reading the rendered choices.

| # | Admin | Filter | Enumerates |
|---|---|---|---|
| F5.1 | `ConsoleAdmin` | `location` | all Location names |
| F5.2 | `SystemProcessorAdmin` | `location` | all Location names |
| F5.3 | `P1ProcessorAdmin` | `system_processor__location` | all Location names |
| F5.4 | `GalaxyProcessorAdmin` | `system_processor__location` | all Location names |
| F5.5 | `MicSessionAdmin` | `day` | all ShowDays, e.g. `2026-02-01 - Day <client name>` |
| F5.6 | `MicAssignmentAdmin` | `session__day`, `session` | all ShowDays + MicSessions |
| F5.7 | `SoundvisionPredictionAdmin` | `show_day` | all ShowDays |
| F5.8 | `MonitorSessionAdmin`, `DiscoveredDeviceAdmin`, `ProjectSNMPConfigAdmin` | `project` | all **project names** |
| F5.9 | `PollResultAdmin`, `DeviceEventAdmin`, `SwitchPortSnapshotAdmin` | `session` | all MonitorSessions, whose `__str__` embeds the project name |
| F5.10 | `SignalFlowDiagramAdmin` | `project` | all project names — **not** currently rendered, because `changelist_view` redirects to the user-facing list. Fixed anyway. |

`AmpAdmin.amp_model__*` and `CommBeltPackAdmin.device_model__device_type` also
enumerate fully, but `AmpModel` and `CommDeviceModel` are deliberately global
hardware catalogues. Not findings.

## F6 — Dashboard counts (issue #100 item (a))

| # | Location | Leak |
|---|---|---|
| F6.1 | `planner/views.py:536-575` `SystemDashboardView` | Every count is global: `Console.objects.count()`, `Device.objects.count()`, `total_inputs`/`total_outputs` summed over `Device.objects.all()`, `SystemProcessor` counts, `CommBeltPack` counts, `Amp.objects.count()`, `total_amp_channels`, `total_cable_runs`, `total_cable_length`. `LoginRequiredMixin` only. **Counts and aggregate magnitudes, no names.** A comment at `views.py:558-560` already admits it. |
| F6.2 | `planner/views.py:6511` `dashboard_stats` | Decorated `@require_GET` three times and **nothing else** — no auth at all. When `current_project` is `None` the filter kwargs collapse to `p = {}` (`views.py:6514-6515`) and every count becomes global. So an anonymous visitor, or any logged-in user with no project, gets global counts of all tenants' equipment. **Counts.** |

## F7 — The duplicate-method bugs

| # | Location | Finding |
|---|---|---|
| F7.1 | `planner/admin.py:2064` and `:2147` `AmpAdmin.formfield_for_foreignkey` | As reported in #100: defined twice, the first is dead. **Not itself a leak** — the live copy (2147) scopes `location` to `AmpLocation.objects.filter(project=current_project)` with an `else: none()`, which is correct. What the dead copy contained: `amp_model = AmpModel.objects.all()` (the default anyway) and `location = Location.objects.filter(...)` — the **wrong model**, since `Amp.location` points at `AmpLocation`. Had the definition order been reversed, the dropdown would have been populated from the wrong table. Merged into one method. |
| F7.2 | `planner/admin.py:4958` and `:5108` `CommBeltPackAdmin.formfield_for_foreignkey` | Same bug class, not reported in #100. The live copy (5108) does the project scoping; the dead copy (4958) suppressed the add/change/delete widget buttons on `position`, `name` and `unit_location`, so that suppression has silently never worked. Merged. |
| F7.3 | `planner/admin.py:1163` and `:1167` `ConsoleAdmin.get_queryset` | Defined twice; the first is an empty stub returning `None`. Harmless only because it is the one that loses. Removed. |
| F7.4 | `accounts/admin.py:88` `ProjectMemberAdmin.get_queryset`, `accounts/admin.py:134` `InvitationAdmin.get_queryset` | Both filter `owner=request.user` and `projectmember__user=request.user`. Neither field exists on `ProjectMember` or `Invitation` → `FieldError`, HTTP 500, for every non-superuser. A crash, not a leak (superusers return early), but it means these pages have never worked for the users they are for. |
| F7.5 | `planner/admin.py` — `BaseEquipmentAdmin.get_queryset` ends with `qs.filter(project_id=...)`, and `MultitrackTemplate`, `ConsoleImport` and `MicGroup` have no `project` field and are absent from the `child_model_paths` map (`admin.py:163-178`) | `FieldError`, HTTP 500 on those three changelists. A crash, not a leak. |
| F7.6 | `planner/views.py` module-level duplicate defs, later silently wins: `bulk_update_mics` 759/862, `export_mic_tracker` 806/993, `delete_session` 980/1058, `dmic_and_rotate` 1599/1722, `get_assignment_details` 1693/2272, `update_amplifier_assignment` 2671/2759/2833, `get_amplifier_assignment` 2734/2808. Also `planner/mobile_views.py` `comm_list` 404/435 | Same hazard as F7.1 at module scope. In each pair the live copy is at least as scoped as the dead one, so no leak is hidden here — but ~1,100 lines of `views.py` are unreachable and any future scoping fix applied to the wrong copy would be a silent no-op. Reported, not removed: deleting them is a large behavioural diff that belongs in its own PR. |

## What is already correct

Worth recording so a later change doesn't undo it:

- **The mobile interface (`/m/`) is clean.** Every view in `planner/mobile_views.py` carries `@login_required` *and* an explicit `user_can_access_project` / owner-or-member check (`mobile_views.py:293-297`). No findings.
- **Signal Flow (phases 9-12) is clean.** `_get_diagram_for_request` scopes by `project=current_project` and every route is decorated.
- **The monitor agent API is clean.** `_authenticate_agent` (`views_monitor.py:38-52`) resolves a per-project Bearer token and every handler re-scopes client-supplied ids with `project=project` — e.g. `agent_snmp_results` at `views_monitor.py:586`. `csrf_exempt` is correct for a token API.
- **`BaseEquipmentAdmin.get_queryset`** (`admin.py:144-190`) is the reason most of the admin is safe: it scopes to `request.current_project` and returns `none()` when there is no project. Because `ModelAdmin.get_object` runs through it, cross-project change-form URLs 404.
- **`CurrentProjectMiddleware`** verifies session-supplied `current_project_id` against ownership or membership before honouring it — a user cannot select a project by editing their session.
- **`accounts.dashboard`, `ProjectAdmin`, `CrewAdmin`, `UserProfileAdmin`** are all correctly scoped.
- **The default `admin.site` mounted at `/audiopatch/admin/`** (`planner/urls.py:147`) registers only `auth.User`, `auth.Group`, `admin_interface.Theme`, `marketing.ContactSubmission` and `marketing.WaitlistSignup` — no tenant data, and each gated by model permissions no group grants. It is a redundant second admin surface that should be removed, but it is not a tenancy leak, so it is left alone here.
- **`SourceHardwareOptionAdmin`** (`admin.py:7238`) is unscoped by design — `SourceHardwareOption` is a global label catalogue with no project FK. Note it is globally *writable* by any project owner or editor (`admin.py:7251-7262`): a shared mutable global, which looks deliberate. Not changed.

---

## Where superusers still see everything

Deliberate, preserved, and asserted by `SuperuserVisibilityTests` so a future
tightening can't remove it silently:

| Location | Behaviour |
|---|---|
| `planner/admin.py:469` `ProjectAdmin.get_queryset` | `is_superuser` → every project, unfiltered. |
| `accounts/admin.py:228` `CrewAdmin.get_queryset` | `is_superuser` → every crew. |
| `planner/admin.py:193-266` `BaseEquipmentAdmin.has_module/view/add/change/delete_permission` | `is_superuser` short-circuits to `True` on all five. |
| `planner/middleware.py:34-56` | Superusers may select any project via the dropdown; everyone else is checked against ownership or membership. |
| `accounts/admin.py:155-183` `UserProfileAdmin` | Superuser-only on all five permission hooks. |
| `planner/admin.py:7421` `SignalFlowDiagramAdmin` | `is_superuser` overrides add/change/delete. |
| New in this PR: `CommConfigAdmin`, `MonitorSessionAdmin`, `DiscoveredDeviceAdmin`, `PollResultAdmin`, `DeviceEventAdmin`, `ProjectSNMPConfigAdmin`, `SwitchPortSnapshotAdmin` | Scoped to `current_project` for everyone, with `is_superuser` honoured the same way `BaseEquipmentAdmin` honours it. |

One thing that is **not** a superuser bypass, and is intended:
`BaseEquipmentAdmin.get_queryset` scopes superusers to the *selected* project
too. Superusers move between projects with the dropdown rather than seeing a
merged list. `SuperuserVisibilityTests.
test_superuser_equipment_admin_still_follows_the_project_switcher` pins that.

---

## Not fixed here, and why

- **F7.6** (duplicate module-level view definitions) — reported, not removed.
  Deleting ~1,100 unreachable lines of `views.py` is a large behavioural diff
  that deserves its own review, and no leak hides in the dead copies.
- **`planner/urls.py:147`** (`admin.site.urls` mounted inside the planner app)
  — no tenant data behind it; removing it risks breaking `{% url 'admin:…' %}`
  reverses in templates.
- **`console_detail`'s `FieldError`** (F2.6) — the view is guarded and now
  requires auth, but the formset is still broken and the view still 500s. It is
  a pre-existing functional bug, not a security one.
- **`SourceHardwareOption` being globally writable** — looks deliberate; left
  for a product decision.

---

## Summary of fixes

| Finding group | Fix |
|---|---|
| F1, F2 (anonymous read and write) | `LoginRequiredMiddleware` added to `settings.MIDDLEWARE`, inverting the default from allow to deny. ~60 views needed no individual change; 24 genuinely public views opt out with `@login_not_required` (all 12 marketing pages, `accounts.register`, `accounts.accept_invitation`, the 9 Bearer-token agent endpoints, the 2 Listen endpoints, `mobile_login`). New views are safe by omission. |
| F1.2 (belt-pack PDF) | `generate_comm_beltpacks_pdf(project=None)` now raises instead of spanning every project. There is no longer a way to ask for a cross-tenant report. |
| F1.6 (fail-open guard) | The `if current_project: check` shape is gone. `planner/tenancy.py` is the shared rule, and its key design point is that callers fold the project into the lookup rather than branching on it — `project=None` compiles to `project__isnull=True` and matches nothing. |
| F2.1–F2.5 (raw-id IDOR) | 34 lookup sites given a project predicate, so a cross-tenant id raises `DoesNotExist` and lands in each endpoint's existing 404 handler. 19 COMM Config endpoints also gained an `ObjectDoesNotExist` clause ahead of their generic `except Exception`, so the answer is 404 rather than a 500 carrying the exception text. |
| F3 (unscoped changelists) | `CommConfigAdmin` and the six monitor admins now inherit `BaseEquipmentAdmin`. `CommConfigAdmin`'s five `is_staff` permission hooks are deleted, restoring the owner/editor/viewer role model. |
| F4 (dropdowns) | New declarative `BaseEquipmentAdmin.project_scoped_fks`, applied to the eleven unscoped fields. A field left out of the map keeps Django's default — correct for the global catalogues, and now a per-field choice rather than an oversight. |
| F5 (filter sidebars) | New `project_scoped_filter` factory, generalising the hand-written `AmpLocationFilter` from issue #21 to the nine entries that were missed. `project` entries on project-scoped changelists are dropped rather than scoped. |
| F6 (dashboard counts) | `SystemDashboardView` counts run through `scope_queryset`. `dashboard_stats` is `@login_required` with an unconditional project filter, so no project means zeros rather than everything. |
| F7.1–F7.3 (duplicate methods) | `AmpAdmin.formfield_for_foreignkey` and `CommBeltPackAdmin.formfield_for_foreignkey` each merged into one; `ConsoleAdmin.get_queryset` collapsed and its debug prints removed. `CommBeltPackAdmin`'s merge also closed a fail-open `if current_project:` with no `else`. |
| F7.4, F7.5 (500s) | `ProjectMemberAdmin` and `InvitationAdmin` no longer filter on a non-existent `owner` field. `ConsoleImport` and `MicGroup` added to `child_model_paths`; `MultitrackTemplate` is owner-scoped; the fall-through returns `none()` instead of raising, so a forgotten registration fails closed. The unregistered `accounts.admin.ProjectAdmin` is deleted rather than left as a trap. |
| F7.6 (duplicate view defs) | Reported only — see "Not fixed here, and why". |
