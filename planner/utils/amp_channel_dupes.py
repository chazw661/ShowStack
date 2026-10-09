"""Which of a pair of duplicated ``AmpChannel`` rows is the real one.

``Amp.save()`` calls ``setup_channels()``, which writes one blank
``AmpChannel`` per channel the amp model declares. ``Project.duplicate()`` then
copied the source amp's channels *on top of* that scaffold instead of replacing
it, so a duplicated 4-channel LA12X ended up holding 8 rows numbered
1,1,2,2,3,3,4,4 (issue #100). ``duplicate()`` now drops the scaffold first, so
no new pairs appear; the rows earlier duplications already wrote stay until
someone clears them.

This module supplies the ``AmpChannel`` half of that job — which columns count
as the engineer's work — and takes the verdicts and the keep-rule from
``dupe_verdicts``. Read that module's docstring for the reasoning, in
particular why "keep the oldest row" is the wrong rule here: the blank scaffold
row is written first and so has the **lower** id.

Two commands act on these rows and must not drift apart, which is why the rule
is not stated in either of them:

  * ``report_duplicate_amp_channels`` — read-only,
  * ``cleanup_duplicate_amp_channels`` — dry-run unless given ``--apply``.

``planner/tests/test_duplicate_amp_channel_cleanup.py`` pins all of it.

There is no protection veto here: an ``AmpChannel``'s entire payload is its own
five columns, with no child rows to lose. ``MicAssignment`` does have them, and
``mic_assignment_dupes`` is the module that deals with it.
"""

from planner.utils.dupe_verdicts import (
    CONFLICTING, IDENTICAL, ONE_SIDED,
    classify_payloads, choose_keeper, group_by, has_content, norm,
)

# The columns that hold the engineer's patch. ``channel_number`` is the
# identity of the row rather than its payload, so it is not compared. Keep in
# step with Project.duplicate()'s AmpChannel copy block.
PATCH_FIELDS = (
    'channel_name', 'channel_setting', 'avb_stream', 'aes_input',
    'analog_input',
)

__all__ = [
    'CONFLICTING', 'IDENTICAL', 'ONE_SIDED', 'PATCH_FIELDS',
    'classify', 'duplicate_groups', 'is_blank', 'judge', 'keeper_of',
    'patch_of',
]


def patch_of(channel):
    """The patch values as a comparable tuple.

    ``avb_stream`` is ``null=True`` while the other four are ``blank``-only, so
    a row written before that field existed reads ``None`` where an untouched
    one reads ``''``. ``norm`` collapses both to ``''`` -- see its docstring for
    why letting them differ would be actively harmful.
    """
    return tuple(norm(getattr(channel, field)) for field in PATCH_FIELDS)


def is_blank(patch):
    """True when a patch tuple carries nothing at all."""
    return not has_content(patch)


def classify(channels):
    """IDENTICAL / ONE-SIDED / CONFLICTING for one group of same-numbered rows."""
    return classify_payloads([patch_of(channel) for channel in channels])


def keeper_of(channels, verdict):
    """The row to keep, or ``None`` for CONFLICTING ("skip this group")."""
    return choose_keeper(channels, [patch_of(c) for c in channels], verdict)


def duplicate_groups(amp):
    """``{channel_number: [channels]}`` for the numbers this amp holds twice.

    Ordered by ``(channel_number, id)`` so the rows within a group read
    scaffold-first, matching the order they were written in.
    """
    return group_by(amp.channels.order_by('channel_number', 'id'),
                    lambda channel: channel.channel_number)


def judge(amp):
    """``(groups, verdicts)`` for one amp. Both empty when it is clean."""
    groups = duplicate_groups(amp)
    verdicts = {number: classify(rows) for number, rows in groups.items()}
    return groups, verdicts
