"""Who's on stage: one part of a day as segments, each with the people on.

Built from what the importer stored (rows, the day's people with the rows
that name them, send/catch events, flags), so the page never re-reads a PDF.
A person is on from their send to their catch when the part has cues for
them; otherwise from the first to the last line listing them in that
segment, at the segment's times.
"""

from dataclasses import dataclass, field

from planner.mic_plan.parser import hm, segment_heading


@dataclass
class Appearance:
    person: object
    on_line: str
    off_line: str
    on_time: str
    off_time: str
    by_cue: bool
    intro_line: str = ''
    order: int = 0            # the row it starts on, for sorting


@dataclass
class Flag:
    kind: str
    text: str
    line: str
    order: int
    person_id: int = None


@dataclass
class Segment:
    name: str
    first_line: str
    t0: str
    t1: str
    is_break: bool
    start: int                # row order range [start, end)
    end: int
    items: list = field(default_factory=list)   # Appearance and Flag, in line order

    @property
    def people(self):
        return [i for i in self.items if isinstance(i, Appearance)]


def line_label(row):
    return row.line_no or '#{}'.format(row.order + 1)


def _windows(events):
    """{person id: [(send event, catch event or None)]}, as the parser pairs them."""
    out = {}
    for e in sorted(events, key=lambda e: (e.event_min if e.event_min is not None else -1,
                                           e.row.order, e.kind != 'send')):
        ws = out.setdefault(e.person_id, [])
        if e.kind == 'send':
            if not ws or ws[-1][1] is not None:
                ws.append([e, None])
        elif ws and ws[-1][1] is None:
            ws[-1][1] = e
    return out


def build(part, rows, people, events):
    """(segments, loose flags) for ``part``. ``rows`` in order, ``people`` the
    day's ShowflowPerson list, ``events`` this part's events (row and person
    loaded). Loose flags belong to no line ("No clock times found")."""
    if not rows:
        return [], [Flag(w['kind'], w['text'], '', -1) for w in part.warnings]
    by_order = {r.order: r for r in rows}
    parser_rows = [r.as_parser_row() for r in rows]
    starts = [k for k, r in enumerate(rows) if r.is_segment]
    if not starts or starts[0] != 0:
        starts = [0] + starts            # what comes before the first segment
    bounds = list(zip(starts, starts[1:] + [len(rows)]))

    segments = []

    def segment_of(order):
        for s in segments:
            if s.start <= order < s.end:
                return s
        return None

    for k, (a, b) in enumerate(bounds):
        head = rows[a]
        name, is_break = segment_heading(parser_rows, a, b)
        if not head.is_segment:
            name = 'Before the first segment' if len(bounds) > 1 else 'Showflow'
        segments.append(Segment(
            name=name, first_line=line_label(head),
            t0=hm(head.segment_t0) if head.is_segment else '',
            t1=hm(head.segment_t1) if head.is_segment else '',
            is_break=is_break, start=rows[a].order, end=rows[b - 1].order + 1))

    windows = _windows(events)
    key = str(part.pk)
    for person in people:
        mentioned = sorted(o for o in person.flags.get('rows', {}).get(key, []) if o in by_order)
        intro = person.flags.get('intro', {}).get(key)
        intro_line = line_label(by_order[intro]) if intro in by_order else ''
        cued = windows.get(person.pk, [])
        # A send or catch line places someone through their cue window, not as
        # "listed" in whatever segment that line happens to fall in.
        cue_rows = {e.row.order for pair in cued for e in pair if e is not None}
        shown = set()         # uncaught sends already shown once
        for s in segments:
            here = [o for o in mentioned if s.start <= o < s.end and o not in cue_rows]
            head = by_order[s.start]
            window = None
            if head.is_segment and head.segment_t0 is not None:
                t0 = head.segment_t0
                t1 = max(head.segment_t1 or t0, t0 + 1)
                for send, catch in cued:
                    on = send.event_min
                    off = catch.event_min if catch else None
                    if catch and segment_of(send.row.order) is segment_of(catch.row.order):
                        # Sent and caught inside one segment's lines ("Guest comes up"):
                        # that segment, whatever time the send was given.
                        if segment_of(send.row.order) is not s:
                            continue
                    elif on is None or on >= t1 or (off is not None and off <= t0):
                        continue
                    if off is None and here == [] and send.pk in shown:
                        continue   # sent, never caught: not on stage for the rest of the day
                    window = (send, catch)
                    shown.add(send.pk)
                    break
            if window:
                send, catch = window
                on_time, off_time = send.event_min, catch.event_min if catch else None
                if catch and segment_of(send.row.order) is segment_of(catch.row.order):
                    on_time, off_time = send.row.est_time, catch.row.est_time   # the lines' own times
                starts_here = [send.row.order] if s.start <= send.row.order < s.end else []
                s.items.append(Appearance(
                    person=person, on_line=line_label(send.row),
                    off_line=line_label(catch.row) if catch else '',
                    on_time=hm(on_time), off_time=hm(off_time) if off_time != on_time else '',
                    by_cue=True, intro_line=intro_line,
                    order=min(here + starts_here) if here or starts_here else s.start))
            elif here:
                s.items.append(Appearance(
                    person=person, on_line=line_label(by_order[here[0]]),
                    off_line=line_label(by_order[here[-1]]), on_time=s.t0, off_time=s.t1,
                    by_cue=False, intro_line=intro_line, order=here[0]))

    loose = []
    for w in part.warnings:
        s = segment_of(w.get('row_order')) if w.get('row_order') is not None else None
        if s is None:
            loose.append(Flag(w['kind'], w['text'], '', -1, w.get('person')))
            continue
        s.items.append(Flag(w['kind'], w['text'], line_label(by_order[w['row_order']]),
                            w['row_order'], w.get('person')))
    for s in segments:
        # In line order; on one line a person comes before the flag about them.
        s.items.sort(key=lambda i: (i.order, isinstance(i, Flag),
                                    getattr(getattr(i, 'person', None), 'display_name', '')))
    return segments, loose
