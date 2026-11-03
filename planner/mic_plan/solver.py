"""Draft mic plan for one show day: who wears which pack, and what each A2
does when. Pure Python (no Django), so it is tested on plain inputs;
``planning`` builds the inputs from the database and saves the result.

Times are minutes from midnight. The logic follows the prototype solver
(docs/mic_plan/PARSING_RULES.md, "The plan"):

1. Appearances. With send/catch cues: send -> catch, kept on while a
   segment that starts before the catch still lists them; someone listed
   with no cue covering them is on for that segment. Without cues: on at
   the first row naming them, off when the row after their last naming
   row starts (at most the end of that segment); listings in consecutive
   segments merge.
2. Hosts: 3+ appearances, or listed in 3+ segments, get one pack all day.
3. A2 time is the binding constraint. Every mic must finish ``margin``
   before its walk-on. Mics come first: a de-mic (or an idle minute) is done
   only when it makes no open mic any later past its deadline, mic by mic,
   so a run of mics that is late anyway never lets de-mics push other mics
   late. Mics are done as early as they are released (``lead`` before the
   walk-on) when a pack is free; without one the mic waits for a pack to
   free up, and only opens a new pack when waiting any longer would make it
   (or another mic) later. Deadlines that cannot all be met are flagged
   "late" or "tight" with their cause (A2 time, or no pack free at a set
   pack count); a run short of A2 time also gets the smallest pre-mic lead
   that fixes it, and whether one more A2 would. Nothing is retried.
4. Packs: the person's own previous pack if free; else, by pack policy,
   ``fewest_packs``: the one free longest (or recycle_at_breaks' whole plan
   when that needs fewer packs); ``recycle_at_breaks`` (the
   default): a pack last worn before the latest break (or the start of a
   later part), lowest RF first, so within a session a worn pack never goes
   to someone else. Else a new one. A set pack count is binding: at it, a
   mic waits for a de-mic, and goes over (a shortage) only when no pack can
   free up before its walk-on; under ``recycle_at_breaks`` it first waits
   for a pack from before the break if one frees by its deadline, then
   reuses the pack free longest mid-session (flagged). A break too short to
   free the packs worn before it is flagged once. Body and HH are separate
   pools; a "backup" person also wears their own backup pack. RF numbers:
   body, body backups, HH, HH backups, then the emergency spare HH (never
   assigned).
5. Shortages are flagged once per stretch over a set pack count; A2 busy
   minutes are counted once each, and work a segment owes that runs past
   its end is "spill".
"""

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field, replace

HOST_MIN = 3                 # appearances or segments that make someone a host
BODY, HH = 'body', 'HH'
RECYCLE_AT_BREAKS, FEWEST_PACKS = 'recycle_at_breaks', 'fewest_packs'
INF = math.inf


@dataclass(frozen=True)
class Settings:
    a2_count: int = 1
    mic_min: int = 3
    demic_min: int = 3
    premic_lead_min: int = 30
    margin_min: int = 5
    body_pack_count: int = None     # None: report the minimum needed
    hh_count: int = None
    emergency_spare_hh: bool = False
    pack_policy: str = RECYCLE_AT_BREAKS
    # 'earliest' (mic people as they arrive) or 'latest' (the prototype's
    # latest-safe mics; kept to check 'earliest' never needs more packs).
    strategy: str = 'earliest'


@dataclass(frozen=True)
class Row:
    key: int                 # ShowflowRow pk
    part: int
    order: int
    line: str
    minute: int = None


@dataclass(frozen=True)
class Segment:
    key: int                 # the heading row's key
    part: int
    start: int               # row orders [start, end)
    end: int
    name: str
    t0: int
    t1: int
    is_break: bool = False


@dataclass(frozen=True)
class Person:
    key: int
    name: str
    mic_type: str = BODY     # BODY or HH
    backup: str = None       # None, BODY or HH: an extra pack of their own


@dataclass(frozen=True)
class Cue:
    kind: str                # 'send' | 'catch'
    person: int
    row: int                 # row key
    minute: int = None


@dataclass(frozen=True)
class Day:
    rows: tuple
    segments: tuple
    people: tuple
    cues: tuple
    listings: dict           # person key -> row keys naming them (Speaker / welcome, not cues)
    cued_parts: frozenset    # parts whose on/off comes from cues


@dataclass
class Appearance:
    person: int
    part: int
    on: float
    off: float
    on_row: int              # row keys
    off_row: int
    source: str              # 'cue' | 'listed' | 'host'
    mic_type: str = BODY
    assumed: str = ''        # what the plan assumed, in words
    note_row: int = None     # the row that assumption is about
    is_host: bool = False
    key: int = 0             # index in Plan.appearances


@dataclass
class Assignment:
    appearance: int
    rf: int
    how: str                 # 'host' | 'same as before' | 'recycled' | 'new' | 'backup'
    backup: bool = False


