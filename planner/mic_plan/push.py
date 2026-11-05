"""Send a day's stored Mic Plan to Mic Tracker (PR 5): the only Mic Plan code
that writes Mic Tracker data.

``preview`` works out every change and writes nothing; ``apply`` works it
out again inside one transaction, checks it is still what the editor saw
(``Preview.digest``) and writes it. Both read the stored plan, never
re-solve.

The plan's sessions are its sessions between breaks (schedule.sessions, the
rule the plan was made with). Each becomes a MicSession with one row
(MicAssignment) per RF it needs, rf_number = the plan's RF, and one
PresenterSlot per wearing of that RF, in wearing order. A host's row is in
the sessions they are on stage in only; a backup is its own row ("backup
for <name>"); the emergency spare is a row with no presenter ("SPARE") in
every session. Those words and "host" go in the slot's notes, which the A1
and A2 views show. Every pushed session has a card for each channel (PR
5.4): RF 1..N of the rig (1..the day's highest RF with no rig), the ones
nobody wears in it an empty row, as a hand-built session's are. Sessions it
writes are ``rf_from_plan``: nothing renumbers them.

A push stores what it matched (MicPlanPush maps) and what it wrote
(snapshots). The next push matches through the maps, so a slot keeps its pk
and with it the A2's photo, notes and settings; a value that differs from
the snapshot was changed in Mic Tracker, and is replaced unless the editor
keeps it.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import time as dtime

from django.db import transaction
from django.db.models import Max

from planner.models import (
    MICD_Q, MicAssignment, MicPlan, MicPlanAppearance, MicPlanPush, MicSession, Presenter, PresenterSlot,
    ShowflowPerson,
)

from planner.utils.typed_names import loose

from . import mt_rows
from .display import rig_text, swap_line, swap_words, tx_note
from .planning import BEFORE_RIG, before_rig, plan_rig, plan_values
from .importer import active_parts
from .schedule import segment_key, sessions as session_numbers
from .solver import HH, hm

MAX_ROWS = 100                       # MicSession.num_mics' upper bound
INF = float('inf')
NAME_MAX = 200

# Slot fields the push owns, and those it writes only while the A2 has not
# changed them (current value still what the last push wrote).
OWNED = ('presenter', 'row', 'order')
GENTLE = ('mic_type', 'notes')


class PushRefused(Exception):
    """``str(e)`` says why; ``status`` is the HTTP status for it."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def last_push(day):
    """The day's latest push that has not been reverted (revert.py)."""
    return MicPlanPush.objects.filter(day=day).exclude(summary__has_key='reverted').first()


def refusal(plan, apps):
    """Why ``plan`` cannot be sent, or ''."""
    if plan is None:
        return 'There is no plan for this day yet.'
    if plan.stale:
        return 'The showflow changed after this plan was made. Re-generate it first.'
    conflicts = sum(1 for f in plan.flags if f['kind'] == 'conflict')
    if conflicts:
        return 'The plan has {} RF conflict{}. Fix {} on the Review tab first.'.format(
            conflicts, '' if conflicts == 1 else 's', 'it' if conflicts == 1 else 'them')
    if any(a.is_host and not a.stage for a in apps):
        return 'This plan was made before Send to Mic Tracker existed. Re-generate it first.'
    if before_rig(plan):
        return BEFORE_RIG
    return ''


def short_of_rig(plan):
    """'The rig is short by 2 body packs (RF 25–26). ...' while the plan
    has packs past the rig's end (solver: over), or ''. The preview shows it
    and cannot be confirmed."""
    over = sorted((p for p in plan.packs if p.get('over')), key=lambda p: p['rf'])
    if not over:
        return ''
    what = []
    for pool, word in (('body', 'body pack'), (HH, 'handheld')):
        n = sum(1 for p in over if p['pool'] == pool)
        if n:
            what.append('{} {}{}'.format(n, word, '' if n == 1 else 's'))
    return 'The rig is short by {} (RF {}). Add channels, or move people, then send.'.format(
        ' and '.join(what), rf_span([p['rf'] for p in over]))


def rf_span(rfs):
    """'25', '25–26', '1–7, 10, 14–23' for sorted RFs."""
    runs = []
    for rf in rfs:
        if runs and rf == runs[-1][1] + 1:
            runs[-1][1] = rf
        else:
            runs.append([rf, rf])
    return ', '.join(str(a) if a == b else '{}\u2013{}'.format(a, b) for a, b in runs)


def cards_text(rows):
    """'12 cards: 9 with presenters, 3 empty' (', 1 spare' when there is one)."""
    spare = sum(1 for r in rows if r['label'] == 'SPARE')
    empty = sum(1 for r in rows if not r['wearings'])
    out = '{} card{}: {} with presenter{}, {} empty'.format(
        len(rows), '' if len(rows) == 1 else 's', len(rows) - spare - empty, '' if len(rows) - spare - empty == 1 else 's',
        empty)
    return out + (', {} spare'.format(spare) if spare else '')


# --------------------------------------------------------------------------
# What the plan wants
# --------------------------------------------------------------------------

