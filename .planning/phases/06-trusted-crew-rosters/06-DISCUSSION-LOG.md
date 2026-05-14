# Phase 6: Trusted Crew Rosters - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-14
**Phase:** 06-trusted-crew-rosters
**Areas discussed:** Model shape, UI placement & navigation, "Add your crew" panel layout, Auto-claim hook on registration

---

## Model Shape

### Question 1: Pending-email member modeling

| Option | Description | Selected |
|--------|-------------|----------|
| Single CrewMember table, nullable user + nullable email | One table, DB CHECK enforces exactly one of user/email non-null. Auto-claim updates row in place. | ✓ |
| Two tables (CrewMember + CrewPendingInvite) | Existing-user rows and pending rows in separate tables. Auto-claim deletes pending row + creates CrewMember row. | |
| Single table, nullable user only; email via UserProfile shadow row | Create placeholder User immediately, auto-claim activates it. Introduces ghost User rows. | |

**User's choice:** Single CrewMember table with nullable user + nullable email
**Notes:** Cleaner queries, single-table reads cover pending and existing members alike. Researcher to confirm Django CheckConstraint with Q expression handles the "exactly one non-null" rule.

### Question 2: Crew model fields beyond name

| Option | Description | Selected |
|--------|-------------|----------|
| Just name + owner FK | Minimum viable shape. Default role per CrewMember only. | ✓ |
| name + owner + crew-level default_role | Crew has its own default applied to new members unless overridden. | |
| name + owner + color/icon for UI | Visual distinction on invite page. Pure UX nicety. | |

**User's choice:** Just name + owner FK
**Notes:** Minimal migration; color/icon and crew-level defaults can be added later if needed.

---

## UI Placement & Navigation

### Question 3: Where does the My Crew page live?

| Option | Description | Selected |
|--------|-------------|----------|
| /accounts/crew/ — new top-level route | Matches existing accounts app pattern, public template dir, @login_required gated. | ✓ |
| /dashboard/crew/ — tab on dashboard | Nested under dashboard, integrated with project list. | |
| /admin/accounts/crew/ — under Django admin | Reuses admin theming + CRUD scaffolding. | |

**User's choice:** /accounts/crew/
**Notes:** First-class user-facing feature, not a power-user backstage tool. Templates land in `accounts/templates/accounts/`.

### Question 4: Where in the nav does the link surface?

| Option | Description | Selected |
|--------|-------------|----------|
| Top-right user menu next to logout | Account-level feature lives with other account actions. One nav entry. | ✓ |
| Dashboard sidebar/card grid alongside modules | Surfaces as a dashboard card next to audio modules. Higher visibility. | |
| Both — user menu link + dashboard card | Maximum discoverability. More nav surface. | |

**User's choice:** Top-right user menu next to logout
**Notes:** Keeps dashboard focused on audio production modules.

---

## "Add your crew" Panel Layout

### Question 5: How does the panel appear on /projects/<id>/invite/?

| Option | Description | Selected |
|--------|-------------|----------|
| Stacked sections: email form on top, crew panel below | Card per crew. Already-on-project members greyed. "Add this crew" button per card. | ✓ |
| Tabs: "Invite by email" / "Add from crew" | Explicit path picker. Cleaner separation but hides crew path behind a click. | |
| Crew picker BEFORE the email form | Nudges users toward the fast path. Mild confusion risk for muscle-memory users. | |
| Modal triggered from "Add crew" button | Cleanest visual diff but adds click + modal state. | |

**User's choice:** Stacked layout, panel below the email form
**Notes:** Preserves existing single-email muscle memory; new feature is discoverable without disrupting current flow.

### Question 6: Confirmation behavior on bulk-add click

| Option | Description | Selected |
|--------|-------------|----------|
| Single click — immediately bulk-adds, shows toast/message | One click = add all eligible members. Trust user intent. | ✓ |
| Two-step — click "Add" then confirm modal with member list | Safer but tedious for daily flow. | |
| Checkbox per member + single "Add selected" button | Most control but slows bulk-add. | |

**User's choice:** Single click — immediate bulk-add with confirmation banner
**Notes:** Trust the user — they already created the crew on purpose.

---

## Auto-Claim Hook on Registration

### Question 7: Where does the auto-claim logic live?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline call inside register() view body | Synchronous, visible, easy to test. Single entry point. | ✓ |
| Django post_save signal on User | Decoupled but invisible. Signal fires on User.update() too — requires filter. | |
| Override RegistrationForm.save() | Form-level. Couples form to crew logic; doesn't fire for non-form-based User creation. | |
| Custom auth backend hook | Most decoupled, most complex. Overkill. | |

**User's choice:** Inline call inside register() view body
**Notes:** Helper module (working name `claim_pending_crew_memberships`) is unit-testable directly; no signal magic.

### Question 8: Email match strictness

| Option | Description | Selected |
|--------|-------------|----------|
| iexact + strip whitespace | Catches trailing whitespace; no provider-specific normalization. | ✓ |
| iexact only (no strip) | Tighter — owner typo (trailing space) won't match. | |
| Strip + gmail dot-and-plus normalization | Catches more edge cases but surprising for users with legitimate plus addressing. | |

**User's choice:** iexact + strip whitespace
**Notes:** Standard Django strictness, matches existing email-uniqueness behavior in the project.

---

## Claude's Discretion

The following implementation details were intentionally left for the researcher/planner:

- Exact email template HTML and subject wording (model after `send_invitation_email` inline-HTML pattern at `accounts/views.py:252`)
- Admin registration of Crew + CrewMember on `showstack_admin_site` (yes, per CLAUDE.md convention)
- `admin_ordering.py` entries for new admin-registered models
- Final URL shape for crew CRUD + bulk-add (suggested: `/accounts/crew/...` and `/projects/<id>/invite/add-crew/<crew_id>/`)
- Button labels, microcopy, CSS styling for the crew cards
- Test fixture shape (mirror Phase 5 `test_channel_record_defaults.py` pattern)

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section. Highlights:

- Per-project role override at bulk-add time
- Bulk REMOVE crew from project
- Multi-crew select on invite page
- Cross-owner crew sharing / workspace model
- In-app notifications
- Mobile `/m/` parity
- Crew-level audit log
- Pro Tools export (Issue #5 followup — separate scope, awaiting sample file)
