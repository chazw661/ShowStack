"""Yamaha Editor channel-label CSV import — pure-function parser.

Inverse direction of `planner/utils/yamaha_export.py`. Reads single-section
CSV files OR a `.zip` bundle of multiple section files, classifies the
console family from the [Information] block, parses each section's rows,
and surfaces per-row + file-level errors.

NO Django ORM imports here. The view layer (planner/views.py Phase 2 views)
imports `parse_upload` and threads the result into a `ConsoleImport`
draft + a diff-vs-current-state computation.

Per CONTEXT.md amendments R-01..R-04 (LOCKED):
- DCA sections recognized but skipped (no ConsoleDCA model in v2.0).
- CL/QL [StName] (stereo returns) skipped (no return model).
- Rivage [StName] _BL/_BR skipped (no stereo group B slot in STEREO_CHOICES).
- Upload accepts single .csv OR .zip of section CSVs.

Reference: RESEARCH § "Section-by-Section Parsing Spec",
§ "Per-Section Default-Row Rules", § "Per-Row Error Catalog",
§ "Code Examples".
"""
from __future__ import annotations

import csv
import io
import zipfile
from io import TextIOWrapper

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

KNOWN_SECTIONS = {
    '[InName]',
    '[MixName]',
    '[MtxName]',
    '[StName]',
    '[StMonoName]',
    '[DCAName]',
    '[MuteDCAName]',
}

# Section header -> Django model name (Plan 03 imports this dict)
SECTION_TARGET_MAP = {
    'InName':     'ConsoleInput',          # writes to .source (NOT .name)
    'MixName':    'ConsoleAuxOutput',
    'MtxName':    'ConsoleMatrixOutput',
    'StMonoName': 'ConsoleStereoOutput',
}

# Recognized but skipped per R-01 (no ConsoleDCA model in v2.0)
OUT_OF_SCOPE_SECTIONS = {'DCAName', 'MuteDCAName'}

# ---------------------------------------------------------------------------
# Per-family per-section channel-number maxes (E_KEY_OUT_OF_RANGE guard)
# ---------------------------------------------------------------------------

FAMILY_LIMITS = {
    'cl_ql': {
        'InName':     72,   # CL5 max; QL5 has 64 rows so will never hit this
        'MixName':    24,
        'MtxName':     8,
        'StMonoName':  3,
        'StName':     16,   # CL/QL returns — section recognized but skipped at section level
        'DCAName':    16,
    },
    'rivage_pm': {
        'InName':    288,
        'MixName':    72,
        'MtxName':    36,
        # StName is string-keyed for Rivage; not subject to a numeric cap
    },
}

# ---------------------------------------------------------------------------
# Valid Yamaha color values
# ---------------------------------------------------------------------------

YAMAHA_COLORS = {
    'Off', 'Red', 'Orange', 'Yellow', 'Green',
    'Sky Blue', 'Blue', 'Purple', 'Pink', 'White',
}

# ---------------------------------------------------------------------------
# Default-row name helpers
# ---------------------------------------------------------------------------


def _name_default_input(n: int) -> str:
    """`ch 1`..,`ch 9`, `ch10`..,`ch99`, `ch100`..`ch288`.

    Uses right-justify width-2 for n<100, else bare integer.
    Verified against CL5 fixture (ch 1 for _01, ch10 for _10)
    and Rivage fixture (ch 1 for _001, ch10 for _010).
    """
    return f'ch{n:>2d}' if n < 100 else f'ch{n}'


def _name_default_mix(n: int, family: str) -> str:
    """CL5 rows 17-24 default to `Fx 1`..`Fx 8` with ICON=Effector.
    All other mixes default to `MX{n:>2d}` with ICON=Blank.
    """
    if family == 'cl_ql' and 17 <= n <= 24:
        return f'Fx {n - 16}'
    return f'MX{n:>2d}'


def _name_default_mtx(n: int) -> str:
    return f'MT{n:>2d}'


