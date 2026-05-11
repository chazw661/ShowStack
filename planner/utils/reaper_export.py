"""Reaper .RPP and .RTrackTemplate exporter for MultitrackSession.

References:
- Reaper RPP format verified from CharlesHolbrow/rppp fixtures + LASS-2 RTrackTemplate
- PEAKCOL bit layout verified across 5 sources: JSFX docs, ReaperToolkit,
  SWS source, X-Raym ReaScript, ReaTeam State Chunk Definitions
- Phase 1 of v2.0 multitrack module — see .planning/phases/01-.../01-RESEARCH.md

Trust boundary note (T-02-02): this module does NOT filter sessions by
project. The caller (Plan 04 view) is responsible for verifying that the
session passed in belongs to the current project — this module trusts its
input and is intentionally a pure string-builder with no DB writes.
"""

import time
import uuid
from io import StringIO


# ──────────────────────────────────────────────────────────────────
# Yamaha CL/QL palette → hex (lands in Phase 1, used by Phase 2/5)
# Phase 1 itself does not consume this — `color_override` is the only
# color source in Phase 1. Phase 2 CSV import populates channel-level
# Yamaha colors and resolves through this table.
# ──────────────────────────────────────────────────────────────────
YAMAHA_TO_HEX = {
    'Off':      None,        # → omit PEAKCOL or write 16576
    'Red':      '#FF0000',
    'Orange':   '#FF8800',
    'Yellow':   '#FFDD00',
    'Green':    '#33CC33',
    'Sky Blue': '#00BBDD',
    'Blue':     '#3366FF',
    'Purple':   '#9933FF',
    'Pink':     '#FF33AA',
    'White':    None,        # → use DAW default (Reaper omits PEAKCOL)
}


# ──────────────────────────────────────────────────────────────────
# Color packing (RPP-03)
# ──────────────────────────────────────────────────────────────────

# Reaper's "no custom color" sentinel — what Reaper itself writes when no
# PEAKCOL is configured. Documented in ReaTeam/Doc State Chunk Definitions.
PEAKCOL_NO_COLOR = 16576


def hex_to_peakcol(hex_color):
    """Convert '#RRGGBB' to a Reaper PEAKCOL int.

    Bit layout (cross-platform — SAME in the file regardless of OS):
        PEAKCOL = 0x01000000 | (B << 16) | (G << 8) | R

    The 0x01000000 high bit signals "custom color enabled."
    Returns 16576 (PEAKCOL_NO_COLOR) for empty / None / malformed input.
    """
    if not hex_color:
        return PEAKCOL_NO_COLOR
    h = hex_color.lstrip('#').strip()
    if len(h) != 6:
        return PEAKCOL_NO_COLOR
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return PEAKCOL_NO_COLOR
    return 0x01000000 | (b << 16) | (g << 8) | r


# ──────────────────────────────────────────────────────────────────
# NAME-token sanitization (RESEARCH Pitfall 8)
# ──────────────────────────────────────────────────────────────────

def _sanitize_name(name):
    """Sanitize a track label for the Reaper NAME token.

    Replaces double-quote with single-quote (Reaper NAME accepts either an
    unquoted single word or a "..."-wrapped string with NO internal `"`).
    Returns '(untitled)' for empty / None.
    """
    if not name:
        return '(untitled)'
    return name.replace('"', "'").strip() or '(untitled)'


# ──────────────────────────────────────────────────────────────────
# Track ordering (RPP-04)
# ──────────────────────────────────────────────────────────────────

# Source-type priority for 'console' mode (input first, manual last).
_SOURCE_TYPE_PRIORITY = {
    'input': 0,
    'aux': 1,
    'matrix': 2,
    'stereo': 3,
    'manual': 4,
}


def _source_channel_number(track):
    """Return an int for sorting in 'console' mode.

    For input → input_ch parsed as int (or large number if non-numeric).
    For aux → aux_number; matrix → matrix_number.
    For stereo → stereo_type ordering (L=0, R=1, M=2).
    For manual → track_number (always sorted last via priority anyway).
    """
    src = track.resolved_source
    if src is None:
        return track.track_number  # manual / orphan — sort by stored order
    if track.source_type == 'input':
        try:
            return int(src.input_ch) if src.input_ch else int(src.dante_number or 999999)
        except (ValueError, TypeError):
            return 999999
    if track.source_type == 'aux':
        try:
            return int(src.aux_number)
        except (ValueError, TypeError):
            return 999999
    if track.source_type == 'matrix':
        try:
            return int(src.matrix_number)
        except (ValueError, TypeError):
            return 999999
    if track.source_type == 'stereo':
        order = {'L': 0, 'R': 1, 'M': 2}
        return order.get(src.stereo_type, 999999)
    return track.track_number


