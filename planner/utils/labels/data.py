"""What goes on the beltpack labels: Mic Tracker rows in, label contents out.

``scope_data`` is the only function here that touches the database. It
flattens the selected sessions into a ``ScopeData`` of plain values, and everything after that is pure, so the grouping rules are tested
with hand-built data and no fixtures.

The model, for anyone arriving cold:

* A "pack" is an RF number. ``MicAssignment.rf_number`` exists once per
  session, but RF n is the same physical bodypack for the whole show (each
  pack is fixed to a console channel), so grouping by RF across sessions and
  days is grouping by the physical pack.
* ``PresenterSlot`` rows hang off an assignment in ``order``; a slot with no
  presenter is an empty line on an A2 card and is skipped (and counted).
* There is no per-presenter time. A presenter's time is their session's
  ``start_time``.
* ``MicAssignment.shared_presenters`` is legacy and not read here: nothing in
  the current UI writes it, and the A2 cards are built from slots.

Merging: one presenter on the same pack across consecutive sessions of the
same day is one label (single-name) or one row (running order). A
single-name label carries the first session's time and "Keynote +2"; a
running-order row carries the sessions' positions in the day after the
name, "Sarah McMillan · S1–3", and its separator stays plain. Consecutive means
adjacent in the day's session order; any session in between where the pack
has a different presenter, no presenter, or no RF row breaks the run -- and
so does a session in between that was not selected.
"""

import re
from dataclasses import dataclass, field

from planner.utils.labels.fonts import normalise


@dataclass(frozen=True)
class SessionInfo:
    id: int
    day_id: int
    day_label: str
    index: int          # position within its whole day, selected or not, 0-based
    name: str
    time: str           # "9:00a", or '' when the session has no start time


@dataclass
class ScopeData:
    sessions: list                      # [SessionInfo], selected only, show order
    # rf -> session_id -> [(presenter_id, name)] in slot order, presenters only
    packs: dict = field(default_factory=dict)
    skipped: int = 0                    # slots without a presenter


@dataclass(frozen=True)
class Entry:
    """One presenter's run on one pack: one or more consecutive sessions."""
    pack: int
    presenter_id: int
    name: str
    sessions: tuple                     # (SessionInfo, ...) in order

    @property
    def first(self):
        return self.sessions[0]

    @property
    def extra(self):
        return len(self.sessions) - 1


@dataclass(frozen=True)
class SingleItem:
    pack: int
    day_label: str
    name: str
    time: str
    session: str                        # "Keynote" or "Keynote +2"


@dataclass(frozen=True)
class RunningUnit:
    """Everything one pack shows in running-order mode for one day, before
    it is split onto labels."""
    pack: int
    header: tuple                       # header lines, right block
    groups: tuple                       # ((separator text or None, ((name, suffix), ...)), ...)


# ---------------------------------------------------------------- formatting

def format_time(t):
    """Compact 12-hour: 9:00a, 12:45p. '' for no time."""
    if t is None:
        return ''
    hour = t.hour % 12 or 12
    return '{}:{:02d}{}'.format(hour, t.minute, 'a' if t.hour < 12 else 'p')


def day_label(day_name, day_date):
    """The day's own name if it has one, else "Tue Nov 3"."""
    name = normalise(day_name)
    if name:
        return name
    return '{} {} {}'.format(day_date.strftime('%a'), day_date.strftime('%b'), day_date.day)


def pack_label(pack):
    """The RF number as the A2 tracker badge shows it: 02d."""
    return '{:02d}'.format(pack)


def with_extra(text, extra):
    return '{} +{}'.format(text, extra) if extra else text


def separator_text(session):
    return '{} · {}'.format(session.time, session.name) if session.time else session.name


def session_span(sessions):
    """Positions in the day, 1-based: "S1–3" for a contiguous run, else
    "S1, S3"."""
    positions = [s.index + 1 for s in sessions]
    if positions == list(range(positions[0], positions[0] + len(positions))):
        return 'S{}–{}'.format(positions[0], positions[-1])
    return ', '.join('S{}'.format(p) for p in positions)


def run_suffix(entry):
    """What a running-order row adds after a merged presenter's name."""
    return session_span(entry.sessions) if entry.extra else ''


_DIGITS = re.compile(r'(\d+)')


def natural_key(value):
    """Sort key putting "2" before "10" (and "RF2" before "RF10")."""
    return [int(part) if part.isdigit() else part.lower()
            for part in _DIGITS.split(str(value))]


# ---------------------------------------------------------------- the database

