"""Row overrides: what the user said about one showflow row, applied as
plan input on every build (``planning.build_day``).

``ShowflowImport.row_overrides`` is a list, one entry per row:

    {'id', 'row': rowkey.describe(...), 'on': [name key], 'off': [...],
     'not_on': [...], 'not_off': [...], 'mic': {name key: 'body' | 'HH'},
     'by', 'by_name', 'at'}

on       they come on at this row          (cued part: a send; cue-free: named here)
off      they go off at this row           (cued: a catch; cue-free: an exit)
not_on   the showflow says they come on here; they don't (its sends and naming dropped)
not_off  it says they go off here; they don't (catches and exits dropped, and a
         group exit here leaves them on)
mic      the type of the appearance they are on at this row

An entry follows its row by ``rowkey.find`` (line label, else start time and
text), so it survives Re-read and Replace. It is applied only while the row's
raw text is what it was when the entry was made: otherwise it is reported
("the showflow changed under your edit", old and new text) and not applied
until the user accepts or drops it. An entry whose row is gone is reported
for the day. Kept on Replace with the part's other settings (importer.confirm).
"""

import secrets

from django.db import transaction
from django.utils import timezone

from . import rowkey
from .parser import name_key

LISTS = ('on', 'off', 'not_on', 'not_off')
MIC_TYPES = ('body', 'HH')


def _rows(part):
    return list(part.rows.order_by('order'))


def resolve(part, rows=None):
    """[(entry, row or None, exact)] for each of ``part``'s entries."""
    rows = rows if rows is not None else _rows(part)
    return [(e,) + rowkey.find(e['row'], rows) for e in part.row_overrides]


def _clean(changes):
    out = {k: list(dict.fromkeys(name_key(n) for n in changes.get(k, ()) if n.strip())) for k in LISTS}
    mic = {name_key(n): t for n, t in (changes.get('mic') or {}).items() if n.strip()}
    if any(t not in MIC_TYPES for t in mic.values()):
        raise ValueError('A mic type is body or HH.')
    for a, b in (('on', 'not_on'), ('off', 'not_off')):
        if set(out[a]) & set(out[b]):
            raise ValueError('Someone is both {} and {} on this row.'.format(a, b.replace('_', ' ')))
    out['mic'] = mic
    return out


def _stale(day):
    from .planning import mark_stale
    mark_stale(day)


@transaction.atomic
def set_row(part, row, changes, user=None):
    """Set what the user says about ``row`` (replacing what they said before);
    nothing left: the entry is dropped. Returns the entry or None."""
    rows = _rows(part)
    keep = [e for e, found, _ in resolve(part, rows) if found is None or found.pk != row.pk]
    changes = _clean(changes)
    entry = None
    if any(changes[k] for k in LISTS) or changes['mic']:
        entry = {'id': secrets.token_hex(4), 'row': rowkey.describe(row, rows), **changes,
                 'by': user.pk if user else None, 'by_name': user.get_username() if user else '',
                 'at': timezone.now().isoformat()}
        keep.append(entry)
    part.row_overrides = keep
    part.save(update_fields=['row_overrides'])
    _stale(part.day)
    return entry


@transaction.atomic
def accept(part, entry_id):
    """Keep an entry whose row changed: it now describes the row as it is."""
    rows = _rows(part)
    for e, found, _ in resolve(part, rows):
        if e['id'] == entry_id:
            if found is None:
                raise ValueError('That line is no longer in this showflow.')
            e['row'] = rowkey.describe(found, rows)
            part.save(update_fields=['row_overrides'])
            _stale(part.day)
            return e
    raise ValueError('No such change.')


@transaction.atomic
def drop(part, entry_id):
    part.row_overrides = [e for e in part.row_overrides if e['id'] != entry_id]
    part.save(update_fields=['row_overrides'])
    _stale(part.day)


def _who(names):
    return ', '.join(names) or 'nobody'


def describe_entry(e):
    """The entry in words: "on: alex host; off: kim keynote; mic: kim keynote HH"."""
    bits = ['{}: {}'.format(k.replace('_', ' '), _who(e[k])) for k in LISTS if e.get(k)]
    bits += ['mic: {} {}'.format(n, t) for n, t in (e.get('mic') or {}).items()]
    return '; '.join(bits)


def plan_input(parts, rows_by_part):
    """What the build needs, from every part's entries:

    (applied, issues): ``applied`` = [(part, row, entry)] for entries whose
    row is unchanged; ``issues`` = plan flags for the rest:
    override_changed (row text changed: old and new) or override_gone.
    """
    applied, issues = [], []
    for part in parts:
        for e, row, exact in resolve(part, rows_by_part[part.pk]):
            line = e['row'].get('line') or '#{}'.format(e['row'].get('order', 0) + 1)
            if row is None:
                issues.append({'kind': 'override_gone', 'row': None, 'person': None, 'entry': e['id'],
                               'part': part.pk,
                               'text': 'Line {} is no longer in this showflow; your change to it ({}) is kept '
                                       'but not applied.'.format(line, describe_entry(e))})
            elif not exact:
                issues.append({'kind': 'override_changed', 'row': row.pk, 'person': None, 'entry': e['id'],
                               'part': part.pk, 'was': e['row']['text'], 'now': rowkey.raw_text(row),
                               'text': 'Line {}: the showflow changed under your edit ({}); not applied '
                                       'until you accept or drop it.'.format(row.line_no or line, describe_entry(e))})
            else:
                applied.append((part, row, e))
    return applied, issues