@dataclass
class Action:
    a2_index: int
    seq: int
    kind: str                # 'mic' | 'demic'
    start_min: float
    end_min: float
    person: int
    person_name: str
    rf_number: int
    appearance: int
    row: int                 # the row it sits on
    segment: int             # the segment heading row it falls in, or None
    reason: str
    late: bool = False
    tight: bool = False
    wait_min: int = 0
    backup: bool = False
    released: float = None   # when it could first be done (not saved)
    due: float = None        # mics: finish by (not saved)


@dataclass
class Pack:
    rf: int
    pool: str
    backup_of: int = None    # person key for a backup pack
    host: bool = False
    spare: bool = False
    label: str = ''


@dataclass
class Plan:
    appearances: list = field(default_factory=list)
    assignments: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    packs: list = field(default_factory=list)
    flags: list = field(default_factory=list)    # {kind, text, row, person}
    busy: dict = field(default_factory=dict)     # segment key -> [minutes per A2]
    # segment key -> {'minutes', 'into' (segment key)}: A2 work the segment
    # owes (de-mics released in it, mics due in it) finishing after it ends.
    spill: dict = field(default_factory=dict)
    swaps: int = 0
    mid_session: int = 0     # packs that went to someone else within a session
    from_policy: str = None  # fewest_packs: set when recycle_at_breaks' plan needed fewer packs


def hm(t):
    t = int(round(t))
    h, m = divmod(t, 60)
    return '{}:{:02d}{}'.format((h - 1) % 12 + 1, m, 'a' if h % 24 < 12 else 'p')


class SolverError(Exception):
    pass


# --------------------------------------------------------------------------
# Appearances
# --------------------------------------------------------------------------

class _Index:
    def __init__(self, day):
        self.day = day
        self.row = {r.key: r for r in day.rows}
        self.part_rows = {}
        for r in sorted(day.rows, key=lambda r: (r.part, r.order)):
            self.part_rows.setdefault(r.part, []).append(r)
        self.part_segs = {}
        for s in sorted(day.segments, key=lambda s: (s.part, s.start)):
            self.part_segs.setdefault(s.part, []).append(s)
        self.people = {p.key: p for p in day.people}

    def seg_of(self, row):
        for s in self.part_segs.get(row.part, ()):
            if s.start <= row.order < s.end:
                return s
        return None

    def seg_index(self, row):
        segs = self.part_segs.get(row.part, [])
        for k, s in enumerate(segs):
            if s.start <= row.order < s.end:
                return k
        return -1           # before the first segment

    def minute(self, row):
        """A row's time; a row without one takes its segment's start."""
        if row.minute is not None:
            return row.minute
        s = self.seg_of(row)
        return s.t0 if s else None

    def line(self, key):
        r = self.row.get(key)
        return (r.line or '#{}'.format(r.order + 1)) if r else '?'


def _listed_segments(ix, person):
    """{part: {segment index: [rows]}} where ``person`` is listed."""
    out = {}
    for key in ix.day.listings.get(person, ()):
        row = ix.row.get(key)
        if row is None:
            continue
        out.setdefault(row.part, {}).setdefault(ix.seg_index(row), []).append(row)
    return out


def _cue_appearances(ix, person, part, cues, listed):
    segs = ix.part_segs.get(part, [])
    ordered = sorted(cues, key=lambda c: (c.minute if c.minute is not None else ix.minute(ix.row[c.row]) or 0,
                                          ix.row[c.row].order, c.kind != 'send'))
    windows = []
    for c in ordered:
        t = c.minute if c.minute is not None else ix.minute(ix.row[c.row])
        if t is None:
            continue
        if c.kind == 'send':
            if not windows or windows[-1]['off'] is not None:
                windows.append({'on': t, 'off': None, 'on_row': c.row, 'off_row': None})
        elif windows and windows[-1]['off'] is None:
            windows[-1]['off'], windows[-1]['off_row'] = max(t, windows[-1]['on']), c.row
    # As the parser's "No cue" rule: listed in a segment = named by its
    # heading row (its Speaker cell), not by a welcome line just before it.
    listed_in = {k: [r for r in rows if r.order == segs[k].start]
                 for k, rows in listed.get(part, {}).items() if k >= 0}
    listed_in = {k: rows for k, rows in listed_in.items() if rows}
    out = []
    for w in windows:
        app = Appearance(person, part, w['on'], w['off'], w['on_row'], w['off_row'] or w['on_row'], 'cue')
        if w['off'] is None:
            # Never caught: on through the segment they were sent into, and on
            # through any segments straight after it that still list them.
            k = next((k for k, s in enumerate(segs) if s.t0 <= w['on'] < s.t1), None)
            if k is None:
                k = next((k for k, s in enumerate(segs) if s.t0 >= w['on']), None)
            off = w['on'] + 20 if k is None else segs[k].t1
            while k is not None and k + 1 < len(segs) and (k + 1) in listed_in:
                k += 1
                off = segs[k].t1
            app.off = off
            app.assumed = 'never caught; assumed off at {}'.format(hm(off))
            app.note_row = w['on_row']
        else:
            # Caught, but a segment starting before the catch still lists them.
            later = [segs[k].t1 for k in listed_in if k >= 0 and w['on'] <= segs[k].t0 <= w['off']]
            if later and max(later) > w['off'] + 1:
                app.assumed = 'caught at {} but still listed; kept on until {}'.format(
                    hm(w['off']), hm(max(later)))
                app.note_row = w['off_row']
                app.off = max(later)
        out.append(app)
    # Listed in a segment no cue window covers: on for that segment.
    for k, rows in sorted(listed_in.items()):
        if k < 0:
            continue
        s = segs[k]
        if any(a.on - 6 <= s.t0 <= a.off for a in out if a.source == 'cue'):
            continue
        first = min(rows, key=lambda r: r.order)
        last = max(rows, key=lambda r: r.order)
        out.append(Appearance(person, part, s.t0, s.t1, first.key, last.key, 'listed',
                              assumed='listed with no send/catch; assumed {}-{}'.format(hm(s.t0), hm(s.t1)),
                              note_row=first.key))
    return out