def plan_sessions(plan, parts):
    """The plan's sessions in run-of-show order: [{key, name, t0, t1, start,
    end}]. ``start``/``end`` bound the minutes that belong to it (the first
    is open below, the last above)."""
    numbers = {p.pk: k + 1 for k, p in enumerate(parts)}
    of = session_numbers(plan.segments)
    groups = {}
    for s in plan.segments:
        groups.setdefault(of[s['row']], []).append(s)
    out = []
    for n in sorted(groups):
        segs = sorted(groups[n], key=lambda s: s['t0'])
        talk = [s for s in segs if not s['is_break']]
        head = talk[0] if talk else segs[0]
        t1 = max(s['t1'] for s in segs)
        out.append({'key': segment_key(segs[0], numbers), 't0': head['t0'], 't1': t1,
                    'first': min(s['t0'] for s in segs),
                    'name': '{} ({}-{})'.format(head['name'] or 'Session', clock(head['t0']), clock(t1))[:NAME_MAX]})
    for k, s in enumerate(out):
        s['start'] = s['first'] if k else -INF
        s['end'] = out[k + 1]['first'] if k + 1 < len(out) else INF
    return out


def clock(t):
    """'8:00' in a session name: the plan's clock without its a/p."""
    return hm(t)[:-1]


def _spans(app):
    return [tuple(x) for x in app.stage] if app.is_host else [(app.on_min, app.off_min)]


def _in(span, sess):
    """First minute of ``span`` inside ``sess``, or None."""
    a, b = span
    if a < sess['end'] and (b > sess['start'] if b > a else a >= sess['start']):
        return max(a, sess['start'])
    return None


def wanted(plan, apps, parts):
    """[{session..., rows: [{rf, pool, notes, wearings: [...]}]}]: the
    sessions that have someone to mic. A wearing: {keys, person, name, host,
    order}; ``keys`` are its slot keys, the first one its own."""
    sessions = plan_sessions(plan, parts)
    packs = {p['rf']: p for p in plan.packs}
    R = plan_rig(plan)
    # (rf, appearance key) -> the transmitter swap that wearing needs.
    swaps = {(p['rf'], w['appearance']): w for p in plan.packs for w in p.get('swaps') or ()}
    worn = {}                        # (session index, rf) -> [(on, app key, app, backup)]
    for app in apps:
        for a in app.assignments.all():
            for k, sess in enumerate(sessions):
                ons = [m for m in (_in(span, sess) for span in _spans(app)) if m is not None]
                if ons:
                    worn.setdefault((k, a.rf_number), []).append((min(ons), app.key, app, a.backup))
    spares = [p['rf'] for p in plan.packs if p.get('spare')]
    # A card for every channel: the rig's, or (no rig) up to the day's highest RF.
    top = R.channels if R.set else max((p['rf'] for p in plan.packs), default=0)
    out = []
    for k, sess in enumerate(sessions):
        rows = []
        for rf in sorted(rf for (j, rf) in worn if j == k):
            wearings = []
            for on, _, app, backup in sorted(worn[(k, rf)], key=lambda w: (w[0], w[1])):
                key = '{}#{}{}'.format(sess['key'], app.skey, '#backup' if backup else '')
                last = wearings[-1] if wearings else None
                pool = packs.get(rf, {}).get('pool', 'body') if backup else app.mic_type
                if last and (last['person'], last['name']) == (app.person_id, app.person_name):
                    last['keys'].append(key)
                    last['host'] = last['host'] or app.is_host
                    last['apps'].append(app.key)
                    continue
                wearings.append({'keys': [key], 'person': app.person_id, 'name': app.person_name,
                                 'host': app.is_host and not backup, 'backup': backup, 'pool': pool,
                                 'apps': [app.key]})
            backup = all(w['backup'] for w in wearings)
            rows.append({'rf': rf, 'pool': wearings[0]['pool'], 'notes': '',
                         'label': 'backup for {}'.format(wearings[0]['name']) if backup else '',
                         'wearings': wearings})
        if not rows:
            continue
        for rf in spares:
            rows.append({'rf': rf, 'pool': HH, 'notes': '', 'label': 'SPARE',
                         'wearings': [{'keys': ['{}#spare|{}'.format(sess['key'], rf)], 'person': None,
                                       'name': '', 'host': False, 'backup': False, 'pool': HH, 'apps': []}]})
        # The channels nobody wears in this session: empty cards (no slot,
        # blank mic type), as Mic Tracker makes them for a session by hand.
        have = {r['rf'] for r in rows}
        rows += [{'rf': rf, 'pool': '', 'notes': '', 'label': '', 'wearings': [], 'empty': True}
                 for rf in range(1, top + 1) if rf not in have]
        rows.sort(key=lambda r: r['rf'])
        for row in rows:
            zone = R.pool_at(row['rf']) if R.set else None
            for k2, w in enumerate(row['wearings']):
                w['order'] = k2
                w['mic_type'] = 'HH' if w['pool'] == HH else ''
                # On the slot, not the row: the A1 Notes column and the A2
                # card both show the slot's notes (the row's shows on /m/ only).
                # Then the transmitter it needs, when not its channel's zone
                # type, and the swap to it.
                notes = ['host' if w['host'] else row['label']]
                if w['person'] is not None:
                    notes.append(tx_note(w['pool'], zone))
                    swap = next((swaps[(row['rf'], k3)] for k3 in w['apps'] if (row['rf'], k3) in swaps), None)
                    if swap is not None:
                        notes.append('{} {}'.format(swap_line(row['rf'], swap['to']), swap_words(swap)))
                w['notes'] = ' \u00b7 '.join(n for n in notes if n)
        out.append(dict(sess, rows=rows, cards=cards_text(rows)))
    return out


# --------------------------------------------------------------------------
# Preview: every change, nothing written
# --------------------------------------------------------------------------

