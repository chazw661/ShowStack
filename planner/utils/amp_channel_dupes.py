"""The one definition of how a duplicated AmpChannel pair is judged.

Two commands act on these duplicates and they must not drift apart:

  * ``report_duplicate_amp_channels`` -- read-only, says what is there,
  * ``cleanup_duplicate_amp_channels`` -- dry-run by default, deletes the
    redundant row.

A report that classified a pair one way and a cleanup that then kept the other
row would be worse than no cleanup at all, so the verdict and the keep-rule are
stated once, here, and pinned by
``planner/tests/test_duplicate_amp_channel_cleanup.py``.

Where the duplicates came from
------------------------------
``Amp.save()`` calls ``setup_channels()``, which writes one blank
``AmpChannel`` per channel the amp model declares. ``Project.duplicate()`` then
copied the source amp's channels *on top of* that scaffold instead of replacing
it, so a duplicated 4-channel LA12X ended up holding 8 rows numbered
1,1,2,2,3,3,4,4 (issue #100). ``duplicate()`` now drops the scaffold first, so
no new pairs appear.

The ordering matters for the keep-rule: the scaffold is written **first**, so
within a pair the lower id is normally the blank row and the higher id carries
the patch. "Keep the oldest" -- the instinct that is right for most duplicate
cleanups, and the rule ``list_duplicate_presenters`` recommends -- would keep
the blank one here and throw the engineer's patch away. So the verdict is
computed from row *contents*, never from id order.

The verdicts
------------
IDENTICAL
    Every row in the group holds the same patch values, the all-blank case
    included. The rows are interchangeable; keep the lowest id, because
    anything else in the database is likelier to already point at it.

ONE-SIDED
    Exactly one row holds patch data and the rest are blank. This is the
    expected shape of the issue #100 bug. Keep the row holding the data,
    whatever its id.

CONFLICTING
    Two or more rows hold patch data and they disagree. Someone edited both
    halves of the pair after the duplication, so there is no mechanical winner
    -- both answers are somebody's work. Keep nothing; a human decides.
"""

from collections import defaultdict

# The columns that hold the engineer's patch. ``channel_number`` is the
# identity of the row rather than its payload, so it is not compared. Keep in
# step with Project.duplicate()'s AmpChannel copy block.
PATCH_FIELDS = (
    'channel_name', 'channel_setting', 'avb_stream', 'aes_input',
    'analog_input',
)

IDENTICAL = 'IDENTICAL'
ONE_SIDED = 'ONE-SIDED'
CONFLICTING = 'CONFLICTING'


def patch_of(channel):
    """The patch values as a comparable tuple.

    ``avb_stream`` is ``null=True`` while the other four are ``blank``-only, so
    a row written before that field existed reads ``None`` where an untouched
    one reads ``''``. Both mean "nothing patched here" and must not register as
    a disagreement -- that would turn a routine ONE-SIDED pair into a
    CONFLICTING one and park it in the manual pile forever.
    """
    return tuple((getattr(channel, f) or '').strip() for f in PATCH_FIELDS)


def is_blank(patch):
    """True when a patch tuple carries nothing at all."""
    return not any(patch)


def classify(channels):
    """IDENTICAL / ONE-SIDED / CONFLICTING for one group of same-numbered rows."""
    patches = [patch_of(c) for c in channels]
    if len(set(patches)) == 1:
        return IDENTICAL
    if sum(1 for p in patches if not is_blank(p)) == 1:
        return ONE_SIDED
    return CONFLICTING


def keeper_of(channels, verdict):
    """The row to keep, or ``None`` when no rule picks one.

    ``None`` is returned for CONFLICTING and must be treated as "skip this
    group", never as "keep the first one".
    """
    if verdict == IDENTICAL:
        return min(channels, key=lambda c: c.id)
    if verdict == ONE_SIDED:
        return next(c for c in channels if not is_blank(patch_of(c)))
    return None


def duplicate_groups(amp):
    """``{channel_number: [channels]}`` for the numbers this amp holds twice.

    Ordered by ``(channel_number, id)`` so the rows within a group read
    scaffold-first, matching the order they were written in.
    """
    by_number = defaultdict(list)
    for channel in amp.channels.order_by('channel_number', 'id'):
        by_number[channel.channel_number].append(channel)
    return {n: rows for n, rows in by_number.items() if len(rows) > 1}


def judge(amp):
    """``(groups, verdicts)`` for one amp. Both empty when it is clean."""
    groups = duplicate_groups(amp)
    verdicts = {n: classify(rows) for n, rows in groups.items()}
    return groups, verdicts