def _listed_appearances(ix, person, part, listed):
    """Cue-free: stretches of rows naming them in consecutive segments."""
    rows = sorted((r for rows in listed.get(part, {}).values() for r in rows), key=lambda r: r.order)
    part_rows = ix.part_rows.get(part, [])
    by_order = {r.order: k for k, r in enumerate(part_rows)}
    stretches = []
    for r in rows:
        k = ix.seg_index(r)
        if stretches and k - stretches[-1]['seg'] in (0, 1):
            stretches[-1]['rows'].append(r)
            stretches[-1]['seg'] = k
        else:
            stretches.append({'rows': [r], 'seg': k})
    out = []
    for st in stretches:
        first, last = st['rows'][0], st['rows'][-1]
        on = ix.minute(first)
        if on is None:
            continue
        seg = ix.seg_of(last)
        nxt = part_rows[by_order[last.order] + 1] if by_order[last.order] + 1 < len(part_rows) else None
        off = nxt.minute if nxt is not None and nxt.minute is not None else None
        cap = seg.t1 if seg else None
        if off is None or (cap is not None and off > cap):
            off = cap if cap is not None else ix.minute(last)
        if off <= on and cap is not None:
            off = cap        # the next row has no later time: on to the end of the segment
        off = max(off, on)
        out.append(Appearance(person, part, on, off, first.key, last.key, 'listed'))
    return out


def appearances(day, ix=None):
    """All appearances of the day, hosts folded into one; and host keys."""
    ix = ix or _Index(day)
    cues_by = {}
    for c in day.cues:
        row = ix.row.get(c.row)
        if row is not None:
            cues_by.setdefault((c.person, row.part), []).append(c)
    out, hosts = [], set()
    # Name order, not key order: keys follow the order a re-import happened to
    # create people in, and ties must break the same way every time.
    for person in sorted(ix.people, key=lambda k: (ix.people[k].name, k)):
        p = ix.people[person]
        listed = _listed_segments(ix, person)
        mine = []
        for part in sorted(ix.part_rows):
            if part in day.cued_parts:
                mine += _cue_appearances(ix, person, part, cues_by.get((person, part), []), listed)
            else:
                mine += _listed_appearances(ix, person, part, listed)
        mine = _merge_overlaps(mine)
        segments = sum(len([k for k in segs if k >= 0]) for segs in listed.values())
        for a in mine:
            a.mic_type = p.mic_type
        if mine and (len(mine) >= HOST_MIN or segments >= HOST_MIN):
            hosts.add(person)
            first = min(mine, key=lambda a: a.on)
            last = max(mine, key=lambda a: a.off)
            mine = [Appearance(person, first.part, first.on, last.off, first.on_row, last.off_row, 'host',
                               mic_type=p.mic_type, is_host=True)]
        out += mine
    out.sort(key=lambda a: (a.on, ix.people[a.person].name, a.person))
    for k, a in enumerate(out):
        a.key = k
    return out, hosts


def _merge_overlaps(apps):
    apps = sorted(apps, key=lambda a: a.on)
    out = []
    for a in apps:
        if out and a.on <= out[-1].off and a.part == out[-1].part:
            prev = out[-1]
            if a.off > prev.off:
                prev.off, prev.off_row = a.off, a.off_row
            if a.assumed and not prev.assumed:
                prev.assumed, prev.note_row = a.assumed, a.note_row
            continue
        out.append(a)
    return out


# --------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------

@dataclass
class _Task:
    kind: str
    app: Appearance
    rel: float
    due: float = None        # mics: finish by
    backup: bool = False
    done: bool = False
    pack_wait: bool = False  # mics: once waited on the pack limit when it could still be on time


@dataclass
class _Pack:
    pool: str
    free_at: float = 0
    backup_of: int = None
    host: bool = False
    wearers: list = field(default_factory=list)   # appearance keys
    tmp: int = 0
    rf: int = 0
    off: float = INF         # while worn: when its wearer comes off (INF for a host)
    session: int = -1        # the last session it was worn in