@dataclass
class Preview:
    plan: object
    last: object
    items: list = field(default_factory=list)      # see _item
    started: list = field(default_factory=list)    # [{pk, name}] sessions with a MIC'D mic
    new_presenters: list = field(default_factory=list)
    matched_presenters: list = field(default_factory=list)
    labels: list = field(default_factory=list)     # ['RF 3 (Opening Session (8:00-8:45))', ...]
    new_sessions: list = field(default_factory=list)   # names: print all their labels
    targets: list = field(default_factory=list)
    short: str = ''                                # short_of_rig: no confirm
    rig: str = ''                                  # the plan's rig, in words
    rig_was: str = ''                              # the last push's, when it differs
    matched: dict = field(default_factory=dict)    # session key -> MicSession pk
    claims: dict = field(default_factory=dict)     # slot key -> existing PresenterSlot pk
    refs: dict = field(default_factory=dict)       # person key -> presenter ref
    digest: str = ''

    def group(self, name, shown=False):
        """Items of ``group``; ``shown``: without those listed in another's line."""
        return [i for i in self.items if i['group'] == name and not (shown and i['data'].get('quiet'))]

    @property
    def changes(self):
        return [i for i in self.items if i['group'] != 'kept']


def _item(group, kind, text, session=None, rf=None, touch=(), item_id='', **data):
    """One change. ``group``: create | update | remove | mt (changed in Mic
    Tracker since the last push: replaced unless kept) | kept (shown only).
    ``touch``: the MicSession pks it writes to (skipped if one has started)."""
    return {'group': group, 'kind': kind, 'text': text, 'session': session, 'rf': rf,
            'touch': sorted(t for t in touch if t), 'id': item_id, 'data': data}


def _presenter_refs(day, wearings):
    """{person key: ref}; ref {'pk', 'name', 'link'} or {'new': name, 'link'}.
    A person linked in People uses that Presenter; otherwise a Presenter of
    the same name (Presenter.resolve) or a new one. ``link``: save it back
    to the person."""
    people = {p.pk: p for p in ShowflowPerson.objects.filter(day=day).select_related('presenter')}
    refs = {}
    for w in wearings:
        if w['person'] is None and not w['name']:
            continue
        key = w['person'] if w['person'] is not None else 'name:' + w['name']
        if key in refs:
            continue
        person = people.get(w['person'])
        if person is not None and person.presenter_id:
            refs[key] = {'pk': person.presenter_id, 'name': person.presenter.name, 'link': False}
            continue
        name = ' '.join(((person.display_name if person else '') or w['name']).split())
        found = Presenter.objects.filter(project_id=day.project_id, name__iexact=name).order_by('id').first()
        if found:
            refs[key] = {'pk': found.pk, 'name': found.name, 'link': person is not None, 'matched': True}
        else:
            refs[key] = {'new': name, 'name': name, 'link': person is not None}
    return refs


def _ref_of(refs, w):
    if w['person'] is None and not w['name']:
        return None
    return refs[w['person'] if w['person'] is not None else 'name:' + w['name']]


def _blank(slot):
    return (slot.presenter_id is None and not slot.photo_data and not slot.photo and not slot.notes
            and not slot.is_micd and not slot.placement and not slot.sensitivity and not slot.output_level)


def _a2_data(slot, snap):
    """Why ``slot`` must not be removed ('' if it may): a photo, notes the
    A2 wrote, or mic'd."""
    if slot.photo_data or slot.photo:
        return 'photo'
    if slot.is_micd:
        return "MIC'D"
    if slot.notes and slot.notes != (snap or {}).get('notes', ''):
        return 'notes'
    return ''


def _row_a2_data(row, snap):
    if row.is_micd:
        return "MIC'D"
    if row.photo:
        return 'photo'
    if row.notes and row.notes != (snap or {}).get('notes', ''):
        return 'notes'
    return ''