# StMonoName canonical defaults (CL/QL master stereo bus + mono)
STMONO_DEFAULT_NAMES = {1: 'ST L', 2: 'ST R', 3: 'MONO'}

# Rivage StName canonical defaults (_AL/_AR are both "ST A"; _BL/_BR are skipped)
RIVAGE_STNAME_DEFAULT_NAMES = {
    '_AL': 'ST A',
    '_AR': 'ST A',
    '_BL': 'ST B',
    '_BR': 'ST B',
}

# ---------------------------------------------------------------------------
# Family detection
# ---------------------------------------------------------------------------


def detect_family(lines: list[str]) -> str:
    """Classify a Yamaha Editor CSV by its [Information] block.

    Reads the first 5 stripped non-empty elements of `lines`:
    - Element 0 must be exactly '[Information]'
    - Element 1 is the model string ('CL5', 'QL5', 'CS-R5', ...)
    - Element 2 (Rivage only) starts with 'DSP-'

    Returns 'cl_ql', 'rivage_pm', or 'unknown'.
    """
    stripped = [l.strip() for l in lines[:5] if l.strip()]
    if not stripped or stripped[0] != '[Information]':
        return 'unknown'
    model = stripped[1] if len(stripped) > 1 else ''
    line3 = stripped[2] if len(stripped) > 2 else ''
    if model.startswith(('CL', 'QL')):
        return 'cl_ql'
    if model.startswith('CS-R') or line3.startswith('DSP-'):
        return 'rivage_pm'
    return 'unknown'


# ---------------------------------------------------------------------------
# Default-row detection
# ---------------------------------------------------------------------------


def is_default_row(section: str, family: str, row: dict) -> bool:
    """True iff this parsed row matches the per-section factory default.

    Implements the default-row table from RESEARCH § "Per-Section Default-Row
    Rules". Used by Plan 03's apply step for D-01 smart-skip.
    """
    n = row.get('channel_number')
    name = row.get('name', '')
    color = row.get('color', '')
    icon = row.get('icon', '')
    key = row.get('key', '')

    if section == 'InName':
        if n is None:
            return False
        return (
            name == _name_default_input(n)
            and color == 'Blue'
            and icon == 'Dynamic'
        )

    if section == 'MixName':
        if n is None:
            return False
        if family == 'cl_ql' and 17 <= n <= 24:
            return (
                name == f'Fx {n - 16}'
                and color == 'Orange'
                and icon == 'Effector'
            )
        return (
            name == _name_default_mix(n, family)
            and color == 'Orange'
            and icon == 'Blank'
        )

    if section == 'MtxName':
        if n is None:
            return False
        return (
            name == _name_default_mtx(n)
            and color == 'Orange'
            and icon == 'Blank'
        )

    if section == 'StMonoName':
        if n not in STMONO_DEFAULT_NAMES:
            return False
        return (
            name == STMONO_DEFAULT_NAMES[n]
            and color == 'Orange'
            and icon == 'Blank'
        )

    if section == 'StName' and family == 'rivage_pm':
        if key not in RIVAGE_STNAME_DEFAULT_NAMES:
            return False
        return (
            name == RIVAGE_STNAME_DEFAULT_NAMES[key]
            and color == 'Orange'
            and icon == 'Blank'
        )

    # CL/QL StName (returns), DCAName, MuteDCAName — out of scope in v2.0;
    # never "default" in a sense that matters to the apply step.
    return False


# ---------------------------------------------------------------------------
# Channel-key parsing
# ---------------------------------------------------------------------------