def _overrun(frees, mics, mic_min):
    """{id(mic): minutes past its deadline} if the open mics are done
    earliest-deadline-first by A2s free at ``frees``."""
    frees = list(frees)
    out = {}
    for m in sorted(mics, key=lambda m: (m.due, m.app.key, m.backup)):
        j = min(range(len(frees)), key=frees.__getitem__)
        end = max(frees[j], m.rel) + mic_min
        frees[j] = end
        out[id(m)] = max(0, end - m.due)
    return out


LEAD_MAX = 240               # MicPlanSettings.premic_lead_min's upper bound


def session_starts(day):
    """[(minute, row key)] where a session starts: each break segment's
    start, and the start of a part that begins after every earlier part has
    ended. Sessions run between them (and the start and end of the day)."""
    out = [(s.t0, s.key) for s in day.segments if s.is_break]
    by_part = {}
    for seg in day.segments:
        by_part.setdefault(seg.part, []).append(seg)
    end = None
    for segs in sorted(by_part.values(), key=lambda segs: min(x.t0 for x in segs)):
        first = min(segs, key=lambda x: (x.t0, x.start))
        if end is not None and first.t0 >= end:
            out.append((first.t0, first.key))
        end = max(x.t1 for x in segs) if end is None else max(end, max(x.t1 for x in segs))
    return sorted(set(out))


def solve(day, settings=Settings(), suggest=True):
    """The day's plan. ``suggest``: work out the fix for each run of late
    mics the A2 can't reach (re-solves the day, so off inside that).

    fewest_packs never needs more packs than recycle_at_breaks: its greedy
    reuse can cost a pack (a mic waiting idle for a pack to free up leaves
    the A2 no time for de-mics later), so the day is also solved with
    recycle_at_breaks, and that plan is used when it needs fewer body packs
    (or as many, and fewer HH) and has no more late, tight or short flags."""
    plan = _solve(day, settings, suggest)
    if settings.pack_policy != FEWEST_PACKS:
        return plan
    alt = _solve(day, replace(settings, pack_policy=RECYCLE_AT_BREAKS), suggest)
    if _fewer_packs(alt, plan):
        # Mid-session reuse and break turnover are no concern of fewest_packs.
        alt.flags = [f for f in alt.flags if f['kind'] not in ('reuse', 'break')]
        alt.from_policy = RECYCLE_AT_BREAKS
        return alt
    return plan


def _fewer_packs(a, b):
    sa, sb = summary(a), summary(b)
    if any(sa[k] > sb[k] for k in ('late', 'tight', 'shortage')):
        return False
    return (sa['body'], sa['hh']) < (sb['body'], sb['hh'])