def _time(minute):
    m = int(round(minute)) % (24 * 60)
    return dtime(m // 60, m % 60)


def _label(sess, rf):
    return 'RF {} · {}'.format(rf, sess)


def preview(day, plan=None):
    """Every change sending ``day``'s plan would make. Raises PushRefused."""
    plan = plan or MicPlan.objects.filter(day=day).first()
    apps = list(MicPlanAppearance.objects.filter(plan=plan).prefetch_related('assignments')) if plan else []
    why = refusal(plan, apps)
    if why:
        raise PushRefused(why, 404 if plan is None else 409)
    targets = wanted(plan, apps, active_parts(day))
    for t in targets:
        if len(t['rows']) > MAX_ROWS:
            raise PushRefused('{} needs {} RFs; Mic Tracker holds at most {} per session.'.format(
                t['name'], len(t['rows']), MAX_ROWS))
    last = last_push(day)
    out = Preview(plan=plan, last=last, targets=targets, short=short_of_rig(plan), rig=rig_text(plan_values(plan)))
    was = (last.summary or {}).get('rig') if last else None
    if was and was != out.rig:
        out.rig_was = was
    prev_sessions = dict(last.sessions) if last else {}
    prev_rows = dict(last.rows) if last else {}
    prev_slots = dict(last.slots) if last else {}
    sess_snap = last.session_snapshot if last else {}
    row_snap = last.row_snapshot if last else {}
    slot_snap = last.slot_snapshot if last else {}

    mt_sessions = {s.pk: s for s in MicSession.objects.filter(day=day)}
    names = {s.pk: s.name for s in mt_sessions.values()}

    # Sessions: through the last push's map, then by name (case, dashes and
    # spaces aside: pushes before #174 wrote an en dash).
    matched, claimed = {}, set()
    for t in targets:
        pk = prev_sessions.get(t['key'])
        if pk in mt_sessions and pk not in claimed:
            matched[t['key']] = pk
            claimed.add(pk)
    for t in targets:
        if t['key'] in matched:
            continue
        pk = next((s.pk for s in sorted(mt_sessions.values(), key=lambda s: (s.order, s.pk))
                   if loose(s.name) == loose(t['name']) and s.pk not in claimed), None)
        if pk is not None:
            matched[t['key']] = pk
            claimed.add(pk)
    started_pks = set(MicAssignment.objects.filter(session__day=day).filter(MICD_Q)
                      .values_list('session_id', flat=True))

    rows = {}                        # (session pk, rf) -> MicAssignment
    for r in MicAssignment.objects.filter(session__day=day).prefetch_related('presenter_slots__presenter'):
        rows[(r.session_id, r.rf_number)] = r
    slots = {}
    for r in rows.values():
        for s in r.presenter_slots.all():
            slots[s.pk] = s
    by_key = {k: pk for k, pk in prev_slots.items() if pk in slots}
    by_skey = {}
    for k, pk in by_key.items():
        by_skey.setdefault(k.split('#', 1)[1], []).append(pk)

    refs = _presenter_refs(day, [w for t in targets for r in t['rows'] for w in r['wearings']])
    out.new_presenters = sorted({r['new'] for r in refs.values() if 'new' in r})
    out.matched_presenters = sorted({r['name'] for r in refs.values() if r.get('matched')})

    for t in targets:
        pk = matched.get(t['key'])
        if pk is None:
            # One line: its rows and slots are listed in it, not one by one.
            what = []
            for row in t['rows']:
                if not row['wearings']:
                    continue                 # an empty card: counted, not listed
                who = ', '.join((_ref_of(refs, w) or {}).get('name', '') + (' (host)' if w['notes'] == 'host' else '')
                                for w in row['wearings'] if _ref_of(refs, w))
                what.append('RF {} {}'.format(row['rf'], ' — '.join(x for x in (who, row['label']) if x)))
            out.items.append(_item('create', 'session_create', 'New session {} ({}): {}'.format(
                t['name'], t['cards'], ' · '.join(what)),
                session=t['key'], name=t['name'], t0=t['t0'], t1=t['t1']))
            out.new_sessions.append(t['name'])
            continue
        s = mt_sessions[pk]
        want = {'name': t['name'], 'start_time': _time(t['t0']).isoformat(), 'end_time': _time(t['t1']).isoformat()}
        have = {'name': s.name, 'start_time': s.start_time.isoformat() if s.start_time else '',
                'end_time': s.end_time.isoformat() if s.end_time else ''}
        snap = sess_snap.get(str(pk))
        set_, mt = {}, {}
        for f, v in want.items():
            if have[f] == v:
                continue
            if snap is None:
                if f == 'name' or not have[f]:
                    set_[f] = v            # a session matched by name: fill its times only if blank
            elif have[f] == snap.get(f):
                set_[f] = v
            else:
                mt[f] = [snap.get(f), have[f], v]
        if set_ or mt:
            what = ', '.join('{} {} → {}'.format(f.replace('_', ' '), have[f] or '—', v)
                             for f, v in {**set_, **{f: x[2] for f, x in mt.items()}}.items())
            out.items.append(_item('mt' if mt else 'update', 'session_update', '{}: {}'.format(s.name, what),
                                   session=t['key'], touch=[pk], item_id='keep_session_{}'.format(pk),
                                   pk=pk, set=set_, mt={f: x[2] for f, x in mt.items()}))

    # Slots: claim through the map, over the whole day before falling back,
    # so one session never takes another's slot: first each wearing's own
    # key, then the same appearance in another session (it moved), then an
    # empty slot on its row. Anything left is created.
    every = []
    for t in targets:
        spk = matched.get(t['key'])
        for row in t['rows']:
            for w in row['wearings']:
                every.append((t, row, w, rows.get((spk, row['rf'])) if spk else None))
    claim, taken = {}, set()

    def take(n, pk):
        claim[n] = pk
        taken.add(pk)

    for n, (t, row, w, existing) in enumerate(every):
        pk = next((by_key[k] for k in w['keys'] if k in by_key and by_key[k] not in taken), None)
        if pk is not None:
            take(n, pk)
    for n, (t, row, w, existing) in enumerate(every):
        if n in claim:
            continue
        pk = next((p for k in w['keys'] for p in by_skey.get(k.split('#', 1)[1], ()) if p not in taken), None)
        if pk is not None:
            take(n, pk)
    for n, (t, row, w, existing) in enumerate(every):
        if n in claim or existing is None:
            continue
        pk = next((s.pk for s in existing.presenter_slots.all()
                   if s.pk not in taken and s.pk not in prev_slots.values() and _blank(s)), None)
        if pk is not None:
            take(n, pk)
    claimed = {id(w): claim.get(n) for n, (_, _, w, _) in enumerate(every)}
    # Every existing slot the plan keeps, changed or not: the next push's map.
    out.claims = {k: pk for n, (_, _, w, _) in enumerate(every) for k in w['keys']
                  for pk in [claim.get(n)] if pk is not None}

    after = {}                       # (session key, rf) -> [presenter names], for labels
    for t in targets:
        spk = matched.get(t['key'])
        for row in t['rows']:
            existing = rows.get((spk, row['rf'])) if spk else None
            where = _label(t['name'], row['rf'])
            if existing is None:
                # Shown with its first slot (or in its new session's line).
                out.items.append(_item('create', 'row_create', '', session=t['key'], rf=row['rf'], touch=[spk],
                                       notes=row['notes'], mic_type='HH' if row['pool'] == HH else '', quiet=True))
            else:
                snap = row_snap.get(str(existing.pk))
                if existing.notes != row['notes']:
                    if (snap is None and not existing.notes) or (snap is not None and existing.notes == snap.get('notes')):
                        out.items.append(_item('update', 'row_update', '{}: row note {}'.format(
                            where, '“{}”'.format(row['notes']) if row['notes'] else 'cleared'), session=t['key'], rf=row['rf'], touch=[spk],
                            pk=existing.pk, notes=row['notes']))
            after[(t['key'], row['rf'])] = [_ref_of(refs, w)['name'] if _ref_of(refs, w) else ''
                                            for w in row['wearings']]
            for w in row['wearings']:
                ref = _ref_of(refs, w)
                who = ref['name'] if ref else 'no presenter'
                pk = claimed[id(w)]
                if pk is None:
                    new_row = existing is None and w['order'] == 0
                    out.items.append(_item('create', 'slot_create', '{}: {}{}{}'.format(
                        where, who, ' (host)' if w['notes'] == 'host' else '',
                        ' — new row{}'.format(', ' + row['label'] if row['label'] else '') if new_row else ''),
                        session=t['key'], rf=row['rf'], touch=[spk], keys=w['keys'], ref=ref, person=w['person'],
                        order=w['order'], mic_type=w['mic_type'], notes=w['notes'], first=new_row,
                        quiet=spk is None))
                    continue
                slot = slots[pk]
                out.items.extend(_slot_change(slot, slot_snap.get(str(pk)), w, ref, t, row, spk, mt_sessions, names))

    # Empty cards a session already in Mic Tracker gains (one line each).
    for t in targets:
        spk = matched.get(t['key'])
        added = [r['rf'] for r in t['rows'] if spk and not r['wearings'] and (spk, r['rf']) not in rows]
        if added:
            out.items.append(_item('create', 'cards_added', '{}: {} empty card{} added (RF {})'.format(
                t['name'], len(added), '' if len(added) == 1 else 's', rf_span(added)), session=t['key'],
                touch=[spk]))

    # What the plan no longer has.
    for pk, slot in slots.items():
        if pk in taken or pk not in prev_slots.values():
            continue
        row = slot.assignment
        where = _label(names.get(row.session_id, ''), row.rf_number)
        who = slot.presenter.name if slot.presenter else 'no presenter'
        why = _a2_data(slot, slot_snap.get(str(pk)))
        if why:
            out.items.append(_item('kept', 'slot_kept', '{}: {} kept — has A2 data ({})'.format(where, who, why),
                                   rf=row.rf_number, touch=[row.session_id], pk=pk))
        else:
            out.items.append(_item('remove', 'slot_remove', '{}: remove {}'.format(where, who), rf=row.rf_number,
                                   touch=[row.session_id], pk=pk))
    wanted_rows = {(matched.get(t['key']), r['rf']) for t in targets for r in t['rows']}
    for pk in set(prev_rows.values()):
        row = next((r for r in rows.values() if r.pk == pk), None)
        if row is None or (row.session_id, row.rf_number) in wanted_rows:
            continue
        where = _label(names.get(row.session_id, ''), row.rf_number)
        why = _row_a2_data(row, row_snap.get(str(pk)))
        if why:
            out.items.append(_item('kept', 'row_kept', '{}: row kept — has A2 data ({})'.format(where, why),
                                   rf=row.rf_number, touch=[row.session_id], pk=pk))
        else:
            out.items.append(_item('remove', 'row_remove', '{}: remove the row if nothing is left on it'.format(where),
                                   rf=row.rf_number, touch=[row.session_id], pk=pk))
    for key, pk in prev_sessions.items():
        if pk in mt_sessions and pk not in matched.values():
            out.items.append(_item('remove', 'session_remove', '{}: remove the session if nothing is left in it'.format(
                names[pk]), touch=[pk], pk=pk))

    # Labels: every RF whose presenters change (a new session: all of its).
    before = {}
    for t in targets:
        spk = matched.get(t['key'])
        if spk is None:
            continue
        for row in t['rows']:
            existing = rows.get((spk, row['rf'])) if spk else None
            before[(t['key'], row['rf'])] = [s.presenter.name if s.presenter else ''
                                             for s in (existing.presenter_slots.all() if existing else ())]
    for t in targets:
        if matched.get(t['key']) is None:
            continue
        for row in t['rows']:
            k = (t['key'], row['rf'])
            if [n for n in after[k] if n] != [n for n in before[k] if n]:
                out.labels.append('RF {} ({})'.format(row['rf'], t['name']))

    out.started = [{'pk': pk, 'name': names[pk]} for pk in sorted(started_pks, key=lambda p: mt_sessions[p].order)
                   if any(pk in i['touch'] for i in out.items)]
    out.matched = matched
    out.refs = refs
    out.digest = hashlib.sha256(json.dumps(
        [plan.version, last.pk if last else None, out.items], sort_keys=True, default=str).encode()).hexdigest()[:20]
    return out


def _slot_change(slot, snap, w, ref, t, row, spk, mt_sessions, names):
    """Items updating ``slot`` to wearing ``w`` (none if nothing changes)."""
    cur = {'presenter': slot.presenter_id, 'row': [slot.assignment.session_id, slot.assignment.rf_number],
           'order': slot.order, 'mic_type': slot.mic_type, 'notes': slot.notes}
    target = {'presenter': ref['pk'] if ref and 'pk' in ref else (ref and 'new'), 'row': [spk, row['rf']],
              'order': w['order'], 'mic_type': w['mic_type'], 'notes': w['notes']}
    set_, mt = {}, {}
    for f in OWNED:
        if cur[f] == target[f]:
            continue
        if snap is not None and f in snap and cur[f] != snap[f]:
            mt[f] = target[f]
        else:
            set_[f] = target[f]
    for f in GENTLE:
        if cur[f] != target[f] and cur[f] == ((snap or {}).get(f, '') if snap is not None else ''):
            set_[f] = target[f]
    if not set_ and not mt:
        return []
    who_now = slot.presenter.name if slot.presenter else 'no presenter'
    who = ref['name'] if ref else 'no presenter'
    where = _label(t['name'], row['rf'])
    bits = []
    changes = {**set_, **mt}
    if 'presenter' in mt:
        bits.append('Mic Tracker has {}, the plan {}'.format(who_now, who))
    elif 'presenter' in changes:
        bits.append('{} → {}'.format(who_now, who))
    if 'row' in changes and cur['row'][0] == spk:
        bits.append('{} RF {} \u2192 RF {}'.format(who, cur['row'][1], row['rf']))
    elif 'row' in changes:
        bits.append('{} moves from {}'.format(who, _label(names.get(cur['row'][0], 'another session'), cur['row'][1])))
    if 'order' in changes and not bits:
        bits.append('{} {} in the rotation'.format(who, 'first' if w['order'] == 0 else 'number {}'.format(w['order'] + 1)))
    if 'mic_type' in changes and not bits:
        bits.append('{} mic type → {}'.format(who, 'handheld' if w['mic_type'] == 'HH' else 'blank'))
    if 'notes' in changes and not bits:
        bits.append('{} note → “{}”'.format(who, w['notes']))
    if set(mt) - {'presenter'}:
        bits.append('Mic Tracker has {}'.format(', '.join(_mt_words(f, cur, names) for f in mt if f != 'presenter')))
    touch = [cur['row'][0], spk]
    return [_item('mt' if mt else 'update', 'slot_update', '{}: {}'.format(where, '; '.join(bits)), session=t['key'],
                  rf=row['rf'], touch=touch, item_id='keep_slot_{}'.format(slot.pk), pk=slot.pk,
                  set={f: v for f, v in set_.items() if f != 'presenter'}, mt={f: v for f, v in mt.items() if f != 'presenter'},
                  presenter=('mt' if 'presenter' in mt else 'set') if 'presenter' in changes else '',
                  ref=ref, person=w['person'], keys=w['keys'], target_session=t['key'])]


def _mt_words(f, cur, names):
    if f == 'row':
        return _label(names.get(cur['row'][0], '?'), cur['row'][1])
    return 'its own order'


# --------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------

SLOT_FIELDS = ('assignment_id', 'presenter_id', 'order', 'is_active', 'mic_type', 'notes')
ROW_FIELDS = ('session_id', 'rf_number', 'notes', 'mic_type')
SESSION_FIELDS = ('day_id', 'name', 'start_time', 'end_time', 'order', 'num_mics', 'rf_from_plan')


def _values(obj, fields):
    return {f: (v.isoformat() if hasattr(v, 'isoformat') else v) for f, v in ((f, getattr(obj, f)) for f in fields)}


@transaction.atomic
def apply(day, version, digest, keep=(), include_started=False, user=None):
    """Write the preview the editor confirmed. ``keep``: the ids of
    "changed in Mic Tracker" items to leave as Mic Tracker has them.
    Returns the MicPlanPush, or None when Mic Tracker already matches the
    version last sent (nothing is written, not even a push record). A newer
    version with nothing to change is recorded, writing no Mic Tracker row."""
    plan = MicPlan.objects.select_for_update().filter(day=day).first()
    if plan is None:
        raise PushRefused('There is no plan for this day yet.', 404)
    if version != plan.version:
        raise PushRefused('The plan changed while you were looking at the preview (now v{}). '
                          'Review it again.'.format(plan.version), 409)
    p = preview(day, plan)
    if p.short:
        raise PushRefused(p.short, 409)
    if digest != p.digest:
        raise PushRefused('Mic Tracker or the plan changed since the preview. Review it again.', 409)
    if not p.changes and p.last is not None and p.last.plan_version == plan.version:
        return None                   # Mic Tracker already matches this version: nothing to write or record
    keep = set(keep)
    started = {s['pk'] for s in p.started}
    skipped = set() if include_started else started
    items = [i for i in p.items if not (set(i['touch']) & skipped)]
    before = {'created': [], 'updated': [], 'deleted': []}

    def updated(obj, fields, model):
        before['updated'].append([model, obj.pk, _values(obj, fields)])

    # Presenters (resolve creates a new one only when no one has the name).
    presenters = {}

    def presenter(ref):
        if ref is None:
            return None
        if 'pk' in ref:
            return ref['pk']
        if ref['new'] not in presenters:
            existed = Presenter.objects.filter(project_id=day.project_id, name__iexact=ref['new']).exists()
            obj = Presenter.resolve(ref['new'], day.project_id)
            if not existed:
                before['created'].append(['presenter', obj.pk])
            presenters[ref['new']] = obj.pk
        return presenters[ref['new']]

    links = {}                                      # person pk -> ref, for the people it writes

    def used(d):
        ref = d.get('ref')
        if ref and ref.get('link') and d.get('person') is not None:
            links[d['person']] = ref

    # Sessions.
    sessions = dict(p.matched)                      # session key -> pk
    order = (MicSession.objects.filter(day=day).aggregate(m=Max('order'))['m'])
    order = -1 if order is None else order
    for t in p.targets:
        if t['key'] in sessions:
            continue
        order += 1
        s = MicSession.objects.create(day=day, name=t['name'], start_time=_time(t['t0']), end_time=_time(t['t1']),
                                      num_mics=max(1, len(t['rows'])), order=order, rf_from_plan=True)
        before['created'].append(['micsession', s.pk])
        sessions[t['key']] = s.pk
    live = {s.pk: s for s in MicSession.objects.select_for_update().filter(pk__in=sessions.values())}
    for pk, s in live.items():
        if pk not in skipped and not s.rf_from_plan:
            updated(s, ('rf_from_plan',), 'micsession')
            s.rf_from_plan = True
            s.save(update_fields=['rf_from_plan'])
    for i in items:
        if i['kind'] != 'session_update':
            continue
        d = i['data']
        s = live[d['pk']]
        values = dict(d['set'])
        if i['id'] not in keep:
            values.update(d['mt'])
        if values:
            updated(s, list(values), 'micsession')
            for f, v in values.items():
                setattr(s, f, v if f == 'name' else dtime.fromisoformat(v))
            s.save(update_fields=list(values))

    # Rows.
    rows = {}
    for r in MicAssignment.objects.select_for_update().filter(session_id__in=sessions.values()):
        rows[(r.session_id, r.rf_number)] = r
    for i in items:
        d = i['data']
        if i['kind'] == 'row_create':
            spk = sessions[i['session']]
            r = MicAssignment.objects.create(session_id=spk, rf_number=i['rf'], notes=d['notes'],
                                             mic_type=d['mic_type'])
            before['created'].append(['micassignment', r.pk])
            rows[(spk, i['rf'])] = r
        elif i['kind'] == 'row_update':
            r = MicAssignment.objects.get(pk=d['pk'])
            updated(r, ('notes',), 'micassignment')
            r.notes = d['notes']
            r.save(update_fields=['notes'])

    # Slots. The map starts from every slot the plan keeps, changed or not.
    slot_keys = dict(p.claims)
    for i in items:
        d = i['data']
        if i['kind'] == 'slot_create':
            row = rows[(sessions[i['session']], i['rf'])]
            s = PresenterSlot.objects.create(assignment=row, presenter_id=presenter(d['ref']), order=d['order'],
                                             is_active=d['first'], mic_type=d['mic_type'], notes=d['notes'])
            used(d)
            before['created'].append(['presenterslot', s.pk])
            for k in d['keys']:
                slot_keys[k] = s.pk
        elif i['kind'] == 'slot_update':
            s = PresenterSlot.objects.select_for_update().get(pk=d['pk'])
            values = dict(d['set'])
            if i['id'] not in keep:
                values.update(d['mt'])
            if d['presenter'] == 'set' or (d['presenter'] == 'mt' and i['id'] not in keep):
                values['presenter'] = presenter(d['ref'])
                used(d)
            fields = {'row': 'assignment_id', 'presenter': 'presenter_id'}
            if values:
                updated(s, [fields.get(f, f) for f in values], 'presenterslot')
                for f, v in values.items():
                    if f == 'row':
                        s.assignment = rows[(sessions[d['target_session']], v[1])]
                    else:
                        setattr(s, fields.get(f, f), v)
                s.save(update_fields=[fields.get(f, f).replace('_id', '') if f == 'row' else fields.get(f, f)
                                      for f in values])
            for k in d['keys']:
                slot_keys[k] = s.pk
    for i in items:
        if i['kind'] == 'slot_remove':
            s = PresenterSlot.objects.filter(pk=i['data']['pk']).first()
            if s is not None:
                before['deleted'].append(['presenterslot', s.pk, mt_rows.full(s)])
                s.delete()
    removed_rows = set()
    for i in items:
        if i['kind'] == 'row_remove':
            r = MicAssignment.objects.filter(pk=i['data']['pk']).first()
            if r is not None and not r.presenter_slots.exists():
                before['deleted'].append(['micassignment', r.pk, mt_rows.full(r)])
                removed_rows.add(r.pk)
                r.delete()
    for i in items:
        if i['kind'] == 'session_remove':
            s = MicSession.objects.filter(pk=i['data']['pk']).first()
            if s is not None and not s.mic_assignments.exists():
                before['deleted'].append(['micsession', s.pk, mt_rows.full(s)])
                s.delete()

    # Links back to People, where there was none.
    for person_pk, ref in links.items():
        pk = presenter(ref)
        if ShowflowPerson.objects.filter(pk=person_pk, day=day, presenter__isnull=True).update(presenter_id=pk):
            before['updated'].append(['showflowperson', person_pk, {'presenter_id': None}])

    # num_mics follows the rows.
    for pk in set(sessions.values()) - skipped:
        s = MicSession.objects.filter(pk=pk).first()
        if s is None:
            continue
        n = s.mic_assignments.count()
        if n and s.num_mics != n:
            updated(s, ('num_mics',), 'micsession')
            MicSession.objects.filter(pk=pk).update(num_mics=n)

    # What this push left in every session it touched: a revert compares
    # Mic Tracker with it to list what changed there since.
    touched = set(sessions.values()) - skipped
    touched |= {pk for model, pk, *_ in before['created'] + before['updated'] + before['deleted']
                if model == 'micsession'}
    for model, pk, *rest in before['deleted']:
        if model == 'micassignment':
            touched.add(rest[0]['session_id'])
    before['scope'] = sorted(touched)
    before['after'] = mt_rows.state(touched)
    push = _record(day, plan, p, sessions, slot_keys, skipped, include_started, user, before, items, keep)
    return push


def _record(day, plan, p, sessions, slot_keys, skipped, include_started, user, before, items, keep=()):
    """The push record: maps and snapshots of what it wrote, carrying the
    last push's entries for skipped (started) sessions so the next push
    still knows them."""
    last = p.last
    out_sessions = {k: pk for k, pk in sessions.items() if MicSession.objects.filter(pk=pk).exists()}
    rows = {}
    for t in p.targets:
        spk = out_sessions.get(t['key'])
        for row in t['rows']:
            r = MicAssignment.objects.filter(session_id=spk, rf_number=row['rf']).first() if spk else None
            if r is not None:
                rows['{}|{}'.format(t['key'], row['rf'])] = r.pk
    slots = dict(slot_keys)
    if last and skipped:
        for k, pk in last.sessions.items():
            if pk in skipped:
                out_sessions.setdefault(k, pk)
        for k, pk in last.rows.items():
            if MicAssignment.objects.filter(pk=pk, session_id__in=skipped).exists():
                rows.setdefault(k, pk)
        for k, pk in last.slots.items():
            if PresenterSlot.objects.filter(pk=pk, assignment__session_id__in=skipped).exists():
                slots.setdefault(k, pk)
    old_slot = last.slot_snapshot if last else {}
    old_row = last.row_snapshot if last else {}
    old_sess = last.session_snapshot if last else {}
    want = {}                                   # slot pk -> what the plan wanted for it
    for t in p.targets:
        for row in t['rows']:
            for w in row['wearings']:
                pk = slots.get(w['keys'][0])
                if pk is not None:
                    want[pk] = (t, row, w)
    slot_snap = {}
    for s in PresenterSlot.objects.filter(pk__in=set(slots.values())).select_related('assignment'):
        prev = old_slot.get(str(s.pk), {})
        if s.assignment.session_id in skipped:
            if prev:
                slot_snap[str(s.pk)] = prev
            continue
        t, row, w = want.get(s.pk, (None, None, None))
        snap = {'presenter': s.presenter_id, 'row': [s.assignment.session_id, s.assignment.rf_number],
                'order': s.order, 'mic_type': s.mic_type, 'notes': s.notes}
        if w is not None:
            # What the plan wants, even where the editor kept Mic Tracker's:
            # a kept value stays "changed in Mic Tracker" next time.
            ref = p.refs.get(w['person'] if w['person'] is not None else 'name:' + w['name']) if w['name'] or w['person'] else None
            if ref is None:
                snap['presenter'] = None
            elif 'pk' in ref:
                snap['presenter'] = ref['pk']
            else:                      # made by this push, or not (kept): the plan's, by name
                snap['presenter'] = Presenter.objects.filter(
                    project_id=day.project_id, name__iexact=ref['new']).order_by('id').values_list('pk', flat=True).first()
            snap['row'] = [out_sessions.get(t['key']), row['rf']]
            snap['order'] = w['order']
            for f in GENTLE:
                if getattr(s, f) != w[f]:      # the A2's value, left alone: still theirs next time
                    snap[f] = prev.get(f, '')
        slot_snap[str(s.pk)] = snap
    row_snap = {}
    for r in MicAssignment.objects.filter(pk__in=set(rows.values())):
        if r.session_id in skipped and str(r.pk) in old_row:
            row_snap[str(r.pk)] = old_row[str(r.pk)]
            continue
        target = next((row for t in p.targets for row in t['rows']
                       if rows.get('{}|{}'.format(t['key'], row['rf'])) == r.pk), None)
        notes = r.notes
        if target is not None and r.notes != target['notes']:
            notes = old_row.get(str(r.pk), {}).get('notes', '')
        row_snap[str(r.pk)] = {'notes': notes, 'mic_type': r.mic_type}
    sess_snap = {}
    for t in p.targets:
        pk = out_sessions.get(t['key'])
        if pk is None:
            continue
        if pk in skipped and str(pk) in old_sess:
            sess_snap[str(pk)] = old_sess[str(pk)]
            continue
        sess_snap[str(pk)] = {'name': t['name'], 'start_time': _time(t['t0']).isoformat(),
                              'end_time': _time(t['t1']).isoformat()}
    summary = {
        'counts': dict({g: sum(1 for i in items if i['group'] == g and not i['data'].get('quiet'))
                        for g in ('create', 'update', 'remove', 'kept')},
                       mt=sum(1 for i in items if i['group'] == 'mt' and i['id'] not in keep),
                       mt_kept=sum(1 for i in items if i['group'] == 'mt' and i['id'] in keep)),
        'kept': [i['text'] for i in items if i['group'] == 'kept'],
        'skipped': [s['name'] for s in p.started if s['pk'] in skipped],
        'labels': p.labels,
        'rig': p.rig,
        'new_sessions': p.new_sessions,
        'new_presenters': p.new_presenters,
    }
    return MicPlanPush.objects.create(
        day=day, plan=plan, plan_version=plan.version, pushed_by=user, include_started=include_started,
        sessions=out_sessions, rows=rows, slots=slots, session_snapshot=sess_snap, row_snapshot=row_snap,
        slot_snapshot=slot_snap, before=before, summary=summary)