def scope_data(project, session_ids):
    """Flatten the selected sessions into ScopeData. The caller has already
    checked that every id belongs to ``project``."""
    from planner.models import MicAssignment, MicSession, PresenterSlot

    selected = set(session_ids)
    days = (MicSession.objects.filter(day__project=project, pk__in=selected)
            .values_list('day_id', flat=True))
    sessions_qs = (MicSession.objects.filter(day__project=project, day_id__in=days)
                   .select_related('day').order_by('day__date', 'day_id', 'order', 'id'))

    # Adjacency is a property of the whole day, so every session of a
    # touched day is indexed and only then are the unselected ones dropped:
    # an unselected session between two selected ones leaves a gap in the
    # index, and the gap breaks a merge.
    sessions, per_day = [], {}
    for s in sessions_qs:
        index = per_day.get(s.day_id, 0)
        per_day[s.day_id] = index + 1
        if s.id not in selected:
            continue
        sessions.append(SessionInfo(
            id=s.id, day_id=s.day_id, day_label=day_label(s.day.name, s.day.date),
            index=index, name=normalise(s.name), time=format_time(s.start_time),
        ))

    data = ScopeData(sessions=sessions)
    session_ids = [s.id for s in sessions]
    rf_by_assignment = dict(
        MicAssignment.objects.filter(session_id__in=session_ids).values_list('id', 'rf_number')
    )
    slots = (PresenterSlot.objects
             .filter(assignment_id__in=list(rf_by_assignment))
             .order_by('order', 'id')
             .values_list('assignment_id', 'assignment__session_id',
                          'presenter_id', 'presenter__name'))
    for assignment_id, session_id, presenter_id, name in slots:
        if presenter_id is None:
            data.skipped += 1
            continue
        rf = rf_by_assignment[assignment_id]
        data.packs.setdefault(rf, {}).setdefault(session_id, []).append(
            (presenter_id, normalise(name)))
    return data


# ---------------------------------------------------------------- grouping

def pack_entries(data, pack):
    """The pack's presenters in show order, consecutive repeats merged."""
    by_session = data.packs.get(pack, {})
    entries = []
    for session in data.sessions:
        for presenter_id, name in by_session.get(session.id, ()):
            last = entries[-1] if entries else None
            if (last is not None and last.presenter_id == presenter_id
                    and last.sessions[-1].day_id == session.day_id
                    and session.index - last.sessions[-1].index in (0, 1)):
                if last.sessions[-1].id != session.id:
                    entries[-1] = Entry(pack, presenter_id, last.name,
                                        last.sessions + (session,))
                continue
            entries.append(Entry(pack, presenter_id, name, (session,)))
    return entries


def sorted_packs(data):
    return sorted(data.packs, key=natural_key)


def single_name_items(data):
    """One label per presenter run, a pack's labels together."""
    items = []
    for pack in sorted_packs(data):
        for entry in pack_entries(data, pack):
            items.append(SingleItem(
                pack=pack, day_label=entry.first.day_label, name=entry.name,
                time=entry.first.time,
                session=with_extra(entry.first.name, entry.extra),
            ))
    return items


def running_units(data):
    """One unit per pack per day. When one session is selected on that day
    the header names it (day, time, session); with several, the header is
    the day alone.

    Separators appear only when the unit covers more than one session; under
    one, the header or the separator-free list already says enough.
    """
    per_day = {}
    for session in data.sessions:
        per_day[session.day_id] = per_day.get(session.day_id, 0) + 1
    units = []
    for pack in sorted_packs(data):
        by_day = {}
        for entry in pack_entries(data, pack):
            by_day.setdefault(entry.first.day_id, []).append(entry)
        for entries in by_day.values():
            first = entries[0].first
            if per_day[first.day_id] == 1:
                header = tuple(line for line in (first.day_label, first.time, first.name) if line)
            else:
                header = (first.day_label,)
            covered = {s.id for e in entries for s in e.sessions}
            if len(covered) > 1:
                groups = []
                for entry in entries:
                    if groups and groups[-1][0] == entry.first.id:
                        groups[-1][2].append(entry)
                    else:
                        groups.append((entry.first.id, entry.first, [entry]))
                # A merged run is marked on its own row, not the separator:
                # the separator names where the label's reading starts, and
                # the run may be one of several names under it.
                groups = tuple(
                    (separator_text(session), tuple((e.name, run_suffix(e)) for e in group))
                    for _, session, group in groups
                )
            else:
                groups = ((None, tuple((e.name, run_suffix(e)) for e in entries)),)
            units.append(RunningUnit(pack=pack, header=header, groups=groups))
    return units
