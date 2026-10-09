"""Which of a pair of duplicated ``MicAssignment`` rows is the real one.

``MicSession.save()`` calls ``create_mic_assignments()``, which writes
``num_mics`` blank ``MicAssignment`` rows. ``Project.duplicate()`` then copied
the source session's assignments *on top of* that scaffold instead of replacing
it, so an 8-mic session came out of duplication holding 16 rows with every
``rf_number`` twice — the same bug as the amp channels in issue #100, one model
over. ``duplicate()`` now drops the scaffold first; the rows earlier
duplications wrote stay until someone clears them.

This module supplies the ``MicAssignment`` half of the job and takes the
verdicts and the keep-rule from ``dupe_verdicts`` — read that docstring first,
especially for why "keep the oldest row" is the wrong rule (the blank scaffold
row is written first and so has the **lower** id).

Why this one needs more care than the amp channels
--------------------------------------------------
An ``AmpChannel``'s whole payload is its own five columns. A ``MicAssignment``
is a parent row:

  * its presenters live entirely in ``PresenterSlot`` children --
    ``MicAssignment.presenter`` looks like a ForeignKey in the source but a
    same-named ``@property`` shadows it, so there is no such column and the
    slots are the only copy,
  * those children carry their own placement, sensitivity, output level,
    notes and mic'd flag,
  * and the A2 card an engineer reads on site is drawn from the slots, not
    from the assignment.

So the payload compared here spans both tables, and on top of that three things
are **protected** outright: a presenter, a note, and the mic'd state. A row
holding the group's only presenter, only note or only mic'd flag is never
deleted, whatever the field-level verdict says. ``dupe_verdicts.decide`` applies
that veto and reports the group as needing a human instead.

The protections are deliberately broader than the payload comparison. The
payload decides *whether a rule can pick a winner*; the veto decides *whether
acting on that winner would destroy something*. Belt and braces: the payload
already makes a presenter-holding row non-empty, so the veto should rarely be
the thing that fires — but "rarely" is not "never", and the row at stake is a
presenter's mic on a live show.

Two commands act on these rows and must not drift apart:

  * ``report_duplicate_mic_assignments`` — read-only,
  * ``cleanup_duplicate_mic_assignments`` — dry-run unless given ``--apply``.

``planner/tests/test_duplicate_mic_assignment_cleanup.py`` pins all of it.
"""

from contextlib import contextmanager

from django.db.models.signals import post_delete

from planner.utils.dupe_verdicts import (
    CONFLICTING, IDENTICAL, ONE_SIDED,
    decide, group_by, has_content, norm,
)

# The assignment's own columns that hold the engineer's work. ``rf_number`` is
# the identity of the row rather than its payload, and ``last_modified`` /
# ``modified_by`` / ``photo`` are bookkeeping. ``group`` is included because a
# copied row carries its colour group and a scaffolded one does not.
#
# ``presenter`` is deliberately absent: despite ``MicAssignment`` declaring
# ``presenter = models.ForeignKey(Presenter, ...)``, a read-only ``@property``
# of the same name further down the class body shadows it, so the field never
# registers with Django and there is no ``presenter_id`` column. The property
# reads the active ``PresenterSlot``, which means a presenter is only ever
# slot-held -- see ``SLOT_FIELDS`` and ``has_presenter``.
ASSIGNMENT_FIELDS = (
    'mic_type', 'is_micd', 'is_d_mic', 'active_presenter_index',
    'placement', 'sensitivity', 'output_level', 'input_channel',
    'notes', 'group_id',
)

# The slot columns worth comparing. ``order`` and ``is_active`` are excluded on
# purpose: they are positional bookkeeping that every slot has, so including
# them would make an otherwise-empty slot register as content and turn routine
# ONE-SIDED pairs into CONFLICTING ones that nothing can ever clean up.
SLOT_FIELDS = (
    'presenter_id', 'mic_type', 'headset_color', 'placement', 'sensitivity',
    'output_level', 'notes', 'is_micd', 'group_id', 'a2_group_id',
)


def slot_signature(slot):
    """One presenter slot as a comparable tuple of strings.

    Everything is rendered as a string so a list of signatures can be sorted
    without comparing an int to a str when one slot has a presenter and another
    does not.
    """
    return tuple(str(norm(getattr(slot, field)) or '')
                 for field in SLOT_FIELDS)


def slot_payload(assignment):
    """The assignment's slots, sorted, with the empty ones dropped.

    Sorted because slot order is not part of what makes two assignments the
    same, and empties dropped so a bare positional slot does not read as work.
    """
    signatures = [slot_signature(slot)
                  for slot in assignment.presenter_slots.all()]
    return tuple(sorted(sig for sig in signatures if has_content(sig)))


def field_patch(assignment):
    """The assignment's own columns as a comparable tuple."""
    return tuple(norm(getattr(assignment, field))
                 for field in ASSIGNMENT_FIELDS)


def payload_of(assignment):
    """Everything that makes this assignment somebody's work, both tables."""
    return (field_patch(assignment), slot_payload(assignment))