def _solve(day, settings, suggest):
    ix = _Index(day)
    plan = Plan()
    apps, hosts = appearances(day, ix)
    plan.appearances = apps
    if not apps:
        return plan
    S = settings
    n = max(1, S.a2_count)

    # Back on within the pre-mic lead of coming off: they keep the pack on
    # (no de-mic, no new mic) rather than being de-mic'd and mic'd again.
    by_person = {}
    for a in apps:
        by_person.setdefault(a.person, []).append(a)
    kept_next = {}           # appearance key -> the next one wearing the same pack
    for mine in by_person.values():
        mine.sort(key=lambda a: a.on)
        for prev, nxt in zip(mine, mine[1:]):
            if nxt.on - prev.off < S.premic_lead_min:
                kept_next[prev.key] = nxt.key
    kept = set(kept_next.values())
    app_by_key = {a.key: a for a in apps}

    tasks = []
    for a in apps:
        p = ix.people[a.person]
        kinds = [False] + ([True] if p.backup else [])
        for backup in kinds:
            if a.key not in kept:
                tasks.append(_Task('mic', a, a.on - S.premic_lead_min, due=a.on - S.margin_min,
                                   backup=backup))
            if not a.is_host and a.key not in kept_next:
                tasks.append(_Task('demic', a, a.off, backup=backup))
    start = min(t.rel for t in tasks)
    frees = [start] * n
    seqs = [0] * n
    packs = []
    worn = {}                # (appearance key, backup) -> _Pack
    behind = []              # (late or tight mic action, its flag)
    last = {}                # person -> their last regular pack
    backups = {}             # person -> backup pack
    limits = {BODY: S.body_pack_count,
              HH: None if S.hh_count is None else max(0, S.hh_count - (1 if S.emergency_spare_hh else 0))}
    recycle = S.pack_policy == RECYCLE_AT_BREAKS
    starts = session_starts(day)
    marks = [m for m, _ in starts]
    turnover = {}            # session start index -> {'mics': set, 'packs': set} (break too short)
    reuse_flags = []         # (flag, pack): mid-session reuse at a set count, RF filled in later

    def session_of(on):
        """A walk-on at or after a session start is in that session."""
        return bisect_right(marks, on)

    def allowed(p, task):
        """May this regular pack go to ``task``'s person under the policy?"""
        return not recycle or p is last.get(task.app.person) or p.session < session_of(task.app.on)

    def at_limit(task):
        pool = pool_of(task)
        return (not task.backup and limits[pool] is not None
                and sum(1 for p in packs if p.pool == pool) >= limits[pool])

    def pool_of(task):
        if task.backup:
            return ix.people[task.app.person].backup
        return task.app.mic_type

    def free_pack(task, t, fallback=False):
        """(pack, how) for ``task`` now, or (None, None). ``fallback``: at a
        set count under recycle_at_breaks, the pack free longest even if it
        was worn this session (how 'mid-session')."""
        if task.backup:
            return backups.get(task.app.person), 'backup'
        pool = pool_of(task)
        free = [p for p in packs if p.pool == pool and p.backup_of is None and p.free_at <= t]
        mine = last.get(task.app.person)
        if mine in free:
            return mine, 'same as before'
        if not recycle:
            if free:
                return min(free, key=lambda p: (p.free_at, p.tmp)), 'recycled'
            return None, None
        ok = [p for p in free if allowed(p, task)]
        if ok:
            return min(ok, key=lambda p: p.tmp), 'recycled'      # down the line
        if fallback and free:
            return min(free, key=lambda p: (p.free_at, p.tmp)), 'mid-session'
        return None, None

    def can_free_in_time(task, t, by=None, any_pack=False):
        """Could a pack of the task's pool (one the policy allows, unless
        ``any_pack``) be free in time for it to be mic'd by ``by`` (its
        deadline), if this A2 de-mic'd it as soon as possible?"""
        pool = pool_of(task)
        by = task.due if by is None else by
        for p in packs:
            if p.pool != pool or p.backup_of is not None:
                continue
            if not any_pack and not allowed(p, task):
                continue
            ready_at = p.free_at if p.free_at < INF else max(t, p.off) + S.demic_min
            if ready_at + S.mic_min <= by:
                return True
        return False

    def blocked(task, t):
        """At a set pack count with none free: the mic waits for a de-mic,
        unless no pack can free up before the walk-on (then it goes over the
        count, and the shortage is flagged)."""
        pool = pool_of(task)
        if task.backup or limits[pool] is None:
            return False
        if sum(1 for p in packs if p.pool == pool) < limits[pool] or free_pack(task, t)[0] is not None:
            return False
        if recycle:
            # A pack from before the break, if one frees by the deadline;
            # else one free now, reused mid-session; else as fewest_packs.
            if can_free_in_time(task, t):
                return True
            if free_pack(task, t, fallback=True)[0] is not None:
                return False
            return can_free_in_time(task, t, by=task.app.on, any_pack=True)
        return can_free_in_time(task, t, by=task.app.on)

    def pack_for(task, t):
        p, h = free_pack(task, t)
        if p is None and at_limit(task):
            p, h = free_pack(task, t, fallback=True)
        return p, h

    def new_pack(task):
        pool = pool_of(task)
        p = _Pack(pool, backup_of=task.app.person if task.backup else None, tmp=len(packs))
        packs.append(p)
        return p

    def row_at(app, t):
        rows = ix.part_rows.get(app.part, [])
        best = rows[0] if rows else None
        for r in rows:
            m = ix.minute(r)
            if m is not None and m <= t + 0.01:
                best = r
        return best

    def record(task, i, t, pack, how):
        dur = S.mic_min if task.kind == 'mic' else S.demic_min
        end = t + dur
        a = task.app
        person = ix.people[a.person]
        late = tight = False
        wait = 0
        if task.kind == 'mic':
            here = session_of(a.on)
            if not task.backup:
                if how in ('recycled', 'mid-session') and pack.session >= here:
                    plan.mid_session += 1
                if how == 'mid-session':
                    reuse_flags.append(({'kind': 'reuse', 'row': a.on_row, 'person': a.person}, pack, task))
                elif how == 'new' and recycle and here > 0:
                    # Packs worn before the break whose wearer is off by this
                    # walk-on, but not yet free: the break was too short.
                    waiting = {id(p) for p in packs if p is not pack and p.pool == pack.pool
                               and p.backup_of is None and p.session < here and p.free_at > t
                               and p.off <= a.on}
                    if waiting:
                        slot = turnover.setdefault(here - 1, {'mics': set(), 'packs': set()})
                        slot['mics'].add(id(task))
                        slot['packs'] |= waiting
                how = 'recycled' if how == 'mid-session' else how
            pack.free_at = INF
            pack.wearers.append(a.key)
            worn[(a.key, task.backup)] = pack
            k = a.key
            while k in kept_next:
                k = kept_next[k]
            pack.off = INF if a.is_host else app_by_key[k].off
            pack.session = len(marks) if a.is_host else bisect_left(marks, pack.off)
            if task.backup:
                backups[a.person] = pack
                reason = 'backup'
            else:
                last[a.person] = pack
                reason = 'host' if a.is_host else {'same as before': 'same pack', 'recycled': 'recycled',
                                                    'new': 'new pack'}[how]
            late = end > a.on
            tight = not late and end > task.due
        else:
            pack.free_at = end
            wait = int(round(t - task.rel))
            reason = 'at catch' if wait <= 1 else '{} min after catch'.format(wait)
            if a.source != 'cue':
                reason = 'when off' if wait <= 1 else '{} min after off'.format(wait)
        row = row_at(a, t)
        seg = ix.seg_of(row) if row else None
        seqs[i] += 1
        plan.actions.append(Action(
            a2_index=i + 1, seq=seqs[i], kind=task.kind, start_min=t, end_min=end, person=a.person,
            person_name=person.name, rf_number=0, appearance=a.key, row=row.key if row else None,
            segment=seg.key if seg else None, reason=reason, late=late, tight=tight, wait_min=wait,
            backup=task.backup, released=task.rel, due=task.due))
        plan.actions[-1]._pack = pack
        if task.kind == 'mic':
            plan.assignments.append(Assignment(a.key, 0, 'backup' if task.backup else
                                               'host' if a.is_host else how, backup=task.backup))
            plan.assignments[-1]._pack = pack
            k = a.key
            while k in kept_next:            # the same pack stays on for their next appearance
                k = kept_next[k]
                worn[(k, task.backup)] = pack
                plan.assignments.append(Assignment(k, 0, 'backup' if task.backup else 'same as before',
                                                   backup=task.backup))
                plan.assignments[-1]._pack = pack
        if late or tight:
            cause = 'pack' if task.pack_wait else 'a2'
            if late:
                text = "Line {}: {} is mic'd {}-{} but walks on at {}{}.".format(
                    ix.line(a.on_row), person.name, hm(t), hm(end), hm(a.on), ' (backup)' if task.backup else '')
            else:
                text = 'Line {}: {} is ready at {}, {} min before walking on (margin {}).'.format(
                    ix.line(a.on_row), person.name, hm(end), int(round(a.on - end)), S.margin_min)
            plan.flags.append({'kind': 'late' if late else 'tight', 'row': a.on_row, 'person': a.person,
                               'cause': cause, 'text': '{} Cause: {}.'.format(text, cause_text(task))})
            behind.append((plan.actions[-1], plan.flags[-1]))
        return end

    def cause_text(task):
        if not task.pack_wait:
            return 'A2 time'
        pool = pool_of(task)
        if pool == BODY:
            return 'no pack free (body limit {})'.format(S.body_pack_count)
        return 'no pack free (handheld limit {}{})'.format(
            S.hh_count, ', 1 kept spare' if S.emergency_spare_hh else '')

    guard = 0
    while not all(t.done for t in tasks):
        guard += 1
        if guard > 200000:
            raise SolverError('The schedule did not finish.')
        i = min(range(n), key=frees.__getitem__)
        t = frees[i]
        open_mics = [x for x in tasks if x.kind == 'mic' and not x.done]
        ready = [m for m in open_mics if m.rel <= t]
        # Waiting on the pack count: no A2 time helps them until a de-mic.
        stuck = {id(m) for m in ready if blocked(m, t)}
        for m in ready:
            if id(m) in stuck and t + S.mic_min <= m.due:
                m.pack_wait = True
        ready = [m for m in ready if id(m) not in stuck]
        open_mics = [m for m in open_mics if id(m) not in stuck]
        demics = [x for x in tasks if x.kind == 'demic' and not x.done and x.rel <= t
                  and (x.app.key, x.backup) in worn]
        base = _overrun(frees, open_mics, S.mic_min)

        def ok_after(delay):
            """Mics come first: holding this A2 ``delay`` min makes no open
            mic any later past its deadline (on - margin)."""
            trial = list(frees)
            trial[i] = t + delay
            after = _overrun(trial, open_mics, S.mic_min)
            return all(after[k] <= base[k] + 1e-9 for k in base)

        job = pack = how = None
        if demics and ok_after(S.demic_min):
            job = min(demics, key=lambda x: (x.rel, x.app.key))
            pack = worn[(job.app.key, job.backup)]
        elif ready:
            if S.strategy == 'earliest':
                # Mic'd as they arrive: when a pack is free, or when none can
                # free up in time anyway (waiting would only make it later).
                with_pack = []
                for m in ready:
                    p, h = pack_for(m, t)
                    if p is not None or (m.backup and m.app.person not in backups) or \
                            (not m.backup and not can_free_in_time(m, t)):
                        with_pack.append((m, p, h))
                if with_pack:
                    job, pack, how = min(with_pack, key=lambda x: (x[0].due, x[0].app.key))
            if job is None and not ok_after(1):
                job = min(ready, key=lambda m: (m.due, m.app.key))
                pack, how = pack_for(job, t)
            if job is not None and pack is None:
                pack, how = new_pack(job), 'new'
        if job is None:
            later = [x.rel for x in tasks if not x.done and x.rel > t]
            later += [p.free_at for p in packs if t < p.free_at < INF]
            frees[i] = min(later) if later and not ready else t + 1
            if not later and not ready:
                frees[i] = t + 1
            continue
        frees[i] = record(job, i, t, pack, how)
        job.done = True

    if suggest:
        _suggest(day, S, behind, ix)
    _number(plan, packs, S, ix)
    for flag, pack, task in reuse_flags:
        pool = pool_of(task)
        flag['text'] = 'Line {}: RF {} reused mid-session \u2014 {} count ({}) reached.'.format(
            ix.line(task.app.on_row), pack.rf, *(('body pack', S.body_pack_count) if pool == BODY
                                                  else ('handheld', S.hh_count)))
        plan.flags.append(flag)
    for k, slot in sorted(turnover.items()):
        n_packs = min(len(slot['mics']), len(slot['packs']))
        minute, key = starts[k]
        brk = next((x for x in day.segments if x.key == key), None)
        plan.flags.append({'kind': 'break', 'row': key, 'person': None, 'text': '{} at line {} too short to turn over {} pack{}.'.format(
            'Break' if brk is not None and brk.is_break else 'Gap before the part', ix.line(key), n_packs,
            '' if n_packs == 1 else 's')})
    _shortages(plan, limits, ix)
    _busy(plan, day, n, S)
    return plan


