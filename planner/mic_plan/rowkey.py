"""Which showflow row is "the same row" after a re-import or Replace.

Things the user did to a row (an override, later a walkthrough check) keep a
description of the row as it was (``describe``). ``find`` looks for it among
a part's current rows:

1. By line label, when the label was there and unique in its part, and
   still is: "112" is "112".
2. Otherwise by start time, then the raw text, fuzzily: the rows with the
   same start (the Start cell, or the estimated time when it is blank;
   within FUZZ_MIN minutes if none match exactly) whose text reads at least
   TEXT_RATIO alike; the most alike wins, then the one whose neighbours
   above and below are unchanged (twins: the same "PPT" row at the same
   time), then the one that is the same n-th of its twins (a run of
   identical rows), then the nearest to where it was.

``exact`` says the row's raw text is unchanged: the caller applies what was
done to it only then, and otherwise says "the showflow changed under your
edit" (never applies it silently).

Rows are anything with line_no, start_text, est_time, order and the text
fields of ShowflowRow (tests pass SimpleNamespace). No Django imports.
"""

import difflib
import re

TEXT_FIELDS = ('line_no', 'start_text', 'end_text', 'duration_text', 'description', 'speaker_text',
               'bsm_text', 'audio_text', 'notes_text')
TEXT_RATIO = 0.75
FUZZ_MIN = 5


def raw_text(row):
    """The row's cells as one string, spaces collapsed: what "changed" means."""
    return ' | '.join(re.sub(r'\s+', ' ', getattr(row, f) or '').strip() for f in TEXT_FIELDS)


def _start(row):
    return re.sub(r'\s+', ' ', (row.start_text or '').strip().lower()) or None


def _unique_lines(rows):
    seen = {}
    for r in rows:
        if r.line_no:
            seen[r.line_no] = seen.get(r.line_no, 0) + 1
    return {line for line, n in seen.items() if n == 1}


def _neighbours(row, rows):
    i = rows.index(row)
    return (raw_text(rows[i - 1]) if i > 0 else None,
            raw_text(rows[i + 1]) if i + 1 < len(rows) else None)


def _nth(row, rows):
    """How many rows before ``row`` read exactly as it does."""
    text = raw_text(row)
    return sum(1 for r in rows[:rows.index(row)] if raw_text(r) == text)


def describe(row, rows):
    """What identifies ``row`` among its part's ``rows`` (in order; JSON-safe)."""
    before, after = _neighbours(row, rows)
    return {'line': row.line_no if row.line_no in _unique_lines(rows) else '',
            'start': _start(row), 'minute': row.est_time, 'order': row.order, 'text': raw_text(row),
            'before': before, 'after': after, 'nth': _nth(row, rows)}


def find(desc, rows):
    """(row, exact) for ``desc`` among ``rows``; (None, False) if it is gone."""
    if desc.get('line') and desc['line'] in _unique_lines(rows):
        row = next(r for r in rows if r.line_no == desc['line'])
        return row, raw_text(row) == desc['text']
    if desc.get('start'):
        pool = [r for r in rows if _start(r) == desc['start']]
    else:
        pool = [r for r in rows if not _start(r) and r.est_time == desc.get('minute')]
        if not pool and desc.get('minute') is not None:
            pool = [r for r in rows if not _start(r) and r.est_time is not None
                    and abs(r.est_time - desc['minute']) <= FUZZ_MIN]
    best, best_key = None, None
    for r in pool:
        text = raw_text(r)
        ratio = 1.0 if text == desc['text'] else difflib.SequenceMatcher(None, text, desc['text']).ratio()
        if ratio < TEXT_RATIO:
            continue
        before, after = _neighbours(r, rows)
        context = (before == desc.get('before')) + (after == desc.get('after'))
        twin = _nth(r, rows) != desc.get('nth') if ratio == 1.0 else True
        key = (-ratio, -context, twin, abs(r.order - desc.get('order', r.order)))
        if best_key is None or key < best_key:
            best, best_key = r, key
    if best is None:
        return None, False
    return best, raw_text(best) == desc['text']