def is_blank(assignment):
    """True when neither the assignment nor its slots carry anything."""
    return not has_content(payload_of(assignment))


# ── The protected things ────────────────────────────────────────────────────
# A row holding the group's only copy of any of these is never deleted.

def has_presenter(assignment):
    """A presenter on any of this assignment's slots.

    ``MicAssignment.presenter`` is a property over the active slot, not a
    column, so the slots are the only place a presenter can live. Checking
    every slot rather than just the active one is deliberate: an inactive slot
    still names a person who is on this mic at some point in the session, and
    losing them is losing data.
    """
    return any(slot.presenter_id
               for slot in assignment.presenter_slots.all())


def has_notes(assignment):
    """A note on the assignment or on any of its slots."""
    if (assignment.notes or '').strip():
        return True
    return any((slot.notes or '').strip()
               for slot in assignment.presenter_slots.all())


def has_micd_state(assignment):
    """The MIC'D / D-MIC flags, on the assignment or on any slot."""
    if assignment.is_micd or assignment.is_d_mic:
        return True
    return any(slot.is_micd for slot in assignment.presenter_slots.all())


PROTECTIONS = {
    'presenter': has_presenter,
    'notes': has_notes,
    "mic'd state": has_micd_state,
}


def describe(assignment):
    """A short, human-readable account of what this row holds.

    Used by both commands so the report and the dry-run describe a row the same
    way. Returns ``'blank'`` when there is nothing to show.
    """
    marks = []

    slots = list(assignment.presenter_slots.all())
    names = [slot.presenter.name for slot in slots
             if slot.presenter_id and slot.presenter]
    if names:
        marks.append('presenter=%s' % ', '.join(sorted(set(names))))

    if slots:
        marks.append('slots=%d' % len(slots))

    if has_micd_state(assignment):
        flags = []
        if assignment.is_micd:
            flags.append("MIC'D")
        if assignment.is_d_mic:
            flags.append('D-MIC')
        if any(slot.is_micd for slot in slots):
            flags.append("slot MIC'D")
        marks.append('+'.join(flags))

    if (assignment.notes or '').strip():
        marks.append('notes=%r' % assignment.notes.strip()[:40])
    elif any((slot.notes or '').strip() for slot in slots):
        marks.append('slot notes')

    for field in ('mic_type', 'placement', 'sensitivity', 'output_level',
                  'input_channel'):
        value = norm(getattr(assignment, field))
        if value:
            marks.append('%s=%s' % (field, value))

    if assignment.group_id:
        marks.append('group=%s' % assignment.group_id)

    return '  '.join(marks) if marks else 'blank'


def duplicate_groups(session):
    """``{rf_number: [assignments]}`` for the numbers this session holds twice.

    Ordered by ``(rf_number, id)`` so rows within a group read scaffold-first,
    matching the order they were written in.
    """
    return group_by(
        session.mic_assignments
        .select_related('session')
        .prefetch_related('presenter_slots__presenter')
        .order_by('rf_number', 'id'),
        lambda assignment: assignment.rf_number,
    )


def decide_group(rows):
    """``(verdict, keeper, lost)`` for one group of same-rf_number rows."""
    return decide(rows, payload_of, PROTECTIONS)


def judge(session):
    """``(groups, decisions)`` for one session. Both empty when it is clean.

    ``decisions`` maps rf_number -> ``(verdict, keeper, lost)``.
    """
    groups = duplicate_groups(session)
    decisions = {number: decide_group(rows)
                 for number, rows in groups.items()}
    return groups, decisions


@contextmanager
def numbering_held():
    """Suspend the issue #36 post_delete renumbering for the duration of a block.

    ``planner/signals.py`` renumbers a session's ``rf_number``s to a
    consecutive 1..N after *any* MicAssignment delete. That is right for the
    Mic Tracker's own delete button and wrong -- actively destructive -- for
    this cleanup, for two reasons:

      * **It would hide the duplicates it cannot clean.** A group skipped as
        CONFLICTING keeps both of its rows. Renumbering the session then pulls
        that pair apart (rf 2 and rf 2 become rf 2 and rf 3), so the report
        afterwards calls the session clean while two rows that mean the same
        mic now claim different ones. The one state worse than a known
        duplicate is a hidden one.

      * **It rewrites the numbering the copy is supposed to preserve.** The
        surviving rows came from the source session and already carry its
        numbering; the cleanup's job is to remove the scaffold, not to
        renumber what is left.

    ``renumber_mic_assignments`` remains the tool for collapsing numbering and
    syncing ``num_mics`` -- run it *after* the report is clean, never before,
    or it will do the hiding described above.
    """
    from planner.models import MicAssignment
    from planner.signals import renumber_mic_assignments_after_delete

    was_connected = post_delete.disconnect(
        renumber_mic_assignments_after_delete, sender=MicAssignment)
    try:
        yield
    finally:
        if was_connected:
            post_delete.connect(
                renumber_mic_assignments_after_delete, sender=MicAssignment)