def _ordered_enabled_tracks(session):
    """Return a list of enabled tracks ordered per session.track_order_mode.

    'console' — by source-type priority then source channel number ascending.
                Manual tracks sort last (by track_number).
    'dante'   — by resolved_dante_number ascending. Tracks without dante
                number sort after those with a number, by track_number.
                Manual tracks sort last.
    'custom'  — by track_number ascending (engineer's drag order).
    """
    tracks = list(session.tracks.filter(enabled=True))
    mode = session.track_order_mode

    if mode == 'custom':
        return sorted(tracks, key=lambda t: t.track_number)

    if mode == 'dante':
        def dante_key(t):
            d = t.resolved_dante_number
            # Manual tracks ALWAYS last; channels with no dante number after
            # those that have one. Within each bucket, by track_number.
            if t.source_type == 'manual':
                return (2, t.track_number)
            if d is None:
                return (1, t.track_number)
            return (0, d, t.track_number)
        return sorted(tracks, key=dante_key)

    # 'console' (default)
    def console_key(t):
        return (
            _SOURCE_TYPE_PRIORITY.get(t.source_type, 99),
            _source_channel_number(t),
            t.track_number,
        )
    return sorted(tracks, key=console_key)


# ──────────────────────────────────────────────────────────────────
# <TRACK> block writer
# ──────────────────────────────────────────────────────────────────

def _track_block(track, indent=2):
    """Render a single MultitrackTrack as a Reaper <TRACK ...> block.

    Required tokens (verified): NAME, PEAKCOL, TRACKHEIGHT, NCHAN, TRACKID,
    MAINSEND 1 0. Forgetting MAINSEND silently breaks audio routing
    (RESEARCH Pitfall 6).
    """
    pad = ' ' * indent
    label = _sanitize_name(track.resolved_label)
    peakcol = hex_to_peakcol(track.resolved_color)
    guid = '{' + str(uuid.uuid4()).upper() + '}'
    return '\n'.join([
        f'{pad}<TRACK {guid}',
        f'{pad}  NAME "{label}"',
        f'{pad}  PEAKCOL {peakcol}',
        f'{pad}  TRACKHEIGHT 0 0 0',
        f'{pad}  NCHAN 2',
        f'{pad}  TRACKID {guid}',
        f'{pad}  MAINSEND 1 0',
        f'{pad}>',
    ])


# ──────────────────────────────────────────────────────────────────
# Public builders (RPP-01, RPP-05)
# ──────────────────────────────────────────────────────────────────

def build_rpp(session):
    """Generate a complete Reaper .RPP file as a string.

    Tracks filtered to enabled=True and ordered per session.track_order_mode.
    """
    enabled_tracks = _ordered_enabled_tracks(session)
    out = StringIO()
    out.write(f'<REAPER_PROJECT 0.1 "7.0/AudiopatchExporter" {int(time.time())}\n')
    out.write('  RIPPLE 0\n')
    out.write('  GROUPOVERRIDE 0 0 0\n')
    out.write('  AUTOXFADE 1\n')
    out.write('  TEMPO 120 4 4\n')
    out.write('  SAMPLERATE 48000 0 0\n')
    for track in enabled_tracks:
        out.write(_track_block(track, indent=2))
        out.write('\n')
    out.write('>\n')
    return out.getvalue()


def build_rtracktemplate(session):
    """Generate a Reaper .RTrackTemplate file as a string.

    Same per-track output as build_rpp but no <REAPER_PROJECT ...> wrapper —
    just back-to-back <TRACK ...> blocks at indent 0. Verified against real
    LASS-2 .RTrackTemplate fixture.
    """
    enabled_tracks = _ordered_enabled_tracks(session)
    out = StringIO()
    for track in enabled_tracks:
        out.write(_track_block(track, indent=0))
        out.write('\n')
    return out.getvalue()
