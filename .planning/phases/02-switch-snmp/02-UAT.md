---
status: complete
phase: 02-switch-snmp
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md]
started: 2026-04-25T02:00:00Z
updated: 2026-04-25T22:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Settings Panel Opens and Saves Community String
expected: Click the gear icon in the dashboard header. A settings panel slides in from the right with a "Community String" input field. Enter a string (e.g., "public"), click "Save Settings". The panel closes and the gear icon briefly flashes green.
result: pass

### 2. Show Mode Toggle Changes Mode
expected: The rollup bar shows a three-segment toggle: Setup / Show / Wrap. Click "Setup" — the button highlights amber and an amber banner appears below: "Setup mode — non-critical alerts suppressed". Click "Show" — banner disappears, button highlights green. Click "Wrap" — banner reappears with "Wrap mode — non-critical alerts suppressed".
result: pass

### 3. Show Mode Persists Across Refresh
expected: Set show mode to "Setup". Refresh the page. The toggle should still show "Setup" as active, and the amber banner should be visible.
result: pass

### 4. Switch Card Port Summary (With Agent Running)
expected: With the agent running against a real switch, switch cards in the Switches section show a collapsed port summary like "24 ports — 22 up — 0 err". If SNMP is not configured, cards show "SNMP not configured" with an "Open Settings" button.
result: blocked
blocked_by: physical-device
reason: "JGS516PE is a Smart Managed Plus switch — does not support SNMP. Need a fully managed switch (M4300, M4500, GSM series) for this test. SNMP unreachable state displayed correctly."

### 5. Switch Card Expands to Port Table
expected: Click a switch card to expand it. A table appears with columns: #, Status, Speed, Bandwidth. Each port row shows a status dot (green=up, red=down), link speed (100M/1G/10G), and bandwidth percentage.
result: blocked
blocked_by: physical-device
reason: "Requires SNMP-capable switch hardware. JGS516PE does not support SNMP."

### 6. Bandwidth Color-Coding
expected: Port bandwidth values are color-coded: green below 70%, amber between 70-90%, red above 90%. Error counters appear in a tooltip when hovering over a port row.
result: blocked
blocked_by: physical-device
reason: "Requires SNMP-capable switch with active traffic for bandwidth data."

### 7. Settings Panel Closes with Escape Key
expected: Open the settings panel. Press Escape. The panel slides closed and the backdrop disappears.
result: pass

## Summary

total: 7
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 3

## Gaps