def _parse_channel_key(
    key: str, section: str, family: str
) -> tuple[int | None, str | None]:
    """Parse the row key column into (channel_number, error_code).

    Rivage [StName] keys (_AL, _AR, _BL, _BR) return (None, None) —
    caller treats `key` as a string identifier.

    [MuteDCAName] keys ('DCA 1', 'Mute 1') return (int, None).

    All other sections expect `_NN` or `_NNN` numeric keys.
    Returns (None, 'E_BAD_KEY') on anything unexpected.
    """
    if section == 'StName' and family == 'rivage_pm':
        if key in {'_AL', '_AR', '_BL', '_BR'}:
            return None, None
        return None, 'E_BAD_KEY'

    if section == 'MuteDCAName':
        parts = key.split()
        if len(parts) == 2 and parts[0] in {'DCA', 'Mute'}:
            try:
                return int(parts[1]), None
            except ValueError:
                return None, 'E_BAD_KEY'
        return None, 'E_BAD_KEY'

    # Standard _NN / _NNN numeric keys
    if not key.startswith('_'):
        return None, 'E_BAD_KEY'
    try:
        return int(key.lstrip('_')), None
    except ValueError:
        return None, 'E_BAD_KEY'


# ---------------------------------------------------------------------------
# Single-section file parser
# ---------------------------------------------------------------------------