def _suggest(day, S, behind, ix):
    """For each run of late or tight mics short of A2 time (mics whose
    release-to-finish windows overlap), the smallest pre-mic lead that puts
    every one of them on time with the same A2s, and whether one more A2
    would too. Both found by solving the day again, not estimated. Added to
    the run's first flag."""
    runs = []
    for act, flag in sorted((x for x in behind if x[1]['cause'] == 'a2'), key=lambda x: x[0].released):
        if runs and act.released < runs[-1]['end']:
            runs[-1]['items'].append((act, flag))
            runs[-1]['end'] = max(runs[-1]['end'], act.end_min)
        else:
            runs.append({'items': [(act, flag)], 'end': act.end_min})
    if not runs:
        return

    def on_time(plan, run):
        keys = {(a.appearance, a.backup) for a, _ in run['items']}
        return not any(a.kind == 'mic' and (a.appearance, a.backup) in keys and (a.late or a.tight)
                       for a in plan.actions)

    lead = {}
    for minutes in range(S.premic_lead_min + 1, LEAD_MAX + 1):
        if len(lead) == len(runs):
            break
        trial = solve(day, replace(S, premic_lead_min=minutes), suggest=False)
        for k, run in enumerate(runs):
            if k not in lead and on_time(trial, run):
                lead[k] = minutes
    more = solve(day, replace(S, a2_count=S.a2_count + 1), suggest=False)
    another = 'a second A2' if S.a2_count == 1 else 'one more A2'
    for k, run in enumerate(runs):
        a2 = on_time(more, run)
        fixes = (['pre-mic lead {} min (now {})'.format(lead[k], S.premic_lead_min)] if k in lead else []) + \
            ([another] if a2 else [])
        if fixes:
            text = 'Fix{}: {}.'.format('' if len(run['items']) == 1 else ' for these {} mics'.format(len(run['items'])),
                                       ', or '.join(fixes))
        else:
            text = 'No pre-mic lead up to {} min or extra A2 puts these on time.'.format(LEAD_MAX)
        act, flag = run['items'][0]
        flag['text'] += ' ' + text
        flag['fix'] = {'lead': lead.get(k), 'a2': a2, 'mics': len(run['items'])}
        first = ix.line(flag['row'])
        for _, other in run['items'][1:]:
            if ix.line(other['row']) != first:
                other['text'] += ' Fix: see line {}.'.format(first)


