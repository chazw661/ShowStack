---
status: partial
phase: 06-trusted-crew-rosters
source: [06-VERIFICATION.md]
started: 2026-05-15T17:15:00Z
updated: 2026-05-15T17:15:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Crew UI visual appearance
expected: Open /crew/ as a logged-in owner. Create two crews ("Concert team", "Corporate team"). Add 2-3 existing users to each with different default roles. Both crews appear in the grid with correct member counts and member names. Role badges (editor/viewer) display correctly in the dark theme.
result: [pending]

### 2. Pending-signup badge on roster
expected: Open /crew/<id>/ for a crew. Add a pending email (e.g. newbie@example.com). The pending row is visually distinct from active-user rows, with an amber "pending signup" pill and no username displayed.
result: [pending]

### 3. "Add your crew" panel on invite page
expected: Navigate to /projects/<id>/invite/ as the project owner. The "Add your crew" panel appears below (not replacing) the existing invite form. Already-member rows are visually struck/greyed. Pending-email members show "pending signup" pill. "Add this crew" button is disabled when eligible_count == 0.
result: [pending]

### 4. Bulk-add flash message
expected: Click "Add this crew" on a crew with 3 members, all new to the project. Flash message reads "Added 3 members from <crew name>; 0 were already on this project." All 3 ProjectMember rows visible in admin or project members page.
result: [pending]

### 5. Pre-onboarding smoke test (SPEC R6 HUMAN-UAT)
expected: As owner, add unregistered@example.com to a crew. Bulk-add that crew to a project. Register a new account as unregistered@example.com. On first login, the new user has a ProjectMember row for that project — they can access it without any manual invitation. The crew roster shows the pending row converted to an active user row.
result: [pending]

### 6. Confirmation email rendering
expected: After bulk-add, verify a confirmation email is delivered via Resend. Subject: "{owner} added you to {project} on ShowStack". Body contains owner label, project name, role, direct "Open project" button with no token URL, and "No action required" note.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