def parse_section_file(uploaded_file, filename: str = '') -> dict:
    """Parse one Yamaha Editor section CSV file (UTF-8, CRLF).

    `uploaded_file` accepts:
    - A plain binary stream (io.BytesIO, open(..., 'rb'), ZipFile member)
    - A Django UploadedFile (has a `.file` attribute)

    Returns::

        {
          'family': 'cl_ql' | 'rivage_pm' | 'unknown',
          'section': 'InName' | ... | None,
          'header_row': [...],
          'rows': [{'key': '_01', 'channel_number': 1,
                    'name': 'ch 1', 'color': 'Blue', 'icon': 'Dynamic'}, ...],
          'errors': [{'code': str, 'line': int, 'detail': str}, ...],
          'source_filename': str,
        }

    Per CSV-04: never raises on a single bad row. File-level fatal codes
    (E_NO_INFORMATION, E_UNKNOWN_FAMILY, E_NO_SECTION) populate `errors`
    and set section=None.

    T-02-08 mitigation: TextIOWrapper uses errors='replace' so
    non-UTF-8 bytes become replacement characters rather than raising.
    """
    # Support both Django UploadedFile and plain binary streams
    if hasattr(uploaded_file, 'file'):
        binary = uploaded_file.file
        binary.seek(0)
    else:
        binary = uploaded_file
        try:
            binary.seek(0)
        except (AttributeError, io.UnsupportedOperation):
            pass

    result = {
        'family': 'unknown',
        'section': None,
        'header_row': [],
        'rows': [],
        'errors': [],
        'source_filename': filename,
    }

    try:
        # newline='' is NON-NEGOTIABLE per RESEARCH Pitfall 4 (Yamaha files are CRLF).
        # errors='replace' implements T-02-08: non-UTF-8 bytes become U+FFFD
        # rather than raising UnicodeDecodeError.
        text = TextIOWrapper(binary, encoding='utf-8', newline='', errors='replace')
        reader = csv.reader(text)
        raw_rows = list(reader)
    except Exception as exc:
        result['errors'].append({'code': 'E_ENCODING', 'line': 0, 'detail': str(exc)})
        return result

    if not raw_rows:
        result['errors'].append({
            'code': 'E_NO_INFORMATION',
            'line': 0,
            'detail': 'empty file',
        })
        return result

    # Reconstruct line-strings from the first 5 csv rows for family detection.
    # Each row is a list of column values; rejoining with comma gives the raw line
    # shape that detect_family expects (e.g. '[Information]', 'CL5', 'V4.1').
    raw_lines = [','.join(r) for r in raw_rows[:5]]
    result['family'] = detect_family(raw_lines)

    if result['family'] == 'unknown':
        result['errors'].append({
            'code': 'E_UNKNOWN_FAMILY',
            'line': 0,
            'detail': 'no [Information] block or unrecognised model',
        })
        return result

    # Locate the first recognised section header (skip [Information])
    section_index = None
    for i, r in enumerate(raw_rows):
        if r and r[0].startswith('[') and r[0] != '[Information]':
            if r[0] in KNOWN_SECTIONS:
                result['section'] = r[0].strip('[]')
                section_index = i
                break

    if not result['section']:
        result['errors'].append({
            'code': 'E_NO_SECTION',
            'line': 0,
            'detail': 'no recognised section header found',
        })
        return result

    # Out-of-scope sections (DCAName, MuteDCAName per R-01) — log informational,
    # return empty rows.  Zero applied rows means Plan 03's apply step never
    # sees these rows.
    if result['section'] in OUT_OF_SCOPE_SECTIONS:
        result['errors'].append({
            'code': 'W_NO_MODEL_TARGET',
            'line': 0,
            'detail': f'section {result["section"]} not imported in v2.0',
            'section': result['section'],
        })
        return result

    # CL/QL [StName] (stereo returns) — no ConsoleStereoReturn model in v2.0 (R-03).
    # Recognize the section, count skipped rows for informational logging, return
    # zero applied rows so Plan 03's apply step never sees them.
    if result['section'] == 'StName' and result['family'] == 'cl_ql':
        skipped_count = 0
        if section_index is not None and section_index + 2 < len(raw_rows):
            for r in raw_rows[section_index + 2:]:
                if r and r[0].strip():
                    skipped_count += 1
        result['errors'].append({
            'code': 'W_NO_MODEL_TARGET',
            'line': 0,
            'detail': (
                f'CL/QL [StName] (stereo returns) — skipped {skipped_count} rows; '
                f'no target model in v2.0'
            ),
            'section': 'StName',
            'family': 'cl_ql',
            'skipped': skipped_count,
            'reason': 'no_target_model_v2.0',
        })
        return result

    # Extract the column header row (immediately after the section header)
    if section_index + 1 < len(raw_rows):
        result['header_row'] = raw_rows[section_index + 1]

    data_rows = raw_rows[section_index + 2:]

    # Family+section cap — defence against absurd row counts (T-02-06).
    fam_caps = FAMILY_LIMITS.get(result['family'], {})
    section_cap = fam_caps.get(result['section'])

    seen_keys: set = set()
    # Line numbers are 1-indexed; data rows start at section_index+3
    for i, row in enumerate(data_rows, start=section_index + 3):
        if not row or not row[0].strip():
            continue  # blank / empty row — skip silently

        # Pitfall 3: trailing comma on Yamaha rows produces a 5-element list.
        # We need exactly 4 meaningful columns.
        if len(row) < 4:
            result['errors'].append({
                'code': 'E_COLUMN_COUNT',
                'line': i,
                'detail': f'expected ≥4 cols, got {len(row)}',
            })
            continue

        key, name, color, icon = row[0], row[1], row[2], row[3]

        # Parse channel key to get the numeric channel_number (or None for
        # string-keyed Rivage StName rows).
        channel_number, key_err = _parse_channel_key(key, result['section'], result['family'])
        if key_err:
            result['errors'].append({
                'code': key_err,
                'line': i,
                'detail': f'bad key {key!r} in section {result["section"]}',
            })
            continue

        # Rivage [StName] _BL/_BR — skip with informational per R-03.
        # Only _AL and _AR are imported (→ ConsoleStereoOutput L/R).
        if (
            result['section'] == 'StName'
            and result['family'] == 'rivage_pm'
            and key in {'_BL', '_BR'}
        ):
            result['errors'].append({
                'code': 'W_NO_MODEL_TARGET',
                'line': i,
                'detail': (
                    f'rivage stereo group B leg {key} not supported in v2.0 '
                    f'(STEREO_CHOICES only has L/R/M)'
                ),
                'section': result['section'],
            })
            continue

        # Range check — only when channel_number is numeric
        if channel_number is not None and section_cap and channel_number > section_cap:
            result['errors'].append({
                'code': 'E_KEY_OUT_OF_RANGE',
                'line': i,
                'detail': (
                    f'channel {channel_number} exceeds section max '
                    f'{section_cap} for {result["family"]} {result["section"]}'
                ),
            })
            continue

        # Duplicate key guard (first wins)
        key_id = (key, channel_number)
        if key_id in seen_keys:
            result['errors'].append({
                'code': 'E_DUPLICATE_KEY',
                'line': i,
                'detail': f'duplicate key {key!r} — first occurrence wins',
            })
            continue
        seen_keys.add(key_id)

        # Color whitelist — unknown color falls back to Blue and logs E_UNKNOWN_COLOR
        if color and color not in YAMAHA_COLORS:
            result['errors'].append({
                'code': 'E_UNKNOWN_COLOR',
                'line': i,
                'detail': f'unknown color {color!r}; falling back to Blue',
            })
            color = 'Blue'

        # Name length — truncate at 100 chars and log E_NAME_TOO_LONG
        if len(name) > 100:
            result['errors'].append({
                'code': 'E_NAME_TOO_LONG',
                'line': i,
                'detail': f'name truncated from {len(name)} to 100 chars',
            })
            name = name[:100]

        result['rows'].append({
            'key': key,
            'channel_number': channel_number,
            'name': name,
            'color': color or 'Blue',  # empty string → default Blue
            'icon': icon,
        })

    return result