def _shortages(plan, limits, ix):
    """One flag per stretch of time with more packs of a pool in use than
    set, at the line where it starts, giving that stretch's peak."""
    worn = {}                 # (rf, appearance, backup) -> [start, end]
    for a in plan.actions:
        key = (a.rf_number, a.appearance, a.backup)
        if a.kind == 'mic':
            worn[key] = [a.start_min, INF, a]
        elif key in worn:
            worn[key][1] = a.end_min
    pools = {p.rf: p.pool for p in plan.packs}
    for pool, limit in limits.items():
        if limit is None:
            continue
        events = []
        for (rf, _, _), (t0, t1, mic) in worn.items():
            if pools.get(rf) == pool:
                events += [(t0, 1, mic), (t1, -1, None)]
        events.sort(key=lambda e: (e[0], e[1]))     # off before on at the same minute
        count, start, peak = 0, None, 0
        for t, step, mic in events:
            count += step
            if count > limit and start is None:
                start, peak = mic, count
            elif start is not None and count > peak:
                peak = count
            if start is not None and count <= limit:
                _flag_shortage(plan, ix, pool, limit, peak, start)
                start = None
        if start is not None:
            _flag_shortage(plan, ix, pool, limit, peak, start)


def _flag_shortage(plan, ix, pool, limit, peak, mic):
    app = plan.appearances[mic.appearance]
    more = peak - limit
    what = 'body pack' if pool == BODY else 'handheld'
    plan.flags.append({
        'kind': 'shortage', 'row': app.on_row, 'person': app.person,
        'text': 'Line {}: need {} more {}{} than the {} set ({} in use from {}).'.format(
            ix.line(app.on_row), more, what, '' if more == 1 else 's', limit, peak, hm(app.on))})


