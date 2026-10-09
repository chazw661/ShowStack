"""How a duplicated pair of rows is judged, and which one survives.

Two tables got doubled by ``Project.duplicate()`` writing a model's own
auto-scaffolded children and then the source's children on top (issue #100):
``AmpChannel`` via ``Amp.save()`` → ``setup_channels()``, and ``MicAssignment``
via ``MicSession.save()`` → ``create_mic_assignments()``. Each has a report
command and a cleanup command, so four commands in total act on these rows and
they all have to agree. The rule is therefore stated once, here, and the
table-specific parts (which columns count as the payload, what must never be
deleted) live in ``amp_channel_dupes.py`` and ``mic_assignment_dupes.py``.

The verdicts
------------
IDENTICAL
    Every row in the group holds the same payload, the all-empty case included.
    The rows are interchangeable; keep the **lowest id**, because anything else
    in the database is likelier to already point at it.

ONE-SIDED
    Exactly one row holds a payload and the rest are empty. The expected shape
    of the issue #100 bug. Keep **the row holding the payload**, whatever its
    id.

CONFLICTING
    Two or more rows hold payloads and they disagree. Someone edited both
    halves of the pair after the duplication, so there is no mechanical winner
    — both answers are somebody's work. Keep nothing; a human decides.

Why the keep-rule is not "keep the oldest"
------------------------------------------
The scaffold is written **first**, so within a pair the empty row has the
**lower** id and the row carrying the engineer's work has the higher one. That
is the opposite of most duplicate cleanups — and the opposite of what
``list_duplicate_presenters`` recommends for presenter rows, where the oldest
is the one ``Presenter.resolve()`` hands back. Keeping the oldest here would
delete the patch and leave the blank. So a keeper is chosen from row
*contents*, never from id order.

The protection veto
-------------------
Classification alone is not enough for a table whose payload lives partly in
related rows. ``MicAssignment`` carries presenters in a child table, so a
victim row can hold something the keeper does not even when the field-level
payloads look decidable. ``losses_from_keeping`` is the backstop: given named
predicates, it refuses any keeper that would let one of them disappear from
the group. A vetoed group is reported as needing a human and is never deleted.
"""


IDENTICAL = 'IDENTICAL'
ONE_SIDED = 'ONE-SIDED'
CONFLICTING = 'CONFLICTING'


def has_content(payload):
    """True when a payload holds anything at all.

    Recurses into tuples and lists so a payload can nest -- a mic assignment's
    is its own fields *plus* a tuple of its presenter slots' fields.
    """
    if isinstance(payload, (tuple, list)):
        return any(has_content(item) for item in payload)
    return bool(payload)


def classify_payloads(payloads):
    """IDENTICAL / ONE-SIDED / CONFLICTING for one group's payloads."""
    if len(set(payloads)) == 1:
        return IDENTICAL
    if sum(1 for payload in payloads if has_content(payload)) == 1:
        return ONE_SIDED
    return CONFLICTING


def choose_keeper(rows, payloads, verdict):
    """The row a verdict points at, or ``None`` when it points at no row.

    ``None`` means "skip this group" and must never be read as "keep the first
    one". ``rows`` and ``payloads`` are parallel sequences.
    """
    if verdict == IDENTICAL:
        return min(rows, key=lambda row: row.id)
    if verdict == ONE_SIDED:
        return next(row for row, payload in zip(rows, payloads)
                    if has_content(payload))
    return None


def losses_from_keeping(rows, keeper, protections):
    """Names of the protected things that keeping ``keeper`` would destroy.

    ``protections`` maps a human-readable name to a predicate over a row. A
    name is returned when some row in the group satisfies its predicate and the
    keeper does not -- i.e. deleting the other rows would remove the last copy
    of that thing from the group. Empty list means the keeper is safe.
    """
    if keeper is None:
        return []
    lost = []
    for name, holds in protections.items():
        holders = [row for row in rows if holds(row)]
        if holders and not any(row.id == keeper.id for row in holders):
            lost.append(name)
    return lost


def decide(rows, payload_of, protections=None):
    """``(verdict, keeper, lost)`` for one group of same-numbered rows.

    ``keeper`` is ``None`` whenever the group must be left alone -- either
    because the verdict is CONFLICTING or because the protection veto fired.
    ``lost`` names what the veto was protecting, and is empty otherwise.
    """
    payloads = [payload_of(row) for row in rows]
    verdict = classify_payloads(payloads)
    keeper = choose_keeper(rows, payloads, verdict)
    lost = losses_from_keeping(rows, keeper, protections or {})
    if lost:
        keeper = None
    return verdict, keeper, lost


def group_by(rows, key):
    """``{key: [rows]}`` keeping only the keys held by more than one row."""
    groups = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    return {value: group for value, group in groups.items() if len(group) > 1}


def norm(value):
    """A comparable form of one field value.

    ``None`` and ``''`` both mean "nothing here" -- a nullable column reads
    ``None`` where a blank-only one reads ``''``, and letting those differ would
    turn a routine ONE-SIDED pair into a CONFLICTING one and park it in the
    manual pile forever. Strings are stripped for the same reason.
    """
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return value