# ---------------------------------------------------------------------------
# Top-level upload entry point
# ---------------------------------------------------------------------------


def parse_upload(uploaded_file, filename: str) -> dict:
    """Top-level parse entry. Handles both single .csv and .zip uploads.

    Branches on zipfile.is_zipfile per R-04 (LOCKED).

    Returns::

        {
          'family': 'cl_ql' | 'rivage_pm' | 'unknown',
          'sections': [parse_section_file_result, ...],  # one per section file
          'fatal_error': str | None,   # set on file-level failure
          'is_zip': bool,
        }

    Zip rules:
    - All member CSVs must report the same family; cross-family = E_MIXED_FAMILIES.
    - T-02-07 zip-slip mitigation: members containing '..' or starting with '/'
      are silently ignored. Members are decoded in-memory via zf.open(name) —
      no extraction to filesystem.
    """
    # Materialise to bytes so we can both detect-zip and re-read the content.
    if hasattr(uploaded_file, 'read'):
        data = uploaded_file.read()
    elif hasattr(uploaded_file, 'file'):
        uploaded_file.file.seek(0)
        data = uploaded_file.file.read()
    else:
        return {
            'family': 'unknown',
            'sections': [],
            'fatal_error': 'E_ENCODING',
            'is_zip': False,
        }

    out: dict = {
        'family': 'unknown',
        'sections': [],
        'fatal_error': None,
        'is_zip': False,
    }

    if zipfile.is_zipfile(io.BytesIO(data)):
        out['is_zip'] = True
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                families: set = set()
                for name in zf.namelist():
                    # T-02-07: reject zip-slip attempts and non-csv members
                    if '..' in name or name.startswith('/'):
                        continue
                    if not name.lower().endswith('.csv'):
                        continue
                    with zf.open(name) as member:
                        section_result = parse_section_file(member, filename=name)
                    out['sections'].append(section_result)
                    if section_result['family'] != 'unknown':
                        families.add(section_result['family'])

                if len(families) > 1:
                    out['fatal_error'] = 'E_MIXED_FAMILIES'
                    return out
                if len(families) == 1:
                    out['family'] = next(iter(families))
                elif not out['sections']:
                    out['fatal_error'] = 'E_NO_SECTION'
        except zipfile.BadZipFile:
            out['fatal_error'] = 'E_ENCODING'
        return out

    # Single-CSV path
    section_result = parse_section_file(io.BytesIO(data), filename=filename)
    out['sections'].append(section_result)
    out['family'] = section_result['family']

    # Surface file-level fatals to the caller for upload-time error banner
    if section_result['section'] is None and section_result['errors']:
        for err in section_result['errors']:
            if err['code'] in {
                'E_ENCODING',
                'E_NO_INFORMATION',
                'E_UNKNOWN_FAMILY',
                'E_NO_SECTION',
            }:
                out['fatal_error'] = err['code']
                break

    return out