def _number(plan, packs, S, ix):
    order = ([p for p in packs if p.pool == BODY and p.backup_of is None]
             + [p for p in packs if p.pool == BODY and p.backup_of is not None]
             + [p for p in packs if p.pool == HH and p.backup_of is None]
             + [p for p in packs if p.pool == HH and p.backup_of is not None])
    for k, p in enumerate(order, 1):
        p.rf = k
    for a in plan.actions:
        a.rf_number = a._pack.rf
        del a._pack
    for s in plan.assignments:
        s.rf = s._pack.rf
        del s._pack
    hosts = {s.rf for s in plan.assignments if s.how == 'host' and not s.backup}
    for p in order:
        if p.backup_of is not None:
            label = '{} backup'.format(ix.people[p.backup_of].name)
        else:
            label = ''
        plan.packs.append(Pack(p.rf, p.pool, backup_of=p.backup_of, host=p.rf in hosts, label=label))
    if S.emergency_spare_hh:
        plan.packs.append(Pack(len(order) + 1, HH, spare=True, label='Spare'))
    # A swap: a pack going to someone other than who wore it last.
    plan.swaps = sum(1 for a in plan.actions if a.kind == 'mic' and a.reason == 'recycled')


def _owners(segments):
    """[(start, end, segment)] with no overlaps: where segments overlap (a
    "Doors" 7:00-8:30 holding a "Pre-Show" 7:45-8:30), a minute belongs to the
    one that started later, so no A2 minute is counted twice."""
    cuts = sorted({t for s in segments for t in (s.t0, s.t1)})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        live = [s for s in segments if s.t0 <= a and b <= s.t1]
        if live:
            out.append((a, b, max(live, key=lambda s: (s.t0, s.start))))
    return out


SPILL_FLAG_MIN = 5            # spill this long (or into a segment with a mic due) goes to Review


def _busy(plan, day, n, S):
    mins = {s.key: [0.0] * n for s in day.segments}
    by_part = {}
    for s in day.segments:
        by_part.setdefault(s.part, []).append(s)
    pieces = {part: _owners(segs) for part, segs in by_part.items()}
    for a in plan.actions:
        part = plan.appearances[a.appearance].part
        for t0, t1, s in pieces.get(part, ()):
            overlap = min(a.end_min, t1) - max(a.start_min, t0)
            if overlap > 0:
                mins[s.key][a.a2_index - 1] += overlap
    for s in day.segments:
        plan.busy[s.key] = [round(m, 1) for m in mins[s.key]]

    # Spill: work a segment owes (de-mics released in it, mics due in it)
    # still going after it ends. Segments shorter than a mic are left out:
    # nothing fits in them, so they always "spill".
    def owner(part, t):
        return next((s for t0, t1, s in pieces.get(part, ()) if t0 <= t < t1), None)

    for part, segs in by_part.items():
        acts = [a for a in plan.actions if plan.appearances[a.appearance].part == part]
        for s in segs:
            if s.t1 - s.t0 < S.mic_min:
                continue
            owed = [a for a in acts if owner(part, a.released if a.kind == 'demic' else a.due) is s]
            end = max((a.end_min for a in owed), default=s.t1)
            if end <= s.t1 + 0.01:
                continue
            into = owner(part, s.t1)
            minutes = int(round(end - s.t1))
            plan.spill[s.key] = {'minutes': minutes, 'into': into.key if into else None}
            mic_due = into is not None and any(
                a.kind == 'mic' and a.due is not None and into.t0 <= a.due < into.t1 for a in acts)
            if minutes >= SPILL_FLAG_MIN or mic_due:
                plan.flags.append({
                    'kind': 'spill', 'row': s.key, 'person': None,
                    'text': 'Line {}: the A2 is still busy {} min after "{}" ends at {}{}{}.'.format(
                        ix_line(day, s.key), minutes, s.name or 'this segment', hm(s.t1),
                        ', into "{}"'.format(into.name) if into else '',
                        ' where a mic is due' if mic_due else '')})


def ix_line(day, key):
    row = next((r for r in day.rows if r.key == key), None)
    return (row.line or '#{}'.format(row.order + 1)) if row else '?'


def summary(plan):
    """Counts for reports and stat tiles."""
    regular = [p for p in plan.packs if not p.spare]
    return {
        'body': sum(1 for p in regular if p.pool == BODY),
        'hh': sum(1 for p in regular if p.pool == HH),
        'hosts': sum(1 for p in regular if p.host),
        'backups': sum(1 for p in regular if p.backup_of is not None),
        'spare': sum(1 for p in plan.packs if p.spare),
        'swaps': plan.swaps,
        'mid_session': plan.mid_session,
        'late': sum(1 for f in plan.flags if f['kind'] == 'late'),
        'tight': sum(1 for f in plan.flags if f['kind'] == 'tight'),
        'shortage': sum(1 for f in plan.flags if f['kind'] == 'shortage'),
        'spill': sum(1 for f in plan.flags if f['kind'] == 'spill'),
    }
